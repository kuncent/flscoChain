"""链客户端统一接口层。

支持三种后端，通过环境变量 CHAIN_MODE 切换：
  - fisco : 连接真实 FISCO-BCOS 节点（通过 JSON-RPC + eth-account 签名）
  - evm   : py-evm / eth-tester 进程内单例（默认，无需外部依赖）
  - mock  : 内存模拟兜底

所有后端实现相同的 ChainClient 接口，上层路由无感知。
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from eth_abi import encode as abi_encode, decode as abi_decode
from eth_utils import function_abi_to_4byte_selector, to_checksum_address

from .config import settings

GAS_PRICE = 8750000000  # 适配 Cancun base fee
GAS_LIMIT = 8_000_000


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
    def list_txs(self, limit: int = 50) -> List[Transaction]: ...
    def list_txs_by_address(self, addr: str) -> List[Transaction]: ...
    def deploy_contract(self, name, abi, bytecode, source, deployer, standard=None, ctor_args=None) -> Dict: ...
    def call_contract(self, address, method, args, caller, abi) -> Dict: ...
    def send_tx(self, from_addr, to_addr, value, data="") -> Dict: ...
    def get_accounts(self) -> List[str]: ...
    def resolve_account(self, alias: str) -> str: ...
    def has_code(self, address: str) -> bool: ...
    def get_balance(self, address: str) -> int: ...


# ===========================================================================
# 真实 EVM 实现
# ===========================================================================
class RealEvmChainClient(ChainClient):
    """基于 py-evm 的真实 EVM 链客户端。

    进程内单例，状态持久化：部署的合约、余额、交易记录跨请求保留。
    """

    def __init__(self):
        from eth_tester import EthereumTester
        from eth_tester.backends.pyevm.main import PyEVMBackend
        self._tester = EthereumTester(PyEVMBackend())
        self._lock = threading.Lock()
        self._txs: List[Transaction] = []
        self._blocks_cache: Dict[int, Block] = {}
        # 创世账户 → 别名映射
        accts = self._tester.get_accounts()
        self._alias_to_addr: Dict[str, str] = {}
        # 固定映射：6 个联盟角色 + 4 个用户角色 = 10 个独立私钥地址
        # 严格顺序：联盟角色用前 6 个地址，用户角色用后 4 个地址，保证不会复用同一私钥
        self._default_aliases = [
            # 索引 0-5：联盟角色 → 独立私钥地址
            "0xadmin", "0xmetro", "0xbus", "0xbike", "0xtakeout", "0xrecycle",
            # 索引 6-9：用户角色 → 独立私钥地址
            "0xlearner", "0xnft", "0xalice", "0xbob",
        ]
        for i, alias in enumerate(self._default_aliases):
            if i < len(accts):
                self._alias_to_addr[alias] = accts[i].lower()
        # 兼容旧别名（0xcarol/dave/... 等）：映射到剩余地址或复用最后一个
        self._compat_aliases = ["0xcarol", "0xdave", "0xeve", "0xfrank", "0xgrace", "0xheidi"]
        for j, alias in enumerate(self._compat_aliases):
            idx = 9 - j  # 倒序映射，避免与 0-5 联盟角色、6-9 标准用户冲突（若不足则复用最后一个账户）
            if idx < 0:
                idx = 9
            self._alias_to_addr.setdefault(alias, accts[idx].lower() if idx < len(accts) else accts[-1].lower())
        # 记录创世块
        self._sync_block(0)

    # ---------- 账户 ----------
    def get_accounts(self) -> List[str]:
        return [a.lower() for a in self._tester.get_accounts()]

    def resolve_account(self, alias: str) -> str:
        """把别名/地址解析为 EVM 真实账户地址。"""
        if not alias:
            return self._tester.get_accounts()[0]
        a = alias.lower()
        if a in self._alias_to_addr:
            return self._alias_to_addr[a]
        # 若是已知真实地址
        for addr in self._tester.get_accounts():
            if addr.lower() == a:
                return addr.lower()
        # 未知别名：按 hash 分配一个创世账户（保证同一别名稳定映射）
        idx = int(hashlib.sha256(a.encode()).hexdigest(), 16) % 10
        addr = self._tester.get_accounts()[idx].lower()
        self._alias_to_addr[a] = addr
        return addr

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

    def list_txs(self, limit: int = 50) -> List[Transaction]:
        return list(reversed(self._txs))[:limit]

    def list_txs_by_address(self, addr: str) -> List[Transaction]:
        a = addr.lower()
        return [t for t in reversed(self._txs)
                if t.from_addr.lower() == a or t.to_addr.lower() == a
                or (t.contract_address or "").lower() == a]

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
        return tx

    # ---------- 部署 ----------
    def deploy_contract(self, name, abi, bytecode, source, deployer, standard=None, ctor_args=None) -> Dict:
        with self._lock:
            sender = self.resolve_account(deployer)
            # 构造完整部署 data = bytecode + 编码后的构造函数参数
            data = _norm_hex(bytecode)
            ctor_types, ctor_vals = _encode_ctor_args(abi, ctor_args)
            if ctor_types:
                data += abi_encode(ctor_types, ctor_vals).hex()
            tx = {
                "from": sender, "to": "",  # 部署交易 to 为空
                "data": "0x" + data if not data.startswith("0x") else data,
                "gas": GAS_LIMIT, "value": 0, "gas_price": GAS_PRICE,
            }
            try:
                tx_hash = self._tester.send_transaction(tx)
                receipt = self._tester.get_transaction_receipt(tx_hash)
                block_number = receipt["block_number"]
                self._sync_block(block_number)
                addr = _hex(receipt["contract_address"])
                self._record_tx(
                    tx_hash, block_number, sender, "", "0",
                    tx["data"], receipt, method="constructor",
                    parsed_args={"name": name, "ctor_args": ctor_args or []},
                    output=addr,
                )
                return {
                    "address": addr, "name": name, "tx_hash": _hex(tx_hash),
                    "block_number": block_number, "standard": standard,
                    "gas_used": int(receipt.get("gas_used", 0)),
                    "status": int(receipt.get("status", 1)),
                }
            except Exception as e:
                raise RuntimeError(f"部署失败: {e}") from e

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

        # 状态变更交易
        with self._lock:
            try:
                tx_hash = self._tester.send_transaction({
                    "from": sender, "to": addr, "data": calldata,
                    "gas": GAS_LIMIT, "value": 0, "gas_price": GAS_PRICE,
                })
                receipt = self._tester.get_transaction_receipt(tx_hash)
                block_number = receipt["block_number"]
                self._sync_block(block_number)
                parsed = {"method": method, "args": args}
                tx_obj = self._record_tx(
                    tx_hash, block_number, sender, addr, "0", calldata, receipt,
                    method=method, parsed_args=parsed, output=_hex(receipt.get("output", "")),
                )
                return {
                    "ok": True, "readonly": False,
                    "tx_hash": _hex(tx_hash), "block_number": block_number,
                    "gas_used": int(receipt.get("gas_used", 0)),
                    "status": "success" if int(receipt.get("status", 1)) == 1 else "reverted",
                    "result": "tx success", "logs": tx_obj.logs,
                    "method": method, "args": args,
                }
            except Exception as e:
                raise RuntimeError(f"调用失败: {e}") from e

    # ---------- 转账 ----------
    def send_tx(self, from_addr, to_addr, value, data=""):
        with self._lock:
            sender = self.resolve_account(from_addr)
            recipient = self.resolve_account(to_addr) if to_addr and not to_addr.startswith("0x") else to_addr
            tx = {
                "from": sender, "to": recipient,
                "value": int(value) if str(value).isdigit() else 0,
                "gas": GAS_LIMIT, "gas_price": GAS_PRICE,
            }
            if data:
                tx["data"] = data if data.startswith("0x") else "0x" + data
            try:
                tx_hash = self._tester.send_transaction(tx)
                receipt = self._tester.get_transaction_receipt(tx_hash)
                bn = receipt["block_number"]
                self._sync_block(bn)
                self._record_tx(tx_hash, bn, sender, recipient, str(tx["value"]),
                                tx.get("data", ""), receipt, method="transfer",
                                parsed_args={"to": to_addr, "value": value})
                return {"tx_hash": _hex(tx_hash), "block_number": bn,
                        "status": "success", "gas_used": int(receipt.get("gas_used", 0))}
            except Exception as e:
                raise RuntimeError(f"转账失败: {e}") from e


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
    """内存模拟链兜底实现。"""
    def __init__(self):
        self._height = 0
        self._txs: List[Transaction] = []
        self._blocks = [Block(0, "0x" + "0" * 64, "0x0", int(time.time()), 0, "0x0", 0)]

    def block_number(self): return self._height - 1
    def get_block(self, n): return self._blocks[n] if 0 <= n < len(self._blocks) else None
    def get_block_by_hash(self, h): return next((b for b in self._blocks if b.hash == h), None)
    def list_blocks(self, s, e): return [b for b in reversed(self._blocks) if s <= b.number <= e]
    def get_tx(self, h): return next((t for t in self._txs if t.hash == h), None)
    def list_txs(self, limit=50): return list(reversed(self._txs))[:limit]
    def list_txs_by_address(self, a):
        al = a.lower()
        return [t for t in reversed(self._txs) if t.from_addr.lower() == al or t.to_addr.lower() == al]
    def get_accounts(self): return ["0xlearner", "0xalice", "0xbob"]
    def resolve_account(self, a): return a or "0xlearner"
    def deploy_contract(self, name, abi, bytecode, source, deployer, standard=None, ctor_args=None):
        import random
        addr = "0x" + hashlib.sha256(f"{name}{time.time()}{random.random()}".encode()).hexdigest()[:40]
        h = "0x" + hashlib.sha256(f"tx{time.time()}".encode()).hexdigest()
        bn = self._height
        self._txs.append(Transaction(h, bn, deployer, "", "0", bytecode[:200] or "", addr, 1, int(time.time()), addr, "constructor", {"name": name}))
        self._blocks.append(Block(bn, h, self._blocks[-1].hash, int(time.time()), 1, deployer, 0))
        self._height += 1
        return {"address": addr, "name": name, "tx_hash": h, "block_number": bn, "standard": standard, "gas_used": 0, "status": 1}
    def call_contract(self, address, method, args, caller, abi):
        return {"ok": True, "readonly": False, "tx_hash": "0xmock", "block_number": self._height, "result": f"mock {method}", "status": "success", "method": method, "args": args}
    def send_tx(self, f, t, v, data=""):
        h = "0x" + hashlib.sha256(f"tx{time.time()}".encode()).hexdigest()
        bn = self._height
        self._txs.append(Transaction(h, bn, f, t, str(v), data, "", 1, int(time.time()), None, "transfer", {"to": t, "value": v}))
        self._blocks.append(Block(bn, h, self._blocks[-1].hash, int(time.time()), 1, f, 0))
        self._height += 1
        return {"tx_hash": h, "block_number": bn, "status": "success", "gas_used": 0}
    def has_code(self, address: str) -> bool:
        return True

    def get_balance(self, address: str) -> int:
        """Mock 模式返回模拟余额（1 ETH）。"""
        return 10**18


# ===========================================================================
# 真实 FISCO-BCOS 节点客户端（JSON-RPC + eth-account 签名）
# ===========================================================================
class FiscoRpcClient(ChainClient):
    """通过 JSON-RPC 连接真实 FISCO-BCOS 节点的链客户端。

    FISCO-BCOS v2.x 的 JSON-RPC 端口（默认 8545）兼容以太坊标准 RPC：
    eth_blockNumber / eth_call / eth_sendRawTransaction / eth_getTransactionReceipt 等。

    本客户端使用 eth-account 离线签名交易，通过 eth_sendRawTransaction 广播，
    无需 FISCO Python SDK / Channel 协议 / 证书。
    """

    # 内置 10 个练习账户（eth-account 离线生成，每次启动固定）
    _GEN_KEYS = [
        "0x" + hashlib.sha256(f"fisco-learner-{i}".encode()).hexdigest() for i in range(10)
    ]

    def __init__(self):
        import httpx
        from eth_account import Account
        self._http = httpx.Client(timeout=15)
        self._rpc = settings.fisco_rpc_url
        self._lock = threading.Lock()
        self._txs: List[Transaction] = []
        self._blocks_cache: Dict[int, Block] = {}
        # 离线生成 10 个账户（私钥固定，地址固定）
        self._accounts: List[str] = []
        self._alias_to_addr: Dict[str, str] = {}
        self._acct_keys: Dict[str, str] = {}  # addr -> private_key
        # 固定映射：前 6 = 联盟角色，后 4 = 用户角色（与 RealEvmChainClient 顺序严格一致）
        aliases = [
            "0xadmin", "0xmetro", "0xbus", "0xbike", "0xtakeout", "0xrecycle",
            "0xlearner", "0xnft", "0xalice", "0xbob",
        ]
        for i, alias in enumerate(aliases):
            pk = self._GEN_KEYS[i]
            acct = Account.from_key(pk)
            addr = acct.address.lower()
            self._accounts.append(addr)
            self._alias_to_addr[alias] = addr
            self._acct_keys[addr] = pk
        # 测试连通性
        try:
            bn = self._rpc_call("eth_blockNumber")
            self._sync_block(int(bn, 16))
        except Exception as e:
            raise RuntimeError(f"无法连接 FISCO-BCOS 节点 {self._rpc}: {e}")

    # ---------- JSON-RPC 底层 ----------
    def _rpc_call(self, method: str, params: list = None) -> Any:
        """发送 JSON-RPC 请求，返回 result 字段。"""
        payload = {"jsonrpc": "2.0", "method": method, "params": params or [], "id": 1}
        r = self._http.post(self._rpc, json=payload)
        data = r.json()
        if "error" in data and data["error"]:
            raise RuntimeError(f"RPC error: {data['error']}")
        return data.get("result")

    def _sign_and_send(self, from_addr: str, to_addr: str, data: str, value: int = 0, gas: int = GAS_LIMIT) -> Tuple[str, int]:
        """离线签名并广播交易，返回 (tx_hash, block_number)。"""
        from eth_account import Account
        pk = self._acct_keys.get(from_addr)
        if not pk:
            raise RuntimeError(f"未知账户 {from_addr}，无对应私钥")
        nonce = int(self._rpc_call("eth_getTransactionCount", [from_addr, "latest"]), 16)
        gas_price_hex = hex(GAS_PRICE)
        tx = {
            "from": from_addr,
            "to": to_addr if to_addr else "",
            "data": data,
            "value": value,
            "gas": gas,
            "gasPrice": gas_price_hex,
            "nonce": nonce,
            "chainId": 1,
        }
        signed = Account.sign_transaction(tx, pk)
        raw_tx = "0x" + signed.raw_transaction.hex()
        tx_hash = self._rpc_call("eth_sendRawTransaction", [raw_tx])
        # 等待 receipt
        receipt = self._wait_receipt(tx_hash)
        block_number = int(receipt.get("blockNumber", "0x0"), 16)
        return tx_hash, block_number, receipt

    def _wait_receipt(self, tx_hash: str, timeout: int = 15) -> Dict:
        """轮询等待交易收据。"""
        for _ in range(timeout * 2):
            r = self._rpc_call("eth_getTransactionReceipt", [tx_hash])
            if r:
                return r
            time.sleep(0.5)
        raise RuntimeError(f"等待交易收据超时: {tx_hash}")

    def _sync_block(self, n: int) -> Block:
        """从链上获取区块信息并缓存。"""
        b = self._rpc_call("eth_getBlockByNumber", [hex(n), False])
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
        a = alias.lower()
        if a in self._alias_to_addr:
            return self._alias_to_addr[a]
        if a.startswith("0x") and len(a) == 42:
            return a
        # 未知别名按 hash 映射
        idx = int(hashlib.sha256(a.encode()).hexdigest(), 16) % len(self._accounts)
        addr = self._accounts[idx]
        self._alias_to_addr[a] = addr
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
        return int(self._rpc_call("eth_blockNumber"), 16)

    def get_block(self, n: int) -> Optional[Block]:
        if n in self._blocks_cache:
            return self._blocks_cache[n]
        return self._sync_block(n)

    def get_block_by_hash(self, h: str) -> Optional[Block]:
        b = self._rpc_call("eth_getBlockByHash", [h, False])
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
        # 尝试从链上查
        tx_data = self._rpc_call("eth_getTransactionByHash", [tx_hash])
        if not tx_data:
            return None
        receipt = self._rpc_call("eth_getTransactionReceipt", [tx_hash]) or {}
        bn = int(tx_data.get("blockNumber", "0x0"), 16)
        return self._build_tx_from_rpc(tx_data, receipt, bn)

    def list_txs(self, limit: int = 50) -> List[Transaction]:
        return list(reversed(self._txs))[:limit]

    def list_txs_by_address(self, addr: str) -> List[Transaction]:
        a = addr.lower()
        return [t for t in reversed(self._txs)
                if t.from_addr.lower() == a or t.to_addr.lower() == a
                or (t.contract_address or "").lower() == a]

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
# 单例工厂
# ===========================================================================
_client: Optional[ChainClient] = None
_init_lock = threading.Lock()


def get_chain_client() -> ChainClient:
    """获取链客户端单例。

    根据 CHAIN_MODE 环境变量选择后端：
      fisco → FiscoRpcClient（真实 FISCO-BCOS 节点，连不上自动降级到 evm）
      evm   → RealEvmChainClient（py-evm 单例，默认）
      mock  → MockChainClient（内存模拟兜底）
    """
    global _client
    if _client is None:
        with _init_lock:
            if _client is None:
                mode = settings.chain_mode.lower()
                if mode == "fisco":
                    try:
                        _client = FiscoRpcClient()
                        print(f"[chain] 已连接真实 FISCO-BCOS 节点: {settings.fisco_rpc_url}")
                    except Exception as e:
                        print(f"[chain] FISCO-BCOS 连接失败，降级到 py-evm: {e}")
                        try:
                            _client = RealEvmChainClient()
                        except Exception as e2:
                            print(f"[chain] py-evm 初始化也失败，降级 mock: {e2}")
                            _client = MockChainClient()
                elif mode == "mock":
                    _client = MockChainClient()
                    print("[chain] 使用 mock 模拟链")
                else:
                    # 默认 evm 模式
                    try:
                        _client = RealEvmChainClient()
                    except Exception as e:
                        print(f"[chain] py-evm 初始化失败，降级 mock: {e}")
                        _client = MockChainClient()
    return _client


def get_chain_mode_label() -> str:
    """返回当前链模式的可读标签（供 API 返回给前端展示）。"""
    c = get_chain_client()
    if isinstance(c, FiscoRpcClient):
        return "fisco"
    elif isinstance(c, RealEvmChainClient):
        return "evm"
    return "mock"
