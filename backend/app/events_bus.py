"""进程内事件总线（任务 #21）：publish / subscribe + asyncio.Queue 扇出。

命名说明：app/learning/events.py 是「学习行为埋点」模块（learning_events 表
唯一写入口），本模块是「运行时事件流」基础设施（tx_confirmed / deployed /
compiled / energy_issued / tutorial_step_done / sandbox_*），二者职责不同，
仅 module 名相近——events_bus 刻意避开 events 命名以示区分，互不依赖
（唯一的单向依赖：publish 时把事件镜像写入 notifications 表，供 SSE 断线后
经 /api/notify/history 补看；埋点表 learning_events 不受影响）。

线程安全设计（稳妥实现）：
- publish() 可能从任意线程调用：FastAPI 事件循环线程、EVM 批量出块后台线程
  （_block_loop）、tx_decoder 编译线程池内的同步调用等；
- 每个订阅者持有「注册时所在的事件循环 + asyncio.Queue」；投递统一经
  loop.call_soon_threadsafe(queue.put_nowait, ev) 调度回订阅者自己的循环
  线程执行——asyncio.Queue 的非线程安全 put_nowait 因此永远在正确线程运行；
- 注册表由 threading.Lock 保护；loop 已关闭 / 即将关闭（RuntimeError）时
  静默放弃投递（订阅者断开时由 SSE handler 的 finally 清理注册表）；
- 队列容量有限（慢消费者只丢事件不阻塞发布方），实时推送非关键路径，
  任何异常只记日志，绝不向业务调用方抛出。

notifications 镜像同样失败容错（与 learning.events.track 同风格：
db 全局锁 + 参数化 SQL，失败仅 warning）。任务 #25 评审修复：镜像写入改为
进程内小批量聚合（队列 + 后台线程约 500ms flush 一批 executemany），
避免每条事件一次事务的写放大；flush 循环顺带做 30 天 TTL 清理。
"""
from __future__ import annotations

import asyncio
import json
import logging
import queue as _queue_mod
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class BusEvent:
    """事件类型常量（SSE `event:` 帧名与此逐字一致，前端按类型注册回调）。"""

    TX_CONFIRMED = "tx_confirmed"        # 交易上链确认（出块回执成功）
    DEPLOYED = "deployed"                # 合约部署成功
    COMPILED = "compiled"                # 合约编译完成
    ENERGY_ISSUED = "energy_issued"      # 绿色能量发放成功
    TUTORIAL_STEP_DONE = "tutorial_step_done"  # 搭链教程步骤完成
    # 沙箱事件（预留：云桌面真实终端接入后启用）
    SANDBOX_READY = "sandbox_ready"
    SANDBOX_EXIT = "sandbox_exit"


@dataclass
class Event:
    """总线事件（immutable 视角：发布后各订阅者共享，不得修改）。"""

    type: str
    payload: dict
    tenant_id: str = ""
    class_id: str = ""
    user_id: str = ""                    # 非空=定向事件（仅该用户可见）；空=广播
    ts: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])


@dataclass
class Subscriber:
    """订阅者：SSE 流 ↔ 事件循环绑定。"""

    id: str
    user_id: str
    tenant_id: str
    class_id: str
    loop: asyncio.AbstractEventLoop
    queue: "asyncio.Queue[Event]"
    role_id: int = 0                     # 角色位（1=管理员 3=教师为特权角色）
    created_at: float = field(default_factory=time.time)


_QUEUE_MAX = 256                        # 单订阅者队列上限（慢消费者丢最旧不丢连接）
_subs: dict = {}
_subs_lock = threading.Lock()


def subscribe(user_id: str = "", tenant_id: str = "", class_id: str = "",
              role_id: int = 0) -> Subscriber:
    """注册订阅者（必须在 asyncio 事件循环线程内调用，如 SSE handler）。

    过滤维度随注册快照固化：user_id / tenant_id / class_id 为空表示该维度
    取「广播 + 与其相关的定向事件」口径（见 _visible）；role_id 用于无班级
    订阅者的班级事件越权拦截（特权角色 {1,3} 除外，见 _visible）。
    """
    loop = asyncio.get_running_loop()
    try:
        rid = int(role_id or 0)
    except (TypeError, ValueError):
        rid = 0
    sub = Subscriber(
        id=uuid.uuid4().hex,
        user_id=(user_id or "").strip(),
        tenant_id=(tenant_id or "").strip(),
        class_id=(class_id or "").strip(),
        loop=loop,
        queue=asyncio.Queue(maxsize=_QUEUE_MAX),
        role_id=rid,
    )
    with _subs_lock:
        _subs[sub.id] = sub
    return sub


def unsubscribe(sub_id: str) -> None:
    """注销订阅者（幂等；SSE handler 的 finally 必调）。"""
    with _subs_lock:
        _subs.pop(sub_id, None)


def subscriber_count() -> int:
    with _subs_lock:
        return len(_subs)


def _visible(sub: Subscriber, ev: Event) -> bool:
    """订阅可见性判定（与 db.scope_where 的「未登记即广播」口径一致）：

    - 事件带 user_id（定向）：仅同 user_id 的订阅者可见；
    - 事件带 class_id（班级）：同班订阅者可见；无班级的订阅者仅特权角色
      （role_id ∈ {1,3}，管理员/教师）可见，普通无班级用户只收广播——
      堵死「班级事件对无班级用户越权可见」的缺口；
    - 事件带 tenant_id：同租户可见；
    - 事件字段为空 = 广播：所有人可见。
    """
    if ev.user_id and sub.user_id and ev.user_id != sub.user_id:
        return False
    if ev.class_id:
        if not sub.class_id:
            if int(sub.role_id or 0) not in (1, 3):
                return False
        elif ev.class_id != sub.class_id:
            return False
    if ev.tenant_id and sub.tenant_id and ev.tenant_id != sub.tenant_id:
        return False
    return True


def _offer(sub: Subscriber, ev: Event) -> None:
    """在订阅者自己的循环线程内投递（由 call_soon_threadsafe 调度）。"""
    try:
        sub.queue.put_nowait(ev)
    except asyncio.QueueFull:
        # 慢消费者：丢弃本条（历史可在 /api/notify/history 补看），保连接不死
        logger.debug("[events_bus] subscriber %s queue full, drop event %s", sub.id, ev.id)


# ---------------------------------------------------------------------------
# notifications 镜像：进程内小批量聚合写入（任务 #25 评审修复写放大）
# publish() 只入队（无锁竞争、无 DB IO），后台 daemon 线程约 500ms 攒一批
# executemany 落库，并在每批顺带做 30 天 TTL 清理。失败容错与原同步写入一致。
# ---------------------------------------------------------------------------
_MIRROR_FLUSH_SECONDS = 0.5             # 攒批窗口（约 500ms flush 一批）
_MIRROR_BATCH_MAX = 500                 # 单批上限（超过即提前 flush，防止长尾积压）
_MIRROR_TTL_DAYS = 30                   # 镜像表保留期（超期行随批清理）
_mirror_queue: "_queue_mod.Queue" = _queue_mod.Queue()
_mirror_thread: Optional[threading.Thread] = None
_mirror_thread_lock = threading.Lock()


def _flush_mirror_batch(batch: list) -> None:
    """把一批镜像行 executemany 落库 + 顺带 30 天 TTL 清理（失败仅日志）。"""
    try:
        from .db import _lock as _DB_LOCK, get_conn
        cutoff = (datetime.utcnow() - timedelta(days=_MIRROR_TTL_DAYS)).isoformat()
        with _DB_LOCK, get_conn() as conn:
            conn.executemany(
                "INSERT INTO notifications(user_id,tenant_id,class_id,event_type,payload,created_at) "
                "VALUES(?,?,?,?,?,?)",
                batch,
            )
            conn.execute("DELETE FROM notifications WHERE created_at < ?", (cutoff,))
    except Exception:
        logger.warning("[events_bus] notifications 镜像 flush 失败 (n=%d)",
                       len(batch), exc_info=True)


def _mirror_worker() -> None:
    """后台 flush 线程：阻塞等首条 → 攒批（窗口/上限先到先止）→ 落库。"""
    while True:
        try:
            first = _mirror_queue.get(timeout=1.0)
        except _queue_mod.Empty:
            continue
        batch = [first]
        deadline = time.time() + _MIRROR_FLUSH_SECONDS
        while len(batch) < _MIRROR_BATCH_MAX:
            remain = deadline - time.time()
            if remain <= 0:
                break
            try:
                batch.append(_mirror_queue.get(timeout=remain))
            except _queue_mod.Empty:
                break
        _flush_mirror_batch(batch)


def _ensure_mirror_worker() -> None:
    """惰性启动后台 flush 线程（双检锁；线程意外退出后下次发布自动重建）。"""
    global _mirror_thread
    if _mirror_thread is not None and _mirror_thread.is_alive():
        return
    with _mirror_thread_lock:
        if _mirror_thread is not None and _mirror_thread.is_alive():
            return
        t = threading.Thread(target=_mirror_worker, name="events-bus-mirror", daemon=True)
        t.start()
        _mirror_thread = t


def flush_pending() -> int:
    """同步清空镜像队列并落库（测试断言 / 优雅停机用）；返回本批行数。

    与后台线程并发安全：双方都以「取到队列里的行就落库」为口径，
    最坏情况只是同一时刻分两批写入，不丢不重。
    """
    batch: list = []
    while True:
        try:
            batch.append(_mirror_queue.get_nowait())
        except _queue_mod.Empty:
            break
    if batch:
        _flush_mirror_batch(batch)
    return len(batch)


def publish(event_type: str, payload: dict,
            tenant_id: str = "", class_id: str = "", user_id: str = "") -> None:
    """发布事件（任意线程可调；永不抛异常——推送失败不影响业务主流程）。

    1) 镜像入队（后台线程批量落 notifications 表，断线补看；失败容错）；
    2) 扇出给全部可见订阅者（跨线程经 call_soon_threadsafe）。
    """
    try:
        ev = Event(
            type=event_type,
            payload=payload if isinstance(payload, dict) else {"data": payload},
            tenant_id=(tenant_id or "").strip(),
            class_id=(class_id or "").strip(),
            user_id=(user_id or "").strip(),
        )
    except Exception:
        logger.warning("[events_bus] 构造事件失败 type=%s", event_type, exc_info=True)
        return

    # 1) 持久化镜像入队（批量聚合写；后台线程故障只记日志，绝不阻塞发布方）
    try:
        from .db import now
        _mirror_queue.put_nowait(
            (ev.user_id, ev.tenant_id, ev.class_id, ev.type,
             json.dumps(ev.payload, ensure_ascii=False), now()),
        )
        _ensure_mirror_worker()
    except Exception:
        logger.warning("[events_bus] notifications 镜像入队失败 type=%s", event_type, exc_info=True)

    # 2) 扇出（快照后投递，避免持锁做 IO）
    with _subs_lock:
        subs: list = list(_subs.values())
    for sub in subs:
        if not _visible(sub, ev):
            continue
        try:
            sub.loop.call_soon_threadsafe(_offer, sub, ev)
        except RuntimeError:
            # loop 已关闭：SSE 断开路径，等待其 finally 清理注册表即可
            pass
        except Exception:
            logger.warning("[events_bus] 投递失败 sub=%s type=%s", sub.id, event_type, exc_info=True)
