"""归属范围与花名册解析（P0-1 / P0-4 修复的单一事实源）。

归档边界：**成绩按学校归档**（教师可看 / 可操作本校全部学生的成绩），
班级不再是权限边界，只作为「聚焦 / 筛选」与沙盘轮次的归属单位。因此本模块
同时提供两条同构的解析链：

  1. resolve_school_scope()：学校范围（成绩册 / 名单 / 看板的默认边界）
     显式绑定 → user_info → 成绩册派生；全落空时 school_unbound=True + hint，
     调用方据此退回到「只看自己录入的行」而不是静默空列表。
  2. resolve_class_scope()：班级范围（沙盘轮次、班级进度看板仍按班使用）
     显式绑定(class_teacher_bind) → user_info → JWT 快照 → 成绩册派生。

背景（问题清单 P0-1）：外部 SSO 对教师不返回 classId（或返回 "0"），登录侧把
缺失值落成空串；若看板以「教师所属班级」为过滤条件，两处任一为空就恒返回 0 行——
而"0 行"在界面上与"你们班没人做"看起来一模一样，会被当成教学结论讲出去。

本模块把这几件事收口成一处，供 auth.py / chain.py / grades.py 共用（避免多处各写一份、
彼此漂移）；其中 teacher_scope() 是「教师能看 / 能改哪些成绩」的唯一边界链
（学校 → 过渡期班级 → 只看自己录的），roster_students() 取数：user_info 有学生就用它；user_info 为空
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
# 成绩改按学校归档后的同构提示：学校是「能不能看 / 能不能改」的硬边界，
# 解析不到学校时界面必须说"没定学校"，而不是把空列表伪装成"没人生成成绩"。
HINT_SCHOOL_UNBOUND = (
    "当前账号还没有确定任教学校（SSO 未下发 schoolId），所以成绩册只看得见你自己录入的行。"
    "请在「学生成绩」页点「绑定任教范围」填写学校 ID（或让管理员代绑）。"
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


def norm_school(raw: Any) -> str:
    """规整学校标识：占位口径与班级一致（SSO 用 "0" / null 表示"没有学校"）。

    单独升一个入口而不是复用 norm_class：两者语义不同（一个是班、一个是校），
    但“无效占位值”必须同一套消化，否则 school_id='0' 会变成一个真实学校。
    """
    return norm_class(raw)


def school_of_expr(t: str) -> str:
    """「一行成绩 / 一条草稿应归属哪个学校」的 SQL 表达式（小写，取不到为空串）。

    行上写了 school_id 就直接用；没写（历史行、旧版本只填了班级的行）则按
    **身份**回查花名册：钱包（含 wallet_alias 登记的别名）→ 学号 → user_id，
    任一命中即算。查边界与写回学校都复用本表达式，避免“筛得到的行写不回学校”。
    """
    return (
        f"(CASE WHEN COALESCE(lower({t}.school_id), '') <> '' THEN lower({t}.school_id) "
        f"ELSE COALESCE((SELECT lower(u.school_id) FROM user_info u "
        f"WHERE COALESCE(u.school_id, '') <> '' "
        f"AND ((COALESCE({t}.wallet, '') <> '' AND (lower(u.wallet) = lower({t}.wallet) "
        f"OR EXISTS(SELECT 1 FROM wallet_alias wa WHERE wa.user_id = u.user_id "
        f"AND lower(wa.alias) = lower({t}.wallet)))) "
        f"OR (COALESCE({t}.student_id, '') <> '' AND u.student_id = {t}.student_id) "
        f"OR (COALESCE({t}.user_id, '') <> '' AND u.user_id = {t}.user_id)) "
        f"ORDER BY (u.role_id = {STUDENT_ROLE}) DESC LIMIT 1), '') END)"
    )


# ===========================================================================
# 字段映射总表：SSO 登录返回 → 本地列 → 它到底用来干什么
# ===========================================================================
# “取错字段”的根源是三套命名混在一起：SSO 用 camelCase、DB 用 snake_case、
# 平台 JWT 只装 5 个键。下表是本项目的**唯一事实源**（改字段必须同步改这里）：
#
#   SSO 字段（data.*）      本地列                用它干什么
#   ─────────────────────────────────────────────────────────────────────
#   userId              user_info.user_id     用户主键（UUID）。成绩行 user_id 也存它；
#                                             平台 JWT 的 user_id。一人一钱包/权限以此为准
#   name                user_info.name        姓名，界面展示（教师列表「学员姓名」）
#   username            user_info.username    ⚠ 实测存的是**姓名**（SSO 把姓名装进了
#                                             username），不是列名暗示的登录账号 →
#                                             **禁止**拿它做唯一定位
#   studentId           user_info.student_id  ⚠ 实测存的是**登录账号**（学生手机号 /
#                                             教师工号），不是学号。成绩行 student_id
#                                             与它同一套字符串 →「按 student_id 回查」成立，
#                                             按它查 username 列恒空（旧 bug 源头）
#   accessToken         （不落库）            外部 SSO 会话令牌，只在登录响应透传；
#                                             平台内部鉴权用自签 JWT（data.token）
#   roleId              user_info.role_id     1=管理员 / 3=教师 / 4=学生；权限只认它
#   ─────────────────────────────────────────────────────────────────────
#   classId             user_info.class_id    班级（norm_class 清洗，0/"0"=无）。学生=所属班，
#   student_grades.class_id                   教师=任教班。**只用于展示与筛选，
#                                             不再是权限边界**（旧版按班归档已废弃）
#   ─────────────────────────────────────────────────────────────────────
#   schoolId            user_info.school_id   ★ **成绩归档的唯一边界字段**（norm_school
#                                             清洗）。教师能看/能改哪些行全由它决定：
#                                             teacher_scope() 解析链 =
#                                             class_teacher_bind.school_id（人工绑定）→
#                                             user_info.school_id（登录写入）→成绩册反推；
#                                             三者都定不出 → 只看自己录的（不退化成全校）
#   → student_grades.school_id                归档结果列。写入时由 _identity_lookup 按
#     grade_draft.school_id                   user_id/钱包/学号 反查花名册自动补齐，
#                                             **只补空值、不改已有值**；历史空行不丢弃，
#                                             读取时走 school_of_expr() 临时定校，
#                                             refresh-training 把它们补写落库
#   schoolName          user_info.school_name 学校名称，**仅供界面回显**；边界比较一律用
#                                             ID（名称可变、可能重名、大小写不定）
#   collegeId           user_info.college_id  学院（SSO 常返回 0=无）。不参与归档/权限
#   majorId             user_info.major_id    专业，同上，仅登记
#
#   两个写入时机：① 登录 → _upsert_user_info（SSO 没返学校/班级时沿用库中原值，
#   不把已定边界抹空）；② 录成绩 → grades.py 自动补归档字段（前端不要求手填）。
#   读取永远不依赖 JWT 里的学校（载荷根本没这个键），而是 current_identity() /
#   resolve_school_scope() 以库为准。


def _school_name_lookup_sql() -> str:
    """“学校 ID → 学校名称”的唯一取数口径（名称只存在于 user_info.school_name）。"""
    return (
        "SELECT school_id, school_name FROM user_info "
        "WHERE COALESCE(school_id, '') <> '' AND COALESCE(school_name, '') <> '' "
        f"ORDER BY (role_id = {TEACHER_ROLE}) DESC, updated_at DESC"
    )


def school_names(conn: sqlite3.Connection) -> dict[str, str]:
    """全库 school_id（小写）→ 学校名称，给列表类接口一次拿完、避免 N+1。

    为什么需要它：成绩 / 草稿行上只存 **school_id**（归档比较只认 ID，名称可变、
    可能重名），而界面要给人看名称。SSO **不下发班级名称**（只有 classId），
    所以班级列只能显示 ID；学校则不同，登录时已存下 schoolName，
    不显示出来纯属接口少 join 了一步。
    """
    out: dict[str, str] = {}
    try:
        rows = conn.execute(_school_name_lookup_sql()).fetchall()
    except sqlite3.Error:
        return out
    for r in rows:
        key = norm_school(r["school_id"]).lower()
        name = str(r["school_name"] or "").strip()
        if key and name:
            out.setdefault(key, name)
    return out


def school_name_of(conn: sqlite3.Connection, school_id: str) -> str:
    """单个学校的名称（查不到返回空串，由调用方降级显示 ID）。"""
    return school_names(conn).get(norm_school(school_id).lower(), "")


def _school_from_grade_book(conn: sqlite3.Connection, teacher_uid: str) -> str:
    """教师亲手录过成绩的那些行所对应的学校（成绩册派生，最后备胎）。"""
    uid = (teacher_uid or "").strip()
    if not uid:
        return ""
    try:
        row = conn.execute(
            f"SELECT {school_of_expr('g')} AS sch FROM student_grades g "
            "WHERE g.teacher_id=? AND COALESCE(g.teacher_id, '') NOT IN ('system', '') "
            f"AND {school_of_expr('g')} <> '' ORDER BY g.updated_at DESC LIMIT 1",
            (uid,),
        ).fetchone()
    except sqlite3.Error:
        return ""
    return norm_school(row["sch"]) if row else ""


def resolve_school_scope(conn: sqlite3.Connection, user: dict) -> dict[str, Any]:
    """解析「当前教师看成绩 / 名单的学校范围」（成绩按学校归档）。

    返回字段：
      school_id       生效学校（'' 表示无）
      school_name     学校名称（可为空，仅用于界面回显）
      school_source   来源标记：bind | user_info | grade_book | '' | 'all'
      school_unbound  教师无学校时为 True（调用方据此收紧到自己的行，不越权也不静默为空）
      all_schools     管理员的全校视角（教师恒为 False）
      hint            可直接展示的中文提示
    """
    rid = int(user.get("role_id") or 0)
    uid = (user.get("user_id") or "").strip()
    if rid == ADMIN_ROLE:
        return {"school_id": "", "school_name": "", "school_source": "all",
                "school_unbound": False, "all_schools": True, "hint": ""}

    school, src, name = "", "", ""
    # 1) 人工绑定（教师自助 / 管理员代绑）优先：它是“人写定的事实”
    if uid:
        try:
            row = conn.execute(
                "SELECT school_id FROM class_teacher_bind WHERE teacher_user_id=?", (uid,)
            ).fetchone()
            school = norm_school(row["school_id"]) if row else ""
        except sqlite3.Error:
            school = ""   # 列尚未迁移（首次启动前）：降级走后面的链路
    if school:
        src = "bind"
    else:
        # 2) user_info（登录时由 SSO 写入 schoolId）
        if uid:
            try:
                row = conn.execute(
                    "SELECT school_id, school_name FROM user_info WHERE user_id=?", (uid,)
                ).fetchone()
                school = norm_school(row["school_id"]) if row else ""
                name = str((row["school_name"] or "") if row else "")
            except sqlite3.Error:
                school = ""
        if school:
            src = "user_info"
        else:
            # 3) 成绩册派生（自己录过的行反推学校）
            school = _school_from_grade_book(conn, uid)
            src = "grade_book" if school else ""
    if not school:
        return {"school_id": "", "school_name": "", "school_source": "",
                "school_unbound": True, "all_schools": False, "hint": HINT_SCHOOL_UNBOUND}
    if not name:
        try:
            row = conn.execute(
                "SELECT school_name FROM user_info WHERE school_id=? AND COALESCE(school_name, '') <> '' "
                "ORDER BY (role_id = ?) DESC LIMIT 1",
                (school, TEACHER_ROLE),
            ).fetchone()
            name = str(row["school_name"] or "") if row else ""
        except sqlite3.Error:
            name = ""
        if not name:
            # 同上口径兼容：库里 school_id 大小写不一时也能拿到名称
            name = school_names(conn).get(norm_school(school).lower(), "")
    return {"school_id": school, "school_name": name, "school_source": src,
            "school_unbound": False, "all_schools": False, "hint": ""}


def class_in_school(conn: sqlite3.Connection, class_id: str, school_id: str) -> bool:
    """该班级是否属于该学校（花名册里有任何一名本校学生就读于该班）。

    学校边界下的「按班筛选」仍须不跳校：拿 class_in_school 卡住显式传入的
    class_id，否则“传个外班班号就能越校”会原样保留（旧版就是如此）。
    查不到任何学生时返回 False（宁看不到也不越权）。
    """
    cls, sch = norm_class(class_id), norm_school(school_id)
    if not cls or not sch:
        return False
    try:
        row = conn.execute(
            "SELECT 1 FROM user_info WHERE class_id=? AND school_id=? LIMIT 1", (cls, sch)
        ).fetchone()
        if row:
            return True
        # 成绩册口径：本班已有成绩行写着本校学校
        row = conn.execute(
            f"SELECT 1 FROM student_grades g WHERE g.class_id=? AND {school_of_expr('g')}=? LIMIT 1",
            (cls, sch.lower()),
        ).fetchone()
    except sqlite3.Error:
        return False
    return bool(row)


def class_allowed_in_scope(conn: sqlite3.Connection, scope: dict, class_id: str) -> bool:
    """显式传入的班级是否落在教师的归档范围内（空班级 = 不筛，恒 True）。

    规则住在这一处：成绩册 / 名单 / 进度看板 三个入口都要卡同样的“不得按外校班筛”，
    写在三份就一定会漂移（HTTP 异常由调用方自己抛，以保留各自的提示文案）。
    """
    cls = norm_class(class_id)
    if not cls:
        return True
    mode = scope.get("mode")
    if mode == "all":
        return True
    if mode == "school":
        return class_in_school(conn, cls, str(scope.get("school_id") or ""))
    if mode == "class":
        return cls == norm_class(str(scope.get("class_id") or ""))
    return False    # mode=self：还没任何任教范围，不拿它当“全校”用


def teacher_scope(conn: sqlite3.Connection, user: dict) -> dict[str, Any]:
    """教师看 / 改成绩与名单的**归档范围**（成绩按学校归档，班级不再是权限边界）。

    与 grades.py 的旧局部实现同一口径，升到本模块是为了让
    成绩册 / 花名册 / 进度看板 三处共用一条边界链，不再各写一份而彼此漂移。

    四种 mode，调用方直接按 mode 编 SQL / 判权限：
      all      管理员：不限制
      school   解析出任教学校 → **本校全部学生**（跨班不限）都能看、能录、能同步
      class    学校定不出但班级定得出（老库 / SSO 不下发 schoolId）→ 沿用旧的班级边界。
               这一级存在的意义：改归档口径不许把教师原本看得见的行「改没了」
      self     学校与班级都定不出 → 只看 / 只改自己录入的行（绝不退化成“看全校”）

    返回字段：mode / school_id / school_name / school_source / school_unbound /
    class_id / class_source / class_unbound / all_schools / hint。
    """
    if int(user.get("role_id") or 0) == ADMIN_ROLE:
        return {"mode": "all", "school_id": "", "school_name": "", "school_source": "all",
                "school_unbound": False, "class_id": "", "class_source": "all",
                "class_unbound": False, "all_schools": True, "hint": ""}
    sch = resolve_school_scope(conn, user)
    if sch["school_id"]:
        return {**sch, "mode": "school", "class_id": "", "class_source": "",
                "class_unbound": False, "hint": ""}
    cls = resolve_class_scope(conn, user)
    if cls["class_id"]:
        return {"mode": "class", "school_id": "", "school_name": "", "school_source": "",
                "school_unbound": True, "all_schools": False,
                "class_id": cls["class_id"], "class_source": cls["class_source"],
                "class_unbound": False, "hint": ""}
    return {"mode": "self", "school_id": "", "school_name": "", "school_source": "",
            "school_unbound": True, "all_schools": False, "class_id": "",
            "class_source": cls["class_source"], "class_unbound": True,
            "hint": sch["hint"] or cls["hint"]}


def bind_teacher_scope(
    conn: sqlite3.Connection, teacher_user_id: str, *,
    class_id: str = "", school_id: str = "", bound_by: str = "",
) -> dict[str, str]:
    """写入「教师 → 任教范围」绑定（学校＝成绩归档边界；班级＝可选聚焦范围）。

    只改传进来的那一列：留空表示“这次不改它”（绑定页可以只绑学校、也可以只绑班级），
    避免“只换个学校focus就把班级绑定抹掉”。同步刷新 user_info 同名字段，
    让“看自己的归属”这条路径也一致。返回绑定后的最终值供接口直接回显。
    """
    from .db import now as _now
    uid = (teacher_user_id or "").strip()
    if not uid:
        raise ValueError("teacher_user_id 不能为空")
    cls, sch = norm_class(class_id), norm_school(school_id)
    if not (cls or sch):
        raise ValueError("class_id / school_id 至少需要一个非空值")
    cur = conn.execute(
        "SELECT class_id, school_id FROM class_teacher_bind WHERE teacher_user_id=?", (uid,)
    ).fetchone()
    final_cls = cls or norm_class(cur["class_id"] if cur else "")
    final_sch = sch or norm_school(cur["school_id"] if cur else "")
    conn.execute(
        "INSERT INTO class_teacher_bind(teacher_user_id, class_id, school_id, bound_by, bound_at) "
        "VALUES (?,?,?,?,?) "
        "ON CONFLICT(teacher_user_id) DO UPDATE SET class_id=excluded.class_id, "
        "school_id=excluded.school_id, bound_by=excluded.bound_by, bound_at=excluded.bound_at",
        (uid, final_cls, final_sch, (bound_by or "").strip(), _now()),
    )
    # 同步刷新 user_info：绑定的班级 / 学校回写到账号上（只补有值的列）
    try:
        if final_cls:
            conn.execute(
                "UPDATE user_info SET class_id=?, updated_at=? WHERE user_id=?",
                (final_cls, _now(), uid),
            )
        if final_sch:
            conn.execute(
                "UPDATE user_info SET school_id=?, updated_at=? WHERE user_id=?",
                (final_sch, _now(), uid),
            )
    except sqlite3.Error:
        pass  # user_info 异常不影响绑定本身（绑定表已是权威来源）
    return {"class_id": final_cls, "school_id": final_sch}


def bind_teacher_class(
    conn: sqlite3.Connection, teacher_user_id: str, class_id: str, bound_by: str,
    school_id: str = "",
) -> str:
    """写入「教师 → 班级」绑定（兼容旧调用方）；学校边界请用 bind_teacher_scope。"""
    return bind_teacher_scope(
        conn, teacher_user_id, class_id=class_id, school_id=school_id, bound_by=bound_by
    )["class_id"]


def _grade_book_pref(r: dict) -> tuple:
    """代表行优选评分（越大越优先）：教师行 > 系统行；真实学号 > 占位学号。"""
    sid = str(r.get("student_id") or "")
    return (
        1 if _is_teacher_row(r.get("teacher_id")) else 0,
        0 if _is_placeholder_sid(sid, str(r.get("wallet") or "")) else 1,
        str(r.get("updated_at") or ""),
    )


def _grade_book_students(
    conn: sqlite3.Connection, class_id: str = "", school_id: str = ""
) -> list[dict]:
    """成绩册派生花名册（P0-4 未修前的可用降级）。

    分组键用「主体」而不是学号（P0-2）：同一个人的教师正式行与系统行常常是
    两个不同的 student_id 字符串（真实学号 vs `W{wallet[:10]}` 占位值，而
    UNIQUE(student_id, course) 恰好允许它们共存），按学号去重会把一个人列成
    两行。principal_of 解析不出稳定主体时退回「非内置钱包」，再退回学号。
    排序用 updated_at 原序，不引入新偏差。

    取数边界：给 school_id 时按**本校成绩行**筛（行上没写学校则按身份回查花名册，
    见 school_of_expr），班级只作可选叠加；没学校时才沿用旧的「有班级就算」口径。
    """
    from .security import BUILTIN_WALLETS, principal_of
    sch = norm_school(school_id)
    cls = norm_class(class_id)
    cols = (
        "student_id, student_name, wallet, class_id, school_id, teacher_id, "
        "training_score, final_score, score, updated_at"
    )
    params: list = []
    if sch:
        sql = (
            f"SELECT {cols}, {school_of_expr('g')} AS school_eff FROM student_grades g "
            f"WHERE {school_of_expr('g')} = ?"
        )
        params.append(sch.lower())
        if cls:
            sql += " AND class_id=?"
            params.append(cls)
    elif cls:
        sql = f"SELECT {cols}, COALESCE(school_id, '') AS school_eff FROM student_grades WHERE class_id=?"
        params.append(cls)
    else:
        # 既无学校也无班级：只能拿“写着班级的行”当口径（旧行为），不拿全库当名单
        sql = ("SELECT " + cols + ", COALESCE(school_id, '') AS school_eff FROM student_grades "
               "WHERE COALESCE(class_id,'')<>''")
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
            "school_id": str(r.get("school_eff") or r.get("school_id") or ""),
            "school_name": "",
            "wallet": r.get("wallet") or "",
            "login_count": 0,
            "last_login_at": "",
        })
    return out


def roster_students(
    conn: sqlite3.Connection, class_id: str = "", *,
    school_id: str = "", all_classes: bool = False
) -> tuple[list[dict], str]:
    """取学生名单，返回 (rows, roster_source)。

    边界优先级：all_classes（管理员全校）> school_id（**本校**，成绩归档口径）
    > class_id（单班聚焦）。三者的降级一致：user_info 有学生就用它，
    为空时用成绩册派生（roster_source='grade_book'），界面必须据此标注数据来源，
    绝不能把它当"全班人数"报出去。
    """
    cls = norm_class(class_id)
    sch = norm_school(school_id)
    base = ("SELECT user_id, username, name, student_id, class_id, school_id, school_name, "
            "wallet, login_count, last_login_at FROM user_info WHERE role_id=?")
    if all_classes:
        rows = conn.execute(
            base + " ORDER BY school_id, class_id, student_id", (STUDENT_ROLE,)
        ).fetchall()
    elif sch:
        sql, args = base + " AND school_id=?", [sch]
        if cls:
            sql += " AND class_id=?"
            args.append(cls)
        rows = conn.execute(sql + " ORDER BY class_id, student_id",
                             (STUDENT_ROLE, *args)).fetchall()
    elif cls:
        rows = conn.execute(
            base + " AND class_id=? ORDER BY student_id", (STUDENT_ROLE, cls)
        ).fetchall()
    else:
        rows = []
    if rows:
        return [dict(r) for r in rows], "user_info"
    derived = _grade_book_students(
        conn, "" if all_classes else cls, "" if all_classes else sch
    )
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
        "SELECT user_id, username, name, student_id, class_id, school_id, school_name, "
        "college_id, wallet, login_count, last_login_at FROM user_info WHERE user_id=?",
        (uid,),
    ).fetchone()
    if row:
        out = dict(row)
        out["school_id"] = norm_school(out.get("school_id"))
        return out
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
        # 行上学校是归档字段：即使花名册没这人也把它带回去，界面才能说清“哪所学校”
        "school_id": norm_school(g["school_id"]), "school_name": "",
        "college_id": "", "wallet": g["wallet"] or uid,
        "login_count": 0, "last_login_at": "",
    }


def current_identity(conn: sqlite3.Connection, user: dict) -> dict:
    """按 JWT 身份回查本人在 user_info 里的**权威归档字段**（/auth/session 用，P1-33）。

    平台 JWT 只装 user_id / role_id / wallet / class_id / user_name（**不装 school_id**，
    机构信息不进可被客户端解读的 token），而前端会话恢复时需要知道学校 / 班级，
    所以这里以库为准回查。查不到返回 {}，调用方保留 JWT 旧值 —— 绝不伪造学校。

    只认 user_id（主键）：登录账号存在 `student_id` 列（SSO 把账号放在 studentId，
    把姓名放在 username），拿账号去查 user_id / username 都命中不了。
    """
    uid = str((user or {}).get("user_id") or "").strip()
    if not uid:
        return {}
    row = conn.execute(
        "SELECT user_id, username, name, role_id, student_id, class_id, school_id, "
        "school_name, college_id, major_id, wallet FROM user_info WHERE user_id=?",
        (uid,),
    ).fetchone()
    if row is None:
        return {}
    return {
        "user_id": uid,
        "username": str(row["username"] or ""),
        "name": str(row["name"] or ""),
        "role_id": int(row["role_id"] or 0),
        "student_id": str(row["student_id"] or ""),
        "class_id": norm_class(row["class_id"]),
        # 本人行上没写学校时，退到与权限边界同一条解析链（bind → user_info → 成绩册）
        "school_id": (norm_school(row["school_id"])
                      or resolve_school_scope(conn, user).get("school_id", "")),
        "school_name": str(row["school_name"] or ""),
        "college_id": norm_class(row["college_id"]),
        "major_id": norm_class(row["major_id"]),
        "wallet": str(row["wallet"] or ""),
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
