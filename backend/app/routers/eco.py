"""生态联盟链高级实战模块 API。

六个联盟节点（管理员 / 地铁 / 公交 / 共享单车 / 外卖 / 回收）协同运营，
基于 GreenEnergy（ERC20）、PlantCertificate（ERC721）、EcoBadge（ERC1155）
三个合约实现绿色能量发放、植树证书兑换、生态勋章/骑行券兑换全流程。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..chain_client import get_chain_client
from ..db import get_conn, now
from ..tx_decoder import compile_source


def _track(event_type: str, target: str = "", ref_id: str = "", wallet: str = "", extra: dict | None = None):
    """轻量学习行为埋点，写入 learning_events（不阻塞主流程）。"""
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO learning_events(wallet,event_type,target,ref_id,extra,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (wallet, event_type, target, ref_id,
                 json.dumps(extra or {}, ensure_ascii=False), now()),
            )
    except Exception:
        pass

router = APIRouter(prefix="/api/eco", tags=["eco"])

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
                     "proof_example": '{"line":"1号线","distance_km":12,"trip_no":"BJ202608070001"}'},
     "can_issue_badge": True, "can_issue_voucher": False, "can_manage_trees": False},
    {"key": "bus",      "name": "公交集团", "icon": "🚌", "color": "#ffcf4d", "wallet": "0xbus",
     "desc": "城市公交运营方，乘坐公交(≥5分钟)发放20点绿色能量",
     "energy_rule": {"action": "公交出行", "points": 20, "proof_field": "ride_minutes", "min": 5, "unit": "min",
                     "proof_no_field": "trip_no",   # 业务单号：公交乘车号
                     "proof_example": '{"route":"86路","ride_minutes":20,"trip_no":"BUS20260807001"}'},
     "can_issue_badge": True, "can_issue_voucher": False, "can_manage_trees": False},
    {"key": "bike",     "name": "共享单车", "icon": "🚲", "color": "#f5379b", "wallet": "0xbike",
     "desc": "共享单车运营方，骑行(≥2km)发放15点能量，可发放骑行券",
     "energy_rule": {"action": "共享单车骑行", "points": 15, "proof_field": "distance_km", "min": 2, "unit": "km",
                     "proof_no_field": "order_id",  # 业务单号：单车订单号
                     "proof_example": '{"order_id":"BK2026080701234","distance_km":3.2,"duration_min":15}'},
     "can_issue_badge": True, "can_issue_voucher": True, "can_manage_trees": False},
    {"key": "takeout",  "name": "外卖平台", "icon": "📦", "color": "#ff7849", "wallet": "0xtakeout",
     "desc": "绿色外卖服务平台，选择「无需餐具」发放10点绿色能量",
     "energy_rule": {"action": "绿色外卖(无需餐具)", "points": 10, "proof_field": "no_cutlery", "min": 1, "unit": "flag",
                     "proof_no_field": "order_id",  # 业务单号：外卖订单号（同一订单不重复发）
                     "proof_example": '{"order_id":"MT2026080700123","no_cutlery":true,"platform_order":"ELM2026080701"}'},
     "can_issue_badge": True, "can_issue_voucher": False, "can_manage_trees": False},
    {"key": "recycling","name": "回收公司", "icon": "♻️", "color": "#52c41a", "wallet": "0xrecycle",
     "desc": "旧物回收公司，回收(≥1kg)发放100点绿色能量",
     "energy_rule": {"action": "可回收物回收", "points": 100, "proof_field": "weight_kg", "min": 1, "unit": "kg",
                     "proof_no_field": "order_no",  # 业务单号：回收单号（同一回收不重复发）
                     "proof_example": '{"order_id":"RC20260807001","weight_kg":2.5,"category":"塑料瓶"}'},
     "can_issue_badge": True, "can_issue_voucher": False, "can_manage_trees": False},
]

# 角色别名兼容：前端若传 'delivery' 旧 key，自动映射到 'takeout'
ROLE_ALIAS = {
    "delivery":  "takeout",     # 旧 key（可能前端/脚本残留） → 新 key takeout
    "recycle":   "recycling",   # 兼容缩写：recycle 是 wallet 别名，ROLES.key 是 recycling
}

# 内置合约清单（名称与 deployed_contracts.name 对应）
BUILTIN_CONTRACTS = [
    {"name": "GreenEnergy",      "standard": "ERC20",   "file": "GreenEnergy.sol"},
    {"name": "PlantCertificate", "standard": "ERC721",  "file": "PlantCertificate.sol"},
    {"name": "EcoBadge",         "standard": "ERC1155", "file": "EcoBadge.sol"},
]

# 勋章 / 骑行券配置：EcoBadge 合约中 BADGE_ID=1, VOUCHER_ID=2
BADGE_CONFIG = {
    "badge":   {"cost": 10, "token_id": 1, "name": "生态勋章"},
    "voucher": {"cost": 20, "token_id": 2, "name": "骑行券"},
}

# 管理员别名 —— 兑换时能量消耗回收目标
ADMIN_ALIAS = "0xadmin"


# ===========================================================================
# 请求模型
# ===========================================================================
class RoleSelectReq(BaseModel):
    wallet: str
    role_key: str


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
    badge_type: str  # badge | voucher


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

    该口径可在后端重启后保持稳定，避免 py-evm 内存链重置导致页面余额归零。
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
    """查询钱包绿色能量余额。

    优先使用持久化业务账本，保证重启后钱包与资产市场仍然一致；如果账本没有记录，
    再尝试读取链上 GreenEnergy.balanceOf 作为补充。
    """
    ledger_balance = _get_energy_ledger_balance(wallet)
    if ledger_balance > 0:
        return str(ledger_balance)
    addr, abi = _find_contract("GreenEnergy")
    if not addr:
        return str(ledger_balance)
    c = get_chain_client()
    try:
        r = c.call_contract(addr, "balanceOf", [c.resolve_account(wallet)], wallet, abi)
        if not r.get("ok"):
            return str(ledger_balance)
        return str(r.get("result") or ledger_balance)
    except Exception:
        return str(ledger_balance)


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
def select_role(req: RoleSelectReq):
    """选择 / 切换联盟节点角色（INSERT OR REPLACE）。"""
    if not _find_role(req.role_key):
        raise HTTPException(400, f"未知角色: {req.role_key}")
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO eco_role_selections(wallet, role_key, selected_at) VALUES(?,?,?)",
            (req.wallet, req.role_key, now()),
        )
    # 行为埋点：学生切换联盟角色（对应 alliance_gov 维度的 eco_role_switch 指标）
    _track("eco_role_switch", target=req.role_key, wallet=req.wallet or "",
           extra={"role_key": req.role_key})
    return {"ok": True, "role": _find_role(req.role_key)}


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
    return {"role_key": row["role_key"], "role": _find_role(row["role_key"])}


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
def deploy_builtin_contract(req: ContractDeployReq):
    """一键编译 + 部署内置绿色合约。

    流程：读取源码 → solc 编译 → 调用 EVM 部署 → 写入 deployed_contracts 表。
    若该合约已部署，则重新部署并覆盖旧记录（保留最新地址）。
    """
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
@router.post("/energy/issue")
def issue_energy(req: EnergyIssueReq):
    """根据角色规则发放绿色能量（调用 GreenEnergy.mint）。

    真实业务逻辑（与实训业务模型一致）：
    1. 调用者必须是联盟角色钱包（0xmetro / 0xbus / 0xbike / 0xtakeout / 0xrecycle）—— FROM 是发放方钱包，不是接收方！
    2. 必须提供对应业务凭证（乘车里程 / 时长 / 外卖订单 / 回收重量），并通过阈值校验
    3. 同一业务单号 + 同一发放角色不允许重复发能量（UNIQUE 防刷）
    4. 写入链上 + 写入业务账本，双写一致

    force=True 可跳过校验（教师演示用），但记录中会标记 proof_validated=0。
    """
    role = _find_role(req.role_key)
    if not role:
        raise HTTPException(400, f"未知角色: {req.role_key}")
    rule = role.get("energy_rule")
    if not rule:
        raise HTTPException(400, f"角色 [{role['name']}] 没有能量发放规则")
    issuer_wallet = role.get("wallet") or f"0x{role['key']}"
    if not req.wallet:
        raise HTTPException(400, "接收能量的钱包 wallet 必填")

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
            "issued_by": issuer_wallet, "received_by": req.wallet,
        }

    # 3. 调用 GreenEnergy.mint(receiver, value, action)
    # ⚠️ 真实业务：FROM = 发放方联盟角色钱包（0xmetro 等），不是接收者 req.wallet！
    r = c.call_contract(
        ge_addr, "mint",
        [c.resolve_account(req.wallet), points, action],
        issuer_wallet, ge_abi,
    )
    if not r.get("ok"):
        raise HTTPException(400, f"能量发放失败（合约调用 by {issuer_wallet}）: {r.get('error','')}")
    tx_hash = r.get("tx_hash", "")

    # 4. 写入业务账本（含新增 5 列溯源字段）
    with get_conn() as conn:
        try:
            conn.execute(
                """INSERT INTO eco_energy_records(
                    wallet, role_key, role_name, action, points, tx_hash, created_at,
                    issuer_wallet, proof_no, proof_payload, proof_validated, proof_threshold
                ) VALUES(?,?,?,?,?,?, ?,?,?,?,?,?)""",
                (
                    req.wallet, role["key"], role["name"], action, points, tx_hash, now(),
                    issuer_wallet,
                    proof_no,
                    json.dumps(proof, ensure_ascii=False) if proof else None,
                    1 if (pr["ok"] and not req.force) else 0,
                    pr.get("threshold") or "",
                ),
            )
        except Exception as e:
            # UNIQUE 命中了上面的防刷查询漏掉的并发情况
            if "UNIQUE" in str(e).upper() or "unique" in str(e):
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
                        "issued_by": issuer_wallet, "received_by": req.wallet,
                    }
            raise

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
        "issued_by": issuer_wallet,       # 发放方联盟角色钱包（链上 FROM）
        "received_by": req.wallet,        # 接收方用户钱包（链上 mint(to)）
        "contract": ge_addr,
        "method": "GreenEnergy.mint(to,value,reason)",
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
def add_tree(req: TreeAddReq):
    """管理员新增树种。"""
    # 验证 wallet 的角色是 admin
    with get_conn() as conn:
        row = conn.execute(
            "SELECT role_key FROM eco_role_selections WHERE wallet=?",
            (req.wallet,),
        ).fetchone()
    if not row or row["role_key"] != "admin":
        raise HTTPException(403, "仅管理员可新增树种")
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
def exchange_certificate(req: CertExchangeReq):
    """花费绿色能量兑换植树证书。"""
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
def exchange_badge(req: BadgeExchangeReq):
    """花费绿色能量兑换生态勋章或骑行券。"""
    cfg = BADGE_CONFIG.get(req.badge_type)
    if not cfg:
        raise HTTPException(400, f"未知类型: {req.badge_type}，支持 badge / voucher")
    cost = cfg["cost"]
    token_id = cfg["token_id"]
    badge_name = cfg["name"]

    # 1. 查找 GreenEnergy 合约，检查余额
    ge_addr, ge_abi = _find_contract("GreenEnergy")
    if not ge_addr:
        raise HTTPException(400, "GreenEnergy 合约未部署")
    balance = _to_int(_get_energy_balance(req.wallet))
    if balance < cost:
        raise HTTPException(400, f"绿色能量不足，需要 {cost}，当前 {balance}")

    c = get_chain_client()
    admin_addr = c.resolve_account(ADMIN_ALIAS)

    # 2. 调用 GreenEnergy.transfer(admin, cost) 从 wallet 转给 admin
    r_transfer = c.call_contract(
        ge_addr, "transfer",
        [admin_addr, cost],
        req.wallet, ge_abi,
    )
    if not r_transfer.get("ok"):
        raise HTTPException(400, "能量扣除失败: " + str(r_transfer.get("error", "")))

    # 3. 查找 EcoBadge 合约，调用 mint(wallet, token_id, 1, "")
    eb_addr, eb_abi = _find_contract("EcoBadge")
    if not eb_addr:
        raise HTTPException(400, "EcoBadge 合约未部署")
    r_mint = c.call_contract(
        eb_addr, "mint",
        [c.resolve_account(req.wallet), token_id, 1, ""],
        req.wallet, eb_abi,
    )
    if not r_mint.get("ok"):
        raise HTTPException(400, "勋章铸造失败: " + str(r_mint.get("error", "")))
    tx_hash = r_mint.get("tx_hash", "")

    # 4. 记录到 eco_badges 表
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO eco_badges(token_id,badge_type,name,owner,cost_energy,issued_by,contract_address,tx_hash,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (token_id, req.badge_type, badge_name, req.wallet, cost,
             req.wallet, eb_addr, tx_hash, now()),
        )
    return {"ok": True, "badge_type": req.badge_type, "tx_hash": tx_hash}


@router.get("/badges/list")
def list_badges(owner: str):
    """返回勋章 / 骑行券列表。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM eco_badges WHERE owner=? ORDER BY id DESC",
            (owner,),
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


# ===========================================================================
# 7. 操作错误/行为记录（供实训报告做打分与错误分析）
# ===========================================================================
@router.post("/errors/record")
def record_error(req: OpErrorRecordReq):
    """前端在操作成功/失败时都可写入审计记录，level=success/info/warn/error。"""
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
def market_list(req: MarketListReq):
    """挂牌绿色资产。校验资产归属 → 写入 eco_market_listings。"""
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
        if row["owner"] != req.seller:
            raise HTTPException(403, "只能挂自己的资产")
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
        if row["owner"] != req.seller:
            raise HTTPException(403, "只能挂自己的资产")
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
    return {"items": [dict(r) for r in rows]}


class MarketBuyReq(BaseModel):
    buyer: str
    listing_id: int


@router.post("/market/buy")
def market_buy(req: MarketBuyReq):
    """购买绿色资产：GreenEnergy 转账(买方→卖方) + NFT 转移(卖方→买方)。"""
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
def market_cancel(payload: dict):
    """取消挂牌（仅卖家本人）。"""
    listing_id = payload.get("listing_id")
    seller = payload.get("seller")
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
