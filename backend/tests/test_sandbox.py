"""任务 #22：运营沙盘测试（场景鉴权 / 轮次启停 / 处置动作 / KPI / 负载线程停止）。

依赖 conftest 的 temp_db + client fixture（CHAIN_MODE=mock 隔离库）。
身份经 security.create_token 签发真实 JWT，走 Authorization: Bearer 全链路。
"""
import json
import time

from app import db as appdb
from app.routers import sandbox
from app.security import create_token

TEACHER = {"user_id": "t1", "role_id": 3, "wallet": "t1", "class_id": "c1", "user_name": "王老师"}
TEACHER2 = {"user_id": "t2", "role_id": 3, "wallet": "t2", "class_id": "c2", "user_name": "李老师"}
STUDENT = {"user_id": "s1", "role_id": 4, "wallet": "s1", "class_id": "c1", "user_name": "小明"}
STUDENT2 = {"user_id": "s2", "role_id": 4, "wallet": "s2", "class_id": "c2", "user_name": "小红"}


def _h(payload: dict) -> dict:
    return {"Authorization": f"Bearer {create_token(payload)}"}


def _mk_scenario(client, stype="replay_attack", **cfg) -> int:
    body = {"scenario_type": stype, "title": f"{stype} 演练",
            "target_tps": cfg.pop("target_tps", 1.0),
            "duration_s": cfg.pop("duration_s", 60),
            "quota": cfg.pop("quota", 100), **cfg}
    r = client.post("/api/sandbox/scenarios", json=body, headers=_h(TEACHER))
    assert r.status_code == 200, r.text
    return int(r.json()["id"])


def _start(client, sid: int) -> dict:
    r = client.post("/api/sandbox/rounds/start", json={"scenario_id": sid}, headers=_h(TEACHER))
    assert r.status_code == 200, r.text
    return r.json()


def _stop(client, rid: int) -> dict:
    r = client.post(f"/api/sandbox/rounds/{rid}/stop", headers=_h(TEACHER))
    assert r.status_code == 200, r.text
    return r.json()


# ===========================================================================
# 场景创建：鉴权与参数钳制
# ===========================================================================
def test_scenario_create_auth(client):
    body = {"scenario_type": "node_down"}
    assert client.post("/api/sandbox/scenarios", json=body).status_code == 401          # 未登录
    assert client.post("/api/sandbox/scenarios", json=body, headers=_h(STUDENT)).status_code == 403  # 学生禁止
    r = client.post("/api/sandbox/scenarios", json=body, headers=_h(TEACHER))
    assert r.status_code == 200
    assert r.json()["class_id"] == "c1"


def test_scenario_type_validation_and_clamp(client):
    r = client.post("/api/sandbox/scenarios", json={"scenario_type": "not_exist"}, headers=_h(TEACHER))
    assert r.status_code == 422
    for st in ("node_down", "consensus_stall", "replay_attack", "gas_spike"):
        assert client.post("/api/sandbox/scenarios", json={"scenario_type": st},
                           headers=_h(TEACHER)).status_code == 200
    # 限额钳制：目标 TPS / 时长 / 配额不得超过安全红线
    r = client.post("/api/sandbox/scenarios",
                    json={"scenario_type": "gas_spike", "target_tps": 99,
                          "duration_s": 99999, "quota": 99999}, headers=_h(TEACHER))
    cfg = r.json()["config"]
    assert cfg["target_tps"] <= sandbox.MAX_TARGET_TPS
    assert cfg["duration_s"] <= sandbox.MAX_DURATION_S
    assert cfg["quota"] <= sandbox.MAX_QUOTA


# ===========================================================================
# 轮次启停 + 负载线程可靠退出
# ===========================================================================
def test_round_start_stop_and_thread_exit(client):
    sid = _mk_scenario(client, "replay_attack", duration_s=60, quota=50)
    started = _start(client, sid)
    rid = started["round_id"]
    rt = sandbox.get_runtime(rid)
    assert rt is not None and rid in sandbox.live_round_ids()

    # 学生端可见本班进行中轮次
    ra = client.get("/api/sandbox/rounds/active", headers=_h(STUDENT)).json()
    assert ra["round"]["id"] == rid and ra["round"]["scenario_type"] == "replay_attack"

    # 停止：接口返回后线程必须已退出（3s 红线）
    t0 = time.time()
    res = _stop(client, rid)
    assert res["status"] == "stopped"
    assert time.time() - t0 <= 3.5
    assert not rt.thread.is_alive()
    assert rid not in sandbox.live_round_ids()

    # 台账落库：stopped + result 含 KPI 汇总
    with appdb.get_conn() as conn:
        row = conn.execute("SELECT * FROM ops_rounds WHERE id=?", (rid,)).fetchone()
    assert row["status"] == "stopped" and row["finished_at"]
    result = json.loads(row["result"])
    assert result["stop_reason"] == "teacher_stopped" and "kpis" in result

    # 幂等：再次停止不报错
    assert client.post(f"/api/sandbox/rounds/{rid}/stop", headers=_h(TEACHER)).status_code == 200


def test_only_one_running_round_per_class(client):
    sid1 = _mk_scenario(client, "node_down")
    sid2 = _mk_scenario(client, "gas_spike")
    rid = _start(client, sid1)["round_id"]
    try:
        r = client.post("/api/sandbox/rounds/start", json={"scenario_id": sid2}, headers=_h(TEACHER))
        assert r.status_code == 409
    finally:
        _stop(client, rid)


def test_cross_class_isolation(client):
    sid = _mk_scenario(client, "node_down")
    rid = _start(client, sid)["round_id"]
    try:
        # 他班学生：看不到活跃轮次 / 禁止提交动作；他班教师：禁止停止
        assert client.get("/api/sandbox/rounds/active", headers=_h(STUDENT2)).json()["round"] is None
        r = client.post(f"/api/sandbox/rounds/{rid}/action",
                        json={"action_type": "restart_node"}, headers=_h(STUDENT2))
        assert r.status_code == 403
        assert client.post(f"/api/sandbox/rounds/{rid}/stop", headers=_h(TEACHER2)).status_code == 403
    finally:
        _stop(client, rid)


# ===========================================================================
# 故障注入：重放记录 / 共识停滞 / 配额自动停止
# ===========================================================================
def test_replay_attack_injects_duplicate_proof_no(client):
    sid = _mk_scenario(client, "replay_attack")
    rid = _start(client, sid)["round_id"]
    try:
        with appdb.get_conn() as conn:
            rows = conn.execute(
                "SELECT proof_no, role_key, proof_payload FROM eco_energy_records "
                "WHERE action LIKE '%重放注入%' ORDER BY id").fetchall()
        assert len(rows) == 2
        assert rows[0]["proof_no"] == rows[1]["proof_no"] != ""
        assert rows[0]["role_key"] != rows[1]["role_key"]  # 同单号跨角色重复提交（审计检出形态）
        assert json.loads(rows[0]["proof_payload"])["suspicious"] is True
    finally:
        _stop(client, rid)


def test_consensus_stall_pauses_load(client):
    sid = _mk_scenario(client, "consensus_stall", target_tps=5.0, quota=200)
    rid = _start(client, sid)["round_id"]
    rt = sandbox.get_runtime(rid)
    try:
        time.sleep(0.8)
        assert rt.attempted == 0  # 出块暂停期间负载生成器不注入
        st = client.get("/api/sandbox/nodes", headers=_h(STUDENT)).json()
        assert st["consensus_stalled"] is True
    finally:
        _stop(client, rid)
    assert client.get("/api/sandbox/nodes", headers=_h(STUDENT)).json()["consensus_stalled"] is False


def test_node_down_marks_offline(client):
    sid = _mk_scenario(client, "node_down", node_index=2)
    rid = _start(client, sid)["round_id"]
    try:
        st = client.get("/api/sandbox/nodes", headers=_h(STUDENT)).json()
        assert st["node_fault"]["offline"] is True and st["node_fault"]["node_index"] == 2
    finally:
        _stop(client, rid)
    assert client.get("/api/sandbox/nodes", headers=_h(STUDENT)).json()["node_fault"] is None


def test_quota_auto_stops_round_and_thread(client):
    sid = _mk_scenario(client, "gas_spike", target_tps=5.0, quota=3, duration_s=60)
    rid = _start(client, sid)["round_id"]
    deadline = time.time() + 10
    while time.time() < deadline and rid in sandbox.live_round_ids():
        time.sleep(0.2)
    assert rid not in sandbox.live_round_ids()  # 配额耗尽：线程自行退出
    with appdb.get_conn() as conn:
        row = conn.execute("SELECT status, result FROM ops_rounds WHERE id=?", (rid,)).fetchone()
    assert row["status"] == "stopped"
    assert json.loads(row["result"])["stop_reason"] == "duration_or_quota"


# ===========================================================================
# 处置动作 + KPI 计算与事件发布
# ===========================================================================
def test_action_and_kpi_flow(client, monkeypatch):
    monkeypatch.setattr(sandbox, "KPI_INTERVAL_SECONDS", 0.4)
    sid = _mk_scenario(client, "node_down", target_tps=1.0, quota=100)
    rid = _start(client, sid)["round_id"]
    try:
        # 非法 action_type -> 422
        r = client.post(f"/api/sandbox/rounds/{rid}/action",
                        json={"action_type": "hack_back"}, headers=_h(STUDENT))
        assert r.status_code == 422
        # 对症处置：重启节点
        time.sleep(0.5)
        r = client.post(f"/api/sandbox/rounds/{rid}/action",
                        json={"action_type": "restart_node", "description": "node2 拉起"},
                        headers=_h(STUDENT))
        assert r.status_code == 200
        kpis = r.json()["kpis"]
        assert kpis["mttd_seconds"] > 0 and kpis["mttr_seconds"] > 0
        assert kpis["handle_rate"] == 100.0

        # 等待至少一个 KPI 采样周期：落库 + 事件镜像（notifications）
        time.sleep(1.0)
        with appdb.get_conn() as conn:
            krow = conn.execute(
                "SELECT value FROM ops_kpis WHERE round_id=? AND metric='mttd_seconds' "
                "ORDER BY id DESC LIMIT 1", (rid,)).fetchone()
            assert krow is not None and krow["value"] > 0
            arow = conn.execute(
                "SELECT detail FROM ops_kpis WHERE round_id=? AND metric='action'",
                (rid,)).fetchone()
            assert json.loads(arow["detail"])["action_type"] == "restart_node"
            ev = conn.execute(
                "SELECT payload FROM notifications WHERE event_type='sandbox_kpi' "
                "AND class_id='c1' ORDER BY id DESC LIMIT 1").fetchone()
            assert ev is not None
            assert json.loads(ev["payload"])["round_id"] == rid

        # 教师端 KPI 明细
        r = client.get(f"/api/sandbox/rounds/{rid}/kpis", headers=_h(TEACHER))
        assert r.status_code == 200 and r.json()["latest"]["handle_rate"]["value"] == 100.0
    finally:
        _stop(client, rid)

    # 结束后动作提交被拒（409）
    assert client.post(f"/api/sandbox/rounds/{rid}/action",
                       json={"action_type": "restart_node"},
                       headers=_h(STUDENT)).status_code == 409


def test_mttr_pending_without_resolution_action(client, monkeypatch):
    """未提交对症动作时：有 MTTD 无 MTTR，处置率 < 100。"""
    monkeypatch.setattr(sandbox, "KPI_INTERVAL_SECONDS", 0.4)
    sid = _mk_scenario(client, "replay_attack")
    rid = _start(client, sid)["round_id"]
    try:
        # audit_replay 才是对症动作；fix_redeploy 仅计 MTTD
        client.post(f"/api/sandbox/rounds/{rid}/action",
                    json={"action_type": "fix_redeploy"}, headers=_h(STUDENT))
        rt = sandbox.get_runtime(rid)
        kpis = sandbox.compute_kpis(rt)
        assert kpis["mttd_seconds"] > 0
        assert kpis["mttr_seconds"] == -1.0
        assert kpis["handle_rate"] == 0.0
    finally:
        _stop(client, rid)


# ===========================================================================
# P1-29：教师令牌无班级 → 回退「班级解析链」
# ===========================================================================
def test_teacher_token_without_class_falls_back_to_binding(client):
    """令牌 class_id 为空不得把轮次写进「空班级桶」，须按绑定班级落地让学生看得见。"""
    from app.db import get_conn
    from app.roster import bind_teacher_class

    ghost = {"user_id": "t9", "role_id": 3, "wallet": "t9", "class_id": "", "user_name": "空令牌老师"}
    unbound = {"user_id": "t8", "role_id": 3, "wallet": "t8", "class_id": "", "user_name": "未绑班老师"}
    with get_conn() as conn:
        bind_teacher_class(conn, "t9", "c1", bound_by="adm")

    r = client.post("/api/sandbox/scenarios", json={"scenario_type": "node_down"},
                    headers=_h(ghost))
    assert r.status_code == 200, r.text
    assert r.json()["class_id"] == "c1", "P1-29：空令牌须回退解析链（绑定优先）"
    rid = 0
    try:
        started = client.post("/api/sandbox/rounds/start",
                              json={"scenario_id": int(r.json()["id"])}, headers=_h(ghost))
        assert started.status_code == 200, started.text
        rid = int(started.json()["round_id"])
        act = client.get("/api/sandbox/rounds/active", headers=_h(STUDENT))
        assert act.status_code == 200 and act.json()["round"], "本班学生须看到进行中的轮次"
        assert int(act.json()["round"]["id"]) == rid
        # 未绑定任何班级的教师仍为空班级（不得凭空拿到别人的班）
        r2 = client.post("/api/sandbox/scenarios", json={"scenario_type": "node_down"},
                         headers=_h(unbound))
        assert r2.status_code == 200 and r2.json()["class_id"] == ""
    finally:
        if rid:
            assert client.post(f"/api/sandbox/rounds/{rid}/stop",
                               headers=_h(ghost)).status_code == 200


# ===========================================================================
# 合成负载的收款方判据（真机回归：沙盘 KPI「交易成功率」曾恒 0%）
# ===========================================================================
def test_resolve_peer_keeps_real_address_and_resolves_alias():
    """0x 开头的内置别名不是地址：必须解析为真址，否则每笔合成转账直接报错。"""
    from app import chain_client as cc
    from app import keystore as ks
    from app import wallet_id as wid

    mapped = "0x" + "cd" * 20

    class _Fake:
        def resolve_account(self, alias):
            return mapped

    real = "0x" + "1a" * 20
    assert cc.resolve_peer(_Fake(), real) == real, "真实地址须原样透传"
    assert cc.resolve_peer(_Fake(), "") == "", "合约部署交易无收款方，不得去解析空值"
    # 前提：密钥库内置别名按地址判据确实不成立（旧代码错就错在只看 0x 前缀）
    assert not any(wid.is_address(a) for a in ks.DEMO_ALIASES)
    for alias in ks.DEMO_ALIASES:
        assert cc.resolve_peer(_Fake(), alias) == mapped, f"{alias} 须走别名解析"


def test_sandbox_load_injection_counts_success(client):
    """负载注入必须真正计入成功数（地址解析回退时只能记 0，成功率永远为空）。"""
    sid = _mk_scenario(client, "node_down", target_tps=2.0, quota=5)
    rid = _start(client, sid)["round_id"]
    rt = sandbox.get_runtime(rid)
    try:
        deadline = time.time() + 8
        while time.time() < deadline and rt.attempted < 2:
            time.sleep(0.2)
        assert rt.attempted >= 2, "负载线程未注入合成交易"
        assert rt.succeeded == rt.attempted, (
            f"合成交易失败 {rt.attempted - rt.succeeded} 笔：对手方地址解析回归")
    finally:
        _stop(client, rid)
