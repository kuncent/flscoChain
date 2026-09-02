"""成就系统 API（成就定义、用户进度、挑战任务、排行榜）。

身份与安全（JWT 上线后重构）：
  - 所有个人化接口不再信任 X-Wallet 自报头，钱包统一从 JWT 上下文
    （security.get_current_user / optional_user）解析；
  - 统计源按真实数据核对修正：
      * tutorial_progress  → chain_tutorial_progress 表 done=1 步数百分比
                             （旧实现查询不存在的 progress 列，成就永不可达）；
      * transactions       → 链客户端 list_txs() 按钱包过滤统计（三模式兼容，
                             异常容错返回 0；evm 模式交易不落 DB transactions 表）；
      * security_audits    → learning_events.event_type='contract_audit'
                             （埋点真实事件名，旧实现查 'security_audit' 恒为 0）；
  - 挑战进度完全服务端计算（按 learning_events / eco_energy_records 行为记录），
    客户端无法伪造；达到条件自动置 completed / completed_at；
  - 成就检查改为"惰性自动"：读取 /my、/stats 时顺带执行发放检查，
    /check 端点保留兼容。
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..chain_client import get_chain_client
from ..db import get_conn, now, scope_where
from ..security import (
    get_current_user,
    optional_user,
    lower_wallet_in,
    resolve_wallet_candidates,
)
from ..learning.tutorial_steps import TUTORIAL
from ..learning.events import EventType

router = APIRouter(prefix="/api/achievements", tags=["achievements"])

# 搭链教程总步数（与搭链云桌面保持一致，用于换算教程完成百分比）
_TUTORIAL_TOTAL = max(1, len(TUTORIAL))


# ==================== 种子数据 ====================

ACHIEVEMENTS_SEED = [
    {
        "id": "first_compile",
        "name": "初次编译",
        "description": "成功编译第一个智能合约",
        "icon": "🔨",
        "category": "development",
        "condition_type": "contract_compile_ok",
        "condition_value": 1,
        "points": 10,
    },
    {
        "id": "compile_master",
        "name": "编译大师",
        "description": "成功编译 10 个智能合约",
        "icon": "⚒️",
        "category": "development",
        "condition_type": "contract_compile_ok",
        "condition_value": 10,
        "points": 50,
    },
    {
        "id": "first_deploy",
        "name": "初次部署",
        "description": "成功部署第一个智能合约",
        "icon": "🚀",
        "category": "deployment",
        "condition_type": "deployed_contracts",
        "condition_value": 1,
        "points": 20,
    },
    {
        "id": "deploy_expert",
        "name": "部署专家",
        "description": "成功部署 5 个智能合约",
        "icon": "🛸",
        "category": "deployment",
        "condition_type": "deployed_contracts",
        "condition_value": 5,
        "points": 100,
    },
    {
        "id": "first_tx",
        "name": "初次交易",
        "description": "完成第一笔链上交易",
        "icon": "💰",
        "category": "transaction",
        "condition_type": "transactions",
        "condition_value": 1,
        "points": 15,
    },
    {
        "id": "tx_whale",
        "name": "交易巨鲸",
        "description": "完成 50 笔链上交易",
        "icon": "🐋",
        "category": "transaction",
        "condition_type": "transactions",
        "condition_value": 50,
        "points": 200,
    },
    {
        "id": "eco_participant",
        "name": "生态参与者",
        "description": "参与低碳联盟生态活动 1 次",
        "icon": "🌱",
        "category": "ecology",
        "condition_type": "eco_energy_records",
        "condition_value": 1,
        "points": 20,
    },
    {
        "id": "eco_master",
        "name": "生态大师",
        "description": "参与低碳联盟生态活动 20 次",
        "icon": "🌳",
        "category": "ecology",
        "condition_type": "eco_energy_records",
        "condition_value": 20,
        "points": 150,
    },
    {
        "id": "nft_collector",
        "name": "NFT 收藏家",
        "description": "铸造或拥有第一个 NFT",
        "icon": "🎨",
        "category": "nft",
        "condition_type": "nft_tokens",
        "condition_value": 1,
        "points": 30,
    },
    {
        "id": "tutorial_complete",
        "name": "教程完成者",
        "description": "完成所有链上教程",
        "icon": "📚",
        "category": "learning",
        "condition_type": "tutorial_progress",
        "condition_value": 100,
        "points": 50,
    },
    {
        "id": "gas_optimizer",
        "name": "Gas 优化师",
        "description": "通过优化节省 1000 Gas",
        "icon": "⛽",
        "category": "optimization",
        "condition_type": "gas_saved",
        "condition_value": 1000,
        "points": 80,
    },
    {
        "id": "security_auditor",
        "name": "安全审计员",
        "description": "完成 5 次合约安全审计",
        "icon": "🔒",
        "category": "security",
        "condition_type": "security_audits",
        "condition_value": 5,
        "points": 120,
    },
    {
        "id": "audit_first",
        "name": "审计初体验",
        "description": "完成 1 次合约安全审计（在合约模块调用 /audit）",
        "icon": "🧐",
        "category": "security",
        "condition_type": "security_audits",
        "condition_value": 1,
        "points": 30,
    },
    {
        "id": "role_all_six",
        "name": "联盟全能角色",
        "description": "切换过全部 6 个低碳联盟角色（管理员/地铁/公交/单车/外卖/回收，"
                       "按角色去重计数，兼容旧别名）",
        "icon": "🤝",
        "category": "ecology",
        "condition_type": "eco_roles_used",
        "condition_value": 6,
        "points": 100,
    },
    {
        "id": "curriculum_l5",
        "name": "编程关卡通关",
        "description": "完成编程关卡（漏洞修复）：累计 2 次合约审计高危项清零"
                       "（修复 bugs 关卡合约后重新 /audit，无 high 风险即算通过）",
        "icon": "🏅",
        "category": "development",
        "condition_type": "audit_pass_count",
        "condition_value": 2,
        "points": 120,
    },
]

CHALLENGES_SEED = [
    {
        "id": "daily_compile",
        "name": "每日编译挑战",
        "description": "在一天内编译 3 个合约",
        "category": "daily",
        "difficulty": "easy",
        "points": 30,
        "condition_type": "contract_compile_ok",
        "condition_value": 3,
        "expires_at": None,
    },
    {
        "id": "gas_challenge",
        "name": "Gas 挑战",
        "description": "在一天内节省 500 Gas",
        "category": "daily",
        "difficulty": "medium",
        "points": 50,
        "condition_type": "gas_saved",
        "condition_value": 500,
        "expires_at": None,
    },
    {
        "id": "eco_chain",
        "name": "生态链挑战",
        "description": "连续 7 天参与生态活动",
        "category": "weekly",
        "difficulty": "hard",
        "points": 100,
        "condition_type": "eco_energy_records",
        "condition_value": 7,
        "expires_at": None,
    },
]


# ==================== 辅助函数 ====================

def _ensure_seed_data() -> None:
    """确保种子数据幂等入库（已存在则跳过）。"""
    with get_conn() as conn:
        # 成就种子
        for ach in ACHIEVEMENTS_SEED:
            existing = conn.execute(
                "SELECT id FROM achievements WHERE id=?", (ach["id"],)
            ).fetchone()
            if not existing:
                conn.execute(
                    """INSERT INTO achievements(id, name, description, icon, category,
                       condition_type, condition_value, points, created_at)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        ach["id"],
                        ach["name"],
                        ach["description"],
                        ach["icon"],
                        ach["category"],
                        ach["condition_type"],
                        ach["condition_value"],
                        ach["points"],
                        now(),
                    ),
                )
        # 挑战种子
        for ch in CHALLENGES_SEED:
            existing = conn.execute(
                "SELECT id FROM challenges WHERE id=?", (ch["id"],)
            ).fetchone()
            if not existing:
                conn.execute(
                    """INSERT INTO challenges(id, name, description, category, difficulty,
                       points, condition_type, condition_value, expires_at, created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        ch["id"],
                        ch["name"],
                        ch["description"],
                        ch["category"],
                        ch["difficulty"],
                        ch["points"],
                        ch["condition_type"],
                        ch["condition_value"],
                        ch["expires_at"],
                        now(),
                    ),
                )


def _count_chain_txs(wallet: str) -> int:
    """从链客户端统计该钱包参与的链上交易数。

    兼容 fisco / evm / mock 三模式（evm 模式交易不落 DB transactions 表，
    必须走链客户端）；任何异常（链未就绪 / RPC 失败）容错返回 0。
    """
    try:
        client = get_chain_client()
        txs = client.list_txs(limit=10000)
        w = (wallet or "").lower()
        if not w:
            return 0
        return sum(
            1 for t in txs
            if (t.from_addr or "").lower() == w or (t.to_addr or "").lower() == w
        )
    except Exception:
        return 0


def _compute_user_stats(wallet: str, user_id: str | None = None) -> dict:
    """从多个真实数据源统计用户行为数据（各源独立容错）。

    口径：所有按钱包的查询统一改用 security.resolve_wallet_candidates 候选集
    + lower(col) 归一（双轨口径：写路径 0xlearner / 读路径 userId，消除恒 0）。

    多租户 scope 浅接线（任务 #15）：user_id 非空时对确认带租户列的表叠加
    db.scope_where 过滤（本用户 + 未登记归属旧行）；None 时不过滤，
    与既有行为完全一致。eco_energy_records 历史建表无租户列，不叠加。
    """
    stats = {
        "contract_compile_ok": 0,
        "deployed_contracts": 0,
        "transactions": 0,
        "eco_energy_records": 0,
        "nft_tokens": 0,
        "tutorial_progress": 0,
        "gas_saved": 0,
        "security_audits": 0,
        "eco_roles_used": 0,
        "audit_pass_count": 0,
    }

    with get_conn() as conn:
        # 钱包候选集（wallet 原值 / user_id / user_info 登记 wallet / '0xlearner' 去重）
        cands = resolve_wallet_candidates(conn, wallet)
        h, lc = lower_wallet_in(cands)

        # 多租户 scope 片段（确认带 user_id 列的表才叠加，见 db.scope_where）
        _sc_le, _sc_le_p = scope_where("learning_events", user_id=user_id)
        _sc_dc, _sc_dc_p = scope_where("deployed_contracts", user_id=user_id)
        _sc_nft, _sc_nft_p = scope_where("nfts", user_id=user_id)
        _sc_tp, _sc_tp_p = scope_where("chain_tutorial_progress", user_id=user_id)

        # 编译成功次数（IDE / 搭链教程埋点：event_type='contract_compile_ok'）
        try:
            row = conn.execute(
                f"SELECT COUNT(*) as cnt FROM learning_events "
                f"WHERE lower(wallet) IN ({h}) AND event_type='{EventType.CONTRACT_COMPILE_OK}'"
                + (" AND " + _sc_le if _sc_le else ""),
                [*lc, *_sc_le_p],
            ).fetchone()
            stats["contract_compile_ok"] = row["cnt"] if row else 0
        except Exception:
            pass

        # 部署合约数（deployed_contracts 表，deployer 为操作钱包）
        try:
            row = conn.execute(
                f"SELECT COUNT(*) as cnt FROM deployed_contracts "
                f"WHERE lower(deployer) IN ({h})"
                + (" AND " + _sc_dc if _sc_dc else ""),
                [*lc, *_sc_dc_p],
            ).fetchone()
            stats["deployed_contracts"] = row["cnt"] if row else 0
        except Exception:
            pass

        # 生态活动记录数（eco_energy_records 表，能量发放/兑换记录）
        try:
            row = conn.execute(
                f"SELECT COUNT(*) as cnt FROM eco_energy_records "
                f"WHERE lower(wallet) IN ({h})",
                lc,
            ).fetchone()
            stats["eco_energy_records"] = row["cnt"] if row else 0
        except Exception:
            # 表可能尚未初始化
            pass

        # NFT 数量（nfts 表 owner）
        try:
            row = conn.execute(
                f"SELECT COUNT(*) as cnt FROM nfts WHERE lower(owner) IN ({h})"
                + (" AND " + _sc_nft if _sc_nft else ""),
                [*lc, *_sc_nft_p],
            ).fetchone()
            stats["nft_tokens"] = row["cnt"] if row else 0
        except Exception:
            pass

        # 教程进度：chain_tutorial_progress 表统计已完成（done=1）步数，
        # 换算为百分比（旧实现查询不存在的 progress 列，导致成就永不可达）
        try:
            row = conn.execute(
                f"SELECT COUNT(*) as cnt FROM chain_tutorial_progress "
                f"WHERE lower(wallet) IN ({h}) AND done=1"
                + (" AND " + _sc_tp if _sc_tp else ""),
                [*lc, *_sc_tp_p],
            ).fetchone()
            done_steps = row["cnt"] if row else 0
            stats["tutorial_progress"] = min(
                100, int(done_steps * 100 / _TUTORIAL_TOTAL)
            )
        except Exception:
            # 表可能尚未创建（未进入过搭链教程）
            pass

        # Gas 节省（行为埋点 extra.gas_saved 累计）
        try:
            row = conn.execute(
                f"SELECT SUM(CAST(JSON_EXTRACT(extra, '$.gas_saved') AS INTEGER)) as total "
                f"FROM learning_events WHERE lower(wallet) IN ({h}) "
                f"AND extra LIKE '%gas_saved%'"
                + (" AND " + _sc_le if _sc_le else ""),
                [*lc, *_sc_le_p],
            ).fetchone()
            stats["gas_saved"] = int(row["total"]) if row and row["total"] else 0
        except Exception:
            pass

        # 安全审计次数（真实埋点事件名为 contract_audit，见 contracts.py /audit）
        try:
            row = conn.execute(
                f"SELECT COUNT(*) as cnt FROM learning_events "
                f"WHERE lower(wallet) IN ({h}) AND event_type='{EventType.CONTRACT_AUDIT}'"
                + (" AND " + _sc_le if _sc_le else ""),
                [*lc, *_sc_le_p],
            ).fetchone()
            stats["security_audits"] = row["cnt"] if row else 0
        except Exception:
            pass

        # 联盟角色去重数（6 个角色全部切换过 → 成就 role_all_six）。
        # eco_role_switch 埋点 target 存 role_key（select_role 校验走 _find_role，
        # 可能带旧别名 delivery/recycle），Python 端归一化别名后再去重计数。
        try:
            rows = conn.execute(
                f"SELECT DISTINCT target FROM learning_events "
                f"WHERE lower(wallet) IN ({h}) AND event_type='{EventType.ECO_ROLE_SWITCH}'"
                + (" AND " + _sc_le if _sc_le else ""),
                [*lc, *_sc_le_p],
            ).fetchall()
            _alias = {"delivery": "takeout", "recycle": "recycling"}
            keys = {
                _alias.get((r["target"] or "").strip().lower(), (r["target"] or "").strip().lower())
                for r in rows
            }
            keys.discard("")
            stats["eco_roles_used"] = len(keys)
        except Exception:
            pass

        # 编程关卡口径：审计通过次数（curriculum_l5，语义=「修复 bugs 关卡后达标」）。
        # 收紧方案（成本最低且精确）：target 限定为 bugs 关卡合约名
        # （contracts.py CONTRACT_FILES 的 ReentrantVault / PhishingAuth，
        # /audit 埋点 target=req.name 即合约名）且 high 风险清零。
        # JSON_EXTRACT(extra,'$.high') IS NOT NULL 防御历史无 high 字段的旧埋点
        # （JSON_EXTRACT 对缺失字段返回 NULL，CAST 后为 0，会被误判为通过）。
        try:
            row = conn.execute(
                f"SELECT COUNT(*) as cnt FROM learning_events "
                f"WHERE lower(wallet) IN ({h}) AND event_type='{EventType.CONTRACT_AUDIT}' "
                f"AND JSON_EXTRACT(extra, '$.high') IS NOT NULL "
                f"AND CAST(JSON_EXTRACT(extra, '$.high') AS INTEGER)=0 "
                f"AND lower(target) IN ('reentrantvault','phishingauth')"
                + (" AND " + _sc_le if _sc_le else ""),
                [*lc, *_sc_le_p],
            ).fetchone()
            stats["audit_pass_count"] = row["cnt"] if row else 0
        except Exception:
            pass

    # 交易数：走链客户端（三模式兼容），不依赖 DB transactions 表；
    # 按候选集逐钱包求和（候选集通常仅 1~2 项；跨候选重复计入同一笔
    # 双向交易的概率可忽略，口径一致性优先）
    stats["transactions"] = sum(_count_chain_txs(c) for c in dict.fromkeys(cands))

    return stats


def _check_and_grant_achievement(wallet: str, achievement: dict, stats: dict) -> bool:
    """检查用户是否满足成就条件，满足则发放。返回是否新获得。"""
    condition_type = achievement["condition_type"]
    condition_value = achievement["condition_value"]
    current_value = stats.get(condition_type, 0)

    if current_value < condition_value:
        # 未达标：同步最新进度（若已有记录），便于前端展示进度条
        with get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM user_achievements WHERE wallet=? AND achievement_id=?",
                (wallet, achievement["id"]),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE user_achievements SET progress=? WHERE wallet=? AND achievement_id=?",
                    (int(current_value), wallet, achievement["id"]),
                )
        return False

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM user_achievements WHERE wallet=? AND achievement_id=?",
            (wallet, achievement["id"]),
        ).fetchone()

        if existing:
            # 已获得，仅刷新进度
            conn.execute(
                "UPDATE user_achievements SET progress=?, completed=1 "
                "WHERE wallet=? AND achievement_id=?",
                (int(current_value), wallet, achievement["id"]),
            )
            return False
        # 新获得
        conn.execute(
            """INSERT INTO user_achievements(wallet, achievement_id, earned_at, progress, completed)
               VALUES(?,?,?,?,1)""",
            (wallet, achievement["id"], now(), int(current_value)),
        )
        return True


def _run_achievement_check(wallet: str, user_id: str | None = None) -> tuple[dict, list]:
    """惰性自动检查：统计真实数据 → 逐项判定发放。返回 (stats, 新达成 id 列表)。

    节流：/my、/stats 等读接口会顺带触发全量成就检查（每钱包十余次统计查询），
    高频刷新开销可观。模块级 dict 记录每钱包上次全量检查时间戳，60 秒内重复
    请求直接返回缓存结果（内存时间戳，进程重启即失效，可接受）。
    锁仅保护 dict 读写（仿 db.py 模块级 threading.Lock 风格），DB 操作在锁外。
    缓存键含 user_id：stats 计算叠加了 scope 过滤（user_id 非空时），
    同一钱包不同身份上下文的结果可能不同，键必须区分。
    """
    wallet = (wallet or "").strip()
    uid = (user_id or "").strip() or None
    if not wallet:
        logging.warning(
            "achievements: 收到空 wallet 的成就检查请求（JWT 上下文缺 wallet），"
            "统计将仅命中演示钱包候选，请检查登录态/身份口径"
        )
    now_ts = time.time()
    cache_key = f"{wallet}|{uid or ''}"
    with _ACHV_CHECK_LOCK:
        cached = _ACHV_CHECK_CACHE.get(cache_key)
        if cached and (now_ts - cached[0]) < _ACHV_CHECK_TTL_SECONDS:
            return cached[1], list(cached[2])

    _ensure_seed_data()
    stats = _compute_user_stats(wallet, uid)
    with get_conn() as conn:
        all_achievements = conn.execute("SELECT * FROM achievements").fetchall()
    newly_earned = []
    for ach in all_achievements:
        if _check_and_grant_achievement(wallet, dict(ach), stats):
            newly_earned.append(ach["id"])

    with _ACHV_CHECK_LOCK:
        _ACHV_CHECK_CACHE[cache_key] = (now_ts, stats, newly_earned)
        # 防膨胀：超过阈值时粗略清理过期条目（量级=活跃钱包数，通常很小）
        if len(_ACHV_CHECK_CACHE) > 512:
            expired = [
                k for k, v in _ACHV_CHECK_CACHE.items()
                if now_ts - v[0] >= _ACHV_CHECK_TTL_SECONDS
            ]
            for k in expired:
                _ACHV_CHECK_CACHE.pop(k, None)
    return stats, newly_earned


# ---------- 挑战进度：服务端计算（拒绝客户端任意加数） ----------

# 懒检查节流缓存：wallet -> (上次全量检查时间戳, stats, 新达成 id 列表)
_ACHV_CHECK_TTL_SECONDS = 60.0
_ACHV_CHECK_LOCK = threading.Lock()
_ACHV_CHECK_CACHE: dict[str, tuple[float, dict, list]] = {}


def _challenge_window(conn, wallet: str, challenge: dict, started_at: Optional[str]):
    """返回 (SQL 时间过滤片段, 参数)，限定挑战进度统计窗口。

    - daily 类：统计"开始挑战当天"的行为（一天内完成）；
    - 其它：统计开始挑战之后的行为。
    """
    day = (started_at or "")[:10]
    if not day:
        return "", []
    if challenge.get("category") == "daily":
        return " AND substr(created_at, 1, 10) = ?", [day]
    return " AND created_at >= ?", [str(started_at)]


def _compute_challenge_progress(conn, wallet: str, challenge: dict,
                                started_at: Optional[str],
                                user_id: str | None = None) -> int:
    """按行为记录表服务端计算挑战进度（不可被客户端伪造）。

    行为表口径与成就统计一致：钱包候选集 + lower(wallet) 归一
    （挑战进度原先按 wallet=? 单值查，写路径 0xlearner 的埋点恒查不到）。
    多租户 scope：learning_events 叠加 db.scope_where（user_id 非空时）；
    eco_energy_records 历史建表无租户列，不叠加。
    """
    cond, params = _challenge_window(conn, wallet, challenge, started_at)
    h, lc = lower_wallet_in(resolve_wallet_candidates(conn, wallet))
    _sc_le, _sc_le_p = scope_where("learning_events", user_id=user_id)
    _le_sc = " AND " + _sc_le if _sc_le else ""
    ctype = challenge.get("condition_type") or ""
    try:
        if ctype == "contract_compile_ok":
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM learning_events "
                f"WHERE lower(wallet) IN ({h}) AND event_type='{EventType.CONTRACT_COMPILE_OK}'{cond}{_le_sc}",
                [*lc, *params, *_sc_le_p],
            ).fetchone()
            return row["cnt"] if row else 0
        if ctype == "gas_saved":
            row = conn.execute(
                "SELECT SUM(CAST(JSON_EXTRACT(extra, '$.gas_saved') AS INTEGER)) as total "
                f"FROM learning_events WHERE lower(wallet) IN ({h}) "
                f"AND extra LIKE '%gas_saved%'{cond}{_le_sc}",
                [*lc, *params, *_sc_le_p],
            ).fetchone()
            return int(row["total"]) if row and row["total"] else 0
        if ctype == "eco_energy_records":
            # "连续 N 天"语义近似为：窗口内参与生态活动的不同天数
            row = conn.execute(
                "SELECT COUNT(DISTINCT substr(created_at, 1, 10)) as cnt "
                f"FROM eco_energy_records WHERE lower(wallet) IN ({h}){cond}",
                lc + params,
            ).fetchone()
            return row["cnt"] if row else 0
        # 其余条件类型：直接以成就统计口径兕底（透传 user_id 保持 scope 一致）
        stats = _compute_user_stats(wallet, user_id)
        return int(stats.get(ctype, 0))
    except Exception:
        return 0


def _sync_user_challenges(wallet: str, user_id: str | None = None) -> None:
    """服务端重算该钱包所有已参与挑战的进度，达标自动置 completed/completed_at。

    多租户 scope：user_id 非空时仅重算本用户（+未登记旧行）的挑战记录，
    他人已归属的挑战记录不越权重算（见 db.scope_where）。
    """
    with get_conn() as conn:
        sc, sp = scope_where("uc", user_id=user_id)
        rows = conn.execute(
            """SELECT uc.id as uc_id, uc.challenge_id, uc.started_at, uc.completed,
                      c.condition_type, c.condition_value, c.category
               FROM user_challenges uc
               JOIN challenges c ON c.id = uc.challenge_id
               WHERE uc.wallet=?""" + (" AND " + sc if sc else ""),
            (wallet, *sp),
        ).fetchall()
        for r in rows:
            if r["completed"] == 1:
                continue  # 已完成不回退
            progress = _compute_challenge_progress(
                conn, wallet, dict(r), r["started_at"], user_id
            )
            done = 1 if progress >= r["condition_value"] else 0
            conn.execute(
                "UPDATE user_challenges SET progress=?, completed=?, completed_at=? WHERE id=?",
                (progress, done, now() if done else None, r["uc_id"]),
            )


# ---------- 响应整形（对齐前端 AchievementBadge 组件字段） ----------

def _shape_achievement(ach: dict, user_row: Optional[dict], stats: dict) -> dict:
    """合并成就定义 + 用户进度，同时输出组件字段与兼容字段。"""
    out = dict(ach)
    completed = bool(user_row and user_row.get("completed"))
    progress = (
        int(user_row["progress"]) if user_row
        else int(stats.get(ach["condition_type"], 0))
    )
    earned_at = user_row.get("earned_at") if user_row else None
    out.update({
        # AchievementBadge 组件字段
        "obtained": completed,
        "current_progress": progress,
        "target_value": ach["condition_value"],
        "condition": ach["description"],
        "obtained_at": earned_at,
        # 兼容字段
        "progress": progress,
        "completed": 1 if completed else 0,
        "earned_at": earned_at,
    })
    return out


def _shape_challenge(ch: dict, user_row: Optional[dict]) -> dict:
    """合并挑战定义 + 用户进度，同时输出组件字段与兼容字段。"""
    out = dict(ch)
    started = bool(user_row)
    completed = bool(user_row and user_row.get("completed"))
    progress = int(user_row["progress"]) if user_row else 0
    out.update({
        # AchievementBadge 组件字段
        "started": started,
        "completed": completed,
        "current_progress": progress,
        "target_value": ch["condition_value"],
        "reward_points": ch["points"],
        # 兼容字段
        "progress": progress,
        "started_at": user_row.get("started_at") if user_row else None,
        "completed_at": user_row.get("completed_at") if user_row else None,
    })
    return out


# ==================== API 端点 ====================

@router.get("")
def list_achievements(user: Optional[dict] = Depends(optional_user)):
    """列出所有成就定义；已登录时惰性执行一次发放检查。"""
    _ensure_seed_data()
    if user:
        _run_achievement_check(user.get("wallet") or "", user.get("user_id") or None)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM achievements ORDER BY category, points"
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.get("/my")
def my_achievements(user: dict = Depends(get_current_user)):
    """当前用户成就进度（惰性自动检查并发放）。

    返回数组（字段对齐 AchievementBadge 组件：obtained / current_progress /
    target_value / points / obtained_at）。
    """
    wallet = user.get("wallet") or ""
    stats, _newly = _run_achievement_check(wallet, user.get("user_id") or None)

    # 多租户 scope：个人成就进度仅命中本用户归属 + 未登记旧行（见 db.scope_where）
    ua_sc, ua_sp = scope_where("user_achievements", user_id=user.get("user_id") or None)
    with get_conn() as conn:
        all_achievements = conn.execute(
            "SELECT * FROM achievements ORDER BY category, points"
        ).fetchall()
        user_ach = conn.execute(
            "SELECT achievement_id, progress, completed, earned_at "
            "FROM user_achievements WHERE wallet=?" + (" AND " + ua_sc if ua_sc else ""),
            (wallet, *ua_sp),
        ).fetchall()

    user_ach_map = {row["achievement_id"]: dict(row) for row in user_ach}
    return [
        _shape_achievement(dict(ach), user_ach_map.get(ach["id"]), stats)
        for ach in all_achievements
    ]


@router.post("/check")
def check_achievements(user: dict = Depends(get_current_user)):
    """检查并自动发放成就（保留兼容；/my 已内置惰性检查）。

    钱包以 JWT 身份为准，请求体中自报的 wallet 一律忽略。
    """
    wallet = user.get("wallet") or ""
    stats, newly_earned = _run_achievement_check(wallet, user.get("user_id") or None)
    return {"newly_earned": newly_earned, "stats": stats}


@router.get("/stats")
def achievement_stats(user: Optional[dict] = Depends(optional_user)):
    """成就排行榜（按积分排序）；已登录时先惰性检查当前用户。"""
    if user:
        _run_achievement_check(user.get("wallet") or "", user.get("user_id") or None)
    _ensure_seed_data()
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT ua.wallet as wallet, COUNT(*) as achievement_count,
                      SUM(a.points) as total_points
               FROM user_achievements ua
               JOIN achievements a ON ua.achievement_id = a.id
               WHERE ua.completed = 1
               GROUP BY ua.wallet
               ORDER BY total_points DESC, achievement_count DESC
               LIMIT 50"""
        ).fetchall()
    return {"leaderboard": [dict(r) for r in rows]}


@router.get("/challenges")
def list_challenges():
    """列出所有挑战任务定义。"""
    _ensure_seed_data()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM challenges ORDER BY difficulty, points"
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.get("/challenges/my")
def my_challenges(user: dict = Depends(get_current_user)):
    """当前用户挑战进度（服务端重算后返回）。

    返回数组（字段对齐 AchievementBadge 组件：started / current_progress /
    target_value / reward_points / difficulty）。
    """
    wallet = user.get("wallet") or ""
    _ensure_seed_data()
    _sync_user_challenges(wallet, user.get("user_id") or None)

    # 多租户 scope：仅返回本用户归属 + 未登记旧行的挑战进度（见 db.scope_where）
    uc_sc, uc_sp = scope_where("user_challenges", user_id=user.get("user_id") or None)
    with get_conn() as conn:
        all_challenges = conn.execute(
            "SELECT * FROM challenges ORDER BY difficulty, points"
        ).fetchall()
        user_ch = conn.execute(
            "SELECT challenge_id, progress, completed, started_at, completed_at "
            "FROM user_challenges WHERE wallet=?" + (" AND " + uc_sc if uc_sc else ""),
            (wallet, *uc_sp),
        ).fetchall()

    user_ch_map = {row["challenge_id"]: dict(row) for row in user_ch}
    return [
        _shape_challenge(dict(ch), user_ch_map.get(ch["id"]))
        for ch in all_challenges
    ]


class StartChallengeReq(BaseModel):
    challenge_id: str


@router.post("/challenges/start")
def start_challenge(req: StartChallengeReq, user: dict = Depends(get_current_user)):
    """开始挑战任务（钱包以 JWT 身份为准）。"""
    _ensure_seed_data()
    wallet = user.get("wallet") or ""

    with get_conn() as conn:
        challenge = conn.execute(
            "SELECT id FROM challenges WHERE id=?", (req.challenge_id,)
        ).fetchone()
        if not challenge:
            raise HTTPException(404, "挑战任务不存在")

        existing = conn.execute(
            "SELECT id FROM user_challenges WHERE wallet=? AND challenge_id=?",
            (wallet, req.challenge_id),
        ).fetchone()
        if existing:
            raise HTTPException(400, "挑战任务已开始")

        conn.execute(
            """INSERT INTO user_challenges(wallet, challenge_id, started_at, progress, completed)
               VALUES(?,?,?,0,0)""",
            (wallet, req.challenge_id, now()),
        )

    # 立即服务端重算一次（开始前的历史行为按窗口规则计入）
    _sync_user_challenges(wallet, user.get("user_id") or None)
    return {"ok": True, "message": "挑战已开始"}


class UpdateProgressReq(BaseModel):
    challenge_id: str
    # progress 字段仅保留以兼容旧客户端；服务端不再信任任何客户端上报值，
    # 进度一律由服务端按行为记录重算。
    progress: Optional[int] = None


@router.post("/challenges/progress")
def update_challenge_progress(
    req: UpdateProgressReq, user: dict = Depends(get_current_user)
):
    """刷新挑战进度（服务端重算）。

    安全改造：不再接受客户端任意加数，progress 入参被忽略；
    进度由 learning_events / eco_energy_records 行为记录在服务端计算，
    达标自动置 completed 与 completed_at。
    """
    _ensure_seed_data()
    wallet = user.get("wallet") or ""

    with get_conn() as conn:
        challenge = conn.execute(
            "SELECT id, condition_value, points FROM challenges WHERE id=?",
            (req.challenge_id,),
        ).fetchone()
        if not challenge:
            raise HTTPException(404, "挑战任务不存在")

        user_ch = conn.execute(
            "SELECT id, progress, completed FROM user_challenges "
            "WHERE wallet=? AND challenge_id=?",
            (wallet, req.challenge_id),
        ).fetchone()
        if not user_ch:
            raise HTTPException(400, "请先开始挑战任务")

    # 服务端重算（含自动完成判定；scope 以 JWT user_id 收紧重算范围）
    _sync_user_challenges(wallet, user.get("user_id") or None)

    with get_conn() as conn:
        fresh = conn.execute(
            "SELECT progress, completed FROM user_challenges "
            "WHERE wallet=? AND challenge_id=?",
            (wallet, req.challenge_id),
        ).fetchone()

    new_progress = fresh["progress"] if fresh else 0
    completed = bool(fresh and fresh["completed"] == 1)
    return {
        "ok": True,
        "progress": new_progress,
        "completed": completed,
        "points_earned": challenge["points"] if completed else 0,
    }
