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
from ..wallet_id import to_address


# ===========================================================================
# 六个联盟链节点角色定义
# ===========================================================================
# ===========================================================================
# 商业模型四维度（职能权威口径，前端业务项渲染与后端 403 拦截共用同一来源）
#
#   issue_energy    发行绿色能量（ERC20 mint 权）        —— 仅 5 个业务联盟节点
#   issue_asset     发行绿色资产（证书 / 勋章 / 骑行券）—— 按协议分治，见 ASSET_FORMS
#   obtain_energy   获取绿色能量（作为接收方）          —— 仅普通用户（居民）
#   exchange_asset  消耗能量兑换绿色资产                —— 仅普通用户（居民）
#   trade_market    二级流通（挂牌 / 购买）             —— 仅普通用户（居民）
#   govern          治理（合约部署 / 目录额度 / 国库销毁）—— 仅管理员
#
# 关键约束：**发行方与使用方必须互斥**。联盟节点是能量与资产的发行方，一旦以
# 节点身份出现就不该同时具备「兑资产 / 进市场」的能力（否则发行方自己凭自己的
# 组织钱包兑自己发的券 = 左手发右手收）；管理员不发行能量，但承担国库与销毁。
# ===========================================================================
DIM_ISSUE_ENERGY = "issue_energy"
DIM_ISSUE_ASSET = "issue_asset"
DIM_OBTAIN_ENERGY = "obtain_energy"
DIM_EXCHANGE_ASSET = "exchange_asset"
DIM_TRADE_MARKET = "trade_market"
DIM_GOVERN = "govern"
DIMENSIONS = (DIM_ISSUE_ENERGY, DIM_ISSUE_ASSET, DIM_OBTAIN_ENERGY,
              DIM_EXCHANGE_ASSET, DIM_TRADE_MARKET, DIM_GOVERN)

# 绿色资产形态（协议决定形态与「发行数量」语义）
ASSET_FORMS = {
    "energy": {
        "asset": "energy", "standard": "ERC20", "name": "绿色能量",
        "form": "同质化代币 · 可分割 · 单位为点",
        "supply_model": "node_quota",          # 发行数量 = 各节点授信配额之和
        "supply_note": "各联盟节点在 energy_quota 额度内按行为核算发行；"
                       "回收进国库后由管理员销毁，净发行量可缩",
        "issuers": ["metro", "bus", "bike", "takeout", "recycling"],
    },
    "certificate": {
        "asset": "certificate", "standard": "ERC721", "name": "植树证书",
        "form": "非同质化 · 每份唯一 · 不可分割",
        "supply_model": "project_quota",       # 发行数量 = 树种项目额度（eco_tree_species.supply）
        "supply_note": "一证一树：每个树种有发行额度，额满即售罄，不允许超发",
        "issuers": ["admin"],
    },
    "badge": {
        "asset": "badge", "standard": "ERC1155", "name": "生态勋章",
        "form": "半同质化 · 同类多份 · 可批量转账",
        "supply_model": "type_quota",          # 发行数量 = 类型 supply / 已铸 minted
        "supply_note": "每个勋章类型有发行上限，同类型可持有 N 份；"
                       "上限由该类型的发行方节点维护，只可上调不可下调",
        "issuers": ["metro", "bus", "bike", "takeout", "recycling"],
    },
    "voucher": {
        "asset": "voucher", "standard": "ERC1155", "name": "骑行券",
        "form": "半同质化 · 权益凭证 · 可批量核销",
        "supply_model": "type_quota",
        "supply_note": "全平台仅维护一份骑行券（token_id=2），"
                       "发行方固定为共享单车节点（兑付义务人）",
        "issuers": ["bike"],
    },
}

# 角色定义：
#   energy_rule      —— 能量发行核算规则（points=达成门槛的基础点数，
#                       bonus_per_unit=超出门槛后每 1 计量单位追加，bonus_cap=单次封顶）
#   energy_quota     —— 该节点全生命周期累计发行授信（0=不限）
#   issues_assets    —— 该角色可发行的绿色资产（与 ASSET_FORMS[asset].issuers 双向一致）
ROLES = [
    {"key": "admin",    "name": "管理员",   "icon": "🛡️", "color": "#4d8dff", "wallet": "0xadmin",
     "desc": "联盟治理方：部署合约、签发植树证书（ERC721）、管理树种目录与发行额度、"
             "运营能量国库与销毁；不发行能量，也不参与居民兑换与市场流通",
     "energy_rule": None, "energy_quota": 0, "issues_assets": ["certificate"],
     "can_issue_badge": False, "can_issue_voucher": False, "can_manage_trees": True},
    {"key": "metro",    "name": "地铁集团", "icon": "🚇", "color": "#00e6c3", "wallet": "0xmetro",
     "desc": "城市地铁运营方 · 能量发行节点：乘坐地铁(≥10km)基础 50 点，"
             "每超 1km 追加 2 点，单次封顶 150 点",
     "energy_rule": {"action": "地铁通勤", "points": 50, "proof_field": "distance_km", "min": 10, "unit": "km",
                     "bonus_per_unit": 2, "bonus_cap": 150,
                     "proof_no_field": "trip_no",   # 业务单号：地铁乘车号（同一张乘车记录不重复发放）
                     "proof_fields": [
                         {"key": "station_in",  "label": "进站口", "type": "text",   "required": True, "placeholder": "如：国贸站"},
                         {"key": "station_out", "label": "出站口", "type": "text",   "required": True, "placeholder": "如：西二旗站"},
                         {"key": "board_time",  "label": "进站时间", "type": "text", "required": True, "placeholder": "如 2026-08-25 08:05"},
                         {"key": "line",        "label": "线路",   "type": "text",   "required": False, "placeholder": "如：1号线"},
                         {"key": "distance_km", "label": "乘坐里程(km)", "type": "number", "required": True, "placeholder": "需 ≥ 10 km"},
                     ],
                     "proof_example": '{"line":"1号线","distance_km":12,"trip_no":"BJ202608070001"}'},
     "energy_quota": 5000, "issues_assets": ["badge"],
     "can_issue_badge": True, "can_issue_voucher": False, "can_manage_trees": False},
    {"key": "bus",      "name": "公交集团", "icon": "🚌", "color": "#ffcf4d", "wallet": "0xbus",
     "desc": "城市公交运营方 · 能量发行节点：乘坐公交(≥5分钟)基础 20 点，"
             "每超 1 分钟追加 1 点，单次封顶 60 点",
     "energy_rule": {"action": "公交出行", "points": 20, "proof_field": "ride_minutes", "min": 5, "unit": "min",
                     "bonus_per_unit": 1, "bonus_cap": 60,
                     "proof_no_field": "trip_no",   # 业务单号：公交乘车号
                     "proof_fields": [
                         {"key": "route",        "label": "公交线路", "type": "text",   "required": True, "placeholder": "如：86路"},
                         {"key": "board_time",   "label": "上车时间", "type": "text",   "required": True, "placeholder": "如 2026-08-25 08:20"},
                         {"key": "ride_minutes", "label": "乘车时长(分钟)", "type": "number", "required": True, "placeholder": "需 ≥ 5 min"},
                     ],
                     "proof_example": '{"route":"86路","ride_minutes":20,"trip_no":"BUS20260807001"}'},
     "energy_quota": 5000, "issues_assets": ["badge"],
     "can_issue_badge": True, "can_issue_voucher": False, "can_manage_trees": False},
    {"key": "bike",     "name": "共享单车", "icon": "🚲", "color": "#f5379b", "wallet": "0xbike",
     "desc": "共享单车运营方 · 能量发行节点兼骑行券唯一发行方：骑行(≥2km)基础 15 点，"
             "每超 1km 追加 3 点，单次封顶 60 点；骑行券的兑付义务人",
     "energy_rule": {"action": "共享单车骑行", "points": 15, "proof_field": "distance_km", "min": 2, "unit": "km",
                     "bonus_per_unit": 3, "bonus_cap": 60,
                     "proof_no_field": "order_id",  # 业务单号：单车订单号
                     "proof_fields": [
                         {"key": "order_id",    "label": "骑行订单号", "type": "text",   "required": True, "placeholder": "如：BK2026080701234"},
                         {"key": "distance_km", "label": "骑行里程(km)", "type": "number", "required": True, "placeholder": "需 ≥ 2 km"},
                         {"key": "duration_min","label": "骑行时长(分钟)", "type": "number", "required": False, "placeholder": "选填，如 15"},
                     ],
                     "proof_example": '{"order_id":"BK2026080701234","distance_km":3.2,"duration_min":15}'},
     "energy_quota": 5000, "issues_assets": ["badge", "voucher"],
     "can_issue_badge": True, "can_issue_voucher": True, "can_manage_trees": False},
    {"key": "takeout",  "name": "外卖平台", "icon": "📦", "color": "#ff7849", "wallet": "0xtakeout",
     "desc": "绿色外卖服务平台 · 能量发行节点：选择「无需餐具」每单固定 10 点"
             "（开关型行为，不按量加成），同一订单不重复发放",
     "energy_rule": {"action": "绿色外卖(无需餐具)", "points": 10, "proof_field": "no_cutlery", "min": 1, "unit": "flag",
                     "bonus_per_unit": 0, "bonus_cap": 10,
                     "proof_no_field": "order_id",  # 业务单号：外卖订单号（同一订单不重复发）
                     "proof_fields": [
                         {"key": "order_id",   "label": "外卖订单号", "type": "text",   "required": True, "placeholder": "如：MT2026080700123"},
                         {"key": "merchant",   "label": "商家名称", "type": "text",     "required": False, "placeholder": "选填，如：轻食沙拉"},
                         {"key": "no_cutlery", "label": "已选择「无需餐具」", "type": "switch", "required": True, "placeholder": ""},
                     ],
                     "proof_example": '{"order_id":"MT2026080700123","no_cutlery":true,"platform_order":"ELM2026080701"}'},
     "energy_quota": 3000, "issues_assets": ["badge"],
     "can_issue_badge": True, "can_issue_voucher": False, "can_manage_trees": False},
    {"key": "recycling","name": "回收公司", "icon": "♻️", "color": "#52c41a", "wallet": "0xrecycle",
     "desc": "旧物回收公司 · 能量发行节点：回收(≥1kg)基础 100 点，"
             "每超 1kg 追加 20 点，单次封顶 500 点",
     "energy_rule": {"action": "可回收物回收", "points": 100, "proof_field": "weight_kg", "min": 1, "unit": "kg",
                     "bonus_per_unit": 20, "bonus_cap": 500,
                     "proof_no_field": "order_no",  # 业务单号：回收单号（同一回收不重复发）
                     "proof_fields": [
                         {"key": "order_no",  "label": "回收单号", "type": "text",   "required": True, "placeholder": "如：RC20260807001"},
                         {"key": "category",  "label": "回收物分类", "type": "text", "required": True, "placeholder": "如：塑料瓶 / 纸箱"},
                         {"key": "weight_kg", "label": "回收重量(kg)", "type": "number", "required": True, "placeholder": "需 ≥ 1 kg"},
                     ],
                     "proof_example": '{"order_id":"RC20260807001","weight_kg":2.5,"category":"塑料瓶"}'},
     "energy_quota": 8000, "issues_assets": ["badge"],
     "can_issue_badge": True, "can_issue_voucher": False, "can_manage_trees": False},
]

# 普通用户（低碳居民）—— 不是联盟节点，但是四维度里唯一的「能量获取方 +
# 资产兑换方 + 市场流通方」，故与节点同等纳入职能矩阵（key=resident）。
RESIDENT_PROFILE = {
    "key": "resident", "name": "普通用户", "icon": "👨‍🎓", "color": "#8fd694", "wallet": "",
    "desc": "低碳居民（学习者本人钱包）：通过 5 种低碳行为获取绿色能量，"
            "消耗能量兑换植树证书 / 勋章 / 骑行券，并可在绿色资产市场挂牌与购买",
    "energy_rule": None, "energy_quota": 0, "issues_assets": [],
    "can_issue_badge": False, "can_issue_voucher": False, "can_manage_trees": False,
}

# 角色别名兼容：前端若传 'delivery' 旧 key，自动映射到 'takeout'
ROLE_ALIAS = {
    "delivery":  "takeout",     # 旧 key（可能前端/脚本残留） → 新 key takeout
    "recycle":   "recycling",   # 兼容缩写：recycle 是 wallet 别名，ROLES.key 是 recycling
}

# 权限位清单（权限矩阵的列；has_energy_rule 为派生位，不计入此处）
PERMISSION_FLAGS = ("can_issue_badge", "can_issue_voucher", "can_manage_trees")

# ---------------------------------------------------------------------------
# 能力位（由角色定义**派生**，不是 ROLES 里的字面字段）
#
# 与 PERMISSION_FLAGS 的分工：
#   PERMISSION_FLAGS —— 历史字面权限位（ROLES dict 的 key，保留以兼容旧调用）；
#   CAP_*             —— 商业职能位，由 profile / energy_rule / issues_assets 派生，
#                        是后端 403 拦截与前端业务项渲染的**唯一判据**。
# 二者不同步的后果就是本次修掉的 bug：地铁节点能兑自己发的券、
# 管理员能新增却永远铸造不了勋章类型（死数据）。
# ---------------------------------------------------------------------------
CAP_ENERGY_ISSUE = "energy.issue"          # 发行绿色能量（ERC20 mint）
CAP_ENERGY_RECEIVE = "energy.receive"      # 作为能量接收方
CAP_ASSET_ISSUE_CERT = "asset.issue.certificate"
CAP_ASSET_ISSUE_BADGE = "asset.issue.badge"
CAP_ASSET_ISSUE_VOUCHER = "asset.issue.voucher"
CAP_ASSET_EXCHANGE = "asset.exchange"      # 消耗能量兑资产
CAP_MARKET_TRADE = "market.trade"          # 二级市挂牌 / 购买
CAP_CATALOG_MANAGE = "govern.catalog"      # 树种 / 资产类型目录与发行额度
CAP_TREASURY_MANAGE = "govern.treasury"    # 能量国库：回收台账 + 销毁
CAP_CONTRACT_DEPLOY = "govern.deploy"      # 联盟链合约部署
CAP_ALL = (
    CAP_ENERGY_ISSUE, CAP_ENERGY_RECEIVE,
    CAP_ASSET_ISSUE_CERT, CAP_ASSET_ISSUE_BADGE, CAP_ASSET_ISSUE_VOUCHER,
    CAP_ASSET_EXCHANGE, CAP_MARKET_TRADE,
    CAP_CATALOG_MANAGE, CAP_TREASURY_MANAGE, CAP_CONTRACT_DEPLOY,
)

# 能力位 → 「不具备时的人话解释」（前端展示「为何不给本角色看这项业务」）
CAP_DENY_REASON = {
    CAP_ENERGY_ISSUE: "只有具备行为核算规则的业务联盟节点才能发行能量",
    CAP_ENERGY_RECEIVE: "能量发行方 / 国库账户不作为接收方（避免发行方自铸）",
    CAP_ASSET_ISSUE_CERT: "植树证书（ERC721）由联盟碳汇方（管理员）统一签发",
    CAP_ASSET_ISSUE_BADGE: "本角色无勋章铸造职能",
    CAP_ASSET_ISSUE_VOUCHER: "骑行券是共享单车节点的专属权益凭证，仅该节点可发行",
    CAP_ASSET_EXCHANGE: "发行方不参与居民兑换（需体验兑换请先切回「普通用户」），否则等于左手发右手收",
    CAP_MARKET_TRADE: "联盟节点与国库账户不进入居民二级市场",
    CAP_CATALOG_MANAGE: "目录与发行额度由管理员治理",
    CAP_TREASURY_MANAGE: "能量国库与销毁仅管理员可操作",
    CAP_CONTRACT_DEPLOY: "联盟链合约由管理员（创世部署方）部署",
}

# 内置联盟组织钱包 → 角色 key（一一对应）
#   注意：这是「友好别名」口径（0xmetro 等），平台对外与资产台账统一用
#   真实链上地址，故所有钱包判定一律走 _wallet_index()（别名 + 地址双口径）。
ALLIANCE_WALLETS: dict = {
    str(r.get("wallet") or "").lower(): r["key"] for r in ROLES if r.get("wallet")
}
# 能量回收国库账户：只收纳回收与销毁，不作为居民参与兑换与市场交易
TREASURY_WALLET = "0xadmin"

# 别名 / 真实地址 → 角色 key 的双口径索引（首次使用时按密钥库建好并常驻）
_WALLET_INDEX: Optional[dict] = None


def _wallet_index() -> dict:
    """组织钱包标识索引 {别名或真实地址: role_key}（别名与地址都能反查角色）。"""
    global _WALLET_INDEX
    if _WALLET_INDEX is None:
        idx: dict = {}
        for alias, key in ALLIANCE_WALLETS.items():
            idx[alias] = key
            addr = to_address(alias)
            if addr:
                idx[addr] = key
        _WALLET_INDEX = idx
    return _WALLET_INDEX


def reset_wallet_index() -> None:
    """密钥库被重建 / 重置后清索引（演示数据重置脚本调用）。"""
    global _WALLET_INDEX
    _WALLET_INDEX = None


def wallet_address(role_key_or_alias: str) -> str:
    """角色 key / 组织钱包别名 → 该机构的真实链上地址（资产台账唯一归属口径）。"""
    k = str(role_key_or_alias or "").strip().lower()
    if not k:
        return ""
    role = find_role(k)
    alias = str((role or {}).get("wallet") or "") or k
    return to_address(alias)


def treasury_wallets() -> list:
    """国库账户的全部合法标识（别名 + 真实地址），供历史行兼容查询。"""
    addr = to_address(TREASURY_WALLET)
    return [TREASURY_WALLET, addr] if addr and addr != TREASURY_WALLET else [TREASURY_WALLET]


def role_of_alliance_wallet(wallet: str) -> Optional[str]:
    """内置组织钱包反查它唯一对应的联盟角色（非组织钱包返回 None）。

    别名（0xmetro）与真实地址（0x44bf…）都认：资产侧统一存真实地址后，
    如果只认别名，机构钱包会被误判成「个人钱包」而丢掉机构身份。
    """
    return _wallet_index().get(str(wallet or "").strip().lower())


def ensure_wallet_role_binding(wallet: str, role_key: str) -> None:
    """组织钱包与角色必须一致（修「0xbus 钱包选 takeout 角色」这类错位）。

    链上交易 FROM 取的是「角色定义里的组织钱包」，若允许任意钱包挂在任意
    角色下，任何学生都能以 0xmetro 名义签出一笔发行交易（真实商业里 = 机构私钥
    被盗用 / 无授权代发）。因此：**用组织钱包登录时只能扮演该钱包自己的角色**；
    个人钱包扮演联盟节点仍允许（实训角色扮演），但会另外记操作人留痕。
    """
    want = role_of_alliance_wallet(wallet)
    if want and role_key and want != role_key:
        role = find_role(role_key)
        raise HTTPException(
            400,
            f"钱包与角色不匹配：{wallet} 是「{find_role(want)['name']}」的组织钱包，"
            f"不能扮演「{(role or {}).get('name', role_key)}」。"
            f"机构业务签章只能由本机构钱包发出；如需扮演其他节点，请切回本人钱包。",
        )


def role_profile(role: Optional[dict]) -> str:
    """角色属于哪个职能层：admin / node / resident（未选角色 = 居民）。"""
    if not role:
        return "resident"
    if role.get("can_manage_trees") or str(role.get("key") or "") == "admin":
        return "admin"
    if role.get("energy_rule") or role.get("issues_assets") or role.get("can_issue_badge"):
        return "node"
    return "resident"


def role_capabilities(role: Optional[dict]) -> set:
    """能力位集合（四维度到可执行动作的展开）。"""
    prof = role_profile(role)
    if prof == "resident":
        return {CAP_ENERGY_RECEIVE, CAP_ASSET_EXCHANGE, CAP_MARKET_TRADE}
    caps: set = set()
    if role.get("energy_rule"):
        caps.add(CAP_ENERGY_ISSUE)
    issued = [str(a) for a in (role.get("issues_assets") or [])]
    if "certificate" in issued:
        caps.add(CAP_ASSET_ISSUE_CERT)
    if "badge" in issued:
        caps.add(CAP_ASSET_ISSUE_BADGE)
    if "voucher" in issued:
        caps.add(CAP_ASSET_ISSUE_VOUCHER)
    if prof == "admin":
        caps |= {CAP_CATALOG_MANAGE, CAP_TREASURY_MANAGE, CAP_CONTRACT_DEPLOY}
    return caps


def has_capability(role: Optional[dict], cap: str) -> bool:
    return cap in role_capabilities(role)


def ensure_capability(role: Optional[dict], cap: str, role_for_name: Optional[dict] = None) -> None:
    """能力不足 → 403（文案带上「当前身份」与「应该怎么切」，可自助恢复）。"""
    if cap in role_capabilities(role):
        return
    cur = (role or RESIDENT_PROFILE).get("name") or "未选择角色"
    ref = role_for_name or role or RESIDENT_PROFILE
    raise HTTPException(
        403,
        f"当前身份【{cur}】不具备该业务的职能权限（{cap}）："
        f"{CAP_DENY_REASON.get(cap, '角色职能不包含此项')}。"
        f"请在「选择你的角色」切到具备该职能的身份后重试",
    )


def dimension_view(role: Optional[dict]) -> dict:
    """按四维度输出该身份的职能明细（工作台与职能矩阵共用，前端只渲染不判定）。"""
    caps = role_capabilities(role)
    rule = (role or {}).get("energy_rule") or None
    assets = []
    for a in (role or {}).get("issues_assets") or []:
        form = ASSET_FORMS.get(a)
        if form:
            assets.append(dict(form))
    return {
        "profile": role_profile(role),
        "issue_energy": {
            "allowed": CAP_ENERGY_ISSUE in caps,
            "rule": rule,
            "quota": int((role or {}).get("energy_quota") or 0),
            "note": (f"{rule['action']}：基础 {rule['points']} 点（{rule.get('proof_field','')}"
                     f" ≥ {rule.get('min','?')} {rule.get('unit','')}），"
                     + (f"每超 1 {rule.get('unit','')} 追加 {rule.get('bonus_per_unit', 0)} 点，"
                        f"单次封顶 {rule.get('bonus_cap', rule['points'])} 点"
                        if int(rule.get("bonus_per_unit") or 0) > 0 else "每行为固定点数")
                     + f"；本节点累计发行授信 {int((role or {}).get('energy_quota') or 0) or '不限'} 点"
                     ) if rule else (CAP_DENY_REASON[CAP_ENERGY_ISSUE] if role else
                                     "能量由业务联盟节点发行，居民是接收方"),
        },
        "issue_asset": {
            "allowed": bool(assets),
            "forms": assets,
            "note": ("可发行：" + " / ".join(f"{a['name']}（{a['standard']}）" for a in assets))
                    if assets else "本身份不发行绿色资产",
        },
        "obtain_energy": {
            "allowed": CAP_ENERGY_RECEIVE in caps,
            "ways": [{"role": r["name"], "icon": r["icon"], "action": r["energy_rule"]["action"],
                      "base": r["energy_rule"]["points"],
                      "cap": r["energy_rule"].get("bonus_cap") or r["energy_rule"]["points"]}
                     for r in ROLES if r.get("energy_rule")],
            "note": "提交低碳行为凭证，由对应联盟节点审核以其组织钱包上链发放" if CAP_ENERGY_RECEIVE in caps
                    else "发行方 / 国库账户不作为能量接收方",
        },
        "exchange_asset": {
            "allowed": CAP_ASSET_EXCHANGE in caps,
            "note": "消耗本人能量兑换，能量转入国库，资产由发行方节点上链签发"
                    if CAP_ASSET_EXCHANGE in caps else CAP_DENY_REASON[CAP_ASSET_EXCHANGE],
        },
        "trade_market": {
            "allowed": CAP_MARKET_TRADE in caps,
            "note": "挂牌 / 购买均以绿色能量结算" if CAP_MARKET_TRADE in caps
                    else CAP_DENY_REASON[CAP_MARKET_TRADE],
        },
        "govern": {
            "allowed": bool({CAP_CATALOG_MANAGE, CAP_TREASURY_MANAGE, CAP_CONTRACT_DEPLOY} & caps),
            "items": [n for n, c in (("合约部署", CAP_CONTRACT_DEPLOY),
                                     ("树种与发行额度目录", CAP_CATALOG_MANAGE),
                                     ("能量国库与销毁", CAP_TREASURY_MANAGE)) if c in caps],
        },
    }


def duty_matrix() -> list:
    """全身份（6 节点 + 居民）× 四维度的职能矩阵（只读派生，供 /roles/duties 与前端渲染）。"""
    rows = []
    for r in ROLES + [RESIDENT_PROFILE]:
        dv = dimension_view(r if r["key"] != "resident" else None)
        caps = role_capabilities(r if r["key"] != "resident" else None)
        rows.append({
            "key": r["key"], "name": r["name"], "icon": r["icon"], "color": r["color"],
            # 对外契约里 wallet 这个名字**只能装真实地址**（0x + 40 hex）；
            # 友好别名（0xmetro）仅供展示，改名 wallet_alias，免得下游把它
            # 当资产标识回写（入库后就是「钱包里出现内部别名」那类缺陷）
            "wallet": (wallet_address(r["key"]) if r.get("wallet") else ""),
            "wallet_alias": r.get("wallet") or "",
            # 真实链上地址（资产台账与前端跳转 / 复制一律用它）
            "address": wallet_address(r["key"]) if r.get("wallet") else "",
            "profile": dv["profile"], "desc": r.get("desc") or "",
            "dimensions": {k: bool(v.get("allowed")) for k, v in dv.items() if isinstance(v, dict)},
            "capabilities": sorted(caps),
            "asset_forms": [a["asset"] for a in dv["issue_asset"]["forms"]],
            "energy_points": (r["energy_rule"]["points"] if r.get("energy_rule") else 0),
            "energy_quota": int(r.get("energy_quota") or 0),
        })
    return rows


def calc_energy_points(role: dict, proof: dict) -> tuple:
    """按真实商业逻辑核算本次发行能量：基础分 + 超门槛部分按量加成，封顶截断。

    回落旧行为：bonus_per_unit 缺省或 0 → 固定 points（不乘量、不截断）。
    返回 (points, 明细 dict)。
    """
    rule = role.get("energy_rule") or {}
    base = int(rule.get("points") or 0)
    per = int(rule.get("bonus_per_unit") or 0)
    cap = int(rule.get("bonus_cap") or 0) or base
    detail = {"base": base, "bonus": 0, "excess": 0.0, "per_unit": per, "cap": cap, "unit": rule.get("unit") or ""}
    if per <= 0 or rule.get("proof_field") == "no_cutlery":
        detail["capped"] = False
        return base, detail
    field = rule.get("proof_field") or ""
    raw = (proof or {}).get(field)
    try:
        val = float(raw) if raw is not None else 0.0
    except (TypeError, ValueError):
        val = 0.0
    try:
        min_v = float(rule.get("min") or 0)
    except (TypeError, ValueError):
        min_v = 0.0
    excess = max(0.0, val - min_v)
    bonus = int(excess * per)
    pts = base + bonus
    capped = pts > cap
    if capped:
        pts = cap
        bonus = max(0, pts - base)
    detail.update({"bonus": bonus, "excess": round(excess, 3), "capped": capped, "total": pts})
    return max(base, pts), detail


# ===========================================================================
# 角色与权限矩阵查询助手
# ===========================================================================
def normalize_role_key(role_key: str) -> str:
    """角色 key 归一化（别名 delivery/recycle → takeout/recycling），不校验角色存在性。

    与 find_role 的分工：find_role 用于「这个 key 能不能办事」（返回角色定义或
    None）；本函数只用于把埋点 target / 历史脏数据里的旧别名收敛到权威 key，
    再做去重计数（口径同 learning.paths._norm_role_keys、achievements 的归一化）。
    未知 key 原样小写返回，由调用方决定是否按已知角色集过滤。
    """
    k = str(role_key or "").strip().lower()
    return ROLE_ALIAS.get(k, k)


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
