"""班级归属与花名册解析（P0-1 / P0-4 修复的单一事实源）。

背景（问题清单 P0-1）：外部 SSO 对教师不返回 classId（或返回 "0"），登录侧把
缺失值落成空串；而三块学情看板（/api/auth/class-students、
/api/auth/platform-progress、/api/chain/tutorial/progress/class）都以
「教师所属班级」+「user_info 花名册」为过滤条件，两处任一为空就恒返回 0 行——
而"0 行"在界面上与"你们班没人做"看起来一模一样，会被当成教学结论讲出去。

本模块把两件事收口成一处，供 auth.py / chain.py 共用（避免三处各写一份、
彼此漂移）：

  1. resolve_class_scope()：班级解析链
     显式绑定(class_teacher_bind) → user_info → JWT 快照 → 成绩册派生；
     全部落空时返回 class_unbound=True + 可直接展示的 hint，而不是一个静默的 0。
  2. roster_students()：花名册取数。user_info 有学生就用它；user_info 为空
     （P0-4 未修前的旧库、或从未登录过的用户）时降级用成绩册派生名单，
     并在返回值里标出来源，让界面能如实说明"这份名单来自成绩册"。
"""
from __future__ import annotations

from typing import Any

import sqlite3

# 教师未绑定班级时给前端的提示（可直接展示，不再返回一个"看起来像空班"的 0）
HINT_CLASS_UNBOUND = (
    "当前账号还没有绑定班级，所以看板看不到学生。"
    "请在「成绩册」里为录入的成绩填写班级，或调用 POST /api/auth/bind-class 绑定班级后再看。"
)
HINT_ROSTER_EMPTY = (
    "花名册（user_info）里还没有该班级的学生记录："
    "学生登录一次即会自动登记。当前列表由成绩册派生，仅供核对，不代表全班人数。"
)

# 学生角色 ID（与 user_info.role_id 口径一致：1=管理员 3=教师 4=学生）
STUDENT_ROLE = 4
TEACHER_ROLE = 3
ADMIN_ROLE = 1

# 系统自动草稿的录入人标识（与 report.py / grades.py 历史写入口径一致）
SYSTEM_TEACHER_ID = "system"

# 系统行的 teacher_id 取值：'system'（报告/草稿链路）+ ''（教程满步建行链路）。
# 与 grades.SYSTEM_TEACHER_IDS 同口径 —— 此前花名册只认 'system'，会把
# teacher_id='' 的占位行误判成教师亲手录入的行。
SYSTEM_TEACHER_IDS = ("system", "")


def _is_teacher_row(teacher_id: Any) -> bool:
    """一行成绩是否教师亲手录入（不得被系统行盖掉权威口径）。"""
    return str(teacher_id if teacher_id is not None else "").strip() not in SYSTEM_TEACHER_IDS


def _is_placeholder_sid(sid: str, wallet: str) -> bool:
    """学号是不是系统合成的占位值（'W' + 钱包前缀，见 grades._refresh_draft）。

    判定规则统一收口到 security.is_placeholder_student_id（成绩行改写 / 花名册
    排名 / 一次性归并脚本三方必须对“这个学号不是人的信息”同一口径）。
    """
    from .security import is_placeholder_student_id

    return is_placeholder_student_id(sid, wallet)


def norm_class(raw: Any) -> str:
    """规整班级标识：None / '' / '0' / 0 / 'null' / 'undefined' 一律视为"未绑定"。

    P0-1 的次因就是 SSO 用 "0" 表示"没有班级"，而库里把它当成了一个真实班级，
    于是 `WHERE class_id='0'` 永远查不到学生。此处统一在入口消化掉。
    """
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s or s.lower() in ("null", "none", "undefined"):
        return ""
    # 数字 0 或其字符串形式（"0" / "0.0"）：SSO 的"无班级"占位
    if s.strip("0").strip(".") == "":
        return ""
    return s


def _class_from_grade_book(conn: sqlite3.Connection, teacher_uid: str) -> str:
    """教师自己录入过成绩的班级（成绩册派生，最后备胎）。"""
    uid = (teacher_uid or "").strip()
    if not uid:
        return ""
    row = conn.execute(
        "SELECT class_id FROM student_grades "
        "WHERE teacher_id=? AND COALESCE(class_id,'')<>'' AND teacher_id<>? "
        "ORDER BY updated_at DESC LIMIT 1",
        (uid, SYSTEM_TEACHER_ID),
    ).fetchone()
    return norm_class(row["class_id"]) if row else ""


def _student_class_from_grade_book(conn: sqlite3.Connection, user: dict) -> str:
    """学生成绩册行上填的班级（教师录入时手填，学号 / 钱包两种口径都试）。"""
    uid = (user.get("user_id") or "").strip()
    wallet = (user.get("wallet") or "").strip()
    sid = ""
    if uid:
        row = conn.execute(
            "SELECT student_id FROM user_info WHERE user_id=?", (uid,)
        ).fetchone()
        sid = str(row["student_id"] or "") if row else ""
    keys = [k for k in (sid, wallet, uid) if k]
    for k in keys:
        row = conn.execute(
            "SELECT class_id FROM student_grades "
            "WHERE (student_id=? OR wallet=?) AND COALESCE(class_id,'')<>'' "
            "ORDER BY updated_at DESC LIMIT 1",
            (k, k),
        ).fetchone()
        if row:
            return norm_class(row["class_id"])
    return ""


def resolve_class_scope(conn: sqlite3.Connection, user: dict) -> dict[str, Any]:
    """解析"当前用户看板的班级范围"，返回统一结构供各看板直接 update 进响应。

    返回字段：
      class_id        生效班级（'' 表示无）
      class_source    来源标记：bind | user_info | jwt | grade_book | '' | 'all'
      class_unbound   教师无班级时为 True（前端据此显示引导，而不是显示"0 人"）
      all_classes     管理员未指定班级时的全校视角（教师恒为 False）
      hint            可直接展示的中文提示（无问题时为 ''）
    """
    rid = int(user.get("role_id") or 0)
    uid = (user.get("user_id") or "").strip()
    jwt_class = norm_class(user.get("class_id"))

    # 1) 人工绑定（管理员代绑 / 教师自助）优先级最高
    bound = ""
    if uid:
        try:
            row = conn.execute(
                "SELECT class_id FROM class_teacher_bind WHERE teacher_user_id=?",
                (uid,),
            ).fetchone()
            bound = norm_class(row["class_id"]) if row else ""
        except Exception:
            bound = ""  # 表尚未创建（首次启动迁移前）：降级走后面的链路
    if bound:
        return {
            "class_id": bound, "class_source": "bind",
            "class_unbound": False, "all_classes": False, "hint": "",
        }

    # 2) user_info（登录时由 SSO 写入）
    db_class = ""
    if uid:
        try:
            row = conn.execute(
                "SELECT class_id FROM user_info WHERE user_id=?", (uid,)
            ).fetchone()
            db_class = norm_class(row["class_id"]) if row else ""
        except Exception:
            db_class = ""
    if db_class:
        return {
            "class_id": db_class, "class_source": "user_info",
            "class_unbound": False, "all_classes": False, "hint": "",
        }

    # 3) JWT 快照（P0-4 未修时 user_info 为空，登录载荷是唯一的班级载体）
    if jwt_class:
        return {
            "class_id": jwt_class, "class_source": "jwt",
            "class_unbound": False, "all_classes": False, "hint": "",
        }

    # 4) 成绩册派生（教师录分时手填的班级）
    derived = (
        _class_from_grade_book(conn, uid)
        if rid in (TEACHER_ROLE, ADMIN_ROLE)
        else _student_class_from_grade_book(conn, user)
    )
    if derived:
        return {
            "class_id": derived, "class_source": "grade_book",
            "class_unbound": False, "all_classes": False, "hint": "",
        }

    # 全部落空：管理员 = 全校视角（合理）；教师 = 明确告知"未绑定"（不再静默 0）
    if rid == ADMIN_ROLE:
        return {
            "class_id": "", "class_source": "all",
            "class_unbound": False, "all_classes": True, "hint": "",
        }
    if rid == TEACHER_ROLE:
        return {
            "class_id": "", "class_source": "",
            "class_unbound": True, "all_classes": False, "hint": HINT_CLASS_UNBOUND,
        }
    return {
        "class_id": "", "class_source": "",
        "class_unbound": False, "all_classes": False, "hint": "",
    }


def bind_teacher_class(
    conn: sqlite3.Connection, teacher_user_id: str, class_id: str, bound_by: str
) -> str:
    """写入「教师 → 班级」绑定，并同步 user_info（若该教师已登录登记过）。返回班级。"""
    from .db import now as _now
    cls = norm_class(class_id)
    if not cls:
        raise ValueError("class_id 不能为空")
    uid = (teacher_user_id or "").strip()
    if not uid:
        raise ValueError("teacher_user_id 不能为空")
    conn.execute(
        "INSERT INTO class_teacher_bind(teacher_user_id, class_id, bound_by, bound_at) "
        "VALUES (?,?,?,?) "
        "ON CONFLICT(teacher_user_id) DO UPDATE SET class_id=excluded.class_id, "
        "bound_by=excluded.bound_by, bound_at=excluded.bound_at",
        (uid, cls, (bound_by or "").strip(), _now()),
    )
    # 同步刷新 user_info.class_id：让"看自己的班级"这条路径也一致
    try:
        conn.execute(
            "UPDATE user_info SET class_id=?, updated_at=? WHERE user_id=?",
            (cls, _now(), uid),
        )
    except Exception:
        pass  # user_info 异常不影响绑定本身（绑定表已是权威来源）
    return cls


def _grade_book_pref(r: dict) -> tuple:
    """代表行优选评分（越大越优先）：教师行 > 系统行；真实学号 > 占位学号。"""
    sid = str(r.get("student_id") or "")
    return (
        1 if _is_teacher_row(r.get("teacher_id")) else 0,
        0 if _is_placeholder_sid(sid, str(r.get("wallet") or "")) else 1,
        str(r.get("updated_at") or ""),
    )


def _grade_book_students(conn: sqlite3.Connection, class_id: str) -> list[dict]:
    """成绩册派生花名册（P0-4 未修前的可用降级）。

    分组键用「主体」而不是学号（P0-2）：同一个人的教师正式行与系统行常常是
    两个不同的 student_id 字符串（真实学号 vs `W{wallet[:10]}` 占位值，而
    UNIQUE(student_id, course) 恰好允许它们共存），按学号去重会把一个人列成
    两行。principal_of 解析不出稳定主体时退回「非内置钱包」，再退回学号。
    排序用 updated_at 原序，不引入新偏差。
    """
    from .security import BUILTIN_WALLETS, principal_of
    sql = (
        "SELECT student_id, student_name, wallet, class_id, school_id, teacher_id, "
        "training_score, final_score, score, updated_at FROM student_grades "
        "WHERE COALESCE(class_id,'')<>''"
    )
    params: list = []
    if class_id:
        sql += " AND class_id=?"
        params.append(class_id)
    sql += " ORDER BY student_id ASC, updated_at DESC"
    picked: dict[str, dict] = {}
    for r in conn.execute(sql, params).fetchall():
        sid = str(r["student_id"] or "")
        if not sid:
            continue
        wallet = str(r["wallet"] or "").strip()
        wk = wallet.lower()
        key = (principal_of(conn, wallet, sid)
               or (wk if wk and wk not in BUILTIN_WALLETS else "sid:" + sid))
        cur = picked.get(key)
        if cur is None or _grade_book_pref(dict(r)) > _grade_book_pref(cur):
            picked[key] = dict(r)
    out: list[dict] = []
    for r in sorted(picked.values(),
                    key=lambda x: (str(x["student_id"] or ""), str(x.get("wallet") or ""))):
        out.append({
            "user_id": "",                    # 成绩册没有 userId：留空，不伪造
            "username": "",
            "name": r.get("student_name") or "",
            "student_id": str(r["student_id"] or ""),
            "class_id": r.get("class_id") or "",
            "school_name": "",
            "wallet": r.get("wallet") or "",
            "login_count": 0,
            "last_login_at": "",
        })
    return out


def roster_students(
    conn: sqlite3.Connection, class_id: str, *, all_classes: bool = False
) -> tuple[list[dict], str]:
    """取学生名单，返回 (rows, roster_source)。

    - user_info 有学生 → 权威花名册（roster_source='user_info'）；
    - user_info 为空（P0-4 未修 / 学生从未登录）→ 成绩册派生
      （roster_source='grade_book'），界面必须据此标注数据来源，
      绝不能把它当"全班人数"报出去。
    """
    cls = norm_class(class_id)
    if all_classes:
        rows = conn.execute(
            "SELECT user_id, username, name, student_id, class_id, school_name, "
            "wallet, login_count, last_login_at FROM user_info WHERE role_id=? "
            "ORDER BY class_id, student_id",
            (STUDENT_ROLE,),
        ).fetchall()
    elif cls:
        rows = conn.execute(
            "SELECT user_id, username, name, student_id, class_id, school_name, "
            "wallet, login_count, last_login_at FROM user_info "
            "WHERE role_id=? AND class_id=? ORDER BY student_id",
            (STUDENT_ROLE, cls),
        ).fetchall()
    else:
        rows = []
    if rows:
        return [dict(r) for r in rows], "user_info"
    derived = _grade_book_students(conn, "" if all_classes else cls)
    return derived, ("grade_book" if derived else "empty")


def self_student_row(conn: sqlite3.Connection, user: dict) -> dict:
    """学生自己的花名册行（P0-1 降级路径）。

    user_info 无记录（旧库未修 P0-4 前登录、或登录持久化失败）时，
    从成绩册取自己最近一行拼一个最小可用行；找不到返回 {}
    （调用方据此显示「名单未登记」而不是一个看起来像真的空卡片）。
    """
    from .security import lower_wallet_in, resolve_wallet_candidates
    uid = (user.get("user_id") or "").strip()
    row = conn.execute(
        "SELECT user_id, username, name, student_id, class_id, school_name, "
        "wallet, login_count, last_login_at FROM user_info WHERE user_id=?",
        (uid,),
    ).fetchone()
    if row:
        return dict(row)
    if not uid:
        return {}
    h, lc = lower_wallet_in(resolve_wallet_candidates(conn, user.get("wallet") or "", uid))
    if not lc:
        return {}
    g = conn.execute(
        f"SELECT student_id, student_name, wallet, class_id, school_id FROM student_grades "
        f"WHERE lower(wallet) IN ({h}) OR lower(COALESCE(student_id,'')) IN ({h}) "
        f"ORDER BY updated_at DESC LIMIT 1",
        lc + lc,
    ).fetchone()
    if not g:
        return {}
    return {
        "user_id": uid, "username": "", "name": g["student_name"] or "",
        "student_id": g["student_id"] or "", "class_id": norm_class(g["class_id"]),
        "school_name": "", "wallet": g["wallet"] or uid,
        "login_count": 0, "last_login_at": "",
    }


def candidates_for_student(conn: sqlite3.Connection, student: dict) -> list[str]:
    """给花名册里的一个学生构造钱包候选集（P0-2 统一口径）。

    花名册行的 wallet 可能是 userId / stu: 别名 / 真实地址 / 成绩册里教师手填
    的任意口径，student_id 可能是学号——全部交给 resolve_wallet_candidates
    并集（它会反查 wallet_alias 与密钥库地址），调用方不再各写各的匹配。
    """
    from .security import resolve_wallet_candidates
    uid = str(student.get("user_id") or "")
    wallet = str(student.get("wallet") or "")
    sid = str(student.get("student_id") or "")
    cands = resolve_wallet_candidates(conn, wallet, uid)
    if sid:
        # 成绩册派生名单只有学号：把学号口径也并入（教师录分时可能用学号当 wallet）
        for c in resolve_wallet_candidates(conn, sid, uid):
            if c not in cands:
                cands.append(c)
    return cands
