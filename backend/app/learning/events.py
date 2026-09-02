"""学习行为埋点收口（learning_events 唯一写入 / 聚合事实源）。

背景（历史教训）：埋点写入助手 _track 曾在 routers/ide.py、routers/contracts.py、
routers/eco.py、routers/report.py、learning/tutorial_engine.py 五处各自复制一份；
事件名字符串漂移曾导致成就永不可达（见 routers/achievements.py 模块注释：
旧实现查询 'security_audit' 而真实埋点是 'contract_audit'）。

本模块统一三件事：
- EventType    全部事件类型常量。值与历史落库字符串完全一致（不得改名，
               保证历史数据兼容）；新增事件必须先在此登记再使用。
- track()      唯一写入入口：参数化 SQL + db 全局锁（与 db.init_db 同风格），
               异常只记日志不抛出（与历史 _track 行为一致，不阻塞业务请求，
               兼容旧 DB 尚无 learning_events 表）。
- aggregate()  4 维实训评分（grades._compute_training_score）所需的原始计数
               聚合，查询口径与原实现逐字一致（钱包候选集 + lower(wallet) IN）；
               只做计数，不含评分公式与封顶逻辑。

注：db.py learning_events 建表注释中的 'nft_mint_ok' 为历史遗留文案，
全库无任何写入 / 查询使用，故不设常量。
"""
from __future__ import annotations

import json
import logging
from typing import Sequence

from ..db import _lock as _DB_LOCK, get_conn, now
from ..security import lower_wallet_in, resolve_wallet_candidates

logger = logging.getLogger(__name__)


class EventType:
    """learning_events.event_type 全量常量（与历史落库字符串逐字一致）。"""

    IDE_OPEN_BUILTIN = "ide_open_builtin"            # 打开内置合约模板（contracts.py GET /builtin/{name}）
    IDE_SAVE_PROJECT = "ide_save_project"            # 保存 .sol 工程文件（ide.py POST /files）
    CONTRACT_COMPILE_OK = "contract_compile_ok"      # solc 编译成功（contracts.py /compile、教程部署 GreenEnergy）
    CONTRACT_COMPILE_FAIL = "contract_compile_fail"  # solc 编译失败（contracts.py /compile）
    INTERFACE_INVOKE = "interface_invoke"            # 合约接口调试调用（contracts.py /invoke）
    CONTRACT_AUDIT = "contract_audit"                # 合约安全审计（contracts.py /audit）
    ECO_ROLE_SWITCH = "eco_role_switch"              # 联盟角色切换（eco.py /role/select）
    ECO_ENERGY_ISSUE = "eco_energy_issue"            # 绿色能量发放（eco.py /energy/issue）
    ECO_CERT_EXCHANGE = "eco_cert_exchange"          # 植树证书兑换（eco.py /certificates/exchange）
    ECO_BADGE_EXCHANGE = "eco_badge_exchange"        # 勋章 / 骑行券兑换（eco.py /badges/exchange）
    BADGE_TYPE_ADD = "badge_type_add"                # 新增勋章类型（eco.py /badges/types）
    BADGE_MINT = "badge_mint"                        # 联盟角色铸造勋章（eco.py /badges/mint）
    REPORT_VIEW = "report_view"                      # 查看 / 下载实训报告（report.py 3 处端点）


def track(event_type: str, target: str = "", ref_id: str = "", wallet: str = "", extra: dict | None = None) -> None:
    """统一学习行为埋点写入（签名与历史各路由的 _track 完全一致）。

    - 参数化 SQL + db 全局锁，风格与 db.init_db 一致；
    - 失败只记日志不抛出：埋点不阻塞业务请求（兼容旧 DB 无 learning_events 表）。
    """
    try:
        with _DB_LOCK, get_conn() as conn:
            conn.execute(
                "INSERT INTO learning_events(wallet,event_type,target,ref_id,extra,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (wallet, event_type, target, ref_id,
                 json.dumps(extra or {}, ensure_ascii=False), now()),
            )
    except Exception:
        logger.warning("learning_events 埋点写入失败 event_type=%s", event_type, exc_info=True)


# aggregate 输出中的事件计数键（值即 event_type，键名与 grades.py metrics 一致）
_AGG_EVENT_KEYS = (
    EventType.IDE_OPEN_BUILTIN,
    EventType.IDE_SAVE_PROJECT,
    EventType.CONTRACT_COMPILE_OK,
    EventType.INTERFACE_INVOKE,
    EventType.ECO_ROLE_SWITCH,
    EventType.REPORT_VIEW,
)


def aggregate(wallet_or_candidates: str | Sequence[str]) -> dict:
    """聚合 4 维实训评分所需的原始计数（只计数，不含评分公式与封顶逻辑）。

    - 传 str：先经 security.resolve_wallet_candidates 求候选集（双轨口径：
      写路径 0xlearner / 读路径 userId，统一 lower(wallet) IN 匹配）；
    - 传候选序列：视为已备好的钱包候选集直接使用；
    - 返回扁平计数 dict，键名与 grades.py _compute_training_score 的
      metrics 键完全一致；候选集为空时返回全 0。
    """
    if isinstance(wallet_or_candidates, str):
        with get_conn() as conn:
            cands = resolve_wallet_candidates(conn, wallet_or_candidates)
    else:
        cands = list(wallet_or_candidates)

    out: dict = {
        "ide_open_builtin": 0, "ide_save_project": 0, "contract_compile_ok": 0,
        "interface_invoke": 0, "eco_role_switch": 0, "report_view": 0,
        "deployed_contracts": 0, "contract_calls": 0, "transactions": 0,
        "nft_mint": 0, "nft_trade": 0, "erc20_transfer": 0,
        "energy_issue": 0, "tutorial_done": 0,
        "eco_market_trade": 0,
    }
    if not cands:
        return out

    h, lc = lower_wallet_in(cands)
    lc2 = lc + lc  # from/to 双列 OR 场景：同一占位符片段复用两份参数
    with get_conn() as conn:
        # 1) 学习事件按类型计数
        event_counts = {
            r["event_type"]: r["cnt"]
            for r in conn.execute(
                f"SELECT event_type, COUNT(*) AS cnt FROM learning_events "
                f"WHERE lower(wallet) IN ({h}) GROUP BY event_type",
                lc,
            ).fetchall()
        }
        for k in _AGG_EVENT_KEYS:
            out[k] = event_counts.get(k, 0)
        # 2) 已部署合约数（该钱包候选集内部署的）
        out["deployed_contracts"] = conn.execute(
            f"SELECT COUNT(*) AS c FROM deployed_contracts WHERE lower(deployer) IN ({h})",
            lc,
        ).fetchone()["c"]
        # 3) 合约调用次数（该钱包候选集内调用的）
        out["contract_calls"] = conn.execute(
            f"SELECT COUNT(*) AS c FROM contract_calls WHERE lower(caller) IN ({h})",
            lc,
        ).fetchone()["c"]
        # 4) 链上交易笔数（该钱包候选集发起 / 接收）
        out["transactions"] = conn.execute(
            f"SELECT COUNT(*) AS c FROM transactions "
            f"WHERE lower(from_addr) IN ({h}) OR lower(to_addr) IN ({h})",
            lc2,
        ).fetchone()["c"]
        # 5) NFT 铸造数（该钱包候选集作为作者）
        out["nft_mint"] = conn.execute(
            f"SELECT COUNT(*) AS c FROM nfts WHERE lower(author) IN ({h})",
            lc,
        ).fetchone()["c"]
        # 6) NFT 交易数（该钱包候选集买 / 卖）
        out["nft_trade"] = conn.execute(
            f"SELECT COUNT(*) AS c FROM nft_trades "
            f"WHERE lower(from_addr) IN ({h}) OR lower(to_addr) IN ({h})",
            lc2,
        ).fetchone()["c"]
        # 7) ERC20 转账数
        out["erc20_transfer"] = conn.execute(
            f"SELECT COUNT(*) AS c FROM wallet_transfers "
            f"WHERE lower(from_addr) IN ({h}) OR lower(to_addr) IN ({h})",
            lc2,
        ).fetchone()["c"]
        # 8) 绿色能量发放数（该钱包候选集作为接收方）
        out["energy_issue"] = conn.execute(
            f"SELECT COUNT(*) AS c FROM eco_energy_records WHERE lower(wallet) IN ({h})",
            lc,
        ).fetchone()["c"]
        # 9) 搭链教程完成步数（done=1）。该表懒建表，未进过教程的库可能不存在，
        #    容错为 0，不影响其余维度计算（与原 grades.py 口径一致）。
        try:
            out["tutorial_done"] = conn.execute(
                f"SELECT COUNT(*) AS c FROM chain_tutorial_progress "
                f"WHERE lower(wallet) IN ({h}) AND done=1",
                lc,
            ).fetchone()["c"]
        except Exception:
            out["tutorial_done"] = 0
        # 10) 绿色资产市场成交数（该钱包候选集买/卖；业务闭环最后一环）。
        #     绿色资产本身就是链上 NFT，成交即流通；旧库无该表时容错为 0。
        try:
            out["eco_market_trade"] = conn.execute(
                f"SELECT COUNT(*) AS c FROM eco_market_listings "
                f"WHERE status='sold' AND (lower(seller) IN ({h}) OR lower(buyer) IN ({h}))",
                lc2,
            ).fetchone()["c"]
        except Exception:
            out["eco_market_trade"] = 0
    return out
