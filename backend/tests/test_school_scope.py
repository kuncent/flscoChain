"""「成绩按学校归档」回归测试（跨班可见 / 可操作，外校一律拦住）。

归档边界从**班级**改成**学校**后，最容易出事的三件事逐条锁住：
  1. 同校不同班的学生成绩，教师必须**看得见也改得动**（这是本次改口径的全部目的）；
  2. 外校成绩必须**看 / 录 / 同步 / 删**四条路径统一 403 —— 少拦一条，边界就是装饰
     （旧版「传个外班班号就能越界」的毛病同样会出现在学校维度上）；
  3. 改口径不许把教师**原本看得见的行改没**：行上没写 school_id 的历史行按身份回查
     （school_of_expr），定不出学校但定了班级的老库走过渡期班级边界（scope_mode='class'），
     两者都没有就只看得见自己录的行（scope_mode='self'，绝不退化成「看全校」）。
顺带锁住本轮收口的两个越权：P1-18（一键刷新遍历全库）、P1-19（删除不校验归属）。
"""
from app.db import get_conn, now
from app.roster import (
    HINT_SCHOOL_UNBOUND,
    bind_teacher_scope,
    class_allowed_in_scope,
    current_identity,
    resolve_school_scope,
    school_of_expr,
    teacher_scope,
)
from app.routers.auth import _upsert_user_info
from app.routers.grades import _refresh_draft
from app.security import create_token

ADMIN = {"user_id": "adm", "role_id": 1, "wallet": "adm", "class_id": "", "user_name": "管理员"}
TEACHER = {"user_id": "tzt001", "role_id": 3, "wallet": "tzt001", "class_id": "", "user_name": "张老师"}
LONE = {"user_id": "tzt900", "role_id": 3, "wallet": "tzt900", "class_id": "", "user_name": "无范围教师"}

SCH_A, SCH_B = "100", "200"


def _h(payload: dict) -> dict:
    return {"Authorization": f"Bearer {create_token(payload)}"}


def _stu(conn, uid, sid, cls, sch):
    """花名册一行（学生）。wallet 用 stu: 别名口径，与草稿 / 成绩行保持一致。

    school_name 随手写上（真实库里登录就会存名称）：列表接口靠它把
    “学校 232” 显示成“天择大学”，不写名称就测不出名称链路。
    """
    conn.execute(
        "INSERT INTO user_info(user_id,name,role_id,student_id,class_id,school_id,"
        "school_name,wallet) VALUES(?,?,?,?,?,?,?,?)",
        (uid, f"名_{sid}", 4, sid, cls, sch, (f"校_{sch}" if sch else ""), f"stu:{uid}"),
    )


def _grade(conn, sid, score, wallet, teacher_id, *, cls="c1", sch="", training=0.0,
           updated="2026-01-01 00:00:00", course="区块链实训"):
    conn.execute(
        "INSERT INTO student_grades(student_id,student_name,course,score,wallet,training_score,"
        "final_score,teacher_id,teacher_name,class_id,school_id,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (sid, f"名_{sid}", course, score, wallet, training, training * 0.6 + score * 0.4,
         teacher_id, teacher_id, cls, sch, now(), updated),
    )


def _gid(sid):
    with get_conn() as conn:
        return int(conn.execute(
            "SELECT id FROM student_grades WHERE student_id=?", (sid,)).fetchone()["id"])


# ===========================================================================
# 边界本身：四态 mode 与「按班筛选不得跳校」
# ===========================================================================
def test_teacher_scope_four_modes(temp_db):
    with get_conn() as conn:
        assert teacher_scope(conn, ADMIN)["mode"] == "all"

        # 既没绑学校也没绑班级 → self（不是「看全校」，也不是静默空列表）
        s = teacher_scope(conn, TEACHER)
        assert s["mode"] == "self" and s["hint"] == HINT_SCHOOL_UNBOUND

        # 老库 / SSO 不下发 schoolId 但定了班级 → 过渡期班级边界（改口径不许丢行）
        bind_teacher_scope(conn, "tzt001", class_id="c1")
        s = teacher_scope(conn, TEACHER)
        assert s["mode"] == "class" and s["class_id"] == "c1" and s["school_unbound"] is True

        # 定了学校 → 学校是硬边界，此时 class_id 为空（班级不再是权限范围）
        bind_teacher_scope(conn, "tzt001", school_id=SCH_A)
        s = teacher_scope(conn, TEACHER)
        assert (s["mode"], s["school_id"], s["class_id"]) == ("school", SCH_A, "")
        assert s["school_source"] == "bind" and s["class_unbound"] is False


def test_class_filter_cannot_jump_school(temp_db):
    with get_conn() as conn:
        _stu(conn, "tzs001", "2024001", "c1", SCH_A)
        _stu(conn, "tzs002", "2024002", "c2", SCH_A)
        _stu(conn, "tzs900", "2024900", "c9", SCH_B)
        bind_teacher_scope(conn, "tzt001", school_id=SCH_A)
        sc = teacher_scope(conn, TEACHER)
        assert class_allowed_in_scope(conn, sc, "") is True        # 空 = 不筛
        assert class_allowed_in_scope(conn, sc, "c2") is True      # 本校跨班可以筛
        assert class_allowed_in_scope(conn, sc, "c9") is False     # 外校班不行
        # 无范围教师：不把「没边界」当「全校」用
        assert class_allowed_in_scope(conn, teacher_scope(conn, LONE), "c1") is False
        # 管理员不受限
        assert class_allowed_in_scope(conn, teacher_scope(conn, ADMIN), "c9") is True


def test_school_of_expr_resolves_legacy_rows_by_identity(temp_db):
    """行上没写 school_id 的历史行，靠钱包 / 学号回查花名册定校（不因此消失）。"""
    with get_conn() as conn:
        _stu(conn, "tzs002", "2024002", "c2", SCH_A)
        _grade(conn, "2024002", 80, "stu:tzs002", "tzt001", cls="c2", sch="")
        r = conn.execute(
            "SELECT " + school_of_expr("g") + " AS sch FROM student_grades g").fetchone()
        assert r["sch"] == SCH_A
        # 花名册里查不到的人：定不出学校（留空，由 self 兜底而不是乱猜）
        _grade(conn, "2024777", 60, "stu:tzs777", "tzt001", cls="cx", sch="")
        r2 = conn.execute(
            "SELECT " + school_of_expr("g") + " AS sch FROM student_grades g "
            "WHERE student_id='2024777'").fetchone()
        assert r2["sch"] == ""


def test_school_scope_resolution_chain(temp_db):
    """学校解析链：绑定 > user_info > 成绩册派生（与班级链同构）。"""
    with get_conn() as conn:
        assert resolve_school_scope(conn, TEACHER)["school_unbound"] is True
        # 成绩册派生：自己录过的行写着哪个学校，就把哪个学校当任教学校
        _stu(conn, "tzs001", "2024001", "c1", SCH_A)
        _grade(conn, "2024001", 90, "stu:tzs001", "tzt001", cls="c1", sch=SCH_A)
        s = resolve_school_scope(conn, TEACHER)
        assert (s["school_id"], s["school_source"]) == (SCH_A, "grade_book")
        # user_info 优先于成绩册
        conn.execute("INSERT INTO user_info(user_id,name,role_id,school_id) "
                     "VALUES('tzt001','张老师',3,?)", (SCH_B,))
        assert resolve_school_scope(conn, TEACHER)["school_source"] == "user_info"
        # 显式绑定最高
        bind_teacher_scope(conn, "tzt001", school_id=SCH_A)
        assert resolve_school_scope(conn, TEACHER)["school_source"] == "bind"


# ===========================================================================
# 读：成绩册 / 统计 / 名单 / 看板 —— 同校跨班全部可见
# ===========================================================================
def test_grades_list_is_school_wide(client, temp_db):
    with get_conn() as conn:
        _stu(conn, "tzs001", "2024001", "c1", SCH_A)
        _stu(conn, "tzs002", "2024002", "c2", SCH_A)   # 同校不同班
        _stu(conn, "tzs900", "2024900", "c9", SCH_B)   # 外校
        bind_teacher_scope(conn, "tzt001", school_id=SCH_A)
        _grade(conn, "2024001", 90, "stu:tzs001", "tzt001", cls="c1", sch=SCH_A)
        _grade(conn, "2024002", 80, "stu:tzs002", "tzt002", cls="c2", sch="")
        _grade(conn, "2024900", 70, "stu:tzs900", "tzt002", cls="c9", sch=SCH_B)

    body = client.get("/api/grades/list", headers=_h(TEACHER)).json()
    assert body["scope_mode"] == "school" and body["school_id"] == SCH_A
    assert sorted(i["student_id"] for i in body["items"]) == ["2024001", "2024002"], \
        "本校跨班（含他人录入的行）都可见，外校不可见"
    legacy = [i for i in body["items"] if i["student_id"] == "2024002"][0]
    assert legacy["school_effective"] == SCH_A, "行上没写学校的历史行按身份回查定校"
    # 归档只存 ID，但界面要看名称：接口得按 ID 把 school_name 补回来
    assert legacy["school_name"] == f"校_{SCH_A}", "只有 ID 会让教师面对一串数字"
    assert body["school_name"] == f"校_{SCH_A}"

    # 校内班聚焦仍可用
    one = client.get("/api/grades/list", params={"class_id": "c2"}, headers=_h(TEACHER)).json()
    assert one["total"] == 1 and one["class_source"] == "query"
    # 外校班号 / 外校校号都不能绕过边界（不是静默改查，是 403）
    assert client.get("/api/grades/list", params={"class_id": "c9"},
                      headers=_h(TEACHER)).status_code == 403
    assert client.get("/api/grades/list", params={"school_id": SCH_B},
                      headers=_h(TEACHER)).status_code == 403

    st = client.get("/api/grades/stats", headers=_h(TEACHER)).json()
    assert st["scope_mode"] == "school" and st["class_count"] == 2, "统计 = 本校，且能看出跨了几个班"
    assert client.get("/api/grades/stats", params={"school_id": SCH_B},
                      headers=_h(TEACHER)).status_code == 403


def test_unbound_teacher_never_degrades_to_school(client, temp_db):
    """self 口径：一行别人的都看不到，但自己录过的永远看得到。"""
    with get_conn() as conn:
        _stu(conn, "tzs001", "2024001", "c1", SCH_A)
        _grade(conn, "2024001", 90, "stu:tzs001", "tzt002", cls="c1", sch=SCH_A)
        # 自己录的行既不写学校也不写班级，花名册也查不到人：学校与班级都定不出
        # → mode=self（一旦写了学校，成绩册就足以反推任教学校，不再是 self）
        _grade(conn, "2024011", 70, "stu:tzs011", "tzt900", cls="", sch="")
    body = client.get("/api/grades/list", headers=_h(LONE)).json()
    assert body["scope_mode"] == "self" and body["hint"] == HINT_SCHOOL_UNBOUND
    assert [i["student_id"] for i in body["items"]] == ["2024011"], "只看自己录入的行"
    assert client.post("/api/grades/draft/apply", json={"all": True},
                       headers=_h(LONE)).status_code == 400, "无范围不得批量同步"


# ===========================================================================
# 写：录入 / 刷新 / 删除
# ===========================================================================
def test_upsert_archives_by_identity_and_blocks_foreign(client, temp_db):
    payload = {"student_id": "2024002", "student_name": "李四",
               "course": "区块链实训", "score": 88}
    with get_conn() as conn:
        _stu(conn, "tzs001", "2024001", "c1", SCH_A)
        _stu(conn, "tzs002", "2024002", "c2", SCH_A)     # 同校不同班
        _stu(conn, "tzs900", "2024900", "c9", SCH_B)     # 外校
        bind_teacher_scope(conn, "tzt001", school_id=SCH_A)
        _grade(conn, "2024900", 70, "stu:tzs900", "tzt002", cls="c9", sch=SCH_B)

    # 不必手填班级 / 学校：按学生身份自动归档到本校 + 本人所在班
    r = client.post("/api/grades/upsert", json=payload, headers=_h(TEACHER))
    assert r.status_code == 200, r.text
    assert (r.json()["school_id"], r.json()["class_id"]) == (SCH_A, "c2")

    # 重复录入命中「已有行」分支（回归：Row 没有 .get，早先这里直接 500）
    r2 = client.post("/api/grades/upsert", json=dict(payload, score=95), headers=_h(TEACHER))
    assert r2.status_code == 200 and r2.json()["action"] == "updated", r2.text
    with get_conn() as conn:
        g = conn.execute("SELECT score, school_id, class_id FROM student_grades "
                         "WHERE student_id='2024002'").fetchone()
    assert (g["score"], g["school_id"], g["class_id"]) == (95, SCH_A, "c2")

    # 不得借录入把学生改到外校（显式传值 + 已有行两种入口都拦）
    assert client.post("/api/grades/upsert", json=dict(payload, school_id=SCH_B),
                       headers=_h(TEACHER)).status_code == 403
    assert client.post("/api/grades/upsert",
                       json={"student_id": "2024900", "student_name": "王五",
                             "course": "区块链实训", "score": 60},
                       headers=_h(TEACHER)).status_code == 403


def test_refresh_training_stays_in_scope(client, temp_db):
    with get_conn() as conn:
        _stu(conn, "tzs001", "2024001", "c1", SCH_A)
        _stu(conn, "tzs002", "2024002", "c2", SCH_A)
        _stu(conn, "tzs900", "2024900", "c9", SCH_B)
        bind_teacher_scope(conn, "tzt001", school_id=SCH_A)
        # 本校两行都没写学校（历史数据），外校一行写了
        _grade(conn, "2024001", 90, "stu:tzs001", "tzt001", cls="c1", sch="")
        _grade(conn, "2024002", 80, "stu:tzs002", "tzt002", cls="c2", sch="")
        _grade(conn, "2024900", 70, "stu:tzs900", "tzt002", cls="c9", sch=SCH_B)

    body = client.post("/api/grades/refresh-training", headers=_h(TEACHER)).json()
    assert body["scope_mode"] == "school"
    assert body["refreshed"] == 2 == body["total_with_wallet"], "P1-18：只刷本校，不再遍历全库"
    assert body["school_backfilled"] == 2, "顺带把本校历史行的 school_id 补上"
    with get_conn() as conn:
        foreign = conn.execute(
            "SELECT updated_at FROM student_grades WHERE student_id='2024900'").fetchone()
        mine = conn.execute(
            "SELECT school_id FROM student_grades WHERE student_id='2024001'").fetchone()
    assert foreign["updated_at"] == "2026-01-01 00:00:00", "外校行不得被一次点击改写"
    assert mine["school_id"] == SCH_A


def test_delete_grade_boundary(client, temp_db):
    with get_conn() as conn:
        _stu(conn, "tzs001", "2024001", "c1", SCH_A)
        _stu(conn, "tzs002", "2024002", "c2", SCH_A)
        _stu(conn, "tzs900", "2024900", "c9", SCH_B)
        bind_teacher_scope(conn, "tzt001", school_id=SCH_A)
        _grade(conn, "2024002", 80, "stu:tzs002", "tzt002", cls="c2", sch=SCH_A)
        _grade(conn, "2024900", 70, "stu:tzs900", "tzt002", cls="c9", sch=SCH_B)
        other_id, foreign_id = _gid("2024002"), _gid("2024900")

    # 本校（哪怕是别的教师录的）可删；外校返回 403 而不是 404（别让人误以为已被删）
    assert client.delete(f"/api/grades/{other_id}", headers=_h(TEACHER)).status_code == 200
    assert client.delete(f"/api/grades/{foreign_id}", headers=_h(TEACHER)).status_code == 403
    with get_conn() as conn:
        assert conn.execute("SELECT 1 FROM student_grades WHERE id=?",
                            (foreign_id,)).fetchone() is not None
    assert client.delete("/api/grades/999999", headers=_h(TEACHER)).status_code == 404


# ===========================================================================
# 草稿：本校跨班都在列表里，外校草稿同步不进去
# ===========================================================================
def test_drafts_school_wide_and_apply(client, temp_db):
    with get_conn() as conn:
        _stu(conn, "tzs001", "2024001", "c1", SCH_A)
        _stu(conn, "tzs002", "2024002", "c2", SCH_A)
        _stu(conn, "tzs900", "2024900", "c9", SCH_B)
        bind_teacher_scope(conn, "tzt001", school_id=SCH_A)
        _refresh_draft(conn, "stu:tzs001", "tzs001")
        _refresh_draft(conn, "stu:tzs002", "tzs002")
        _refresh_draft(conn, "stu:tzs900", "tzs900")

    body = client.get("/api/grades/drafts", headers=_h(TEACHER)).json()
    assert body["scope_mode"] == "school" and body["school_id"] == SCH_A
    assert sorted(d["student_id"] for d in body["items"]) == ["2024001", "2024002"], \
        "草稿列表同样按学校（跨班不限）"
    foreign_id = [d["id"] for d in body["items"] if d["student_id"] == "2024001"][0]
    assert body["items"][0]["school_missing"] is False

    a = client.post("/api/grades/draft/apply", json={"all": True}, headers=_h(TEACHER))
    assert a.status_code == 200 and a.json()["synced"] == 2, a.text
    with get_conn() as conn:
        got = {r["student_id"]: r["school_id"] for r in conn.execute(
            "SELECT student_id, school_id FROM student_grades").fetchall()}
    assert got == {"2024001": SCH_A, "2024002": SCH_A}

    # 外校草稿按 id 硬塞也必须 403（否则「只能操作本校」被同步动作绕过）
    with get_conn() as conn:
        fd = conn.execute("SELECT id FROM grade_draft WHERE student_id='2024900'").fetchone()
    assert client.post("/api/grades/draft/apply", json={"draft_id": int(fd["id"])},
                       headers=_h(TEACHER)).status_code == 403


def test_orphan_draft_adopts_operator_school(client, temp_db):
    """定不出归属的草稿（花名册查无此人）仍是暗数据不得吞掉，采纳时归入操作者本校。"""
    with get_conn() as conn:
        bind_teacher_scope(conn, "tzt001", school_id=SCH_A)
        draft = _refresh_draft(conn, "stu:tzs999", "tzs999")
    assert draft["school_missing"] is True
    body = client.get("/api/grades/drafts", headers=_h(TEACHER)).json()
    assert body["total"] == 1 and body["orphan_total"] == 1
    assert body["school_missing_total"] == 1
    a = client.post("/api/grades/draft/apply", json={"draft_id": body["items"][0]["id"]},
                    headers=_h(TEACHER))
    assert a.status_code == 200 and a.json()["synced"] == 1, a.text
    with get_conn() as conn:
        g = conn.execute("SELECT school_id, class_id FROM student_grades").fetchone()
    assert g["school_id"] == SCH_A, "本校教师采纳的草稿归入本校"


def test_transitional_class_mode_keeps_old_behaviour(client, temp_db):
    """老库（只有班级绑定）：改口径后仍按班看得见原本那几行，不多看也不少看。"""
    with get_conn() as conn:
        _stu(conn, "tzs001", "2024001", "c1", "")
        _stu(conn, "tzs002", "2024002", "c2", "")
        bind_teacher_scope(conn, "tzt001", class_id="c1")
        _grade(conn, "2024001", 90, "stu:tzs001", "tzt001", cls="c1")
        _grade(conn, "2024002", 80, "stu:tzs002", "tzt002", cls="c2")    # 他人录的跳班行
        _grade(conn, "2024011", 75, "stu:tzs011", "tzt001", cls="c3")    # 自己录的跳班行
    body = client.get("/api/grades/list", headers=_h(TEACHER)).json()
    assert body["scope_mode"] == "class" and body["class_id"] == "c1"
    assert [i["student_id"] for i in body["items"]] == ["2024001", "2024011"], \
        "本班所有人 + 自己录过的行（改口径不许把历史行改没）"
    assert client.get("/api/grades/list", params={"class_id": "c2"},
                      headers=_h(TEACHER)).status_code == 403, "过渡口径下班级仍是边界"


# ===========================================================================
# 绑定入口与看板：名单 / 搭链进度 / 平台概览 必须与成绩册同一人群
# ===========================================================================
def test_bind_school_only_and_status_api(client, temp_db):
    with get_conn() as conn:
        conn.execute("INSERT INTO user_info(user_id,name,role_id,wallet) "
                     "VALUES('tzt001','张老师',3,'tzt001')")
        _stu(conn, "tzs001", "2024001", "c1", SCH_A)
    b = client.post("/api/auth/bind-class", json={"school_id": SCH_A}, headers=_h(TEACHER))
    assert b.status_code == 200 and b.json()["school_id"] == SCH_A, b.text
    assert b.json()["class_id"] == ""
    # "0" 不是学校也不是班级：两个字段全为占位值时要求至少一个真实值
    assert client.post("/api/auth/bind-class", json={"school_id": "0"},
                       headers=_h(TEACHER)).status_code == 400

    s = client.get("/api/auth/roster-status", headers=_h(TEACHER)).json()
    assert s["scope_mode"] == "school" and s["school_id"] == SCH_A
    assert s["checks"]["school_resolved"] is True
    assert s["roster_scope_text"] == f"本校 {SCH_A}"
    assert s["roster_count"] == 1
    # 只改班级不清学校（绑定页可以分两次填）
    c = client.post("/api/auth/bind-class", json={"class_id": "c1"}, headers=_h(TEACHER))
    assert (c.json()["class_id"], c.json()["school_id"]) == ("c1", SCH_A)


def test_boards_share_grade_population(client, temp_db):
    """成绩册、学生名单、搭链进度、平台概览四处的「本校」必须是同一批人。"""
    with get_conn() as conn:
        _stu(conn, "tzs001", "2024001", "c1", SCH_A)
        _stu(conn, "tzs002", "2024002", "c2", SCH_A)
        _stu(conn, "tzs900", "2024900", "c9", SCH_B)
        bind_teacher_scope(conn, "tzt001", school_id=SCH_A)

    cs = client.get("/api/auth/class-students", headers=_h(TEACHER)).json()
    assert cs["scope_mode"] == "school" and cs["total"] == 2
    cp = client.get("/api/chain/tutorial/progress/class", headers=_h(TEACHER)).json()
    assert cp["scope_mode"] == "school" and cp["total"] == cs["total"], \
        "看板人数与名单不一致会让教师得出错误结论"
    assert {i["student_id"] for i in cp["items"]} == {"2024001", "2024002"}
    pp = client.get("/api/auth/platform-progress", headers=_h(TEACHER)).json()
    assert pp["scope"] == "school" and pp["total_students"] == 2 and pp["class_count"] == 2

    # 校内班聚焦 / 外校班拒绝，两条路径口径一致
    one = client.get("/api/chain/tutorial/progress/class", params={"class_id": "c2"},
                     headers=_h(TEACHER)).json()
    assert one["total"] == 1 and one["class_source"] == "query"
    for url in ("/api/auth/class-students", "/api/chain/tutorial/progress/class"):
        assert client.get(url, params={"class_id": "c9"}, headers=_h(TEACHER)).status_code == 403, url


def test_admin_still_sees_all_schools(client, temp_db):
    with get_conn() as conn:
        _stu(conn, "tzs001", "2024001", "c1", SCH_A)
        _stu(conn, "tzs900", "2024900", "c9", SCH_B)
        _grade(conn, "2024001", 90, "stu:tzs001", "tzt001", cls="c1", sch=SCH_A)
        _grade(conn, "2024900", 70, "stu:tzs900", "tzt002", cls="c9", sch=SCH_B)
    body = client.get("/api/grades/list", headers=_h(ADMIN)).json()
    assert body["scope_mode"] == "all" and body["total"] == 2
    # 管理员可按学校收窄（含行上没写学校、靠身份定校的历史行）
    conn_a = client.get("/api/grades/list", params={"school_id": SCH_A}, headers=_h(ADMIN)).json()
    assert [i["student_id"] for i in conn_a["items"]] == ["2024001"]


# ===========================================================================
# 归档字段从哪里来：登录落库 → user_info.school_id → 会话回显（P1-32 / P1-33）
# ===========================================================================
def test_login_persist_archives_school_and_keeps_old_on_blank(temp_db):
    """登录落库只认 schoolId；SSO 本次没返就沿用库里已定的，不把边界抹空。"""
    _upsert_user_info({
        "userId": "u-lin-1", "name": "林同学", "username": "林同学",
        "studentId": "19898800031", "roleId": 4, "classId": "216",
        "schoolId": "232", "schoolName": "天择大学", "collegeId": 0,
    })
    with get_conn() as conn:
        r = conn.execute("SELECT * FROM user_info WHERE user_id='u-lin-1'").fetchone()
        assert (r["school_id"], r["class_id"], r["student_id"]) == ("232", "216", "19898800031")
        # 归档边界就是这一列：教师 / 学生同一个 user_id 都能定出学校
        assert resolve_school_scope(conn, {"user_id": "u-lin-1", "role_id": 3})["school_id"] == "232"
        # 实测口径：登录账号存在 student_id 列，username 列是姓名 →
        # 拿账号去查 username 必空（旧版“取错字段”就在此）
        assert conn.execute("SELECT 1 FROM user_info WHERE username='19898800031'").fetchone() is None

    # 再登一次：SSO 没返学校 / 班级（给的是占位值）→ 库里边界必须原样保留
    _upsert_user_info({"userId": "u-lin-1", "name": "林同学", "roleId": 4,
                       "studentId": "19898800031", "classId": "0", "schoolId": 0})
    with get_conn() as conn:
        r = conn.execute("SELECT school_id, class_id, login_count FROM user_info "
                         "WHERE user_id='u-lin-1'").fetchone()
        assert (r["school_id"], r["class_id"]) == ("232", "216"), "边界被一次空登录抹平了"
        assert r["login_count"] == 2


def test_school_placeholder_never_becomes_a_real_school(temp_db):
    """SSO 用 "0" 表示无学校：不能落库成一个真学校（否则教师边界是「本校 0 · 0 人」）。"""
    _upsert_user_info({"userId": "u-zero", "name": "零同学", "roleId": 4,
                       "studentId": "s0", "classId": "0", "schoolId": "0",
                       "collegeId": "0", "majorId": "0.0"})
    with get_conn() as conn:
        r = conn.execute("SELECT school_id, class_id, college_id, major_id "
                         "FROM user_info WHERE user_id='u-zero'").fetchone()
        assert (r["school_id"], r["class_id"]) == ("", "")
        assert (r["college_id"], r["major_id"]) == ("", "")
        # 占位学校定不出边界 → 只能看自己录的（不越权也不静默空列表）
        assert teacher_scope(conn, {"user_id": "u-zero", "role_id": 3})["mode"] == "self"


def test_session_echoes_archival_fields_from_db(client):
    """会话恢复必须回查 user_info 回显学校 / 班级：JWT 载荷里根本没有 school_id。"""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO user_info(user_id,username,name,role_id,student_id,class_id,"
            "school_id,school_name,wallet) VALUES(?,?,?,?,?,?,?,?,?)",
            ("u-sess", "赵佳正", "赵佳正", 4, "19898800030", "216", "232", "天择大学", "w-sess"),
        )
        assert current_identity(conn, {"user_id": "nobody"}) == {}
        assert current_identity(conn, {}) == {}
    tok = create_token({"user_id": "u-sess", "role_id": 4, "wallet": "w-sess",
                        "class_id": "", "user_name": ""})
    r = client.get("/api/auth/session", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active"] is True and body["userId"] == "u-sess"
    # JWT 里 class_id 是空的，回显必须以库为准；学校更是只有库里才有
    assert (body["schoolId"], body["schoolName"]) == ("232", "天择大学")
    assert (body["classId"], body["studentId"]) == ("216", "19898800030")
    assert body["name"] == "赵佳正" and body["roleName"] == "学生"
