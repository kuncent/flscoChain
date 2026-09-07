"""联盟角色「体验多样性」统一统计（报告 E 项 / 微任务 eco_t2 / 学习路径共用口径）。

背景：这个计数曾在多处各写一遍 SQL（report.py 的 `_load_eco_brief`、missions.py 的
`eco_t2`），口径漂移在真机上直接表现为「报告 E 项 6/6 满分，任务 T2 却 5/6 未达标」——
同一学生同一批行为被两套查询判成不同结果，学生看不懂、教师也无法申诉。
本模块是唯一实现：**任何地方要问"这名学生体验过几种联盟角色"都必须调用它**。

口径（四步，缺一不可）：
  1. 主源 `learning_events.event_type=eco_role_switch` 的 target。
     不能只读 `eco_role_selections`：该表有 UNIQUE(wallet)，只存「当前选中的那一个」
     角色（切回普通用户还会 DELETE 该行），COUNT(DISTINCT role_key) 上限恒为 1。
  2. 认人双口径：`learning_events.wallet` 存的是**当时操作的钱包**（学生点角色卡即切到
     机构钱包，全班共用同一个值），只按本人钱包筛会漏掉「以节点身份体验」那一段；
     故取 `wallet ∈ 候选集` **OR** `user_id = 本人` 的并集。
  3. 补集 `eco_role_selections.role_key`：埋点上线前的存量数据只有当前选择可读。
  4. 全部经 `normalize_role_key` 归一（delivery→takeout、recycle→recycling），
     再与 `ROLES` 权威角色集取交集，脏埋点 / 「resident」等未知 key 不得虚增计数。
"""
from __future__ import annotations

import sqlite3
from typing import Any, Iterable

from ..db import scope_where
from ..security import lower_wallet_in
from .alliance_roles import ROLES, normalize_role_key
from .events import EventType

# 权威角色 key 集合（admin/metro/bus/bike/takeout/recycling）
KNOWN_ROLE_KEYS = frozenset(str(r["key"]) for r in ROLES)


def experienced_roles(
    conn: sqlite3.Connection,
    candidates: Iterable[str] | None,
    user_id: str | None = None,
    *,
    apply_scope: bool = False,
) -> dict[str, Any]:
    """统计该学生体验过的联盟角色（唯一口径实现）。

    Args:
      conn:        已打开的数据库连接（调用方持有，本函数不开新连接）
      candidates:  钱包候选集（真实地址 / user_id / `stu:` 别名 / 学号），空则全局聚合
      user_id:     登录身份，用于 `learning_events.user_id` 第二认人口径
      apply_scope: 是否叠加多租户 scope_where（报告按学生过滤时传 True；
                   教师/管理员全局视角传 False）

    Returns:
      {"keys": set[str], "count": int, "switches": int, "wallets": int}
        keys     —— 归一并与权威角色集求交后的角色 key 集合
        count    —— len(keys)，即「体验过几种角色」（E 项 / T2 直接用它）
        switches —— 真实切换动作次数（含切回普通用户），供报告展示行为强度
        wallets  —— 涉及的不同操作钱包数
    """
    cands = [str(c) for c in (candidates or []) if str(c or "").strip()]
    in_h, in_p = lower_wallet_in(cands)
    filtered = bool(in_p)

    parts: list[str] = ["event_type=?", "COALESCE(target, '') <> ''"]
    params: list[Any] = [EventType.ECO_ROLE_SWITCH]

    owner_parts: list[str] = []
    if filtered:
        owner_parts.append(f"lower(wallet) IN ({in_h})")
    # 全局聚合（candidates 为空）时不加任何认人条件，保持“全链口径”不变
    by_uid = bool(user_id) and filtered and _has_user_id_col(conn)
    if by_uid:
        owner_parts.append("lower(COALESCE(user_id, '')) = ?")
    if owner_parts:
        parts.append("(" + " OR ".join(owner_parts) + ")")
        if filtered:
            params += list(in_p)
        if by_uid:
            params.append(str(user_id).lower())

    if apply_scope and user_id:
        sc_sql, sc_params = scope_where("learning_events", user_id=str(user_id))
        if sc_sql:
            parts.append(sc_sql)
            params += list(sc_params)

    ev_rows = conn.execute(
        "SELECT target, wallet FROM learning_events WHERE " + " AND ".join(parts),
        params,
    ).fetchall()

    keys = {normalize_role_key(str(r["target"] or "")) for r in ev_rows}
    switches = len(ev_rows)
    wallets = len({str(r["wallet"] or "").lower() for r in ev_rows if r["wallet"]})

    # 当前选择表补集（埋点上线前的存量数据）
    sel_params: list[Any] = []
    sel_where = ""
    if filtered:
        sel_where = f" WHERE lower(wallet) IN ({in_h})"
        sel_params = list(in_p)
    for row in conn.execute(
        f"SELECT DISTINCT role_key FROM eco_role_selections{sel_where}", sel_params
    ).fetchall():
        keys.add(normalize_role_key(str(row["role_key"] or "")))

    keys &= KNOWN_ROLE_KEYS
    return {"keys": keys, "count": len(keys), "switches": switches, "wallets": wallets}


def _has_user_id_col(conn: sqlite3.Connection) -> bool:
    """learning_events 是否存在 user_id 列（旧库升级前可能还没有）。"""
    try:
        cols = conn.execute("PRAGMA table_info(learning_events)").fetchall()
    except sqlite3.Error:
        return False
    return any(str(c[1]).lower() == "user_id" for c in cols)
