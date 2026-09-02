"""多租户上下文容器与请求级解析（任务 #18）。

职责：
  1. TenantContext：请求级租户身份容器（user_id / class_id / school_id /
     wallet / role_id），由 JWT 验签结果构造，只读。
  2. 身份解析单次化：main.py 在 CORS 之后注册的租户中间件对每个请求预解析
     一次 JWT（复用 security.resolve_identity / identity_from_request），结果
     挂 request.state._current_user；security.get_current_user / optional_user
     与本模块 ctx() 均优先读该缓存 —— 全请求生命周期只验签一次。
     中间件里只做一次轻量 HMAC 验签（无 Authorization 头的请求近乎零成本，
     仅读 header），不做任何 DB 查询（无重活）。
  3. scope_filter：读侧租户过滤片段（optional 鉴权的数据面），复用
     db.scope_where 的 NULL / '' 兼容口径，供 explorer / monitor / ide
     按 ctx.user_id 叠加到既有手写 SQL，历史未归属行永不"丢失"。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Request

from .db import scope_where
from .security import PRIVILEGED_ROLES, identity_from_request


@dataclass
class TenantContext:
    """请求级租户身份上下文（来源：JWT 载荷，只读）。

    school_id：登录签发的 JWT 载荷不含该字段（create_token 固定五字段
    user_id / role_id / wallet / class_id / user_name），默认空串；
    需要精确值时由调用方按 user_id 查 user_info 补全，本模块刻意不查库，
    保证解析路径（含中间件）无 DB 访问。
    """

    user_id: str = ""
    class_id: str = ""
    school_id: str = ""
    wallet: str = ""
    role_id: int = 0
    user_name: str = ""

    @property
    def privileged(self) -> bool:
        """教师 / 管理员（PRIVILEGED_ROLES，可跨学生查看教学管理数据）。"""
        return self.role_id in PRIVILEGED_ROLES


def parse_context(request: Request) -> Optional[TenantContext]:
    """从请求解析租户上下文（只解析，不重复验签）。

    优先复用 request.state._current_user（租户中间件预解析 /
    get_current_user 依赖注入的验签结果）；仅当缓存缺失时才经
    security.identity_from_request 走一次解析并回填缓存。
    未登录 / token 无效返回 None（不抛 401，由调用方决策）。
    """
    cached = getattr(request.state, "_current_user", None)
    if cached is None:
        cached = identity_from_request(request)
        if cached is not None:
            request.state._current_user = cached
    if not cached:
        return None
    return TenantContext(
        user_id=str(cached.get("user_id") or ""),
        class_id=str(cached.get("class_id") or ""),
        school_id=str(cached.get("school_id") or ""),
        wallet=str(cached.get("wallet") or ""),
        role_id=int(cached.get("role_id") or 0),
        user_name=str(cached.get("user_name") or ""),
    )


# 「已解析且确认无身份」哨兵：未登录请求缓存该值，避免每次 ctx() 重复解析
_NO_CTX = object()


def ctx(request: Request) -> Optional[TenantContext]:
    """取值助手（懒式 + request.state._tenant_ctx 缓存）。

    首次访问时才解析（中间件已预解析的场景直接命中 parse_context 的缓存），
    后续访问零成本。未登录返回 None。
    """
    cached = getattr(request.state, "_tenant_ctx", None)
    if cached is not None:
        return None if cached is _NO_CTX else cached
    parsed = parse_context(request)
    request.state._tenant_ctx = parsed if parsed is not None else _NO_CTX
    return parsed


def tenant_context(request: Request) -> Optional[TenantContext]:
    """FastAPI 依赖：`Depends(tenant_context)` 获取租户上下文（可为 None）。"""
    return ctx(request)


def request_uid(request: Request) -> str:
    """当前登录 user_id（未登录返回空串）—— 路由侧 scope_filter 的便捷取值。"""
    tc = ctx(request)
    return tc.user_id if tc else ""


def scope_filter(alias: str, uid: str) -> tuple[str, list]:
    """读侧租户过滤片段（optional 鉴权的统一数据面，任务 #18）。

    - 登录（uid 非空）：db.scope_where 语义 —— 本人归属行 + user_id 未登记
      的旧行（'' / NULL 通配，历史数据不"丢失"）；
    - 未登录：仅未登记旧行 —— 内置演示 / 历史公共数据仍可读（不破坏现有
      页面），明确归属他人的私有行一律不可见（optional 语义下无 token
      退化为"只读公共数据"）。

    返回 (WHERE 条件片段, 参数列表)；调用方按需以 `WHERE` / `AND` 拼入
    既有手写 SQL（片段自带括号，多条件拼接安全）。
    """
    if uid:
        return scope_where(alias, user_id=uid)
    return (f"({alias}.user_id = '' OR {alias}.user_id IS NULL)", [])


def register_tenant_middleware(app) -> None:
    """注册租户上下文中间件（main.py 在 CORS 之后调用）。

    中间件只做一次轻量身份预解析并挂 request.state._current_user：
    - 无 Authorization 头的请求（静态资源 / 健康检查 / 匿名读）近乎零成本；
    - 带 token 的请求做一次 HMAC 验签（微秒级），结果被 get_current_user /
      optional_user / tenant.ctx 全链路复用，不重复验签；
    - 不做 DB 查询，不抛异常（token 无效仅视为未登录，401 仍由依赖层决策）。
    """

    @app.middleware("http")
    async def _tenant_context_middleware(request: Request, call_next):
        ident = identity_from_request(request)
        if ident is not None:
            request.state._current_user = ident
        return await call_next(request)
