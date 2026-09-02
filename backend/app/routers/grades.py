"""学生成绩管理 API（闭环逻辑版）。

成绩体系三段式：
  - 实训成绩（training_score）：由平台数据自动计算（链搭建 / 合约 / 链上验证 / 联盟治理 4 维加权）
  - 教师评分（score）：教师手动录入（实训报告 / 课堂表现 等）
  - 综合成绩（final_score）：系统合成 = 训练成绩 × 0.6 + 教师评分 × 0.4

闭环：学生在平台完成 4 大实训模块 → 系统按权重自动汇总实训成绩 →
      教师录入教师评分 → 系统合成综合成绩 → 形成完整评价。

权限：仅教师（roleId=3）和管理员（roleId=1）可访问；学生（roleId=4）禁止。
身份通过 JWT 验签解析（Authorization: Bearer，见 app/security.py），不再信任 X-* 自报头。

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

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..db import get_conn, now, scope_where
from ..security import ensure_own_wallet, require_role, get_current_user, PRIVILEGED_ROLES
# 实训成绩原始计数统一由 learning.events.aggregate 聚合（单一事实源，只计数不含公式）
from ..learning.events import aggregate as aggregate_training_counts


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


def _require_teacher(user: dict = Depends(require_role(1, 3))) -> Tuple[int, str, str]:
    """校验当前登录身份是否可访问成绩模块（基于 JWT 角色：1 管理员 / 3 教师）；
    返回 (roleId, userId, userName)。"""
    return int(user.get("role_id") or 0), (user.get("user_id") or ""), (user.get("user_name") or "")


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

    # 原始计数统一由 learning.events.aggregate 聚合（单一事实源）：
    # 钱包候选集兼容双轨口径（写路径 0xlearner / 读路径 userId）+ lower(wallet) IN
    # 归一，计数口径与本函数原实现逐字一致；评分公式与封顶逻辑保持不变。
    m = aggregate_training_counts(wallet)

    # === 维度 1：链搭建（IDE 打开 / 工程保存 / 搭链教程完成步数）===
    opens = m["ide_open_builtin"]
    saves = m["ide_save_project"]
    # 教程每完成 1 步 +8 分（共 10 步封顶 80 分）；合计仍以 100 分封顶。
    # 新增项只增不减：存量用户分数只会持平或上升。
    chain_setup_score = min(100.0, opens * 5 + saves * 10 + m["tutorial_done"] * 8)

    # === 维度 2：合约开发（编译成功 + 部署数）===
    compiles_ok = m["contract_compile_ok"]
    contract_dev_score = min(100.0, compiles_ok * 5 + m["deployed_contracts"] * 25)

    # === 维度 3：链上验证（接口调用 + 合约调用 + 链上交易）===
    invokes = m["interface_invoke"]
    chain_verify_score = min(100.0, invokes * 5 + m["contract_calls"] * 4 + m["transactions"] * 3)

    # === 维度 4：联盟治理（角色切换 + 能量发放 + NFT 铸造/交易 + 绿色市场成交 + ERC20 转账 + 报告查看）===
    # 能量发放是联盟角色核心职责：基于业务凭据签发绿色能量，体现真实联盟链治理流程；
    # 绿色市场成交（eco_market_trade）是业务闭环最后一环：绿色资产即链上 NFT，成交即流通。
    role_switches = m["eco_role_switch"]
    report_views = m["report_view"]
    alliance_gov_score = min(
        100.0,
        role_switches * 8 + m["energy_issue"] * 10 + m["nft_mint"] * 6
        + m["nft_trade"] * 5 + m["eco_market_trade"] * 5
        + m["erc20_transfer"] * 2 + report_views * 4,
    )

    detail = {
        "chain_setup": {
            "score": round(chain_setup_score, 1),
            "weight": TRAINING_WEIGHTS["chain_setup"],
            "metrics": {
                "ide_open_builtin": opens,
                "ide_save_project": saves,
                "tutorial_done": m["tutorial_done"],
            },
        },
        "contract_dev": {
            "score": round(contract_dev_score, 1),
            "weight": TRAINING_WEIGHTS["contract_dev"],
            "metrics": {"contract_compile_ok": compiles_ok, "deployed_contracts": m["deployed_contracts"]},
        },
        "chain_verify": {
            "score": round(chain_verify_score, 1),
            "weight": TRAINING_WEIGHTS["chain_verify"],
            "metrics": {
                "interface_invoke": invokes,
                "contract_calls": m["contract_calls"],
                "transactions": m["transactions"],
            },
        },
        "alliance_gov": {
            "score": round(alliance_gov_score, 1),
            "weight": TRAINING_WEIGHTS["alliance_gov"],
            "metrics": {
                "eco_role_switch": role_switches,
                "energy_issue": m["energy_issue"],
                "nft_mint": m["nft_mint"],
                "nft_trade": m["nft_trade"],
                "eco_market_trade": m["eco_market_trade"],
                "erc20_transfer": m["erc20_transfer"],
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
# 学生端：按 wallet 查看自己的成绩（无需教师权限）
# ===========================================================================
@router.get("/my")
def my_grades(
    wallet: str = Query(..., description="学生链上钱包地址"),
    user: dict = Depends(get_current_user),
):
    """学生查看自己的实训成绩（按 wallet 查询，无需教师权限）。

    身份校验：学生仅能查询自己钱包（钱包从 JWT 取，必须与登录身份一致）；
    教师 / 管理员可查任意钱包。返回该 wallet 关联的所有成绩记录 +
    实时计算的实训成绩明细；若该 wallet 尚未有成绩记录，则实时计算并返回预览（不入库）。
    """
    w = wallet.strip()
    if not w:
        raise HTTPException(400, "wallet 必填")
    ensure_own_wallet(user, w)  # 学生仅能查自己钱包，教师/管理员不受限

    # 多租户 scope 浅接线：学生（非特权角色）按本人 user_id 收紧可见范围
    # （命中本人归属行 + 未登记归属旧行，见 db.scope_where）；教师/管理员
    # 传 None 不过滤，保持全局视图，避免特权视角"丢数据"。
    # 注：student_grades 租户列由 db.init_db 在线迁移补齐（旧行 DEFAULT ''）。
    scope_uid = (user.get("user_id") or "").strip() or None
    if int(user.get("role_id") or 0) in PRIVILEGED_ROLES:
        scope_uid = None
    sc, sp = scope_where("student_grades", user_id=scope_uid)

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM student_grades WHERE wallet=?"
            + (" AND " + sc if sc else "")
            + " ORDER BY course ASC",
            (w, *sp),
        ).fetchall()

    items = []
    for r in rows:
        item = dict(r)
        try:
            item["training_detail"] = json.loads(item.get("training_detail") or "{}")
        except (TypeError, json.JSONDecodeError):
            item["training_detail"] = {}
        items.append(item)

    # 实时计算当前 wallet 的实训成绩（用于对比 / 预览）
    training_now, detail_now = _compute_training_score(w)

    return {
        "wallet": w,
        "grades": items,
        "total": len(items),
        "training_now": training_now,
        "detail_now": detail_now,
    }


# ===========================================================================
# 报告→成绩闭环：按 wallet 自动创建/更新成绩草稿
# ===========================================================================
@router.post("/auto-draft")
def auto_draft_grade(
    wallet: str = Query(..., description="学生链上钱包地址"),
    student_id: str = Query("", description="学号（可选，为空则用 wallet 前 10 位）"),
    student_name: str = Query("", description="学生姓名（可选）"),
    course: str = Query("区块链实训", description="课程名称"),
    user: dict = Depends(get_current_user),
):
    """报告生成时自动为学生创建/更新成绩草稿（打通 report→grades）。

    闭环逻辑：学生完成实训 → 查看/下载报告 → 系统自动按 wallet 计算实训成绩
    → 写入 student_grades 作为草稿（teacher_id='system', score=0 待教师录入）。
    身份校验：学生仅能为自己钱包生成草稿（钱包必须与 JWT 身份一致）；教师/管理员不受限。
    """
    w = wallet.strip()
    if not w:
        raise HTTPException(400, "wallet 必填")
    ensure_own_wallet(user, w)  # 学生仅能写本人钱包，教师/管理员不受限

    sid = student_id.strip() or f"W{w[:10]}"
    sname = student_name.strip() or f"学生_{w[:6]}"
    ts = now()

    training_score, detail = _compute_training_score(w)
    detail_json = json.dumps(detail, ensure_ascii=False)
    # 草稿阶段 teacher_score=0，等教师录入后更新
    final_score = _compute_final(training_score, 0)

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM student_grades WHERE student_id=? AND course=?",
            (sid, course),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE student_grades
                   SET wallet=?, training_score=?, final_score=?,
                       training_detail=?, updated_at=?
                   WHERE id=?""",
                (w, training_score, final_score, detail_json, ts, existing["id"]),
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
                   VALUES (?, ?, ?, 0, ?, ?, ?, ?, 'system', '系统自动', '', '', '实训报告自动生成草稿', ?, ?)""",
                (sid, sname, course, w, training_score, final_score, detail_json, ts, ts),
            )
            grade_id = cur.lastrowid
            action = "created"

    return {
        "id": grade_id,
        "action": action,
        "wallet": w,
        "training_score": training_score,
        "final_score": final_score,
        "detail": detail,
    }


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
