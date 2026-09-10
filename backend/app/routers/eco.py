"""生态联盟链高级实战模块 API。

六个联盟节点（管理员 / 地铁 / 公交 / 共享单车 / 外卖 / 回收）协同运营，
基于 GreenEnergy（ERC20）、PlantCertificate（ERC721）、EcoBadge（ERC1155）
三个合约实现绿色能量发放、植树证书兑换、生态勋章/骑行券兑换全流程。
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..chain_client import get_chain_client
from ..db import _lock as _DB_LOCK, get_conn, now
from ..security import (
    BUILTIN_WALLETS,
    PRIVILEGED_ROLES,
    assert_actor_wallet,
    builtin_addresses,
    ensure_own_wallet,
    get_current_user,
    lower_wallet_in,
    optional_user,
    redact_secrets,
    resolve_wallet_candidates,
)
from ..tx_decoder import compile_source
# 联盟角色权威定义与权限助手已统一至 app/learning/alliance_roles.py（ROLES/ROLE_ALIAS
# 逐字段原样迁入；本模块经 import 保持原引用入口，散落的权限 if-else 改用统一助手，
# 403 文案与校验结果语义完全不变）
from ..learning.alliance_roles import (
    ASSET_FORMS,
    ALLIANCE_WALLETS,
    CAP_ASSET_EXCHANGE,
    CAP_ASSET_ISSUE_BADGE,
    CAP_ASSET_ISSUE_CERT,
    CAP_ASSET_ISSUE_VOUCHER,
    CAP_CATALOG_MANAGE,
    CAP_CONTRACT_DEPLOY,
    CAP_ENERGY_ISSUE,
    CAP_ENERGY_RECEIVE,
    CAP_MARKET_TRADE,
    CAP_TREASURY_MANAGE,
    RESIDENT_PROFILE,
    ROLES,
    ROLE_ALIAS,
    TREASURY_WALLET,
    calc_energy_points,
    dimension_view,
    duty_matrix,
    ensure_admin_for_trees,
    ensure_asset_owner,
    ensure_bike_for_voucher,
    ensure_capability,
    ensure_issuer_role,
    ensure_minter_role,
    ensure_wallet_role_binding,
    find_role,
    role_capabilities,
    role_of_alliance_wallet,
    role_profile,
    wallet_address,
)
# 钱包口径归一：资产相关标识一律用真实链上地址（0x + 40 hex），不得出现
# `stu:uuid` / 裸 user_id 这类带冒号、连字符的内部别名（见 app/wallet_id 说明）。
from ..wallet_id import address_variants, alias_of as wallet_id_alias, to_address
# 能量流水账（余额的唯一事实源）已下沉至 app/energy_ledger.py：eco 路由与 seed
# 播种共用同一套 ref 规范，避免两处各写一套口径导致余额双计 / 资金不守恒。
from ..energy_ledger import (
    FLOW_BACKFILL,
    FLOW_EXCHANGE,
    FLOW_ISSUE,
    FLOW_LABELS,
    FLOW_MARKET_IN,
    FLOW_MARKET_OUT,
    FLOW_TREASURY_BURN,
    FLOW_TREASURY_IN,
    backfill_energy_flows as _backfill_energy_flows,
    ensure_flow as _ensure_flow,
    flow_balance as _flow_balance,
    ledger_balances as _ledger_balances,
    record_exchange_cost as _record_exchange_cost,
    treasury_stats as _treasury_stats,
)
# 学习行为埋点统一收口至 learning.events（EventType 常量 + track 唯一写入实现）
from ..learning.events import EventType, track as _track
# 任务 #21：五级验证流水线（记录模式：L3/L4 复用本接口既有校验与执行结果）+ 事件总线
from .. import verifier
from ..events_bus import BusEvent, publish as bus_publish


router = APIRouter(prefix="/api/eco", tags=["eco"])

logger = logging.getLogger(__name__)

# ===========================================================================
# 六个联盟链节点角色定义（ROLES / ROLE_ALIAS）已迁至 app/learning/alliance_roles.py
# （权威定义，内容逐字段原样迁入；本文件顶部 import 保持引用入口不变。前端
#  EnergyProofForm.vue 依赖的 energy_rule.proof_fields 亦随迁未动。）
# ===========================================================================

# 内置合约清单 / 构造参数 / 链上发行权白名单已抽至 app/alliance_contracts.py（单一来源，
# seed 播种与本路由一键部署共用，避免两侧口径分叉）
from ..alliance_contracts import (
    BUILTIN_CONTRACTS,
    DEFAULT_CTOR_ARGS,
    ENERGY_TOKEN_NAME,
    grant_issuers,
    has_issuer_control,
    issuer_enforcement,
    latest_deployed,
    scope_wallets,
    sync_energy_token,
)

# 默认勋章 / 骑行券类型（EcoBadge 合约中 BADGE_ID=1, VOUCHER_ID=2）
DEFAULT_BADGE_TYPES = [
    {"badge_type": "badge",   "name": "生态勋章", "icon": "🏅", "cost_energy": 10,
     "token_id": 1, "supply": 100, "issuer_role": "",  "image_url": "",
     "desc": "绿色出行达人的荣誉勋章（默认类型，全体联盟节点可发放）"},
    {"badge_type": "voucher", "name": "骑行券",   "icon": "🎫", "cost_energy": 20,
     "token_id": 2, "supply": 100, "issuer_role": "bike", "image_url": "",
     "desc": "可兑换一次免费共享单车骑行（仅共享单车公司发放）"},
]

# 管理员别名 —— 兑换时能量消耗回收目标（= 能量国库账户）
ADMIN_ALIAS = TREASURY_WALLET

# 能量流水类型常量（FLOW_*）与记账实现见 app/energy_ledger.py（文件顶部 import）


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
    supply: int = 0        # ERC721 项目发行额度（一证一树；0 = 不限额，仅存量兼容）
    wallet: str


class CertExchangeReq(BaseModel):
    wallet: str
    species_id: int


class BadgeExchangeReq(BaseModel):
    wallet: str
    badge_type: str          # badge | voucher（内置类型快捷方式）
    type_id: Optional[int] = None   # 指定兑换的勋章/骑行券类型 ID（生态勋章支持自定义多类型）
    quantity: int = 1        # ERC1155 同类多份：一次兑换份数（成本 = 单价 × 份数）


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
    校验规则（与 ROLES.energy_rule 对齐，点数由 calc_energy_points 按量核算）：
    - 地铁 metro：proof.distance_km ≥ 10km → 基础 50 点，超出部分按里程追加（单次有封顶）
    - 公交 bus：proof.ride_minutes ≥ 5min → 基础 20 点，超出部分按时长追加
    - 单车 bike：proof.distance_km ≥ 2km → 基础 15 点，超出部分按里程追加
    - 外卖 takeout：proof.no_cutlery == True → 固定 10 点（碳减排不可按量放大）
    - 回收 recycling：proof.weight_kg ≥ 1kg → 基础 100 点，按称重追加

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
    """查询钱包当前选择的联盟角色（eco_role_selections），未选择返回 None。

    写入侧已统一为真实地址，但历史行可能仍是旧别名，故查询按
    「原值 + 真实地址」双口径匹配，避免迁移前角色选择突然失效。
    """
    if not wallet:
        return None
    vs = [v for v in address_variants(wallet) if v]
    if not vs:
        return None
    marks = ",".join(["?"] * len(vs))
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT role_key FROM eco_role_selections WHERE lower(wallet) IN ({marks})",
            vs,
        ).fetchone()
    if not row:
        return None
    return _find_role(row["role_key"])


def _find_contract(name: str):
    """从 deployed_contracts 表查找指定名称的最新部署合约。

    返回 (address, abi) 元组；未找到或地址在当前链上无代码（stale 记录）时返回 (None, None)。
    取址实现已上收到 alliance_contracts.latest_deployed（与 NFT 市场结算、seed 播种同一口径）。
    """
    return latest_deployed(name)


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
    """钱包标识归一 → **真实链上地址**（资产台账唯一口径）。

    旧行为只做 lower()，于是 `stu:0ae7783d-d59d-40e1-…`（带冒号与连字符的
    登录别名）也能当资产归属落库：同一人在证书 / 勋章 / 流水里出现多套
    归属，前端无法复制跳转、与链上 from_addr 也对不上。现在 eco 全部读写
    经本函数归一；密钥库不可用时降级原值小写（不抛异常）。
    """
    return to_address(wallet)


def _wallet_marks(wallet: str) -> tuple:
    """(SQL 占位串, 参数列表)：按「原别名 + 真实地址」双口径命中历史行。"""
    vs = [v for v in address_variants(wallet) if v] or [""]
    return ",".join(["?"] * len(vs)), vs


def _identity_role(wallet: str) -> Optional[dict]:
    """该钱包「以什么身份」办事 —— 内置组织钱包恒为其机构角色，个人钱包看角色选择表。

    修 B2（组织钱包 ↔ 角色错位）：旧口径只看 eco_role_selections，于是库里
    「0xbus → takeout」这种脏数据会让公交钱包以外的人以公交机构名义签章，
    而组织钱包自己反而要「先点选角色」才能办本机构的业务。组织钱包与机构
    是一一对应的（ALLIANCE_WALLETS），身份由钱包本身决定，不需要也不允许选。
    """
    w = _norm_wallet(wallet)
    if not w:
        return None
    fixed = role_of_alliance_wallet(w)
    if fixed:
        return find_role(fixed)
    return _selected_role(w)


def _ensure_governor(user: dict, action: str) -> None:
    """治理动作的**登录身份**校验（修 B12：冒用组织钱包 = 提权）。

    assert_actor_wallet 允许任何登录用户以内置组织钱包（0xadmin 等）作为 actor，
    这是实训演示的基础；但 `_identity_role(0xadmin)` 会恒返回【管理员】能力，
    于是一个学生只要把 wallet 写成 0xadmin 就能改目录额度 / 销毁能量 / 部署联盟合约。
    能力位只能证明「这个钱包的机构身份」，不能证明「这个登录账号有权治理」，
    因此治理类端点需叠加一层账号身份校验（仅教师 / 平台管理员）。
    """
    if int(user.get("role_id") or 0) in PRIVILEGED_ROLES:
        return
    raise HTTPException(
        403,
        f"「{action}」属联盟治理职能，仅教师 / 平台管理员账号可执行；"
        f"学生账号可查阅树种目录、发行额度与能量国库（只读），不能改写。",
    )


# ===========================================================================
# 能量流水账：实现已下沉至 app/energy_ledger.py（含 ref 命名规范与资金守恒推导）
#   _ensure_flow(conn, wallet=, kind=, amount=, ref=, note=, role_key=)  幂等落账
#   _record_exchange_cost(conn, wallet=, cost=, kind_prefix=, obj_id=, note=)
#       → 兑换双写：兑换人出账 + 国库入账
#   _flow_balance(conn, wallet) / _backfill_energy_flows(conn) / _treasury_stats(conn)
# ===========================================================================


def _get_energy_ledger_balance(wallet: str) -> int:
    """绿色能量账本余额 = Σ 该钱包流水（余额的唯一事实源）。

    历史上这里是「按当前 owner 现算成本」的实现，会在资产易主时凭空回补成本
    （B1 通胀漏洞），已整体替换为流水口径；流水不足时由 init_eco_db 的
    _backfill_energy_flows 存量摊平，因此不需要任何兼容分支。

    纯读、无链上副作用；负数净额按 0 展示（脏数据由国库治理科目纠偏）。
    """
    w = _norm_wallet(wallet)
    if not w:
        return 0
    with get_conn() as conn:
        return max(0, _flow_balance(conn, w))


def _chain_energy_balance(wallet: str, *, addr: str = "", abi: Any = None) -> tuple:
    """只读链上 GreenEnergy.balanceOf，返回 (余额 或 None, 错误原文)。

    `None` 与 `0` 必须分开：0 = 链上确实是 0，None = 当前链上取不到可信数值
    （合约无代码 / 调用 revert / mock 链返回非数值）。旧实现把两者一律吞成 0，
    于是「查询失败」在钱包页显示成「能量凭空消失」，在兑换页变成一句英文 revert。
    """
    if not addr:
        addr, abi = _find_contract("GreenEnergy")
    if not addr:
        return None, "GreenEnergy 合约在当前链上不可用（链已重置或尚未部署）"
    c = get_chain_client()
    try:
        r = c.call_contract(addr, "balanceOf", [c.resolve_account(wallet)], wallet, abi or [])
    except Exception as e:  # 链不可用 / 客户端异常
        return None, f"链上余额查询异常: {e}"
    if not r.get("ok"):
        return None, f"链上余额查询失败: {r.get('error') or r.get('status') or 'reverted'}"
    try:
        return _to_int(r.get("result", "0")), ""
    except (TypeError, ValueError):
        return None, f"链上余额返回值非数值: {r.get('result')!r}"


def _energy_balance_view(wallet: str) -> dict:
    """绿色能量余额的**全平台唯一视图**（钱包页 / 联盟页 / 兑换校验同一口径）。

    - balance：对外余额 = 账本净额（余额的唯一事实源），账本无记录时退回链上；
    - ledger_balance / chain_balance：两侧原值，供前端展示「链上待同步」差额；
    - needs_sync / sync_gap：账本 > 链上（沙盒链重启后链上还没追平账本的历史差额）；
    - chain_known：链上数值是否可信（False = 取不到，不做任何同步判定）。

    纯读、无链上写副作用；回填只在写路径（_require_chain_balance）与启动对账里做。
    """
    w = _norm_wallet(wallet)
    ledger = _get_energy_ledger_balance(w)
    chain_raw, err = _chain_energy_balance(w)
    chain_known = chain_raw is not None
    chain = int(chain_raw or 0) if chain_known else 0
    if ledger > 0:
        balance, source = ledger, "ledger"
    else:
        balance, source = chain, "chain"
    return {
        "wallet": w,
        "balance": int(balance),
        "source": source,
        "ledger_balance": int(ledger),
        "chain_balance": int(chain),
        "chain_known": chain_known,
        "needs_sync": bool(chain_known and ledger > chain),
        "sync_gap": max(0, int(ledger) - int(chain)) if chain_known else 0,
        "chain_error": err,
    }


def _get_energy_balance(wallet: str) -> str:
    """查询钱包绿色能量余额（纯读，不产生任何链上写副作用）。

    口径实现见 `_energy_balance_view`：账本净额优先、链上余额只读回退；
    GET /energy/balance 与画像等读接口不再触发链上交易，避免页面加载污染块高。
    """
    return str(_energy_balance_view(wallet)["balance"])


def _sync_chain_balance(wallet: str) -> dict:
    """把持久化业务账本余额回填到链上（账本 > 链上时由管理员 mint 差额）。

    本地沙盒链（py-evm）在服务重启后会重置，为保证「兑换 / 挂牌购买」的链上转账
    能够真实执行，需要将账本与链上余额对齐。回填通过 GreenEnergy.mint 由管理员
    钱包发出；差额本身已在账本中，故不重复写 eco_energy_records。

    返回 {"ok", "diff", "ledger_balance", "chain_balance", "chain_balance_after",
    "chain_known", "detail"}。**失败必须让调用方看得见**：旧实现在 mint 失败时
    `if not r.get("ok"): return` 静默放弃，链上余额永远追不上账本，居民兑换只能
    吃到 `GE: insufficient balance` 这类合约 revert 原文（勋章 / 骑行券全部报错）。
    mint 因缺链上发行权失败时，先补授白名单（_try_repair_issuer）再重试一次。
    """
    ledger = _get_energy_ledger_balance(wallet)
    res = {"ok": True, "diff": 0, "ledger_balance": int(ledger), "chain_balance": 0,
           "chain_balance_after": 0, "chain_known": False, "detail": ""}
    if ledger <= 0:
        return res
    addr, abi = _find_contract("GreenEnergy")
    if not addr:
        res.update(ok=False, diff=int(ledger), detail=(
            "GreenEnergy 合约在当前链上不可用（链已重置或尚未部署），无法把账本能量补给链上。"
            "请联盟管理员在「联盟链」页重新部署 GreenEnergy 后重试。"))
        return res
    c = get_chain_client()
    before_raw, err = _chain_energy_balance(wallet, addr=addr, abi=abi)
    res["chain_known"] = before_raw is not None
    chain_bal = int(before_raw or 0)
    res["chain_balance"] = chain_bal
    diff = ledger - chain_bal
    if before_raw is None:
        # 链上读不到可信数值（mock 链 / 非 EVM 模式）：仍按账本全额补发，但事后无法复核
        diff = ledger
    if diff <= 0:
        res["chain_balance_after"] = chain_bal
        res["detail"] = err
        return res
    args = [c.resolve_account(wallet), diff, "账本回填"]
    r = c.call_contract(addr, "mint", args, ADMIN_ALIAS, abi)
    if not r.get("ok") and _try_repair_issuer(c, addr, abi, "GreenEnergy", ADMIN_ALIAS):
        r = c.call_contract(addr, "mint", args, ADMIN_ALIAS, abi)   # 补授发行权后重试一次
    after_raw, err2 = _chain_energy_balance(wallet, addr=addr, abi=abi)
    res["chain_balance_after"] = int(after_raw or 0)
    res["diff"] = int(diff)
    if after_raw is None:                    # 无法复核：以本次 mint 的结果为准
        res["chain_known"] = False
        res["ok"] = bool(r.get("ok"))
        res["detail"] = "" if res["ok"] else str(r.get("error") or err2 or "链上未返回成功")
    elif res["chain_balance_after"] >= ledger:
        # 回填不入账本（账本本来就有这笔余额），只打印链上补给痕迹
        print(f"[eco] 账本回填 {wallet}: +{diff} 能量 (mint by {ADMIN_ALIAS})")
        res["detail"] = f"已向链上补发 {diff} 点能量"
    elif not r.get("ok"):
        res["ok"] = False
        res["detail"] = (
            f"链上能量补发失败：账本 {ledger} 点 / 链上 {chain_bal} 点，需补 {diff} 点；"
            f"失败原因：{r.get('error') or err or '合约未返回成功'}。"
            "通常是当前链实例上的 GreenEnergy 未授予管理员发行权（onlyIssuer），"
            "请联盟管理员在「联盟链」页执行一次能量对账，或重新部署 GreenEnergy。")
    else:
        res["ok"] = False
        res["detail"] = (
            f"链上能量补发后仍与账本不一致：账本 {ledger} 点 / 链上 {res['chain_balance_after']} 点。"
            "请联盟管理员在「联盟链」页执行一次能量对账后重试。")
    return res


def _require_chain_balance(wallet: str, cost: int, action: str) -> None:
    """扣能动作前的统一能量保障：余额校验 → 账本回填链上 → 链上硬校验。

    任一道关卡不过都抛**可诊断中文 400**（说清账本 / 链上 / 缺口 / 处理指引），
    不再让合约 revert 英文原文冒到前端。链上数值不可信时（mock / legacy）
    退化为「只做账本校验 + 尽力回填」，与既有 mock 测试与沙盒模式口径一致。
    """
    view = _energy_balance_view(wallet)
    if view["balance"] < cost:
        raise HTTPException(
            400,
            f"绿色能量不足：{action}需要 {cost}，当前 {view['balance']}"
            + (f"（账本 {view['ledger_balance']} / 链上 {view['chain_balance']}）"
               if view["chain_known"] else ""),
        )
    sync = _sync_chain_balance(wallet)
    if not sync["ok"]:
        raise HTTPException(400, sync["detail"])
    if sync["chain_known"] and int(sync["chain_balance_after"]) < cost:
        raise HTTPException(
            400,
            f"链上能量余额不足，无法{action}扣款：账本 {view['ledger_balance']} 点 / "
            f"链上 {sync['chain_balance_after']} 点，需要 {cost} 点。"
            "请联盟管理员在「联盟链」页执行一次能量对账后重试。")


def _chain_deduct_hint(wallet: str, cost: int, r: dict) -> str:
    """链上扣款失败时的可诊断文案：合约 revert 原文 + 当前账本 / 链上实际数字。"""
    view = _energy_balance_view(wallet)
    tail = (f"（账本 {view['ledger_balance']} / 链上 {view['chain_balance']}，本次需 {cost}）"
            if view["chain_known"] else f"（当前链实例读不到可信余额，本次需 {cost}）")
    return f"{r.get('error') or r.get('status') or '转账未成功'}{tail}"


def _compensate_energy(c, ge_addr: str, ge_abi, from_wallet: str, to_addr: str, amount: int) -> bool:
    """链上能量回滚（best effort）：把已经转走的能量由收款方原路退回。

    适用于「先扣能量、后铸资产」的两步链路：第二步在链上 revert 时，第一步的
    transfer 已经真实生效，不回滚就会让居民白付能量拿不到资产（账本也没记，
    事后只能人工对账）。退回本身是普通 transfer，只需 from_wallet 有权动自己的余额。
    """
    try:
        r = c.call_contract(ge_addr, "transfer", [to_addr, int(amount)], from_wallet, ge_abi)
        return bool(r.get("ok"))
    except Exception:
        return False


def _try_repair_issuer(c, contract_addr: str, abi, contract_name: str,
                       issuer_wallet: str) -> bool:
    """mint revert 时自动补授链上发行白名单（幂等，best effort）。

    适用场景：EVM 链重置 / 密钥库轮换后合约 issuers 映射内地址与新地址不对应，
    导致业务节点钱包 mint 被 onlyIssuer 拒绝。本函数：
    1. 只读确认 issuer_wallet 确实不在链上白名单（若是则失败另有原因，不补授）；
    2. 调用 grant_issuers 补授（addIssuer 重复执行只是写一次 true，无副作用）。

    返回 True 表示白名单已成功补授，调用方可以安全重试 mint。
    只在合约支持 addIssuer 时生效（旧合约返回 False，走应用层校验）。
    """
    if not contract_addr or not has_issuer_control(abi):
        return False
    try:
        # 只读 issuers(addr) getter：确认是否确实缺权（不是余额不足等其它原因）
        if _abi_has(abi, "issuers"):
            check = c.call_contract(contract_addr, "issuers", [issuer_wallet],
                                    TREASURY_WALLET, abi)
            # ok=True 且 result 为 truthy → 已在白名单，mint 失败另有原因，不重试
            if check.get("ok") and check.get("result"):
                return False
        # 补授（幂等）：为全量 scope 钱包逐一 addIssuer，单次失败不阻断其余
        grant = grant_issuers(c, contract_addr, abi, contract_name,
                              operator=TREASURY_WALLET)
        return bool(grant.get("granted"))
    except Exception:
        return False


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


def _reserve_badge_quota(type_id: int, qty: int) -> bool:
    """ERC1155 发行额度原子占位（同类可多份）：一条 UPDATE 带 `minted + qty <= supply` 守卫。

    先查后改在并发下会超发，故占位与校验合并为一条语句；返回 False 表示额度不足。
    """
    with _DB_LOCK, get_conn() as conn:
        return bool(conn.execute(
            "UPDATE eco_badge_types SET minted = minted + ? WHERE id=? AND minted + ? <= supply",
            (int(qty), int(type_id), int(qty)),
        ).rowcount)


def _refund_badge_quota(type_id: int, qty: int) -> None:
    """归还已占但未用掉的发行额度（链上 mint 失败 / 合约未部署时调用）。"""
    with _DB_LOCK, get_conn() as conn:
        conn.execute(
            "UPDATE eco_badge_types SET minted = MAX(0, minted - ?) WHERE id=?",
            (int(qty), int(type_id)),
        )


def _refund_species_quota(species_id: int) -> None:
    """归还 ERC721 植树证书的项目额度（一证一树，占位 1 份）。"""
    with _DB_LOCK, get_conn() as conn:
        conn.execute(
            "UPDATE eco_tree_species SET issued = MAX(0, issued - 1) WHERE id=?",
            (int(species_id),),
        )


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
def _issued_energy_by_role() -> dict:
    """各发行节点累计已发行能量（一次 GROUP BY）。

    角色卡片与职能矩阵都要显示「发行授信 已用/上限」，逐个角色调
    _role_issued_energy 会打 6 次查询；这里合并成一次，查不到（流水表还没建）
    就返回空字典，前端按「无授信数据」渲染，不影响主流程。
    """
    try:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT role_key, COALESCE(SUM(amount), 0) AS total FROM eco_energy_flows "
                "WHERE kind=? AND role_key IS NOT NULL AND role_key<>'' GROUP BY role_key",
                (FLOW_ISSUE,),
            ).fetchall()
        return {str(r["role_key"]): int(r["total"] or 0) for r in rows}
    except Exception:
        return {}


@router.get("/roles")
def list_roles():
    """六个联盟节点角色列表。

    wallet / address = 该机构的**真实链上地址**（资产归属 / 交易发起 / 前端复制
    跳转一律用它），wallet_alias = 机构友好别名（0xmetro，只作展示与密钥库取号）；
    energy_issued = 该节点累计已发行能量（与 energy_quota 配对，前端据此画授信进度）。
    """
    issued = _issued_energy_by_role()
    out = []
    for r in ROLES:
        addr = wallet_address(r["key"]) or ""
        out.append(dict(r, wallet=addr, wallet_alias=r.get("wallet") or "",
                        address=addr, energy_issued=int(issued.get(r["key"], 0))))
    return out


# 四维度表头（前端矩阵卡片直接按此顺序渲染，不自己判定）
_DUTY_DIMENSIONS = [
    {"key": "issue_energy", "name": "发行绿色能量",
     "desc": "审核本人业务凭证并以其组织钱包上链 mint（仅业务节点）"},
    {"key": "issue_asset", "name": "发行绿色资产",
     "desc": "按协议形态发行：ERC721 一证一树 / ERC1155 同类多份"},
    {"key": "obtain_energy", "name": "获取绿色能量",
     "desc": "提交低碳行为凭证由节点审核发放（仅居民）"},
    {"key": "exchange_asset", "name": "兑换绿色资产",
     "desc": "耗自身能量兑换，能量转入国库（仅居民）"},
    {"key": "trade_market", "name": "二级市场交易",
     "desc": "居民之间以绿色能量结算的资产流转（仅居民）"},
    {"key": "govern", "name": "联盟治理",
     "desc": "合约部署 / 树种与发行额度目录 / 能量国库与销毁（仅管理员）"},
]


@router.get("/roles/duties")
def roles_duties(wallet: str = "", user: Optional[dict] = Depends(optional_user)):
    """四维度职能矩阵：谁发行能量 / 谁发行资产 / 谁获取能量 / 谁兑换资产。

    只读派生接口（数据源：alliance_roles.duty_matrix）——前端严格按 capabilities
    渲染业务项，不得自己写一套角色名单判定（避免前后端权限口径漂移）。
    传 wallet 且已登录时额外返回该钱包的**当前身份视图**（组织钱包恒为机构角色）。

    矩阵主体是公开的角色定义，故改为 optional_user：未登录 / JWT 过期时前端
    仍能拿到完整矩阵（identity=null），不至于整块“角色职能矩阵”空白。
    """
    issued = _issued_energy_by_role()
    out: dict = {
        "dimensions": _DUTY_DIMENSIONS,
        "matrix": [dict(m, energy_issued=int(issued.get(m["key"], 0))) for m in duty_matrix()],
        "asset_forms": [dict(v) for v in ASSET_FORMS.values()],
        "identity": None,
    }
    if wallet and user:
        w = _ensure_viewable_wallet(user, wallet, "wallet")
        sel = _identity_role(w)
        addr = _norm_wallet(w)
        out["identity"] = {
            "wallet": addr,
            # 友好别名（机构钱包 0xmetro / 本人 stu:xxx）：只作展示，不当资产标识
            "wallet_alias": (wallet_id_alias(addr) or (sel or {}).get("wallet") or ""),
            "address": addr,
            "profile": role_profile(sel),
            "role_key": (sel or {}).get("key") or "resident",
            "role_name": (sel or RESIDENT_PROFILE).get("name") or "",
            # 职能所属机构的友好别名（0xmetro）：只作展示；对外不再以
            # role_wallet 之名装别名（wallet 结尾的字段一律是真实地址）
            "role_wallet_alias": (sel or {}).get("wallet") or "",
            "role_address": wallet_address((sel or {}).get("key") or ""),
            "capabilities": sorted(role_capabilities(sel)),
            "dimensions": dimension_view(sel),
        }
    return out


@router.post("/role/select")
def select_role(req: RoleSelectReq, user: dict = Depends(get_current_user)):
    """选择 / 切换联盟节点角色（INSERT OR REPLACE）。操作者身份从 JWT 验签解析。"""
    role = _find_role(req.role_key)
    if not role:
        raise HTTPException(400, f"未知角色: {req.role_key}")
    req.wallet = assert_actor_wallet(user, req.wallet)  # 防伪造他人身份
    # 修 B2（写入侧）：组织钱包只能挂自己的角色，否则库里会留下
    # 「0xbus → takeout」这种脏数据，使机构业务签章错位（读取侧已由 _identity_role 免疫）
    ensure_wallet_role_binding(req.wallet, role["key"])
    # 以权威 key 落库（delivery/recycle 等别名在此归一化，避免前后端 key 不一致导致页面联动错位）
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO eco_role_selections(wallet, role_key, selected_at) VALUES(?,?,?)",
            (req.wallet, role["key"], now()),
        )
    # 行为埋点：学生切换联盟角色（对应 alliance_gov 维度的 eco_role_switch 指标）
    # wallet 落的是**当时操作的钱包**（点角色卡时为机构钱包），另落 user_id 作为
    # 操作人归属，否则报告 E 项（角色体验多样性）按本人钱包筛不到这次切换。
    _track(EventType.ECO_ROLE_SWITCH, target=role["key"], wallet=req.wallet or "",
           extra={"role_key": role["key"]},
           user_id=str(user.get("user_id") or ""))
    return {"ok": True, "role": role}


@router.get("/role/current")
def current_role(wallet: str, user: dict = Depends(get_current_user)):
    """查询钱包当前选中的角色（P1-27：只读接口需登录，仅限本人 / 公开演示钱包）。"""
    wallet = _ensure_viewable_wallet(user, wallet, "wallet")
    marks, params = _wallet_marks(wallet)
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT role_key FROM eco_role_selections WHERE lower(wallet) IN ({marks})",
            params,
        ).fetchone()
    if not row:
        return {"role_key": None, "profile": "resident", "wallet": _norm_wallet(wallet),
                "capabilities": sorted(role_capabilities(None))}
    role = _find_role(row["role_key"])
    # 库里可能有历史别名 key（delivery/recycle），统一回权威 key，保证前端角色卡片高亮联动一致
    key = role["key"] if role else row["role_key"]
    return {"role_key": key, "role": role, "profile": role_profile(role),
            "wallet": _norm_wallet(wallet),
            "capabilities": sorted(role_capabilities(role))}


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
def role_workbench(role_key: str, wallet: str = "", user: dict = Depends(get_current_user)):
    """角色工作台：职能维度 + 能力位 + 该身份的链上活动统计 + 待办业务清单（只读聚合）。

    - 职能与能力位统一由 alliance_roles 派生（dimension_view / role_capabilities），
      前端只渲染不判定；
    - 链上活动统计：contract_calls 按 caller、transactions 收发、能量发行按**流水**统计
      （不重算归属，与国库审计同一口径）；
    - role_key=resident（或未选角色）返回**居民工作台**：申领能量 / 兑换资产 / 市场交易。
    """
    if (role_key or "").strip().lower() in ("", "resident", "learner", "user"):
        return _resident_workbench(user, wallet)
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
        # 绿色能量发行统计（按流水、role_key 口径：与国库审计 / 节点授信完全一致）
        er = conn.execute(
            "SELECT COUNT(*) AS issue_count, COALESCE(SUM(amount),0) AS total_points, "
            "MAX(created_at) AS last_issued_at FROM eco_energy_flows "
            "WHERE kind=? AND role_key=?", (FLOW_ISSUE, role["key"]),
        ).fetchone()
    quota = int(role.get("energy_quota") or 0)
    used = int(er["total_points"] or 0)
    return {
        "role_key": role["key"],
        "role": dict(role),
        "profile": role_profile(role),
        "capabilities": sorted(role_capabilities(role)),
        "dimensions": dimension_view(role),
        "permissions": {
            "can_issue_badge": bool(role.get("can_issue_badge")),
            "can_issue_voucher": bool(role.get("can_issue_voucher")),
            "can_manage_trees": bool(role.get("can_manage_trees")),
            "has_energy_rule": bool(role.get("energy_rule")),
        },
        "activity": {
            # 归属匹配的权威口径：真实地址；别名只作展示（旧版把 0xmetro 直接
            # 叫 wallet，前端 / 审计无法区分它是不是一个可转账的地址）
            "wallet": resolved_addr or role_wallet,
            "wallet_alias": role_wallet,
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
                "total_points": used,
                "last_issued_at": er["last_issued_at"] or "",
                "quota": quota,
                "quota_used": used,
                "quota_remaining": (quota - used) if quota > 0 else -1,   # -1 = 未设授信上限
            },
        },
        "todos": _workbench_todos(role),
    }


def _resident_todos() -> list:
    """居民的三项业务（四维度中属于居民的那三面）。"""
    return [
        {"key": "obtain_energy", "source": "capability:energy_receive",
         "title": "提交低碳行为凭证，申领绿色能量",
         "desc": "地铁 / 公交 / 单车 / 外卖 / 回收五个节点各自审核并以其组织钱包上链发行；"
                 "能量按业务量核算（超出门槛部分追加，单次封顶），居民不能自铸"},
        {"key": "exchange_asset", "source": "capability:asset_exchange",
         "title": "兑换绿色资产",
         "desc": "植树证书（ERC721·一证一树、额满即止）/ 生态勋章与骑行券（ERC1155·同类可多份）；"
                 "能量付给发行方节点对应的项目额度，同时回收进国库"},
        {"key": "trade_market", "source": "capability:market_trade",
         "title": "二级市场挂牌 / 收购",
         "desc": "居民之间以绿色能量结算；ERC1155 可按份拆挂，成交写双方能量流水"},
    ]


def _resident_workbench(user: dict, wallet: str) -> dict:
    """居民工作台（不发行任何资产与能量，只作为接收方 / 兑换方 / 交易方）。"""
    w = _ensure_viewable_wallet(user, wallet, "wallet") if wallet else ""
    stats: dict = {"energy_balance": 0, "certificates": 0, "badge_units": 0,
                   "listings_active": 0}
    if w:
        with get_conn() as conn:
            stats["energy_balance"] = max(0, _flow_balance(conn, _norm_wallet(w)))
            stats["certificates"] = conn.execute(
                "SELECT COUNT(*) FROM eco_certificates WHERE lower(owner)=?",
                (_norm_wallet(w),)).fetchone()[0] or 0
            stats["badge_units"] = conn.execute(
                "SELECT COALESCE(SUM(quantity),0) FROM eco_badges WHERE lower(owner)=?",
                (_norm_wallet(w),)).fetchone()[0] or 0
            stats["listings_active"] = conn.execute(
                "SELECT COUNT(*) FROM eco_market_listings WHERE lower(seller)=? AND status='active'",
                (_norm_wallet(w),)).fetchone()[0] or 0
    return {
        "role_key": "resident",
        "role": dict(RESIDENT_PROFILE),
        "profile": "resident",
        "capabilities": sorted(role_capabilities(None)),
        "dimensions": dimension_view(None),
        "wallet": _norm_wallet(w),
        "activity": stats,
        "todos": _resident_todos(),
    }


# ===========================================================================
# 2. 合约状态与源码
# ===========================================================================
@router.get("/contracts/status")
def contracts_status():
    """检查三个内置合约是否已部署，并输出链上发行权口径。"""
    ge_addr, ge_abi = _find_contract("GreenEnergy")
    pc_addr, pc_abi = _find_contract("PlantCertificate")
    eb_addr, eb_abi = _find_contract("EcoBadge")

    def _one(addr, abi, name):
        return {
            "deployed": bool(addr),
            "address": addr,
            # onchain = 合约层有 issuers 白名单；legacy = 旧合约，发行权仅靠应用层拦
            "enforcement": issuer_enforcement(abi) if addr else "none",
            "issuer_scope": scope_wallets(name),
        }

    return {
        "green_energy": _one(ge_addr, ge_abi, "GreenEnergy"),
        "plant_certificate": _one(pc_addr, pc_abi, "PlantCertificate"),
        "eco_badge": _one(eb_addr, eb_abi, "EcoBadge"),
        "all_deployed": bool(ge_addr and pc_addr and eb_addr),
        # 三份都已部署且均带链上白名单 → onchain；否则提示管理员重新部署
        "enforcement": ("onchain" if (ge_addr and pc_addr and eb_addr
                                      and has_issuer_control(ge_abi)
                                      and has_issuer_control(pc_abi)
                                      and has_issuer_control(eb_abi))
                        else "legacy"),
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
# 构造参数 DEFAULT_CTOR_ARGS（联盟创世口径：GreenEnergy 初始供应 0）与内置合约
# 清单均从 app/alliance_contracts.py import（文件顶部），此处不重复定义。


class ContractDeployReq(BaseModel):
    name: str          # GreenEnergy | PlantCertificate | EcoBadge
    deployer: str = ""  # 留空 = 按 JWT 本人钱包；不再默认 0xlearner（密钥库内部别名）


@router.post("/contracts/deploy")
def deploy_builtin_contract(req: ContractDeployReq, user: dict = Depends(get_current_user)):
    """一键编译 + 部署内置绿色合约。

    流程：读取源码 → solc 编译 → 调用 EVM 部署 → 写入 deployed_contracts 表。
    若该合约已部署，则重新部署并覆盖旧记录（保留最新地址）。
    """
    req.deployer = assert_actor_wallet(user, req.deployer, "deployer")  # 部署者身份从 JWT 解析
    # 职能硬拦（修 B14）：三个内置合约是**联盟公共基础设施**（能量 / 证书 / 勋章的结算层），
    # 不是学生自己的实训工程；学生写自己的合约走 POST /api/contracts/deploy（IDE 侧）。
    _ensure_governor(user, "联盟内置合约部署")
    # 链上部署方统一为创世账户（0xadmin）：否则不同学生的地址会造成
    # mint / burn 的 msg.sender 权限口径随部署人漂移，后续发行与销毁无法对账。
    # 落库口径用它的**真实地址**（资产台账只认地址，别名仅密钥库内部标识）。
    req.deployer = _norm_wallet(TREASURY_WALLET) or TREASURY_WALLET
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

    # 3.5 能量代币登记同步（修「联盟页有能量、市场付款显示 0」）：
    #     GreenEnergy 重新部署后，能量钱包余额与 NFT / 绿色资产市场的结算币种
    #     必须一起切到新地址，否则两个页面读的是链上两份互不相干的代币合约。
    if req.name == ENERGY_TOKEN_NAME:
        sync_energy_token(r["address"], owner=req.deployer)

    # 4. 链上发行权白名单初始化（修 B13：旧合约任何人可 mint）
    #    owner = 创世账户（0xadmin），部署后由其把业务节点组织钱包加入 issuers
    grant = grant_issuers(c, r["address"], comp["abi"], req.name, operator=TREASURY_WALLET)

    return {
        "ok": True,
        "name": req.name,
        "address": r["address"],
        "tx_hash": r["tx_hash"],
        "block_number": r.get("block_number"),
        "gas_used": r.get("gas_used", 0),
        "standard": target["standard"],
        "issuer_grant": grant,
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
        # 双口径删除：未迁移的历史别名行也要一起清掉，否则「切回普通用户」后
        # 身份仍从 eco_role_selections 读到旧机构角色（地址化前后的两套口径）
        marks, params = _wallet_marks(req.wallet)
        conn.execute(f"DELETE FROM eco_role_selections WHERE lower(wallet) IN ({marks})", params)
    _track(EventType.ECO_ROLE_SWITCH, target="resident", wallet=req.wallet or "",
           extra={"role_key": ""}, user_id=str(user.get("user_id") or ""))
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


def _role_issued_energy(conn: Any, role_key: str) -> int:
    """某发行节点累计已发行的能量点数（只看流水 kind=issue，国库投放不计）。"""
    return int(conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM eco_energy_flows WHERE kind=? AND role_key=?",
        (FLOW_ISSUE, role_key),
    ).fetchone()[0] or 0)


def _issue_energy_core(req: "EnergyIssueReq", user: dict, uc: dict,
                       _t0: float, _pl: dict) -> dict:
    """issue_energy 主体（四维度职能口径：发行方限定 + 按量计价 + 授信配额 + 流水入账）。"""
    role = _find_role(req.role_key)
    if not role:
        raise HTTPException(400, f"未知角色: {req.role_key}")
    req.wallet = assert_actor_wallet(user, req.wallet)  # 接收方钱包必须与登录身份匹配（或内置生态钱包）
    # 职能硬拦：只有具备行为核算规则的业务节点才能发行能量（管理员 / 居民 → 403）
    ensure_capability(role, CAP_ENERGY_ISSUE)
    rule = role.get("energy_rule")
    # 发行方身份：机构角色的**真实链上地址**（链上 FROM 与库内归属同一口径）
    issuer_wallet = wallet_address(role["key"])
    if not req.wallet:
        raise HTTPException(400, "接收能量的钱包 wallet 必填")
    # 发行方与接收方必须隔离（修 B2b「发行方自铸」）：组织钱包 / 国库账户不能做接收方，
    # 否则地铁节点给自家钱包发能量 = 无对价的自我增发，真实商业里就是伪造运营数据。
    if role_of_alliance_wallet(_norm_wallet(req.wallet)):
        raise HTTPException(
            400,
            f"接收方 {req.wallet} 是联盟组织钱包 / 能量国库账户，不得作为能量接收方："
            f"能量只能发行给低碳居民（个人钱包），否则构成发行方自铸。",
        )
    # 钱包与机构必须一致（修 B2“0xbus 钱包签 takeout 业务”这类冒名发行）
    ensure_wallet_role_binding(req.wallet, role["key"])

    # 权限闭环（两种发放模式）：
    # - 操作者钱包已选联盟角色 → 角色扮演发放：选中角色必须与发放角色一致，
    #   避免未切换角色即可随意调用发币接口；
    # - 操作者钱包未选角色（普通用户/居民身份）→ 居民申请发放：提交低碳行为凭证，
    #   由对应联盟节点审核（下方阈值校验）后发放，链上 FROM 仍是该组织钱包，
    #   体现「只有联盟节点有发行权」的角色意义；教师演示可用 force=true 跳过校验。
    sel = _identity_role(req.wallet)
    mode = "force" if req.force else ("role_play" if sel else "resident_apply")
    if not req.force and sel is not None:
        ensure_issuer_role(role, sel)
    # 操作人留痕：个人钱包扮演机构时，“链上 FROM = 0xmetro”背后可能是任何学生，
    # 必须把真实登录身份一并落库（审计时能回答“这笔发行是谁签的”）。
    operator_wallet = _norm_wallet(user.get("wallet") or user.get("user_id") or req.wallet or "")
    operator_user_id = (user.get("user_id") or "").strip()

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
    action = rule["action"]
    # 按真实商业逻辑计价：达成门槛给基础分，超出部分按计量单位逐量加成，单次封顶
    points, pdetail = calc_energy_points(role, proof)
    pdetail = dict(pdetail or {})
    pdetail.update({"action": action, "unit": pdetail.get("unit") or rule.get("unit") or ""})

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

    # 2.5 发行授信校验（修「发行量无上限 = 能量无限通胀」）：每个节点全生命周期
    # 累计发行不得超出 energy_quota；余额不足时提示管理员上调授信或回收销毁。
    quota = int(role.get("energy_quota") or 0)
    quota_used = 0
    if quota > 0:
        with get_conn() as conn:
            quota_used = _role_issued_energy(conn, role["key"])
        if quota_used + points > quota:
            raise HTTPException(
                400,
                f"【{role['name']}】能量发行授信已用尽：累计已发行 {quota_used} 点 / "
                f"授信 {quota} 点（剩余 {max(0, quota - quota_used)}），本次核算 {points} 点无法发行。"
                f"能量发行量必须受节点授信约束，否则与无限印钞无异；"
                f"请由管理员在「能量国库」上调授信或执行回收销毁。",
            )

    # 3. 并发防双铸占位（任务 #25 评审修复 TOCTOU）：先在 db 全局锁内 INSERT 占位行
    # （tx_hash=''），靠 UNIQUE(proof_no, role_key) 拦截并发同单号请求；
    # 占位成功后再链上 mint，成功则 UPDATE 回填 tx_hash；mint 失败则删除占位行、
    # 按原错误语义抛出。占位命中 UNIQUE → 走原幂等回放路径（不重复落行）。
    with _DB_LOCK, get_conn() as conn:
        try:
            cur = conn.execute(
                """INSERT INTO eco_energy_records(
                    wallet, role_key, role_name, action, points, tx_hash, created_at,
                    issuer_wallet, proof_no, proof_payload, proof_validated, proof_threshold,
                    operator_wallet, operator_user_id, points_base, points_bonus, points_capped
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    req.wallet, role["key"], role["name"], action, points, "", now(),
                    issuer_wallet,
                    proof_no,
                    json.dumps(proof, ensure_ascii=False) if proof else None,
                    1 if (pr["ok"] and not req.force) else 0,
                    pr.get("threshold") or "",
                    operator_wallet, operator_user_id,
                    int(pdetail.get("base") or 0), int(pdetail.get("bonus") or 0),
                    1 if pdetail.get("capped") else 0,
                ),
            )
            record_id = cur.lastrowid
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
    # mint revert 且链上白名单缺该发行方 → 自动补授后重试
    # （修「密钥库轮换 / 链重置后持续 revert」：首次失败即自愈，无需人工介入）
    if not r.get("ok") and _try_repair_issuer(c, ge_addr, ge_abi, "GreenEnergy", issuer_wallet):
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

    # 5. 回填 tx_hash 完成占位行的双写闭环（链上 + 业务账本）+ 能量流水入账
    with _DB_LOCK, get_conn() as conn:
        conn.execute(
            "UPDATE eco_energy_records SET tx_hash=? WHERE proof_no=? AND role_key=?",
            (tx_hash, proof_no, role["key"]),
        )
        # 余额 = Σ 流水：发行入账与链上 mint 同生命周期（mint 失败时不写流水）
        _ensure_flow(conn, wallet=req.wallet, kind=FLOW_ISSUE, amount=points,
                     ref=f"energy:{record_id}", note=action, role_key=role["key"])

    _track(EventType.ECO_ENERGY_ISSUE, target=role["key"], ref_id=proof_no, wallet=req.wallet,
           extra={"role": role["name"], "points": points, "action": action,
                  "base": pdetail.get("base"), "bonus": pdetail.get("bonus"),
                  "capped": bool(pdetail.get("capped"))})

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
        # 计价明细（为什么是这个点数）与发行授信余量，前端直接展示不另算
        "points_detail": pdetail,
        "energy_quota": quota,
        "quota_used": quota_used,
        "quota_remaining": (quota - quota_used - points) if quota > 0 else -1,
        "operator_wallet": operator_wallet,   # 真实操作人（个人钱包扮演机构时留痕）
        "contract": ge_addr,
        "method": "GreenEnergy.mint(to,value,reason)",
        "pipeline": _pipeline,
    }


@router.get("/energy/records")
def energy_records(
    wallet: str,
    limit: int = 50,
    by: str = "receiver",
    role_key: str = "",
    user: dict = Depends(get_current_user),
):
    """绿色能量发放台账（只读接口需登录，学生仅限本人 / 本人候选集内的演示钱包）。

    同一张 eco_energy_records 有两个视角，谁办事就看谁的账：
    - `by=receiver`（默认）：钱包作为**接收方**的获取记录 —— 普通用户「我的能量从哪来」；
    - `by=issuer`：钱包作为**发行方组织钱包**的发放记录 —— 业务节点「本节点发行了多少、
      发给了哪些居民」。
      记录的 `wallet` 是接收居民地址、`issuer_wallet` 才是节点组织钱包，节点若用默认
      口径查自己，结果恒为空表（发行方看不到自己的发行列表）。
    `total_points` 由 SQL 聚合得出，不受 limit 截断，前端汇总条直接用。
    """
    wallet = _ensure_viewable_wallet(user, wallet, "wallet")
    marks, params = _wallet_marks(wallet)
    col = "issuer_wallet" if (by or "").strip().lower() == "issuer" else "wallet"
    where = f"lower({col}) IN ({marks})"
    rk = (role_key or "").strip().lower()
    if rk:
        where += " AND lower(role_key)=?"
        params = params + [rk]
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM eco_energy_records WHERE {where} ORDER BY id DESC LIMIT ?",
            (*params, max(1, min(int(limit or 50), 200))),
        ).fetchall()
        agg = conn.execute(
            f"SELECT COALESCE(SUM(points),0) AS pts, COUNT(1) AS cnt "
            f"FROM eco_energy_records WHERE {where}",
            params,
        ).fetchone()
    items = [dict(r) for r in rows]
    for d in items:
        # 两侧地址显式命名，前端按视角取列，不再靠 wallet 一列两头解释
        d["receiver_wallet"] = d.get("wallet") or ""
        d["issuer_wallet"] = d.get("issuer_wallet") or ""
    return {
        "items": items,
        "by": "issuer" if col == "issuer_wallet" else "receiver",
        "wallet": wallet,
        "total_points": int(agg["pts"] or 0) if agg else 0,
        "total_count": int(agg["cnt"] or 0) if agg else 0,
    }


@router.get("/energy/flows")
def energy_flows(wallet: str, limit: int = 100, user: dict = Depends(get_current_user)):
    """绿色能量流水账（余额的唯一事实源）：逐笔展示发行 / 兑换回收 / 市场买卖 / 销毁。"""
    wallet = _ensure_viewable_wallet(user, wallet, "wallet")
    w = _norm_wallet(wallet)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM eco_energy_flows WHERE lower(wallet)=? ORDER BY id DESC LIMIT ?",
            (w, limit),
        ).fetchall()
        items = []
        for r in rows:
            d = dict(r)
            d["kind_label"] = FLOW_LABELS.get(d.get("kind") or "", d.get("kind") or "")
            items.append(d)
        balance = max(0, _flow_balance(conn, w))
    return {"wallet": w, "balance": balance, "items": items}


@router.get("/energy/balance")
def energy_balance(wallet: str, user: dict = Depends(get_current_user)):
    """查询钱包绿色能量余额（统一视图：账本为事实源 + 链上余额与待同步差额）。

    旧返回体只有 balance 一个数字，钱包页与联盟页各自另取口径（一个读链上、一个读
    账本），同一个人在两个页面看到两个余额。现在两侧共用 `_energy_balance_view`，
    额外带上 ledger_balance / chain_balance / needs_sync，前端只渲染不再自行取数。
    """
    wallet = _ensure_viewable_wallet(user, wallet, "wallet")
    view = _energy_balance_view(wallet)
    return {"wallet": view["wallet"], "balance": str(view["balance"]), **view}


class ReconcileChainReq(BaseModel):
    """能量对账请求体（治理动作）。wallet 只是办事身份，缺省用国库账户。"""
    wallet: str = ""


@router.post("/energy/reconcile-chain")
def reconcile_chain_balance(req: ReconcileChainReq, user: dict = Depends(get_current_user)):
    """能量对账：把账本余额全量补齐到链上（联盟治理动作，仅教师 / 平台管理员）。

    背景：本地沙盒链（py-evm）每次重启后链上余额全清零，而能量账本在 SQLite 里
    是持久的；不重建就会出现「联盟页有能量、钱包页是 0、兑换报 GE: insufficient
    balance」。启动时会自动对一次（见 main.lifespan），本端点供管理员手动触发并
    查看逐钱包结果（只补差额，不改账本、不重复计入发行量）。
    """
    req.wallet = assert_actor_wallet(user, req.wallet or TREASURY_WALLET)
    _ensure_governor(user, "能量国库对账")
    ensure_capability(_identity_role(req.wallet), CAP_TREASURY_MANAGE)
    return align_chain_balances()


# ===========================================================================
# 4. 树种管理
# ===========================================================================
@router.get("/trees")
def list_trees():
    """返回所有树种列表（含 ERC721 项目发行额度：额度 / 已发行 / 剩余，前端据此展示售罄）。"""
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM eco_tree_species ORDER BY id DESC").fetchall()
    items = []
    for r in rows:
        d = dict(r)
        supply = int(d.get("supply") or 0)
        issued = int(d.get("issued") or 0)
        d["issued"] = issued
        d["supply"] = supply
        d["remaining"] = (supply - issued) if supply > 0 else -1   # -1 = 不限额（存量兼容）
        d["sold_out"] = supply > 0 and issued >= supply
        items.append(d)
    return {"items": items}


@router.post("/trees/add")
def add_tree(req: TreeAddReq, user: dict = Depends(get_current_user)):
    """管理员新增树种（ERC721 植树证书的发行目录，同时备案项目发行额度）。"""
    req.wallet = assert_actor_wallet(user, req.wallet)  # 操作者身份从 JWT 解析
    # 职能硬拦：树种目录与发行额度属「治理」维度，仅管理员（0xadmin 或扮演 admin 的钱包），
    # 且登录账号必须是教师 / 平台管理员（治理权不随钱包走，修 B12）
    _ensure_governor(user, "树种目录维护")
    ensure_capability(_identity_role(req.wallet), CAP_CATALOG_MANAGE)
    if req.required_energy < 1000:
        raise HTTPException(400, "树种所需能量不能少于 1000")
    if req.supply < 0:
        raise HTTPException(400, "发行额度 supply 不能为负（0 = 不限额，仅用于存量兼容）")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO eco_tree_species(name,required_energy,image_url,description,created_by,created_at,"
            "supply,issued,status) VALUES(?,?,?,?,?,?,?,0,'active')",
            (req.name, req.required_energy, req.image_url, req.description, req.wallet,
             now(), req.supply),
        )
        tree_id = cur.lastrowid
    return {"ok": True, "id": tree_id, "supply": req.supply, "issued": 0}


class TreeUpdateReq(BaseModel):
    wallet: str
    species_id: int
    supply: Optional[int] = None      # 项目发行额度：只可上调
    status: Optional[str] = None      # active | off（下架不可兑，不影响已发证书）


@router.post("/trees/update")
def update_tree(req: TreeUpdateReq, user: dict = Depends(get_current_user)):
    """治理：上调植树证书的项目发行额度 / 下架树种（已发行证书不可变）。"""
    req.wallet = assert_actor_wallet(user, req.wallet)
    _ensure_governor(user, "发行额度与树种目录治理")
    ensure_capability(_identity_role(req.wallet), CAP_CATALOG_MANAGE)
    if req.supply is None and req.status is None:
        raise HTTPException(400, "请至少指定 supply（发行额度）或 status（active/off）")
    if req.status is not None and req.status not in ("active", "off"):
        raise HTTPException(400, "status 仅支持 active / off")
    with _DB_LOCK, get_conn() as conn:
        row = dict(conn.execute("SELECT * FROM eco_tree_species WHERE id=?",
                                (req.species_id,)).fetchone() or {})
        if not row:
            raise HTTPException(404, "树种不存在")
        issued = int(row.get("issued") or 0)
        if req.supply is not None:
            if int(req.supply) < 0:
                raise HTTPException(400, "发行额度不能为负")
            if 0 < int(req.supply) < issued:
                raise HTTPException(
                    400,
                    f"发行额度只可上调：「{row['name']}」已发行 {issued} 张证书，"
                    f"下调额度会使链上存量事实超发。",
                )
        sets: list = []
        params: list = []
        if req.supply is not None:
            sets.append("supply=?")
            params.append(int(req.supply))
        if req.status is not None:
            sets.append("status=?")
            params.append(req.status)
        params.append(req.species_id)
        conn.execute(f"UPDATE eco_tree_species SET {', '.join(sets)} WHERE id=?", params)
        row2 = dict(conn.execute("SELECT * FROM eco_tree_species WHERE id=?",
                                 (req.species_id,)).fetchone() or {})
    supply = int(row2.get("supply") or 0)
    issued = int(row2.get("issued") or 0)
    return {"ok": True, "id": req.species_id, "supply": supply, "issued": issued,
            "remaining": (supply - issued) if supply > 0 else -1,
            "sold_out": supply > 0 and issued >= supply,
            "status": row2.get("status") or "active"}


# ===========================================================================
# 5. 植树证书兑换（ERC721 · 居民专属兑换 + 项目额度约束）
# ===========================================================================
@router.post("/certificates/exchange")
def exchange_certificate(req: CertExchangeReq, user: dict = Depends(get_current_user)):
    """居民花费绿色能量兑换植树证书（一证一树，额满即售罄）。

    四维度口径：本接口属「兑换绿色资产」，只对居民（普通用户）开放；联盟节点与
    国库账户不得兑换（否则就是发行方凭自己的组织钱包兑自己发的资产，左手发右手收）。
    能量记账：居民 → 国库（不是凭空消失），证书由碳汇方（管理员）在链上签发。
    """
    req.wallet = assert_actor_wallet(user, req.wallet)  # 兑换者身份从 JWT 解析
    ensure_capability(_identity_role(req.wallet), CAP_ASSET_EXCHANGE)
    # 1. 查找树种信息
    with get_conn() as conn:
        tree = conn.execute(
            "SELECT * FROM eco_tree_species WHERE id=?",
            (req.species_id,),
        ).fetchone()
    if not tree:
        raise HTTPException(404, "树种不存在")
    if (tree["status"] or "active") != "active":
        raise HTTPException(400, f"树种「{tree['name']}」已下架，暂不可兑换")
    cost = int(tree["required_energy"])

    # 1.5 ERC721 发行额度占位（修 B8：旧表无额度字段，任何树可无限铸造）
    #     占位用「UPDATE ... WHERE issued < supply」的原子语句，并发下不会超发；
    #     后续链上步骤失败时回滚占位，额度不会白耗。
    with _DB_LOCK, get_conn() as conn:
        reserved = conn.execute(
            "UPDATE eco_tree_species SET issued = issued + 1 "
            "WHERE id=? AND status='active' AND (supply <= 0 OR issued < supply)",
            (req.species_id,),
        ).rowcount
        if not reserved:
            row = dict(conn.execute("SELECT supply, issued FROM eco_tree_species WHERE id=?",
                                    (req.species_id,)).fetchone() or {})
            raise HTTPException(
                400,
                f"「{tree['name']}」植树证书发行额度已满：已发行 {int(row.get('issued') or 0)} / "
                f"额度 {int(row.get('supply') or 0)}（一证一树，额满即售罄）。"
                f"请由管理员在树种目录上调项目额度，或选择其他在册树种。",
            )

    try:
        # 2. 查找 GreenEnergy 合约（取址唯一口径：latest_deployed）
        ge_addr, ge_abi = _find_contract("GreenEnergy")
        if not ge_addr:
            raise HTTPException(400, "GreenEnergy 合约在当前链上不可用（链已重置或尚未部署），"
                                     "请联盟管理员重新部署后重试")

        c = get_chain_client()
        admin_addr = c.resolve_account(ADMIN_ALIAS)

        # 2.5 扣能前的能量保障：账本余额校验 + 回填链上 + 硬校验（失败给可诊断中文）
        _require_chain_balance(req.wallet, cost, "兑换植树证书")

        # 3. 调用 GreenEnergy.transfer(admin, cost) 从 wallet 转给能量国库
        r_transfer = c.call_contract(
            ge_addr, "transfer",
            [admin_addr, cost],
            req.wallet, ge_abi,
        )
        if not r_transfer.get("ok"):
            raise HTTPException(400, "能量扣除失败: "
                                     + _chain_deduct_hint(req.wallet, cost, r_transfer))

        # 4. 查找 PlantCertificate 合约
        pc_addr, pc_abi = _find_contract("PlantCertificate")
        if not pc_addr:
            raise HTTPException(400, "PlantCertificate 合约未部署")

        # 5. 生成唯一 token_id（uuid 前 32 位整数）
        token_id = uuid.uuid4().int & 0xFFFFFFFF
        uri = f"pc://{token_id}"

        # 6. 调用 PlantCertificate.mint(wallet, token_id, species_id, uri) 从碳汇方发起
        r_mint = c.call_contract(
            pc_addr, "mint",
            [c.resolve_account(req.wallet), token_id, req.species_id, uri],
            ADMIN_ALIAS, pc_abi,
        )
        if not r_mint.get("ok"):
            # 能量已入国库但证书未铸成：必须由国库原路退回，不能让居民白付能量
            back = _compensate_energy(c, ge_addr, ge_abi, ADMIN_ALIAS,
                                      c.resolve_account(req.wallet), cost)
            raise HTTPException(
                400,
                "证书铸造失败: " + str(r_mint.get("error", ""))
                + ("（已扣能量由国库原路退回）" if back
                   else "（能量退回失败，请联系联盟管理员凭交易凭证处理）"),
            )
        tx_hash = r_mint.get("tx_hash", "")

        # 7. 生成唯一证书编号 PC-YYYYMMDD-XXXX
        date_str = datetime.now().strftime("%Y%m%d")
        cert_no = f"PC-{date_str}-{uuid.uuid4().hex[:4].upper()}"
    except HTTPException:
        # 任何一步失败都要归还额度（否则失败一次就白耗 1 份，统计与链上不一致）
        _refund_species_quota(req.species_id)
        raise

    # 8. 记录到 eco_certificates 表 + 能量流水双写（居民出账 / 国库入账）
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO eco_certificates(token_id,species_id,species_name,owner,exchanged_by,"
            "cost_energy,contract_address,tx_hash,cert_no,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (str(token_id), req.species_id, tree["name"], req.wallet, req.wallet, cost,
             pc_addr, tx_hash, cert_no, now()),
        )
        _record_exchange_cost(conn, wallet=req.wallet, cost=cost, kind_prefix="cert",
                              obj_id=cur.lastrowid, note=f"植树证书 · {tree['name']}")
    _track(EventType.ECO_CERT_EXCHANGE, target=tree["name"], ref_id=cert_no, wallet=req.wallet,
           extra={"species_id": req.species_id, "cost": cost, "token_id": str(token_id)})
    with get_conn() as conn:
        used = dict(conn.execute("SELECT issued, supply FROM eco_tree_species WHERE id=?",
                                 (req.species_id,)).fetchone() or {})
    supply_n = int(used.get("supply") or 0)
    issued_n = int(used.get("issued") or 0)
    return {"ok": True, "token_id": str(token_id), "cert_no": cert_no, "tx_hash": tx_hash,
            "cost_energy": cost, "standard": "ERC721",
            "quota": {"supply": supply_n, "issued": issued_n,
                      "remaining": (supply_n - issued_n) if supply_n > 0 else -1}}


@router.get("/certificates/list")
def list_certificates(owner: str, user: dict = Depends(get_current_user)):
    """返回植树证书列表（P1-27：只读接口同样需登录，学生仅限本人或本人扮演的角色）。"""
    owner = _ensure_viewable_wallet(user, owner, "owner")
    marks, params = _wallet_marks(owner)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM eco_certificates WHERE lower(owner) IN ({marks}) ORDER BY id DESC",
            params,
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


# ===========================================================================
# 6. 生态勋章 / 骑行券兑换
# ===========================================================================
@router.post("/badges/exchange")
def exchange_badge(req: BadgeExchangeReq, user: dict = Depends(get_current_user)):
    """居民花费绿色能量兑换生态勋章 / 骑行券（ERC1155 · 同类可多份）。

    四维度口径：本接口属「兑换绿色资产」，仅对居民开放；能量从居民转入国库（可审计），
    资产由**该类型的发行方节点**在链上签发（骑行券 = 共享单车节点，而不是管理员代签），
    否则「谁发行、谁兑付」的义务关系在链上对不上（修 B10 发行方口径两套）。
    """
    req.wallet = assert_actor_wallet(user, req.wallet)  # 兑换者身份从 JWT 解析
    ensure_capability(_identity_role(req.wallet), CAP_ASSET_EXCHANGE)
    qty = int(req.quantity or 1)
    if qty <= 0:
        raise HTTPException(400, "兑换数量必须大于 0")
    with get_conn() as conn:
        bt = _get_badge_type(conn, type_id=req.type_id, badge_type=req.badge_type)
    if not bt:
        raise HTTPException(400, f"未知勋章类型: {req.badge_type}（type_id={req.type_id}）")
    cost = int(bt["cost_energy"]) * qty          # 同类多份：成本按份数乘以单价
    token_id = int(bt["token_id"])
    badge_name = bt["name"]
    bt_id = bt["id"]
    issuer_role = bt["issuer_role"] or ""
    # 发行方节点的链上身份（ERC1155 mint 的 FROM）；旧数据 issuer_role 为空时回退国库代签
    issuer_wallet = wallet_address(issuer_role) if issuer_role else ""
    issuer_wallet = issuer_wallet or _norm_wallet(ADMIN_ALIAS)

    # 0. ERC1155 发行额度原子占位（修「先查后改」的超发窗口），失败回滚
    if not _reserve_badge_quota(bt_id, qty):
        raise HTTPException(
            400,
            f"「{badge_name}」发行量不足：上限 {int(bt['supply'])}，已铸 {int(bt['minted'])}，"
            f"本次需 {qty} 份。请等待发行方节点补发或下调数量。",
        )

    try:
        # 1. 查找 GreenEnergy 合约（取址唯一口径：latest_deployed）
        ge_addr, ge_abi = _find_contract("GreenEnergy")
        if not ge_addr:
            raise HTTPException(400, "GreenEnergy 合约在当前链上不可用（链已重置或尚未部署），"
                                     "请联盟管理员重新部署后重试")

        c = get_chain_client()
        admin_addr = c.resolve_account(ADMIN_ALIAS)

        # 1.5 扣能前的能量保障：账本余额校验 + 回填链上 + 硬校验（失败给可诊断中文）
        _require_chain_balance(req.wallet, cost, f"兑换「{badge_name}」")

        # 2. 能量回收：调用 GreenEnergy.transfer(国库, cost) 从 wallet 转出
        r_transfer = c.call_contract(
            ge_addr, "transfer",
            [admin_addr, cost],
            req.wallet, ge_abi,
        )
        if not r_transfer.get("ok"):
            raise HTTPException(400, "能量扣除失败: "
                                     + _chain_deduct_hint(req.wallet, cost, r_transfer))

        # 3. 查找 EcoBadge 合约，由该类型的发行方节点 mint 到居民钱包（amount = 份数）
        eb_addr, eb_abi = _find_contract("EcoBadge")
        if not eb_addr:
            raise HTTPException(400, "EcoBadge 合约未部署")
        r_mint = c.call_contract(
            eb_addr, "mint",
            [c.resolve_account(req.wallet), token_id, qty, bt["image_url"] or ""],
            issuer_wallet, eb_abi,
        )
        # EcoBadge.mint revert 且链上白名单缺该发行方 → 自动补授后重试
        # （此时能量已转入国库但未退回，补授成功则继续铸造，无需用户感知）
        if not r_mint.get("ok") and _try_repair_issuer(c, eb_addr, eb_abi, "EcoBadge", issuer_wallet):
            r_mint = c.call_contract(
                eb_addr, "mint",
                [c.resolve_account(req.wallet), token_id, qty, bt["image_url"] or ""],
                issuer_wallet, eb_abi,
            )
        if not r_mint.get("ok"):
            # 同上：能量已在链上转进国库，铸造失败时必须回滚，否则居民白付
            back = _compensate_energy(c, ge_addr, ge_abi, ADMIN_ALIAS,
                                      c.resolve_account(req.wallet), cost)
            raise HTTPException(
                400,
                f"勋章铸造失败（发行方 {issuer_wallet}）: {r_mint.get('error', '')}"
                f"。若提示无发行权限，请确认【{issuer_role or '管理员'}】已在合约发行白名单内。"
                + ("（已扣能量由国库原路退回）" if back
                   else "（能量退回失败，请联系联盟管理员凭交易凭证处理）"),
            )
        tx_hash = r_mint.get("tx_hash", "")
    except HTTPException:
        _refund_badge_quota(bt_id, qty)  # 链上未成 → 归还已占额度（含能量转账已回滚的情形）
        raise

    # 4. 记账：本次兑换一行（含份数）+ 能量流水双写（居民出账 / 国库入账）
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO eco_badges(token_id,badge_type,name,owner,exchanged_by,cost_energy,"
            "issued_by,issuer_role,contract_address,tx_hash,created_at,quantity) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (token_id, bt["badge_type"], badge_name, req.wallet, req.wallet, cost,
             issuer_wallet, issuer_role, eb_addr, tx_hash, now(), qty),
        )
        _record_exchange_cost(conn, wallet=req.wallet, cost=cost, kind_prefix="badge",
                              obj_id=cur.lastrowid, note=f"{badge_name} ×{qty}")
    _track(EventType.ECO_BADGE_EXCHANGE, target=badge_name, ref_id=str(token_id), wallet=req.wallet,
           extra={"badge_type": bt["badge_type"], "type_id": req.type_id, "cost": cost, "qty": qty})
    return {"ok": True, "badge_type": bt["badge_type"], "type_id": bt_id, "tx_hash": tx_hash,
            "badge_id": cur.lastrowid, "quantity": qty, "cost_energy": cost,
            "standard": "ERC1155", "issued_by": issuer_wallet}


@router.get("/badges/list")
def list_badges(owner: str, by: str = "owner", user: dict = Depends(get_current_user)):
    """勋章 / 骑行券列表（含 ERC1155 份数；只读接口需登录）。

    两个视角（与能量台账同构，发行方要能看见自己放出去的资产）：
    - `by=owner`（默认）：当前钱包**持有**的份数 —— 居民「我的勋章 / 骑行券」；
    - `by=issued`：当前钱包作为**发行方组织钱包**（`issued_by`）发行 / 发放出去的清单
      —— 业务节点铸造入口的闭环反馈（谁发行、谁负责、谁兑付）。
      `source` 区分两条发行链路：有 `exchanged_by` = 居民消耗能量兑换，否则 = 联盟铸造发放。
    """
    owner = _ensure_viewable_wallet(user, owner, "owner")
    marks, params = _wallet_marks(owner)
    col = "issued_by" if (by or "").strip().lower() == "issued" else "owner"
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM eco_badges WHERE lower({col}) IN ({marks}) ORDER BY id DESC",
            params,
        ).fetchall()
    items = [dict(r) for r in rows]
    # 聚合视图：同一 token_id 的总持有份数（前端「我的勋章」按协议形态汇总展示）
    held: dict = {}
    for d in items:
        k = int(d.get("token_id") or 0)
        held[str(k)] = held.get(str(k), 0) + int(d.get("quantity") or 1)
    for d in items:
        d["total_held"] = held.get(str(int(d.get("token_id") or 0)), 0)
        d["source"] = (
            "mint"
            if not (d.get("exchanged_by") or "") and not int(d.get("cost_energy") or 0)
            else "exchange"
        )
    return {"items": items, "by": "issued" if col == "issued_by" else "owner"}


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
    """联盟发行节点新增 / 维护勋章、骑行券类型定义（ERC1155 半同质化，同类可多份）。

    职能口径（修 B4 / B5）：
    - 类型的 **发行方恒为当前操作者的节点角色**（issuer_role = 当前角色），因为「谁发行、谁铸造、
      谁兑付」必须一人到底；旧实现允许管理员建类型，但管理员无铸造职能 → 建出来永远铸不了（死数据）；
    - 骑行券（voucher）全平台仅一份、仅共享单车节点可维护（它是兑付义务人）；
    - 发行上限只可上调不可下调（下调会让已铸量 > 上限，链上存量变成事实超发）。
    """
    req.wallet = assert_actor_wallet(user, req.wallet)  # 操作者身份从 JWT 解析
    if req.badge_type not in ("badge", "voucher"):
        raise HTTPException(400, "badge_type 必须是 badge 或 voucher")
    if req.cost_energy <= 0:
        raise HTTPException(400, "所需能量值必须大于 0")
    if req.supply <= 0:
        raise HTTPException(400, "发行数量（supply）必须大于 0")

    role = _identity_role(req.wallet)
    if not role:
        raise HTTPException(403, "操作者未选择联盟角色：请先在「绿色低碳联盟链」页面选择角色后再新增")
    if req.badge_type == "voucher":
        ensure_capability(role, CAP_ASSET_ISSUE_VOUCHER)
        ensure_bike_for_voucher(role["key"], action="add")
    else:
        ensure_capability(role, CAP_ASSET_ISSUE_BADGE)

    with get_conn() as conn:
        if req.badge_type == "voucher":
            # 骑行券固定 token_id=2，全平台仅维护一份
            exist = conn.execute(
                "SELECT id, supply, minted FROM eco_badge_types "
                "WHERE badge_type='voucher' ORDER BY id ASC LIMIT 1"
            ).fetchone()
            if exist:
                minted = int(exist["minted"] or 0)
                if int(req.supply) < minted:
                    raise HTTPException(
                        400,
                        f"骑行券发行上限只可上调不可下调：已铸造 {minted} 份，"
                        f"新上限 {req.supply} 会使链上存量事实超发。",
                    )
                conn.execute(
                    "UPDATE eco_badge_types SET name=?, icon=?, image_url=?, cost_energy=?, "
                    "supply=?, issuer_role=?, desc=? WHERE id=?",
                    (req.name, req.icon, req.image_url, req.cost_energy, req.supply,
                     role["key"], req.desc, exist["id"]),
                )
                return {"ok": True, "id": exist["id"], "updated": True,
                        "token_id": 2, "badge_type": "voucher", "issuer_role": role["key"]}
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
    return {"ok": True, "id": cur.lastrowid, "token_id": token_id,
            "badge_type": req.badge_type, "issuer_role": role["key"]}


@router.post("/badges/mint")
def mint_badge(req: BadgeMintReq, user: dict = Depends(get_current_user)):
    """联盟发行节点铸造发放勋章 / 骑行券给居民（ERC1155 mint，链上 FROM = 发行节点钱包）。

    与「居民兑换」的区别（资产发行的两条链路）：
    - 兑换（/badges/exchange）：居民花自己的能量，能量回收进国库，资产由发行方节点签发；
    - 铸造发放（本接口）：节点主动运营投放（企业激励），不消耗居民能量，但仍占用类型发行额度。

    职能：仅具备「该资产发行权」的联盟节点可执行（管理员与居民 403）；
    接收方必须是居民钱包，节点不能给自己铸（否则形成无对价资产）。
    """
    role = _find_role(req.role_key)
    if not role:
        raise HTTPException(400, f"未知角色: {req.role_key}")
    req.wallet = assert_actor_wallet(user, req.wallet)  # 操作者身份从 JWT 解析
    if not req.wallet:
        raise HTTPException(400, "操作者钱包 wallet 必填")
    if req.quantity <= 0:
        raise HTTPException(400, "铸造数量必须大于 0")

    # 权限：操作者当前身份必须与声明角色一致（普通居民无铸造能力）
    ensure_minter_role(role, _identity_role(req.wallet))
    ensure_wallet_role_binding(req.wallet, role["key"])
    if not req.to_wallet:
        raise HTTPException(400, "接收者钱包 to_wallet 必填")
    if _norm_wallet(req.to_wallet) == _norm_wallet(req.wallet):
        raise HTTPException(400, "接收者不能是操作者本人钱包：自铸资产没有对价，也不服务任何居民行为")
    if role_of_alliance_wallet(_norm_wallet(req.to_wallet)):
        raise HTTPException(
            400,
            f"接收方 {req.to_wallet} 是联盟组织钱包 / 国库账户：绿色资产只能发放给居民钱包，"
            f"节点之间互相倒手不产生任何低碳行为价值。",
        )

    # 接收方归属统一为真实地址（写入 eco_badges.owner 前归一，避免别名入资产表）
    req.to_wallet = to_address(req.to_wallet, create=True)

    with get_conn() as conn:
        bt = _get_badge_type(conn, type_id=req.type_id)
    if not bt:
        raise HTTPException(400, f"未知勋章类型 type_id={req.type_id}")
    # 职能硬拦：骑行券仅 bike（它是兑付义务人）；勋章仅具备铸造职能的业务节点
    if bt["badge_type"] == "voucher":
        ensure_capability(role, CAP_ASSET_ISSUE_VOUCHER)
        ensure_bike_for_voucher(role["key"], action="mint")
    else:
        ensure_capability(role, CAP_ASSET_ISSUE_BADGE)
    # 类型的发行方与操作角色必须一致（地铁节点不能代公交节点发它自己的勋章）
    owner_role = bt["issuer_role"] or ""
    if owner_role and owner_role != role["key"]:
        raise HTTPException(
            403,
            f"「{bt['name']}」的发行方是【{(find_role(owner_role) or {}).get('name', owner_role)}】，"
            f"【{role['name']}】不能代其铸造（谁发行、谁负责）。",
        )

    # 发行额度原子占位（同兑换路径，避开并发超发）
    if not _reserve_badge_quota(bt["id"], int(req.quantity)):
        raise HTTPException(
            400,
            f"「{bt['name']}」发行量上限 {bt['supply']}，已铸造 {bt['minted']}，"
            f"剩余可铸造 {max(0, int(bt['supply']) - int(bt['minted']))}，本次请求 {req.quantity}",
        )

    eb_addr, eb_abi = _find_contract("EcoBadge")
    if not eb_addr:
        _refund_badge_quota(bt["id"], int(req.quantity))
        raise HTTPException(400, "EcoBadge 合约未部署")

    c = get_chain_client()
    issuer_wallet = wallet_address(role["key"])
    try:
        r = c.call_contract(
            eb_addr, "mint",
            [c.resolve_account(req.to_wallet), int(bt["token_id"]), int(req.quantity),
             bt["image_url"] or ""],
            issuer_wallet, eb_abi,
        )
        # EcoBadge mint 失败且链上白名单缺该发行方 → 自动补授后重试
        if not r.get("ok") and _try_repair_issuer(c, eb_addr, eb_abi, "EcoBadge", issuer_wallet):
            r = c.call_contract(
                eb_addr, "mint",
                [c.resolve_account(req.to_wallet), int(bt["token_id"]), int(req.quantity),
                 bt["image_url"] or ""],
                issuer_wallet, eb_abi,
            )
        if not r.get("ok"):
            raise HTTPException(400, f"铸造失败（交易发起方 {issuer_wallet}）: {r.get('error','')}")
    except HTTPException:
        _refund_badge_quota(bt["id"], int(req.quantity))  # 链上未成 → 归还已占额度
        raise
    tx_hash = r.get("tx_hash", "")

    # 落库：一行 = 一次发放（quantity 记份数）；发行方 / 签发钱包随资产长期留存，
    # exchanged_by 留空（无对价投放，不消耗居民能量，故不写能量流水）
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO eco_badges(token_id,badge_type,name,owner,cost_energy,issued_by,"
            "issuer_role,contract_address,tx_hash,created_at,quantity) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (int(bt["token_id"]), bt["badge_type"], bt["name"], req.to_wallet, 0,
             issuer_wallet, role["key"], eb_addr, tx_hash, now(), int(req.quantity)),
        )
        badge_id = cur.lastrowid
    _track(EventType.BADGE_MINT, target=bt["badge_type"], wallet=req.wallet or "",
           extra={"type_id": bt["id"], "to": req.to_wallet, "qty": req.quantity,
                  "issued_by": issuer_wallet})
    with get_conn() as conn:
        row = _get_badge_type(conn, type_id=bt["id"]) or {}
    return {"ok": True, "badge_id": badge_id, "badge_type": bt["badge_type"],
            "type_id": bt["id"], "to": req.to_wallet, "quantity": int(req.quantity),
            "tx_hash": tx_hash, "issued_by": issuer_wallet, "issuer_role": role["key"],
            "standard": "ERC1155",
            "quota": {"supply": int(row.get("supply") or 0), "minted": int(row.get("minted") or 0)}}


# ===========================================================================
# 7. 操作错误/行为记录（供实训报告做打分与错误分析）
# ===========================================================================
def _ensure_viewable_wallet(user: dict, provided: str, field: str = "wallet") -> str:
    """eco 只读接口的可见性判定：本人候选集 ∪ 平台内置联盟角色/演示钱包。

    与写侧 `assert_actor_wallet` 保持同一口径（否则学生一切到「地铁集团」就
    发现自己刚做完全链上操作、却 403 看不到日志）。内置钱包是公开演示身份，
    不携带某个学生的个资；但**其他学生的真实钱包**仍只能走 ensure_own_wallet
    → 403（P1-27 要修的是「未登录匿名全表开放」，不是把教学场景拦死）。

    返回值一律是**真实链上地址**：资产表已按地址归属，把别名原样递给下游
    等值查询（WHERE owner=?）就会出现「刚兑换完却看不到自己的证书」。
    需要兼容未迁移的历史行时，调用方用 `_wallet_marks()` 双口径查询。
    """
    p = (provided or "").strip()
    pl = p.lower()
    if pl and (pl in BUILTIN_WALLETS or pl in builtin_addresses()):
        return _norm_wallet(p) or p
    w = ensure_own_wallet(user, p, field)
    return _norm_wallet(w) or w


@router.post("/errors/record")
def record_error(req: OpErrorRecordReq, user: dict = Depends(get_current_user)):
    """前端在操作成功/失败时都可写入审计记录，level=success/info/warn/error。

    P1-26：除 `wallet`（操作发生时的**业务钱包**，可能是联盟角色钱包，也可能是
    被操作对象）外，额外记 `actor_wallet` / `actor_user_id`（登录身份），扣分
    统计才能回答“这事到底是谁干的”，而不是把行政角色发的能量失误算到学生头上。
    P1-27：detail / message 入库前先脱敏（前端会 JSON.stringify 整个错误对象，
    里面常带 Authorization: Bearer <JWT>）。
    """
    req.wallet = assert_actor_wallet(user, req.wallet)  # 审计归属以登录身份为准
    if req.level not in ("info", "success", "warn", "error"):
        raise HTTPException(400, "level 非法")
    if req.module not in ("role", "energy", "tree", "certificate", "badge", "contract", "other"):
        raise HTTPException(400, "module 非法")
    actor_wallet = _norm_wallet(user.get("wallet") or user.get("user_id") or "")
    actor_user_id = (user.get("user_id") or "").strip()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO eco_operation_logs(wallet,module,action,level,message,detail,created_at,"
            "actor_wallet,actor_user_id) VALUES(?,?,?,?,?,?,?,?,?)",
            (req.wallet, req.module, req.action, req.level,
             redact_secrets(req.message or "")[:500],
             redact_secrets(req.detail or "")[:2000], now(),
             actor_wallet, actor_user_id),
        )
    return {"ok": True, "id": cur.lastrowid}


@router.get("/errors/list")
def list_errors(
    wallet: str = "",
    limit: int = 200,
    user: dict = Depends(get_current_user),
):
    """查询操作日志（P1-27：从此需登录，不再匿名全表开放）。

    - 教师 / 管理员：传 wallet 按钱包（候选集口径，P0-2）过滤，不传返回全部；
    - 学生：只能看与本人相关的行（actor_wallet / actor_user_id 命中，或存量
      actor 为空但 wallet 属于本人候选集）；wallet 参数指向他人 → 403。
    回显前对 detail / message 再过一道 redact_secrets（存量未清洗行兜底）。
    """
    try:
        limit = max(1, min(int(limit or 200), 1000))
    except (TypeError, ValueError):
        limit = 200
    role = int(user.get("role_id") or 0)
    my_uid = (user.get("user_id") or "").strip()
    req_w = (wallet or "").strip()
    with get_conn() as conn:
        if role in PRIVILEGED_ROLES:
            if req_w:
                cands = resolve_wallet_candidates(conn, req_w, "")
                h, lp = lower_wallet_in(cands)
                rows = conn.execute(
                    "SELECT * FROM eco_operation_logs"
                    f" WHERE lower(wallet) IN ({h})"
                    f" OR lower(COALESCE(actor_wallet, '')) IN ({h})"
                    " ORDER BY id DESC LIMIT ?",
                    (*lp, *lp, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM eco_operation_logs ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
        else:
            # 学生：本人相关行；以联盟角色身份（内置钱包）操作时，该角色钱包的
            # 日志也一并可见（他刚刚就是拿这个身份在链上做事）
            view_w = _ensure_viewable_wallet(user, req_w)
            cands = resolve_wallet_candidates(
                conn, view_w or (user.get("wallet") or ""), my_uid
            )
            h, lp = lower_wallet_in(cands)
            if not lp:
                return {"items": [], "total": 0, "error_count": 0,
                        "warn_count": 0, "success_count": 0}
            rows = conn.execute(
                "SELECT * FROM eco_operation_logs WHERE "
                f"lower(COALESCE(actor_wallet, '')) IN ({h})"
                " OR lower(COALESCE(actor_user_id, '')) = ?"
                " OR (COALESCE(actor_wallet, '') = '' AND COALESCE(actor_user_id, '') = ''"
                f"   AND lower(wallet) IN ({h}))"
                " ORDER BY id DESC LIMIT ?",
                (*lp, my_uid.lower(), *lp, limit),
            ).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        d["detail"] = redact_secrets(d.get("detail") or "")
        d["message"] = redact_secrets(d.get("message") or "")
        items.append(d)
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
def wallet_profile(wallet: str, user: dict = Depends(get_current_user)):
    """综合查询钱包的角色、能量余额、能量记录、证书、勋章、骑行券。

    P1-27：从此需登录；学生只能查本人（wallet 需落在本人候选集内，P0-2）或
    本人正在扮演的内置联盟角色钱包，教师 / 管理员可查任意钱包。
    P0-2：资产/记录按**钱包候选集**取数（同一学生的证书可能记在 userId / stu:
    别名 / 真地址任一口径下，单值等值会“我的资产不见了”）；
    energy_balance 是合约状态（按地址存），仍按传入钱包原值查询，不跨地址合并。
    """
    w = (wallet or "").strip()
    if not w:
        raise HTTPException(400, "钱包地址不能为空")
    _ensure_viewable_wallet(user, w)  # 学生仅限本人（候选集）或本人扮演的联盟角色
    with get_conn() as conn:
        privileged = int(user.get("role_id") or 0) in PRIVILEGED_ROLES
        if not privileged and w.lower() in BUILTIN_WALLETS:
            # 学生查的是他正在扮演的联盟角色钱包：只看该角色口径，不把自己的
            # 资产并入一个公共角色页（否则学生会误读为“角色有资产”）
            cands = resolve_wallet_candidates(conn, w, "")
        else:
            cands = resolve_wallet_candidates(
                conn, w, "" if privileged else (user.get("user_id") or "")
            )
        h, lp = lower_wallet_in(cands)
        role_row = conn.execute(
            f"SELECT role_key FROM eco_role_selections WHERE lower(wallet) IN ({h}) "
            "ORDER BY id DESC LIMIT 1", lp,
        ).fetchone()
        role = _find_role(role_row["role_key"]) if role_row else None

        energy_rows = conn.execute(
            f"SELECT * FROM eco_energy_records WHERE lower(wallet) IN ({h}) "
            "ORDER BY id DESC LIMIT 50", lp,
        ).fetchall()

        cert_rows = conn.execute(
            f"SELECT * FROM eco_certificates WHERE lower(owner) IN ({h}) ORDER BY id DESC", lp,
        ).fetchall()

        badge_rows = conn.execute(
            f"SELECT * FROM eco_badges WHERE badge_type='badge' AND lower(owner) IN ({h}) "
            "ORDER BY id DESC", lp,
        ).fetchall()

        voucher_rows = conn.execute(
            f"SELECT * FROM eco_badges WHERE badge_type='voucher' AND lower(owner) IN ({h}) "
            "ORDER BY id DESC", lp,
        ).fetchall()

    return {
        "wallet": w,
        "wallet_candidates": cands,
        "role": role,
        "energy_balance": _get_energy_balance(w),
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
    quantity: int = 1         # 挂牌份数：ERC1155 同类可多份可拆挂；ERC721 恒为 1


@router.post("/market/list")
def market_list(req: MarketListReq, user: dict = Depends(get_current_user)):
    """居民挂牌绿色资产（二级市场）。校验资产归属 → 写入 eco_market_listings。

    职能口径：二级市场是**居民之间**的资产流转，联盟发行节点与国库账户不得下场
    挂单 / 抢单（否则发行方既能凭空发行又能回收，成了自己的做市商）。
    协议形态：ERC721 植树证书一证一树不可拆 → 挂牌份数恒为 1；
    ERC1155 勋章 / 骑行券同一类型可持有数份 → 可按份拆挂（不超过本行持有量）。
    """
    req.seller = assert_actor_wallet(user, req.seller, "seller")  # 卖家身份从 JWT 解析
    if req.asset_type not in ("certificate", "badge", "voucher"):
        raise HTTPException(400, "asset_type 必须是 certificate/badge/voucher")
    if req.price_energy <= 0:
        raise HTTPException(400, "价格必须大于 0")
    ensure_capability(_identity_role(req.seller), CAP_MARKET_TRADE)
    qty = int(req.quantity or 1)
    if qty <= 0:
        raise HTTPException(400, "挂牌份数必须大于 0")

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
        held = 1
        if qty != 1:
            qty = 1   # ERC721 不可拆：一张证书 = 一棵树，份数参数强制归 1
    else:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT id, token_id, badge_type, name, owner, contract_address, quantity "
                "FROM eco_badges WHERE id=?",
                (req.asset_id,),
            ).fetchone()
        if not row:
            raise HTTPException(404, "资产不存在")
        ensure_asset_owner(row["owner"], req.seller)
        asset_name = row["name"]
        token_id = str(row["token_id"])
        contract_addr = row["contract_address"]
        standard = "ERC1155"
        held = int(row["quantity"] or 1)
        if qty > held:
            raise HTTPException(
                400,
                f"挂牌份数超过持有量：「{asset_name}」当前持有 {held} 份，本次请求 {qty} 份。",
            )

    # 检查是否已在售（同一行资产仅允许一个在售挂牌，避免一份资产拆成多单超卖）
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM eco_market_listings WHERE asset_type=? AND asset_id=? AND status='active'",
            (req.asset_type, req.asset_id),
        ).fetchone()
    if existing:
        raise HTTPException(400, "该资产已在市场中挂牌，请先取消原挂牌")

    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO eco_market_listings(seller,asset_type,asset_id,asset_name,token_id,"
            "contract_address,standard,price_energy,quantity,status,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,'active',?)",
            (req.seller, req.asset_type, req.asset_id, asset_name, token_id,
             contract_addr, standard, req.price_energy, qty, now()),
        )
        listing_id = cur.lastrowid
    return {"ok": True, "listing_id": listing_id, "asset_name": asset_name,
            "price": req.price_energy, "quantity": qty, "held": held, "standard": standard}


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
def market_items(asset_type: str = "", seller: str = "",
                 user: dict = Depends(get_current_user)):
    """查询市场在售绿色资产。可选按类型/卖家过滤（需登录，与 P1-27 只读接口口径一致）。"""
    sql = "SELECT * FROM eco_market_listings WHERE status='active'"
    params: list = []
    if asset_type:
        sql += " AND asset_type=?"
        params.append(asset_type)
    if seller:
        marks, sp = _wallet_marks(seller)
        sql += f" AND lower(seller) IN ({marks})"
        params.extend(sp)
    sql += " ORDER BY created_at DESC"
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        items = []
        for r in rows:
            d = dict(r)
            d["image_url"] = _listing_image(conn, d)
            d["quantity"] = int(d.get("quantity") or 1)
            items.append(d)
    return {"items": items}


@router.get("/market/trades")
def market_trades(limit: int = 100, user: dict = Depends(get_current_user)):
    """绿色资产市场已成交记录（status='sold'，权威数据源）：市场页交易时间线据此展示，
    不区分钱包与浏览器均可见，不依赖浏览器本地缓存。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM eco_market_listings WHERE status='sold' ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        d["quantity"] = int(d.get("quantity") or 1)
        items.append(d)
    return {"items": items}


class MarketBuyReq(BaseModel):
    buyer: str
    listing_id: int


def _release_listing(listing_id: int) -> None:
    """成交失败时释放锁单（sold → active），不留下「已标售但资产未交割」的脏状态。"""
    with _DB_LOCK, get_conn() as conn:
        conn.execute(
            "UPDATE eco_market_listings SET status='active', buyer=NULL, tx_hash=NULL WHERE id=?",
            (int(listing_id),),
        )


@router.post("/market/buy")
def market_buy(req: MarketBuyReq, user: dict = Depends(get_current_user)):
    """购买绿色资产：锁单 → 能量付款(买方→卖方) → 资产交割(卖方→买方) → 双流水记账。

    三个口径修正（旧实现都有真实资金 / 账本问题）：
    - B1 能量必须按流水记账：成交的链上 transfer 真实改动了双方余额，账本必须同步
      写「买方 market_out / 卖方 market_in」两笔流水，否则买方可拿同一笔能量反复兑换；
    - B6 交割数量按协议：ERC1155 按挂牌份数交割（旧实现硬编码 amount=1，拆挂 3 份只给 1 份）；
    - 并发抢单：旧实现「先查 active 再改 sold」，两个买家可同时付款而只有一个能拿到资产；
      现改为 UPDATE ... WHERE status='active' 原子锁单，未抢到单的不产生任何转账。
    """
    req.buyer = assert_actor_wallet(user, req.buyer, "buyer")  # 买家身份从 JWT 解析
    ensure_capability(_identity_role(req.buyer), CAP_MARKET_TRADE)

    # 0. 原子锁单：抢到挂牌才进入资金流程（防并发双买）
    with _DB_LOCK, get_conn() as conn:
        locked = conn.execute(
            "UPDATE eco_market_listings SET buyer=?, status='sold' WHERE id=? AND status='active'",
            (req.buyer, req.listing_id),
        ).rowcount
        row = conn.execute("SELECT * FROM eco_market_listings WHERE id=?",
                           (req.listing_id,)).fetchone()
    if not row:
        raise HTTPException(404, "挂牌记录不存在")
    listing = dict(row)
    if not locked:
        raise HTTPException(400, "该挂牌已售出或已取消（可能刚被别人抢拍），请刷新市场后重试")
    seller = listing["seller"]
    buyer = req.buyer
    if _norm_wallet(seller) == _norm_wallet(buyer):
        _release_listing(req.listing_id)
        raise HTTPException(400, "不能购买自己的资产")
    price = int(listing["price_energy"])
    qty = int(listing.get("quantity") or 1)

    # 1. 校验买方 GreenEnergy 余额
    ge_addr, ge_abi = _find_contract("GreenEnergy")
    if not ge_addr:
        _release_listing(req.listing_id)
        raise HTTPException(400, "GreenEnergy 合约在当前链上不可用（链已重置或尚未部署），"
                                 "请联盟管理员重新部署后重试")
    c = get_chain_client()
    buyer_addr = c.resolve_account(buyer)
    seller_addr = c.resolve_account(seller)
    # 余额口径：与证书 / 勋章兑换同一事实源（账本为准，扣款前把差额回填到链上），
    # 失败要把刚抢到的挂牌还回去，否则一次余额不足就把挂牌永久锁死。
    try:
        _require_chain_balance(buyer, price, "市场购买")
    except HTTPException:
        _release_listing(req.listing_id)
        raise

    # 2. GreenEnergy 转账：买方 → 卖方
    r_pay = c.call_contract(ge_addr, "transfer", [seller_addr, price], buyer, ge_abi)
    if not r_pay.get("ok"):
        _release_listing(req.listing_id)
        raise HTTPException(400, "能量支付失败: " + _chain_deduct_hint(buyer, price, r_pay))
    pay_tx = r_pay.get("tx_hash", "")

    # 3. 资产交割：卖方 → 买方（失败则尽力退款，不让买方白付）
    nft_abi = _load_abi(listing["contract_address"])
    if not nft_abi:
        _refund_payment(c, ge_addr, ge_abi, seller, buyer_addr, price)
        _release_listing(req.listing_id)
        raise HTTPException(400, "NFT 合约 ABI 未找到（能量已原路退回，本次不成交）")
    token_id_int = int(listing["token_id"])
    if listing["standard"] == "ERC721":
        r_nft = c.call_contract(listing["contract_address"], "transferFrom",
                                [seller_addr, buyer_addr, token_id_int],
                                seller, nft_abi)
    else:
        r_nft = c.call_contract(listing["contract_address"], "safeTransferFrom",
                                [seller_addr, buyer_addr, token_id_int, qty],
                                seller, nft_abi)
    if not r_nft.get("ok"):
        refunded = _refund_payment(c, ge_addr, ge_abi, seller, buyer_addr, price)
        _release_listing(req.listing_id)
        raise HTTPException(
            400,
            "资产交割失败: " + str(r_nft.get("error", ""))
            + ("（付款能量已由卖方原路退回，挂牌已重新开放）"
               if refunded else "（付款能量退回失败，请联系发行节点凭交易凭证处理）"),
        )
    nft_tx = r_nft.get("tx_hash", pay_tx)

    # 4. 资产归属落库（份数守恒：ERC1155 拆挂时卖方留余量、买方另起一行）
    with _DB_LOCK, get_conn() as conn:
        conn.execute(
            "UPDATE eco_market_listings SET status='sold', buyer=?, tx_hash=? WHERE id=?",
            (buyer, nft_tx, req.listing_id),
        )
        if listing["asset_type"] == "certificate":
            conn.execute("UPDATE eco_certificates SET owner=? WHERE id=?", (buyer, listing["asset_id"]))
        else:
            src = dict(conn.execute("SELECT * FROM eco_badges WHERE id=?",
                                    (listing["asset_id"],)).fetchone() or {})
            remain = int(src.get("quantity") or 1) - qty
            if remain <= 0:
                conn.execute("UPDATE eco_badges SET owner=? WHERE id=?",
                             (buyer, listing["asset_id"]))
            else:
                # 部分拆挂：卖方行只走 qty 份，余量仍归卖方；成交份数入买方新行（易主不改兑换成本）
                conn.execute("UPDATE eco_badges SET quantity=? WHERE id=?",
                             (remain, listing["asset_id"]))
                conn.execute(
                    "INSERT INTO eco_badges(token_id,badge_type,name,owner,exchanged_by,cost_energy,"
                    "issued_by,issuer_role,contract_address,tx_hash,created_at,quantity) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (src.get("token_id"), src.get("badge_type"), src.get("name"), buyer,
                     src.get("exchanged_by") or src.get("seller") or "", 0,
                     src.get("issued_by") or "", src.get("issuer_role") or "",
                     src.get("contract_address") or listing.get("contract_address") or "",
                     nft_tx, now(), qty),
                )
        # 5. 能量流水双写（ref 幂等：重复成交不会双扣）
        _ensure_flow(conn, wallet=buyer, kind=FLOW_MARKET_OUT, amount=-price,
                     ref=f"market:{req.listing_id}:pay",
                     note=f"购入 {listing['asset_name']}" + (f" ×{qty}" if qty > 1 else ""))
        _ensure_flow(conn, wallet=seller, kind=FLOW_MARKET_IN, amount=price,
                     ref=f"market:{req.listing_id}:recv",
                     note=f"售出 {listing['asset_name']}" + (f" ×{qty}" if qty > 1 else ""))
    # 成交不另写 learning_events：成绩侧 eco_market_trade 已按 eco_market_listings
    # 的 status='sold' 直接计数（见 learning.events.aggregate），重复埋点会双计分。
    return {
        "ok": True,
        "pay_tx": pay_tx,
        "nft_tx": nft_tx,
        "asset_name": listing["asset_name"],
        "price": price,
        "quantity": qty,
        "standard": listing["standard"],
    }


def _refund_payment(c, ge_addr: str, ge_abi, seller: str, buyer_addr: str, price: int) -> bool:
    """成交失败时的资金回滚：由卖方（当时收款人）把能量退回买方地址。"""
    return _compensate_energy(c, ge_addr, ge_abi, seller, buyer_addr, price)


@router.post("/market/cancel")
def market_cancel(payload: dict, user: dict = Depends(get_current_user)):
    """取消挂牌（仅卖家本人）。

    撤单不做能力硬拦：下架是居民的**退出通道**，即使他已把身份切到联盟节点（或
    历史遗留挂牌），也必须能把之前的挂单收回来，否则资产会被卡在在售状态。
    """
    listing_id = payload.get("listing_id")
    seller = assert_actor_wallet(user, payload.get("seller"), "seller")  # 卖家身份从 JWT 解析
    with get_conn() as conn:
        row = conn.execute(
            "SELECT seller, status FROM eco_market_listings WHERE id=?",
            (listing_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "挂牌记录不存在")
        if _norm_wallet(row["seller"]) != _norm_wallet(seller):
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


def _abi_has(abi, fn_name: str) -> bool:
    """ABI 能力探测（兼容旧版本合约：缺该函数时给可读提示，而不是透传 revert）。"""
    try:
        return any(isinstance(i, dict) and i.get("type") == "function"
                   and i.get("name") == fn_name for i in (abi or []))
    except Exception:
        return False


# ===========================================================================
# 8.5 能量国库与销毁（治理维度：仅管理员）
#     兑换回收的能量不是「消失」而是回到国库；若可无限重新投放就是二次发行（通胀），
#     因此国库必须能销毁，且销毁量 / 发行量 / 在途量全部由流水表可审计推导。
# ===========================================================================
@router.get("/treasury/overview")
def treasury_overview(wallet: str = "", user: dict = Depends(get_current_user)):
    """能量国库视图：累计发行 / 回收 / 已销毁 / 国库余额 / 在途流通 + 五节点发行授信。

    口径全部来自 eco_energy_flows（按事件记账、不因归属变更重算），
    并额外输出资金守恒校验（inflation_audit）供监管页直接展示。
    供所有登录身份**只读**（供应量与销毁台账在真实联盟链上本来就是公开的），
    能否执行销毁由 can_burn 返回，前端据此决定是否展示销毁入口。
    """
    with get_conn() as conn:
        stats = _treasury_stats(conn)
        ledger_sum = int(conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM eco_energy_flows").fetchone()[0] or 0)
        burns = [dict(r) for r in conn.execute(
            "SELECT * FROM eco_energy_burns ORDER BY id DESC LIMIT 20").fetchall()]
    expected = int(stats["total_issued"]) - int(stats["total_burned"])
    stats["inflation_audit"] = {
        "ledger_sum": ledger_sum,               # Σ 全体流水
        "expected_sum": expected,               # 累计发行 − 累计销毁
        "conserved": ledger_sum == expected,    # False = 账本漏记 / 双记（必须人工介入）
        "diff": ledger_sum - expected,
    }
    stats["burns"] = burns
    stats["pending_burn_cap"] = min(int(stats["treasury_balance"]), int(stats["pending_burn"]))
    # 销毁权限 = 机构身份（管理员）且 登录账号为教师/平台管理员（修 B12）
    try:
        role = _identity_role(wallet) if wallet else None
        can_burn = bool(role and CAP_TREASURY_MANAGE in role_capabilities(role)) \
            and int(user.get("role_id") or 0) in PRIVILEGED_ROLES
    except Exception:
        can_burn = False
    stats["can_burn"] = can_burn
    # treasury_wallet / treasury_wallet_alias 由 energy_ledger.supply_stats 统一给出
    # （前者是国库真实地址，后者是 0xadmin 友好别名），此处不再叠一层旧口径
    return {"ok": True, **stats}


class TreasuryBurnReq(BaseModel):
    wallet: str            # 操作者（仅管理员）
    amount: int            # 销毁点数
    note: str = ""


@router.post("/treasury/burn")
def treasury_burn(req: TreasuryBurnReq, user: dict = Depends(get_current_user)):
    """销毁国库回收的能量（链上真实 GreenEnergy.burn，由 0xadmin 发起）。

    销毁 = 退出流通、总供应量下降（不是转给任何人），因此：
    - 仅治理身份可执行（发行节点与居民 403）；
    - 上限只取「已回收未销毁」部分（pending_burn），不动尚未投放的国库存量；
    - 成功后写 eco_energy_burns 凭证 + 国库出账流水（ref=burn:{id}，幂等）。
    """
    req.wallet = assert_actor_wallet(user, req.wallet)
    role = _identity_role(req.wallet)
    _ensure_governor(user, "能量国库销毁")
    ensure_capability(role, CAP_TREASURY_MANAGE)
    if req.amount <= 0:
        raise HTTPException(400, "销毁数量必须大于 0")

    with get_conn() as conn:
        stats = _treasury_stats(conn)
        wallet_balance = max(0, _flow_balance(conn, TREASURY_WALLET))
    cap = min(wallet_balance, int(stats["pending_burn"]))
    if req.amount > cap:
        raise HTTPException(
            400,
            f"可销毁余额不足：国库余额 {wallet_balance}，其中已回收未销毁 {stats['pending_burn']}，"
            f"本次可销毁上限 {cap}。销毁只能针对居民兑换回收进国库的能量，"
            f"不能销毁尚未发行的授信额度。",
        )

    ge_addr, ge_abi = _find_contract("GreenEnergy")
    if not ge_addr:
        raise HTTPException(400, "GreenEnergy 合约未部署")
    if not _abi_has(ge_abi, "burn"):
        raise HTTPException(400, "当前链上的 GreenEnergy 合约不含 burn() 方法，"
                                 "请重新部署 contracts/GreenEnergy.sol 后再执行销毁")

    c = get_chain_client()
    # 国库链上余额可能因沙盒链重置而低于账本（与居民同一回填口径，失败不再静默）
    sync = _sync_chain_balance(TREASURY_WALLET)
    if not sync["ok"]:
        raise HTTPException(400, sync["detail"])
    r = c.call_contract(ge_addr, "burn", [int(req.amount)], TREASURY_WALLET, ge_abi)
    if not r.get("ok"):
        raise HTTPException(400, "链上销毁失败: "
                                 + _chain_deduct_hint(TREASURY_WALLET, int(req.amount), r))

    note = (req.note or "").strip() or "国库能量销毁"
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO eco_energy_burns(amount,tx_hash,contract_address,operator,note,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (int(req.amount), r.get("tx_hash", ""), ge_addr, _norm_wallet(TREASURY_WALLET), note, now()),
        )
        _ensure_flow(conn, wallet=TREASURY_WALLET, kind=FLOW_TREASURY_BURN,
                     amount=-int(req.amount), ref=f"burn:{cur.lastrowid}", note=note)
        stats_after = _treasury_stats(conn)
    _track(EventType.ECO_ENERGY_BURN, target="GreenEnergy", ref_id=str(cur.lastrowid),
           wallet=req.wallet or "", extra={"amount": int(req.amount),
                                           "tx_hash": r.get("tx_hash", "")})
    return {"ok": True, "burn_id": cur.lastrowid, "amount": int(req.amount),
            "tx_hash": r.get("tx_hash", ""), "total_burned": stats_after["total_burned"],
            "net_issuance": stats_after["net_issuance"],
            "burn_rate": stats_after["burn_rate"]}


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
        # P1-26：actor_wallet / actor_user_id = 登录身份（“这事是谁干的”）；
        #   wallet 列仍是操作发生时的**业务钱包**（可能是联盟角色钱包 / 被操作对象）。
        conn.execute("""
        CREATE TABLE IF NOT EXISTS eco_operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet TEXT NOT NULL,
            module TEXT NOT NULL,       -- role | energy | tree | certificate | badge | contract | other
            action TEXT NOT NULL,       -- 操作动作
            level TEXT NOT NULL,        -- info | success | warn | error
            message TEXT NOT NULL,      -- 简短描述
            detail TEXT,                -- 详细错误 / 堆栈
            created_at TEXT NOT NULL,
            actor_wallet TEXT NOT NULL DEFAULT '',
            actor_user_id TEXT NOT NULL DEFAULT ''
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

        # === P1-26 / P1-27：eco_operation_logs 在线迁移（旧库补列 + 存量凭证清洗）===
        # 1) actor_* 两列：新库由上面的 CREATE 直接带上，旧库 ALTER 补列（幂等）。
        log_cols = {r[1] for r in conn.execute(
            "PRAGMA table_info(eco_operation_logs)").fetchall()}
        for _col in ("actor_wallet", "actor_user_id"):
            if _col not in log_cols:
                try:
                    conn.execute("ALTER TABLE eco_operation_logs "
                                 f"ADD COLUMN {_col} TEXT NOT NULL DEFAULT ''")
                except Exception:
                    pass  # 并发初始化 / 已存在：幂等容错
        conn.execute("CREATE INDEX IF NOT EXISTS idx_eco_logs_actor "
                     "ON eco_operation_logs(actor_wallet)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_eco_logs_actor_uid "
                     "ON eco_operation_logs(actor_user_id)")
        # 2) **故意不回填**存量行的 actor_*：回填等于把“被操作钱包”伪造成“操作人”，
        #    会使历史扣分统计从「钱包口径」静默切到「操作人口径」（正在教书的
        #    班级分数会突然变）。存量行保持 actor 为空，由报告侧
        #    report._actor_scope 的“actor 全空 → 退回 wallet 口径”分支接管（只新增
        #    行适用新口径）。
        # 3) 存量清洗（P1-27）：detail / message 里已落库的 JWT / Bearer 头一次性
        #    打码（只改敏感串，保留其余文本与行结构），否则这些行一旦被报告
        #    回显或下载就能把别人的 token 拾出来。
        dirty = conn.execute(
            "SELECT id, detail, message FROM eco_operation_logs "
            "WHERE detail LIKE '%Bearer %' OR detail LIKE '%eyJ%' "
            "OR message LIKE '%Bearer %' OR message LIKE '%eyJ%'"
        ).fetchall()
        cleaned = 0
        for r in dirty:
            d = redact_secrets(str(r["detail"] or ""))
            m = redact_secrets(str(r["message"] or ""))
            if d != (r["detail"] or "") or m != (r["message"] or ""):
                conn.execute("UPDATE eco_operation_logs SET detail=?, message=? WHERE id=?",
                             (d, m, r["id"]))
                cleaned += 1
        if cleaned:
            logger.warning("eco_operation_logs 存量凭证清洗：%d 行已脱敏（P1-27）", cleaned)

        # ===================================================================
        # 四维度职能模型落库（能量流水账 + 发行额度 + 数量语义 + 操作人留痕）
        # 全部为在线幂等迁移：新库由 CREATE 直接带上，旧库 ALTER 补列 + 存量摊平。
        # ===================================================================
        # 1) 能量流水表：余额的唯一事实源（修 B1 资产易主回补成本）
        conn.execute("""
        CREATE TABLE IF NOT EXISTS eco_energy_flows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet TEXT NOT NULL,             -- 记账钱包（居民 / 联盟节点 / 国库）
            kind TEXT NOT NULL,               -- 见 FLOW_* 常量
            amount INTEGER NOT NULL,          -- 有符号：入账为正、出账为负
            ref TEXT NOT NULL DEFAULT '',     -- 业务事件唯一标识（幂等键）
            note TEXT NOT NULL DEFAULT '',
            role_key TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_energy_flows_wallet "
                     "ON eco_energy_flows(wallet)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_energy_flows_kind "
                     "ON eco_energy_flows(kind)")
        try:
            # 部分索引：只对非空 ref 强制唯一（空 ref 为人工治理科目，不参与幂等）
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_energy_flows_ref "
                         "ON eco_energy_flows(ref) WHERE ref<>''")
        except Exception:
            pass  # 存量脏数据撞唯一约束：保持无索引运行，流水仍可用
        # 2) 能量销毁台账（国库回收 → 管理员真实 burn 的凭证）
        conn.execute("""
        CREATE TABLE IF NOT EXISTS eco_energy_burns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount INTEGER NOT NULL,           -- 销毁点数
            tx_hash TEXT NOT NULL DEFAULT '',
            contract_address TEXT NOT NULL DEFAULT '',
            operator TEXT NOT NULL DEFAULT '',  -- 执行销毁的钱包（仅管理员）
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )""")
        # 3) ERC721 发行额度：一证一树 → 树种项目额度（supply=0 视为不限额，兼容旧数据）
        _ensure_column(conn, "eco_tree_species", "supply",
                       "INTEGER NOT NULL DEFAULT 0")    # 发行数量上限（项目额度）
        _ensure_column(conn, "eco_tree_species", "issued",
                       "INTEGER NOT NULL DEFAULT 0")    # 已发行数量
        _ensure_column(conn, "eco_tree_species", "status",
                       "TEXT NOT NULL DEFAULT 'active'")  # active | off（下架不可兑）
        # 4) 兑换成本归属人（不随市场转手变化）+ ERC1155 同类多份的数量语义
        _ensure_column(conn, "eco_certificates", "exchanged_by",
                       "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "eco_badges", "exchanged_by",
                       "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "eco_badges", "quantity",
                       "INTEGER NOT NULL DEFAULT 1")     # 持有份数（ERC1155 amount）
        _ensure_column(conn, "eco_badges", "issuer_role",
                       "TEXT NOT NULL DEFAULT ''")       # 发行方节点（易主后仍可溯源）
        _ensure_column(conn, "eco_market_listings", "quantity",
                       "INTEGER NOT NULL DEFAULT 1")     # 挂牌份数（ERC721 恒为 1）
        # 5) 能量发行留痕：个人钱包扮演机构时的真实操作人 + 计价明细
        _ensure_column(conn, "eco_energy_records", "operator_wallet",
                       "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "eco_energy_records", "operator_user_id",
                       "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "eco_energy_records", "points_base",
                       "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "eco_energy_records", "points_bonus",
                       "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "eco_energy_records", "points_capped",
                       "INTEGER NOT NULL DEFAULT 0")      # 1=超门槛按量加成后被封顶截断

        # ---- 存量数据回填（均幂等）----
        # 兑换成本归属：已被市场转手的资产 → 取首次成交时的卖家（当时实际支付能量的人）
        conn.execute("""
        UPDATE eco_certificates SET exchanged_by = COALESCE((
            SELECT l.seller FROM eco_market_listings l
            WHERE l.asset_type='certificate' AND l.asset_id=eco_certificates.id
              AND l.status='sold' ORDER BY l.id ASC LIMIT 1), owner)
        WHERE COALESCE(exchanged_by,'')=''""")
        conn.execute("""
        UPDATE eco_badges SET exchanged_by = COALESCE((
            SELECT l.seller FROM eco_market_listings l
            WHERE l.asset_type=eco_badges.badge_type AND l.asset_id=eco_badges.id
              AND l.status='sold' ORDER BY l.id ASC LIMIT 1), owner)
        WHERE COALESCE(exchanged_by,'')=''""")
        # 树种已发行数：按存量证书重算（supply=0 的旧数据 → 额度不限制，但已发行量仍如实统计）
        conn.execute("""
        UPDATE eco_tree_species SET issued = COALESCE((
            SELECT COUNT(*) FROM eco_certificates c WHERE c.species_id=eco_tree_species.id), 0)""")
        # 存量发放记录的计价明细：旧数据按固定点数口径回填
        conn.execute("UPDATE eco_energy_records SET points_base=points, points_bonus=0 "
                     "WHERE COALESCE(points_base,0)=0 AND COALESCE(points,0)>0")
        flows_added = _backfill_energy_flows(conn)
        if flows_added:
            logger.info("eco_energy_flows 存量摊平：新增 %d 笔流水", flows_added)


def reconcile_energy_flows() -> int:
    """启动收尾对账：把不经 API 直写业务表的历史数据（如 seed 播种）补成流水。

    幂等（INSERT OR IGNORE + 固定 ref），可重复调用；失败不影响启动。
    """
    try:
        with get_conn() as conn:
            return _backfill_energy_flows(conn)
    except Exception as e:  # pragma: no cover - 启动兜底
        logger.warning("能量流水对账跳过：%s", e)
        return 0


def align_chain_balances() -> dict:
    """启动收尾对账（链上侧）：把全量账本余额补齐到链上 GreenEnergy。

    为什么必须在启动时做：本地沙盒链是**进程内内存链**，后端每重启一次，链上
    余额与合约状态全部清零，而能量账本（SQLite）保留全量历史。只靠兑换路径里的
    逐个回填，用户会先看到「钱包页能量为 0 / 不增长」，并在首次兑换时拿到一句
    合约 revert 原文。本函数在 seed（内置合约已部署）之后跑一遍，使链上余额从启动
    那一刻起就与账本一致；已一致或读不到链的钱包不会发任何交易。

    返回 {"total", "aligned", "skipped", "failed", "minted_total", "items": [...]}。
    """
    report = {"total": 0, "aligned": 0, "skipped": 0, "failed": 0,
              "minted_total": 0, "items": []}
    try:
        wallets = _ledger_balances()
    except Exception as e:  # pragma: no cover - 启动兜底
        logger.warning("链上能量对账跳过（读账本失败）：%s", e)
        return report
    report["total"] = len(wallets)
    if not wallets:
        return report
    if not latest_deployed("GreenEnergy")[0]:
        report["skipped"] = len(wallets)
        logger.info("链上能量对账跳过：当前链实例上没有可用的 GreenEnergy")
        return report
    for wallet, ledger in wallets:
        sync = _sync_chain_balance(wallet)
        item = {
            "wallet": wallet,
            "ledger_balance": int(ledger),
            "chain_balance": int(sync.get("chain_balance") or 0),
            "chain_balance_after": int(sync.get("chain_balance_after") or 0),
            "minted": int(sync.get("diff") or 0) if sync.get("ok") else 0,
            "ok": bool(sync.get("ok")),
            "detail": sync.get("detail") or "",
        }
        report["items"].append(item)
        if not sync.get("ok"):
            report["failed"] += 1
            logger.warning("[eco] 链上能量对账失败 %s: %s", wallet, sync.get("detail"))
            continue
        if item["minted"] > 0:
            report["aligned"] += 1
            report["minted_total"] += item["minted"]
        else:
            report["skipped"] += 1
    if report["aligned"]:
        print(f"[eco] 启动能量对账：{report['aligned']} 个钱包补发 {report['minted_total']} 点"
              f"（失败 {report['failed']}）")
    return report
