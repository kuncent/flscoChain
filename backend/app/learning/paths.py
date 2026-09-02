"""学习路径单一事实源（P1-P4 路径常量 + 服务端核验接口）。

背景：Dashboard.vue 曾把 10 步学习路径（P1-P4 四阶段、每步含 goal /
kpoints / accept 验收文案 / eta / 关联页面路由）硬编码在前端，验收标准
无服务端核验，与后端既有的单一事实源资产脱节（TUTORIAL 10 步、
achievements.py 的 ACHIEVEMENTS_SEED 15 成就、learning_events 行为埋点）。

本模块收口三件事：
- STAGE_PATH  学习路径常量：自 Dashboard.vue pathSteps 逐字平移（title /
              desc / goal / kpoints / accept / eta / keywords / icon / to /
              level / tag / tagClass 逐字一致，由临时对比脚本验证，用后即删），
              并为每条标注：
              - tutorialSteps  关联的 TUTORIAL 步骤号（仅 /cloud 直接承载
                全部 10 步教程；其余阶段 accept 不引用教程步骤 → 留空 []）
              - achievements   关联成就 id（以 routers/achievements.py
                ACHIEVEMENTS_SEED 实际 key 为准，语义不对应的留空 []）
              - checks         accept 逐项核验规则：kind=metric（可核验指标，
                键见 _extra_metrics / events.aggregate）/ kind=achievement
                （成就已获得）/ kind=manual（不可自动核验，仅展示）
- 核验引擎    GET /api/learning/path：按各阶段 accept 语义映射到的可核验
              指标（部署数 / 事件计数 / 成就）自动判定 verified；
              manual 项不参与自动判定。
- 兜底约定    表不存在 / 空数据一律降级为空态（计数 0、verified=false），
              不抛错；DB 不可用时 stages 文案仍完整返回，由前端回退。

依赖约束：遵守 learning/__init__.py 包约定，只依赖底层模块（db / security /
learning.events / learning.tutorial_steps），禁止 import routers.*
（routers.achievements 反向依赖本包，会成环）；成就 id 与 achievements.py
以模块注释声明来源保持人工同步。
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends

from ..db import get_conn
from ..security import lower_wallet_in, optional_user, resolve_wallet_candidates
from .events import EventType, aggregate
from .tutorial_steps import TUTORIAL

router = APIRouter(prefix="/api/learning", tags=["learning"])

# TUTORIAL 步骤总数（搭链教程 10 步）；核验阈值随 TUTORIAL 演进自动跟随
_TUTORIAL_TOTAL = len(TUTORIAL)

# eco_role_switch / eco_energy_issue 埋点 target 的旧别名归一
# （口径与 routers/achievements.py _compute_user_stats 的 eco_roles_used 一致）
_ROLE_ALIAS = {"delivery": "takeout", "recycle": "recycling"}

# 3 份系统合约的部署核验名（deployed_contracts.name 小写匹配）
_SYSTEM_CONTRACT_NAMES = ("greenenergy", "plantcertificate", "ecobadge")


# ---------------------------------------------------------------------------
# P1-P4 学习路径常量（自 Dashboard.vue pathSteps 逐字平移；键名与前端
# PathStep 字段对齐，响应直接透传）。
# checks[k].text 与 accept[k] 逐项对应。
# ---------------------------------------------------------------------------
STAGE_PATH: list[dict[str, Any]] = [
    {
        "id": "P1-1", "level": "P1", "to": "/dashboard", "icon": "DataBoard",
        "title": "总览 · 绿色低碳联盟链项目",
        "desc": "了解项目全貌：6 个联盟成员、3 份智能合约、能量发放→兑换闭环",
        "keywords": ["项目全貌", "6 角色联盟", "3 合约体系"],
        "tag": "起点", "tagClass": "",
        "eta": "5 分钟",
        "goal": "能复述绿色低碳联盟链的业务架构：谁发能量、谁兑换、能量如何流转",
        "kpoints": [
            "联盟成员：管理员/地铁/公交/单车/外卖/回收 6 组织",
            "GreenEnergy(ERC20) → 能量代币；PlantCertificate(ERC721) → 植树证书；EcoBadge(ERC1155) → 勋章/骑行券",
            "商业闭环：低碳行为→发能量→累积→兑换 NFT 资产→能量回收",
        ],
        "accept": ["阅读本页所有步骤描述", '明确下一步是"搭建链底层"'],
        "tutorialSteps": [],
        "achievements": [],
        "checks": [
            {"text": "阅读本页所有步骤描述", "kind": "manual"},
            {"text": '明确下一步是"搭建链底层"', "kind": "manual"},
        ],
    },
    {
        "id": "P1-2", "level": "P1", "to": "/cloud", "icon": "Monitor",
        "title": "搭建链底层 · 10 步搭链",
        "desc": "启动 4 节点联盟链 → 6 联盟组织接入 → 部署 GreenEnergy → 6 角色发能量链路验证",
        "keywords": ["FISCO-BCOS", "PBFT", "GreenEnergy", "节点启动"],
        "tag": "必修", "tagClass": "",
        "eta": "30 分钟",
        "goal": "亲手搭建一条联盟链并部署绿色能量代币合约",
        "kpoints": [
            "4 节点 PBFT 共识：3f+1 容错",
            "build_chain.sh 一键生成节点配置",
            "GreenEnergy 构造函数：initialSupply=1000000",
            "deploy → name/balanceOf/transfer 验证",
        ],
        "accept": [
            "完成 10/10 步骤",
            "成功部署 GreenEnergy 合约",
            "调用 name() 返回 GreenEnergy",
            "完成 6 角色发能量链路验证",
        ],
        # /cloud 页直接承载 TUTORIAL 全部 10 步（accept 第一条即 10/10）
        "tutorialSteps": list(range(1, _TUTORIAL_TOTAL + 1)),
        "achievements": ["first_deploy", "tutorial_complete"],
        "checks": [
            {"text": "完成 10/10 步骤", "kind": "metric", "key": "tutorial_done", "value": _TUTORIAL_TOTAL},
            {"text": "成功部署 GreenEnergy 合约", "kind": "metric", "key": "deployed_contracts", "value": 1},
            {"text": "调用 name() 返回 GreenEnergy", "kind": "manual"},
            {"text": "完成 6 角色发能量链路验证", "kind": "manual"},
        ],
    },
    {
        "id": "P2-1", "level": "P2", "to": "/ide", "icon": "EditPen",
        "title": "开发业务合约 · PlantCertificate + EcoBadge",
        "desc": "从内置模板起步：查看 GreenEnergy/PlantCertificate/EcoBadge 源码 → Solc 编译 → 部署",
        "keywords": ["Solidity", "ERC721", "ERC1155", "编译部署"],
        "eta": "15 分钟",
        "goal": "理解 3 份业务合约的 Solidity 实现并独立编译部署",
        "kpoints": [
            "PlantCertificate(ERC721)：每份证书唯一，含树种 ID + URI",
            "EcoBadge(ERC1155)：半同质化，badge ID=1 勋章 / ID=2 骑行券",
            "GreenEnergy(ERC20)：mint(to,value,reason) 向用户发放能量",
        ],
        "accept": ["至少查看 3 份内置合约源码", "独立编译成功 ≥1 次", "成功部署 PlantCertificate 或 EcoBadge"],
        "tutorialSteps": [],
        "achievements": ["first_compile", "first_deploy"],
        "checks": [
            {"text": "至少查看 3 份内置合约源码", "kind": "metric", "key": "builtin_viewed_contracts", "value": 3},
            {"text": "独立编译成功 ≥1 次", "kind": "metric", "key": "contract_compile_ok", "value": 1},
            {"text": "成功部署 PlantCertificate 或 EcoBadge", "kind": "metric", "key": "deployed_asset_contracts", "value": 1},
        ],
    },
    {
        "id": "P2-2", "level": "P2", "to": "/contracts", "icon": "Files",
        "title": "管理已部署合约 · 3 合约体系",
        "desc": "查看 GreenEnergy / PlantCertificate / EcoBadge 部署状态，确认 3 合约全部就绪",
        "keywords": ["合约地址", "ERC20/721/1155", "部署状态"],
        "eta": "5 分钟",
        "goal": "确认 3 份系统合约全部部署成功，记录合约地址",
        "kpoints": [
            "GreenEnergy：绿色能量代币（ERC20）",
            "PlantCertificate：植树证书（ERC721）",
            "EcoBadge：生态勋章+骑行券（ERC1155）",
        ],
        "accept": ["3/3 合约全部部署", "能区分 3 种代币标准的用途"],
        "tutorialSteps": [],
        "achievements": ["first_deploy"],
        "checks": [
            {"text": "3/3 合约全部部署", "kind": "metric", "key": "deployed_system_contracts", "value": 3},
            {"text": "能区分 3 种代币标准的用途", "kind": "manual"},
        ],
    },
    {
        "id": "P2-3", "level": "P2", "to": "/interfaces", "icon": "Connection",
        "title": "接口调试 · 验证合约方法",
        "desc": "通过 ABI 调试 GreenEnergy.mint() / PlantCertificate.mint() / EcoBadge.mint() 等核心方法",
        "keywords": ["ABI", "mint", "balanceOf", "view vs send"],
        "eta": "10 分钟",
        "goal": '能用在线接口独立完成"读 + 写"两类合约调用',
        "kpoints": [
            "GreenEnergy.mint(to,value,reason) → 发放能量",
            "PlantCertificate.mint(to,tokenId,speciesId,uri) → 铸造证书",
            "call（只读不花 Gas）vs send（写上链花 Gas）",
        ],
        "accept": ["成功调用 ≥1 个 view 方法（如 balanceOf）", "成功调用 ≥1 个写方法并上链"],
        "tutorialSteps": [],
        "achievements": [],
        "checks": [
            {"text": "成功调用 ≥1 个 view 方法（如 balanceOf）", "kind": "metric", "key": "interface_invoke", "value": 1},
            {"text": "成功调用 ≥1 个写方法并上链", "kind": "metric", "key": "transactions", "value": 1},
        ],
    },
    {
        "id": "P3-1", "level": "P3", "to": "/eco", "icon": "Promotion",
        "title": "联盟治理与运营 · 6 角色 + 能量 + 兑换",
        "desc": "配置 6 大联盟角色权限 → 5 种低碳场景发放绿色能量 → 兑换植树证书/勋章/骑行券",
        "keywords": ["角色权限", "能量发放", "资产兑换", "商业闭环"],
        "tag": "核心", "tagClass": "accent",
        "eta": "40 分钟",
        "goal": "完成绿色低碳联盟链的完整商业闭环：角色→发能量→兑换→回收",
        "kpoints": [
            "6 角色：管理员(管理树种) / 地铁(50) / 公交(20) / 单车(15) / 外卖(10) / 回收(100)",
            "能量发放：各角色按业务规则向用户钱包 mint 绿色能量",
            "兑换闭环：能量→transfer(admin)→mint NFT 证书/勋章，能量回收至管理员",
        ],
        "accept": ["完成 6/6 角色切换体验", "能量发放 ≥3 种不同角色", "兑换 ≥2 类不同资产（证书/勋章/骑行券）"],
        "tutorialSteps": [],
        "achievements": ["role_all_six", "eco_participant", "nft_collector"],
        "checks": [
            {"text": "完成 6/6 角色切换体验", "kind": "metric", "key": "eco_roles_switched", "value": 6},
            {"text": "能量发放 ≥3 种不同角色", "kind": "metric", "key": "eco_issue_roles", "value": 3},
            {"text": "兑换 ≥2 类不同资产（证书/勋章/骑行券）", "kind": "metric", "key": "eco_exchange_kinds", "value": 2},
        ],
    },
    {
        "id": "P3-2", "level": "P3", "to": "/wallet", "icon": "Wallet",
        "title": "能量钱包 · 查询绿色能量余额",
        "desc": "查询钱包中的 GreenEnergy 余额、能量转账记录、辅助理解能量流转",
        "keywords": ["余额查询", "能量流转", "ERC20"],
        "tag": "工具", "tagClass": "info",
        "eta": "5 分钟",
        "goal": "能独立查询任意地址的绿色能量余额并理解能量流向",
        "kpoints": [
            "balanceOf(address) 查询能量余额",
            "transfer(to,amount) 发起链上能量转账",
            "能量从联盟成员→用户→管理员（兑换回收）的流转路径",
        ],
        "accept": ["成功查询 ≥1 个地址的能量余额", '理解能量"发放→累积→消耗"的流转模型'],
        "tutorialSteps": [],
        "achievements": [],
        "checks": [
            {"text": "成功查询 ≥1 个地址的能量余额", "kind": "manual"},
            {"text": '理解能量"发放→累积→消耗"的流转模型', "kind": "manual"},
        ],
    },
    {
        "id": "P3-3", "level": "P3", "to": "/nft", "icon": "Picture",
        "title": "绿色资产市场 · NFT 铸造与交易",
        "desc": "铸造 ERC721/1155 绿色资产 NFT、上架交易，辅助理解植树证书/勋章的 NFT 本质",
        "keywords": ["NFT 铸造", "ERC721", "ERC1155", "资产交易"],
        "tag": "工具", "tagClass": "info",
        "eta": "10 分钟",
        "goal": "理解植树证书和生态勋章本质上就是 ERC721/ERC1155 NFT",
        "kpoints": [
            "ERC721：每件 NFT 唯一（如植树证书）",
            "ERC1155：同类批量（如勋章/骑行券）",
            "mint + safeTransferFrom 的资产流转机制",
        ],
        "accept": ["成功铸造 ≥1 件 NFT", "理解证书/勋章与 NFT 的对应关系"],
        "tutorialSteps": [],
        "achievements": ["nft_collector"],
        "checks": [
            {"text": "成功铸造 ≥1 件 NFT", "kind": "metric", "key": "nft_mint", "value": 1},
            {"text": "理解证书/勋章与 NFT 的对应关系", "kind": "manual"},
        ],
    },
    {
        "id": "P4-1", "level": "P4", "to": "/monitor", "icon": "BellFilled",
        "title": "调用监听器 · 监控业务调用",
        "desc": "观察能量发放、资产兑换的合约调用次数、方法分布、失败率，复盘业务运行",
        "keywords": ["调用统计", "方法分布", "Gas 消耗", "失败率"],
        "eta": "5 分钟",
        "goal": '会用监听器定位"哪个角色发了多少能量、兑换是否成功"',
        "kpoints": [
            "最近调用列表：按时间倒序",
            "失败调用标红（status=0）",
            "方法分布可辅助发现异常调用模式",
        ],
        "accept": ["能在列表中找到自己刚才的 mint/transfer 调用", "理解 status=1 成功 / 0 失败的含义"],
        "tutorialSteps": [],
        "achievements": [],
        "checks": [
            {"text": "能在列表中找到自己刚才的 mint/transfer 调用", "kind": "metric", "key": "contract_calls", "value": 1},
            {"text": "理解 status=1 成功 / 0 失败的含义", "kind": "manual"},
        ],
    },
    {
        "id": "P4-2", "level": "P4", "to": "/explorer", "icon": "Search",
        "title": "区块链浏览器 · 链上验证",
        "desc": "按高度查块、按 hash 查交易，验证能量发放和资产兑换真的上链了",
        "keywords": ["区块查询", "交易解码", "事件日志", "链上验证"],
        "eta": "5 分钟",
        "goal": '能独立用浏览器验证"一笔能量发放交易真的上链了"',
        "kpoints": [
            "区块：height / timestamp / txRoot",
            "交易：from / to / input data 解码",
            "Receipt：logs 事件（Transfer / Mint）",
        ],
        "accept": ["输入一笔 tx_hash 查到对应交易", "能解码出 Transfer 事件参数"],
        "tutorialSteps": [],
        "achievements": ["first_tx"],
        "checks": [
            {"text": "输入一笔 tx_hash 查到对应交易", "kind": "metric", "key": "transactions", "value": 1},
            {"text": "能解码出 Transfer 事件参数", "kind": "manual"},
        ],
    },
]


# ---------------------------------------------------------------------------
# 服务端核验引擎（读侧统计一律走 resolve_wallet_candidates 候选集 + lower(col) IN）
# ---------------------------------------------------------------------------

def _norm_role_keys(values: Any) -> set:
    """埋点 target 的角色 key 归一化去重（与 achievements.py 口径一致）。"""
    out: set = set()
    for r in values or ():
        k = (r or "").strip().lower()
        out.add(_ROLE_ALIAS.get(k, k))
    out.discard("")
    return out


def _extra_metrics(cands: list) -> dict:
    """events.aggregate 之外的补充核验指标（各源独立容错，表不存在按 0 处理）。"""
    out = {
        "builtin_viewed_contracts": 0,   # 查看过的内置合约源码去重数（IDE 模板打开埋点）
        "deployed_asset_contracts": 0,   # PlantCertificate / EcoBadge 部署数
        "deployed_system_contracts": 0,  # 3 份系统合约去重部署数
        "eco_roles_switched": 0,         # 切换过的联盟角色去重数（6 角色口径）
        "eco_issue_roles": 0,            # 发放过能量的角色去重数（按埋点 target）
        "eco_exchange_kinds": 0,         # 兑换过的资产类别数（证书 / 勋章·骑行券）
    }
    h, lc = lower_wallet_in(cands)
    if not lc:
        return out
    try:
        with get_conn() as conn:
            out["builtin_viewed_contracts"] = conn.execute(
                f"SELECT COUNT(DISTINCT target) AS c FROM learning_events "
                f"WHERE lower(wallet) IN ({h}) AND event_type=?",
                (*lc, EventType.IDE_OPEN_BUILTIN),
            ).fetchone()["c"]
            out["deployed_asset_contracts"] = conn.execute(
                f"SELECT COUNT(*) AS c FROM deployed_contracts WHERE lower(deployer) IN ({h}) "
                f"AND lower(name) IN ('plantcertificate','ecobadge')",
                lc,
            ).fetchone()["c"]
            out["deployed_system_contracts"] = conn.execute(
                f"SELECT COUNT(DISTINCT lower(name)) AS c FROM deployed_contracts "
                f"WHERE lower(deployer) IN ({h}) "
                f"AND lower(name) IN {_SYSTEM_CONTRACT_NAMES}",
                lc,
            ).fetchone()["c"]
            out["eco_roles_switched"] = len(_norm_role_keys([
                r["target"] for r in conn.execute(
                    f"SELECT target FROM learning_events "
                    f"WHERE lower(wallet) IN ({h}) AND event_type=?",
                    (*lc, EventType.ECO_ROLE_SWITCH),
                ).fetchall()
            ]))
            out["eco_issue_roles"] = len(_norm_role_keys([
                r["target"] for r in conn.execute(
                    f"SELECT target FROM learning_events "
                    f"WHERE lower(wallet) IN ({h}) AND event_type=?",
                    (*lc, EventType.ECO_ENERGY_ISSUE),
                ).fetchall()
            ]))
            kinds = conn.execute(
                f"SELECT COUNT(DISTINCT event_type) AS c FROM learning_events "
                f"WHERE lower(wallet) IN ({h}) AND event_type IN (?,?)",
                (*lc, EventType.ECO_CERT_EXCHANGE, EventType.ECO_BADGE_EXCHANGE),
            ).fetchone()["c"]
            out["eco_exchange_kinds"] = int(kinds)
    except Exception:
        # 表不存在 / 库异常：保留默认 0 值，不影响其余指标
        pass
    return out


def _tutorial_done_count(cands: list, steps: list) -> int:
    """chain_tutorial_progress 中指定步骤的 done 去重计数（懒建表容错为 0）。"""
    if not steps:
        return 0
    h, lc = lower_wallet_in(cands)
    if not lc:
        return 0
    try:
        with get_conn() as conn:
            ph = ",".join("?" * len(steps))
            return conn.execute(
                f"SELECT COUNT(DISTINCT step) AS c FROM chain_tutorial_progress "
                f"WHERE lower(wallet) IN ({h}) AND done=1 AND step IN ({ph})",
                (*lc, *steps),
            ).fetchone()["c"]
    except Exception:
        return 0


def _achieved_achievement_ids(cands: list) -> set:
    """user_achievements 中已完成（completed=1）的成就 id 集合（表不存在容错为空）。"""
    h, lc = lower_wallet_in(cands)
    if not lc:
        return set()
    try:
        with get_conn() as conn:
            rows = conn.execute(
                f"SELECT achievement_id FROM user_achievements "
                f"WHERE lower(wallet) IN ({h}) AND completed=1",
                lc,
            ).fetchall()
            return {r["achievement_id"] for r in rows}
    except Exception:
        return set()


def _build_read_model(wallet: str) -> dict:
    """聚合读模型：候选集 / 指标计数 / 已获得成就（任何一环失败都降级空态）。"""
    empty = {"cands": [], "metrics": {}, "achieved": set()}
    try:
        with get_conn() as conn:
            cands = resolve_wallet_candidates(conn, wallet)
    except Exception:
        return empty
    try:
        metrics = dict(aggregate(cands))
    except Exception:
        metrics = {}
    try:
        metrics.update(_extra_metrics(cands))
    except Exception:
        pass
    try:
        achieved = _achieved_achievement_ids(cands)
    except Exception:
        achieved = set()
    return {"cands": cands, "metrics": metrics, "achieved": achieved}


def _resolve_check(chk: dict, metrics: dict, achieved: set) -> dict:
    """把单条 accept 核验规则解析为响应结构（manual 项只展示不判定）。"""
    kind = chk.get("kind", "manual")
    out: dict[str, Any] = {
        "text": chk.get("text", ""),
        "kind": kind,
        "manual": kind == "manual",
        "verified": False,
    }
    if kind == "metric":
        cur = int(metrics.get(chk.get("key", ""), 0) or 0)
        target = int(chk.get("value", 1))
        out["current"] = cur
        out["target"] = target
        out["verified"] = cur >= target
    elif kind == "achievement":
        out["achievement_id"] = chk.get("id", "")
        out["verified"] = chk.get("id", "") in achieved
    return out


@router.get("/path")
def learning_path(wallet: str = "", user: Optional[dict] = Depends(optional_user)):
    """学习路径单一事实源：P1-P4 十步清单 + 每阶段服务端核验状态。

    身份口径：JWT wallet 优先（不可伪造）；query wallet 仅作未登录演示
    降级（未登录且无 wallet 时候选集回落 0xlearner 演示口径）。

    响应：{ wallet, total, stages: [{ id, level, to, icon, title, desc,
    keywords, tag, tagClass, eta, goal, kpoints, accept, tutorialSteps,
    achievements, progress: { tutorial_progress, achievements, checks,
    auto_total }, verified }] }。表不存在 / 空数据兜底空态，不抛错。
    """
    w = ((user or {}).get("wallet") or wallet or "").strip()
    rm = _build_read_model(w)
    metrics: dict = rm["metrics"]
    achieved: set = rm["achieved"]
    cands: list = rm["cands"]

    stages: list[dict[str, Any]] = []
    for st in STAGE_PATH:
        checks = [_resolve_check(c, metrics, achieved) for c in st["checks"]]
        auto = [c for c in checks if not c["manual"]]
        tp = None
        if st.get("tutorialSteps"):
            tp = {
                "done": _tutorial_done_count(cands, st["tutorialSteps"]),
                "total": len(st["tutorialSteps"]),
            }
        ach = None
        if st.get("achievements"):
            ach = {
                "achieved": [a for a in st["achievements"] if a in achieved],
                "total": len(st["achievements"]),
            }
        stage = {k: v for k, v in st.items() if k != "checks"}
        stage["progress"] = {
            "tutorial_progress": tp,
            "achievements": ach,
            "checks": checks,
            "auto_total": len(auto),
        }
        # verified = 存在可自动核验项 且 全部通过（全 manual 的阶段保持 false）
        stage["verified"] = bool(auto) and all(c["verified"] for c in auto)
        stages.append(stage)

    return {
        "wallet": w or "0xlearner",
        "total": len(stages),
        "stages": stages,
    }
