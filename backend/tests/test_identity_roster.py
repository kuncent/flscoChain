"""P0-1 / P0-2 / P0-3 / P0-4 + P1-8 / P1-25 / P1-26 / P1-27 回归测试。

覆盖「严重问题清单」的修复点，每条断言都对着事故场景写：
  - P0-1 教师无班级 → 看板恒空：改判为 class_unbound + hint，班级解析链有优先级
  - P0-2 四套钱包口径：候选集含注册别名与真实地址；共享钱包必须显式认领
  - P0-3 报告链上交易恒 0：多地址并集查询去重、排序、分页、异常隔离
  - P0-4 登录落库：_upsert_user_info 不再列数不匹配，班级 "0" 归空且不抹原值
  - P1-8 GET 去副作用：/report/aggregate 不再写成绩表
  - P1-25 草稿分表 + 写保护：教师正式行永不被系统按「教师分=0」重算（84.3→0.6 事故）
  - P1-26 审计归因：新行按 actor_*，存量行退回钱包口径（不动历史分数）
  - P1-27 鉴权与脱敏：两个 eco 只读接口需登录，detail 里的 JWT 入库即打码
附带缺陷（真机验证时发现）：无效 / 过期 JWT 从租户中间件抛出 401，会被
Starlette 当成未捕获异常变成 500 纯文本，一并锁进文末回归。
"""
import json

import pytest

from app.chain_client import ChainClient
from app.db import get_conn, now
from app.roster import (
    HINT_CLASS_UNBOUND,
    bind_teacher_class,
    candidates_for_student,
    norm_class,
    resolve_class_scope,
    roster_students,
    self_student_row,
)
from app.routers.auth import _upsert_user_info
from app.routers.grades import (
    SYSTEM_TEACHER_IDS,
    _apply_draft_to_grades,
    _compute_final,
    _is_teacher_owned,
    _pick_wallet,
    _refresh_draft,
)
from app.routers.report import _actor_scope, _load_eco_brief
from app.wallet_id import is_address, to_address
from app.security import (
    claim_legacy_alias,
    create_token,
    lower_wallet_in,
    owns_wallet,
    redact_secrets,
    register_wallet_aliases,
    resolve_wallet_candidates,
)

ADMIN = {"user_id": "adm", "role_id": 1, "wallet": "adm", "class_id": "", "user_name": "管理员"}
TEACHER = {"user_id": "tzt001", "role_id": 3, "wallet": "tzt001", "class_id": "", "user_name": "张老师"}
STUDENT = {"user_id": "tzs001", "role_id": 4, "wallet": "stu:tzs001", "class_id": "c1", "user_name": "张三"}
OTHER = {"user_id": "tzs002", "role_id": 4, "wallet": "stu:tzs002", "class_id": "c1", "user_name": "李四"}


def _h(payload: dict) -> dict:
    return {"Authorization": f"Bearer {create_token(payload)}"}


# ===========================================================================
# P0-4：登录落库（列数不匹配 + 静默吞异常）
# ===========================================================================
def test_upsert_user_info_inserts_and_normalizes_class(temp_db):
    """首次登录必须真的落一行；SSO 的 "0" 归空，且不把已绑定班级抹掉。"""
    assert _upsert_user_info({"userId": "tzs001", "roleId": 4, "name": "张三",
                              "studentId": "2024001", "classId": "0"}) is True
    with get_conn() as conn:
        r = conn.execute("SELECT * FROM user_info WHERE user_id='tzs001'").fetchone()
        assert r is not None, "P0-4：列数不匹配会让每次登录都插入失败"
        assert norm_class(r["class_id"]) == ""       # "0" 不是班级
        # 钱包列也是资产口径：落库必须是真实链上地址（不再是 user_id / stu: 别名）
        assert is_address(r["wallet"]) and r["wallet"] == to_address("tzs001")
        assert r["login_count"] == 1
        # 班级已绑定后，SSO 再次不返班级 → 沿用库中原值
        conn.execute("UPDATE user_info SET class_id='c1' WHERE user_id='tzs001'")
    _upsert_user_info({"userId": "tzs001", "roleId": 4, "name": "张三", "classId": ""})
    with get_conn() as conn:
        r = conn.execute("SELECT class_id, login_count FROM user_info WHERE user_id='tzs001'").fetchone()
        assert r["class_id"] == "c1"
        assert r["login_count"] == 2


def test_upsert_user_info_registers_aliases(temp_db):
    """登录即登记本人口径别名（内置演示钱包除外）。"""
    _upsert_user_info({"userId": "tzs001", "roleId": 4, "studentId": "2024001", "classId": "c1"})
    with get_conn() as conn:
        aliases = {r[0] for r in conn.execute(
            "SELECT alias FROM wallet_alias WHERE user_id='tzs001'").fetchall()}
    assert {"tzs001", "2024001"} <= aliases


# ===========================================================================
# P0-2：钱包主键统一
# ===========================================================================
def test_register_wallet_aliases_skips_builtin_and_no_overwrite(temp_db):
    with get_conn() as conn:
        register_wallet_aliases(conn, "tzs001", {"tzs001": "user_id",
                                                "stu:tzs001": "student_alias",
                                                "0xlearner": "legacy"})
        owner = conn.execute("SELECT user_id FROM wallet_alias WHERE alias='0xlearner'").fetchone()
        assert owner is None, "内置演示钱包不得被自动归属（否则第一个登录者独占全班数据）"
        register_wallet_aliases(conn, "tzs002", {"0xlearner": "legacy", "stu:tzs001": "student_alias"})
        row = conn.execute("SELECT user_id FROM wallet_alias WHERE alias='stu:tzs001'").fetchone()
        assert row["user_id"] == "tzs001", "自动注册不得改写他人归属"


def test_claim_legacy_alias_overwrites_with_audit(temp_db):
    with get_conn() as conn:
        register_wallet_aliases(conn, "tzs002", {"stu:tzs002": "student_alias"})
        r1 = claim_legacy_alias(conn, "0xlearner", "tzs002", claimed_by="adm")
        assert r1["previous_owner"] == "" and r1["claimed_by"] == "adm"
        r2 = claim_legacy_alias(conn, "0xlearner", "tzs001", claimed_by="adm2")
        assert r2["previous_owner"] == "tzs002"
        assert r2["user_id"] == "tzs001"


def test_candidates_include_claimed_wallet_and_lower_in(temp_db):
    with get_conn() as conn:
        conn.execute("INSERT INTO user_info(user_id, name, role_id, wallet) VALUES('tzs001','张三',4,'stu:tzs001')")
        conn.execute("INSERT INTO user_info(user_id, name, role_id, wallet) VALUES('tzs002','李四',4,'stu:tzs002')")
        register_wallet_aliases(conn, "tzs001", {"tzs001": "user_id", "stu:tzs001": "student_alias"})
        # 未认领：0xlearner 不并入（否则跨账号数据相同）
        assert "0xlearner" not in resolve_wallet_candidates(conn, "stu:tzs001", "tzs001")
        claim_legacy_alias(conn, "0xlearner", "tzs001", "adm")
        cands = resolve_wallet_candidates(conn, "stu:tzs001", "tzs001")
        assert {"stu:tzs001", "tzs001", "0xlearner"} <= set(cands)
        # 他人候选集不受影响
        assert "0xlearner" not in resolve_wallet_candidates(conn, "stu:tzs002", "tzs002")
        h, lp = lower_wallet_in(cands)
        assert len(lp) == len(cands) and h.count("?") == len(lp)


def test_owns_wallet_accepts_any_own_caliber(temp_db):
    with get_conn() as conn:
        conn.execute("INSERT INTO user_info(user_id, name, role_id, wallet) VALUES('tzs001','张三',4,'stu:tzs001')")
        register_wallet_aliases(conn, "tzs001", {"tzs001": "user_id", "stu:tzs001": "student_alias"})
        claim_legacy_alias(conn, "0xlearner", "tzs001", "adm")
    assert owns_wallet(dict(STUDENT), "0xLEARNER") is True   # 大小写不敏感
    assert owns_wallet(dict(STUDENT), "tzs001") is True
    assert owns_wallet(dict(OTHER), "0xlearner") is False    # 已归他人


# ===========================================================================
# P0-1：班级解析链 + 花名册降级
# ===========================================================================
def test_class_scope_priority_chain(temp_db):
    with get_conn() as conn:
        s = resolve_class_scope(conn, dict(TEACHER))
        assert s["class_unbound"] is True and s["hint"] == HINT_CLASS_UNBOUND

        conn.execute(
            "INSERT INTO student_grades(student_id,student_name,course,score,wallet,"
            "teacher_id,teacher_name,class_id,created_at,updated_at) "
            "VALUES('2024001','张三','区块链实训',90,'stu:tzs001','tzt001','张老师','c9',?,?)",
            (now(), now()),
        )
        s = resolve_class_scope(conn, dict(TEACHER))
        assert (s["class_id"], s["class_source"]) == ("c9", "grade_book")

        conn.execute("INSERT INTO user_info(user_id,name,role_id,class_id) VALUES('tzt001','张老师',3,'c8')")
        s = resolve_class_scope(conn, dict(TEACHER))
        assert (s["class_id"], s["class_source"]) == ("c8", "user_info")

        bind_teacher_class(conn, "tzt001", "c7", bound_by="adm")
        s = resolve_class_scope(conn, dict(TEACHER))
        assert (s["class_id"], s["class_source"]) == ("c7", "bind")
        assert s["class_unbound"] is False and s["hint"] == ""

        # 管理员无班级 → 全校视角（不是 class_unbound）
        a = resolve_class_scope(conn, dict(ADMIN))
        assert a["all_classes"] is True and a["class_unbound"] is False


def test_roster_falls_back_to_grade_book(temp_db):
    """user_info 没有学生记录时降级用成绩册派生，并如实标来源（不再恒空）。"""
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO student_grades(student_id,student_name,course,score,wallet,"
            "teacher_id,class_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            [
                ("2024001", "张三", "区块链实训", 88, "stu:tzs001", "tzt001", "c1", now(), "2026-01-01 00:00:00"),
                # 同一钱包、但学号是系统合成的占位值（P0-2：UNIQUE(student_id,course)
                # 允许这种「一人两行」共存）→ 花名册必须收敛成一人一行
                ("Wstu:tzs00", "系统草稿名", "区块链实训", 0, "stu:tzs001", "system", "c1", now(), "2026-09-01 00:00:00"),
                ("2024002", "李四", "区块链实训", 70, "stu:tzs002", "tzt001", "c1", now(), "2026-01-02 00:00:00"),
                ("2024003", "王五", "区块链实训", 60, "stu:tzs003", "tzt001", "c2", now(), "2026-01-02 00:00:00"),
            ],
        )
        rows, src = roster_students(conn, "c1")
        assert src == "grade_book"
        assert [r["student_id"] for r in rows] == ["2024001", "2024002"], "同主体的占位学号行不重复列人"
        assert rows[0]["name"] == "张三", "同一人多口径：教师行的真实姓名优先"
        _, src_empty = roster_students(conn, "c404")
        assert src_empty == "empty"

        # user_info 有学生则为权威花名册
        conn.execute("INSERT INTO user_info(user_id,name,role_id,class_id,student_id) "
                     "VALUES('tzs001','张三',4,'c1','2024001')")
        rows2, src2 = roster_students(conn, "c1")
        assert src2 == "user_info" and rows2[0]["user_id"] == "tzs001"
        # 候选集：花名册行（只有学号）也能扩到本人全部口径
        assert "2024001" in candidates_for_student(conn, rows2[0]) or "tzs001" in candidates_for_student(conn, rows2[0])


def test_self_student_row_from_grades(temp_db):
    """学生未落 user_info（旧库）时，看板仍能从成绩册拼出自己的行。"""
    with get_conn() as conn:
        assert self_student_row(conn, dict(STUDENT)) == {}
        conn.execute(
            "INSERT INTO student_grades(student_id,student_name,course,score,wallet,"
            "teacher_id,class_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            ("2024001", "张三", "区块链实训", 88, "stu:tzs001", "tzt001", "c1", now(), now()),
        )
        me = self_student_row(conn, dict(STUDENT))
        assert me["student_id"] == "2024001" and me["class_id"] == "c1"


def test_bind_class_and_roster_status_api(client, temp_db):
    """教师自助绑定班级后，自检接口立刻从 class_unbound 变为 bind 来源。"""
    r = client.get("/api/auth/roster-status", headers=_h(TEACHER))
    assert r.status_code == 200
    body = r.json()
    assert body["class_unbound"] is True and body["hint"]
    assert body["checks"]["roster_available"] is False

    b = client.post("/api/auth/bind-class", json={"class_id": "c1"}, headers=_h(TEACHER))
    assert b.status_code == 200 and b.json()["class_id"] == "c1", b.text
    # 教师不得代绑他人
    assert client.post("/api/auth/bind-class", json={"class_id": "c2", "teacher_user_id": "tzt002"},
                       headers=_h(TEACHER)).status_code == 403
    # "0" 不是班级
    assert client.post("/api/auth/bind-class", json={"class_id": "0"},
                       headers=_h(TEACHER)).status_code == 400

    a = client.get("/api/auth/roster-status", headers=_h(TEACHER))
    assert a.json()["class_source"] == "bind" and a.json()["class_unbound"] is False

    # 认领接口仅限管理员
    assert client.post("/api/auth/wallet-alias/claim", json={"alias": "0xlearner", "user_id": "tzs001"},
                       headers=_h(TEACHER)).status_code == 403
    conn_err = client.post("/api/auth/wallet-alias/claim",
                           json={"alias": "0xlearner", "user_id": "nobody"}, headers=_h(ADMIN))
    assert conn_err.status_code == 404
    with get_conn() as conn:
        conn.execute("INSERT INTO user_info(user_id,name,role_id) VALUES('tzs001','张三',4)")
    ok = client.post("/api/auth/wallet-alias/claim",
                     json={"alias": "0xlearner", "user_id": "tzs001"}, headers=_h(ADMIN))
    assert ok.status_code == 200 and ok.json()["user_id"] == "tzs001", ok.text


def test_class_students_uses_roster_and_candidates(client, temp_db):
    """看板不再恒空：教师绑班后即使 user_info 为空也由成绩册派生名单。"""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO student_grades(student_id,student_name,course,score,wallet,training_score,"
            "final_score,teacher_id,class_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            ("2024001", "张三", "区块链实训", 88, "stu:tzs001", 70, 80.8, "tzt001", "c1", now(), now()),
        )
        bind_teacher_class(conn, "tzt001", "c1", bound_by="tzt001")
    r = client.get("/api/auth/class-students", headers=_h(TEACHER))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["class_source"] == "bind" and body["roster_source"] == "grade_book"
    assert body["total"] >= 1
    names = [i.get("name") or i.get("student_name") for i in body["items"]]
    assert "张三" in names


# ===========================================================================
# P0-2 / P0-1：成绩册读取口径
# ===========================================================================
def _mk_grade(conn, sid, score, wallet, teacher_id, training=0.0, updated="2026-01-01 00:00:00",
              course="区块链实训", cls="c1"):
    conn.execute(
        "INSERT INTO student_grades(student_id,student_name,course,score,wallet,training_score,"
        "final_score,teacher_id,teacher_name,class_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (sid, f"名_{sid}", course, score, wallet, training,
         _compute_final(training, score), teacher_id, teacher_id, cls, now(), updated),
    )


def test_grades_stats_dedupes_multi_caliber_rows(client, temp_db):
    """同一**人**的教师行 + 系统行（两个不同的学号口径）只能算一个人。"""
    with get_conn() as conn:
        conn.execute("INSERT INTO user_info(user_id,name,role_id,student_id,class_id,wallet) "
                     "VALUES('tzs001','张三',4,'2024001','c1','stu:tzs001')")
        _mk_grade(conn, "2024001", 90, "stu:tzs001", "tzt001", training=72.0, updated="2026-01-01 00:00:00")
        _mk_grade(conn, "tzs001", 0, "0xlearner", "system", training=1.0, updated="2026-09-01 00:00:00")
        _mk_grade(conn, "2024002", 60, "stu:tzs002", "tzt001", training=50.0)
    r = client.get("/api/grades/stats", headers=_h(ADMIN))
    assert r.status_code == 200, r.text
    body = r.json()
    it = body["items"][0]
    assert it["cnt"] == 2 and it["teacher_rows"] == 2
    assert it["avg_manual"] == pytest.approx(75.0)   # (90 + 60) / 2，草稿的 0 分不再拉低
    assert body["duplicate_rows"] == 1 and body["total_rows"] == 3


def test_grades_list_marks_row_kind_and_class_hint(client, temp_db):
    with get_conn() as conn:
        conn.execute("INSERT INTO user_info(user_id,name,role_id,student_id,class_id,wallet) "
                     "VALUES('tzs001','张三',4,'2024001','c1','stu:tzs001')")
        _mk_grade(conn, "2024001", 90, "stu:tzs001", "tzt001", training=72.0)
        _mk_grade(conn, "tzs001", 0, "0xlearner", "system", training=1.0, updated="2026-09-01 00:00:00")
        _mk_grade(conn, "2024099", 55, "stu:tzs999", "tzt999", training=40.0, cls="c2")
    # 未显式绑定班级：经 P0-1 解析链从成绩册派生出本人任教班级，仍然不越权看全校
    body = client.get("/api/grades/list", headers=_h(TEACHER)).json()
    assert body["class_source"] == "grade_book" and body["class_unbound"] is False
    assert body["class_id"] == "c1" and body["total"] == 2
    assert sorted(i["row_kind"] for i in body["items"]) == ["system", "teacher"]
    # 完全无班级线索的教师：不越权看全部，只返回自己录入的行（为空）+ hint
    lonely = {"user_id": "tzt777", "role_id": 3, "wallet": "tzt777", "class_id": "", "user_name": "无班教师"}
    lb = client.get("/api/grades/list", headers=_h(lonely)).json()
    assert lb["class_unbound"] is True and lb["hint"] and lb["items"] == []
    a = client.get("/api/grades/list", headers=_h(ADMIN)).json()
    assert a["class_source"] == "all" and a["total"] == 3


# ===========================================================================
# P1-25：草稿独立 + 教师行写保护
# ===========================================================================
def test_is_teacher_owned_rule(temp_db):
    assert not any(_is_teacher_owned(x) for x in SYSTEM_TEACHER_IDS)
    assert _is_teacher_owned("tzt001") is True


def test_refresh_draft_never_touches_grade_book(client, temp_db):
    with get_conn() as conn:
        conn.execute("INSERT INTO user_info(user_id,name,role_id,student_id,class_id) "
                     "VALUES('tzs001','张三',4,'2024001','c1')")
    r = client.post("/api/grades/draft/refresh", params={"wallet": "stu:tzs001"}, headers=_h(STUDENT))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["student_id"] == "2024001" and body["class_id"] == "c1"
    with get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM student_grades").fetchone()["c"] == 0
        d = conn.execute("SELECT * FROM grade_draft WHERE user_id='tzs001'").fetchone()
        assert d is not None and d["course"] == "区块链实训"
    # 幂等：再刷一次不新增行
    client.post("/api/grades/draft/refresh", params={"wallet": "stu:tzs001"}, headers=_h(STUDENT))
    with get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM grade_draft").fetchone()["c"] == 1


# ===========================================================================
# 真机体验发现（教师线）：草稿身份必须跟着钱包主人走
# ===========================================================================
def test_teacher_proxy_refresh_attributes_draft_to_wallet_owner(client, temp_db):
    """教师代学生刷新草稿：不得把被评价人写成教师自己。

    旧行为下 uid_key = 调用者，落出一条 user_id=教师 / student_name=老师1号 而
    wallet=学生地址的假草稿（真机实测：赵佳正的钱包被登成「老师1号 / tzt001」），
    教师点「全班同步」就会把真实学生的成绩行改名。
    """
    with get_conn() as conn:
        conn.execute("INSERT INTO user_info(user_id,username,name,role_id,student_id,class_id,wallet) "
                     "VALUES('tzs001','19898800030','张三',4,'2024001','c1','stu:tzs001')")
        conn.execute("INSERT INTO user_info(user_id,username,name,role_id,class_id,wallet) "
                     "VALUES('tzt001','tzt001','老师1号',3,'c1','tzt001')")
    r = client.post("/api/grades/draft/refresh", params={"wallet": "stu:tzs001"}, headers=_h(TEACHER))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_id"] == "tzs001", "草稿归属必须是钱包主人（学生）"
    assert body["student_id"] == "2024001" and body["student_name"] == "张三"
    assert body["operator_user_id"] == "tzt001" and body["identity_corrected"] is True
    with get_conn() as conn:
        rows = conn.execute("SELECT user_id, student_name FROM grade_draft").fetchall()
        assert len(rows) == 1 and rows[0]["user_id"] == "tzs001", "不得凭空多出一条教师草稿"


def test_cross_identity_draft_apply_is_rejected(temp_db):
    """历史错配草稿（旧版本产物）同步时必须拒绝，不能改写学生姓名。"""
    with get_conn() as conn:
        conn.execute("INSERT INTO user_info(user_id,username,name,role_id,student_id,class_id,wallet) "
                     "VALUES('tzs001','19898800030','张三',4,'2024001','c1','stu:tzs001')")
        conn.execute("INSERT INTO user_info(user_id,username,name,role_id,class_id,wallet) "
                     "VALUES('tzt001','tzt001','老师1号',3,'c1','tzt001')")
        _mk_grade(conn, "2024001", 90, "stu:tzs001", "tzt001", training=60.0)
        payload = {"user_id": "tzt001", "wallet": "stu:tzs001", "course": "区块链实训",
                   "training_score": 88.0, "training_detail": {}, "class_id": "c1",
                   "school_id": "", "student_id": "tzt001", "student_name": "老师1号", "id": 99}
        res = _apply_draft_to_grades(conn, payload, dict(TEACHER))
        assert res["action"] == "rejected", res
        g = conn.execute("SELECT student_name, score, final_score FROM student_grades").fetchone()
        assert g["student_name"] == "名_2024001", "学生姓名不得被错配草稿改写（_mk_grade 里的原始行名）"
        assert g["student_name"] != "老师1号"
        assert g["score"] == 90 and g["final_score"] == pytest.approx(_compute_final(60.0, 90))


def test_apply_draft_preserves_teacher_score(temp_db):
    """事故回归：草稿盖教师行把综合分算成「教师分=0」（在库副本上实测 84.3 → 0.6）。"""
    with get_conn() as conn:
        _mk_grade(conn, "2024001", 100, "stu:tzs001", "tzt001", training=57.2)
        before = conn.execute("SELECT final_score FROM student_grades").fetchone()["final_score"]
        assert before == pytest.approx(_compute_final(57.2, 100))
        draft = _refresh_draft(conn, "stu:tzs001", "tzs001")
        conn.execute("UPDATE grade_draft SET training_score=30 WHERE id=?", (draft["draft_id"],))
        row = conn.execute("SELECT * FROM grade_draft WHERE id=?", (draft["draft_id"],)).fetchone()
        payload = dict(row)
        payload["training_detail"] = json.loads(payload["training_detail"] or "{}")
        res = _apply_draft_to_grades(conn, payload, dict(TEACHER))
        assert res["action"] == "training_only", res
        after = conn.execute("SELECT score, training_score, final_score, teacher_id "
                             "FROM student_grades").fetchone()
        assert after["score"] == 100, "教师分绝不被系统清零"
        assert after["training_score"] == 30, "实训维度按草稿刷新"
        assert after["final_score"] == pytest.approx(_compute_final(30, 100))
        assert after["teacher_id"] == "tzt001", "归属仍是原教师"


def test_apply_draft_adopts_system_row_and_creates(temp_db):
    with get_conn() as conn:
        _mk_grade(conn, "2024001", 0, "0xlearner", "system", training=1.0)
        payload = {"wallet": "stu:tzs001", "course": "区块链实训", "training_score": 66.0,
                   "training_detail": {}, "class_id": "c1", "school_id": "",
                   "student_id": "2024001", "student_name": "张三", "id": 1}
        res = _apply_draft_to_grades(conn, payload, dict(TEACHER))
        assert res["action"] == "adopted"
        r = conn.execute("SELECT teacher_id, wallet, final_score FROM student_grades").fetchone()
        assert r["teacher_id"] == "tzt001" and r["wallet"] == "stu:tzs001"
        assert r["final_score"] == pytest.approx(_compute_final(66.0, 0))
        # 无行 → 新建（钱包与学号两个口径都对不上任何人）
        payload2 = dict(payload, student_id="2024999", wallet="stu:tzs999")
        res2 = _apply_draft_to_grades(conn, payload2, dict(TEACHER))
        assert res2["action"] == "created"
        assert conn.execute("SELECT COUNT(*) c FROM student_grades").fetchone()["c"] == 2


def test_drafts_list_and_apply_api(client, temp_db):
    with get_conn() as conn:
        bind_teacher_class(conn, "tzt001", "c1", bound_by="tzt001")
        conn.execute("INSERT INTO user_info(user_id,name,role_id,student_id,class_id) "
                     "VALUES('tzs001','张三',4,'2024001','c1')")
        _refresh_draft(conn, "stu:tzs001", "tzs001")
    r = client.get("/api/grades/drafts", headers=_h(TEACHER))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["class_source"] == "" or body["class_id"] == "c1"
    assert body["total"] == 1 and body["items"][0]["target_row_kind"] == "none"
    a = client.post("/api/grades/draft/apply", json={"draft_id": body["items"][0]["id"]},
                    headers=_h(TEACHER))
    assert a.status_code == 200 and a.json()["synced"] == 1, a.text
    assert a.json()["items"][0]["action"] == "created"
    with get_conn() as conn:
        g = conn.execute("SELECT student_id, teacher_id FROM student_grades").fetchone()
        assert (g["student_id"], g["teacher_id"]) == ("2024001", "tzt001")
    # 学生无权访问草稿列表
    assert client.get("/api/grades/drafts", headers=_h(STUDENT)).status_code == 403


def test_my_grades_returns_draft_not_grades(client, temp_db):
    with get_conn() as conn:
        conn.execute("INSERT INTO user_info(user_id,name,role_id,student_id,class_id) "
                     "VALUES('tzs001','张三',4,'2024001','c1')")
        _refresh_draft(conn, "stu:tzs001", "tzs001")
    r = client.get("/api/grades/my", params={"wallet": "stu:tzs001"}, headers=_h(STUDENT))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 0 and body["draft"] and body["draft"]["training_score"] >= 0
    assert "tzs001" in body["wallet_candidates"]


# ===========================================================================
# 学生获取成绩的三段卡点（P1-30 / P2-31 / P2-32，真机走「我的成绩」时发现）
# ===========================================================================
def test_pick_wallet_never_replaces_real_address_with_account_id(temp_db):
    """P2-31：成绩册行的钱包列不得被账号 ID 覆盖（否则无法与链上对账）。"""
    addr, addr2 = to_address("tzs001"), "0x" + "a" * 40   # 第二个是任意合法地址形态
    assert _pick_wallet(addr, "0ae7783d-d59d-40e1-8fcc-001d752ee3fb") == addr
    assert _pick_wallet(addr, "stu:tzs001") == addr
    assert _pick_wallet(addr, "0xlearner") == addr          # 内置演示钱包（既有规则）
    assert _pick_wallet("", addr) == addr
    assert _pick_wallet("0xlearner", "stu:tzs001") == "stu:tzs001"   # 均非真地址时仍收敛
    assert _pick_wallet(addr, addr2) == addr2


def test_draft_wallet_normalized_and_row_keeps_real_address(client, temp_db):
    """P2-31 全链路：前端传登录 user_id，草稿与成绩行都必须落在真实地址上。"""
    addr = to_address("tzs001")
    with get_conn() as conn:
        conn.execute("INSERT INTO user_info(user_id,name,role_id,student_id,class_id,wallet) "
                     "VALUES('tzs001','张三',4,'2024001','c1',?)", (addr,))
        bind_teacher_class(conn, "tzt001", "c1", bound_by="tzt001")
    r = client.post("/api/grades/draft/refresh", params={"wallet": "tzs001"}, headers=_h(STUDENT))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["wallet"] == addr, "草稿入库的钱包必须是可核对的真实链上地址"
    a = client.post("/api/grades/draft/apply", json={"draft_id": body["draft_id"]},
                    headers=_h(TEACHER))
    assert a.status_code == 200, a.text
    with get_conn() as conn:
        g = conn.execute("SELECT wallet, class_id FROM student_grades").fetchone()
        assert g["wallet"] == addr and is_address(g["wallet"])
        assert g["class_id"] == "c1"


def test_orphan_draft_visible_and_stamped_with_teacher_class(client, temp_db):
    """P1-30：无班级草稿不得变成暗数据；采纳时自动归入操作教师的班级。"""
    with get_conn() as conn:
        bind_teacher_class(conn, "tzt001", "c1", bound_by="tzt001")
        # 花名册无该生、成绩册也无行 → 旧版会落进空班级桶，教师按班级永远筛不到
        draft = _refresh_draft(conn, "stu:tzs999", "tzs999")
    assert draft["class_id"] == "" and draft["class_missing"] is True
    body = client.get("/api/grades/drafts", headers=_h(TEACHER)).json()
    assert body["total"] == 1 and body["orphan_total"] == 1, "无班级草稿必须看得见"
    assert body["items"][0]["class_missing"] is True
    a = client.post("/api/grades/draft/apply", json={"draft_id": body["items"][0]["id"]},
                    headers=_h(TEACHER))
    assert a.status_code == 200 and a.json()["synced"] == 1, a.text
    with get_conn() as conn:
        g = conn.execute("SELECT class_id FROM student_grades").fetchone()
        assert g["class_id"] == "c1", "成绩行无班级时在教师列表里不存在，教师分无从录入"


def test_orphan_draft_falls_back_to_token_class_for_owner(client, temp_db):
    """P1-30 回退链：花名册没班级时，本人令牌里的班级快照仍能把草稿归班。"""
    with get_conn() as conn:
        conn.execute("INSERT INTO user_info(user_id,name,role_id,student_id,class_id) "
                     "VALUES('tzs001','张三',4,'2024001','')")
    body = client.post("/api/grades/draft/refresh", params={"wallet": "stu:tzs001"},
                       headers=_h(STUDENT)).json()
    assert body["class_id"] == "c1", "学生令牌带班级（STUDENT.class_id=c1）→ 草稿不再落空桶"
    assert body["class_missing"] is False


def test_my_grades_exposes_draft_sync_state(client, temp_db):
    """P2-32：学生端要能看出草稿是否已被教师同步入册，而不是自己猜。"""
    with get_conn() as conn:
        conn.execute("INSERT INTO user_info(user_id,name,role_id,student_id,class_id) "
                     "VALUES('tzs001','张三',4,'2024001','c1')")
        bind_teacher_class(conn, "tzt001", "c1", bound_by="tzt001")
        draft = _refresh_draft(conn, "stu:tzs001", "tzs001")
    body = client.get("/api/grades/my", params={"wallet": "stu:tzs001"},
                      headers=_h(STUDENT)).json()
    assert body["draft"]["in_grades"] is False
    assert body["draft"]["applied"] is False
    assert body["draft"]["status"] == "pending_teacher"
    client.post("/api/grades/draft/apply", json={"draft_id": draft["draft_id"]},
                headers=_h(TEACHER))
    body2 = client.get("/api/grades/my", params={"wallet": "stu:tzs001"},
                        headers=_h(STUDENT)).json()
    assert body2["draft"]["in_grades"] is True and body2["draft"]["applied"] is True
    assert body2["draft"]["status"] == "synced" and body2["draft"]["grades_row_id"]


# ===========================================================================
# P1-8：GET 不再写成绩
# ===========================================================================
def test_report_aggregate_has_no_grade_side_effect(client, temp_db):
    with get_conn() as conn:
        conn.execute("INSERT INTO user_info(user_id,name,role_id,student_id,class_id) "
                     "VALUES('tzs001','张三',4,'2024001','c1')")
    before = client.get("/api/report/aggregate", params={"wallet": "stu:tzs001"}, headers=_h(STUDENT))
    assert before.status_code == 200, before.text
    assert "identity" in before.json()
    with get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM student_grades").fetchone()["c"] == 0
        assert conn.execute("SELECT COUNT(*) c FROM grade_draft").fetchone()["c"] == 0
    # 学生用自己的已认领口径查自己报告不再 403（P0-2）
    with get_conn() as conn:
        claim_legacy_alias(conn, "0xlearner", "tzs001", "adm")
    r = client.get("/api/report/aggregate", params={"wallet": "0xlearner"}, headers=_h(STUDENT))
    assert r.status_code == 200, r.text
    assert "0xlearner" in r.json()["identity"]["wallet_candidates"]
    assert client.get("/api/report/aggregate", params={"wallet": "stu:tzs002"},
                      headers=_h(STUDENT)).status_code == 403


# ===========================================================================
# P0-3：链上交易多地址并集
# ===========================================================================
def _tx(h, ts, bn=0, frm="0xa"):
    from app.chain_client import Transaction
    return Transaction(hash=h, block_number=bn, from_addr=frm, to_addr="", value="0",
                       input="", output="", status=1, timestamp=ts, contract_address=None,
                       method=None, parsed_args=None)


def _fake_client(mapping):
    """绕开 ABC 实例化，只验基类的多地址归并实现。"""
    inst = ChainClient.__new__(ChainClient)
    def _by_addr(addr, limit=None, offset=0):
        if addr.lower() in mapping.get("__boom__", []):
            raise RuntimeError("单口径查询失败")
        return list(mapping.get(addr.lower(), []))
    inst.list_txs_by_address = _by_addr
    return inst


def test_list_txs_by_addresses_dedup_order_page(temp_db):
    t1, t2, t3 = _tx("0xh1", 100), _tx("0xh2", 300), _tx("0xh3", 200)
    c = _fake_client({"0xa": [t1, t2], "0xb": [t2, t3], "0xc": [t1]})
    got = c.list_txs_by_addresses(["0xa", "0xb", "0xc", "", "0xmissing"], limit=10)
    assert [t.hash for t in got] == ["0xh2", "0xh3", "0xh1"], "按时间降序 + hash 去重"
    assert [t.hash for t in c.list_txs_by_addresses(["0xa", "0xb"], limit=2)] == ["0xh2", "0xh3"]
    assert [t.hash for t in c.list_txs_by_addresses(["0xa", "0xb"], limit=2, offset=2)] == ["0xh1"]
    # 单口径异常不影响其余口径
    c2 = _fake_client({"0xa": [t1], "__boom__": ["0xboom"]})
    assert [t.hash for t in c2.list_txs_by_addresses(["0xboom", "0xa"])] == ["0xh1"]
    # 候选集上限（防止把整班地址都塞进来）
    many = {f"0x{i}": [_tx(f"0xtx{i}", i)] for i in range(12)}
    assert len(_fake_client(many).list_txs_by_addresses(list(many))) == 8


# ===========================================================================
# P1-26 + P1-27：审计归因 / 鉴权 / 脱敏
# ===========================================================================
def test_redact_secrets_covers_jwt_forms():
    raw = ('{"config":{"headers":{"Authorization":"Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9'
           '.eyJ1c2VyX2lkIjoiMTIzIn0.abc-_123"}}}')
    out = redact_secrets(raw)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in out and "***" in out
    # JSON 引号键名形式（前端上报 axios error.config 就是这一形）
    assert '"token": "abcdef"' not in redact_secrets('"token": "abcdef"')
    assert redact_secrets('"tokens": "ok"') == '"tokens": "ok"', "不得误伤非凭据键名"


def test_actor_scope_sql(temp_db):
    sql, params = _actor_scope(["tzs001", "0xlearner"], "tzs001")
    assert "actor_wallet" in sql and "actor_user_id" in sql and sql.count("IN (") == 2
    # 候选集两遍（actor_wallet + 存量行退回钱包）+ actor_user_id 本身 = 3 次
    assert params.count("tzs001") == 3 and params.count("0xlearner") == 2
    assert _actor_scope([], "") == ("", [])


def test_legacy_logs_keep_wallet_attribution_new_rows_use_actor(temp_db):
    """存量行退回钱包口径（历史分数不动）；新行按操作人归因（别人的失误不扣我分）。"""
    W = "stu:tzs001"
    with get_conn() as conn:
        # 存量行：actor 两列皆空，wallet = 本人
        conn.execute(
            "INSERT INTO eco_operation_logs(wallet,module,action,level,message,detail,created_at)"
            "VALUES(?,?,?,?,?,?,?)", (W, "energy", "issue", "error", "老数据", "", now()))
        # 新行：操作人是本人
        conn.execute(
            "INSERT INTO eco_operation_logs(wallet,module,action,level,message,detail,created_at,"
            "actor_wallet,actor_user_id) VALUES(?,?,?,?,?,?,?,?,?)",
            (W, "energy", "issue", "error", "本人", "", now(), W, "tzs001"))
        # 新行：操作人是他人（wallet 列却是本人 —— 行政角色给本人发能量的失败尝试）
        conn.execute(
            "INSERT INTO eco_operation_logs(wallet,module,action,level,message,detail,created_at,"
            "actor_wallet,actor_user_id) VALUES(?,?,?,?,?,?,?,?,?)",
            (W, "energy", "issue", "error", "他人", "", now(), "0xadmin", "adm"))
    eco = _load_eco_brief(W, user_id="tzs001", candidates=[W, "tzs001"])
    assert eco["logs"]["error_count"] == 2
    assert eco["logs"]["total"] >= 2
    assert len(eco["logs"]["recent_issues"]) == 2 or len(eco["logs"]["recent_issues"]) >= 1


def test_record_error_writes_actor_and_redacts(client, temp_db):
    jwt_like = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiemhhIn0.sig123"
    r = client.post("/api/eco/errors/record", headers=_h(STUDENT), json={
        "wallet": "stu:tzs001", "module": "energy", "action": "issue", "level": "error",
        "message": "失败 " + jwt_like, "detail": json.dumps({"err": jwt_like}),
    })
    assert r.status_code == 200, r.text
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM eco_operation_logs WHERE id=?", (r.json()["id"],)).fetchone()
    assert row["actor_user_id"] == "tzs001"
    # actor_wallet 存**真实地址**（传入的 stu: 别名在写侧已归一）
    assert row["actor_wallet"] == to_address("stu:tzs001")
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in (row["detail"] + row["message"])


def test_errors_list_and_wallet_profile_require_login(client, temp_db):
    assert client.get("/api/eco/errors/list").status_code == 401
    assert client.get("/api/eco/wallet/stu:tzs001").status_code == 401
    with get_conn() as conn:
        conn.execute("INSERT INTO user_info(user_id,name,role_id,wallet) VALUES('tzs001','张三',4,'stu:tzs001')")
        conn.execute("INSERT INTO user_info(user_id,name,role_id,wallet) VALUES('tzs002','李四',4,'stu:tzs002')")
        conn.execute("INSERT INTO eco_certificates(token_id,species_id,species_name,owner,"
                     "cost_energy,contract_address,tx_hash,cert_no,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                     ("1", 1, "树", "stu:tzs001", 100, "0xc", "0xt", "C1", now()))
    mine = client.get("/api/eco/wallet/stu:tzs001", headers=_h(STUDENT))
    assert mine.status_code == 200 and len(mine.json()["certificates"]) == 1
    assert client.get("/api/eco/wallet/stu:tzs002", headers=_h(STUDENT)).status_code == 403
    assert client.get("/api/eco/errors/list", params={"wallet": "stu:tzs002"},
                      headers=_h(STUDENT)).status_code == 403
    # 联盟角色钱包（学生正在扮演的教学操作身份）不得被个资校验拦掉：
    # 与写侧 assert_actor_wallet 同口径，否则 P1-27 会顺手把实战页改 403
    assert client.get("/api/eco/wallet/0xmetro", headers=_h(STUDENT)).status_code == 200
    assert client.get("/api/eco/errors/list", params={"wallet": "0xmetro"},
                      headers=_h(STUDENT)).status_code == 200
    # 教师 / 管理员可看任意人
    assert client.get("/api/eco/wallet/stu:tzs001", headers=_h(TEACHER)).status_code == 200
    lst = client.get("/api/eco/errors/list", headers=_h(ADMIN))
    assert lst.status_code == 200 and "items" in lst.json()


def test_eco_logs_legacy_migration_on_old_db(tmp_path, monkeypatch):
    """旧库（无 actor 列）跑 init_eco_db：补列 + 存量 JWT 清洗，且不改历史归因口径。"""
    from app.config import settings
    from app.routers.eco import init_eco_db

    db_file = tmp_path / "legacy.sqlite3"
    monkeypatch.setattr(settings, "db_path", db_file)
    import sqlite3
    c = sqlite3.connect(str(db_file))
    c.execute("""CREATE TABLE eco_operation_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, wallet TEXT NOT NULL, module TEXT NOT NULL,
        action TEXT NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL, detail TEXT,
        created_at TEXT NOT NULL)""")
    c.execute("INSERT INTO eco_operation_logs(wallet,module,action,level,message,detail,created_at)"
              " VALUES('0xlearner','other','a','error','带 token: Bearer eyJhbGciOi.eyJh.b',"
              "'{\"authorization\": \"Bearer eyJhbGciOi.eyJh.b\"}', '2026-01-01 00:00:00')")
    c.commit()
    c.close()

    init_eco_db()
    with get_conn() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(eco_operation_logs)").fetchall()}
        assert {"actor_wallet", "actor_user_id"} <= cols
        row = conn.execute("SELECT detail, message, actor_wallet FROM eco_operation_logs").fetchone()
        assert "eyJhbGciOi" not in row["detail"] and "eyJhbGciOi" not in row["message"]
        assert row["actor_wallet"] == "", "存量行不回填：保持钱包口径，历史分数不动"
    # 幂等重入
    init_eco_db()


# ===========================================================================
# P0-2 一次性归并脚本：改写必须保守（在真实库副本上演练时抓出的风险）
# ===========================================================================
def _load_identity_script():
    """按路径加载 scripts/normalize_identity.py（不属于包，是一次性运维脚本）。"""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "normalize_identity.py"
    assert path.exists(), f"归并脚本不存在: {path}"
    spec = importlib.util.spec_from_file_location("normalize_identity", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_is_placeholder_student_id_rule():
    """占位学号判定只看一个口径，且「无从对照钱包」时一律保守判否。"""
    from app.roster import _is_placeholder_sid
    from app.routers.grades import _is_synthetic_sid
    from app.security import is_placeholder_student_id

    assert is_placeholder_student_id("W0xlearner", "0xlearner")
    assert is_placeholder_student_id("Wstu:0ae778", "stu:0ae7783d-d59d")
    assert is_placeholder_student_id("W0ae7783d-d", "0ae7783d-d59d-40e1")
    assert not is_placeholder_student_id("19898800030", "0xlearner")
    # 真实学号也可能以 W 开头：没有钱包可对照时不得判为垃圾（否则会被改写掉）
    assert not is_placeholder_student_id("W2024001", "")
    assert not is_placeholder_student_id("", "0xlearner")
    # 旧的两处本地实现已收敛到同一函数（不再各自“取前 10 位”）
    assert _is_placeholder_sid("W0xlearner", "0xlearner")
    assert _is_synthetic_sid("Wstu:0ae778", "stu:0ae7783d-d59d")
    assert not _is_synthetic_sid("W2024001", "")


def test_normalize_identity_merge_keeps_real_student_id(temp_db):
    """认领共享钱包后归并重复行，但教师行里的真实 SSO 学号一字不改。"""
    script = _load_identity_script()

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO student_grades(student_id,student_name,course,class_id,wallet,score,"
            "teacher_id,training_score,final_score,created_at,updated_at)"
            " VALUES('19898800030','实训学生','区块链实训','班级1','0xlearner',85.0,"
            "'tzt001',88.8,84.3,?,?)", (now(), now()))
        conn.execute(
            "INSERT INTO student_grades(student_id,student_name,course,wallet,score,teacher_id,"
            "training_score,final_score,created_at,updated_at)"
            " VALUES('W0xlearner','学生_0xlear','区块链实训','0xlearner',0.0,"
            "'system',88.8,53.3,?,?)", (now(), now()))
        keeper_id = conn.execute(
            "SELECT id FROM student_grades WHERE teacher_id='tzt001'").fetchone()["id"]
        claim_legacy_alias(conn, "0xlearner", "tzs001", "admin001")

        # 0) dry-run 不得动任何数据
        st0 = script.step_merge_grades(conn, apply_changes=False)
        assert st0["merged"] == 1, "dry-run 也要把计划报出来"
        assert conn.execute("SELECT COUNT(*) AS n FROM student_grades").fetchone()["n"] == 2
        assert conn.execute("SELECT COUNT(*) AS n FROM grade_merge_archive").fetchone()["n"] == 0

        # 1) 真实执行：下线重复行，教师行学号与综合分保持原样
        st = script.step_merge_grades(conn, apply_changes=True)
        assert st["merged"] == 1 and st["rewritten"] == 0 and st["conflicts"] == 0
        rows = conn.execute(
            "SELECT student_id, teacher_id, final_score, class_id FROM student_grades").fetchall()
        assert [(r["student_id"], r["teacher_id"], r["final_score"], r["class_id"])
                for r in rows] == [("19898800030", "tzt001", 84.3, "班级1")], \
            "保留教师行，学号 / 班级 / 综合分一字不改"

        # 2) 被下线的行整行原文入档，可从归档直接恢复
        arc = conn.execute(
            "SELECT grade_id, merged_into, payload FROM grade_merge_archive").fetchall()
        assert len(arc) == 1
        assert arc[0]["merged_into"] == keeper_id
        assert json.loads(arc[0]["payload"])["student_id"] == "W0xlearner"

        # 3) 再跑一轮应无可归并（幂等）
        assert script.step_merge_grades(conn, apply_changes=True)["merged"] == 0


def test_normalize_identity_apply_authoritative_student_id(temp_db):
    """user_info 有权威学号时，造主键行必须收敛到真实学号与班级。"""
    script = _load_identity_script()

    with get_conn() as conn:
        conn.execute("INSERT INTO user_info(user_id,name,role_id,wallet,student_id,class_id)"
                     " VALUES('tzs001','张三',4,'stu:tzs001','2024001','c1')")
        conn.execute(
            "INSERT INTO student_grades(student_id,student_name,course,wallet,score,teacher_id,"
            "training_score,final_score,created_at,updated_at)"
            " VALUES('W0xlearner','张三','区块链实训','tzs001',0.0,'system',60,36,"
            "'2026-01-01 00:00:00','2026-01-01 00:00:00')")
        conn.execute(
            "INSERT INTO student_grades(student_id,student_name,course,wallet,score,teacher_id,"
            "training_score,final_score,created_at,updated_at)"
            " VALUES('tzs001','张三','区块链实训','stu:tzs001',0.0,'system',70,42,"
            "'2026-02-01 00:00:00','2026-02-01 00:00:00')")

        st = script.step_merge_grades(conn, apply_changes=True)
        assert st["merged"] == 1 and st["rewritten"] == 1
        r = conn.execute(
            "SELECT student_id, class_id, wallet FROM student_grades").fetchone()
        assert r["student_id"] == "2024001" and r["class_id"] == "c1", \
            "有权威花名册时以花名册为准"
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM grade_merge_archive").fetchone()["n"] == 1


# ===========================================================================
# 附带缺陷：带无效 / 过期 JWT 的请求不得返回 500 纯文本
# 租户中间件在 ExceptionMiddleware 之外，从它里面抛 HTTPException 会被当成
# 未捕获异常：客户端拿到 500 text/plain，前端只有 401 才跳登录页，
# 于是 JWT 过期后用户永久卡在报错页，无法自助重新登录。
# ===========================================================================
def test_invalid_bearer_token_returns_401_json_not_500(client, temp_db):
    r = client.get("/api/grades/stats", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401, f"应为 401，实际 {r.status_code}：{r.text[:120]!r}"
    assert r.headers["content-type"].startswith("application/json"), r.text[:120]
    assert r.json()["detail"]


def test_expired_bearer_token_keeps_precise_401_detail(client, temp_db):
    """过期与「伪造」都要 401，但过期要给出可引导重新登录的精确文案。"""
    expired = create_token(
        {"user_id": "tzs001", "role_id": 4, "wallet": "stu:tzs001"},
        expires_seconds=-10,
    )
    r = client.get("/api/auth/roster-status",
                   headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401, f"实际 {r.status_code}：{r.text[:120]!r}"
    assert "过期" in r.json()["detail"]


def test_session_probe_reports_inactive_not_500(client, temp_db):
    """/auth/session 是「探测」接口语义：坏 token 必须 200 + active=false。"""
    r = client.get("/api/auth/session", headers={"Authorization": "Bearer bad.token.x"})
    assert r.status_code == 200, f"实际 {r.status_code}：{r.text[:120]!r}"
    assert r.json()["active"] is False
