"""绿色能量流水账（Energy Ledger）—— 余额的唯一事实源。

为什么需要独立的流水表（修 B1「资产易主 → 能量凭空回补」通胀漏洞）：
旧实现用 `SUM(cost_energy) WHERE owner = ?` 现算兑换成本，而市场成交会把
eco_certificates.owner / eco_badges.owner 改成 buyer —— 成本跟着归属跑：
  卖方：当初兑换扣掉的 1500 点随证书「离开」，账本凭空回补（等于无锚增发）；
  买方：付款 price + 承接 1500 成本 = 同一笔成本被扣两次。

真实账本必须「按事件记账、事后不因归属变更重算」，故：余额 = Σ 流水，
每笔业务事件以全局唯一 ref 幂等落账（INSERT OR IGNORE），且资金守恒：
  Σ 全体流水 == 累计发行 − 累计销毁（兑换只是「居民 → 国库」的内部转移）。

ref 命名规范（**新写入与存量回填共用同一套**，口径不一致会双计余额）：
    energy:{record_id}                        节点发行（+ 接收方）
    cert:{cert_id} / cert-treasury:{cert_id}  证书兑换（- 兑换人 / + 国库）
    badge:{badge_id} / badge-treasury:{id}    勋章兑换（同上）
    market:{listing_id}:pay / :recv           市场成交（- 买方 / + 卖方）
    burn:{burn_id}                            国库销毁（- 国库）

依赖约束：只依赖 db 与 learning.alliance_roles（单一权威口径），禁止 import
routers.eco —— routers/seed 两侧都从这里取数，避免循环导入与规范漂移。
"""
from __future__ import annotations

from typing import Any, Optional

from .db import get_conn, now
from .learning.alliance_roles import ROLES, TREASURY_WALLET, wallet_address
from .wallet_id import to_address


# ---------------------------------------------------------------------------
# 流水类型（amount 有符号：入账为正、出账为负）
# ---------------------------------------------------------------------------
FLOW_ISSUE = "issue"                    # 联盟节点发行（+）
FLOW_EXCHANGE = "exchange_out"          # 居民兑换资产支付（-）
FLOW_MARKET_IN = "market_in"            # 市场卖出收款（+）
FLOW_MARKET_OUT = "market_out"          # 市场购买付款（-）
FLOW_TREASURY_IN = "treasury_in"        # 国库回收兑换能量（+，只记国库账户）
FLOW_TREASURY_BURN = "treasury_burn"    # 国库销毁（-，只记国库账户）
FLOW_BACKFILL = "backfill"              # 创世/治理投放回填（管理员国库）

FLOW_LABELS = {
    FLOW_ISSUE: "联盟节点发行",
    FLOW_EXCHANGE: "兑换资产支付",
    FLOW_MARKET_IN: "市场卖出收款",
    FLOW_MARKET_OUT: "市场购买付款",
    FLOW_TREASURY_IN: "国库回收",
    FLOW_TREASURY_BURN: "国库销毁",
    FLOW_BACKFILL: "国库投放/回填",
}


def norm_wallet(wallet: str) -> str:
    """统一钱包标识 → **真实链上地址**（0x + 40 位十六进制）。

    能量流水是资产台账，一行一个地址口径即可；历史上这里只 lower()，于是
    `stu:0ae7783d-d59d-…`（带冒号连字符的内部别名）与真实地址两种写法共存，
    同一人余额被拆成两行、链上账与库内账对不上。现在写入侧统一归一，
    历史行由 scripts/normalize_asset_wallets.py 迁移；密钥库不可用时降级原值。
    """
    return to_address(wallet)


def ensure_flow(conn: Any, *, wallet: str, kind: str, amount: int, ref: str = "",
                note: str = "", role_key: str = "") -> bool:
    """写一笔能量流水；ref 非空时幂等（同 ref 重复写返回 False 且不长新行）。"""
    if not wallet or int(amount) == 0:
        return False
    cur = conn.execute(
        "INSERT OR IGNORE INTO eco_energy_flows(wallet,kind,amount,ref,note,role_key,created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (norm_wallet(wallet), kind, int(amount), ref or "", note or "", role_key or "", now()),
    )
    return cur.rowcount > 0


def record_exchange_cost(conn: Any, *, wallet: str, cost: int, kind_prefix: str,
                         obj_id: int, note: str = "") -> None:
    """兑换成本的账本双写：兑换人出账 + 国库入账（能量守恒，不凭空消失）。

    kind_prefix 取 "cert" | "badge"，与 ref 命名规范一一对应。
    """
    cost = int(cost or 0)
    if cost <= 0 or not obj_id:
        return
    ensure_flow(conn, wallet=wallet, kind=FLOW_EXCHANGE, amount=-cost,
                ref=f"{kind_prefix}:{obj_id}", note=note)
    ensure_flow(conn, wallet=TREASURY_WALLET, kind=FLOW_TREASURY_IN, amount=cost,
                ref=f"{kind_prefix}-treasury:{obj_id}", note=f"回收：{note or kind_prefix}")


def flow_balance(conn: Any, wallet: str) -> int:
    """某钱包的流水净额（可为负：历史脏数据不掩盖，由国库治理科目纠偏）。"""
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM eco_energy_flows WHERE lower(wallet)=?",
        (norm_wallet(wallet),),
    ).fetchone()
    return int(row[0] or 0)


def balance_of(wallet: str) -> int:
    """按钱包查账本净额（负数按 0 展示）。"""
    if not norm_wallet(wallet):
        return 0
    with get_conn() as conn:
        return max(0, flow_balance(conn, wallet))


def _table_exists(conn: Any, table: str) -> bool:
    return bool(conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone())


def backfill_energy_flows(conn: Any) -> int:
    """把存量业务数据一次性摊成流水（幂等，可反复执行；返回新增流水行数）。

    关键口径：证书/勋章的兑换成本记给 **exchanged_by（当初掏能量的人）**，
    而不是当前的 owner —— 老数据里资产可能已被市场转手，用 owner 就把 B1 又抄一遍。
    """
    added = 0
    if not _table_exists(conn, "eco_energy_flows"):
        return 0

    if _table_exists(conn, "eco_energy_records"):
        for r in conn.execute(
            "SELECT id, wallet, points, action, role_key FROM eco_energy_records"
        ).fetchall():
            added += int(ensure_flow(
                conn, wallet=r["wallet"], kind=FLOW_ISSUE, amount=int(r["points"] or 0),
                ref=f"energy:{r['id']}", note=r["action"] or "", role_key=r["role_key"] or ""))

    if _table_exists(conn, "eco_certificates"):
        for r in conn.execute(
            "SELECT id, cost_energy, owner, exchanged_by, species_name FROM eco_certificates"
        ).fetchall():
            cost = int(r["cost_energy"] or 0)
            if cost <= 0:
                continue
            payer = r["exchanged_by"] or r["owner"]
            added += int(ensure_flow(
                conn, wallet=payer, kind=FLOW_EXCHANGE, amount=-cost,
                ref=f"cert:{r['id']}", note=f"植树证书 · {r['species_name'] or ''}"))
            added += int(ensure_flow(
                conn, wallet=TREASURY_WALLET, kind=FLOW_TREASURY_IN, amount=cost,
                ref=f"cert-treasury:{r['id']}", note=f"回收：证书 #{r['id']}"))

    if _table_exists(conn, "eco_badges"):
        for r in conn.execute(
            "SELECT id, cost_energy, owner, exchanged_by, name FROM eco_badges"
        ).fetchall():
            cost = int(r["cost_energy"] or 0)
            if cost <= 0:
                continue
            payer = r["exchanged_by"] or r["owner"]
            added += int(ensure_flow(
                conn, wallet=payer, kind=FLOW_EXCHANGE, amount=-cost,
                ref=f"badge:{r['id']}", note=r["name"] or ""))
            added += int(ensure_flow(
                conn, wallet=TREASURY_WALLET, kind=FLOW_TREASURY_IN, amount=cost,
                ref=f"badge-treasury:{r['id']}", note=f"回收：{r['name'] or '勋章'} #{r['id']}"))

    if _table_exists(conn, "eco_market_listings"):
        for r in conn.execute(
            "SELECT id, seller, buyer, price_energy, asset_name FROM eco_market_listings "
            "WHERE status='sold' AND COALESCE(buyer,'')<>''"
        ).fetchall():
            price = int(r["price_energy"] or 0)
            if price <= 0:
                continue
            added += int(ensure_flow(
                conn, wallet=r["buyer"], kind=FLOW_MARKET_OUT, amount=-price,
                ref=f"market:{r['id']}:pay", note=f"购入 {r['asset_name'] or ''}"))
            added += int(ensure_flow(
                conn, wallet=r["seller"], kind=FLOW_MARKET_IN, amount=price,
                ref=f"market:{r['id']}:recv", note=f"售出 {r['asset_name'] or ''}"))

    if _table_exists(conn, "eco_energy_burns"):
        for r in conn.execute("SELECT id, amount, note FROM eco_energy_burns").fetchall():
            added += int(ensure_flow(
                conn, wallet=TREASURY_WALLET, kind=FLOW_TREASURY_BURN,
                amount=-int(r["amount"] or 0), ref=f"burn:{r['id']}",
                note=r["note"] or "国库销毁"))
    return added


def treasury_stats(conn: Any) -> dict:
    """能量国库与通胀审计指标（只读，口径全部来自流水表，不重算归属）。

    资金守恒：Σ 全体流水 == total_issued − total_burned == circulating + treasury_balance
    """
    def _sum(where: str, params: Optional[list] = None) -> int:
        return int(conn.execute(
            f"SELECT COALESCE(SUM(amount), 0) FROM eco_energy_flows WHERE {where}",
            params or [],
        ).fetchone()[0] or 0)

    minted = _sum("kind IN (?,?) AND amount > 0", [FLOW_ISSUE, FLOW_BACKFILL])
    recycled = _sum("kind=?", [FLOW_TREASURY_IN])
    burned = -_sum("kind=?", [FLOW_TREASURY_BURN])
    treasury = flow_balance(conn, TREASURY_WALLET)
    per_role = conn.execute(
        "SELECT role_key, COALESCE(SUM(amount),0) AS issued FROM eco_energy_flows "
        "WHERE kind=? AND amount > 0 GROUP BY role_key",
        (FLOW_ISSUE,),
    ).fetchall()
    issued_by_role = {r["role_key"]: int(r["issued"] or 0) for r in per_role}
    quotas: list = []
    for r in ROLES:
        if not r.get("energy_rule"):
            continue
        quota = int(r.get("energy_quota") or 0)
        used = int(issued_by_role.get(r["key"]) or 0)
        quotas.append({
            "role_key": r["key"], "role_name": r["name"], "icon": r["icon"],
            # wallet = 机构钱包真实地址，wallet_alias = 友好别名（仅展示）
            "wallet": wallet_address(r["key"]) or "",
            "wallet_alias": r.get("wallet") or "",
            "quota": quota, "used": used,
            "remaining": (quota - used) if quota > 0 else -1,   # -1 = 未设授信上限
            "used_ratio": round(used * 100.0 / quota, 1) if quota > 0 else None,
        })
    return {
        # 钱包字段统一真实地址（可核对 / 可转账），别名另存一列只作展示
        "treasury_wallet": wallet_address(TREASURY_WALLET) or TREASURY_WALLET,
        "treasury_wallet_alias": TREASURY_WALLET,
        # 国库在链上的真实地址（前端展示 / 跳转用；流水已按地址归一记账）
        "treasury_address": wallet_address(TREASURY_WALLET) or TREASURY_WALLET,
        "total_issued": minted,                # 累计发行（含国库投放）
        "total_recycled": recycled,            # 兑换回收进国库
        "total_burned": burned,                # 已真实销毁（退出流通）
        "treasury_balance": max(0, treasury),  # 国库余额（待投放 / 待销毁）
        "net_issuance": minted - burned,       # 净发行量（链上总供应口径）
        "circulating": minted - recycled,      # 居民侧在途流通量
        "pending_burn": max(0, recycled - burned),  # 已回收未销毁 = 潜在通胀敞口
        "burn_rate": round(burned * 100.0 / recycled, 1) if recycled else 0.0,
        "node_quotas": quotas,
    }
