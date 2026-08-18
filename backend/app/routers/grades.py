"""学生成绩管理 API（闭环逻辑版）。

成绩体系三段式：
  - 实训成绩（training_score）：由平台数据自动计算（链搭建 / 合约 / 链上验证 / 联盟治理 4 维加权）
  - 教师评分（score）：教师手动录入（实训报告 / 课堂表现 等）
  - 综合成绩（final_score）：系统合成 = 训练成绩 × 0.6 + 教师评分 × 0.4

闭环：学生在平台完成 4 大实训模块 → 系统按权重自动汇总实训成绩 →
      教师录入教师评分 → 系统合成综合成绩 → 形成完整评价。

权限：仅教师（roleId=3）和管理员（roleId=1）可访问；学生（roleId=4）禁止。
身份通过 HTTP Header `X-User-Id` / `X-Role-Id` / `X-User-Name` 传递。

接口：
  GET    /api/grades/list                 成绩列表（含实训/教师/综合 3 项）
  GET    /api/grades/stats                按课程聚合统计
  POST   /api/grades/upsert               新增 / 更新（按 学号+课程 唯一；含 wallet 自动算实训成绩）
  DELETE /api/grades/{id}                 删除一条
  POST   /api/grades/compute-training     按 wallet 实时计算实训成绩明细（不入库，仅返回）
  POST   /api/grades/refresh-training     批量重算所有记录的实训成绩（教师一键刷新）
"""
from __future__ import annotations

import json
from typing import Optional, Tuple
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from ..db import get_conn, now


def _decode_name(raw: str) -> str:
    """解码 X-User-Name：前端用 encodeURIComponent 编码中文，后端需 unquote 还原。"""
    if not raw:
        return ""
    try:
        return unquote(raw)
    except Exception:
        return raw

router = APIRouter(prefix="/api/grades", tags=["grades"])

# 允许访问成绩模块的角色：1=管理员，3=教师
ALLOWED_ROLES = {1, 3}

# 综合成绩权重：实训成绩 60% + 教师评分 40%
W_TRAINING = 0.6
W_MANUAL = 0.4

# 实训成绩 4 维权重（合计 1.0）
TRAINING_WEIGHTS = {
    "chain_setup":   0.20,  # 链搭建（IDE 使用 / 工程保存）
    "contract_dev":   0.30,  # 合约开发（编译 / 部署）
    "chain_verify":   0.25,  # 链上验证（接口调用 / 交易 / 合约调用）
    "alliance_gov":   0.25,  # 联盟治理（角色切换 / NFT 铸造 / 转账 / 治理参与）
}


def _require_teacher(
    x_role_id: Optional[str] = Header(default=None, alias="X-Role-Id"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
) -> Tuple[int, str, str]:
    """校验当前登录身份是否可访问成绩模块；返回 (roleId, userId, userName)。"""
    try:
        rid = int(x_role_id) if x_role_id else 0
    except (TypeError, ValueError):
        rid = 0
    if rid not in ALLOWED_ROLES:
        raise HTTPException(status_code=403, detail="无权限访问学生成绩模块（仅教师 / 管理员）")
    return rid, (x_user_id or ""), _decode_name(x_user_name or "")


# ===========================================================================
# 实训成绩计算引擎（核心闭环逻辑）
# ===========================================================================
def _compute_training_score(wallet: str) -> Tuple[float, dict]:
    """根据 wallet 在平台上的真实活动数据，计算 4 维实训成绩。

    返回 (training_score, detail)：
      detail = {
        "chain_setup":   {"score": xx, "weight": 0.20, "metrics": {...}},
        "contract_dev":  {...},
        "chain_verify":  {...},
        "alliance_gov":  {...},
      }
    """
    if not wallet:
        return 0.0, {k: {"score": 0, "weight": v, "metrics": {}} for k, v in TRAINING_WEIGHTS.items()}

    with get_conn() as conn:
        # 1) 学习事件按类型计数
        event_counts = {
            r["event_type"]: r["cnt"]
            for r in conn.execute(
                "SELECT event_type, COUNT(*) AS cnt FROM learning_events WHERE wallet=? GROUP BY event_type",
                (wallet,),
            ).fetchall()
        }
        # 2) 已部署合约数（该 wallet 部署的）
        deploy_count = conn.execute(
            "SELECT COUNT(*) AS c FROM deployed_contracts WHERE deployer=?",
            (wallet,),
        ).fetchone()["c"]
        # 3) 合约调用次数（该 wallet 调用的）
        call_count = conn.execute(
            "SELECT COUNT(*) AS c FROM contract_calls WHERE caller=?",
            (wallet,),
        ).fetchone()["c"]
        # 4) 链上交易笔数（该 wallet 发起 / 接收）
        tx_count = conn.execute(
            "SELECT COUNT(*) AS c FROM transactions WHERE from_addr=? OR to_addr=?",
            (wallet, wallet),
        ).fetchone()["c"]
        # 5) NFT 铸造数（该 wallet 作为作者）
        nft_mint_count = conn.execute(
            "SELECT COUNT(*) AS c FROM nfts WHERE author=?",
            (wallet,),
        ).fetchone()["c"]
        # 6) NFT 交易数（该 wallet 买 / 卖）
        nft_trade_count = conn.execute(
            "SELECT COUNT(*) AS c FROM nft_trades WHERE from_addr=? OR to_addr=?",
            (wallet, wallet),
        ).fetchone()["c"]
        # 7) ERC20 转账数
        transfer_count = conn.execute(
            "SELECT COUNT(*) AS c FROM wallet_transfers WHERE from_addr=? OR to_addr=?",
            (wallet, wallet),
        ).fetchone()["c"]

    # === 维度 1：链搭建（IDE 打开 / 工程保存）===
    opens = event_counts.get("ide_open_builtin", 0)
    saves = event_counts.get("ide_save_project", 0)
    chain_setup_score = min(100.0, opens * 5 + saves * 10)

    # === 维度 2：合约开发（编译成功 + 部署数）===
    compiles_ok = event_counts.get("contract_compile_ok", 0)
    contract_dev_score = min(100.0, compiles_ok * 5 + deploy_count * 25)

    # === 维度 3：链上验证（接口调用 + 合约调用 + 链上交易）===
    invokes = event_counts.get("interface_invoke", 0)
    chain_verify_score = min(100.0, invokes * 5 + call_count * 4 + tx_count * 3)

    # === 维度 4：联盟治理（角色切换 + NFT 铸造/交易 + ERC20 转账 + 报告查看）===
    role_switches = event_counts.get("eco_role_switch", 0)
    report_views = event_counts.get("report_view", 0)
    alliance_gov_score = min(
        100.0,
        role_switches * 8 + nft_mint_count * 6 + nft_trade_count * 5 + transfer_count * 2 + report_views * 4,
    )

    detail = {
        "chain_setup": {
            "score": round(chain_setup_score, 1),
            "weight": TRAINING_WEIGHTS["chain_setup"],
            "metrics": {"ide_open_builtin": opens, "ide_save_project": saves},
        },
        "contract_dev": {
            "score": round(contract_dev_score, 1),
            "weight": TRAINING_WEIGHTS["contract_dev"],
            "metrics": {"contract_compile_ok": compiles_ok, "deployed_contracts": deploy_count},
        },
        "chain_verify": {
            "score": round(chain_verify_score, 1),
            "weight": TRAINING_WEIGHTS["chain_verify"],
            "metrics": {
                "interface_invoke": invokes,
                "contract_calls": call_count,
                "transactions": tx_count,
            },
        },
        "alliance_gov": {
            "score": round(alliance_gov_score, 1),
            "weight": TRAINING_WEIGHTS["alliance_gov"],
            "metrics": {
                "eco_role_switch": role_switches,
                "nft_mint": nft_mint_count,
                "nft_trade": nft_trade_count,
                "erc20_transfer": transfer_count,
                "report_view": report_views,
            },
        },
    }
    training_score = round(sum(d["score"] * d["weight"] for d in detail.values()), 1)
    return training_score, detail


def _compute_final(training: float, manual: float) -> float:
    """综合成绩 = 训练成绩 × 0.6 + 教师评分 × 0.4"""
    return round(training * W_TRAINING + manual * W_MANUAL, 1)


# ===========================================================================
# 请求 / 响应模型
# ===========================================================================
class GradeUpsertReq(BaseModel):
    student_id: str = Field(..., description="学号")
    student_name: str = Field(..., description="学生姓名")
    course: str = Field(..., description="课程名称")
    score: float = Field(..., ge=0, le=100, description="教师评分 0-100（实训报告 / 课堂表现）")
    wallet: str = Field("", description="学生链上钱包地址（提供则自动算实训成绩）")
    class_id: str = Field("", description="班级 ID（可选）")
    school_id: str = Field("", description="学校 ID（可选）")
    remark: str = Field("", description="备注（可选）")


class ComputeTrainingReq(BaseModel):
    wallet: str = Field(..., description="学生链上钱包地址")
    manual_score: Optional[float] = Field(None, ge=0, le=100, description="如提供，一并返回综合成绩")


# ===========================================================================
# 查询接口
# ===========================================================================
@router.get("/list")
def list_grades(
    student_id: Optional[str] = Query(None, description="按学号精确筛选"),
    student_name: Optional[str] = Query(None, description="按姓名模糊筛选"),
    course: Optional[str] = Query(None, description="按课程模糊筛选"),
    class_id: Optional[str] = Query(None, description="按班级精确筛选（不传则教师自动按其班级过滤）"),
    teacher = Depends(_require_teacher),
):
    """成绩列表查询（教师 / 管理员可见）。

    权限规则：
      - 教师（roleId=3）：默认只看自己班级的学生成绩；不传 class_id 时自动按
        user_info 表中教师的 class_id 过滤，避免越权看到其他班级
      - 管理员（roleId=1）：可查看全部班级成绩

    每行包含：实训成绩(training_score) + 教师评分(score) + 综合成绩(final_score) +
              实训明细(training_detail, JSON 字符串)
    """
    rid, uid, _uname = teacher
    sql = "SELECT * FROM student_grades WHERE 1=1"
    params: list = []
    # 教师角色自动按班级过滤：若前端未显式传 class_id，则查 user_info 取教师所属班级
    if rid == 3 and not class_id:
        teacher_class = ""
        if uid:
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT class_id FROM user_info WHERE user_id=?", (uid,)
                ).fetchone()
                if row:
                    teacher_class = row["class_id"] or ""
        if teacher_class:
            class_id = teacher_class
    if student_id:
        sql += " AND student_id = ?"; params.append(student_id)
    if student_name:
        sql += " AND student_name LIKE ?"; params.append(f"%{student_name}%")
    if course:
        sql += " AND course LIKE ?"; params.append(f"%{course}%")
    if class_id:
        sql += " AND class_id = ?"; params.append(class_id)
    sql += " ORDER BY course ASC, student_id ASC"
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    # 解析 training_detail JSON 便于前端使用
    for r in rows:
        try:
            r["training_detail"] = json.loads(r.get("training_detail") or "{}")
        except (TypeError, json.JSONDecodeError):
            r["training_detail"] = {}
        # 兜底解码旧数据中 URL 编码的 teacher_name（历史录入未解码导致乱码）
        r["teacher_name"] = _decode_name(r.get("teacher_name") or "")
    return {"total": len(rows), "items": rows}


@router.get("/stats")
def grades_stats(teacher = Depends(_require_teacher)):
    """按课程聚合：实训 / 教师 / 综合 三项的平均分 + 人数。

    教师默认只统计自己班级的成绩，管理员统计全部。
    """
    rid, uid, _uname = teacher
    teacher_class = ""
    if rid == 3 and uid:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT class_id FROM user_info WHERE user_id=?", (uid,)
            ).fetchone()
            if row:
                teacher_class = row["class_id"] or ""
    if teacher_class:
        sql = """
            SELECT
                course,
                COUNT(*)                   AS cnt,
                ROUND(AVG(training_score), 2)  AS avg_training,
                ROUND(AVG(score), 2)           AS avg_manual,
                ROUND(AVG(final_score), 2)     AS avg_final
            FROM student_grades
            WHERE class_id=?
            GROUP BY course
            ORDER BY course ASC
        """
        params: list = [teacher_class]
    else:
        sql = """
            SELECT
                course,
                COUNT(*)                   AS cnt,
                ROUND(AVG(training_score), 2)  AS avg_training,
                ROUND(AVG(score), 2)           AS avg_manual,
                ROUND(AVG(final_score), 2)     AS avg_final
            FROM student_grades
            GROUP BY course
            ORDER BY course ASC
        """
        params = []
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    return {"items": rows}


# ===========================================================================
# 实训成绩计算接口（实时算，不入库）
# ===========================================================================
@router.post("/compute-training")
def compute_training(req: ComputeTrainingReq, _=Depends(_require_teacher)):
    """按 wallet 实时计算实训成绩明细（不入库），便于教师在新增/编辑时预览。"""
    training, detail = _compute_training_score(req.wallet.strip())
    resp = {
        "wallet": req.wallet.strip(),
        "training_score": training,
        "detail": detail,
        "weights": {"training": W_TRAINING, "manual": W_MANUAL},
    }
    if req.manual_score is not None:
        resp["manual_score"] = req.manual_score
        resp["final_score"] = _compute_final(training, req.manual_score)
    return resp


# ===========================================================================
# 新增 / 更新（按 学号+课程 唯一）
# ===========================================================================
@router.post("/upsert")
def upsert_grade(
    req: GradeUpsertReq,
    auth_ctx: Tuple[int, str, str] = Depends(_require_teacher),
):
    rid, uid, uname = auth_ctx
    ts = now()
    # 自动计算实训成绩 + 综合成绩（若提供了 wallet）
    training_score, detail = _compute_training_score(req.wallet.strip())
    final_score = _compute_final(training_score, req.score)
    detail_json = json.dumps(detail, ensure_ascii=False)
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM student_grades WHERE student_id=? AND course=?",
            (req.student_id, req.course),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE student_grades
                   SET student_name=?, score=?, wallet=?, training_score=?, final_score=?,
                       training_detail=?, class_id=?, school_id=?, remark=?,
                       teacher_id=?, teacher_name=?, updated_at=?
                   WHERE id=?""",
                (req.student_name, req.score, req.wallet.strip(), training_score, final_score,
                 detail_json, req.class_id, req.school_id, req.remark,
                 uid, uname, ts, existing["id"]),
            )
            grade_id = existing["id"]
            action = "updated"
        else:
            cur = conn.execute(
                """INSERT INTO student_grades
                   (student_id, student_name, course, score, wallet,
                    training_score, final_score, training_detail,
                    teacher_id, teacher_name, class_id, school_id, remark,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (req.student_id, req.student_name, req.course, req.score, req.wallet.strip(),
                 training_score, final_score, detail_json,
                 uid, uname, req.class_id, req.school_id, req.remark, ts, ts),
            )
            grade_id = cur.lastrowid
            action = "created"
    return {
        "id": grade_id, "action": action,
        "training_score": training_score, "final_score": final_score, "detail": detail,
    }


# ===========================================================================
# 批量刷新所有成绩的实训成绩（教师一键刷新闭环数据）
# ===========================================================================
@router.post("/refresh-training")
def refresh_all_training(_=Depends(_require_teacher)):
    """遍历所有已绑定 wallet 的成绩记录，按最新平台数据重算实训成绩 + 综合成绩。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, wallet, score FROM student_grades WHERE wallet != ''"
        ).fetchall()
        updated = 0
        ts = now()
        for r in rows:
            wid = r["wallet"]
            if not wid:
                continue
            training, detail = _compute_training_score(wid)
            final = _compute_final(training, r["score"] or 0)
            conn.execute(
                """UPDATE student_grades
                   SET training_score=?, final_score=?, training_detail=?, updated_at=?
                   WHERE id=?""",
                (training, final, json.dumps(detail, ensure_ascii=False), ts, r["id"]),
            )
            updated += 1
    return {"refreshed": updated, "total_with_wallet": len(rows)}


# ===========================================================================
# 删除
# ===========================================================================
@router.delete("/{grade_id}")
def delete_grade(grade_id: int, _=Depends(_require_teacher)):
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM student_grades WHERE id=?", (grade_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="成绩记录不存在或已被删除")
    return {"deleted": grade_id}
