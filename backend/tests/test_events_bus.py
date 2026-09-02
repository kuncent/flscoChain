"""events_bus 测试：publish→订阅扇出 / 跨线程投递 / 可见性过滤 / 断线清理 / notifications 镜像。"""
import asyncio

from app import events_bus
from app.db import get_conn


def _run(coro):
    """在新事件循环内执行异步场景（订阅者注册需要 running loop）。"""
    return asyncio.run(coro)


class TestPublishSubscribe:
    def test_publish_reaches_subscriber(self, temp_db):
        """同循环发布 → 订阅者队列收到事件（payload / type 原样）。"""
        async def scenario():
            sub = events_bus.subscribe(user_id="u1", class_id="c1")
            events_bus.publish(events_bus.BusEvent.TX_CONFIRMED, {"tx_hash": "0xabc"})
            ev = await asyncio.wait_for(sub.queue.get(), timeout=2)
            events_bus.unsubscribe(sub.id)
            return ev

        ev = _run(scenario())
        assert ev.type == "tx_confirmed"
        assert ev.payload == {"tx_hash": "0xabc"}

    def test_cross_thread_publish_is_safe(self, temp_db):
        """跨线程发布（EVM 批量出块后台线程场景）：经 call_soon_threadsafe 投递。"""
        async def scenario():
            sub = events_bus.subscribe(user_id="u1")
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, events_bus.publish,
                events_bus.BusEvent.DEPLOYED, {"name": "C"}, "", "", "")
            ev = await asyncio.wait_for(sub.queue.get(), timeout=2)
            events_bus.unsubscribe(sub.id)
            return ev

        ev = _run(scenario())
        assert ev.type == "deployed" and ev.payload == {"name": "C"}

    def test_targeted_event_only_visible_to_owner(self, temp_db):
        """定向事件（带 user_id）：仅同 user 订阅者可见。"""
        async def scenario():
            s1 = events_bus.subscribe(user_id="u1")
            s2 = events_bus.subscribe(user_id="u2")
            events_bus.publish("energy_issued", {"i": 1}, user_id="u1")
            ev = await asyncio.wait_for(s1.queue.get(), timeout=2)
            assert ev.user_id == "u1"
            assert s2.queue.empty()  # 他人定向事件不可见
            events_bus.unsubscribe(s1.id)
            events_bus.unsubscribe(s2.id)

        _run(scenario())

    def test_class_scope_filter(self, temp_db):
        """班级事件：同班可见，异班不可见；无班级订阅者仅特权角色（教师/管理员）
        可见，普通无班级用户只收广播（任务 #25：堵死无班级用户越权接收班级事件）。"""
        async def scenario():
            same = events_bus.subscribe(user_id="a", class_id="c1")
            other = events_bus.subscribe(user_id="b", class_id="c2")
            teacher = events_bus.subscribe(user_id="t", role_id=3)      # 特权：无班级可见各班事件
            student = events_bus.subscribe(user_id="s", role_id=2)      # 普通：无班级只收广播
            events_bus.publish("tutorial_step_done", {"step": 3}, class_id="c1")
            ev = await asyncio.wait_for(same.queue.get(), timeout=2)
            assert ev.payload == {"step": 3}
            assert other.queue.empty()
            await asyncio.wait_for(teacher.queue.get(), timeout=2)   # 教师（特权）可见
            assert student.queue.empty()                             # 无班级普通用户不可见（越权拦截）
            for s in (same, other, teacher, student):
                events_bus.unsubscribe(s.id)

        _run(scenario())

    def test_unsubscribe_idempotent_and_cleanup(self, temp_db):
        """断线清理：注销幂等，注册表归位。"""
        async def scenario():
            before = events_bus.subscriber_count()
            sub = events_bus.subscribe()
            assert events_bus.subscriber_count() == before + 1
            events_bus.unsubscribe(sub.id)
            events_bus.unsubscribe(sub.id)  # 幂等
            assert events_bus.subscriber_count() == before

        _run(scenario())


class TestNotificationsMirror:
    def test_publish_mirrors_to_notifications(self, temp_db):
        """publish 镜像写 notifications（任务 #25：后台小批量聚合，
        flush_pending 同步排空后断言；供 SSE 断线后经 /history 补看）。"""
        events_bus.publish("energy_issued", {"points": 50},
                           user_id="u9", class_id="c9")
        events_bus.flush_pending()
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM notifications WHERE event_type='energy_issued'",
            ).fetchone()
        assert row is not None
        assert row["user_id"] == "u9" and row["class_id"] == "c9"
        assert '"points": 50' in row["payload"]

    def test_publish_never_raises_even_if_table_missing(self, temp_db):
        """notifications 表缺失时仅降级日志，不向业务调用方抛异常。"""
        with get_conn() as conn:
            conn.execute("DROP TABLE notifications")
        events_bus.publish("tx_confirmed", {"ok": 1})   # 入队不应抛出
        events_bus.flush_pending()                       # flush 失败仅日志，不抛出
