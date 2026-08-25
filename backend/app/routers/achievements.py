"""成就系统 API（成就定义、用户进度、挑战任务、排行榜）。"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

from ..db import get_conn, now

router = APIRouter(prefix="/api/achievements", tags=["achievements"])


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


def _compute_user_stats(wallet: str) -> dict:
    """从多个表统计用户行为数据。"""
    stats = {
        "contract_compile_ok": 0,
        "deployed_contracts": 0,
        "transactions": 0,
        "eco_energy_records": 0,
        "nft_tokens": 0,
        "tutorial_progress": 0,
        "gas_saved": 0,
        "security_audits": 0,
    }
    
    with get_conn() as conn:
        # 编译成功次数
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM learning_events WHERE wallet=? AND event_type='contract_compile_ok'",
            (wallet,),
        ).fetchone()
        stats["contract_compile_ok"] = row["cnt"] if row else 0
        
        # 部署合约数
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM deployed_contracts WHERE deployer=?",
            (wallet,),
        ).fetchone()
        stats["deployed_contracts"] = row["cnt"] if row else 0
        
        # 交易数
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM transactions WHERE from_addr=?",
            (wallet,),
        ).fetchone()
        stats["transactions"] = row["cnt"] if row else 0
        
        # 生态活动记录数
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM eco_energy_records WHERE wallet=?",
                (wallet,),
            ).fetchone()
            stats["eco_energy_records"] = row["cnt"] if row else 0
        except Exception:
            # 表可能不存在
            pass
        
        # NFT 数量
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM nfts WHERE owner=?",
            (wallet,),
        ).fetchone()
        stats["nft_tokens"] = row["cnt"] if row else 0
        
        # 教程进度（假设 chain_tutorial_progress 表存在，存储 progress 字段 0-100）
        try:
            row = conn.execute(
                "SELECT progress FROM chain_tutorial_progress WHERE wallet=? ORDER BY id DESC LIMIT 1",
                (wallet,),
            ).fetchone()
            stats["tutorial_progress"] = row["progress"] if row else 0
        except Exception:
            # 表可能不存在
            pass
        
        # Gas 节省（从 learning_events 的 extra 字段统计，或从其他表）
        # 这里简化处理，实际可能需要更复杂的逻辑
        try:
            row = conn.execute(
                "SELECT SUM(CAST(JSON_EXTRACT(extra, '$.gas_saved') AS INTEGER)) as total FROM learning_events WHERE wallet=? AND extra LIKE '%gas_saved%'",
                (wallet,),
            ).fetchone()
            stats["gas_saved"] = row["total"] if row and row["total"] else 0
        except Exception:
            pass
        
        # 安全审计次数（假设从 learning_events 或其他表统计）
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM learning_events WHERE wallet=? AND event_type='security_audit'",
                (wallet,),
            ).fetchone()
            stats["security_audits"] = row["cnt"] if row else 0
        except Exception:
            pass
    
    return stats


def _check_and_grant_achievement(wallet: str, achievement: dict, stats: dict) -> bool:
    """检查用户是否满足成就条件，满足则发放。返回是否新获得。"""
    condition_type = achievement["condition_type"]
    condition_value = achievement["condition_value"]
    current_value = stats.get(condition_type, 0)
    
    if current_value < condition_value:
        return False
    
    # 检查是否已获得
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM user_achievements WHERE wallet=? AND achievement_id=?",
            (wallet, achievement["id"]),
        ).fetchone()
        
        if existing:
            # 已存在，更新进度
            conn.execute(
                "UPDATE user_achievements SET progress=?, completed=1 WHERE wallet=? AND achievement_id=?",
                (current_value, wallet, achievement["id"]),
            )
            return False
        else:
            # 新获得
            conn.execute(
                """INSERT INTO user_achievements(wallet, achievement_id, earned_at, progress, completed)
                   VALUES(?,?,?,?,1)""",
                (wallet, achievement["id"], now(), current_value),
            )
            return True


# ==================== API 端点 ====================

@router.get("")
def list_achievements():
    """列出所有成就。"""
    _ensure_seed_data()
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM achievements ORDER BY category, points").fetchall()
    return {"items": [dict(r) for r in rows]}


@router.get("/my")
def my_achievements(x_wallet: str = Header(..., alias="X-Wallet")):
    """当前用户成就进度。"""
    _ensure_seed_data()
    wallet = x_wallet
    stats = _compute_user_stats(wallet)
    
    with get_conn() as conn:
        # 所有成就
        all_achievements = conn.execute("SELECT * FROM achievements").fetchall()
        # 用户已获得的成就
        user_ach = conn.execute(
            "SELECT achievement_id, progress, completed, earned_at FROM user_achievements WHERE wallet=?",
            (wallet,),
        ).fetchall()
    
    user_ach_map = {row["achievement_id"]: dict(row) for row in user_ach}
    
    result = []
    for ach in all_achievements:
        ach_dict = dict(ach)
        user_progress = user_ach_map.get(ach["id"])
        if user_progress:
            ach_dict["progress"] = user_progress["progress"]
            ach_dict["completed"] = user_progress["completed"]
            ach_dict["earned_at"] = user_progress["earned_at"]
        else:
            ach_dict["progress"] = stats.get(ach["condition_type"], 0)
            ach_dict["completed"] = 0
            ach_dict["earned_at"] = None
        result.append(ach_dict)
    
    return {"items": result, "stats": stats}


@router.post("/check")
def check_achievements(x_wallet: str = Header(..., alias="X-Wallet")):
    """检查并自动发放成就。"""
    _ensure_seed_data()
    wallet = x_wallet
    stats = _compute_user_stats(wallet)
    
    with get_conn() as conn:
        all_achievements = conn.execute("SELECT * FROM achievements").fetchall()
    
    newly_earned = []
    for ach in all_achievements:
        if _check_and_grant_achievement(wallet, dict(ach), stats):
            newly_earned.append(ach["id"])
    
    return {"newly_earned": newly_earned, "stats": stats}


@router.get("/stats")
def achievement_stats():
    """成就排行榜（按获得成就数量排序）。"""
    _ensure_seed_data()
    with get_conn() as conn:
        # 统计每个用户获得的成就数量和总积分
        rows = conn.execute(
            """SELECT wallet, COUNT(*) as achievement_count, 
                      SUM(CASE WHEN completed=1 THEN points ELSE 0 END) as total_points
               FROM user_achievements ua
               JOIN achievements a ON ua.achievement_id = a.id
               WHERE ua.completed = 1
               GROUP BY wallet
               ORDER BY total_points DESC, achievement_count DESC
               LIMIT 50"""
        ).fetchall()
    
    return {"leaderboard": [dict(r) for r in rows]}


@router.get("/challenges")
def list_challenges():
    """列出所有挑战任务。"""
    _ensure_seed_data()
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM challenges ORDER BY difficulty, points").fetchall()
    return {"items": [dict(r) for r in rows]}


@router.get("/challenges/my")
def my_challenges(x_wallet: str = Header(..., alias="X-Wallet")):
    """当前用户挑战进度。"""
    _ensure_seed_data()
    wallet = x_wallet
    stats = _compute_user_stats(wallet)
    
    with get_conn() as conn:
        all_challenges = conn.execute("SELECT * FROM challenges").fetchall()
        user_ch = conn.execute(
            "SELECT challenge_id, progress, completed, started_at, completed_at FROM user_challenges WHERE wallet=?",
            (wallet,),
        ).fetchall()
    
    user_ch_map = {row["challenge_id"]: dict(row) for row in user_ch}
    
    result = []
    for ch in all_challenges:
        ch_dict = dict(ch)
        user_progress = user_ch_map.get(ch["id"])
        if user_progress:
            ch_dict["progress"] = user_progress["progress"]
            ch_dict["completed"] = user_progress["completed"]
            ch_dict["started_at"] = user_progress["started_at"]
            ch_dict["completed_at"] = user_progress["completed_at"]
        else:
            ch_dict["progress"] = 0
            ch_dict["completed"] = 0
            ch_dict["started_at"] = None
            ch_dict["completed_at"] = None
        result.append(ch_dict)
    
    return {"items": result, "stats": stats}


class StartChallengeReq(BaseModel):
    challenge_id: str


@router.post("/challenges/start")
def start_challenge(req: StartChallengeReq, x_wallet: str = Header(..., alias="X-Wallet")):
    """开始挑战任务。"""
    _ensure_seed_data()
    wallet = x_wallet
    
    with get_conn() as conn:
        # 检查挑战是否存在
        challenge = conn.execute(
            "SELECT id FROM challenges WHERE id=?", (req.challenge_id,)
        ).fetchone()
        if not challenge:
            raise HTTPException(404, "挑战任务不存在")
        
        # 检查是否已开始
        existing = conn.execute(
            "SELECT id FROM user_challenges WHERE wallet=? AND challenge_id=?",
            (wallet, req.challenge_id),
        ).fetchone()
        
        if existing:
            raise HTTPException(400, "挑战任务已开始")
        
        # 创建用户挑战记录
        conn.execute(
            """INSERT INTO user_challenges(wallet, challenge_id, started_at, progress, completed)
               VALUES(?,?,?,0,0)""",
            (wallet, req.challenge_id, now()),
        )
    
    return {"ok": True, "message": "挑战已开始"}


class UpdateProgressReq(BaseModel):
    challenge_id: str
    progress: int


@router.post("/challenges/progress")
def update_challenge_progress(
    req: UpdateProgressReq, x_wallet: str = Header(..., alias="X-Wallet")
):
    """更新挑战进度。"""
    _ensure_seed_data()
    wallet = x_wallet
    
    with get_conn() as conn:
        # 检查挑战是否存在
        challenge = conn.execute(
            "SELECT id, condition_value, points FROM challenges WHERE id=?",
            (req.challenge_id,),
        ).fetchone()
        if not challenge:
            raise HTTPException(404, "挑战任务不存在")
        
        # 检查用户是否已开始该挑战
        user_ch = conn.execute(
            "SELECT id, progress, completed FROM user_challenges WHERE wallet=? AND challenge_id=?",
            (wallet, req.challenge_id),
        ).fetchone()
        
        if not user_ch:
            raise HTTPException(400, "请先开始挑战任务")
        
        if user_ch["completed"] == 1:
            raise HTTPException(400, "挑战已完成")
        
        # 更新进度
        new_progress = req.progress
        completed = 1 if new_progress >= challenge["condition_value"] else 0
        completed_at = now() if completed else None
        
        conn.execute(
            """UPDATE user_challenges 
               SET progress=?, completed=?, completed_at=?
               WHERE wallet=? AND challenge_id=?""",
            (new_progress, completed, completed_at, wallet, req.challenge_id),
        )
    
    return {
        "ok": True,
        "progress": new_progress,
        "completed": completed == 1,
        "points_earned": challenge["points"] if completed else 0,
    }
