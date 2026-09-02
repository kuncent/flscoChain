"""链客户端统一接口层。

支持三种后端，通过环境变量 CHAIN_MODE 切换：
  - fisco : 连接真实 FISCO-BCOS 节点（JSON-RPC + FISCO v2 原生交易格式签名广播）
  - evm   : py-evm / eth-tester 进程内单例（默认，无需外部依赖）
  - mock  : 内存模拟兜底

所有后端实现相同的 ChainClient 接口，上层路由无感知。

fisco 模式下节点不可达/初始化失败会抛出 ChainUnavailableError（不静默降级），
由调用方（路由层）转换为对前端的明确错误。
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
from collections import OrderedDict, deque
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import rlp
from eth_abi import encode as abi_encode, decode as abi_decode
from eth_account import Account
from eth_utils import (
    function_abi_to_4byte_selector,
    keccak,
    to_canonical_address,
    to_checksum_address,
    to_hex,
)
from rlp.sedes import Binary, List as RlpList, big_endian_int

from .config import settings
from . import keystore as ks
from .db import get_conn
# 任务 #21：出块/部署成功点发事件（publish 内部经 call_soon_threadsafe 线程安全，永不抛异常）
from . import events_bus

GAS_PRICE = 8750000000  # 适配 Cancun base fee
GAS_LIMIT = 8_000_000

# 任务 #20：内存交易列表上限（有界 deque，防长期运行内存无限增长）
_TX_MEM_MAX = 1000
# 任务 #20：同步交易等待出块的汇聚窗口（秒）：窗口内并发到齐的交易合并进同一块。
# 窗口过后仍未出块则主动 flush，保证单笔交易最坏延迟可控。
_AGGREGATE_WINDOW_CAP = 0.4

# FISCO-BCOS v2 交易参数（gas 在 FISCO 中无计费语义，仅作为资源上限）
FISCO_GAS_LIMIT = 300_000_000        # FISCO v2 默认单笔 gasLimit 上限
FISCO_BLOCK_LIMIT_MARGIN = 500       # blockLimit = 当前块高 + 500（FISCO 要求）

# evm 模式下，别名账户首次注册时从内置创世账户注资的原生币数量（1000 ETH）
_ALIAS_FUND_WEI = 1000 * 10**18


@dataclass
class Block:
    number: int
    hash: str
    parent_hash: str
    timestamp: int
    tx_count: int
    miner: str
    size: int


@dataclass
class Transaction:
    hash: str
    block_number: int
    from_addr: str
    to_addr: str
    value: str
    input: str
    output: str
    status: int
    timestamp: int
    contract_address: Optional[str]
    method: Optional[str]
    parsed_args: Optional[Dict[str, Any]]
    gas_used: int = 0
    gas_price: int = 0
    gas_cost_wei: int = 0
    gas_cost_gwei: float = 0.0
    confirmations: int = 0
    logs: List[Any] = field(default_factory=list)


class ChainClient:
    """统一链接口。"""
    def block_number(self) -> int: ...
    def get_block(self, n: int) -> Optional[Block]: ...
    def get_block_by_hash(self, h: str) -> Optional[Block]: ...
    def list_blocks(self, start: int, end: int) -> List[Block]: ...
    def get_tx(self, tx_hash: str) -> Optional[Transaction]: ...
    def list_txs(self, limit: int = 50, offset: int = 0) -> List[Transaction]: ...
    def list_txs_by_address(self, addr: str, limit: Optional[int] = None, offset: int = 0) -> List[Transaction]: ...
    def deploy_contract(self, name, abi, bytecode, source, deployer, standard=None, ctor_args=None) -> Dict: ...
    def call_contract(self, address, method, args, caller, abi) -> Dict: ...
    def send_tx(self, from_addr, to_addr, value, data="") -> Dict: ...
    def get_accounts(self) -> List[str]: ...
    def resolve_account(self, alias: str) -> str: ...
    def has_code(self, address: str) -> bool: ...
    def get_balance(self, address: str) -> int: ...


# ===========================================================================
# 交易池与持久化辅助（任务 #20）
# ===========================================================================
class _PoolEntry:
    """交易池条目：预签名交易 + 同步等待器。

    入池时即完成签名（手动管理 nonce，见 _sign_tx_locked），调用方通过
    done Event 同步等待回执；批量出块后统一分发 receipt / error。
    """
    __slots__ = ("params", "signed", "tx_hash", "done", "receipt", "error")

    def __init__(self, params: dict, signed: Any, tx_hash: str):
        self.params = params                 # 原始交易参数（canonical 地址），供降级重签
        self.signed = signed                 # py-evm SignedTransactionAPI
        self.tx_hash = tx_hash               # 0x 前缀交易哈希
        self.done = threading.Event()        # 出块后置位
        self.receipt: Optional[dict] = None  # eth-tester 回执 dict
        self.error: Optional[str] = None


def _canon(addr: str) -> bytes:
    """把 0x hex 地址转为 py-evm 内部所需的 20 字节 canonical 地址；空地址返回空字节串。"""
    if not addr:
        return b""
    s = addr if addr.startswith("0x") else "0x" + addr
    return to_canonical_address(s)


def _persist_tx_db(tx: Transaction, class_id: str = "",
                   persist_block: bool = False, block: Optional[Block] = None) -> None:
    """把链上交易（及可选块）同步写入 SQLite transactions/blocks 表（任务 #20）。

    - transactions：hash 全局唯一（含签名字段，跨链实例不重复），多班级链实例
      可共存写入；INSERT OR IGNORE 防重复；
    - blocks：number 为主键，仅全局/默认实例（class_id=''）写入；班级实例块号
      空间独立，写同表必然主键冲突（见 db.py init_db 注释），只驻留内存；
    - 写失败仅日志降级，不影响链上执行结果（DB 可用时 Explorer 分页查询生效）。
    """
    try:
        with get_conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO transactions
                   (hash, block_number, from_addr, to_addr, value, input, output,
                    status, timestamp, contract_address, method, parsed_args,
                    class_id, tenant_id, user_id, session_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (tx.hash, tx.block_number, tx.from_addr, tx.to_addr, tx.value,
                 tx.input, tx.output, tx.status, tx.timestamp, tx.contract_address,
                 tx.method,
                 json.dumps(tx.parsed_args, ensure_ascii=False) if tx.parsed_args is not None else None,
                 class_id or "", "", "", ""),
            )
            if persist_block and block is not None:
                conn.execute(
                    """INSERT OR IGNORE INTO blocks
                       (number, hash, parent_hash, timestamp, tx_count, miner, size, class_id)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (block.number, block.hash, block.parent_hash, block.timestamp,
                     block.tx_count, block.miner, block.size, class_id or ""),
                )
    except Exception as e:
        print(f"[chain] 交易持久化 DB 失败（降级，仅内存可见）: {e}")


def _row_to_tx(row) -> Transaction:
    """把 transactions 表行转为 Transaction（未落库字段取 dataclass 默认值）。"""
    parsed = None
    raw = row["parsed_args"]
    if raw:
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = None
    return Transaction(
        hash=row["hash"],
        block_number=int(row["block_number"] or 0),
        from_addr=row["from_addr"] or "",
        to_addr=row["to_addr"] or "",
        value=str(row["value"] if row["value"] is not None else "0"),
        input=row["input"] or "",
        output=row["output"] or "",
        status=int(row["status"]) if row["status"] is not None else 1,
        timestamp=int(row["timestamp"] or 0),
        contract_address=row["contract_address"],
        method=row["method"],
        parsed_args=parsed,
    )


def _txs_from_db(where: str = "", params: Optional[list] = None,
                 limit: Optional[int] = 50, offset: int = 0,
                 class_id: Optional[str] = None) -> List[Transaction]:
    """从 SQLite 分页读取交易（ORDER BY timestamp DESC，任务 #20）。

    - LIMIT -1 表示不限制条数（与旧 list_txs_by_address 全量返回语义对齐）；
    - 命中 db.py 迁移建好的复合索引 (from_addr, timestamp) / (to_addr, timestamp)
      / (tenant_id, user_id, timestamp)；
    - class_id 过滤：None 不过滤（工具默认）；传 '' 过滤全局/默认实例交易；
      传班级 ID 只查本班交易（班级链空间隔离，防串班）；
    - DB 不可用时抛出异常，由调用方回退内存扫描。
    """
    conds: list = []
    if where:
        conds.append("(" + where + ")")
    if class_id is not None:
        conds.append("class_id = ?")
        params = list(params or []) + [class_id]
    sql = ("SELECT * FROM transactions "
           + ("WHERE " + " AND ".join(conds) + " " if conds else "")
           + "ORDER BY timestamp DESC, block_number DESC LIMIT ? OFFSET ?")
    with get_conn() as conn:
        rows = conn.execute(
            sql,
            list(params or []) + [(-1 if limit is None else int(limit)), int(offset or 0)],
        ).fetchall()
    return [_row_to_tx(r) for r in rows]


# ===========================================================================
# 真实 EVM 实现
# ===========================================================================
class RealEvmChainClient(ChainClient):
    """基于 py-evm 的真实 EVM 链客户端。

    进程内单例，状态持久化：部署的合约、余额、交易记录跨请求保留。

    任务 #20 批量出块（基于 py-evm MiningChain.mine_all，已验证）：
    - 业务交易先入内存交易池（入池时预签名，同 sender 池内 nonce 手动递增）；
    - 后台线程每 EVM_BLOCK_INTERVAL（默认 2s）把池内多笔交易合并产出新块；
    - 同步语义：send_tx / call_contract / deploy_contract 提交后等待回执，
      先等汇聚窗口（窗口内并发交易合批），超窗口主动 flush，超时再兜底 flush
      —— 返回结构与旧实现完全一致（block_number/status/gas_used 全量可用），
      单笔交易最坏延迟 = 窗口(≤0.4s) + 出块时间，教学场景无感；
    - 批量出块失败（如批量内含无效交易）自动降级为逐笔出块（每笔重取最新
      nonce），单笔失败只影响单笔；
    - flush() 供关键路径（部署等）立即同步出块。

    班级级链空间（任务 #20）：class_id 非空时实例独立；LRU 逐出前把业务状态
    快照落盘 storage/chains/{class_id}/snapshot.json，重入时惰性恢复（账户经
    密钥库复原，历史交易恢复可查；EVM 执行状态无法跨实例序列化，与进程重启
    行为一致，合约需重新部署）。
    """

    def __init__(self, class_id: Optional[str] = None):
        from eth_tester import EthereumTester
        from eth_tester.backends.pyevm.main import PyEVMBackend
        self._tester = EthereumTester(PyEVMBackend())
        self._lock = threading.Lock()
        self._class_id = (class_id or "").strip()
        # 任务 #20：内存交易列表改为有界 deque（旧无界 List）
        self._txs: "deque[Transaction]" = deque(maxlen=_TX_MEM_MAX)
        self._blocks_cache: Dict[int, Block] = {}
        # py-evm 内存链每次进程启动从创世块重建；内置创世账户仅作为注资来源，
        # 业务别名账户一律从加密密钥库加载（私钥随机生成、不再硬编码）
        self._genesis_accounts = [a.lower() for a in self._tester.get_accounts()]
        self._fund_source_idx = 0
        self._on_chain: set = set()  # 本 tester 实例内已注册+注资的地址（内存态）
        # 别名 → 地址 / 私钥映射（密钥统一来自 keystore）
        self._alias_to_addr: Dict[str, str] = {}
        self._acct_keys: Dict[str, str] = {}  # addr -> private_key(hex)
        # 固定演示别名各自拥有独立密钥，随机生成后加密持久化，重启后地址不变；
        # 顺序与 keystore.DEMO_ALIASES 严格一致：0-5 联盟角色，6-7 用户角色
        for alias in ks.DEMO_ALIASES:
            self._ensure_alias_account(alias)
        # 记录创世块
        self._sync_block(0)
        # 任务 #20：交易池 + 后台批量出块线程
        self._pool: List[_PoolEntry] = []
        self._stop_event = threading.Event()
        if self._class_id:
            self._restore_from_snapshot()
        self._blocker = threading.Thread(
            target=self._block_loop,
            name=f"evm-blocker-{self._class_id or 'default'}",
            daemon=True,
        )
        self._blocker.start()

    # ---------- 班级快照（任务 #20：LRU 逐出落盘 / 重入惰性恢复） ----------
    def _snapshot_path(self):
        return settings.chains_dir / self._class_id / "snapshot.json"

    def save_snapshot(self) -> Optional[str]:
        """把业务可见状态快照落盘（json），返回快照文件路径；全局实例无快照。

        恢复范围：别名→地址映射、已注册账户、交易历史（内存可见层）。
        EVM 执行状态（合约代码/存储/余额）无法跨实例序列化，与进程重启行为
        一致：重入后账户经密钥库复原（地址不变、重新注资），合约需重新部署。
        """
        if not self._class_id:
            return None
        snap = {
            "version": 1,
            "class_id": self._class_id,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "aliases": dict(self._alias_to_addr),
            "on_chain": sorted(self._on_chain),
            "txs": [asdict(t) for t in self._txs],
            "height": self.block_number(),
        }
        path = self._snapshot_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
        return str(path)

    def _restore_from_snapshot(self) -> None:
        """重入时从快照惰性恢复历史交易与账户映射；失败降级为全新链状态。"""
        path = self._snapshot_path()
        if not path.exists():
            return
        try:
            snap = json.loads(path.read_text(encoding="utf-8"))
            aliases = snap.get("aliases") or {}
            for alias in aliases:
                # 密钥库持久：同一 alias 复原同一地址，并重新注册+注资本实例
                self._ensure_alias_account(alias)
            restored = 0
            for d in (snap.get("txs") or []):
                try:
                    self._txs.append(Transaction(**d))
                    restored += 1
                except Exception:
                    continue  # 版本变更导致字段不匹配时跳过单笔
            print(f"[chain] 班级链 {self._class_id} 从快照恢复 {restored} 笔历史交易 "
                  f"（链执行状态从新块高重建，与进程重启行为一致）")
        except Exception as e:
            print(f"[chain] 班级链 {self._class_id} 快照恢复失败（使用全新链状态）: {e}")

    # ---------- 批量出块（任务 #20） ----------
    def _chain(self):
        return self._tester.backend.chain

    def _block_interval(self) -> float:
        try:
            return max(0.5, float(settings.evm_block_interval or 2.0))
        except Exception:
            return 2.0

    def _aggregate_window(self) -> float:
        return min(_AGGREGATE_WINDOW_CAP, self._block_interval() / 4)

    def _block_loop(self) -> None:
        """后台线程：每 interval 秒把交易池内多笔交易合并产出新块。"""
        interval = self._block_interval()
        while not self._stop_event.wait(interval):
            try:
                with self._lock:
                    if self._pool:
                        self._flush_pending_locked("interval")
            except Exception as e:
                print(f"[chain] 后台出块异常（继续运行）: {e}")

    def shutdown(self) -> None:
        """停止后台出块线程（LRU 逐出时调用；重入时新实例会另起新线程）。"""
        self._stop_event.set()

    def flush(self, timeout: float = 10.0) -> int:
        """同步出块：把交易池内全部交易合并产出新块，返回当前块高（关键路径用）。"""
        with self._lock:
            return self._flush_pending_locked("flush-api")

    # ---------- 账户 ----------
    def _ensure_alias_account(self, alias: str) -> str:
        """为别名获取/创建专属独立账户（密钥库持久化），并在内存链上注册+注资。"""
        a = (alias or "").strip().lower()
        if a in self._alias_to_addr:
            return self._alias_to_addr[a]
        addr, pk = ks.get_or_create_account(a)
        self._alias_to_addr[a] = addr
        self._acct_keys[addr] = pk
        self._register_on_chain(addr, pk)
        return addr

    def _register_on_chain(self, addr: str, pk: str) -> None:
        """把账户注册进 eth-tester（可签名），并从创世账户注资原生币。"""
        addr_l = addr.lower()
        if addr_l in self._on_chain:
            return
        with self._lock:  # 注册+注资交易与批量出块/其他注册互斥
            if addr_l in self._on_chain:
                return
            try:
                # eth-tester 要求私钥为 0x 前缀的 64 位 hex 字符串（内部自行转 bytes）
                pk_str = pk if pk.startswith("0x") else "0x" + pk
                self._tester.add_account(pk_str)
            except Exception:
                pass  # 账户已存在于 tester 账户列表（理论上随机密钥不会碰撞）
            # 注资：从内置创世账户拨付初始余额，来源账户不足时轮换下一个创世账户
            n_src = len(self._genesis_accounts)
            src = self._genesis_accounts[0]
            for _ in range(n_src):
                src = self._genesis_accounts[self._fund_source_idx % n_src]
                if int(self._tester.get_balance(src)) >= _ALIAS_FUND_WEI + 21000 * GAS_PRICE:
                    break
                self._fund_source_idx += 1
            self._tester.send_transaction({
                "from": src, "to": addr_l, "value": _ALIAS_FUND_WEI,
                "gas": 21000, "gas_price": GAS_PRICE,
            })
            self._on_chain.add(addr_l)

    def get_accounts(self) -> List[str]:
        """返回固定演示别名对应的账户地址（按 DEMO_ALIASES 顺序）。"""
        return [self._alias_to_addr[a] for a in ks.DEMO_ALIASES if a in self._alias_to_addr]

    def resolve_account(self, alias: str) -> str:
        """把别名/地址解析为 EVM 真实账户地址。

        未知别名不再哈希映射到共享创世账户，而是从密钥库生成/读取其专属独立账户，
        保证每个钱包别名与链上地址一一对应，杜绝不同学生资产串扰。
        """
        if not alias:
            return self._alias_to_addr[ks.DEMO_ALIASES[0]]
        a = alias.strip().lower()
        if a in self._alias_to_addr:
            return self._alias_to_addr[a]
        # 已是真实地址（42 位 0x 开头）：直接返回，含创世账户与合约地址
        if a.startswith("0x") and len(a) == 42:
            return a
        # 未知别名：生成/读取专属独立账户（持久化到密钥库）
        return self._ensure_alias_account(a)

    # ---------- 代码检查 ----------
    def has_code(self, address: str) -> bool:
        """检查指定地址是否有合约代码（用于识别 stale 部署记录）。"""
        try:
            a = address if address.startswith("0x") else self.resolve_account(address)
            code = self._tester.get_code(a)
            return bool(code) and code != "0x"
        except Exception:
            return False

    # ---------- 余额 ----------
    def get_balance(self, address: str) -> int:
        """查询账户原生代币余额（wei），返回真实链上数值。"""
        a = address if address.startswith("0x") else self.resolve_account(address)
        return int(self._tester.get_balance(a))

    # ---------- 区块 ----------
    def block_number(self) -> int:
        return self._tester.get_block_by_number("latest")["number"]

    def _sync_block(self, n: int) -> Block:
        b = self._tester.get_block_by_number(n)
        blk = Block(
            number=n,
            hash=_hex(b["hash"]),
            parent_hash=_hex(b.get("parent_hash", b.get("parentHash", ""))),
            timestamp=int(b.get("timestamp", 0)),
            tx_count=len(b.get("transactions", [])),
            miner=_hex(b.get("miner", "0x0")),
            size=int(b.get("size", 0) or 0),
        )
        self._blocks_cache[n] = blk
        return blk

    def get_block(self, n: int) -> Optional[Block]:
        if n in self._blocks_cache:
            return self._blocks_cache[n]
        if n < 0 or n > self.block_number():
            return None
        return self._sync_block(n)

    def get_block_by_hash(self, h: str) -> Optional[Block]:
        for b in self._blocks_cache.values():
            if b.hash == h:
                return b
        return None

    def list_blocks(self, start: int, end: int) -> List[Block]:
        end = min(end, self.block_number())
        start = max(0, start)
        out = []
        for n in range(end, start - 1, -1):
            out.append(self.get_block(n))
        return [b for b in out if b]

    # ---------- 交易 ----------
    def get_tx(self, tx_hash: str) -> Optional[Transaction]:
        h = tx_hash.lower()
        for t in self._txs:
            if t.hash.lower() == h:
                return t
        return None

    def list_txs(self, limit: int = 50, offset: int = 0) -> List[Transaction]:
        """最新交易分页（任务 #20）：优先查 DB（LIMIT/OFFSET + 索引排序），
        DB 不可用时回退内存扫描，行为与旧实现兼容。"""
        try:
            txs = _txs_from_db(limit=limit, offset=offset, class_id=self._class_id)
        except Exception:
            items = list(reversed(self._txs))
            start = int(offset or 0)
            return items[start:start + int(limit)] if int(limit) > 0 else items[start:]
        height = self.block_number()
        for t in txs:
            t.confirmations = max(0, height - t.block_number)
        return txs

    def list_txs_by_address(self, addr: str, limit: Optional[int] = None, offset: int = 0) -> List[Transaction]:
        """按地址查询交易（任务 #20）：优先查 DB 分页（命中 (from_addr, timestamp)
        / (to_addr, timestamp) 复合索引），DB 不可用回退内存扫描。
        limit=None 时返回全部（与旧签名 list_txs_by_address(addr) 语义一致）。"""
        a = (addr or "").lower()
        try:
            where = "(from_addr = ? OR to_addr = ? OR COALESCE(contract_address, '') = ?)"
            txs = _txs_from_db(where, [a, a, a], limit=limit, offset=offset,
                               class_id=self._class_id)
        except Exception:
            items = [t for t in reversed(self._txs)
                     if t.from_addr.lower() == a or t.to_addr.lower() == a
                     or (t.contract_address or "").lower() == a]
            start = int(offset or 0)
            return items[start:] if limit is None else items[start:start + int(limit)]
        height = self.block_number()
        for t in txs:
            t.confirmations = max(0, height - t.block_number)
        return txs

    def _record_tx(self, tx_hash, block_number, from_addr, to_addr, value,
                   input_data, receipt, method=None, parsed_args=None, output=""):
        logs = []
        for lg in receipt.get("logs", []):
            logs.append({
                "address": _hex(lg["address"]),
                "topics": [_hex(tp) for tp in lg["topics"]],
                "data": _hex(lg["data"]),
                "log_index": lg.get("log_index", 0),
            })
        gas_used = int(receipt.get("gas_used", 0))
        gas_price = GAS_PRICE
        gas_cost_wei = gas_used * gas_price
        gas_cost_gwei = gas_cost_wei / 1e9
        current_block = self.block_number()
        confirmations = max(0, current_block - block_number)
        tx = Transaction(
            hash=_hex(tx_hash),
            block_number=block_number,
            from_addr=from_addr.lower() if from_addr else "",
            to_addr=to_addr.lower() if to_addr else "",
            value=str(value),
            input=input_data or "",
            output=output,
            status=int(receipt.get("status", 1)),
            timestamp=int(self.get_block(block_number).timestamp) if self.get_block(block_number) else int(time.time()),
            contract_address=_hex(receipt["contract_address"]) if receipt.get("contract_address") else None,
            method=method,
            parsed_args=parsed_args,
            gas_used=gas_used,
            gas_price=gas_price,
            gas_cost_wei=gas_cost_wei,
            gas_cost_gwei=gas_cost_gwei,
            confirmations=confirmations,
            logs=logs,
        )
        self._txs.append(tx)
        # 任务 #20：同步持久化到 SQLite（失败降级日志，不影响链上结果）；
        # 仅全局实例（class_id=''）写 blocks 表，班级实例只写 transactions（hash 全局唯一）
        _persist_tx_db(
            tx, class_id=self._class_id,
            persist_block=not self._class_id,
            block=self._blocks_cache.get(block_number),
        )
        # 任务 #21：交易确认 → 事件总线（批量出块位于后台线程，publish 经
        # call_soon_threadsafe 跨线程投递，线程安全；失败不影响出块流程）
        events_bus.publish(
            events_bus.BusEvent.TX_CONFIRMED,
            {"tx_hash": tx.hash, "block_number": block_number,
             "from": tx.from_addr, "to": tx.to_addr,
             "method": tx.method or "", "status": tx.status,
             "contract_address": tx.contract_address or ""},
            class_id=self._class_id)
        return tx

    # ---------- 交易提交与批量出块核心（任务 #20） ----------
    def _sign_tx_locked(self, params: dict):
        """预签名：同 sender 在池内的第 k 笔交易 nonce = 链上 nonce + k，
        保证同批多笔交易（同一 sender）在 mine_all 时 nonce 严格递增
        （py-evm 批量 apply 不自动补 nonce，已验证自动 nonce 同 sender 必冲突）。"""
        sender = params["from"]
        pending_same = sum(1 for e in self._pool if e.params.get("from") == sender)
        full = dict(params)
        full["nonce"] = self._tester.backend.get_nonce(sender) + pending_same
        return self._tester.backend._get_normalized_and_signed_evm_transaction(full)

    def _sign_fresh(self, params: dict):
        """降级重签：每次实时取链上最新 nonce（逐笔出块时状态已推进）。"""
        full = dict(params)
        full["nonce"] = self._tester.backend.get_nonce(params["from"])
        return self._tester.backend._get_normalized_and_signed_evm_transaction(full)

    def _enqueue_locked(self, params: dict) -> _PoolEntry:
        signed = self._sign_tx_locked(params)
        entry = _PoolEntry(params=params, signed=signed, tx_hash=_hex(signed.hash))
        self._pool.append(entry)
        return entry

    def _flush_pending_locked(self, reason: str) -> int:
        """把池内全部交易合并产出新块（锁内调用）；返回当前块高。

        - 批量走 py-evm mine_all（多笔交易同块、时间戳递增、gas 由 EVM 真实执行）；
        - 批量失败（含无效交易）降级逐笔出块（每笔重取最新 nonce），
          单笔失败只影响单笔（与旧 auto-mine 逐笔语义对齐）。
        """
        if not self._pool:
            return self.block_number()
        batch, self._pool = self._pool, []
        signed = [e.signed for e in batch]
        try:
            result, _receipts, _comps = self._chain().mine_all(signed)
            blk_no = result.imported_block.number
            self._sync_block(blk_no)
            for e in batch:
                e.receipt = self._tester.get_transaction_receipt(to_hex(e.signed.hash))
                e.done.set()
            print(f"[chain] 批量出块({reason}): {len(batch)} 笔交易合并 → 块 #{blk_no}")
        except Exception as exc:
            print(f"[chain] 批量出块失败，降级逐笔出块: {exc}")
            for e in batch:
                try:
                    fresh = self._sign_fresh(e.params)
                    res, _, _ = self._chain().mine_all([fresh])
                    self._sync_block(res.imported_block.number)
                    e.signed = fresh
                    e.receipt = self._tester.get_transaction_receipt(to_hex(fresh.hash))
                except Exception as e2:
                    e.error = str(e2)
                e.done.set()
        return self.block_number()

    def _flush_pending(self, reason: str) -> None:
        with self._lock:
            self._flush_pending_locked(reason)

    def _submit_and_wait(self, params: dict, immediate: bool = False) -> dict:
        """提交交易入池并同步等待出块回执（send_tx 语义兼容的关键）。

        时序语义（保持与旧实现调用方兼容，不改返回结构——同步等待出块）：
        1. 锁内入池（预签名，立即得到 tx_hash）；
        2. 等汇聚窗口：窗口内并发的其他交易同批合并出块（批量收益来源）；
        3. 窗口过仍未出块 → 主动 flush；再超时 → 兑底 flush + 短等；
        4. 返回 eth-tester 回执 dict（transaction_hash/block_number/status/gas_used）；
           交易无效时抛 RuntimeError（与旧实现一致）。
        immediate=True（关键路径如部署）跳过窗口立即 flush。
        """
        with self._lock:
            entry = self._enqueue_locked(params)
            if immediate:
                self._flush_pending_locked("immediate")
        if not immediate:
            if not entry.done.wait(self._aggregate_window()):
                self._flush_pending("window")
        if not entry.done.wait(self._block_interval() + 6.0):
            self._flush_pending("timeout")
            entry.done.wait(5.0)
        if entry.error:
            raise RuntimeError(entry.error)
        if entry.receipt is None:
            raise RuntimeError("等待交易回执超时")
        return entry.receipt

    # ---------- 部署 ----------
    def deploy_contract(self, name, abi, bytecode, source, deployer, standard=None, ctor_args=None) -> Dict:
        sender = self.resolve_account(deployer)
        # 构造完整部署 data = bytecode + 编码后的构造函数参数
        data = _norm_hex(bytecode)
        ctor_types, ctor_vals = _encode_ctor_args(abi, ctor_args)
        if ctor_types:
            data += abi_encode(ctor_types, ctor_vals).hex()
        data_bytes = bytes.fromhex(data) if data else b""
        params = {
            "from": _canon(sender), "to": b"",  # 部署交易 to 为空
            "data": data_bytes,
            "gas": GAS_LIMIT, "value": 0, "gas_price": GAS_PRICE,
        }
        try:
            # 关键路径：立即同步出块（不等汇聚窗口），回执时序与旧实现一致
            receipt = self._submit_and_wait(params, immediate=True)
        except RuntimeError as e:
            raise RuntimeError(f"部署失败: {e}") from e
        block_number = int(receipt["block_number"])
        self._sync_block(block_number)
        tx_hash = receipt["transaction_hash"]
        addr = _hex(receipt["contract_address"]) if receipt.get("contract_address") else None
        self._record_tx(
            tx_hash, block_number, sender, "", "0",
            "0x" + data_bytes.hex(), receipt, method="constructor",
            parsed_args={"name": name, "ctor_args": ctor_args or []},
            output=addr or "",
        )
        # 任务 #25 评审修复：DEPLOYED 事件统一由 contracts 路由层发布（带 user_id 定向），
        # 链客户端不再重复发布（避免双重发布）；本部署交易的 TX_CONFIRMED 已由
        # _record_tx 统一发出，与调用/转账路径口径一致。
        return {
            "address": addr, "name": name, "tx_hash": _hex(tx_hash),
            "block_number": block_number, "standard": standard,
            "gas_used": int(receipt.get("gas_used", 0)),
            "status": int(receipt.get("status", 1)),
        }

    # ---------- 调用 ----------
    def call_contract(self, address, method, args, caller, abi) -> Dict:
        addr = self.resolve_account(address) if not address.startswith("0x") else address
        # 找到方法 ABI
        fn_abi = _find_fn_abi(abi, method)
        if not fn_abi:
            raise RuntimeError(f"未在 ABI 中找到方法 {method}")
        is_readonly = fn_abi.get("stateMutability") in ("view", "pure") or fn_abi.get("constant", False)
        sender = self.resolve_account(caller)
        selector = function_abi_to_4byte_selector(fn_abi)
        in_types = [i["type"] for i in fn_abi.get("inputs", [])]
        encoded_args = abi_encode(in_types, _coerce_args(in_types, args)) if in_types else b""
        calldata = "0x" + selector.hex() + encoded_args.hex()

        if is_readonly:
            # 只读 call：不修改状态，不消耗 Gas，返回真实解码值
            try:
                out_raw = self._tester.call({
                    "from": sender, "to": addr, "data": calldata,
                    "gas": GAS_LIMIT, "value": 0,
                })
                out_types = [o["type"] for o in fn_abi.get("outputs", [])]
                decoded = abi_decode(out_types, _to_bytes(out_raw)) if out_types else []
                decoded_str = _stringify_decoded(out_types, decoded)
                return {
                    "ok": True, "readonly": True, "result": decoded_str,
                    "raw": _hex(out_raw), "method": method, "args": args,
                    "status": "success",
                }
            except Exception as e:
                return {"ok": False, "readonly": True, "error": str(e), "method": method, "args": args, "status": "reverted"}

        # 状态变更交易：入池同步等待出块（返回结构与旧实现一致）
        params = {
            "from": _canon(sender), "to": _canon(addr), "data": _to_bytes(calldata),
            "gas": GAS_LIMIT, "value": 0, "gas_price": GAS_PRICE,
        }
        try:
            receipt = self._submit_and_wait(params)
        except RuntimeError as e:
            raise RuntimeError(f"调用失败: {e}") from e
        block_number = int(receipt["block_number"])
        self._sync_block(block_number)
        parsed = {"method": method, "args": args}
        tx_obj = self._record_tx(
            receipt["transaction_hash"], block_number, sender, addr, "0", calldata, receipt,
            method=method, parsed_args=parsed, output=_hex(receipt.get("output", "")),
        )
        return {
            "ok": True, "readonly": False,
            "tx_hash": _hex(receipt["transaction_hash"]), "block_number": block_number,
            "gas_used": int(receipt.get("gas_used", 0)),
            "status": "success" if int(receipt.get("status", 1)) == 1 else "reverted",
            "result": "tx success", "logs": tx_obj.logs,
            "method": method, "args": args,
        }

    # ---------- 转账 ----------
    def send_tx(self, from_addr, to_addr, value, data=""):
        sender = self.resolve_account(from_addr)
        recipient = self.resolve_account(to_addr) if to_addr and not to_addr.startswith("0x") else to_addr
        val = int(value) if str(value).isdigit() else 0
        params = {
            "from": _canon(sender),
            "to": _canon(recipient) if recipient else b"",
            "value": val,
            "gas": GAS_LIMIT, "gas_price": GAS_PRICE,
        }
        if data:
            params["data"] = _to_bytes(data)
        try:
            # 同步等待出块：返回结构与旧实现完全一致（不返回 pending）
            receipt = self._submit_and_wait(params)
        except RuntimeError as e:
            raise RuntimeError(f"转账失败: {e}") from e
        bn = int(receipt["block_number"])
        self._sync_block(bn)
        data_hex = ("0x" + params["data"].hex()) if params.get("data") else ""
        self._record_tx(receipt["transaction_hash"], bn, sender, recipient, str(val),
                        data_hex, receipt, method="transfer",
                        parsed_args={"to": to_addr, "value": value})
        return {"tx_hash": _hex(receipt["transaction_hash"]), "block_number": bn,
                "status": "success", "gas_used": int(receipt.get("gas_used", 0))}


# ===========================================================================
# 工具函数
# ===========================================================================
def _hex(v) -> str:
    """把 bytes/str 统一转为 0x 开头小写 hex 字符串。"""
    if v is None:
        return ""
    if isinstance(v, (bytes, bytearray)):
        return "0x" + v.hex()
    if isinstance(v, str):
        s = v.lower()
        return s if s.startswith("0x") else "0x" + s
    return str(v)


def _to_bytes(v) -> bytes:
    if isinstance(v, (bytes, bytearray)):
        return bytes(v)
    if isinstance(v, str):
        s = v[2:] if v.startswith("0x") else v
        return bytes.fromhex(s)
    return b""


def _norm_hex(s: str) -> str:
    if not s:
        return ""
    return s[2:] if s.startswith("0x") else s


def _find_fn_abi(abi: List[Any], name: str) -> Optional[Dict]:
    for item in abi:
        if item.get("type") == "function" and item.get("name") == name:
            return item
    return None


def _encode_ctor_args(abi: List[Any], ctor_args: List[Any]) -> Tuple[List[str], List[Any]]:
    """从 ABI 提取构造函数参数类型，与传入参数匹配。"""
    ctor = next((x for x in abi if x.get("type") == "constructor"), None)
    if not ctor or not ctor.get("inputs"):
        return [], []
    types = [i["type"] for i in ctor["inputs"]]
    vals = _coerce_args(types, ctor_args or [])
    return types, vals


def _coerce_arg(t: str, v: Any) -> Any:
    """把前端传入的字符串参数转换为 ABI 编码所需类型。"""
    if v is None:
        return 0
    if isinstance(v, (int,)):
        return v
    s = str(v)
    if t.startswith("uint") or t.startswith("int"):
        return int(s, 0) if s.startswith("0x") else int(s)
    if t == "address":
        # eth_abi 接受 bytes 或 str；传 checksum
        return s
    if t.startswith("bytes"):
        s2 = s[2:] if s.startswith("0x") else s
        return bytes.fromhex(s2)
    if t == "bool":
        return s.lower() in ("true", "1", "yes")
    return s


def _coerce_args(types: List[str], args: List[Any]) -> List[Any]:
    return [_coerce_arg(t, args[i]) if i < len(args) else _coerce_arg(t, "") for i, t in enumerate(types)]


def _stringify_decoded(types: List[str], decoded: tuple) -> Any:
    """把 ABI 解码结果转为前端可读形式。"""
    if not decoded:
        return None
    if len(decoded) == 1:
        v = decoded[0]
        if isinstance(v, (bytes, bytearray)):
            return "0x" + v.hex()
        return v
    out = []
    for t, v in zip(types, decoded):
        if isinstance(v, (bytes, bytearray)):
            out.append("0x" + v.hex())
        else:
            out.append(v)
    return out


# ===========================================================================
# Mock 兜底（无 py-evm 时使用）
# ===========================================================================
class MockChainClient(ChainClient):
    """内存模拟链兜底实现。

    任务 #20：支持 class_id（班级注册表每班独立实例）；交易同步写 SQLite
    transactions 表（class_id='' 时也写 blocks），list_txs 优先查 DB。
    """
    def __init__(self, class_id: Optional[str] = None):
        self._class_id = (class_id or "").strip()
        self._height = 0
        # 任务 #20：内存交易列表改为有界 deque（旧无界 List）
        self._txs: "deque[Transaction]" = deque(maxlen=_TX_MEM_MAX)
        self._blocks = [Block(0, "0x" + "0" * 64, "0x0", int(time.time()), 0, "0x0", 0)]

    def block_number(self): return self._height - 1
    def get_block(self, n): return self._blocks[n] if 0 <= n < len(self._blocks) else None
    def get_block_by_hash(self, h): return next((b for b in self._blocks if b.hash == h), None)
    def list_blocks(self, s, e): return [b for b in reversed(self._blocks) if s <= b.number <= e]
    def get_tx(self, h): return next((t for t in self._txs if t.hash == h), None)
    def list_txs(self, limit: int = 50, offset: int = 0):
        """最新交易分页（任务 #20）：优先查 DB，DB 不可用回退内存。"""
        try:
            return _txs_from_db(limit=limit, offset=offset, class_id=self._class_id)
        except Exception:
            items = list(reversed(self._txs))
            start = int(offset or 0)
            return items[start:start + int(limit)] if int(limit) > 0 else items[start:]
    def list_txs_by_address(self, a, limit: Optional[int] = None, offset: int = 0):
        al = (a or "").lower()
        try:
            where = "(from_addr = ? OR to_addr = ?)"
            return _txs_from_db(where, [al, al], limit=limit, offset=offset,
                                class_id=self._class_id)
        except Exception:
            items = [t for t in reversed(self._txs) if t.from_addr.lower() == al or t.to_addr.lower() == al]
            start = int(offset or 0)
            return items[start:] if limit is None else items[start:start + int(limit)]
    def get_accounts(self): return ["0xlearner"]
    def resolve_account(self, a): return a or "0xlearner"
    def deploy_contract(self, name, abi, bytecode, source, deployer, standard=None, ctor_args=None):
        addr = "0x" + hashlib.sha256(f"{name}{time.time()}{secrets.token_hex(8)}".encode()).hexdigest()[:40]
        h = "0x" + hashlib.sha256(f"tx{time.time()}{secrets.token_hex(8)}".encode()).hexdigest()
        bn = self._height
        tx = Transaction(h, bn, deployer, "", "0", bytecode[:200] or "", addr, 1, int(time.time()), addr, "constructor", {"name": name})
        blk = Block(bn, h, self._blocks[-1].hash, int(time.time()), 1, deployer, 0)
        self._txs.append(tx)
        self._blocks.append(blk)
        self._height += 1
        # 任务 #20：同步持久化（班级 mock 实例只写 transactions）
        _persist_tx_db(tx, class_id=self._class_id, persist_block=not self._class_id, block=blk)
        # 任务 #25 评审修复：DEPLOYED 统一由 contracts 路由层发布（带 user_id 定向），
        # mock 此处补发该部署交易的 TX_CONFIRMED（与 EVM/FISCO 口径对齐：
        # payload 含 tx_hash/block_number/from/to/status/contract_address）。
        events_bus.publish(events_bus.BusEvent.TX_CONFIRMED,
                           {"tx_hash": h, "block_number": bn, "from": deployer, "to": "",
                            "method": "constructor", "status": 1, "contract_address": addr},
                           class_id=self._class_id)
        return {"address": addr, "name": name, "tx_hash": h, "block_number": bn, "standard": standard, "gas_used": 0, "status": 1}
    def call_contract(self, address, method, args, caller, abi):
        return {"ok": True, "readonly": False, "tx_hash": "0xmock", "block_number": self._height, "result": f"mock {method}", "status": "success", "method": method, "args": args}
    def send_tx(self, f, t, v, data=""):
        # 任务 #20：hash 掺入随机数，避免同秒交易哈希碰撞导致 DB 主键冲突丢交易
        h = "0x" + hashlib.sha256(f"tx{time.time()}{secrets.token_hex(8)}".encode()).hexdigest()
        bn = self._height
        tx = Transaction(h, bn, f, t, str(v), data, "", 1, int(time.time()), None, "transfer", {"to": t, "value": v})
        blk = Block(bn, h, self._blocks[-1].hash, int(time.time()), 1, f, 0)
        self._txs.append(tx)
        self._blocks.append(blk)
        self._height += 1
        _persist_tx_db(tx, class_id=self._class_id, persist_block=not self._class_id, block=blk)
        # 任务 #21：交易确认 → 事件总线（mock 后端）
        events_bus.publish(events_bus.BusEvent.TX_CONFIRMED,
                           {"tx_hash": h, "block_number": bn, "from": f, "to": t,
                            "method": "transfer", "status": 1, "contract_address": ""},
                           class_id=self._class_id)
        return {"tx_hash": h, "block_number": bn, "status": "success", "gas_used": 0}
    def has_code(self, address: str) -> bool:
        return True

    def get_balance(self, address: str) -> int:
        """Mock 模式返回模拟余额（1 ETH）。"""
        return 10**18


# ===========================================================================
# FISCO-BCOS 模式异常与 v2 原生交易编码
# ===========================================================================
class ChainUnavailableError(RuntimeError):
    """CHAIN_MODE=fisco 但节点不可达/初始化失败。

    禁止静默降级到 evm/mock：上层必须把本异常暴露给调用方（如 HTTP 503），
    message 中包含节点地址与具体原因，便于前端/运维定位。
    """


# FISCO-BCOS v2 交易 RLP 结构（顺序与节点端 Transaction 字段严格一致）：
#   [randomid, gasPrice, gasLimit, blockLimit, to, value, data,
#    fisco_chain_id, group_id, extra_data]
# 与以太坊区别：无 nonce（用随机 32 字节 randomid）、无 chainId 在签名域，
# 多出 fisco_chain_id / group_id / extra_data，blockLimit 为交易有效期上限。
_FISCO_TX_SEDES = RlpList(
    [
        Binary.fixed_length(32),              # randomid（32 字节随机值，替代以太坊 nonce）
        big_endian_int,                       # gasPrice
        big_endian_int,                       # gasLimit
        big_endian_int,                       # blockLimit
        Binary.fixed_length(20, allow_empty=True),  # to（部署交易为空）
        big_endian_int,                       # value
        Binary(),                             # data
        big_endian_int,                       # fisco_chain_id
        big_endian_int,                       # group_id
        Binary(),                             # extra_data
    ]
)
# 签名后交易 = 未签名 10 字段 + [v(=chain_id), r, s]，共 13 字段，同序编码/解码可互验
_FISCO_SIGNED_TX_SEDES = RlpList(list(_FISCO_TX_SEDES) + [big_endian_int] * 3)


def _fisco_to_field(to_addr: str) -> bytes:
    """把目标地址转为 20 字节；部署交易（空地址）返回空字节串。"""
    if not to_addr:
        return b""
    return _to_bytes(to_addr)


def encode_fisco_unsigned_tx(
    to_addr: str,
    data: str,
    value: int,
    block_limit: int,
    chain_id: int,
    group_id: int,
    gas_limit: int = FISCO_GAS_LIMIT,
    gas_price: int = 0,
    extra_data: bytes = b"",
) -> bytes:
    """按 FISCO-BCOS v2 格式 RLP 编码未签名交易。"""
    randomid = secrets.token_bytes(32)
    fields = [
        randomid,
        gas_price,
        gas_limit,
        block_limit,
        _fisco_to_field(to_addr),
        int(value),
        _to_bytes(data),
        chain_id,
        group_id,
        extra_data,
    ]
    return rlp.encode(fields, sedes=_FISCO_TX_SEDES)


def sign_fisco_tx(unsigned_tx: bytes, private_key: bytes, chain_id: int) -> bytes:
    """对未签名交易做 secp256k1 签名并拼装签名后交易。

    流程：keccak256(unsigned_tx) → secp256k1 签名得 (v, r, s)，
    FISCO v2 的签名域 v 直接取链上 chain_id（与官方 JS/Python SDK 一致），
    最终 raw 交易 = RLP([ unsigned_tx 各字段, chain_id, r, s ])。
    """
    msg_hash = keccak(unsigned_tx)
    sig = Account._sign_hash(msg_hash, private_key)  # SignSignature(v, r, s)
    decoded = rlp.decode(unsigned_tx, sedes=_FISCO_TX_SEDES)
    signed_fields = list(decoded) + [chain_id, sig.r, sig.s]
    return rlp.encode(signed_fields, sedes=_FISCO_SIGNED_TX_SEDES)


def encode_fisco_signed_tx(
    to_addr: str,
    data: str,
    value: int,
    block_limit: int,
    chain_id: int,
    group_id: int,
    private_key: bytes,
    gas_limit: int = FISCO_GAS_LIMIT,
    gas_price: int = 0,
    extra_data: bytes = b"",
) -> str:
    """一步完成编码+签名，返回 0x 开头、可直接送 eth_sendRawTransaction 的 hex。"""
    unsigned = encode_fisco_unsigned_tx(
        to_addr, data, value, block_limit, chain_id, group_id,
        gas_limit=gas_limit, gas_price=gas_price, extra_data=extra_data,
    )
    return "0x" + sign_fisco_tx(unsigned, private_key, chain_id).hex()


# ===========================================================================
# 真实 FISCO-BCOS 节点客户端（JSON-RPC + FISCO v2 原生交易格式）
# ===========================================================================
class FiscoRpcClient(ChainClient):
    """通过 JSON-RPC 连接真实 FISCO-BCOS 节点的链客户端。

    FISCO-BCOS v2.x 的 JSON-RPC 端口（默认 8545）兼容以太坊标准 RPC：
    eth_blockNumber / eth_call / eth_sendRawTransaction / eth_getTransactionReceipt 等。
    部分方法支持可选第二参数 group_id（字符串），本客户端均显式传入配置的组。

    交易按 FISCO v2 原生格式签名广播（非以太坊 legacy 格式）：
    字段 [randomid, gasPrice, gasLimit, blockLimit, to, value, data,
    fisco_chain_id, group_id, extra_data]，RLP 编码后 secp256k1 签名
    （v=chain_id），拼为 [编码交易, v, r, s] 再 RLP，经 eth_sendRawTransaction 广播。
    无需 FISCO Python SDK / Channel 协议 / 证书。

    任务 #20：支持 group_id 参数（班级级链空间注册表按 class_id 确定性映射
    groupId 后创建/复用实例；不传则用配置默认组，与既有行为一致）。
    """

    def __init__(self, group_id: Optional[int] = None):
        import httpx
        self._http = httpx.Client(timeout=15)
        self._rpc = settings.fisco_rpc_url
        self._group_id = int(group_id) if (group_id and int(group_id) > 0) else settings.fisco_group_id
        self._class_id = ""  # 同组可能服务多个班级，交易归属不区分（记 ''）
        self._lock = threading.Lock()
        # 任务 #20：内存交易列表改为有界 deque（旧无界 List）
        self._txs: "deque[Transaction]" = deque(maxlen=_TX_MEM_MAX)
        self._blocks_cache: Dict[int, Block] = {}
        # 演示账户由加密密钥库随机生成并持久化（私钥不再硬编码推导，任何人无法复算）
        # 顺序与 keystore.DEMO_ALIASES 严格一致：0-5 联盟角色，6-7 用户角色，重启后地址不变
        self._accounts: List[str] = []
        self._alias_to_addr: Dict[str, str] = {}
        self._acct_keys: Dict[str, str] = {}  # addr -> private_key
        for alias in ks.DEMO_ALIASES:
            addr, pk = ks.get_or_create_account(alias)
            self._accounts.append(addr)
            self._alias_to_addr[alias] = addr
            self._acct_keys[addr] = pk
        # 连通性 + 组有效性校验（失败直接抛 ChainUnavailableError，不降级）
        try:
            bn = self._rpc_call("eth_blockNumber", [str(self._group_id)])
            self._height0 = int(bn, 16)
            self._sync_block(self._height0)
        except Exception as e:
            raise ChainUnavailableError(
                f"无法连接 FISCO-BCOS 节点 {self._rpc}（groupId={self._group_id}）: {e}"
            ) from e
        # chainId：优先取配置，否则启动时通过 getClientVersion 自动获取（签名必需）
        self._chain_id = self._resolve_chain_id(settings.fisco_chain_id)

    # ---------- chainId 解析 ----------
    def _resolve_chain_id(self, configured: int) -> int:
        if configured and configured > 0:
            return configured
        try:
            ver = self._rpc_call("getClientVersion") or {}
            cid = ver.get("Chain Id") or ver.get("chainId")
            if cid is None:
                raise RuntimeError(f"getClientVersion 响应缺少 Chain Id 字段: {ver}")
            return int(cid)
        except Exception as e:
            raise ChainUnavailableError(
                f"FISCO-BCOS 节点 {self._rpc} 未配置 FISCO_CHAIN_ID 且无法通过 "
                f"getClientVersion 自动获取 chainId: {e}"
            ) from e

    # ---------- JSON-RPC 底层 ----------
    def _rpc_call(self, method: str, params: list = None) -> Any:
        """发送 JSON-RPC 请求，返回 result 字段。"""
        payload = {"jsonrpc": "2.0", "method": method, "params": params or [], "id": 1}
        r = self._http.post(self._rpc, json=payload)
        data = r.json()
        if "error" in data and data["error"]:
            raise RuntimeError(f"RPC error: {data['error']}")
        return data.get("result")

    def _sign_and_send(self, from_addr: str, to_addr: str, data: str, value: int = 0, gas: int = FISCO_GAS_LIMIT) -> Tuple[str, int, Dict]:
        """按 FISCO v2 原生格式签名并广播交易，返回 (tx_hash, block_number, receipt)。

        编码流程：字段 [randomid, gasPrice, gasLimit, blockLimit, to, value, data,
        fisco_chain_id, group_id, extra_data] → RLP → keccak → secp256k1(v=chain_id)
        → [编码交易, v, r, s] → RLP → hex → eth_sendRawTransaction。
        """
        pk = self._acct_keys.get(from_addr)
        if not pk:
            raise RuntimeError(f"未知账户 {from_addr}，无对应私钥")
        pk_bytes = _to_bytes(pk)
        # blockLimit = 当前块高 + 500（FISCO 要求，超过则节点拒收）
        block_limit = self.block_number() + FISCO_BLOCK_LIMIT_MARGIN
        raw_tx = encode_fisco_signed_tx(
            to_addr=to_addr, data=data, value=value, block_limit=block_limit,
            chain_id=self._chain_id, group_id=self._group_id, private_key=pk_bytes,
            gas_limit=gas, gas_price=0,
        )
        tx_hash = self._rpc_call("eth_sendRawTransaction", [raw_tx, str(self._group_id)])
        if not tx_hash:
            raise RuntimeError("eth_sendRawTransaction 未返回交易哈希")
        receipt = self._wait_receipt(tx_hash)
        block_number = int(receipt.get("blockNumber", "0x0"), 16)
        return tx_hash, block_number, receipt

    def _wait_receipt(self, tx_hash: str, timeout: int = 15) -> Dict:
        """轮询等待交易收据。"""
        for _ in range(timeout * 2):
            r = self._rpc_call("eth_getTransactionReceipt", [tx_hash, str(self._group_id)])
            if r:
                return r
            time.sleep(0.5)
        raise RuntimeError(f"等待交易收据超时: {tx_hash}")

    def _sync_block(self, n: int) -> Block:
        """从链上获取区块信息并缓存。"""
        b = self._rpc_call("eth_getBlockByNumber", [hex(n), False, str(self._group_id)])
        if not b:
            return self._blocks_cache.get(n) or Block(n, "0x0", "0x0", 0, 0, "0x0", 0)
        blk = Block(
            number=int(b.get("number", "0x0"), 16),
            hash=b.get("hash", "0x0"),
            parent_hash=b.get("parentHash", "0x0"),
            timestamp=int(b.get("timestamp", "0x0"), 16),
            tx_count=len(b.get("transactions", [])),
            miner=b.get("miner", "0x0"),
            size=int(b.get("size", "0x0"), 16),
        )
        self._blocks_cache[blk.number] = blk
        return blk

    # ---------- 账户 ----------
    def get_accounts(self) -> List[str]:
        return list(self._accounts)

    def resolve_account(self, alias: str) -> str:
        if not alias:
            return self._accounts[0]
        a = alias.strip().lower()
        if a in self._alias_to_addr:
            return self._alias_to_addr[a]
        if a.startswith("0x") and len(a) == 42:
            return a
        # 未知别名：从密钥库生成/读取其专属独立账户（持久化），杜绝共享账户串扰
        addr, pk = ks.get_or_create_account(a)
        self._alias_to_addr[a] = addr
        self._acct_keys[addr] = pk
        return addr

    # ---------- 代码检查 ----------
    def has_code(self, address: str) -> bool:
        """检查指定地址是否有合约代码（用于识别 stale 部署记录）。"""
        try:
            a = address if address.startswith("0x") else self.resolve_account(address)
            code = self._rpc_call("eth_getCode", [a, "latest"])
            return bool(code) and code != "0x"
        except Exception:
            return False

    # ---------- 余额 ----------
    def get_balance(self, address: str) -> int:
        """查询账户原生代币余额（wei），通过真实 JSON-RPC 返回链上数值。"""
        a = address if address.startswith("0x") else self.resolve_account(address)
        bal = self._rpc_call("eth_getBalance", [a, "latest"])
        return int(bal, 16) if bal else 0

    # ---------- 区块 ----------
    def block_number(self) -> int:
        return int(self._rpc_call("eth_blockNumber", [str(self._group_id)]), 16)

    def get_block(self, n: int) -> Optional[Block]:
        if n in self._blocks_cache:
            return self._blocks_cache[n]
        return self._sync_block(n)

    def get_block_by_hash(self, h: str) -> Optional[Block]:
        b = self._rpc_call("eth_getBlockByHash", [h, False, str(self._group_id)])
        if not b:
            return None
        blk = Block(
            number=int(b.get("number", "0x0"), 16),
            hash=b.get("hash", "0x0"),
            parent_hash=b.get("parentHash", "0x0"),
            timestamp=int(b.get("timestamp", "0x0"), 16),
            tx_count=len(b.get("transactions", [])),
            miner=b.get("miner", "0x0"),
            size=int(b.get("size", "0x0"), 16),
        )
        self._blocks_cache[blk.number] = blk
        return blk

    def list_blocks(self, start: int, end: int) -> List[Block]:
        end = min(end, self.block_number())
        start = max(0, start)
        out = []
        for n in range(end, start - 1, -1):
            b = self.get_block(n)
            if b:
                out.append(b)
        return out

    # ---------- 交易 ----------
    def get_tx(self, tx_hash: str) -> Optional[Transaction]:
        h = tx_hash.lower()
        for t in self._txs:
            if t.hash.lower() == h:
                return t
        # 尝试从链上查（显式传入 groupId）
        tx_data = self._rpc_call("eth_getTransactionByHash", [tx_hash, str(self._group_id)])
        if not tx_data:
            return None
        receipt = self._rpc_call("eth_getTransactionReceipt", [tx_hash, str(self._group_id)]) or {}
        bn = int(tx_data.get("blockNumber", "0x0"), 16)
        return self._build_tx_from_rpc(tx_data, receipt, bn)

    def list_txs(self, limit: int = 50, offset: int = 0) -> List[Transaction]:
        """最新交易分页（任务 #20）：优先查 DB，DB 不可用回退内存。"""
        try:
            txs = _txs_from_db(limit=limit, offset=offset, class_id=self._class_id)
        except Exception:
            items = list(reversed(self._txs))
            start = int(offset or 0)
            return items[start:start + int(limit)] if int(limit) > 0 else items[start:]
        height = self.block_number()
        for t in txs:
            t.confirmations = max(0, height - t.block_number)
        return txs

    def list_txs_by_address(self, addr: str, limit: Optional[int] = None, offset: int = 0) -> List[Transaction]:
        a = (addr or "").lower()
        try:
            where = "(from_addr = ? OR to_addr = ? OR COALESCE(contract_address, '') = ?)"
            txs = _txs_from_db(where, [a, a, a], limit=limit, offset=offset,
                               class_id=self._class_id)
        except Exception:
            items = [t for t in reversed(self._txs)
                     if t.from_addr.lower() == a or t.to_addr.lower() == a
                     or (t.contract_address or "").lower() == a]
            start = int(offset or 0)
            return items[start:] if limit is None else items[start:start + int(limit)]
        height = self.block_number()
        for t in txs:
            t.confirmations = max(0, height - t.block_number)
        return txs

    def _build_tx_from_rpc(self, tx_data: dict, receipt: dict, block_number: int) -> Transaction:
        logs = []
        for lg in receipt.get("logs", []):
            logs.append({
                "address": lg.get("address", ""),
                "topics": lg.get("topics", []),
                "data": lg.get("data", "0x"),
                "log_index": int(lg.get("logIndex", "0x0"), 16),
            })
        blk = self.get_block(block_number)
        gas_used = int(receipt.get("gasUsed", "0x0"), 16)
        gas_price = GAS_PRICE
        gas_cost_wei = gas_used * gas_price
        gas_cost_gwei = gas_cost_wei / 1e9
        current_block = self.block_number()
        confirmations = max(0, current_block - block_number)
        return Transaction(
            hash=tx_data.get("hash", ""),
            block_number=block_number,
            from_addr=tx_data.get("from", "").lower(),
            to_addr=(tx_data.get("to") or "").lower(),
            value=str(int(tx_data.get("value", "0x0"), 16)),
            input=tx_data.get("input", ""),
            output=receipt.get("output", ""),
            status=int(receipt.get("status", "0x1"), 16),
            timestamp=blk.timestamp if blk else int(time.time()),
            contract_address=receipt.get("contractAddress"),
            method=None,
            parsed_args=None,
            gas_used=gas_used,
            gas_price=gas_price,
            gas_cost_wei=gas_cost_wei,
            gas_cost_gwei=gas_cost_gwei,
            confirmations=confirmations,
            logs=logs,
        )

    def _record_tx(self, tx_hash, block_number, from_addr, to_addr, value,
                   input_data, receipt, method=None, parsed_args=None, output=""):
        tx = self._build_tx_from_rpc(
            {"hash": tx_hash, "from": from_addr, "to": to_addr, "value": value, "input": input_data},
            receipt, block_number,
        )
        tx.method = method
        tx.parsed_args = parsed_args
        tx.output = output
        self._txs.append(tx)
        # 任务 #20：同步持久化到 SQLite（fisco 实例 class_id=''，同时写 blocks 缓存）
        _persist_tx_db(
            tx, class_id=self._class_id,
            persist_block=not self._class_id,
            block=self._blocks_cache.get(block_number),
        )
        # 任务 #21：交易确认 → 事件总线（FISCO 后端）
        events_bus.publish(
            events_bus.BusEvent.TX_CONFIRMED,
            {"tx_hash": tx.hash, "block_number": block_number,
             "from": tx.from_addr, "to": tx.to_addr,
             "method": tx.method or "", "status": tx.status,
             "contract_address": tx.contract_address or ""},
            class_id=self._class_id)
        return tx

    # ---------- 部署 ----------
    def deploy_contract(self, name, abi, bytecode, source, deployer, standard=None, ctor_args=None) -> Dict:
        with self._lock:
            sender = self.resolve_account(deployer)
            data = _norm_hex(bytecode)
            ctor_types, ctor_vals = _encode_ctor_args(abi, ctor_args)
            if ctor_types:
                data += abi_encode(ctor_types, ctor_vals).hex()
            full_data = "0x" + data if not data.startswith("0x") else data
            try:
                tx_hash, block_number, receipt = self._sign_and_send(sender, "", full_data)
                self._sync_block(block_number)
                addr = receipt.get("contractAddress", "")
                if not addr:
                    # FISCO-BCOS 可能不返回 contractAddress，从 receipt logs 推导
                    addr = receipt.get("logs", [{}])[0].get("address", "") if receipt.get("logs") else ""
                self._record_tx(
                    tx_hash, block_number, sender, "", "0", full_data, receipt,
                    method="constructor", parsed_args={"name": name, "ctor_args": ctor_args or []},
                    output=addr,
                )
                # 任务 #25 评审修复：DEPLOYED 事件统一由 contracts 路由层发布（带 user_id 定向），
                # FISCO 链客户端不再重复发布；本部署交易的 TX_CONFIRMED 已由 _record_tx 发出。
                return {
                    "address": addr, "name": name, "tx_hash": tx_hash,
                    "block_number": block_number, "standard": standard,
                    "gas_used": int(receipt.get("gasUsed", "0x0"), 16),
                    "status": int(receipt.get("status", "0x1"), 16),
                }
            except Exception as e:
                raise RuntimeError(f"FISCO 部署失败: {e}") from e

    # ---------- 调用 ----------
    def call_contract(self, address, method, args, caller, abi) -> Dict:
        addr = address if address.startswith("0x") else self.resolve_account(address)
        fn_abi = _find_fn_abi(abi, method)
        if not fn_abi:
            raise RuntimeError(f"未在 ABI 中找到方法 {method}")
        is_readonly = fn_abi.get("stateMutability") in ("view", "pure") or fn_abi.get("constant", False)
        sender = self.resolve_account(caller)
        selector = function_abi_to_4byte_selector(fn_abi)
        in_types = [i["type"] for i in fn_abi.get("inputs", [])]
        encoded_args = abi_encode(in_types, _coerce_args(in_types, args)) if in_types else b""
        calldata = "0x" + selector.hex() + encoded_args.hex()

        if is_readonly:
            try:
                out_raw = self._rpc_call("eth_call", [{"from": sender, "to": addr, "data": calldata}, "latest"])
                if not out_raw or out_raw == "0x":
                    return {"ok": True, "readonly": True, "result": None, "raw": "0x", "method": method, "args": args, "status": "success"}
                out_types = [o["type"] for o in fn_abi.get("outputs", [])]
                decoded = abi_decode(out_types, _to_bytes(out_raw)) if out_types else []
                decoded_str = _stringify_decoded(out_types, decoded)
                return {"ok": True, "readonly": True, "result": decoded_str, "raw": out_raw, "method": method, "args": args, "status": "success"}
            except Exception as e:
                return {"ok": False, "readonly": True, "error": str(e), "method": method, "args": args, "status": "reverted"}

        # 状态变更
        with self._lock:
            try:
                tx_hash, block_number, receipt = self._sign_and_send(sender, addr, calldata)
                self._sync_block(block_number)
                tx_obj = self._record_tx(
                    tx_hash, block_number, sender, addr, "0", calldata, receipt,
                    method=method, parsed_args={"method": method, "args": args},
                    output=receipt.get("output", ""),
                )
                return {
                    "ok": True, "readonly": False, "tx_hash": tx_hash,
                    "block_number": block_number,
                    "gas_used": int(receipt.get("gasUsed", "0x0"), 16),
                    "status": "success" if int(receipt.get("status", "0x1"), 16) == 1 else "reverted",
                    "result": "tx success", "logs": tx_obj.logs,
                    "method": method, "args": args,
                }
            except Exception as e:
                raise RuntimeError(f"FISCO 调用失败: {e}") from e

    # ---------- 转账 ----------
    def send_tx(self, from_addr, to_addr, value, data=""):
        with self._lock:
            sender = self.resolve_account(from_addr)
            recipient = self.resolve_account(to_addr) if to_addr and not to_addr.startswith("0x") else to_addr
            val = int(value) if str(value).isdigit() else 0
            try:
                tx_hash, block_number, receipt = self._sign_and_send(sender, recipient, data or "0x", value=val)
                self._sync_block(block_number)
                self._record_tx(tx_hash, block_number, sender, recipient, str(val), data or "", receipt,
                                method="transfer", parsed_args={"to": to_addr, "value": value})
                return {"tx_hash": tx_hash, "block_number": block_number,
                        "status": "success", "gas_used": int(receipt.get("gasUsed", "0x0"), 16)}
            except Exception as e:
                raise RuntimeError(f"FISCO 转账失败: {e}") from e


# ===========================================================================
# 客户端工厂（默认全局单例 + 班级级链空间注册表）
# ===========================================================================
_client: Optional[ChainClient] = None
_init_lock = threading.Lock()

# 任务 #20：班级级链空间注册表（线程安全，_registry_lock 保护）。
# - fisco: class_id 确定性映射 groupId，同 group 共享一个客户端（N:1 复用）
# - evm  : 每班一个 RealEvmChainClient，LRU 上限 8，逐出前快照落盘、重入惰性恢复
# - mock : 每班一个独立 MockChainClient
_registry_lock = threading.Lock()
_fisco_by_group: Dict[int, FiscoRpcClient] = {}
_mock_by_class: Dict[str, MockChainClient] = {}
_evm_by_class: OrderedDict[str, RealEvmChainClient] = OrderedDict()
EVM_CLASS_LRU_MAX = 8


def _default_client() -> ChainClient:
    """构建/返回默认全局链客户端（class_id=None 语义，行为与历史版本一致）。"""
    global _client
    if _client is None:
        with _init_lock:
            if _client is None:
                mode = settings.chain_mode.lower()
                if mode == "fisco":
                    # 显式错误路径：连接失败直接抛出，由路由层转为 503 告知前端，
                    # 禁止回退到 evm/mock（与“真实联盟链”宣称保持一致）
                    _client = FiscoRpcClient()
                    print(
                        f"[chain] 已连接真实 FISCO-BCOS 节点: {settings.fisco_rpc_url}"
                        f" (groupId={_client._group_id}, chainId={_client._chain_id})"
                    )
                elif mode == "mock":
                    _client = MockChainClient()
                    print("[chain] 使用 mock 模拟链")
                else:
                    # 默认 evm 模式（初始化失败降级 mock 的行为保持不变）
                    try:
                        _client = RealEvmChainClient()
                    except Exception as e:
                        print(f"[chain] py-evm 初始化失败，降级 mock: {e}")
                        _client = MockChainClient()
    return _client


def _class_group_id(class_id: str) -> int:
    """class_id → FISCO groupId 的确定性映射。

    sha256(class_id) 前 8 字节取模映射到 FISCO_GROUP_RANGE = [lo, hi]，
    稳定可复现：同一班级始终落在同一分组；不同班级可能共享分组（N:1），
    由 FISCO groupId 维度天然隔离教学数据。
    """
    lo, hi = settings.fisco_group_bounds
    digest = hashlib.sha256(class_id.strip().encode("utf-8")).digest()
    return lo + (int.from_bytes(digest[:8], "big") % (hi - lo + 1))


def _evict_oldest_evm() -> None:
    """LRU 逐出最旧的班级 EVM 实例：先快照落盘再关闭。

    快照失败仅日志降级，不阻断逐出（内存实例此时已移出注册表）。
    快照语义：EVM 执行状态（合约代码/存储）无法跨实例序列化，快照保存
    业务可见层（账户经 keystore 复原、交易历史），与进程重启行为一致。
    """
    _, victim = _evm_by_class.popitem(last=False)
    try:
        victim.save_snapshot()
    except Exception as exc:  # 快照失败不影响逐出
        print(f"[chain] 班级链快照落盘失败(class_id={victim._class_id}): {exc}")
    finally:
        try:
            victim.shutdown()
        except Exception:
            pass


def get_chain_client(class_id: Optional[str] = None) -> ChainClient:
    """获取链客户端（默认全局单例；传 class_id 返回班级级隔离实例）。

    - class_id 为 None/空串：返回默认全局单例（与历史无参调用完全兼容，
      现有路由/服务均无参调用，行为不变）。
    - class_id 非空：按 CHAIN_MODE 返回班级级实例：
        fisco → class_id 确定性映射 groupId，同 group 复用同一 FiscoRpcClient
                （建连失败抛 ChainUnavailableError，不缓存、不降级）；
        evm   → 班级专属 RealEvmChainClient（LRU ≤8，逐出前快照落盘、
                重入时构造内自动从快照恢复；初始化失败降级班级 mock）；
        mock  → 班级专属 MockChainClient。
    线程安全：注册表读写均在 _registry_lock 内；全局单例仍由 _init_lock 保护。
    注意：本任务不改路由调用方（均为无参调用），班级隔离接线由后续任务完成。
    """
    if not class_id or not str(class_id).strip():
        return _default_client()
    cid = str(class_id).strip()
    mode = settings.chain_mode.lower()
    with _registry_lock:
        if mode == "fisco":
            group = _class_group_id(cid)
            c = _fisco_by_group.get(group)
            if c is None:
                # 建连失败直接向上抛 ChainUnavailableError，不写注册表
                c = FiscoRpcClient(group_id=group)
                _fisco_by_group[group] = c
                print(f"[chain] 班级链(fisco) class_id={cid} -> groupId={group}")
            return c
        if mode == "mock":
            c = _mock_by_class.get(cid)
            if c is None:
                c = _mock_by_class[cid] = MockChainClient(class_id=cid)
                print(f"[chain] 班级链(mock) class_id={cid}")
            return c
        # evm（默认）：LRU 命中即复用；未命中新建（构造内自动尝试快照恢复），
        # 初始化失败降级班级 mock（与全局 evm→mock 降级策略一致）
        c = _evm_by_class.get(cid)
        if c is not None:
            _evm_by_class.move_to_end(cid)
            return c
        try:
            c = RealEvmChainClient(class_id=cid)
        except Exception as e:
            print(f"[chain] 班级 py-evm 初始化失败(class_id={cid})，降级 mock: {e}")
            c = _mock_by_class.get(cid)
            if c is None:
                c = _mock_by_class[cid] = MockChainClient(class_id=cid)
            return c
        _evm_by_class[cid] = c
        while len(_evm_by_class) > EVM_CLASS_LRU_MAX:
            _evict_oldest_evm()
        print(f"[chain] 班级链(evm) class_id={cid} (LRU {len(_evm_by_class)}/{EVM_CLASS_LRU_MAX})")
        return c


def get_chain_mode_label() -> str:
    """返回当前链模式的可读标签（供 API 返回给前端展示）。"""
    c = get_chain_client()
    if isinstance(c, FiscoRpcClient):
        return "fisco"
    elif isinstance(c, RealEvmChainClient):
        return "evm"
    return "mock"


def describe_mode() -> Dict[str, Any]:
    """描述当前链模式与真实状态，供 /api/chain/status 与 /health 接入。

    返回 {mode, real, description}：
      - mode        : 配置的 CHAIN_MODE（fisco / evm / mock）
      - real        : 是否连接到真实链节点（仅 fisco 且连通时为 True）
      - description : 中文可读描述（含节点地址与失败原因）
    evm/mock 模式声明为“非真实链”，不会尝试初始化重客户端。
    """
    mode = settings.chain_mode.lower()
    if mode == "mock":
        return {"mode": "mock", "real": False,
                "description": "内存模拟链（mock），仅用于无链环境兜底演示"}
    if mode == "evm":
        return {"mode": "evm", "real": False,
                "description": "py-evm 进程内单例（真实 EVM 执行，非外部链节点）"}
    # fisco 模式：若客户端已成功初始化则直接认定已连接；
    # 否则做一次轻量探测（不缓存客户端，避免在只读探测时建立重状态）
    global _client
    with _init_lock:
        c = _client
    if isinstance(c, FiscoRpcClient):
        return {"mode": "fisco", "real": True,
                "description": f"已连接真实 FISCO-BCOS 节点: {settings.fisco_rpc_url}"
                               f" (groupId={c._group_id}, chainId={c._chain_id})"}
    try:
        import httpx
        resp = httpx.post(
            settings.fisco_rpc_url,
            json={"jsonrpc": "2.0", "method": "eth_blockNumber",
                  "params": [str(settings.fisco_group_id)], "id": 1},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise RuntimeError(f"RPC error: {data['error']}")
        height = int(data.get("result", "0x0"), 16)
        return {"mode": "fisco", "real": True,
                "description": f"已连接真实 FISCO-BCOS 节点: {settings.fisco_rpc_url}"
                               f" (groupId={settings.fisco_group_id}, 当前块高 {height})"}
    except Exception as e:
        return {"mode": "fisco", "real": False,
                "description": f"FISCO-BCOS 节点不可达: {settings.fisco_rpc_url}，原因: {e}"}
