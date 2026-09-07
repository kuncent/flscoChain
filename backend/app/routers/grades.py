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
  GET    /api/grades/stats                按课程聚合统计（按 主体+课程 去重，P0-2）
  POST   /api/grades/upsert               新增 / 更新（按 学号+课程 唯一；含 wallet 自动算实训成绩）
  DELETE /api/grades/{id}                 删除一条
  POST   /api/grades/compute-training     按 wallet 实时计算实训成绩明细（不入库，仅返回）
  POST   /api/grades/refresh-training     批量重算所有记录的实训成绩（教师一键刷新）
  POST   /api/grades/draft/refresh        刷新系统草稿（写 grade_draft，不进成绩册）
  GET    /api/grades/drafts               教师查看待同步草稿
  POST   /api/grades/draft/apply          教师显式把草稿同步为正式成绩
"""
from __future__ import annotations

import json
from typing import Any, Optional, Tuple
from urllib.parse import unquote

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..db import get_conn, now, scope_where
from ..roster import norm_class, resolve_class_scope
from ..wallet_id import is_address
from ..security import (
    BUILTIN_WALLETS,
    PRIVILEGED_ROLES,
    ensure_own_wallet,
    get_current_user,
    identifying_wallets,
    is_placeholder_student_id,
    lower_wallet_in,
    principal_of,
    require_role,
    resolve_wallet_candidates,
)
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

# 系统自动草稿默认课程名（与历史写入口径一致）
TRAINING_COURSE = "区块链实训"

# 系统生成行的 teacher_id 取值：'system'（报告/草稿链路）与 ''（教程满步建行链路）。
# 除此之外，一行就是教师亲手录入的正式成绩——系统一律不得改写（P1-25）。
SYSTEM_TEACHER_IDS = ("system", "")


def _is_teacher_owned(teacher_id: Any) -> bool:
    """一行成绩是否属于教师亲手录入（系统不得覆写，P1-25 写保护判定）。"""
    return str(teacher_id if teacher_id is not None else "").strip() not in SYSTEM_TEACHER_IDS


def _is_synthetic_sid(sid: str, wallet: str = "") -> bool:
    """该学号是不是系统合成的占位值（'W' + 钱包前缀，见 _refresh_draft）。

    占位学号只携带钱包信息、不携带人的信息，匹配 / 覆盖时都得降级处理。
    判定规则收口到 security.is_placeholder_student_id —— 与花名册排名、一次性
    归并脚本共用一条口径，不再各写一份截断规则（旧实现只认 10 位，会漏
    `W0xlearner` / `Wstu:0ae778` 这类别名截断）。
    """
    return is_placeholder_student_id(sid, wallet)


def _pick_wallet(cur: str, new: str) -> str:
    """成绩行的 wallet 只朝「更能唯一指人」的方向收敛。

    草稿带的是共享演示钱包（0xlearner 等）时，绝不覆盖行上已有的真实地址。
    """
    if not (new or "").strip():
        return cur or ""
    if new.strip().lower() in BUILTIN_WALLETS and (cur or "").strip():
        return cur
    # 「我的成绩」前端把登录 user_id 当 wallet 传（一人一钱包以账号为准），于是草稿
    # 里带的可能是 UUID / stu: 别名。拿它覆盖成绩册行上已有的真实地址，会让「钱包」
    # 列变成无法与区块链浏览器对账的账号 ID（教师按地址搜不到、导出后核不上）。
    # 因此：行上已是真实地址时，只接受同样为真实地址的新值。
    if is_address(cur or "") and not is_address(new):
        return (cur or "").strip()
    return new


def _find_student_grade_row(
    conn, *, wallet: str, draft_user_id: str, student_id: str, course: str
):
    """在成绩册里定位「该生该课」的目标行（P0-2 + P1-25 共用口径）。

    不能只按 student_id 等值匹配：草稿在 user_info 缺失时学号会退化成合成值
    （'W' + 钱包前 10 位），而教师行里存的是真实学号，两者不相等 → 同步时会
    另起一行，把 P0-2 的「一人多行」重新造一遍。因此匹配口径为：
      - 钱包：identifying_wallets（候选集去掉未认领的共享演示钱包）；
      - 学号：草稿学号 + 草稿 user_id；但当钱包口径已能指人时，**不拿合成
        占位学号去匹配**（所有 0xlearner 用户的占位学号都长得一样）。
    排序：教师正式行优先，否则教师分会被留在旧行、另起一行系统分。
    """
    wkeys = identifying_wallets(conn, wallet, draft_user_id)
    synthetic_sid = f"W{(wallet or '')[:10]}"
    skeys = [
        s for s in (str(student_id or ""), str(draft_user_id or ""))
        if s and not (wkeys and s == synthetic_sid)
    ]
    conds: list[str] = []
    params: list = []
    if wkeys:
        h, lc = lower_wallet_in(wkeys)
        conds.append(f"lower(COALESCE(wallet, '')) IN ({h})")
        params += lc
    if skeys:
        conds.append("student_id IN (" + ",".join("?" * len(skeys)) + ")")
        params += skeys
    if not conds:
        return None
    params.append(course)
    return conn.execute(
        "SELECT id, teacher_id, score, remark, class_id, school_id, student_id, wallet, "
        "updated_at FROM student_grades WHERE (" + " OR ".join(conds) + ") AND course=? "
        "ORDER BY (COALESCE(teacher_id,'') IN ('system','')) ASC, updated_at DESC LIMIT 1",
        params,
    ).fetchone()


def _require_teacher(user: dict = Depends(require_role(1, 3))) -> dict:
    """校验当前登录身份是否可访问成绩模块（基于 JWT 角色：1 管理员 / 3 教师）。

    P0-1：直接返回 JWT 身份上下文（而不是 (rid, uid, uname) 三元组），班级
    解析链 resolve_class_scope 需要载荷里的 class_id 快照作为备胎口径。
    """
    return user


def _teacher_class_scope(conn, user: dict) -> dict:
    """教师看成绩册的班级范围（P0-1）：返回 {class_id, class_source, class_unbound, hint}。

    管理员不限制（class_source='all'）；教师未解析出班级时 **不自作主张看全部**，
    而是回退到「只看自己录入的行」（避免越权 + 避免静默空列表）。
    """
    rid = int(user.get("role_id") or 0)
    if rid == 1:
        return {"class_id": "", "class_source": "all",
                "class_unbound": False, "hint": ""}  # 管理员：不限班级
    scope = resolve_class_scope(conn, user)
    return {
        "class_id": scope["class_id"],
        "class_source": scope["class_source"],
        "class_unbound": bool(scope["class_unbound"]),
        "hint": scope["hint"],
    }


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
      - 教师（roleId=3）：默认只看自己班级的学生成绩；班级经 P0-1 解析链
        （显式绑定 → user_info → JWT 快照 → 成绩册派生）得出；全部落空时
        不越权看全部，改为只返回自己录入过的行，并标 class_unbound + hint
      - 管理员（roleId=1）：可查看全部班级成绩

    每行包含：实训成绩(training_score) + 教师评分(score) + 综合成绩(final_score) +
              实训明细(training_detail, JSON 字符串)
    另为每行标 `row_kind`（P1-25）：teacher=教师正式行 / system=系统行（可被同步覆写）。
    """
    user = teacher
    rid = int(user.get("role_id") or 0)
    uid = user.get("user_id") or ""
    sql = "SELECT * FROM student_grades WHERE 1=1"
    params: list = []
    class_unbound = False
    class_source = ""
    hint = ""
    # 教师角色自动按班级过滤：若前端未显式传 class_id，走 P0-1 解析链取教师所属班级
    if class_id:
        class_source = "query"
    else:
        with get_conn() as conn:
            scope = _teacher_class_scope(conn, user)
        class_source = scope["class_source"]
        class_unbound = scope["class_unbound"]
        hint = scope["hint"]
        if rid == 3:
            if scope["class_id"]:
                class_id = scope["class_id"]
            elif class_unbound:
                # 未绑定班级：只看自己录入的行（不越权、也不静默返回空）
                sql += " AND COALESCE(teacher_id, '') = ?"; params.append(uid)
    if student_id:
        sql += " AND student_id = ?"; params.append(student_id)
    if student_name:
        sql += " AND student_name LIKE ?"; params.append(f"%{student_name}%")
    if course:
        sql += " AND course LIKE ?"; params.append(f"%{course}%")
    if class_id:
        sql += " AND class_id = ?"; params.append(norm_class(class_id))
    # 同一学生多口径行（P0-2）：教师正式行排在前，系统行紧随，便于界面分组识别
    sql += " ORDER BY course ASC, student_id ASC, " \
           "(COALESCE(teacher_id,'') IN ('system','')) ASC, updated_at DESC"
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
        # P1-25：行归属标记（前端据此区分“系统草稿”与“教师正式成绩”）
        r["row_kind"] = "teacher" if _is_teacher_owned(r.get("teacher_id")) else "system"
    return {
        "total": len(rows), "items": rows,
        "class_id": norm_class(class_id or ""),
        "class_source": class_source,
        "class_unbound": class_unbound,
        "hint": hint,
    }


@router.get("/stats")
def grades_stats(teacher=Depends(_require_teacher)):
    """按课程聚合：实训 / 教师 / 综合 三项的平均分 + 人数。

    教师默认只统计自己班级的成绩（班级经 P0-1 解析链），管理员统计全部。

    P0-2 去重：同一**人**可能同时存在教师正式行与系统草稿行（一人一钱包上线前
    草稿学号是 `W{wallet[:10]}` 造出来的，与教师填的真实学号不是同一个字符串，
    而 UNIQUE(student_id, course) 恰好允许它们共存），直接 AVG 会把一个人算两次、
    并把草稿分混进均值。此处先按主体（security.principal_of：钱包/学号反查到的
    稳定 userId）去重，身份查不出时才退回学号；同时返回
    `total_rows` / `duplicate_rows`，让“重复行”在数字上可见而不是静默影响结论。
    """
    user = teacher
    rid = int(user.get("role_id") or 0)
    uid = user.get("user_id") or ""
    teacher_class, class_unbound, hint, class_source = "", False, "", ""
    with get_conn() as conn:
        scope = _teacher_class_scope(conn, user)   # 管理员：class_source='all'、不限制
        teacher_class = scope["class_id"]
        class_unbound = scope["class_unbound"]
        hint = scope["hint"]
        class_source = scope["class_source"]
        sql = (
            "SELECT course, student_id, wallet, teacher_id, class_id, score, "
            "training_score, final_score, updated_at FROM student_grades"
        )
        params: list = []
        conds: list = []
        if teacher_class:
            conds.append("class_id=?")
            params.append(teacher_class)
        elif class_unbound:
            # 未绑定班级：只统计自己录入的行（不越权汇总全校）
            conds.append("COALESCE(teacher_id, '')=?")
            params.append(uid)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]

        def _key(r: dict) -> tuple:
            """聚合主键：(课程, 本人稳定主体)；身份查不出时退回学号。"""
            p = principal_of(conn, str(r.get("wallet") or ""), str(r.get("student_id") or ""))
            return (str(r.get("course") or ""),
                    p or ("sid:" + str(r.get("student_id") or "")))

        def _rank(r: dict) -> tuple:
            """有效行排序键：教师行 > 系统行；同层取更新时间最新。"""
            return (
                1 if _is_teacher_owned(r.get("teacher_id")) else 0,
                str(r.get("updated_at") or ""),
            )

        picked: dict[tuple, dict] = {}
        duplicate_rows = 0
        for r in rows:
            key = _key(r)
            cur = picked.get(key)
            if cur is None:
                picked[key] = r
                continue
            duplicate_rows += 1
            if _rank(r) > _rank(cur):
                picked[key] = r
    groups: dict[str, list[dict]] = {}
    for r in picked.values():
        groups.setdefault(str(r.get("course") or ""), []).append(r)
    items = []
    for course in sorted(groups):
        rs = groups[course]
        n = len(rs) or 1
        items.append({
            "course": course,
            "cnt": len(rs),                                   # 去重后的人数
            "avg_training": round(sum(float(r["training_score"] or 0) for r in rs) / n, 2),
            "avg_manual": round(sum(float(r["score"] or 0) for r in rs) / n, 2),
            "avg_final": round(sum(float(r["final_score"] or 0) for r in rs) / n, 2),
            "teacher_rows": sum(1 for r in rs if _is_teacher_owned(r.get("teacher_id"))),
        })
    return {
        "items": items,
        "total_rows": len(rows),
        "duplicate_rows": duplicate_rows,
        "class_id": teacher_class,
        "class_source": class_source,
        "class_unbound": class_unbound,
        "hint": hint,
        "note": "统计口径：按 (课程, 学生主体) 去重后的有效行（教师行优先于系统行）",
    }


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
    user: dict = Depends(_require_teacher),
):
    """教师录入 / 更新成绩（教师主动写成绩册，是唯一能产生「教师正式行」的入口）。

    命中同 (学号, 课程) 的系统行（teacher_id 为 system/''）时直接接管并改写；
    已存在的其他教师行同样按「后录入者覆盖」的旧语义保留（不改现有业务行为）。
    """
    rid = int(user.get("role_id") or 0)
    uid = user.get("user_id") or ""
    uname = user.get("user_name") or ""
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

    P0-2：成绩行按**钱包候选集** `lower(wallet) IN (...)` 取（教师录分时可能用 userId /
    stu: 别名 / 真实地址任一口径，单值匹配会“明明有成绩却看不到”）；候选集查不到时
    再按学号兼容一次（旧行 wallet 为空只填了学号）。
    P1-25：另外返回系统草稿 `draft`（存于 grade_draft，不混入成绩册）。
    """
    w = wallet.strip()
    if not w:
        raise HTTPException(400, "wallet 必填")
    ensure_own_wallet(user, w)  # 学生仅能查自己钱包，教师/管理员不受限

    # 多租户 scope 浅接线：学生（非特权角色）按本人 user_id 收紧可见范围
    # （命中本人归属行 + 未登记归属旧行，见 db.scope_where）；教师/管理员
    # 传 None 不过滤，保持全局视图，避免特权视角"丢数据"。
    # 注：student_grades 租户列由 db.init_db 在线迁移补齐（旧行 DEFAULT ''）。
    my_uid = (user.get("user_id") or "").strip()
    scope_uid = my_uid or None
    if int(user.get("role_id") or 0) in PRIVILEGED_ROLES:
        scope_uid = None
    sc, sp = scope_where("student_grades", user_id=scope_uid)

    with get_conn() as conn:
        cands = resolve_wallet_candidates(conn, w, my_uid)
        h, lc = lower_wallet_in(cands)
        # 学号口径兼容（旧行 wallet 为空 / 教师只填了学号）
        sid_h, sid_p = "", []
        if scope_uid:
            ur = conn.execute(
                "SELECT student_id FROM user_info WHERE user_id=?", (scope_uid,)
            ).fetchone()
            sid = str(ur["student_id"] or "") if ur else ""
            if sid:
                sid_h, sid_p = "?", [sid]
        where = f"(lower(wallet) IN ({h})"
        params: list = list(lc)
        if sid_h:
            where += f" OR (COALESCE(wallet, '') = '' AND student_id IN ({sid_h}))"
            params += sid_p
        where += ")"
        if sc:
            where += " AND " + sc
            params += list(sp)
        rows = conn.execute(
            "SELECT * FROM student_grades WHERE " + where + " ORDER BY course ASC",
            params,
        ).fetchall()
        draft = None
        if lc:
            try:
                draft = conn.execute(
                    "SELECT * FROM grade_draft "
                    "WHERE user_id=? OR lower(wallet) IN (" + h + ") "
                    "ORDER BY updated_at DESC LIMIT 1",
                    (my_uid, *lc),
                ).fetchone()
            except Exception:
                draft = None  # grade_draft 尚未创建（迁移未跑完）：不影响成绩返回
        # 草稿回签：本条草稿是否已被教师同步进成绩册（与 with 同层，确保总是已绑定）
        applied_row = None
        if draft is not None:
            d0 = dict(draft)
            applied_row = _find_student_grade_row(
                conn, wallet=str(d0.get("wallet") or w),
                draft_user_id=str(d0.get("user_id") or my_uid),
                student_id=str(d0.get("student_id") or ""),
                course=str(d0.get("course") or TRAINING_COURSE),
            )

    items = []
    for r in rows:
        item = dict(r)
        try:
            item["training_detail"] = json.loads(item.get("training_detail") or "{}")
        except (TypeError, json.JSONDecodeError):
            item["training_detail"] = {}
        # P1-25：学生也能看出哪一行是教师正式评过的分、哪一行还只是系统算的实训分
        item["row_kind"] = "teacher" if _is_teacher_owned(item.get("teacher_id")) else "system"
        items.append(item)

    # 实时计算当前 wallet 的实训成绩（用于对比 / 预览）
    training_now, detail_now = _compute_training_score(w)

    # 草稿状态回签（修「学生不知道成绩走到哪一步」）：草稿本身不产生综合分，必须
    # 教师同步入册；此前学生只能靠“成绩记录空不空”猜，这里直接给出结论。
    draft_out = _draft_payload(draft)
    if draft_out is not None:
        grades_ts = str(applied_row["updated_at"] if applied_row is not None else "")
        draft_ts = str(draft_out.get("updated_at") or "")
        draft_out["in_grades"] = applied_row is not None
        # 草稿没班级时，「全部同步」的批量筛不到它（与 /grades/drafts 同一预警口径）
        draft_out["class_missing"] = not str(draft_out.get("class_id") or "").strip()
        # applied = 成绩册已有该生该课的行，且更新时间不早于本草稿（本次草稿已被采纳）
        draft_out["applied"] = applied_row is not None and grades_ts >= draft_ts
        draft_out["grades_row_id"] = int(applied_row["id"]) if applied_row is not None else None
        draft_out["grades_updated_at"] = grades_ts
        draft_out["status"] = "synced" if draft_out["applied"] else "pending_teacher"
        draft_out["status_text"] = (
            "已入册：教师已同步本草稿，正式成绩参与综合分" if draft_out["applied"]
            else ("成绩册里那一行还是更早的快照：你刚刷新的部分尚待教师再同步一次"
                  if applied_row is not None else "待教师同步为正式成绩（入册需教师动作，学生不可自助）")
        )

    return {
        "wallet": w,
        "wallet_candidates": cands,
        "grades": items,
        "total": len(items),
        "training_now": training_now,
        "detail_now": detail_now,
        "draft": draft_out,
        "note": "成绩册（grades）仅在教师录入/同步后产生；draft 为系统实时草稿，不计入综合分",
    }


# ===========================================================================
# 实训成绩草稿（P1-8 / P1-25）：草稿只写 grade_draft，成绩册只由教师动作产生
# ===========================================================================
def _draft_payload(row: Any) -> Optional[dict]:
    """grade_draft 行 → 响应体（training_detail 解析成对象）。"""
    if row is None:
        return None
    d = dict(row)
    try:
        d["training_detail"] = json.loads(d.get("training_detail") or "{}")
    except (TypeError, json.JSONDecodeError):
        d["training_detail"] = {}
    return d


def _wallet_owner(conn, wallet: str) -> Optional[dict]:
    """该钱包归属的登录账号（user_info 行），学生行优先。

    存在意义：草稿（grade_draft）的身份**必须跟着钱包主人走，而不是跟着调用者走**。
    实测缺陷：教师在自己账号上代学生刷新草稿时，uid_key 取的是调用者（教师），
    于是落出一条 user_id=教师 / student_name=老师1号 而 wallet=学生地址的假草稿；
    教师点「全班同步」就会把真实学生的成绩行改名。
    """
    if not wallet:
        return None
    cands = resolve_wallet_candidates(conn, wallet, "")
    if not cands:
        return None
    h, params = lower_wallet_in(cands)
    rows = conn.execute(
        "SELECT user_id, name, role_id, student_id, class_id, school_id, wallet FROM user_info "
        f"WHERE lower(user_id) IN ({h}) OR lower(wallet) IN ({h}) OR lower(username) IN ({h})",
        (*params, *params, *params),
    ).fetchall()
    if not rows:
        return None
    for r in rows:                     # 成绩草稿只服务学生评价 → 学生行优先
        if int(r["role_id"] or 0) == 4:
            return dict(r)
    return dict(rows[0])


def _refresh_draft(
    conn, wallet: str, user_id: str = "",
    *, student_id: str = "", student_name: str = "", course: str = TRAINING_COURSE,
    class_hint: str = "",
) -> dict:
    """按 wallet 重算实训成绩并写入 grade_draft（UNIQUE(user_id, course)）。

    本函数**绝不触碰 student_grades** —— 这正是它存在的全部意义：旧实现把草稿
    直接写进成绩册，一旦花名册里有该生真实学号，UPDATE 就会命中教师正式行，
    并把综合分重算成「教师分按 0 计」（在库副本上实测 84.3 → 0.6）。
    学号/姓名/班级口径以 user_info 为准（外部 SSO 有真实数据时优先用它）。

    class_hint：调用者令牌里的班级快照，仅作最后一级回退（且只在本人自刷时用），
    见下方班级回退链。
    """
    caller_uid = (user_id or "").strip()
    owner = _wallet_owner(conn, wallet)
    owner_uid = str((owner or {}).get("user_id") or "")
    # 草稿归属 = 钱包主人；调用者只是操作人（教师代刷不得把自己写成被评价人）
    uid_key = owner_uid or caller_uid or (wallet or "").strip()
    cands = resolve_wallet_candidates(conn, wallet, uid_key)
    # 钱包口径收敛：候选集里有真实地址就用它入库。前端传的是登录 user_id（UUID）时，
    # 直接落库会让成绩册 / 草稿的「钱包」列变成账号 ID，教师无法与链上对账。
    addr = next((c for c in cands if is_address(str(c))), "")
    wallet_out = addr or (wallet or "").strip()
    training, detail = _compute_training_score(wallet_out)
    detail_json = json.dumps(detail, ensure_ascii=False)
    ts = now()

    u = None
    if uid_key:
        u = conn.execute(
            "SELECT student_id, name, class_id, school_id FROM user_info WHERE user_id=?",
            (uid_key,),
        ).fetchone()
    sid = (student_id or (str(u["student_id"] or "") if u else "") or f"W{(wallet_out or '')[:10]}")
    sname = (student_name or (str(u["name"] or "") if u else "") or f"学生_{(wallet_out or '')[:6]}")
    school_id = str(u["school_id"] or "") if u else ""
    # 班级回退链：花名册 → 成绩册已有行 → 本人令牌快照。
    # 三者都拿不到时草稿落进空班级桶，而教师端草稿列表按班级等值筛选 →
    # 该生刷多少次草稿都不会出现在待同步列表里，正式成绩永远等不到。
    class_id = norm_class(str(u["class_id"] or "")) if u else ""
    if not class_id:
        tgt = _find_student_grade_row(
            conn, wallet=wallet_out, draft_user_id=uid_key, student_id=sid, course=course
        )
        class_id = norm_class(tgt["class_id"]) if tgt else ""
    if not class_id and caller_uid and caller_uid == uid_key:
        class_id = norm_class(class_hint)   # 教师代刷不得把教师的班级写进学生草稿

    existing = conn.execute(
        "SELECT id FROM grade_draft WHERE user_id=? AND course=?", (uid_key, course)
    ).fetchone()
    if existing:
        conn.execute(
            """UPDATE grade_draft
               SET wallet=?, student_id=?, student_name=?, class_id=?, school_id=?,
                   training_score=?, training_detail=?, updated_at=?
               WHERE id=?""",
            (wallet_out, sid, sname, class_id, school_id, training, detail_json, ts, existing["id"]),
        )
        draft_id, action = int(existing["id"]), "updated"
    else:
        cur = conn.execute(
            """INSERT INTO grade_draft
               (user_id, wallet, student_id, student_name, course,
                class_id, school_id, training_score, training_detail, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (uid_key, wallet_out, sid, sname, course, class_id, school_id,
             training, detail_json, ts, ts),
        )
        draft_id, action = int(cur.lastrowid), "created"
    return {
        "draft_id": draft_id, "action": action, "course": course,
        "user_id": uid_key, "wallet": wallet_out, "wallet_candidates": cands,
        "student_id": sid, "student_name": sname,
        "class_id": class_id, "school_id": school_id,
        # 班级为空 = 草稿会被教师端的本班筛选漏掉，界面必须把它当预警而不是一行注释
        "class_missing": not class_id,
        "training_score": training, "detail": detail,
        # 操作人留痕：代刷（教师/管理员）时调用者与草稿归属不是同一个人，
        # 界面据此提示「已按钱包主人身份建档」，不假装是本人操作
        "operator_user_id": caller_uid,
        "identity_corrected": bool(owner_uid and caller_uid and owner_uid != caller_uid),
    }


def _apply_draft_to_grades(conn, draft: dict, operator: dict) -> dict:
    """把一条系统草稿同步进成绩册（教师显式动作，P1-25 唯一的草稿 → 成绩通道）。

    写保护（按目标行的 teacher_id 判定，系统不再有任何隐式改写路径）：
      - 教师正式行：只刷新实训维度（wallet / training_score / training_detail），
        综合分用**该行自己的**教师分重算 —— 绝不把教师分当作 0；
      - 系统行（teacher_id ∈ system/''）：整行接管，归属转给操作教师；
      - 无匹配行：新建一行（教师分=0，待教师录入评分）。
    目标行按身份（钱包候选集 + 学号）而非单一学号匹配，见 _find_student_grade_row。
    """
    uid = operator.get("user_id") or ""
    uname = operator.get("user_name") or ""
    ts = now()
    wallet = str(draft.get("wallet") or "")
    course = str(draft.get("course") or TRAINING_COURSE)
    training = float(draft.get("training_score") or 0)
    detail_json = json.dumps(draft.get("training_detail") or {}, ensure_ascii=False)
    class_id = norm_class(str(draft.get("class_id") or ""))
    if not class_id:
        # 草稿本身没班级（花名册与成绩册都取不到）时，落到操作教师自己解析出的班级：
        # “教师把这条草稿采纳进本班”正是它的语义。否则同步出的成绩行 class_id 为空，
        # 在任何教师的本班成绩册里都不存在 → 教师分无从录入 → 学生综合分永远碜在草稿阶段。
        class_id = _teacher_class_scope(conn, operator).get("class_id") or ""
    school_id = str(draft.get("school_id") or "")
    sid = str(draft.get("student_id") or "")
    sname = str(draft.get("student_name") or "")
    draft_user = str(draft.get("user_id") or "")

    # 身份兜底（修「全班同步一次，学生姓名被改写成教师姓名」）：草稿的 user_id 必须
    # 就是该钱包的主人。历史错配草稿（旧版本教师代刷产物）一旦被同步，会把真实
    # 学生的成绩行改名 —— 宁可拒绝同步并给出可执行指引，也不静默改写。
    owner = _wallet_owner(conn, wallet)
    owner_uid = str((owner or {}).get("user_id") or "")
    if draft_user and owner_uid and draft_user != owner_uid:
        return {"id": None, "action": "rejected", "student_id": sid,
                "reason": f"草稿身份（{draft_user}）与钱包 {wallet} 的归属账号「"
                          f"{(owner or {}).get('name') or owner_uid}」不一致，已拒绝同步："
                          f"请学生本人到「我的成绩」点「刷新我的实训分」后重新同步"}

    row = _find_student_grade_row(
        conn, wallet=wallet, draft_user_id=draft_user, student_id=sid, course=course
    )
    # 真实学号可以补进占位行（收敛 P0-2）；反过来绝不拿占位值盖掉真值
    better_sid = (
        sid if (row and sid and not _is_synthetic_sid(sid, wallet)
                and _is_synthetic_sid(str(row["student_id"] or ""), wallet))
        else ""
    )
    new_wallet = _pick_wallet(str(row["wallet"] or "") if row else "", wallet)

    if row and _is_teacher_owned(row["teacher_id"]):
        manual = float(row["score"] or 0)
        # 孤儿行补班级：教师行 class_id 为空时（旧版本无隐式写入遗留），这一行在
        # 任何教师的本班列表里都看不到，教师想改分也找不到入口。只补空、不改动已有班级。
        backfill_class = bool(class_id) and not str(row["class_id"] or "").strip()
        conn.execute(
            "UPDATE student_grades SET wallet=?, training_score=?, final_score=?, "
            "training_detail=?" + (", student_id=?" if better_sid else "") +
            (", class_id=?" if backfill_class else "") +
            ", updated_at=? WHERE id=?",
            (new_wallet, training, _compute_final(training, manual), detail_json,
             *((better_sid,) if better_sid else ()),
             *((class_id,) if backfill_class else ()), ts, row["id"]),
        )
        return {"id": int(row["id"]), "action": "training_only",
                "student_id": better_sid or str(row["student_id"] or ""),
                "reason": "该行是教师正式成绩，仅刷新实训维度，教师分与备注不变",
                "class_id": class_id if backfill_class else str(row["class_id"] or ""),
                "score": manual, "final_score": _compute_final(training, manual)}

    if row:
        manual = float(row["score"] or 0)
        conn.execute(
            """UPDATE student_grades
               SET student_name=?, wallet=?, training_score=?, final_score=?, training_detail=?,
                   teacher_id=?, teacher_name=?, class_id=?, school_id=?, updated_at=?
                   """
            + (", student_id=?" if better_sid else "")
            + """ WHERE id=?""",
            (sname, new_wallet, training, _compute_final(training, manual), detail_json,
             uid, uname, class_id or row["class_id"] or "", school_id or row["school_id"] or "",
             ts, *((better_sid,) if better_sid else ()), row["id"]),
        )
        return {"id": int(row["id"]), "action": "adopted",
                "student_id": better_sid or str(row["student_id"] or ""),
                "score": manual, "final_score": _compute_final(training, manual)}

    manual = 0.0
    cur = conn.execute(
        """INSERT INTO student_grades
           (student_id, student_name, course, score, wallet,
            training_score, final_score, training_detail,
            teacher_id, teacher_name, class_id, school_id, remark,
            created_at, updated_at)
           VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (sid, sname, course, wallet, training, _compute_final(training, manual), detail_json,
         uid, uname, class_id, school_id, "由系统草稿同步生成，待教师录入评分", ts, ts),
    )
    return {"id": int(cur.lastrowid), "action": "created", "score": manual,
            "final_score": _compute_final(training, manual)}


@router.post("/draft/refresh")
def refresh_draft(
    wallet: str = Query(..., description="学生链上钱包地址"),
    student_id: str = Query("", description="学号（可选，为空则取 user_info）"),
    student_name: str = Query("", description="学生姓名（可选）"),
    course: str = Query(TRAINING_COURSE, description="课程名称"),
    user: dict = Depends(get_current_user),
):
    """刷新**系统草稿**（写 grade_draft，不进成绩册）。

    由前端「我的成绩」页主动点击触发；查看报告等 GET 接口不再隐式写库（P1-8）。
    身份校验：学生仅能刷新本人钱包；教师 / 管理员不受限。
    """
    w = wallet.strip()
    if not w:
        raise HTTPException(400, "wallet 必填")
    ensure_own_wallet(user, w)
    my_uid = (user.get("user_id") or "").strip()
    with get_conn() as conn:
        result = _refresh_draft(conn, w, my_uid, student_id=student_id.strip(),
                                student_name=student_name.strip(), course=course,
                                class_hint=str(user.get("class_id") or ""))
    result["grades_touched"] = False
    return result


# 向后兼容：/auto-draft 名称保留但行为已改（不再写 student_grades）
@router.post("/auto-draft", deprecated=True)
def auto_draft_grade(
    wallet: str = Query(..., description="学生链上钱包地址"),
    student_id: str = Query("", description="学号（可选，为空则取 user_info）"),
    student_name: str = Query("", description="学生姓名（可选）"),
    course: str = Query(TRAINING_COURSE, description="课程名称"),
    user: dict = Depends(get_current_user),
):
    """**已废弃**：等价于 /draft/refresh。旧版会把草稿写进 student_grades 并
    覆盖教师正式分（P1-25 事故源），现统一改写 grade_draft；`id` 字段从此指
    草稿行 id，正式成绩请用 /draft/apply 由教师显式产生。"""
    out = refresh_draft(wallet=wallet, student_id=student_id,
                        student_name=student_name, course=course, user=user)
    out["deprecated"] = True
    out["table"] = "grade_draft"
    return out


@router.get("/drafts")
def list_drafts(
    class_id: Optional[str] = Query(None, description="按班级筛选（教师默认本班）"),
    course: Optional[str] = Query(None, description="按课程模糊筛选"),
    teacher=Depends(_require_teacher),
):
    """教师端：查看待同步的系统草稿（P1-25）。

    草稿不再混在成绩册里，教师在这里单独看到「系统算了但还没采纳」的列表，
    逐条（或让 /draft/apply 按班级批量）同步为正式成绩。
    班级范围经 P0-1 解析链；未绑定班级时返回空列表 + class_unbound + hint。
    """
    user = teacher
    with get_conn() as conn:
        scope = _teacher_class_scope(conn, user)
        teacher_class = scope["class_id"]
        class_source = scope["class_source"]
        class_unbound = scope["class_unbound"]
        hint = scope["hint"]
        if class_id:
            teacher_class = norm_class(class_id)
            class_source = "query"
            class_unbound = False
            hint = ""
        elif class_unbound:
            return {"total": 0, "items": [], "class_id": "", "class_source": class_source,
                    "class_unbound": True, "hint": hint,
                    "note": "未解析到所属班级，暂不展示草稿"}
        sql = "SELECT * FROM grade_draft WHERE 1=1"
        params: list = []
        # 无班级草稿一并带出并标记：它们是「学生刷了但教师永远看不到」的暗数据
        # （SSO 未下发班级 / 花名册无该生时会产生），只按班级等值筛选会被静默丢掉，
        # 学生就此拿不到正式成绩。空班级不是“别人的班”，展示给教师不跨班越权。
        include_orphan = bool(teacher_class) and not str(class_id or "").strip()
        if teacher_class:
            if include_orphan:
                sql += " AND (class_id=? OR COALESCE(class_id, '')='')"
            else:
                sql += " AND class_id=?"
            params.append(teacher_class)
        if course:
            sql += " AND course LIKE ?"
            params.append(f"%{course}%")
        sql += " ORDER BY class_id ASC, student_id ASC, updated_at DESC"
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]

        # 标记每条草稿在成绩册里的目标行归属：教师行（只刷实训）/ 系统行 / 无行
        for d in rows:
            try:
                d["training_detail"] = json.loads(d.get("training_detail") or "{}")
            except (TypeError, json.JSONDecodeError):
                d["training_detail"] = {}
            tgt = _find_student_grade_row(
                conn, wallet=str(d.get("wallet") or ""),
                draft_user_id=str(d.get("user_id") or ""),
                student_id=str(d.get("student_id") or ""),
                course=str(d.get("course") or TRAINING_COURSE),
            )
            d["target_grade_id"] = int(tgt["id"]) if tgt else None
            d["target_row_kind"] = (
                "teacher" if tgt and _is_teacher_owned(tgt["teacher_id"])
                else ("system" if tgt else "none")
            )
            d["class_missing"] = not str(d.get("class_id") or "").strip()
        if include_orphan:
            rows.sort(key=lambda d: bool(d.get("class_missing")))  # 本班在前、无班级在后（稳定排序）
    orphan_total = sum(1 for d in rows if d.get("class_missing"))
    return {
        "total": len(rows), "items": rows,
        "orphan_total": orphan_total,
        "class_id": teacher_class, "class_source": class_source,
        "class_unbound": class_unbound, "hint": hint,
        "note": "草稿不影响学生综合分；同步（/draft/apply）后才进入成绩册"
                + (f"；其中 {orphan_total} 条未标班级，不会被「全部同步」批量带走，"
                   "请逐条同步（同步时会自动归入你解析出的班级）" if orphan_total else ""),
    }


@router.post("/draft/apply")
def apply_draft(
    req: dict = Body(...),
    teacher=Depends(_require_teacher),
):
    """教师显式把草稿同步为正式成绩（P1-25：成绩册唯一的系统写入通道，且需人工触发）。

    请求体：`{"draft_id": 12}` 或 `{"user_id": "tzs001", "course": "区块链实训"}`，
    或 `{"class_id": "...", "all": true}` 批量同步本班草稿。
    写保护见 _apply_draft_to_grades：教师正式行永远只刷实训维度，不会被清零。
    """
    user = teacher
    draft_id = req.get("draft_id")
    uid = str(req.get("user_id") or "").strip()
    course = str(req.get("course") or TRAINING_COURSE)
    do_all = bool(req.get("all"))
    results: list[dict] = []
    with get_conn() as conn:
        if do_all:
            scope = _teacher_class_scope(conn, user)
            teacher_class = scope["class_id"]
            class_unbound = scope["class_unbound"]
            want_class = norm_class(str(req.get("class_id") or "")) or teacher_class
            if class_unbound and not want_class:
                raise HTTPException(400, "未绑定班级，不能批量同步；请先调用 /api/auth/bind-class")
            sql = "SELECT * FROM grade_draft WHERE 1=1"
            params: list = []
            if want_class:
                sql += " AND class_id=?"
                params.append(want_class)
            drafts = conn.execute(sql, params).fetchall()
        else:
            if draft_id:
                one = conn.execute(
                    "SELECT * FROM grade_draft WHERE id=?", (int(draft_id),)).fetchone()
            elif uid:
                one = conn.execute(
                    "SELECT * FROM grade_draft WHERE user_id=? AND course=?",
                    (uid, course)).fetchone()
            else:
                raise HTTPException(400, "需提供 draft_id，或 user_id + course，或 all=true")
            if not one:
                raise HTTPException(404, "草稿不存在（可先调用 /api/grades/draft/refresh）")
            drafts = [one]
        for d in drafts:
            payload = _draft_payload(d) or {}
            applied = _apply_draft_to_grades(conn, payload, user)
            applied["draft_id"] = payload.get("id")
            applied.setdefault("student_id", payload.get("student_id"))
            applied["training_score"] = payload.get("training_score")
            results.append(applied)
    rejected = sum(1 for r in results if r.get("action") == "rejected")
    return {"synced": len(results) - rejected, "rejected": rejected, "items": results,
            "note": "教师正式行仅刷新实训维度（action=training_only），教师分与备注不变；"
                    "身份与钱包归属不一致的草稿会被拒绝（action=rejected）"}


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
