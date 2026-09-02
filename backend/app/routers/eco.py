"""生态联盟链高级实战模块 API。

六个联盟节点（管理员 / 地铁 / 公交 / 共享单车 / 外卖 / 回收）协同运营，
基于 GreenEnergy（ERC20）、PlantCertificate（ERC721）、EcoBadge（ERC1155）
三个合约实现绿色能量发放、植树证书兑换、生态勋章/骑行券兑换全流程。
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..chain_client import get_chain_client
from ..db import _lock as _DB_LOCK, get_conn, now
from ..security import assert_actor_wallet, get_current_user
from ..tx_decoder import compile_source
# 联盟角色权威定义与权限助手已统一至 app/learning/alliance_roles.py（ROLES/ROLE_ALIAS
# 逐字段原样迁入；本模块经 import 保持原引用入口，散落的权限 if-else 改用统一助手，
# 403 文案与校验结果语义完全不变）
from ..learning.alliance_roles import (
    ROLES,
    ROLE_ALIAS,
    ensure_admin_for_trees,
    ensure_asset_owner,
    ensure_bike_for_voucher,
    ensure_issuer_role,
    ensure_minter_role,
)
# 学习行为埋点统一收口至 learning.events（EventType 常量 + track 唯一写入实现）
from ..learning.events import EventType, track as _track
# 任务 #21：五级验证流水线（记录模式：L3/L4 复用本接口既有校验与执行结果）+ 事件总线
from .. import verifier
from ..events_bus import BusEvent, publish as bus_publish


router = APIRouter(prefix="/api/eco", tags=["eco"])

# ===========================================================================
# 六个联盟链节点角色定义（ROLES / ROLE_ALIAS）已迁至 app/learning/alliance_roles.py
# （权威定义，内容逐字段原样迁入；本文件顶部 import 保持引用入口不变。前端
#  EnergyProofForm.vue 依赖的 energy_rule.proof_fields 亦随迁未动。）
# ===========================================================================

# 内置合约清单（名称与 deployed_contracts.name 对应）
BUILTIN_CONTRACTS = [
    {"name": "GreenEnergy",      "standard": "ERC20",   "file": "GreenEnergy.sol"},
    {"name": "PlantCertificate", "standard": "ERC721",  "file": "PlantCertificate.sol"},
    {"name": "EcoBadge",         "standard": "ERC1155", "file": "EcoBadge.sol"},
]

# 默认勋章 / 骑行券类型（EcoBadge 合约中 BADGE_ID=1, VOUCHER_ID=2）
DEFAULT_BADGE_TYPES = [
    {"badge_type": "badge",   "name": "生态勋章", "icon": "🏅", "cost_energy": 10,
     "token_id": 1, "supply": 100, "issuer_role": "",  "image_url": "",
     "desc": "绿色出行达人的荣誉勋章（默认类型，全体联盟节点可发放）"},
    {"badge_type": "voucher", "name": "骑行券",   "icon": "🎫", "cost_energy": 20,
     "token_id": 2, "supply": 100, "issuer_role": "bike", "image_url": "",
     "desc": "可兑换一次免费共享单车骑行（仅共享单车公司发放）"},
]

# 管理员别名 —— 兑换时能量消耗回收目标
ADMIN_ALIAS = "0xadmin"


# ===========================================================================
# 请求模型
# ===========================================================================
class RoleSelectReq(BaseModel):
    wallet: str
    role_key: str


class RoleClearReq(BaseModel):
    wallet: str

# role/clear 端点位于本文件「3. 绿色能量」分区前，用于普通用户（居民/学习者）身份切换

class EnergyIssueReq(BaseModel):
    wallet: str           # 接收能量的用户钱包（学习者 / 普通用户）
    role_key: str         # 发放能量的联盟角色（必须是有发放权限的角色）
    proof: dict = {}      # 业务凭证（地铁=乘车记录 / 外卖=订单号 / 回收=称重记录）
    force: bool = False   # 教师演示用：跳过凭证校验（默认 False，正式环境关闭）


class TreeAddReq(BaseModel):
    name: str
    required_energy: int
    image_url: str = ""
    description: str = ""
    wallet: str


class CertExchangeReq(BaseModel):
    wallet: str
    species_id: int


class BadgeExchangeReq(BaseModel):
    wallet: str
    badge_type: str          # badge | voucher（内置类型快捷方式）
    type_id: Optional[int] = None   # 指定兑换的勋章/骑行券类型 ID（生态勋章支持管理员自定义多类型）


class BadgeTypeAddReq(BaseModel):
    wallet: str              # 操作者钱包（必须是联盟角色：admin / metro / bus / bike / takeout / recycling）
    badge_type: str          # badge | voucher
    name: str
    icon: str = "🏅"
    image_url: str = ""
    cost_energy: int         # 兑换所需能量值
    supply: int              # 发行数量上限
    desc: str = ""


class BadgeMintReq(BaseModel):
    wallet: str              # 操作者钱包（联盟角色钱包，交易的 FROM）
    role_key: str            # 操作者当前选中的联盟角色
    type_id: int             # 勋章/骑行券类型 ID
    to_wallet: str           # 接收者（居民钱包）
    quantity: int = 1        # 铸造数量


class OpErrorRecordReq(BaseModel):
    wallet: str
    module: str       # role | energy | tree | certificate | badge | contract | other
    action: str       # 操作名称，如 select_role / issue_energy / exchange_badge ...
    level: str = "warn"   # warn | error | info
    message: str
    detail: str = ""  # 错误详情 / 堆栈


# ===========================================================================
# 内部工具函数
# ===========================================================================
def _find_role(role_key: str) -> Optional[dict]:
    """根据 role_key 查找角色定义，自动识别别名（如 'delivery' → 'takeout'）。"""
    if not role_key:
        return None
    k = role_key.strip().lower()
    k = ROLE_ALIAS.get(k, k)
    for r in ROLES:
        if r["key"] == k:
            return r
    return None


def _validate_energy_proof(role: dict, proof: dict, force: bool = False) -> dict:
    """校验发放能量的业务凭证。

    返回 {'ok': bool, 'msg': str, 'proof_no': str, 'threshold': str}
    校验规则（与 ROLES.energy_rule 对齐）：
    - 地铁 metro：proof.distance_km ≥ 10km → 发放 50 点
    - 公交 bus：proof.ride_minutes ≥ 5min → 发放 20 点
    - 单车 bike：proof.distance_km ≥ 2km → 发放 15 点
    - 外卖 takeout：proof.no_cutlery == True → 发放 10 点
    - 回收 recycling：proof.weight_kg ≥ 1kg → 发放 100 点

    force=True 时跳过校验（教师演示用）。
    """
    rule = role.get("energy_rule") or {}
    pf = proof or {}
    # 业务单号提取优先级（保证同一业务事件不重复发能量）：
    #   1) role.energy_rule.proof_no_field （显式配置，专业且无歧义）
    #   2) 常见单号字段兜底（兼容前端/脚本的非正式调用）
    no_fields: list = []
    explicit = rule.get("proof_no_field")
    if explicit:
        no_fields.append(explicit)
    no_fields += ["trip_id", "trip_no", "order_id", "order_no", "platform_order"]
    proof_no = ""
    for f in no_fields:
        v = pf.get(f)
        if v is not None and str(v).strip():
            proof_no = str(v).strip()
            break
    if not proof_no and force:
        proof_no = f"{role['key']}-{uuid.uuid4().hex[:8]}"
    threshold = f"{rule.get('proof_field', '')} ≥ {rule.get('min', '?')} {rule.get('unit', '')}"

    if force:
        return {
            "ok": True, "proof_no": proof_no or f"{role['key']}-force-{uuid.uuid4().hex[:6]}",
            "threshold": threshold, "msg": "教师演示：跳过业务凭证校验",
        }

    # 必填业务字段校验（进站口 / 出站口 / 进站时间 / 订单号 / 回收分类等）
    missing = []
    for f in rule.get("proof_fields") or []:
        if f.get("required"):
            v = pf.get(f["key"])
            if v is None or v == "" or (isinstance(v, str) and not v.strip()):
                missing.append(f.get("label") or f["key"])
    if missing:
        return {"ok": False, "threshold": threshold, "proof_no": proof_no,
                "msg": f"{role['name']} 发放能量缺少必填业务数据：{'、'.join(missing)}。请补全业务凭证后重新提交"}

    if rule.get("proof_field") == "distance_km":  # 地铁 / 单车
        val = pf.get("distance_km")
        try:
            val_n = float(val) if val is not None else 0
        except (TypeError, ValueError):
            val_n = 0
        min_v = float(rule.get("min", 0) or 0)
        if val_n < min_v:
            return {"ok": False, "threshold": threshold, "proof_no": proof_no,
                    "msg": f"{role['name']} 发放 {rule['points']} 点能量需要 {rule.get('action','')} ≥ {min_v} {rule.get('unit','')}，当前 {val_n}"}
        return {"ok": True, "proof_no": proof_no, "threshold": threshold, "msg": "业务凭证校验通过"}

    if rule.get("proof_field") == "ride_minutes":  # 公交
        val = pf.get("ride_minutes")
        try:
            val_n = float(val) if val is not None else 0
        except (TypeError, ValueError):
            val_n = 0
        min_v = float(rule.get("min", 0) or 0)
        if val_n < min_v:
            return {"ok": False, "threshold": threshold, "proof_no": proof_no,
                    "msg": f"{role['name']} 发放 {rule['points']} 点能量需要乘车时长 ≥ {min_v} {rule.get('unit','')}，当前 {val_n}"}
        return {"ok": True, "proof_no": proof_no, "threshold": threshold, "msg": "业务凭证校验通过"}

    if rule.get("proof_field") == "no_cutlery":  # 外卖：无需餐具
        if not pf.get("no_cutlery"):
            return {"ok": False, "threshold": "no_cutlery = true", "proof_no": proof_no,
                    "msg": f"{role['name']} 仅对「无需餐具」绿色外卖订单发放 {rule['points']} 点能量，需设置 proof.no_cutlery=true"}
        return {"ok": True, "proof_no": proof_no, "threshold": threshold, "msg": "绿色订单标记校验通过"}

    if rule.get("proof_field") == "weight_kg":  # 回收
        val = pf.get("weight_kg")
        try:
            val_n = float(val) if val is not None else 0
        except (TypeError, ValueError):
            val_n = 0
        min_v = float(rule.get("min", 0) or 0)
        if val_n < min_v:
            return {"ok": False, "threshold": threshold, "proof_no": proof_no,
                    "msg": f"{role['name']} 发放 {rule['points']} 点能量需要回收物 ≥ {min_v} kg，当前 {val_n} kg"}
        return {"ok": True, "proof_no": proof_no, "threshold": threshold, "msg": "回收称重记录校验通过"}

    # admin 等没有能量规则的角色
    return {"ok": False, "threshold": "N/A", "proof_no": proof_no, "msg": f"角色 {role['name']} 没有能量发放规则"}


def _selected_role(wallet: str) -> Optional[dict]:
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
    return _find_role(row["role_key"])


def _find_contract(name: str):
    """从 deployed_contracts 表查找指定名称的最新部署合约。

    返回 (address, abi) 元组；未找到或地址在当前链上无代码（stale 记录）时返回 (None, None)。
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT address, abi FROM deployed_contracts WHERE name=? ORDER BY created_at DESC LIMIT 1",
            (name,),
        ).fetchone()
    if not row:
        return None, None
    # 校验地址在当前链实例上确有合约代码，避免后端重启后 stale 记录导致调用静默失败
    c = get_chain_client()
    if not c.has_code(row["address"]):
        return None, None
    return row["address"], json.loads(row["abi"])


def _to_int(v: Any) -> int:
    """把合约返回值安全转为整数。"""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return 0
        if s.startswith("0x"):
            return int(s, 16)
        return int(s)
    return 0


def _norm_wallet(wallet: str) -> str:
    """统一钱包标识，避免大小写差异导致资产归属判断不一致。"""
    return (wallet or "").strip().lower()


def _get_energy_ledger_balance(wallet: str) -> int:
    """从持久化业务账本计算绿色能量余额。

    账本口径：
    - 低碳行为发放：增加能量；
    - 兑换证书 / 勋章 / 骑行券：扣减能量；
    - 市场购买：买方扣减；
    - 市场售出：卖方增加。

    该口径用于审计/流水与展示余额基准（纯读，无链上写副作用）；
    写路径（兑换/能量回收/挂牌购买）在账本→链上回填同步后，
    以链上 balanceOf 校验并执行转账。
    """
    w = _norm_wallet(wallet)
    if not w:
        return 0
    with get_conn() as conn:
        issued = conn.execute(
            "SELECT COALESCE(SUM(points), 0) FROM eco_energy_records WHERE lower(wallet)=?",
            (w,),
        ).fetchone()[0] or 0
        cert_cost = conn.execute(
            "SELECT COALESCE(SUM(cost_energy), 0) FROM eco_certificates WHERE lower(owner)=?",
            (w,),
        ).fetchone()[0] or 0
        badge_cost = conn.execute(
            "SELECT COALESCE(SUM(cost_energy), 0) FROM eco_badges WHERE lower(owner)=?",
            (w,),
        ).fetchone()[0] or 0
        market_spent = conn.execute(
            "SELECT COALESCE(SUM(price_energy), 0) FROM eco_market_listings WHERE status='sold' AND lower(buyer)=?",
            (w,),
        ).fetchone()[0] or 0
        market_income = conn.execute(
            "SELECT COALESCE(SUM(price_energy), 0) FROM eco_market_listings WHERE status='sold' AND lower(seller)=?",
            (w,),
        ).fetchone()[0] or 0
    return max(0, int(issued) - int(cert_cost) - int(badge_cost) - int(market_spent) + int(market_income))


def _get_energy_balance(wallet: str) -> str:
    """查询钱包绿色能量余额（纯读，不产生任何链上写副作用）。

    口径：账本余额（持久化业务账本）优先，链上余额只读回退：
    - 账本有记录时直接返回账本净额（沙盒链重启重置后仍能正确展示历史余额）；
    - 账本无记录时只读查询链上 GreenEnergy.balanceOf（不 mint、不回填）；
    - 合约未部署 / 链上调用异常时返回 0。

    链上回填（_sync_chain_balance，差额>0 时由 0xadmin 真实发起 GreenEnergy.mint）
    仅保留在写路径（兑换 / 能量回收 / 挂牌购买等已有调用点）：
    GET /energy/balance、画像等读接口不再触发链上交易，
    避免页面加载污染块高与交易流、并发首访重复 mint。
    """
    ledger = _get_energy_ledger_balance(wallet)
    if ledger > 0:
        return str(ledger)
    addr, abi = _find_contract("GreenEnergy")
    if not addr:
        return "0"
    c = get_chain_client()
    try:
        r = c.call_contract(addr, "balanceOf", [c.resolve_account(wallet)], wallet, abi)
        if r.get("ok"):
            return str(_to_int(r.get("result", "0")))
    except Exception:
        pass
    return "0"


def _sync_chain_balance(wallet: str) -> None:
    """把持久化业务账本余额回填到链上（账本 > 链上时由管理员 mint 差额）。

    本地沙盒链（py-evm）在服务重启后会重置，为保证「兑换 / 挂牌购买」的链上转账
    能够真实执行，需要将账本与链上余额对齐。回填通过 GreenEnergy.mint 由管理员
    钱包发出；差额本身已在账本中，故不重复写 eco_energy_records。
    """
    ledger = _get_energy_ledger_balance(wallet)
    if ledger <= 0:
        return
    addr, abi = _find_contract("GreenEnergy")
    if not addr:
        return
    c = get_chain_client()
    try:
        r = c.call_contract(addr, "balanceOf", [c.resolve_account(wallet)], wallet, abi)
        chain_bal = _to_int(r.get("result", "0")) if r.get("ok") else 0
    except Exception:
        chain_bal = 0
    diff = ledger - chain_bal
    if diff <= 0:
        return
    r = c.call_contract(
        addr, "mint",
        [c.resolve_account(wallet), diff, "账本回填"],
        ADMIN_ALIAS, abi,
    )
    if not r.get("ok"):
        return
    # 回填不入账本（账本本来就有这笔余额），仅记录链上补给痕迹到能量记录表会虚增账本，
    # 因此不写 eco_energy_records，只打印日志。
    print(f"[eco] 账本回填 {wallet}: +{diff} 能量 (mint by 0xadmin)")


def _get_badge_type(conn, *, type_id: Optional[int] = None, badge_type: Optional[str] = None) -> Optional[dict]:
    """按类型 ID 或内置类型（badge/voucher 的默认类型）查询勋章/骑行券类型定义。"""
    row = None
    if type_id:
        row = conn.execute("SELECT * FROM eco_badge_types WHERE id=?", (type_id,)).fetchone()
    elif badge_type:
        row = conn.execute(
            "SELECT * FROM eco_badge_types WHERE badge_type=? ORDER BY id ASC LIMIT 1",
            (badge_type,),
        ).fetchone()
    return dict(row) if row else None


def _active_listing_for_asset(conn, asset_type: str, asset_id: int):
    """查询资产当前是否存在有效挂牌。"""
    return conn.execute(
        "SELECT * FROM eco_market_listings WHERE asset_type=? AND asset_id=? AND status='active' ORDER BY id DESC LIMIT 1",
        (asset_type, asset_id),
    ).fetchone()


def _attach_listing_state(conn, row: dict, asset_type: str) -> dict:
    """给资产返回值附加挂牌状态，前端可据此禁用重复挂牌并展示下架入口。"""
    listing = _active_listing_for_asset(conn, asset_type, int(row["id"]))
    row["listed"] = bool(listing)
    row["active_listing"] = dict(listing) if listing else None
    row["market_status"] = "listed" if listing else "wallet"
    return row


# ===========================================================================
# 1. 角色管理
# ===========================================================================
@router.get("/roles")
def list_roles():
    """返回六个联盟节点角色列表。"""
    return ROLES


@router.post("/role/select")
def select_role(req: RoleSelectReq, user: dict = Depends(get_current_user)):
    """选择 / 切换联盟节点角色（INSERT OR REPLACE）。操作者身份从 JWT 验签解析。"""
    role = _find_role(req.role_key)
    if not role:
        raise HTTPException(400, f"未知角色: {req.role_key}")
    req.wallet = assert_actor_wallet(user, req.wallet)  # 防伪造他人身份
    # 以权威 key 落库（delivery/recycle 等别名在此归一化，避免前后端 key 不一致导致页面联动错位）
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO eco_role_selections(wallet, role_key, selected_at) VALUES(?,?,?)",
            (req.wallet, role["key"], now()),
        )
    # 行为埋点：学生切换联盟角色（对应 alliance_gov 维度的 eco_role_switch 指标）
    _track(EventType.ECO_ROLE_SWITCH, target=role["key"], wallet=req.wallet or "",
           extra={"role_key": role["key"]})
    return {"ok": True, "role": role}


@router.get("/role/current")
def current_role(wallet: str):
    """查询钱包当前选中的角色。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT role_key FROM eco_role_selections WHERE wallet=?",
            (wallet,),
        ).fetchone()
    if not row:
        return {"role_key": None}
    role = _find_role(row["role_key"])
    # 库里可能有历史别名 key（delivery/recycle），统一回权威 key，保证前端角色卡片高亮联动一致
    key = role["key"] if role else row["role_key"]
    return {"role_key": key, "role": role}


def _workbench_todos(role: dict) -> list:
    """由 ROLES 权限位静态推导的「待办运营动作」清单（只读映射，不修改 ROLES 结构）。

    推导规则（与任务要求的静态映射一致）：
    - can_issue_voucher=true → 审核并发放绿色出行凭证（骑行券）
    - can_issue_badge=true   → 铸造发放生态勋章（ERC1155）
    - can_manage_trees=true  → 上架 / 维护树种并发放植树证书
    - energy_rule 存在       → 审核业务凭证并发放绿色能量
    """
    todos: list = []
    rule = role.get("energy_rule")
    if rule:
        todos.append({
            "key": "issue_energy",
            "source": "energy_rule",
            "title": f"审核业务凭证并发放绿色能量（{rule.get('action', '')} +{rule.get('points', '?')} 点/次）",
            "desc": (f"核验 {rule.get('proof_field', '')} ≥ {rule.get('min', '?')} {rule.get('unit', '')}，"
                     "同一业务单号 + 同一角色不重复发放"),
        })
    if role.get("can_issue_badge"):
        todos.append({
            "key": "issue_badge",
            "source": "can_issue_badge",
            "title": "铸造发放生态勋章（ERC1155）",
            "desc": "向达标居民铸造生态勋章，或由居民消耗能量自助兑换",
        })
    if role.get("can_issue_voucher"):
        todos.append({
            "key": "issue_voucher",
            "source": "can_issue_voucher",
            "title": "审核并发放绿色出行凭证（骑行券）",
            "desc": "骑行券仅由共享单车节点维护与发放（issuer_role=bike）",
        })
    if role.get("can_manage_trees"):
        todos.append({
            "key": "manage_trees",
            "source": "can_manage_trees",
            "title": "上架 / 维护可兑换树种并发放植树证书",
            "desc": "管理树种目录与所需能量，居民凭能量兑换 ERC721 植树证书",
        })
    if role.get("key") == "admin":
        # 管理员不发放能量，但承担能量治理职责（国库回收 + 账本回填）
        todos.append({
            "key": "energy_treasury",
            "source": "admin",
            "title": "能量国库管理（回收 + 账本回填）",
            "desc": "居民兑换证书/勋章/骑行券消耗的能量转入管理员国库（0xadmin）；"
                    "沙盒链重置后由管理员 mint 回填居民账本余额",
        })
    return todos


@router.get("/role/workbench")
def role_workbench(role_key: str, user: dict = Depends(get_current_user)):
    """角色工作台：职责 + 权限位 + 该角色钱包的链上活动统计 + 待办运营动作清单（只读聚合）。

    - 职责与权限位直接读 ROLES 定义（不修改既有字段结构）
    - 链上活动统计：contract_calls 按 caller、transactions 收发、eco_energy_records 按 role_key
    - 待办运营动作：由 can_issue_* 权限位静态推导（见 _workbench_todos）
    """
    role = _find_role(role_key)
    if not role:
        raise HTTPException(404, f"未知角色: {role_key}")
    role_wallet = (role.get("wallet") or f"0x{role['key']}").strip()
    # 角色钱包在链上的真实地址（六个联盟角色均为固定演示别名，链初始化时已注册，解析无副作用）
    resolved_addr = ""
    try:
        resolved = get_chain_client().resolve_account(role_wallet)
        if resolved:
            resolved_addr = str(resolved)
    except Exception:
        resolved_addr = ""
    # 合约调用 / 交易的归属匹配：同时兼容「角色别名」与「链上真实地址」两种落库口径
    candidates = {role_wallet.lower()}
    if resolved_addr:
        candidates.add(resolved_addr.lower())
    ph = ",".join("?" for _ in candidates)
    cands = list(candidates)
    ok_ph = ",".join("?" for _ in range(2))
    with get_conn() as conn:
        # 合约调用统计（按 caller）
        call_total = conn.execute(
            f"SELECT COUNT(*) FROM contract_calls WHERE lower(COALESCE(caller,'')) IN ({ph})", cands,
        ).fetchone()[0] or 0
        call_ok = conn.execute(
            f"SELECT COUNT(*) FROM contract_calls WHERE lower(COALESCE(caller,'')) IN ({ph}) "
            f"AND lower(COALESCE(status,'')) IN ({ok_ph})", cands + ["success", "1"],
        ).fetchone()[0] or 0
        call_methods = conn.execute(
            f"SELECT method, COUNT(*) AS count FROM contract_calls "
            f"WHERE lower(COALESCE(caller,'')) IN ({ph}) "
            "GROUP BY method ORDER BY count DESC LIMIT 8", cands,
        ).fetchall()
        # 链上交易收发统计
        tx_sent = conn.execute(
            f"SELECT COUNT(*) FROM transactions WHERE lower(COALESCE(from_addr,'')) IN ({ph})", cands,
        ).fetchone()[0] or 0
        tx_recv = conn.execute(
            f"SELECT COUNT(*) FROM transactions WHERE lower(COALESCE(to_addr,'')) IN ({ph})", cands,
        ).fetchone()[0] or 0
        # 绿色能量发放统计（按 role_key：发放次数 / 总量 / 最近发放时间）
        er = conn.execute(
            "SELECT COUNT(*) AS issue_count, COALESCE(SUM(points),0) AS total_points, "
            "MAX(created_at) AS last_issued_at FROM eco_energy_records WHERE role_key=?",
            (role["key"],),
        ).fetchone()
    return {
        "role_key": role["key"],
        "role": dict(role),
        "permissions": {
            "can_issue_badge": bool(role.get("can_issue_badge")),
            "can_issue_voucher": bool(role.get("can_issue_voucher")),
            "can_manage_trees": bool(role.get("can_manage_trees")),
            "has_energy_rule": bool(role.get("energy_rule")),
        },
        "activity": {
            "wallet": role_wallet,
            "chain_address": resolved_addr,
            "contract_calls": {
                "total": int(call_total),
                "success": int(call_ok),
                "failed": int(call_total) - int(call_ok),
                "methods": [{"method": r["method"], "count": r["count"]} for r in call_methods],
            },
            "transactions": {
                "sent": int(tx_sent),
                "received": int(tx_recv),
                "total": int(tx_sent) + int(tx_recv),
            },
            "energy": {
                "issue_count": int(er["issue_count"] or 0),
                "total_points": int(er["total_points"] or 0),
                "last_issued_at": er["last_issued_at"] or "",
            },
        },
        "todos": _workbench_todos(role),
    }


# ===========================================================================
# 2. 合约状态与源码
# ===========================================================================
@router.get("/contracts/status")
def contracts_status():
    """检查三个内置合约是否已部署。"""
    ge_addr, _ = _find_contract("GreenEnergy")
    pc_addr, _ = _find_contract("PlantCertificate")
    eb_addr, _ = _find_contract("EcoBadge")
    return {
        "green_energy": {"deployed": bool(ge_addr), "address": ge_addr},
        "plant_certificate": {"deployed": bool(pc_addr), "address": pc_addr},
        "eco_badge": {"deployed": bool(eb_addr), "address": eb_addr},
        "all_deployed": bool(ge_addr and pc_addr and eb_addr),
    }


@router.get("/contracts/builtin")
def builtin_contracts():
    """返回三个内置合约的 Solidity 源码。"""
    out = []
    for c in BUILTIN_CONTRACTS:
        p = settings.contracts_dir / c["file"]
        out.append({
            "name": c["name"],
            "standard": c["standard"],
            "file": c["file"],
            "source": p.read_text(encoding="utf-8") if p.exists() else "",
        })
    return out


# ---------- 一键编译 + 部署 ----------
# 各合约构造函数默认参数（学生无需手动填写）
DEFAULT_CTOR_ARGS = {
    "GreenEnergy":      [1_000_000_000],            # uint256 _initialSupply = 10亿
    "PlantCertificate": ["PlantCertificate", "PCERT"],  # string _name, string _symbol
    "EcoBadge":         [],                          # 无构造函数
}


class ContractDeployReq(BaseModel):
    name: str          # GreenEnergy | PlantCertificate | EcoBadge
    deployer: str = "0xlearner"


@router.post("/contracts/deploy")
def deploy_builtin_contract(req: ContractDeployReq, user: dict = Depends(get_current_user)):
    """一键编译 + 部署内置绿色合约。

    流程：读取源码 → solc 编译 → 调用 EVM 部署 → 写入 deployed_contracts 表。
    若该合约已部署，则重新部署并覆盖旧记录（保留最新地址）。
    """
    req.deployer = assert_actor_wallet(user, req.deployer, "deployer")  # 部署者身份从 JWT 解析
    target = next((c for c in BUILTIN_CONTRACTS if c["name"] == req.name), None)
    if not target:
        raise HTTPException(400, f"未知合约: {req.name}，支持: GreenEnergy / PlantCertificate / EcoBadge")

    src_path = settings.contracts_dir / target["file"]
    if not src_path.exists():
        raise HTTPException(404, f"合约源码文件不存在: {target['file']}")
    source = src_path.read_text(encoding="utf-8")

    # 1. 编译
    comp = compile_source(source)
    if not comp.get("ok"):
        raise HTTPException(400, "编译失败: " + "; ".join(comp.get("errors") or []))

    # 2. 部署
    c = get_chain_client()
    ctor_args = DEFAULT_CTOR_ARGS.get(req.name, [])
    try:
        r = c.deploy_contract(
            req.name, comp["abi"], comp["bytecode"], source,
            req.deployer, target["standard"], ctor_args,
        )
    except Exception as e:
        raise HTTPException(400, f"部署失败: {e}")

    # 3. 持久化（先删旧地址记录避免 UNIQUE 冲突）
    with get_conn() as conn:
        conn.execute("DELETE FROM deployed_contracts WHERE address=?", (r["address"],))
        conn.execute(
            "INSERT INTO deployed_contracts(address,name,abi,bytecode,source,deployer,tx_hash,standard,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (r["address"], req.name, json.dumps(comp["abi"]), comp["bytecode"], source,
             req.deployer, r["tx_hash"], target["standard"], now()),
        )

    return {
        "ok": True,
        "name": req.name,
        "address": r["address"],
        "tx_hash": r["tx_hash"],
        "block_number": r.get("block_number"),
        "gas_used": r.get("gas_used", 0),
        "standard": target["standard"],
    }


# ===========================================================================
# 3. 绿色能量
# ===========================================================================
def _energy_replay_pipeline(reason: str) -> dict:
    """幂等命中（防刷）返回的 pipeline：不落新 task_runs，仅标注 replay。"""
    return {
        "run_id": "",
        "ok": True,
        "status": "idempotent",
        "latency_ms": 0.0,
        "stages": [{"stage": "replay", "ok": True, "detail": reason,
                    "latency_ms": 0.0, "skipped": True}],
    }


@router.post("/role/clear")
def clear_role(req: RoleClearReq, user: dict = Depends(get_current_user)):
    """清除当前钱包的联盟角色选择，回到普通用户（居民/学习者）身份。"""
    req.wallet = assert_actor_wallet(user, req.wallet)
    with get_conn() as conn:
        conn.execute("DELETE FROM eco_role_selections WHERE wallet=?", (req.wallet,))
    _track(EventType.ECO_ROLE_SWITCH, target="resident", wallet=req.wallet or "", extra={"role_key": ""})
    return {"ok": True}


@router.post("/energy/issue")
def issue_energy(req: EnergyIssueReq, user: dict = Depends(get_current_user)):
    """根据角色规则发放绿色能量（调用 GreenEnergy.mint）。

    真实业务逻辑（与实训业务模型一致）：
    1. 发放交易 FROM = 联盟角色组织钱包（0xmetro / 0xbus / 0xbike / 0xtakeout / 0xrecycle）——
       联盟角色的核心意义即「能量发行方」，只有联盟节点有权 mint 绿色能量；
    2. 两种发放模式：
       - 居民申请（操作者未选联盟角色 = 普通用户）：居民提交低碳行为凭证，
         对应联盟节点审核（阈值校验）后发放到自己钱包——普通用户的 5 种获取能量方式；
       - 角色扮演（操作者已选联盟角色）：选中角色必须与发放角色一致，体验联盟节点审核发放职责；
    3. 必须提供对应业务凭证（乘车里程 / 时长 / 外卖订单 / 回收重量），并通过阈值校验；
    4. 同一业务单号 + 同一发放角色不允许重复发能量（UNIQUE 防刷）；
    5. 写入链上 + 写入业务账本，双写一致。

    force=True 可跳过校验（教师演示用），但记录中会标记 proof_validated=0。

    任务 #21：走五级验证流水线（记录模式）——L1 compile / L2 semantic 不适用（skipped），
    L3 business 复用本接口既有校验结果（角色权限 + 业务凭证阈值，不重复校验两次），
    L4 onchain 复用 GreenEnergy.mint 执行结果；响应既有字段全保留，追加 pipeline。
    成功/失败均写 task_runs；幂等命中返回 replay 标记、不重复落行。
    """
    _t0 = time.perf_counter()
    uc = verifier.user_ctx_from(user)
    _pl = {"wallet": req.wallet or "", "role_key": req.role_key or "", "force": bool(req.force)}
    try:
        return _issue_energy_core(req, user, uc, _t0, _pl)
    except HTTPException as e:
        # 任一环节失败也落一行 task_runs（status=failed），随后原样抛出（错误语义不变）
        verifier.record_failure("energy_issue", _pl, uc, _t0, detail=str(e.detail),
                                task_ref=(req.proof or {}).get("proof_no", "") if isinstance(req.proof, dict) else "")
        raise


def _issue_energy_core(req: "EnergyIssueReq", user: dict, uc: dict,
                       _t0: float, _pl: dict) -> dict:
    """issue_energy 主体（既有逻辑原样保留，仅在返回前追加 pipeline 与事件）。"""
    role = _find_role(req.role_key)
    if not role:
        raise HTTPException(400, f"未知角色: {req.role_key}")
    req.wallet = assert_actor_wallet(user, req.wallet)  # 接收方钱包必须与登录身份匹配（或内置生态钱包）
    rule = role.get("energy_rule")
    if not rule:
        raise HTTPException(400, f"角色 [{role['name']}] 没有能量发放规则")
    issuer_wallet = role.get("wallet") or f"0x{role['key']}"
    if not req.wallet:
        raise HTTPException(400, "接收能量的钱包 wallet 必填")

    # 权限闭环（两种发放模式）：
    # - 操作者钱包已选联盟角色 → 角色扮演发放：选中角色必须与发放角色一致，
    #   避免未切换角色即可随意调用发币接口；
    # - 操作者钱包未选角色（普通用户/居民身份）→ 居民申请发放：提交低碳行为凭证，
    #   由对应联盟节点审核（下方阈值校验）后发放，链上 FROM 仍是该组织钱包，
    #   体现「只有联盟节点有发行权」的角色意义；教师演示可用 force=true 跳过校验。
    sel = _selected_role(req.wallet)
    mode = "force" if req.force else ("role_play" if sel else "resident_apply")
    if not req.force and sel is not None:
        ensure_issuer_role(role, sel)

    ge_addr, ge_abi = _find_contract("GreenEnergy")
    if not ge_addr:
        raise HTTPException(400, "GreenEnergy 合约未部署，请先部署合约")

    # 1. 业务凭证校验（阈值规则 + force 开关）
    proof = (req.proof or {}) if isinstance(req.proof, dict) else {}
    pr = _validate_energy_proof(role, proof, force=bool(req.force))
    if not pr["ok"]:
        raise HTTPException(
            400,
            f"业务凭证校验失败：{pr['msg']}。"
            f"请提供 proof.{rule.get('proof_field','')} = {rule.get('min','?')} {rule.get('unit','')} 以上",
        )
    proof_no = (pr.get("proof_no") or "").strip()
    if not proof_no:
        proof_no = f"{role['key']}-{uuid.uuid4().hex[:8]}"

    c = get_chain_client()
    points = int(rule["points"])
    action = rule["action"]

    # 2. 幂等校验（防刷）：同一 proof_no + role_key 已经发过 → 直接返回旧结果（UNIQUE 兜底）
    with get_conn() as conn:
        dup = conn.execute(
            "SELECT * FROM eco_energy_records WHERE proof_no=? AND role_key=? LIMIT 1",
            (proof_no, role["key"]),
        ).fetchone()
    if dup:
        return {
            "ok": True, "idempotent": True,
            "points": dup["points"], "tx_hash": dup["tx_hash"] or "",
            "action": dup["action"],
            "proof_no": dup["proof_no"], "proof_validated": bool(dup["proof_validated"]),
            "proof_threshold": dup["proof_threshold"] or "",
            "warning": "该业务单号已发放过能量，已做幂等返回",
            "mode": mode,
            "issued_by": issuer_wallet, "received_by": req.wallet,
            "pipeline": _energy_replay_pipeline(
                f"幂等命中：proof_no={dup['proof_no']} 已发放，直接返回旧结果"),
        }

    # 3. 并发防双铸占位（任务 #25 评审修复 TOCTOU）：先在 db 全局锁内 INSERT 占位行
    # （tx_hash=''），靠 UNIQUE(proof_no, role_key) 拦截并发同单号请求；
    # 占位成功后再链上 mint，成功则 UPDATE 回填 tx_hash；mint 失败则删除占位行、
    # 按原错误语义抛出。占位命中 UNIQUE → 走原幂等回放路径（不重复落行）。
    with _DB_LOCK, get_conn() as conn:
        try:
            conn.execute(
                """INSERT INTO eco_energy_records(
                    wallet, role_key, role_name, action, points, tx_hash, created_at,
                    issuer_wallet, proof_no, proof_payload, proof_validated, proof_threshold
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    req.wallet, role["key"], role["name"], action, points, "", now(),
                    issuer_wallet,
                    proof_no,
                    json.dumps(proof, ensure_ascii=False) if proof else None,
                    1 if (pr["ok"] and not req.force) else 0,
                    pr.get("threshold") or "",
                ),
            )
        except Exception as e:
            # UNIQUE 命中（并发占位已由其它请求完成）→ 原幂等回放路径
            if "UNIQUE" in str(e).upper():
                row = conn.execute(
                    "SELECT * FROM eco_energy_records WHERE proof_no=? AND role_key=? LIMIT 1",
                    (proof_no, role["key"]),
                ).fetchone()
                if row:
                    return {
                        "ok": True, "idempotent": True,
                        "points": row["points"], "tx_hash": row["tx_hash"] or "",
                        "action": row["action"],
                        "proof_no": proof_no,
                        "mode": mode,
                        "issued_by": issuer_wallet, "received_by": req.wallet,
                        "pipeline": _energy_replay_pipeline(
                            f"幂等命中（UNIQUE 占位）：proof_no={proof_no} 已发放"),
                    }
            raise

    # 4. 调用 GreenEnergy.mint(receiver, value, action)
    # ⚠️ 真实业务：FROM = 发放方联盟角色钱包（0xmetro 等），不是接收者 req.wallet！
    r = c.call_contract(
        ge_addr, "mint",
        [c.resolve_account(req.wallet), points, action],
        issuer_wallet, ge_abi,
    )
    if not r.get("ok"):
        # mint 失败：删除占位行释放单号（下次可重试），再按原错误语义抛出
        with _DB_LOCK, get_conn() as conn:
            conn.execute(
                "DELETE FROM eco_energy_records WHERE proof_no=? AND role_key=? AND tx_hash=''",
                (proof_no, role["key"]),
            )
        raise HTTPException(400, f"能量发放失败（合约调用 by {issuer_wallet}）: {r.get('error','')}")
    tx_hash = r.get("tx_hash", "")

    # 5. 回填 tx_hash 完成占位行的双写闭环（链上 + 业务账本）
    with _DB_LOCK, get_conn() as conn:
        conn.execute(
            "UPDATE eco_energy_records SET tx_hash=? WHERE proof_no=? AND role_key=?",
            (tx_hash, proof_no, role["key"]),
        )

    _track(EventType.ECO_ENERGY_ISSUE, target=role["key"], ref_id=proof_no, wallet=req.wallet,
           extra={"role": role["name"], "points": points, "action": action})

    # 任务 #21：记录模式流水线——L3 复用既有校验结果（角色权限 + 凭证阈值），
    # L4 复用 mint 执行结果，不重复校验 / 不重复算分（L5 只读聚合出成绩影响摘要）
    _stages = [
        verifier.stage_skipped("compile", "能量发放非合约编译类任务"),
        verifier.stage_skipped("semantic", "无 ABI/构造参数语义校验需求"),
        verifier.stage_result(
            "business", True,
            f"角色权限与业务凭证校验通过（proof_no={proof_no}，force={bool(req.force)}）"),
        verifier.stage_result(
            "onchain", bool(r.get("ok")),
            f"GreenEnergy.mint 上链成功，tx={tx_hash}",
            latency_ms=(time.perf_counter() - _t0) * 1000),
    ]
    _pipeline = verifier.finalize_run(
        "energy_issue", _pl, uc, _stages, started_at=_t0, task_ref=proof_no)

    # 事件总线：能量发放成功 → SSE 推送（线程安全，前端 Monitor/Dashboard 刷新）
    bus_publish(BusEvent.ENERGY_ISSUED,
                {"role_key": role["key"], "points": points, "tx_hash": tx_hash,
                 "proof_no": proof_no, "wallet": req.wallet},
                user_id=uc.get("user_id") or "", class_id=uc.get("class_id") or "")

    return {
        "ok": True,
        "points": points,
        "tx_hash": tx_hash,
        "action": action,
        # 溯源信息：链下业务单号 → 链上 tx_hash → 发放方/接收方钱包
        "proof_no": proof_no,
        "proof_validated": bool(pr["ok"] and not req.force),
        "proof_threshold": pr.get("threshold") or "",
        "proof_msg": pr.get("msg") or "",
        "mode": mode,                     # resident_apply=居民申请 / role_play=角色扮演 / force=教师演示
        "issued_by": issuer_wallet,       # 发放方联盟角色钱包（链上 FROM）
        "received_by": req.wallet,        # 接收方用户钱包（链上 mint(to)）
        "contract": ge_addr,
        "method": "GreenEnergy.mint(to,value,reason)",
        "pipeline": _pipeline,
    }


@router.get("/energy/records")
def energy_records(wallet: str, limit: int = 50):
    """返回绿色能量发放记录。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM eco_energy_records WHERE wallet=? ORDER BY id DESC LIMIT ?",
            (wallet, limit),
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.get("/energy/balance")
def energy_balance(wallet: str):
    """查询钱包绿色能量余额（GreenEnergy.balanceOf）。"""
    return {"wallet": wallet, "balance": _get_energy_balance(wallet)}


# ===========================================================================
# 4. 树种管理
# ===========================================================================
@router.get("/trees")
def list_trees():
    """返回所有树种列表。"""
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM eco_tree_species ORDER BY id DESC").fetchall()
    return {"items": [dict(r) for r in rows]}


@router.post("/trees/add")
def add_tree(req: TreeAddReq, user: dict = Depends(get_current_user)):
    """管理员新增树种。"""
    req.wallet = assert_actor_wallet(user, req.wallet)  # 操作者身份从 JWT 解析
    # 验证 wallet 的角色是 admin（统一权限助手；精确 wallet=? 匹配口径保持不变）
    with get_conn() as conn:
        row = conn.execute(
            "SELECT role_key FROM eco_role_selections WHERE wallet=?",
            (req.wallet,),
        ).fetchone()
    ensure_admin_for_trees(row["role_key"] if row else None)
    # 验证所需能量下限
    if req.required_energy < 1000:
        raise HTTPException(400, "树种所需能量不能少于 1000")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO eco_tree_species(name,required_energy,image_url,description,created_by,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (req.name, req.required_energy, req.image_url, req.description, req.wallet, now()),
        )
        tree_id = cur.lastrowid
    return {"ok": True, "id": tree_id}


# ===========================================================================
# 5. 植树证书兑换
# ===========================================================================
@router.post("/certificates/exchange")
def exchange_certificate(req: CertExchangeReq, user: dict = Depends(get_current_user)):
    """花费绿色能量兑换植树证书。"""
    req.wallet = assert_actor_wallet(user, req.wallet)  # 兑换者身份从 JWT 解析
    # 1. 查找树种信息
    with get_conn() as conn:
        tree = conn.execute(
            "SELECT * FROM eco_tree_species WHERE id=?",
            (req.species_id,),
        ).fetchone()
    if not tree:
        raise HTTPException(404, "树种不存在")
    cost = tree["required_energy"]

    # 2. 查找 GreenEnergy 合约，调用 balanceOf 检查余额
    ge_addr, ge_abi = _find_contract("GreenEnergy")
    if not ge_addr:
        raise HTTPException(400, "GreenEnergy 合约未部署")
    balance = _to_int(_get_energy_balance(req.wallet))
    if balance < cost:
        raise HTTPException(400, f"绿色能量不足，需要 {cost}，当前 {balance}")

    c = get_chain_client()
    admin_addr = c.resolve_account(ADMIN_ALIAS)

    # 2.5 账本 → 链上余额回填（重启后沙盒链余额归零，回填后转账才能真实执行）
    _sync_chain_balance(req.wallet)

    # 3. 调用 GreenEnergy.transfer(admin, cost) 从 wallet 转给 admin
    r_transfer = c.call_contract(
        ge_addr, "transfer",
        [admin_addr, cost],
        req.wallet, ge_abi,
    )
    if not r_transfer.get("ok"):
        raise HTTPException(400, "能量扣除失败: " + str(r_transfer.get("error", "")))

    # 4. 查找 PlantCertificate 合约
    pc_addr, pc_abi = _find_contract("PlantCertificate")
    if not pc_addr:
        raise HTTPException(400, "PlantCertificate 合约未部署")

    # 5. 生成唯一 token_id（uuid 前 32 位整数）
    token_id = uuid.uuid4().int & 0xFFFFFFFF
    uri = f"pc://{token_id}"

    # 6. 调用 PlantCertificate.mint(wallet, token_id, species_id, uri) 从 admin 发起
    r_mint = c.call_contract(
        pc_addr, "mint",
        [c.resolve_account(req.wallet), token_id, req.species_id, uri],
        ADMIN_ALIAS, pc_abi,
    )
    if not r_mint.get("ok"):
        raise HTTPException(400, "证书铸造失败: " + str(r_mint.get("error", "")))
    tx_hash = r_mint.get("tx_hash", "")

    # 7. 生成唯一证书编号 PC-YYYYMMDD-XXXX
    date_str = datetime.now().strftime("%Y%m%d")
    cert_no = f"PC-{date_str}-{uuid.uuid4().hex[:4].upper()}"

    # 8. 记录到 eco_certificates 表
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO eco_certificates(token_id,species_id,species_name,owner,cost_energy,contract_address,tx_hash,cert_no,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (str(token_id), req.species_id, tree["name"], req.wallet, cost,
             pc_addr, tx_hash, cert_no, now()),
        )
    _track(EventType.ECO_CERT_EXCHANGE, target=tree["name"], ref_id=cert_no, wallet=req.wallet,
           extra={"species_id": req.species_id, "cost": cost, "token_id": str(token_id)})
    return {"ok": True, "token_id": str(token_id), "cert_no": cert_no, "tx_hash": tx_hash}


@router.get("/certificates/list")
def list_certificates(owner: str):
    """返回植树证书列表。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM eco_certificates WHERE owner=? ORDER BY id DESC",
            (owner,),
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


# ===========================================================================
# 6. 生态勋章 / 骑行券兑换
# ===========================================================================
@router.post("/badges/exchange")
def exchange_badge(req: BadgeExchangeReq, user: dict = Depends(get_current_user)):
    """居民花费绿色能量兑换生态勋章 / 骑行券（能量转入管理员国库，实现能量回收闭环）。

    与「联盟角色发放」的区别：兑换消耗居民自己的绿色能量（cost_energy），
    铸造（mint）由管理员合约账户执行，普通居民不能自铸。
    """
    req.wallet = assert_actor_wallet(user, req.wallet)  # 兑换者身份从 JWT 解析
    with get_conn() as conn:
        bt = _get_badge_type(conn, type_id=req.type_id, badge_type=req.badge_type)
        if not bt:
            raise HTTPException(400, f"未知勋章类型: {req.badge_type}（type_id={req.type_id}）")
        cost = int(bt["cost_energy"])
        token_id = int(bt["token_id"])
        badge_name = bt["name"]
        bt_id = bt["id"]
        # 发行量上限校验（供应不足则提示等待联盟节点补发）
        if int(bt["minted"]) >= int(bt["supply"]):
            raise HTTPException(400, f"「{badge_name}」发行量已达上限 {bt['supply']}，暂不可兑换")

    # 1. 查找 GreenEnergy 合约，检查余额
    ge_addr, ge_abi = _find_contract("GreenEnergy")
    if not ge_addr:
        raise HTTPException(400, "GreenEnergy 合约未部署")
    balance = _to_int(_get_energy_balance(req.wallet))
    if balance < cost:
        raise HTTPException(400, f"绿色能量不足，需要 {cost}，当前 {balance}")

    c = get_chain_client()
    admin_addr = c.resolve_account(ADMIN_ALIAS)

    # 1.5 账本 → 链上余额回填（重启后沙盒链余额归零，回填后转账才能真实执行）
    _sync_chain_balance(req.wallet)

    # 2. 能量回收：调用 GreenEnergy.transfer(admin, cost) 从 wallet 转给管理员国库
    r_transfer = c.call_contract(
        ge_addr, "transfer",
        [admin_addr, cost],
        req.wallet, ge_abi,
    )
    if not r_transfer.get("ok"):
        raise HTTPException(400, "能量扣除失败: " + str(r_transfer.get("error", "")))

    # 3. 查找 EcoBadge 合约，由管理员合约账户 mint 到居民钱包
    eb_addr, eb_abi = _find_contract("EcoBadge")
    if not eb_addr:
        raise HTTPException(400, "EcoBadge 合约未部署")
    r_mint = c.call_contract(
        eb_addr, "mint",
        [c.resolve_account(req.wallet), token_id, 1, bt["image_url"] or ""],
        ADMIN_ALIAS, eb_abi,
    )
    if not r_mint.get("ok"):
        raise HTTPException(400, "勋章铸造失败: " + str(r_mint.get("error", "")))
    tx_hash = r_mint.get("tx_hash", "")

    # 4. 记录到 eco_badges 表 + 类型已铸数量 +1
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO eco_badges(token_id,badge_type,name,owner,cost_energy,issued_by,contract_address,tx_hash,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (token_id, req.badge_type, badge_name, req.wallet, cost,
             ADMIN_ALIAS, eb_addr, tx_hash, now()),
        )
        conn.execute("UPDATE eco_badge_types SET minted = minted + 1 WHERE id=?", (bt_id,))
    _track(EventType.ECO_BADGE_EXCHANGE, target=badge_name, ref_id=str(token_id), wallet=req.wallet,
           extra={"badge_type": req.badge_type, "type_id": req.type_id, "cost": cost})
    return {"ok": True, "badge_type": req.badge_type, "type_id": bt_id, "tx_hash": tx_hash}


@router.get("/badges/list")
def list_badges(owner: str):
    """返回勋章 / 骑行券列表。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM eco_badges WHERE owner=? ORDER BY id DESC",
            (owner,),
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


# ---------------------------------------------------------------------------
# 6.1 勋章 / 骑行券类型管理（联盟角色铸造入口）
# ---------------------------------------------------------------------------
@router.get("/badges/types")
def list_badge_types():
    """返回全部勋章 / 骑行券类型定义（含发行上限与已铸数量，供兑换 / 铸造界面渲染）。"""
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM eco_badge_types ORDER BY id ASC").fetchall()
    return [dict(r) for r in rows]


@router.post("/badges/types/add")
def add_badge_type(req: BadgeTypeAddReq, user: dict = Depends(get_current_user)):
    """联盟角色新增勋章 / 骑行券类型定义（ERC1155）。

    权限（与实训业务模型一致）：
    - badge 勋章：管理员 + 任意联盟节点均可新增（需先在绿色低碳联盟链选定角色）；
    - voucher 骑行券：仅共享单车公司（bike）可维护（EcoBadge 合约固定 VOUCHER_ID=2，仅允许一份）。
    """
    req.wallet = assert_actor_wallet(user, req.wallet)  # 操作者身份从 JWT 解析
    if req.badge_type not in ("badge", "voucher"):
        raise HTTPException(400, "badge_type 必须是 badge 或 voucher")
    if req.cost_energy <= 0:
        raise HTTPException(400, "所需能量值必须大于 0")
    if req.supply <= 0:
        raise HTTPException(400, "发行数量（supply）必须大于 0")

    role = _selected_role(req.wallet)
    if not role:
        raise HTTPException(403, "操作者未选择联盟角色：请先在「绿色低碳联盟链」页面选择角色后再新增")
    if req.badge_type == "voucher":
        ensure_bike_for_voucher(role["key"], action="add")

    with get_conn() as conn:
        if req.badge_type == "voucher":
            # 骑行券固定 token_id=2，仅维护一份
            exist = conn.execute(
                "SELECT id FROM eco_badge_types WHERE badge_type='voucher' ORDER BY id ASC LIMIT 1"
            ).fetchone()
            if exist:
                conn.execute(
                    "UPDATE eco_badge_types SET name=?, icon=?, image_url=?, cost_energy=?, "
                    "supply=?, issuer_role=?, desc=? WHERE id=?",
                    (req.name, req.icon, req.image_url, req.cost_energy, req.supply,
                     role["key"], req.desc, exist["id"]),
                )
                return {"ok": True, "id": exist["id"], "updated": True,
                        "token_id": 2, "badge_type": "voucher"}
            token_id = 2
        else:
            # 新勋章类型：token_id 自增（避开内置 BADGE_ID=1 / VOUCHER_ID=2）
            max_id = conn.execute(
                "SELECT COALESCE(MAX(token_id), 0) FROM eco_badge_types WHERE badge_type='badge'"
            ).fetchone()[0]
            token_id = max_id + 1
            if token_id <= 1:
                token_id = 3 if max_id == 1 else max_id + 1
            # 避开 VOUCHER_ID=2 与 BADGE_ID=1 冲突
            while token_id in (1, 2):
                token_id += 1
        cur = conn.execute(
            "INSERT INTO eco_badge_types(badge_type,name,icon,image_url,cost_energy,supply,"
            "minted,issuer_role,token_id,desc,created_at) VALUES(?,?,?,?,?,?,0,?,?,?,?)",
            (req.badge_type, req.name, req.icon, req.image_url, req.cost_energy,
             req.supply, role["key"], token_id, req.desc, now()),
        )
    _track(EventType.BADGE_TYPE_ADD, target=req.badge_type, wallet=req.wallet or "",
           extra={"type_id": cur.lastrowid, "issuer_role": role["key"]})
    return {"ok": True, "id": cur.lastrowid, "token_id": token_id, "badge_type": req.badge_type}


@router.post("/badges/mint")
def mint_badge(req: BadgeMintReq, user: dict = Depends(get_current_user)):
    """联盟角色铸造发放勋章 / 骑行券给居民（ERC1155 mint，链上 FROM = 联盟角色钱包）。

    与「居民兑换」的区别（业务闭环的两条链路）：
    - 兑换（/badges/exchange）：居民花费自己的绿色能量，由管理员合约账户铸造，能量回收；
    - 铸造发放（本接口）：联盟节点运营行为直接向居民发放，不消耗居民能量（如企业激励）。

    权限：操作者必须先选择联盟角色；voucher 仅共享单车公司（bike）可发放。
    """
    role = _find_role(req.role_key)
    if not role:
        raise HTTPException(400, f"未知角色: {req.role_key}")
    req.wallet = assert_actor_wallet(user, req.wallet)  # 操作者身份从 JWT 解析
    if not req.wallet:
        raise HTTPException(400, "操作者钱包 wallet 必填")
    if req.quantity <= 0:
        raise HTTPException(400, "铸造数量必须大于 0")

    # 权限：操作者当前选中角色必须与声明一致（普通居民无铸造能力）
    ensure_minter_role(role, _selected_role(req.wallet))
    if not req.to_wallet:
        raise HTTPException(400, "接收者钱包 to_wallet 必填")

    with get_conn() as conn:
        bt = _get_badge_type(conn, type_id=req.type_id)
    if not bt:
        raise HTTPException(400, f"未知勋章类型 type_id={req.type_id}")
    # 权限矩阵校验：骑行券仅 bike；生态勋章需角色具备 can_issue_badge 权限位（如管理员无铸造权）
    if bt["badge_type"] == "voucher":
        ensure_bike_for_voucher(role["key"], action="mint")
    elif not role.get("can_issue_badge"):
        raise HTTPException(
            403,
            f"角色【{role['name']}】不具备勋章铸造权限位：can_issue_badge，"
            f"请切换到具备铸造权的联盟业务角色",
        )
    remaining = int(bt["supply"]) - int(bt["minted"])
    if int(req.quantity) > remaining:
        raise HTTPException(
            400,
            f"「{bt['name']}」发行量上限 {bt['supply']}，已铸造 {bt['minted']}，"
            f"剩余可铸造 {remaining}，本次请求 {req.quantity}",
        )

    eb_addr, eb_abi = _find_contract("EcoBadge")
    if not eb_addr:
        raise HTTPException(400, "EcoBadge 合约未部署")

    c = get_chain_client()
    issuer_wallet = role.get("wallet") or f"0x{role['key']}"
    r = c.call_contract(
        eb_addr, "mint",
        [c.resolve_account(req.to_wallet), int(bt["token_id"]), int(req.quantity),
         bt["image_url"] or ""],
        issuer_wallet, eb_abi,
    )
    if not r.get("ok"):
        raise HTTPException(400, f"铸造失败（交易发起方 {issuer_wallet}）: {r.get('error','')}")
    tx_hash = r.get("tx_hash", "")

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO eco_badges(token_id,badge_type,name,owner,cost_energy,issued_by,"
            "contract_address,tx_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (int(bt["token_id"]), bt["badge_type"], bt["name"], req.to_wallet, 0,
             issuer_wallet, eb_addr, tx_hash, now()),
        )
        conn.execute(
            "UPDATE eco_badge_types SET minted = minted + ? WHERE id=?",
            (int(req.quantity), bt["id"]),
        )
    _track(EventType.BADGE_MINT, target=bt["badge_type"], wallet=req.wallet or "",
           extra={"type_id": bt["id"], "to": req.to_wallet, "qty": req.quantity,
                  "issued_by": issuer_wallet})
    return {"ok": True, "badge_type": bt["badge_type"], "type_id": bt["id"],
            "to": req.to_wallet, "quantity": int(req.quantity), "tx_hash": tx_hash}


# ===========================================================================
# 7. 操作错误/行为记录（供实训报告做打分与错误分析）
# ===========================================================================
@router.post("/errors/record")
def record_error(req: OpErrorRecordReq, user: dict = Depends(get_current_user)):
    """前端在操作成功/失败时都可写入审计记录，level=success/info/warn/error。"""
    req.wallet = assert_actor_wallet(user, req.wallet)  # 审计归属以登录身份为准
    if req.level not in ("info", "success", "warn", "error"):
        raise HTTPException(400, "level 非法")
    if req.module not in ("role", "energy", "tree", "certificate", "badge", "contract", "other"):
        raise HTTPException(400, "module 非法")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO eco_operation_logs(wallet,module,action,level,message,detail,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (req.wallet, req.module, req.action, req.level,
             req.message[:500], req.detail[:2000], now()),
        )
    return {"ok": True, "id": cur.lastrowid}


@router.get("/errors/list")
def list_errors(wallet: str = "", limit: int = 200):
    """查询操作日志。传 wallet 过滤，不传返回全部（教师汇总）。"""
    with get_conn() as conn:
        if wallet:
            rows = conn.execute(
                "SELECT * FROM eco_operation_logs WHERE wallet=? ORDER BY id DESC LIMIT ?",
                (wallet, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM eco_operation_logs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    items = [dict(r) for r in rows]
    total = len(items)
    errors = sum(1 for i in items if i.get("level") == "error")
    warns = sum(1 for i in items if i.get("level") == "warn")
    success = sum(1 for i in items if i.get("level") == "success")
    return {
        "items": items,
        "total": total,
        "error_count": errors,
        "warn_count": warns,
        "success_count": success,
    }


# ===========================================================================
# 8. 综合钱包查询
# ===========================================================================
@router.get("/wallet/{wallet}")
def wallet_profile(wallet: str):
    """综合查询钱包的角色、能量余额、能量记录、证书、勋章、骑行券。"""
    with get_conn() as conn:
        role_row = conn.execute(
            "SELECT role_key FROM eco_role_selections WHERE wallet=?",
            (wallet,),
        ).fetchone()
        role = _find_role(role_row["role_key"]) if role_row else None

        energy_rows = conn.execute(
            "SELECT * FROM eco_energy_records WHERE wallet=? ORDER BY id DESC LIMIT 50",
            (wallet,),
        ).fetchall()

        cert_rows = conn.execute(
            "SELECT * FROM eco_certificates WHERE owner=? ORDER BY id DESC",
            (wallet,),
        ).fetchall()

        badge_rows = conn.execute(
            "SELECT * FROM eco_badges WHERE owner=? AND badge_type='badge' ORDER BY id DESC",
            (wallet,),
        ).fetchall()

        voucher_rows = conn.execute(
            "SELECT * FROM eco_badges WHERE owner=? AND badge_type='voucher' ORDER BY id DESC",
            (wallet,),
        ).fetchall()

    return {
        "wallet": wallet,
        "role": role,
        "energy_balance": _get_energy_balance(wallet),
        "energy_records": [dict(r) for r in energy_rows],
        "certificates": [dict(r) for r in cert_rows],
        "badges": [dict(r) for r in badge_rows],
        "vouchers": [dict(r) for r in voucher_rows],
    }


# ===========================================================================
# 9. 绿色资产交易市场（挂牌 / 购买 / 查询 / 取消）
#    植树证书(ERC721) / 生态勋章(ERC1155) / 骑行券(ERC1155) 均可在市场挂牌交易
#    交易媒介：GreenEnergy 绿色能量代币（ERC20）
# ===========================================================================

class MarketListReq(BaseModel):
    seller: str
    asset_type: str          # certificate | badge | voucher
    asset_id: int             # eco_certificates.id 或 eco_badges.id
    price_energy: int         # 挂牌价格（绿色能量）


@router.post("/market/list")
def market_list(req: MarketListReq, user: dict = Depends(get_current_user)):
    """挂牌绿色资产。校验资产归属 → 写入 eco_market_listings。"""
    req.seller = assert_actor_wallet(user, req.seller, "seller")  # 卖家身份从 JWT 解析
    if req.asset_type not in ("certificate", "badge", "voucher"):
        raise HTTPException(400, "asset_type 必须是 certificate/badge/voucher")
    if req.price_energy <= 0:
        raise HTTPException(400, "价格必须大于 0")

    # 查资产并校验归属
    if req.asset_type == "certificate":
        with get_conn() as conn:
            row = conn.execute(
                "SELECT id, token_id, species_name, owner, contract_address FROM eco_certificates WHERE id=?",
                (req.asset_id,),
            ).fetchone()
        if not row:
            raise HTTPException(404, "证书不存在")
        ensure_asset_owner(row["owner"], req.seller)
        asset_name = f"植树证书 · {row['species_name']}"
        token_id = row["token_id"]
        contract_addr = row["contract_address"]
        standard = "ERC721"
    else:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT id, token_id, badge_type, name, owner, contract_address FROM eco_badges WHERE id=?",
                (req.asset_id,),
            ).fetchone()
        if not row:
            raise HTTPException(404, "资产不存在")
        ensure_asset_owner(row["owner"], req.seller)
        asset_name = row["name"]
        token_id = str(row["token_id"])
        contract_addr = row["contract_address"]
        standard = "ERC1155"

    # 检查是否已在售
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM eco_market_listings WHERE asset_type=? AND asset_id=? AND status='active'",
            (req.asset_type, req.asset_id),
        ).fetchone()
    if existing:
        raise HTTPException(400, "该资产已在市场中挂牌")

    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO eco_market_listings(seller,asset_type,asset_id,asset_name,token_id,contract_address,standard,price_energy,status,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,'active',?)",
            (req.seller, req.asset_type, req.asset_id, asset_name, token_id,
             contract_addr, standard, req.price_energy, now()),
        )
        listing_id = cur.lastrowid
    return {"ok": True, "listing_id": listing_id, "asset_name": asset_name, "price": req.price_energy}


def _listing_image(conn, listing: dict) -> str:
    """回填挂牌卡片图片：证书→树种图；勋章/骑行券→类型图（缺失返回空串，前端降级为图标）。"""
    try:
        if listing.get("asset_type") == "certificate":
            row = conn.execute(
                "SELECT ts.image_url FROM eco_certificates c "
                "JOIN eco_tree_species ts ON ts.name = c.species_name WHERE c.id=?",
                (listing.get("asset_id"),),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT image_url FROM eco_badge_types WHERE token_id=CAST(? AS INTEGER)",
                (listing.get("token_id"),),
            ).fetchone()
        return (row["image_url"] or "") if row else ""
    except Exception:
        return ""


@router.get("/market/items")
def market_items(asset_type: str = "", seller: str = ""):
    """查询市场在售绿色资产。可选按类型/卖家过滤。"""
    sql = "SELECT * FROM eco_market_listings WHERE status='active'"
    params: list = []
    if asset_type:
        sql += " AND asset_type=?"
        params.append(asset_type)
    if seller:
        sql += " AND seller=?"
        params.append(seller)
    sql += " ORDER BY created_at DESC"
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        items = []
        for r in rows:
            d = dict(r)
            d["image_url"] = _listing_image(conn, d)
            items.append(d)
    return {"items": items}


@router.get("/market/trades")
def market_trades(limit: int = 100):
    """绿色资产市场已成交记录（status='sold'，权威数据源）：市场页交易时间线据此展示，
    跨钱包/浏览器可见，不依赖浏览器本地缓存。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM eco_market_listings WHERE status='sold' ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


class MarketBuyReq(BaseModel):
    buyer: str
    listing_id: int


@router.post("/market/buy")
def market_buy(req: MarketBuyReq, user: dict = Depends(get_current_user)):
    """购买绿色资产：GreenEnergy 转账(买方→卖方) + NFT 转移(卖方→买方)。"""
    req.buyer = assert_actor_wallet(user, req.buyer, "buyer")  # 买家身份从 JWT 解析
    with get_conn() as conn:
        listing = conn.execute(
            "SELECT * FROM eco_market_listings WHERE id=? AND status='active'",
            (req.listing_id,),
        ).fetchone()
    if not listing:
        raise HTTPException(404, "挂牌资产不存在或已售出")
    if listing["seller"] == req.buyer:
        raise HTTPException(400, "不能购买自己的资产")

    price = listing["price_energy"]
    seller = listing["seller"]
    buyer = req.buyer
    c = get_chain_client()

    # 1. 校验买方 GreenEnergy 余额
    ge_addr, ge_abi = _find_contract("GreenEnergy")
    if not ge_addr:
        raise HTTPException(400, "GreenEnergy 合约未部署")
    # 余额口径：先同步账本→链上，再以链上 balanceOf 为唯一事实源校验购买力
    _sync_chain_balance(buyer)
    bal_r = c.call_contract(ge_addr, "balanceOf", [c.resolve_account(buyer)], buyer, ge_abi)
    if not bal_r.get("ok"):
        raise HTTPException(400, "余额查询失败")
    bal = _to_int(bal_r.get("result", "0"))
    if bal < price:
        raise HTTPException(400, f"绿色能量不足：需要 {price}，当前 {bal}")

    # 2. GreenEnergy 转账：买方 → 卖方
    r_pay = c.call_contract(ge_addr, "transfer",
                            [c.resolve_account(seller), price], buyer, ge_abi)
    if not r_pay.get("ok"):
        raise HTTPException(400, "能量支付失败: " + str(r_pay.get("error", "")))
    pay_tx = r_pay.get("tx_hash", "")

    # 3. NFT 转移：卖方 → 买方
    nft_abi = _load_abi(listing["contract_address"])
    if not nft_abi:
        raise HTTPException(400, "NFT 合约 ABI 未找到")
    token_id_int = int(listing["token_id"])
    if listing["standard"] == "ERC721":
        r_nft = c.call_contract(listing["contract_address"], "transferFrom",
                                [c.resolve_account(seller), c.resolve_account(buyer), token_id_int],
                                seller, nft_abi)
    else:
        r_nft = c.call_contract(listing["contract_address"], "safeTransferFrom",
                                [c.resolve_account(seller), c.resolve_account(buyer), token_id_int, 1],
                                seller, nft_abi)
    if not r_nft.get("ok"):
        raise HTTPException(400, "NFT 转移失败: " + str(r_nft.get("error", "")))
    nft_tx = r_nft.get("tx_hash", pay_tx)

    # 4. 更新数据：标记售出 + 转移资产归属
    with get_conn() as conn:
        conn.execute(
            "UPDATE eco_market_listings SET status='sold', buyer=?, tx_hash=? WHERE id=?",
            (buyer, nft_tx, req.listing_id),
        )
        if listing["asset_type"] == "certificate":
            conn.execute("UPDATE eco_certificates SET owner=? WHERE id=?", (buyer, listing["asset_id"]))
        else:
            conn.execute("UPDATE eco_badges SET owner=? WHERE id=?", (buyer, listing["asset_id"]))

    return {
        "ok": True,
        "pay_tx": pay_tx,
        "nft_tx": nft_tx,
        "asset_name": listing["asset_name"],
        "price": price,
    }


@router.post("/market/cancel")
def market_cancel(payload: dict, user: dict = Depends(get_current_user)):
    """取消挂牌（仅卖家本人）。"""
    listing_id = payload.get("listing_id")
    seller = assert_actor_wallet(user, payload.get("seller"), "seller")  # 卖家身份从 JWT 解析
    with get_conn() as conn:
        row = conn.execute(
            "SELECT seller, status FROM eco_market_listings WHERE id=?",
            (listing_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "挂牌记录不存在")
        if row["seller"] != seller:
            raise HTTPException(403, "只能取消自己的挂牌")
        if row["status"] != "active":
            raise HTTPException(400, "该资产已售出或已取消")
        conn.execute("UPDATE eco_market_listings SET status='cancelled' WHERE id=?", (listing_id,))
    return {"ok": True}


def _load_abi(address: str):
    """从 deployed_contracts 表加载合约 ABI。"""
    with get_conn() as conn:
        r = conn.execute("SELECT abi FROM deployed_contracts WHERE address=?", (address,)).fetchone()
    return json.loads(r["abi"]) if r else []


# ===========================================================================
# 8. 监管审计视角（全链只读聚合，无副作用）
# ===========================================================================
@router.get("/audit/overview")
def audit_overview(user: dict = Depends(get_current_user)):
    """以「监管审计方」身份聚合全链只读指标。

    - 当前块高：get_chain_client().block_number()，链不可用时返回 null（不抛错、不降级发交易）
    - 异常调用明细：contract_calls 中 status=0 / reverted / failed 等非 success 的最近若干条
    - 各角色发放总量对比：eco_energy_records 按 role_key 聚合（含零发放角色，便于横向对比）

    严格只读：不写任何表、不发起任何链上交易。
    """
    # 1. 当前块高（链不可用 / 未初始化时静默降级；mock 空链返回 -1，规整为 null）
    height = None
    try:
        height = int(get_chain_client().block_number())
    except Exception:
        height = None
    if height is not None and height < 0:
        height = None
    with get_conn() as conn:
        calls_total = conn.execute("SELECT COUNT(*) FROM contract_calls").fetchone()[0] or 0
        calls_ok = conn.execute(
            "SELECT COUNT(*) FROM contract_calls WHERE lower(COALESCE(status,'')) IN ('success','1')",
        ).fetchone()[0] or 0
        abn_rows = conn.execute(
            "SELECT id, contract_address, method, caller, tx_hash, block_number, status, result, created_at "
            "FROM contract_calls WHERE lower(COALESCE(status,'')) NOT IN ('success','1') "
            "ORDER BY id DESC LIMIT 20",
        ).fetchall()
        abn_count = conn.execute(
            "SELECT COUNT(*) FROM contract_calls WHERE lower(COALESCE(status,'')) NOT IN ('success','1')",
        ).fetchone()[0] or 0
        tx_total = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] or 0
        er_rows = conn.execute(
            "SELECT role_key, COUNT(*) AS issue_count, COALESCE(SUM(points),0) AS total_points, "
            "MAX(created_at) AS last_issued_at FROM eco_energy_records GROUP BY role_key",
        ).fetchall()
    er_map = {r["role_key"]: dict(r) for r in er_rows}
    role_items: list = []
    seen: set = set()
    # 六个联盟角色固定输出（含零发放），保证对比口径稳定
    for r in ROLES:
        seen.add(r["key"])
        agg = er_map.get(r["key"]) or {}
        role_items.append({
            "role_key": r["key"], "role_name": r["name"], "icon": r["icon"], "color": r["color"],
            "issue_count": int(agg.get("issue_count") or 0),
            "total_points": int(agg.get("total_points") or 0),
            "last_issued_at": agg.get("last_issued_at") or "",
        })
    # 历史遗留 role_key（如 delivery）不在 ROLES 中时也如实展示，审计口径不丢数据
    for rk, agg in er_map.items():
        if rk in seen:
            continue
        role_items.append({
            "role_key": rk, "role_name": rk, "icon": "🌿", "color": "#7b8aab",
            "issue_count": int(agg.get("issue_count") or 0),
            "total_points": int(agg.get("total_points") or 0),
            "last_issued_at": agg.get("last_issued_at") or "",
        })
    rate = round(int(calls_ok) * 100.0 / int(calls_total), 1) if calls_total else 100.0
    # 截断超长 result / 错误详情，避免审计列表被大文本撑爆
    abn_items = []
    for r in abn_rows:
        d = dict(r)
        if d.get("result") and len(str(d["result"])) > 160:
            d["result"] = str(d["result"])[:160] + "…"
        abn_items.append(d)
    return {
        "generated_at": now(),
        "block_height": height,
        "calls": {
            "total": int(calls_total),
            "success": int(calls_ok),
            "failed": int(calls_total) - int(calls_ok),
            "success_rate": rate,
        },
        "transactions_total": int(tx_total),
        "abnormal_calls": {"count": int(abn_count), "items": abn_items},
        "role_energy": {
            "items": role_items,
            "total_points": sum(i["total_points"] for i in role_items),
            "total_issue_count": sum(i["issue_count"] for i in role_items),
        },
    }


# ===========================================================================
# 数据库初始化
# ===========================================================================
def _ensure_column(conn: Any, table: str, col: str, definition: str):
    """SQLite 安全加列：列不存在时才 ALTER TABLE，避免重启报错。"""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    cols = {r["name"] for r in rows}
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")


def init_eco_db():
    """初始化 eco 模块数据库表，并保证向后兼容（新增列自动迁移）。"""
    with get_conn() as conn:
        # 角色选择记录
        conn.execute("""
        CREATE TABLE IF NOT EXISTS eco_role_selections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet TEXT NOT NULL,
            role_key TEXT NOT NULL,
            selected_at TEXT NOT NULL,
            UNIQUE(wallet)
        )""")
        # 绿色能量发放记录
        conn.execute("""
        CREATE TABLE IF NOT EXISTS eco_energy_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet TEXT NOT NULL,
            role_key TEXT NOT NULL,
            role_name TEXT NOT NULL,
            action TEXT NOT NULL,
            points INTEGER NOT NULL,
            tx_hash TEXT,
            created_at TEXT NOT NULL
        )""")
        # 能量发放记录：新增业务凭证溯源字段（链下订单 → 链上能量映射）
        _ensure_column(conn, "eco_energy_records", "issuer_wallet",
                       "TEXT NOT NULL DEFAULT ''")   # 发放者钱包（联盟角色，不是接收者）
        _ensure_column(conn, "eco_energy_records", "proof_no",
                       "TEXT NOT NULL DEFAULT ''")   # 业务单号（地铁乘车号/外卖订单号/回收单号）
        _ensure_column(conn, "eco_energy_records", "proof_payload",
                       "TEXT")                       # 业务凭证 JSON 原文（含距离/时长/重量等）
        _ensure_column(conn, "eco_energy_records", "proof_validated",
                       "INTEGER NOT NULL DEFAULT 0")  # 1=通过校验 0=force跳过或未校验
        _ensure_column(conn, "eco_energy_records", "proof_threshold",
                       "TEXT NOT NULL DEFAULT ''")   # 校验阈值（如 distance_km ≥ 10 km）
        # 建唯一索引防刷：同一业务单号 + 同一发放角色不允许重复发能量
        try:
            conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_energy_proof_role
            ON eco_energy_records(proof_no, role_key)
            """)
        except Exception:
            pass  # 旧版本 SQLite 兼容
        # 树种
        conn.execute("""
        CREATE TABLE IF NOT EXISTS eco_tree_species (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            required_energy INTEGER NOT NULL,
            image_url TEXT,
            description TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        # 植树证书
        conn.execute("""
        CREATE TABLE IF NOT EXISTS eco_certificates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_id TEXT NOT NULL,
            species_id INTEGER NOT NULL,
            species_name TEXT NOT NULL,
            owner TEXT NOT NULL,
            cost_energy INTEGER NOT NULL,
            contract_address TEXT,
            tx_hash TEXT,
            cert_no TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        # 生态勋章 / 骑行券
        conn.execute("""
        CREATE TABLE IF NOT EXISTS eco_badges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_id INTEGER NOT NULL,
            badge_type TEXT NOT NULL,
            name TEXT NOT NULL,
            owner TEXT NOT NULL,
            cost_energy INTEGER NOT NULL,
            issued_by TEXT,
            contract_address TEXT,
            tx_hash TEXT,
            created_at TEXT NOT NULL
        )""")
        # 操作日志（成功 / 失败 / 警告，供实训报告打分与错误分析）
        conn.execute("""
        CREATE TABLE IF NOT EXISTS eco_operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet TEXT NOT NULL,
            module TEXT NOT NULL,       -- role | energy | tree | certificate | badge | contract | other
            action TEXT NOT NULL,       -- 操作动作
            level TEXT NOT NULL,        -- info | success | warn | error
            message TEXT NOT NULL,      -- 简短描述
            detail TEXT,                -- 详细错误 / 堆栈
            created_at TEXT NOT NULL
        )""")
        # 绿色资产交易市场（挂牌记录）
        conn.execute("""
        CREATE TABLE IF NOT EXISTS eco_market_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller TEXT NOT NULL,
            asset_type TEXT NOT NULL,       -- certificate | badge | voucher
            asset_id INTEGER NOT NULL,       -- eco_certificates.id 或 eco_badges.id
            asset_name TEXT NOT NULL,
            token_id TEXT NOT NULL,
            contract_address TEXT,
            standard TEXT NOT NULL,          -- ERC721 | ERC1155
            price_energy INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',  -- active | sold | cancelled
            buyer TEXT,
            tx_hash TEXT,
            created_at TEXT NOT NULL
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_market_status ON eco_market_listings(status)")
        # 勋章 / 骑行券类型（发行量上限、铸造方角色、兑换成本）
        conn.execute("""
        CREATE TABLE IF NOT EXISTS eco_badge_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            badge_type TEXT NOT NULL,          -- badge | voucher
            name TEXT NOT NULL,
            icon TEXT,
            image_url TEXT,
            cost_energy INTEGER NOT NULL DEFAULT 0,
            supply INTEGER NOT NULL DEFAULT 0, -- 发行数量上限
            minted INTEGER NOT NULL DEFAULT 0, -- 已铸造数量
            issuer_role TEXT NOT NULL DEFAULT '', -- 铸造方联盟角色（空=全体）
            token_id INTEGER NOT NULL,
            desc TEXT,
            created_at TEXT NOT NULL
        )""")
        # 默认勋章 / 骑行券类型播种（仅当表为空时插入，避免重复）
        bt_count = conn.execute("SELECT COUNT(*) FROM eco_badge_types").fetchone()[0]
        if bt_count == 0:
            for bt in DEFAULT_BADGE_TYPES:
                conn.execute(
                    "INSERT INTO eco_badge_types(badge_type,name,icon,image_url,cost_energy,supply,"
                    "minted,issuer_role,token_id,desc,created_at) VALUES(?,?,?,?,?,?,0,?,?,?,?)",
                    (bt["badge_type"], bt["name"], bt["icon"], bt["image_url"], bt["cost_energy"],
                     bt["supply"], bt["issuer_role"], bt["token_id"], bt["desc"], now()),
                )
