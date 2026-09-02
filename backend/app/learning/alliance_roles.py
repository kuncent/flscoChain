"""统一联盟角色模块（权威定义）。

ROLES / ROLE_ALIAS 自 app/routers/eco.py 原样迁入（内容逐字段不变，
前端 EnergyProofForm.vue 依赖 energy_rule.proof_fields，严禁改动任何字段）。
本模块是联盟角色数据的单一权威来源：

- app/routers/eco.py      → from ..learning.alliance_roles import ROLES, ROLE_ALIAS
- app/learning/tutorial_steps.py → ROLE_ENERGY_RULES 由此派生（单一代码来源）

依赖约束：本模块只依赖底层（db），禁止 import chain / eco（避免循环导入）。
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, Request

from ..db import get_conn


# ===========================================================================
# 六个联盟链节点角色定义
# ===========================================================================
ROLES = [
    {"key": "admin",    "name": "管理员",   "icon": "🛡️", "color": "#4d8dff", "wallet": "0xadmin",
     "desc": "平台管理方，部署合约、管理树种、发放植树证书", "energy_rule": None,
     "can_issue_badge": False, "can_issue_voucher": False, "can_manage_trees": True},
    {"key": "metro",    "name": "地铁集团", "icon": "🚇", "color": "#00e6c3", "wallet": "0xmetro",
     "desc": "城市地铁运营方，乘坐地铁(≥10km)发放50点绿色能量",
     "energy_rule": {"action": "地铁通勤", "points": 50, "proof_field": "distance_km", "min": 10, "unit": "km",
                     "proof_no_field": "trip_no",   # 业务单号：地铁乘车号（同一张乘车记录不重复发放）
                     "proof_fields": [
                         {"key": "station_in",  "label": "进站口", "type": "text",   "required": True, "placeholder": "如：国贸站"},
                         {"key": "station_out", "label": "出站口", "type": "text",   "required": True, "placeholder": "如：西二旗站"},
                         {"key": "board_time",  "label": "进站时间", "type": "text", "required": True, "placeholder": "如 2026-08-25 08:05"},
                         {"key": "line",        "label": "线路",   "type": "text",   "required": False, "placeholder": "如：1号线"},
                         {"key": "distance_km", "label": "乘坐里程(km)", "type": "number", "required": True, "placeholder": "需 ≥ 10 km"},
                     ],
                     "proof_example": '{"line":"1号线","distance_km":12,"trip_no":"BJ202608070001"}'},
     "can_issue_badge": True, "can_issue_voucher": False, "can_manage_trees": False},
    {"key": "bus",      "name": "公交集团", "icon": "🚌", "color": "#ffcf4d", "wallet": "0xbus",
     "desc": "城市公交运营方，乘坐公交(≥5分钟)发放20点绿色能量",
     "energy_rule": {"action": "公交出行", "points": 20, "proof_field": "ride_minutes", "min": 5, "unit": "min",
                     "proof_no_field": "trip_no",   # 业务单号：公交乘车号
                     "proof_fields": [
                         {"key": "route",        "label": "公交线路", "type": "text",   "required": True, "placeholder": "如：86路"},
                         {"key": "board_time",   "label": "上车时间", "type": "text",   "required": True, "placeholder": "如 2026-08-25 08:20"},
                         {"key": "ride_minutes", "label": "乘车时长(分钟)", "type": "number", "required": True, "placeholder": "需 ≥ 5 min"},
                     ],
                     "proof_example": '{"route":"86路","ride_minutes":20,"trip_no":"BUS20260807001"}'},
     "can_issue_badge": True, "can_issue_voucher": False, "can_manage_trees": False},
    {"key": "bike",     "name": "共享单车", "icon": "🚲", "color": "#f5379b", "wallet": "0xbike",
     "desc": "共享单车运营方，骑行(≥2km)发放15点能量，可发放骑行券",
     "energy_rule": {"action": "共享单车骑行", "points": 15, "proof_field": "distance_km", "min": 2, "unit": "km",
                     "proof_no_field": "order_id",  # 业务单号：单车订单号
                     "proof_fields": [
                         {"key": "order_id",    "label": "骑行订单号", "type": "text",   "required": True, "placeholder": "如：BK2026080701234"},
                         {"key": "distance_km", "label": "骑行里程(km)", "type": "number", "required": True, "placeholder": "需 ≥ 2 km"},
                         {"key": "duration_min","label": "骑行时长(分钟)", "type": "number", "required": False, "placeholder": "选填，如 15"},
                     ],
                     "proof_example": '{"order_id":"BK2026080701234","distance_km":3.2,"duration_min":15}'},
     "can_issue_badge": True, "can_issue_voucher": True, "can_manage_trees": False},
    {"key": "takeout",  "name": "外卖平台", "icon": "📦", "color": "#ff7849", "wallet": "0xtakeout",
     "desc": "绿色外卖服务平台，选择「无需餐具」发放10点绿色能量",
     "energy_rule": {"action": "绿色外卖(无需餐具)", "points": 10, "proof_field": "no_cutlery", "min": 1, "unit": "flag",
                     "proof_no_field": "order_id",  # 业务单号：外卖订单号（同一订单不重复发）
                     "proof_fields": [
                         {"key": "order_id",   "label": "外卖订单号", "type": "text",   "required": True, "placeholder": "如：MT2026080700123"},
                         {"key": "merchant",   "label": "商家名称", "type": "text",     "required": False, "placeholder": "选填，如：轻食沙拉"},
                         {"key": "no_cutlery", "label": "已选择「无需餐具」", "type": "switch", "required": True, "placeholder": ""},
                     ],
                     "proof_example": '{"order_id":"MT2026080700123","no_cutlery":true,"platform_order":"ELM2026080701"}'},
     "can_issue_badge": True, "can_issue_voucher": False, "can_manage_trees": False},
    {"key": "recycling","name": "回收公司", "icon": "♻️", "color": "#52c41a", "wallet": "0xrecycle",
     "desc": "旧物回收公司，回收(≥1kg)发放100点绿色能量",
     "energy_rule": {"action": "可回收物回收", "points": 100, "proof_field": "weight_kg", "min": 1, "unit": "kg",
                     "proof_no_field": "order_no",  # 业务单号：回收单号（同一回收不重复发）
                     "proof_fields": [
                         {"key": "order_no",  "label": "回收单号", "type": "text",   "required": True, "placeholder": "如：RC20260807001"},
                         {"key": "category",  "label": "回收物分类", "type": "text", "required": True, "placeholder": "如：塑料瓶 / 纸箱"},
                         {"key": "weight_kg", "label": "回收重量(kg)", "type": "number", "required": True, "placeholder": "需 ≥ 1 kg"},
                     ],
                     "proof_example": '{"order_id":"RC20260807001","weight_kg":2.5,"category":"塑料瓶"}'},
     "can_issue_badge": True, "can_issue_voucher": False, "can_manage_trees": False},
]

# 角色别名兼容：前端若传 'delivery' 旧 key，自动映射到 'takeout'
ROLE_ALIAS = {
    "delivery":  "takeout",     # 旧 key（可能前端/脚本残留） → 新 key takeout
    "recycle":   "recycling",   # 兼容缩写：recycle 是 wallet 别名，ROLES.key 是 recycling
}

# 权限位清单（权限矩阵的列；has_energy_rule 为派生位，不计入此处）
PERMISSION_FLAGS = ("can_issue_badge", "can_issue_voucher", "can_manage_trees")


# ===========================================================================
# 角色与权限矩阵查询助手
# ===========================================================================
def find_role(role_key: str) -> Optional[dict]:
    """根据 role_key 查找角色定义，自动识别别名（如 'delivery' → 'takeout'）。"""
    if not role_key:
        return None
    k = role_key.strip().lower()
    k = ROLE_ALIAS.get(k, k)
    for r in ROLES:
        if r["key"] == k:
            return r
    return None


def get_role_permissions(role) -> Optional[dict]:
    """权限矩阵查询：传入角色定义 dict 或 role_key（支持别名），返回权限位字典。

    返回 {"key","name","can_issue_badge","can_issue_voucher","can_manage_trees",
          "has_energy_rule"}；角色不存在返回 None。
    """
    r = role if isinstance(role, dict) else find_role(role)
    if not r:
        return None
    return {
        "key": r.get("key", ""),
        "name": r.get("name", ""),
        "can_issue_badge": bool(r.get("can_issue_badge")),
        "can_issue_voucher": bool(r.get("can_issue_voucher")),
        "can_manage_trees": bool(r.get("can_manage_trees")),
        "has_energy_rule": bool(r.get("energy_rule")),
    }


def role_permission_matrix() -> list:
    """返回全部联盟角色的权限矩阵（按 ROLES 固定顺序的只读快照）。"""
    return [get_role_permissions(r) for r in ROLES]


def has_permission(role: dict, flag: str) -> bool:
    """判断角色是否拥有指定权限位（未知权限位一律 False）。"""
    if flag not in PERMISSION_FLAGS:
        return False
    return bool((role or {}).get(flag))


def get_selected_role(wallet: str) -> Optional[dict]:
    """查询钱包当前选择的联盟角色（eco_role_selections），未选择返回 None。"""
    if not wallet:
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT role_key FROM eco_role_selections WHERE lower(wallet)=lower(?)",
            (wallet,),
        ).fetchone()
    if not row:
        return None
    return find_role(row["role_key"])


# ===========================================================================
# FastAPI 依赖工厂
# ===========================================================================
def require_alliance_role(*flags: str):
    """依赖工厂：校验「当前请求角色」具备全部指定联盟权限位，不满足抛 403。

    - flags 取值：can_issue_badge / can_issue_voucher / can_manage_trees
    - 「当前请求角色」的解析口径：请求中 wallet（query 参数优先，其次 JSON body 的
      wallet 字段）在 eco_role_selections 中选中的联盟角色
    - 未选择角色 / 角色缺少任一权限位 → HTTPException(403, ...)，
      错误信息风格与既有 eco 端点的 403 文案一致
    - 依赖返回值为当前角色定义 dict，可作为端点参数直接使用

    用法：
        @router.post("/xxx")
        def xxx(role: dict = Depends(require_alliance_role("can_issue_badge"))):
            ...
    """

    async def _dependency(request: Request) -> dict:
        wallet = request.query_params.get("wallet") or ""
        if not wallet:
            try:
                body = await request.json()
                if isinstance(body, dict):
                    wallet = str(body.get("wallet") or "")
            except Exception:
                pass  # 无 body / 非 JSON（如 GET）时静默跳过
        sel = get_selected_role(wallet)
        if not sel:
            raise HTTPException(
                403,
                "操作者未选择联盟角色：请先在「绿色低碳联盟链」页面选择角色后再操作",
            )
        missing = [f for f in flags if not has_permission(sel, f)]
        if missing:
            raise HTTPException(
                403,
                f"角色【{sel['name']}】不具备所需联盟权限位：{', '.join(missing)}",
            )
        return sel

    return _dependency


# ===========================================================================
# 业务上下文权限助手（自 eco.py 各端点散落的权限 if-else 抽取，供多处复用；
# 403 文案与原实现逐字一致，校验结果语义完全不变）
# ===========================================================================
def ensure_issuer_role(role: dict, sel: Optional[dict]) -> None:
    """发放能量前的操作者角色一致性校验（原 eco.issue_energy 权限闭环）。

    - sel 为 None：操作者未选择联盟角色 → 403
    - sel.key != role.key：当前选中角色与本次发放角色不一致 → 403
    """
    if not sel:
        raise HTTPException(
            403,
            f"操作者未选择联盟角色：请先在「绿色低碳联盟链」页面切换到【{role['name']}】后再发放能量",
        )
    if sel["key"] != role["key"]:
        raise HTTPException(
            403,
            f"操作者当前选择的是【{sel['name']}】，与本次发放角色【{role['name']}】不一致。"
            f"请先在「绿色低碳联盟链」切换为对应联盟角色",
        )


def ensure_minter_role(role: dict, sel: Optional[dict]) -> None:
    """铸造发放前的操作者角色一致性校验（原 eco.mint_badge 权限校验）。"""
    if not sel or sel["key"] != role["key"]:
        raise HTTPException(
            403,
            f"铸造权限不足：操作者当前角色为「{sel['name'] if sel else '未选择'}」，"
            f"与声明的「{role['name']}」不一致。请先在「绿色低碳联盟链」切换对应联盟角色",
        )


def ensure_admin_for_trees(selected_role_key: Optional[str]) -> None:
    """树种管理权限校验：仅管理员（admin）可新增树种（原 eco.add_tree 校验）。"""
    if not selected_role_key or selected_role_key != "admin":
        raise HTTPException(403, "仅管理员可新增树种")


def ensure_bike_for_voucher(role_key: str, action: str) -> None:
    """骑行券（voucher）仅共享单车公司（bike）可操作（原 eco 两处校验）。

    - action="add"  → 新增骑行券类型（eco.add_badge_type 文案）
    - action="mint" → 铸造发放骑行券（eco.mint_badge 文案）
    """
    if action == "add":
        if role_key != "bike":
            raise HTTPException(403, "骑行券仅共享单车公司（bike）可新增，请切换到「共享单车」角色")
        return
    if role_key != "bike":
        raise HTTPException(403, "骑行券仅共享单车公司（bike）可发放")


def ensure_asset_owner(owner: str, operator: str) -> None:
    """资产归属校验：只有资产所有者本人可操作（原 eco.market_list 校验）。"""
    if owner != operator:
        raise HTTPException(403, "只能挂自己的资产")
