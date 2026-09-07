"""联盟内置合约的权威定义（合约清单 / 构造参数 / 链上发行权白名单）。

为什么单独成模块：`GreenEnergy / PlantCertificate / EcoBadge` 三份合约的清单与
构造参数此前在 app/routers/eco.py 与 app/seed.py 各写一份，改一处漏一处
（例如把部署方从学生改成国库时，两侧口径就会分叉）。本模块是**唯一来源**：

- app/routers/eco.py   → BUILTIN_CONTRACTS / DEFAULT_CTOR_ARGS / grant_issuers
- app/seed.py          → 同上（播种部署后授予业务节点链上发行权）

发行权的两层模型（对应四维度职能口径，见 learning/alliance_roles.py）：
  ① 应用层：eco 路由按能力位（CAP_ENERGY_ISSUE / CAP_ASSET_ISSUE_*）403 拦截；
  ② 链上合约层：mint / burn 的 msg.sender 必须在 issuers 白名单内。
只有 ① 时，任何拿到 /api/contracts/call 的人都能直接对合约发 mint；只有 ② 时，
无法表达「哪个节点该发哪类资产」。两层必须同时成立。

依赖约束：只依赖 learning.alliance_roles（角色 ↔ 组织钱包）与 db / chain_client，不 import routers。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from .chain_client import get_chain_client
from .db import get_conn, now
from .learning.alliance_roles import TREASURY_WALLET, find_role


# 内置合约清单（名称与 deployed_contracts.name 对应）
BUILTIN_CONTRACTS = [
    {"name": "GreenEnergy",      "standard": "ERC20",   "file": "GreenEnergy.sol"},
    {"name": "PlantCertificate", "standard": "ERC721",  "file": "PlantCertificate.sol"},
    {"name": "EcoBadge",         "standard": "ERC1155", "file": "EcoBadge.sol"},
]

# 构造函数默认参数（联盟侧一键部署 / 启动播种共用）
# GreenEnergy 初始供应 = 0：真实商业里能量代币不存在「创世预挖给某个钱包」，
# 每一点能量都必须由节点审核低碳行为后 mint 出来。传正数会让链上 totalSupply 大于
# 能量流水累计发行量，通胀审计（Σ 流水 == 发行 − 销毁）就永远对不上。
DEFAULT_CTOR_ARGS = {
    "GreenEnergy":      [0],                          # uint256 _initialSupply = 0
    "PlantCertificate": ["PlantCertificate", "PCERT"],  # string _name, string _symbol
    "EcoBadge":         [],                           # 无构造函数参数
}

# 各合约的链上发行白名单范围（owner = 创世部署方 0xadmin，默认可发行 + 可维护白名单）
# - GreenEnergy：5 个业务联盟节点组织钱包（能量发行方）；管理员不发行能量，
#   但作为国库需要 burn 权（burn 用 owner 身份，不需进白名单）
# - EcoBadge：勋章/骑行券由业务节点发行，骑行券履约方是 bike；旧内置类型无发行方时
#   由 owner（0xadmin）代签
# - PlantCertificate：植树证书由联盟碳汇方（owner）统一签发，不开放给节点
ISSUER_SCOPES = {
    "GreenEnergy":      ("metro", "bus", "bike", "takeout", "recycling"),
    "EcoBadge":         ("metro", "bus", "bike", "takeout", "recycling"),
    "PlantCertificate": (),
}

# 白名单维护函数名（新版合约才有；旧合约部署后探测不到 → 降级为 legacy）
ISSUER_CONTROL_FN = "addIssuer"


def contract_file(name: str) -> str:
    """合约名 → 源码文件名（未登记返回空串）。"""
    for c in BUILTIN_CONTRACTS:
        if c["name"] == name:
            return str(c["file"])
    return ""


def abi_function(abi: Any, fn_name: str) -> Optional[dict]:
    """在 ABI 数组里查函数定义（容忍 abi 为 None / JSON 字符串 / 非 dict 元素）。"""
    if isinstance(abi, str):
        import json as _json
        try:
            abi = _json.loads(abi)
        except Exception:
            return None
    if not abi:
        return None
    for item in abi:
        if isinstance(item, dict) and item.get("type") == "function" and item.get("name") == fn_name:
            return item
    return None


def has_issuer_control(abi: Any) -> bool:
    """该合约是否带链上发行白名单（addIssuer）——旧合约返回 False。"""
    return abi_function(abi, ISSUER_CONTROL_FN) is not None


def issuer_enforcement(abi: Any) -> str:
    """链上权限口径：onchain = 合约层已白名单化；legacy = 仅应用层校验。"""
    return "onchain" if has_issuer_control(abi) else "legacy"


def scope_wallets(contract_name: str) -> list:
    """该合约应被授予发行权的组织钱包列表（role_key 解析为钱包别名）。"""
    out: list = []
    for key in ISSUER_SCOPES.get(contract_name) or ():
        role = find_role(key) or {}
        w = str(role.get("wallet") or "").strip()
        if w and w not in out:
            out.append(w)
    return out


def grant_issuers(client: Any, address: str, abi: Any, contract_name: str,
                  operator: str = TREASURY_WALLET) -> dict:
    """部署后把业务节点组织钱包加入链上发行白名单（仅 owner 可调用 addIssuer）。

    幂等：addIssuer 重复执行只是把 bool 再写一次 + 多一条事件，不影响状态；
    单个钱包授权失败不阻断其余授权（链上账户未初始化等环境问题可后续补）。

    返回：{"enforcement": "onchain|legacy", "granted": [...], "failed": [...], "operator": ...}
    """
    scope = scope_wallets(contract_name)
    if not has_issuer_control(abi):
        return {"enforcement": "legacy", "granted": [], "failed": [],
                "operator": operator, "scope": scope,
                "reason": "合约 ABI 无 addIssuer（旧版本），发行权仅由应用层能力位校验"}
    if not address:
        return {"enforcement": "onchain", "granted": [], "failed": scope,
                "operator": operator, "scope": scope, "reason": "合约地址为空"}
    granted: list = []
    failed: list = []
    for wallet in scope:
        try:
            target = client.resolve_account(wallet)
            r = client.call_contract(address, ISSUER_CONTROL_FN, [target], operator, abi)
        except Exception as e:  # 链不可用 / 账户未注册：不抛出，交由状态接口暴露口径
            failed.append({"wallet": wallet, "error": str(e)})
            continue
        if r.get("ok"):
            granted.append(wallet)
        else:
            failed.append({"wallet": wallet, "error": str(r.get("error") or r.get("status") or "")})
    return {"enforcement": "onchain", "granted": granted, "failed": failed,
            "operator": operator, "scope": scope}


# ---------------------------------------------------------------------------
# 「哪一份合约是当前生效的」—— 全平台唯一取址口径
#
# 为什么必须收口（P0，实测复现）：GreenEnergy 是可被反复部署的（教程第 9 步、
# 联盟页「一键激活」都会再部署一份），而平台曾存在两套取址：
#   ① 联盟业务读写（能量发行 / 兑换 / 余额）→ 按 created_at DESC 取 deployed_contracts 最新一份；
#   ② 能量钱包页与 NFT 市场结算 → 读 tokens 表，而该表只在后端启动的 seed 里写一次。
# 于是「重启后重跑第 9 步」把 ① 切到新地址、② 仍指旧地址：学生在联盟页有 270 点能量，
# 到 NFT 市场付款却被告知「当前 0」，报告 C 项「成交 +5」结构性拿不到。
# 因此取址只有 latest_deployed() 一个入口，且每次部署 GreenEnergy 后必须 sync_energy_token()。
# ---------------------------------------------------------------------------
ENERGY_TOKEN_NAME = "GreenEnergy"
ENERGY_TOKEN_SYMBOL = "GE"


def _as_ts(val: Any) -> float:
    """created_at → 可比较的 unix 时间戳（兼容 ISO 文本与秒级数字，解析失败归 0）。"""
    s = str(val or "").strip()
    if not s:
        return 0.0
    if s.replace(".", "", 1).isdigit():
        try:
            return float(s)
        except ValueError:
            return 0.0
    try:
        return datetime.fromisoformat(s.replace(" ", "T", 1)).timestamp()
    except ValueError:
        return 0.0


def latest_deployed(name: str) -> tuple:
    """同名合约在 deployed_contracts 中的**最新一份**，返回 (address, abi)。

    地址在当前链实例上已无代码（链重置后的 stale 记录）→ 返回 (None, None)，
    与既有 `_find_contract` 语义完全一致：宁可报「合约未部署」，也不要拿一个
    链上不存在的地址去调用（那会产生一批无法归因的 reverted 记录）。

    ⚠️ 不能直接 ORDER BY created_at DESC：created_at 是 TEXT，而
    `datetime.isoformat()` 会省略微秒部分的尾随零（200000µs 存成 "…45.2"），
    于是**字典序与时间序不一致**（实测：同一秒内先后两次部署，旧记录反而排在前）。
    取错实例的后果不是“数据旧一点”而是余额口径错：新合约上人人余额 0，
    整个绿色经济会看起来“能量凭空消失”。故在 Python 侧按真实时间戳取最大，
    同一时刻再按 rowid 取最后插入的那一份。
    """
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT address, abi, created_at, rowid AS rid FROM deployed_contracts WHERE name=?",
            (name,),
        ).fetchall()
    if not rows:
        return None, None
    best = max(rows, key=lambda r: (_as_ts(r["created_at"]), int(r["rid"] or 0)))
    if not get_chain_client().has_code(best["address"]):
        return None, None
    try:
        abi = json.loads(best["abi"] or "[]")
    except (TypeError, ValueError):
        abi = []
    return best["address"], abi


def sync_energy_token(address: str, owner: str = "") -> bool:
    """把最新部署的 GreenEnergy 重新登记为流通代币（能量钱包余额 + 市场结算币种）。

    DELETE + INSERT 与 seed 同口径（tokens 表按地址 UNIQUE，不能靠 UPDATE 换址留残行）；
    total_supply 传 0：能量不存在创世预挖，发行量以能量流水为准（见 DEFAULT_CTOR_ARGS 注释）。
    """
    if not address:
        return False
    owner = owner or get_chain_client().resolve_account(TREASURY_WALLET) or TREASURY_WALLET
    with get_conn() as conn:
        conn.execute("DELETE FROM tokens WHERE name=?", (ENERGY_TOKEN_NAME,))
        conn.execute(
            "INSERT INTO tokens(address,name,symbol,decimals,total_supply,owner,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (address, ENERGY_TOKEN_NAME, ENERGY_TOKEN_SYMBOL, 0, "0", owner, now()),
        )
    return True
