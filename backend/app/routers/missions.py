"""联盟运营微任务服务端自动验收 API。

任务清单见 app/missions_data.py（文案平移自前端 Dashboard.vue L5_MICRO_TASKS）。
验收原则：不依赖前端打卡，直接按钱包查询平台真实业务数据自动判定；
统计口径与 app/routers/grades.py 的实训成绩计算引擎保持一致
（learning_events / deployed_contracts / eco_energy_records 等表）。

接口：
  GET /api/missions/curriculum?wallet=   任务清单 + 每项服务端自动验收状态
"""
from __future__ import annotations

import logging
import sqlite3

from fastapi import APIRouter, Depends, Query

from ..db import get_conn
from ..learning.events import EventType
from ..missions_data import MISSIONS
from ..security import (
    assert_actor_wallet,
    get_current_user,
    lower_wallet_in,
    resolve_wallet_candidates,
)

router = APIRouter(prefix="/api/missions", tags=["missions"])

# T1 验收口径：3 份系统合约（deployed_contracts.name，统一小写比对）
SYSTEM_CONTRACTS = ("greenenergy", "plantcertificate", "ecobadge")
# T3~T7 验收口径：5 个能量发放业务角色（管理员 admin 不发放业务能量）。
# recycling 为 eco.py ROLES 的正式 role_key（0xrecycle 只是钱包地址别名）；
# 历史埋点可能存旧键 recycle/delivery，统计时用 _ROLE_NORM_SQL 归一，
# 避免虚增 distinct 计数或漏计旧数据。
ECO_ISSUE_ROLES = ("metro", "bus", "bike", "takeout", "recycling")
# 历史角色别名归一（与 eco.py ROLE_ALIAS / achievements.py 口径一致）
_ROLE_NORM_SQL = (
    "CASE WHEN lower(role_key)='delivery' THEN 'takeout' "
    "WHEN lower(role_key)='recycle' THEN 'recycling' ELSE lower(role_key) END"
)
# T4~T7 角色发放多样性阈值（distinct role_key 数，对应报告 F 项分档）
ROLE_DIVERSITY_NEED = {"eco_t4": 2, "eco_t5": 3, "eco_t6": 4, "eco_t7": 5}
# T4~T7 同时要求对应场景角色至少发放过一次（与任务文案「切到 XX 角色」对应）
ROLE_SCENE_OF = {"eco_t4": "bus", "eco_t5": "bike", "eco_t6": "takeout", "eco_t7": "recycling"}


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    """健壮单值查询：表 / 列不存在或空数据一律返回 0，不抛错（空态兜底）。"""
    try:
        row = conn.execute(sql, params).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except sqlite3.Error:
        return 0


def _issue_stats(
    conn: sqlite3.Connection, h: str, lc: list[str], role: str | None = None
) -> tuple[int, int]:
    """能量发放统计（eco_energy_records，候选集 + lower 口径仿 grades.py）。

    role_key 做别名归一（delivery→takeout、recycle→recycling），
    避免历史别名记录漏计或虚增 distinct 计数。
    返回 (指定角色发放次数（role=None 时与 distinct 同值）, 不同角色种数)。
    """
    holders = ",".join("?" * len(ECO_ISSUE_ROLES))
    distinct = _scalar(
        conn,
        f"SELECT COUNT(DISTINCT {_ROLE_NORM_SQL}) FROM eco_energy_records "
        f"WHERE lower(wallet) IN ({h}) AND {_ROLE_NORM_SQL} IN ({holders})",
        (*lc, *ECO_ISSUE_ROLES),
    )
    if role is None:
        return distinct, distinct
    n = _scalar(
        conn,
        f"SELECT COUNT(*) FROM eco_energy_records "
        f"WHERE lower(wallet) IN ({h}) AND {_ROLE_NORM_SQL}=?",
        (*lc, role),
    )
    return n, distinct


def _verify_task(conn: sqlite3.Connection, key: str, wallet: str, h: str, lc: list[str]) -> dict:
    """按任务 key 查询平台真实业务数据，返回 {verified: bool, progress: str}。

    所有按钱包的查询统一走候选集（h=占位符片段，lc=小写候选参数），
    兼容写路径演示钱包 0xlearner / 埋点 JWT wallet（userId）双轨口径。
    """
    if key == "eco_t1":
        holders = ",".join("?" * len(SYSTEM_CONTRACTS))
        n = _scalar(
            conn,
            "SELECT COUNT(DISTINCT lower(name)) FROM deployed_contracts "
            f"WHERE lower(name) IN ({holders})",
            SYSTEM_CONTRACTS,
        )
        return {"verified": n >= len(SYSTEM_CONTRACTS), "progress": f"{n}/3 份系统合约已部署激活"}
    if key == "eco_t2":
        # COUNT(DISTINCT target) 做别名归一（delivery→takeout、recycle→recycling），
        # 避免历史别名虚增已体验角色计数
        n = _scalar(
            conn,
            "SELECT COUNT(DISTINCT CASE WHEN lower(target) IN ('delivery','takeout') THEN 'takeout' "
            "WHEN lower(target) IN ('recycle','recycling') THEN 'recycling' "
            "ELSE lower(target) END) FROM learning_events "
            f"WHERE event_type='{EventType.ECO_ROLE_SWITCH}' AND lower(wallet) IN ({h})",
            lc,
        )
        return {"verified": n >= 6, "progress": f"已切换体验 {n}/6 个联盟角色"}
    if key == "eco_t3":
        n, _d = _issue_stats(conn, h, lc, "metro")
        return {"verified": n >= 1, "progress": f"地铁角色已向本钱包发放 {n} 次能量"}
    if key in ROLE_DIVERSITY_NEED:
        need = ROLE_DIVERSITY_NEED[key]
        scene = ROLE_SCENE_OF[key]
        n, distinct = _issue_stats(conn, h, lc, scene)
        ok = n >= 1 and distinct >= need
        return {"verified": ok, "progress": f"{scene} 已发放 {n} 次 · 角色多样性 {distinct}/{need} 种"}
    if key == "eco_t8":
        n = _scalar(
            conn,
            f"SELECT COUNT(DISTINCT species_id) FROM eco_certificates WHERE lower(owner) IN ({h})",
            lc,
        )
        return {"verified": n >= 2, "progress": f"已兑换 {n} 种树种的植树证书（需 ≥2 种）"}
    if key == "eco_t9":
        n = _scalar(
            conn,
            f"SELECT COUNT(DISTINCT badge_type) FROM eco_badges WHERE lower(owner) IN ({h})",
            lc,
        )
        return {"verified": n >= 2, "progress": f"已兑换 {n}/2 类绿色资产（勋章 / 骑行券）"}
    if key == "eco_t10":
        # 写入侧 report_view 埋点钱包是 JWT wallet（userId），读参数可能是
        # currentWallet（0xlearner）：候选集覆盖两种口径
        n = _scalar(
            conn,
            f"SELECT COUNT(*) FROM learning_events "
            f"WHERE event_type='{EventType.REPORT_VIEW}' AND lower(wallet) IN ({h})",
            lc,
        )
        return {"verified": n >= 1, "progress": f"已生成 / 查看实训报告 {n} 次（需 ≥1 次）"}
    return {"verified": False, "progress": "暂无自动验收口径"}


@router.get("/curriculum")
def missions_curriculum(
    wallet: str = Query("", description="学生链上钱包地址（缺省取当前登录身份钱包）"),
    user: dict = Depends(get_current_user),
):
    """联盟运营 10 微任务清单 + 每项服务端自动验收状态。

    鉴权风格与相邻路由一致：JWT 验签（get_current_user）+ assert_actor_wallet
    （学生仅能查询本人 / 内置联盟角色钱包，教师 / 管理员不受限）。

    每项 verify 字段：
      verified  bool   服务端按平台真实数据自动验收是否通过
      progress  str    验收进度（数字 / 描述）
      source    str    'verified'   = 服务端验收通过（前端直接算完成）
                       'unverified' = 服务端数据未达标（前端可叠加本地打卡 → 'self-claimed'）
      evidence  str    关联验收数据源描述
    """
    w = assert_actor_wallet(user, wallet, "wallet") or "0xlearner"
    items: list[dict] = []
    verified_count = 0
    with get_conn() as conn:
        # 候选集：读参数可能是演示钱包（前端 currentWallet），而 report_view 等埋点
        # 写入用 JWT wallet（userId）——传入登录 user_id 把两种口径并入候选
        cands = resolve_wallet_candidates(
            conn, w, user.get("wallet") or user.get("user_id") or ""
        )
        h, lc = lower_wallet_in(cands)
        for m in MISSIONS:
            v = _verify_task(conn, m["key"], w, h, lc)
            if v["verified"]:
                verified_count += 1
            items.append({
                "key": m["key"],
                "phase": m["phase"],
                "title": m["title"],
                "desc": m["desc"],
                "label": m["label"],
                "hint": m["hint"],
                "to": m["to"],
                "verify": {
                    "source": "verified" if v["verified"] else "unverified",
                    "verified": v["verified"],
                    "progress": v["progress"],
                    "evidence": m["verify_desc"],
                },
            })
    if verified_count == 0:
        logging.warning(
            "missions: 钱包 %s（候选集 %s）10 项任务全部未达标——若该用户已有学习行为，"
            "可能是钱包口径错位或数据缺失，请人工核对",
            w, cands,
        )
    return {
        "wallet": w,
        "total": len(items),
        "verified_count": verified_count,
        "items": items,
    }
