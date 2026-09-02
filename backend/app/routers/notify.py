"""事件通知路由（任务 #21）：SSE 实时推送 + 事件历史分页。

鉴权说明：
- 与全站一致的 JWT 验签（复用 security.decode_token，401 语义与
  get_current_user 完全一致：过期/无效均 401）；
- 浏览器原生 EventSource 无法携带自定义请求头，因此 /stream 与 /history
  除 `Authorization: Bearer` 外，额外兼容 `?token=<JWT>` 查询参数
  （同一验签路径，仅传递通道不同；token 走 URL 会进访问日志，教学内网
  场景可接受，已在 deploy/nginx.chain.conf 注释说明）。

SSE 帧格式（前端 events.ts 对应解析）：
    : connected          ← 初始注释帧（立即建立连接）
    event: <event_type>  ← 命名事件帧（与 events_bus.BusEvent 常量一致）
    data: {json}
    : keepalive          ← 心跳注释帧（15s 一次，保活代理/浏览器连接）

客户端断开：StreamingResponse 生成器被关闭时 finally 清理订阅
（events_bus.unsubscribe），不泄漏队列。
"""
from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from .. import events_bus
from ..db import get_conn
from ..security import PRIVILEGED_ROLES, decode_token

router = APIRouter(prefix="/api/notify", tags=["notify"])

# 心跳间隔：需显著小于反向代理读超时（nginx /api/notify/ 配 3600s，
# 前端 EventSource 断线重连兜底），15s 兼顾保活与空闲开销。
HEARTBEAT_SECONDS = 15.0


def _authenticate(authorization: Optional[str], token: Optional[str]) -> dict:
    """JWT 验签：优先 Authorization: Bearer；EventSource 场景兼容 ?token=。"""
    if authorization and authorization.lower().startswith("bearer "):
        return decode_token(authorization[7:].strip())
    if token:
        return decode_token(token.strip())
    raise HTTPException(
        status_code=401, detail="未登录或登录已过期，请先登录",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.get("/stream")
async def stream(
    authorization: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None, description="EventSource 无法带自定义头，JWT 可经 query 传递"),
):
    """SSE 实时事件流（按登录身份的 user/tenant/class 过滤；心跳注释帧保活）。"""
    user = _authenticate(authorization, token)
    # 订阅维度随注册快照固化：定向事件仅本人可见，班级事件同班可见，广播全员可见。
    # 任务 #25 评审修复：
    # - tenant_id 取登录身份值（原固定空串导致 tenant 过滤恒不生效）；
    # - role_id 传入订阅快照：无班级且非特权角色（role_id ∉ {1,3}）的订阅者
    #   只收广播（class_id=''）事件，不收任何班级事件（越权拦截）。
    sub = events_bus.subscribe(
        user_id=user.get("user_id") or "",
        tenant_id=user.get("tenant_id") or "",
        class_id=(user.get("class_id") or "").strip(),
        role_id=int(user.get("role_id") or 0),
    )

    async def event_stream():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    ev = await asyncio.wait_for(sub.queue.get(), timeout=HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"   # 注释帧心跳：客户端忽略，代理保持连接
                    continue
                data = json.dumps(
                    {"id": ev.id, "type": ev.type, "payload": ev.payload, "ts": ev.ts},
                    ensure_ascii=False,
                )
                yield f"event: {ev.type}\ndata: {data}\n\n"
        finally:
            # 客户端断开 / 生成器关闭：清理订阅，避免队列泄漏
            events_bus.unsubscribe(sub.id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # 提示反代不缓冲（与 nginx proxy_buffering off 双保险）
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/history")
def history(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    event_type: str = Query(default="", description="按事件类型过滤（可选）"),
    authorization: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None),
):
    """分页查询事件历史（SSE 断线补看）。

    scope（与全站租户口径一致）：
    - 本人的定向事件（user_id = 当前登录）；
    - 广播事件（user_id = ''：交易确认 / 部署等全员可见事件）；
    - 班级维度：登录身份带 class_id 时，仅本班班级事件 + 无班级归属的广播；
      无班级且非特权角色（role_id ∉ {1,3}）仅广播（任务 #25 越权拦截，
      与 /stream 订阅可见性同步）；
    - 租户维度：tenant_id = 本人租户 或 ''（未登记租户的历史/广播行兼容可见）。
    """
    user = _authenticate(authorization, token)
    uid = user.get("user_id") or ""
    class_id = (user.get("class_id") or "").strip()
    role_id = int(user.get("role_id") or 0)
    tenant_id = str(user.get("tenant_id") or "")

    where = "(user_id = ? OR user_id = '')"
    params: list = [uid]
    if class_id:
        where += " AND (class_id = ? OR class_id = '')"
        params.append(class_id)
    elif role_id not in PRIVILEGED_ROLES:
        # 无班级的普通用户：只查广播事件（class_id=''），不收任何班级事件
        where += " AND class_id = ''"
    # 租户过滤（与 M1 兼容口径一致：本人租户 + 未登记租户的空串行）
    where += " AND (tenant_id = ? OR tenant_id = '')"
    params.append(tenant_id)
    if event_type:
        where += " AND event_type = ?"
        params.append(event_type)

    with get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM notifications WHERE {where}", params,
        ).fetchone()["c"]
        rows = conn.execute(
            "SELECT id,user_id,tenant_id,class_id,event_type,payload,created_at "
            f"FROM notifications WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [int(limit), int(offset)],
        ).fetchall()

    items = []
    for r in rows:
        d = dict(r)
        try:
            d["payload"] = json.loads(d.get("payload") or "{}")
        except (TypeError, ValueError):
            pass
        items.append(d)
    return {"items": items, "total": int(total), "limit": int(limit), "offset": int(offset)}
