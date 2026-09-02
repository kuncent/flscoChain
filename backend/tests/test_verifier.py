"""verifier 五级流水线 + notify SSE/历史端点测试。

覆盖：五级门控（失败→后续 skipped）、task_runs 落库（成功/失败都写）、
记录模式（finalize_run / record_failure）、SSE 401 鉴权（无 token / 无效 /
过期 token），以及直调 /stream 端点验证帧格式 / 事件投递 / 断开清理订阅
（starlette TestClient 不支持无限流式响应，故直接驱动
StreamingResponse.body_iterator）、/history scope 与分页、能量发放并发占位防双铸。
"""
import asyncio
import json
import threading
import time

from app import events_bus, verifier
from app.db import get_conn
from app.routers.notify import stream as notify_stream
from app.security import create_token

UC = {"user_id": "u1", "wallet": "0xlearner", "class_id": "c1",
      "tenant_id": "", "role_id": 1}


def _token(**kw) -> str:
    base = {"user_id": "u1", "role_id": 1, "wallet": "0xlearner",
            "class_id": "c1", "user_name": "tester"}
    base.update(kw)
    return create_token(base)


class TestRunPipeline:
    def test_all_stages_pass_success(self, temp_db):
        pr = verifier.run_pipeline(
            "deploy", {"name": "T"}, UC,
            compile_fn=lambda ctx: (True, "compile ok", {"abi": []}),
            semantic_fn=lambda ctx: (True, "semantic ok"),
            business_fns=[("wallet_whitelist", lambda ctx: (True, "wl ok"))],
            onchain_fn=lambda ctx: (True, "deployed", {"tx_hash": "0x1"}),
        )
        assert pr.ok and pr.status == "success"
        assert [s["stage"] for s in pr.stages] == list(verifier.STAGES)
        assert all(s["ok"] for s in pr.stages)
        assert pr.pipeline["run_id"] == pr.run_id
        # task_runs 落库（成功）
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM task_runs WHERE task_type='deploy'").fetchone()
        assert row is not None
        assert row["status"] == "success"
        assert row["user_id"] == "u1" and row["wallet"] == "0xlearner"
        assert row["class_id"] == "c1"

    def test_stage_failure_gates_following(self, temp_db):
        """L1 失败 → L2/L3/L4 门控 skipped，L5 仍附加；失败也落库。"""
        pr = verifier.run_pipeline(
            "compile", {"source": "bad"}, UC,
            compile_fn=lambda ctx: (False, "compile error"),
            semantic_fn=lambda ctx: (True, "should not run"),
            business_fns=[("x", lambda ctx: (True, "should not run"))],
            onchain_fn=lambda ctx: (True, "should not run"),
        )
        assert not pr.ok and pr.status == "failed"
        by = {s["stage"]: s for s in pr.stages}
        assert by["compile"]["ok"] is False
        assert by["semantic"]["skipped"] and by["business"]["skipped"]
        assert by["onchain"]["skipped"]
        assert by["scoring"]["ok"] is True  # L5 始终附加，不影响门控
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM task_runs WHERE task_type='compile'").fetchone()
        assert row is not None and row["status"] == "failed"

    def test_business_any_rule_fail_then_fail(self, temp_db):
        """L3 多条业务规则：任一失败 → 该级失败并门控后续。"""
        pr = verifier.run_pipeline(
            "deploy", {}, UC,
            compile_fn=lambda ctx: (True, "ok"),
            business_fns=[
                ("proof_no_replay", lambda ctx: (True, "no replay")),
                ("role_perm", lambda ctx: (False, "no permission")),
            ],
            onchain_fn=lambda ctx: (True, "should not run"),
        )
        assert not pr.ok
        by = {s["stage"]: s for s in pr.stages}
        assert by["business"]["ok"] is False
        assert "role_perm" in by["business"]["detail"]
        assert by["onchain"]["skipped"]

    def test_none_stage_marked_skipped_ok(self, temp_db):
        """不适用级（传 None）→ skipped 且 ok=True，不算失败。"""
        pr = verifier.run_pipeline("compile", {}, UC)  # 全 None
        assert pr.ok and pr.status == "success"
        assert all(s["skipped"] for s in pr.stages if s["stage"] != "scoring")

    def test_onchain_exception_recorded_not_raised(self, temp_db):
        """L4 抛异常 → 不外抛，记入 onchain_error 供调用方还原错误响应。"""
        def boom(ctx):
            raise RuntimeError("chain down")

        pr = verifier.run_pipeline(
            "deploy", {}, UC,
            compile_fn=lambda ctx: (True, "ok"),
            onchain_fn=boom,
        )
        assert not pr.ok
        assert pr.onchain_error and "chain down" in pr.onchain_error


class TestRecordMode:
    def test_finalize_run_appends_scoring_and_persists(self, temp_db):
        t0 = time.perf_counter()
        pipeline = verifier.finalize_run(
            "energy_issue", {"wallet": "0xlearner"}, UC,
            [verifier.stage_skipped("compile", "n/a"),
             verifier.stage_skipped("semantic", "n/a"),
             verifier.stage_result("business", True, "proof ok"),
             verifier.stage_result("onchain", True, "mint ok")],
            started_at=t0, task_ref="proof-1")
        assert pipeline["ok"] is True
        assert len(pipeline["stages"]) == 5  # 自动补 L5
        assert pipeline["stages"][-1]["stage"] == "scoring"
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM task_runs WHERE task_ref='proof-1'").fetchone()
        assert row is not None and row["status"] == "success"

    def test_record_failure_persists_failed_row(self, temp_db):
        verifier.record_failure("energy_issue", {"wallet": "0xlearner"}, UC,
                                time.perf_counter(), "凭证校验失败",
                                task_ref="proof-2")
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM task_runs WHERE task_ref='proof-2'").fetchone()
        assert row is not None and row["status"] == "failed"
        assert "凭证校验失败" in row["stage_results"]


class TestCompileEndpointPipeline:
    def test_compile_response_has_pipeline_and_task_runs(self, client):
        """POST /contracts/compile：响应含 pipeline（纯新增），task_runs 落库（失败也写）。"""
        headers = {"Authorization": f"Bearer {_token()}"}
        r = client.post(
            "/api/contracts/compile",
            json={"name": "Bad", "source": "pragma solidity ^0.4.25; contract X {"},
            headers=headers,
        )
        assert r.status_code == 200  # 编译失败仍 200 + errors（既有语义）
        body = r.json()
        assert body["ok"] is False and body["errors"]
        pl = body["pipeline"]
        assert set(pl) >= {"run_id", "stages", "ok", "latency_ms"}
        assert pl["ok"] is False and pl["run_id"]
        stages = {s["stage"] for s in pl["stages"]}
        assert "compile" in stages and "scoring" in stages
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM task_runs WHERE task_type='compile'").fetchone()
        assert row is not None and row["status"] == "failed"

    def test_compile_unauthenticated_rejected(self, client):
        r = client.post("/api/contracts/compile",
                        json={"name": "X", "source": "x"})
        assert r.status_code == 401


class TestNotifyEndpoints:
    def test_stream_requires_auth(self, client):
        """SSE 401：无 token 拒绝。"""
        assert client.get("/api/notify/stream").status_code == 401

    def test_history_requires_auth(self, client):
        assert client.get("/api/notify/history").status_code == 401

    def test_stream_invalid_token_rejected(self, client):
        r = client.get("/api/notify/stream", params={"token": "not-a-jwt"})
        assert r.status_code == 401

    def test_stream_expired_token_rejected(self, client):
        """过期 JWT → 401（与 get_current_user 同一验签路径/语义）。"""
        expired = create_token(
            {"user_id": "u1", "role_id": 1, "wallet": "0xlearner",
             "class_id": "c1", "user_name": "tester"},
            expires_seconds=-60,
        )
        assert client.get("/api/notify/stream",
                          params={"token": expired}).status_code == 401
        assert client.get("/api/notify/history",
                          params={"token": expired}).status_code == 401

    def test_stream_query_token_valid_vs_invalid(self, client, temp_db):
        """client.get('/api/notify/stream?token=...')：无效→401；有效→200（SSE 流）。

        401 在建流前完成验签，client.get 可直接断言；200 场景为无限流，
        TestClient portal 会同步读完整个响应体而挂起，故沿用既有直驱
        body_iterator 方式（等价覆盖同一端点路径，验签失败会抛 401）。
        """
        # 无效 token → 401
        assert client.get("/api/notify/stream",
                          params={"token": "bad-token"}).status_code == 401

        # 有效 token → 200（直驱：?token= 通道验签通过并产出 SSE 流）
        async def scenario():
            resp = await notify_stream(authorization=None, token=_token())
            assert resp.status_code == 200
            assert resp.media_type == "text/event-stream"
            first = await asyncio.wait_for(resp.body_iterator.__anext__(), timeout=2)
            assert ": connected" in first
            await resp.body_iterator.aclose()

        asyncio.run(scenario())

    def test_stream_frames_and_cleanup(self, temp_db):
        """直驱 /stream 生成器：初始注释帧 → 事件帧格式 → 断开清理订阅。

        （starlette TestClient 的 portal 会同步等待整个 ASGI 应用返回，
        无法驱动无限流；直调端点函数 + body_iterator 等价覆盖同一路径。）
        """
        async def scenario():
            before = events_bus.subscriber_count()
            resp = await notify_stream(
                authorization=f"Bearer {_token()}", token=None)
            assert resp.media_type == "text/event-stream"
            assert resp.headers.get("X-Accel-Buffering") == "no"
            it = resp.body_iterator
            first = await asyncio.wait_for(it.__anext__(), timeout=2)
            assert ": connected" in first
            assert events_bus.subscriber_count() == before + 1
            # 发布一条广播事件 → 收到命名事件帧（event:/data: 格式）
            events_bus.publish("tx_confirmed", {"tx_hash": "0xzz"})
            frame = await asyncio.wait_for(it.__anext__(), timeout=2)
            assert "event: tx_confirmed" in frame and '"tx_hash": "0xzz"' in frame
            # 客户端断开（生成器关闭）→ finally 清理订阅，注册表归位
            await it.aclose()
            assert events_bus.subscriber_count() == before

        asyncio.run(scenario())

    def test_stream_query_token_auth_ok(self, temp_db):
        """EventSource 兼容通道：无 Authorization 时 ?token= 同样验签通过。"""
        async def scenario():
            resp = await notify_stream(authorization=None, token=_token())
            assert resp.media_type == "text/event-stream"
            first = await asyncio.wait_for(resp.body_iterator.__anext__(), timeout=2)
            assert ": connected" in first
            await resp.body_iterator.aclose()

        asyncio.run(scenario())

    def test_history_scope_and_filter(self, client):
        """/history：本人定向 + 广播可见，他人定向 / 异班班级事件不可见；类型过滤与分页字段。"""
        events_bus.publish("tx_confirmed", {"i": 1})                      # 广播
        events_bus.publish("energy_issued", {"i": 2}, user_id="u1")       # 本人定向
        events_bus.publish("energy_issued", {"i": 3}, user_id="uX")       # 他人定向
        events_bus.publish("deployed", {"i": 4}, class_id="c2")           # 异班班级事件
        events_bus.flush_pending()  # 任务 #25：镜像改为后台批量写入，断言前同步排空
        headers = {"Authorization": f"Bearer {_token()}"}
        r = client.get("/api/notify/history", headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert body["limit"] == 20 and body["offset"] == 0
        payloads = [it["payload"] for it in body["items"]]
        assert {"i": 1} in payloads and {"i": 2} in payloads
        assert {"i": 3} not in payloads   # 他人定向不可见
        assert {"i": 4} not in payloads   # 异班班级事件不可见
        # 类型过滤
        r2 = client.get("/api/notify/history",
                        params={"event_type": "energy_issued"}, headers=headers)
        items2 = r2.json()["items"]
        assert items2 and all(it["event_type"] == "energy_issued" for it in items2)
        assert {"i": 3} not in [it["payload"] for it in items2]


class TestEnergyIssueConcurrent:
    """H1：能量发放并发同 proof_no+role_key 防双铸（占位行 + UNIQUE 拦截）。"""

    _GE_ABI = [{
        "type": "function", "name": "mint", "stateMutability": "nonpayable",
        "inputs": [{"name": "to", "type": "address"},
                   {"name": "value", "type": "uint256"},
                   {"name": "reason", "type": "string"}],
        "outputs": [],
    }]

    def test_concurrent_same_proof_single_record(self, client):
        """5 线程并发同 proof_no：仅 1 笔非幂等成功，账本恰 1 行（无双重 mint）。"""
        headers = {"Authorization": f"Bearer {_token()}"}
        # 直接种入 GreenEnergy 部署记录（mock 链 has_code 恒真，避开 solc 依赖）
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO deployed_contracts(address,name,abi,bytecode,source,"
                "deployer,tx_hash,standard,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                ("0x" + "e" * 40, "GreenEnergy", json.dumps(self._GE_ABI),
                 "0x00", "", "0xlearner", "0xseed", "ERC20", "2026-01-01T00:00:00"),
            )
        # 接收方钱包选定 metro 角色（发放权限闭环，非 force 路径）
        r = client.post("/api/eco/role/select",
                        json={"wallet": "0xlearner", "role_key": "metro"},
                        headers=headers)
        assert r.status_code == 200

        bodies: list = []
        lock = threading.Lock()

        def fire():
            rr = client.post(
                "/api/eco/energy/issue",
                json={"wallet": "0xlearner", "role_key": "metro",
                      "proof": {"trip_no": "TRIP-DUP-1", "station_in": "国贸站",
                                "station_out": "西二旗站", "board_time": "2026-08-31 08:05",
                                "distance_km": 20}},
                headers=headers,
            )
            with lock:
                bodies.append((rr.status_code, rr.json()))

        threads = [threading.Thread(target=fire) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(code == 200 for code, _ in bodies)
        # 恰 1 笔真实发放（非幂等），其余全部幂等回放（不重复落行）
        fresh = [b for _, b in bodies if not b.get("idempotent")]
        replays = [b for _, b in bodies if b.get("idempotent")]
        assert len(fresh) == 1 and len(replays) == 4
        assert fresh[0]["proof_no"] == "TRIP-DUP-1"
        # 账本唯一行：占位 + UNIQUE 拦截成功，无双重 mint 落账
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM eco_energy_records "
                "WHERE proof_no='TRIP-DUP-1' AND role_key='metro'",
            ).fetchall()
        assert len(rows) == 1
        assert rows[0]["points"] == 50
        assert rows[0]["tx_hash"] == "0xmock"  # 占位行已回填真实 tx_hash
