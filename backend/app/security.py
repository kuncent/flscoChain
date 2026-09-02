"""服务端 JWT 鉴权体系。

职责：
  1. JWT_SECRET 管理：从环境变量 / backend/.env 读取；缺失时自动生成随机密钥并持久化到 .env。
  2. create_token(payload)：签发 24h 过期 JWT，载荷含 user_id / role_id / wallet / class_id / user_name。
  3. FastAPI 依赖：
       - get_current_user()：解析 Authorization: Bearer 并验签，失败/过期返回 401；
       - optional_user()：未登录返回 None（读接口可匿名、写接口必登录的场景）；
       - require_role(*role_ids)：角色受限依赖工厂，角色不符返回 403。
  4. 操作者身份解析辅助：写接口的操作者身份统一从 JWT 上下文解析，
     请求体携带的身份字段必须与 JWT 身份一致（或为平台内置生态钱包）。

兼容层：环境变量 AUTH_DEV_HEADER_FALLBACK（默认 false），仅当为 true 时
才允许在无 Bearer token 时回退读取旧 X-* 自报头，便于开发调试；生产默认关闭。
"""
from __future__ import annotations

import os
import secrets
import time
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

import jwt
from fastapi import Depends, Header, HTTPException, Request

from .config import settings

# JWT 算法与有效期（24 小时）
ALGORITHM = "HS256"
TOKEN_TTL_SECONDS = 24 * 3600

# backend/.env 文件路径（本文件位于 backend/app/ 下，上溯一级即 backend/）
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

# 平台内置生态钱包（联盟角色钱包 / 默认学习钱包）：
# 它们是链上操作的演示身份，不代表真实登录用户，允许已登录用户在链上操作中使用
BUILTIN_WALLETS = {
    "0xadmin", "0xmetro", "0xbus", "0xbike", "0xtakeout", "0xrecycle",
    "0xlearner", "default",
}

# 教师 / 管理员角色（可代操作 / 查看他人数据的教学管理场景）
PRIVILEGED_ROLES = {1, 3}


# ===========================================================================
# JWT_SECRET 管理（环境变量优先；缺失则自动生成并持久化到 backend/.env）
# ===========================================================================
def _read_secret_from_env_file() -> str:
    """从 backend/.env 中解析 JWT_SECRET 项。"""
    try:
        if not _ENV_FILE.exists():
            return ""
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("JWT_SECRET="):
                return s.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def _persist_secret(secret: str) -> None:
    """把自动生成的 JWT_SECRET 追加写入 backend/.env（重启后保持稳定）。"""
    try:
        content = _ENV_FILE.read_text(encoding="utf-8") if _ENV_FILE.exists() else ""
        if content and not content.endswith("\n"):
            content += "\n"
        content += (
            "\n# ===== JWT 鉴权（服务端签名密钥，勿泄露 / 勿提交到版本库）=====\n"
            f"JWT_SECRET={secret}\n"
        )
        _ENV_FILE.write_text(content, encoding="utf-8")
    except Exception:
        pass  # 写入失败不阻塞启动（密钥仍保留在当前进程环境变量中）


_SECRET_CACHE: Optional[str] = None


def jwt_secret() -> str:
    """返回当前进程使用的 JWT 签名密钥（惰性初始化 + 自动持久化）。"""
    global _SECRET_CACHE
    if _SECRET_CACHE is None:
        secret = os.getenv("JWT_SECRET") or _read_secret_from_env_file()
        if not secret:
            secret = secrets.token_urlsafe(48)
            os.environ["JWT_SECRET"] = secret
            _persist_secret(secret)
        _SECRET_CACHE = secret
    return _SECRET_CACHE


# ===========================================================================
# 签发 / 解析
# ===========================================================================
def create_token(payload: dict, expires_seconds: int = TOKEN_TTL_SECONDS) -> str:
    """签发 JWT。载荷固定包含 user_id / role_id / wallet / class_id / user_name。"""
    now_ts = int(time.time())
    data = {
        "user_id": str(payload.get("user_id") or ""),
        "role_id": int(payload.get("role_id") or 0),
        "wallet": str(payload.get("wallet") or ""),
        "class_id": str(payload.get("class_id") or ""),
        "user_name": str(payload.get("user_name") or ""),
        "iat": now_ts,
        "exp": now_ts + expires_seconds,
    }
    return jwt.encode(data, jwt_secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """验签并解析 JWT；失败 / 过期统一抛 401。返回身份上下文 dict。"""
    try:
        data = jwt.decode(token, jwt_secret(), algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401, detail="登录已过期，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401, detail="无效的登录凭据，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _normalize_ctx(data)


def _normalize_ctx(data: dict) -> dict:
    """把载荷规整为统一的身份上下文结构。"""
    try:
        rid = int(data.get("role_id") or 0)
    except (TypeError, ValueError):
        rid = 0
    return {
        "user_id": str(data.get("user_id") or ""),
        "role_id": rid,
        "wallet": str(data.get("wallet") or ""),
        "class_id": str(data.get("class_id") or ""),
        "user_name": str(data.get("user_name") or ""),
    }


def _parse_bearer(authorization: Optional[str]) -> Optional[str]:
    """从 Authorization 头提取 Bearer token（无则返回 None）。"""
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip() or None
    return authorization.strip() or None


def _ctx_from_legacy_headers(
    x_user_id: Optional[str], x_role_id: Optional[str], x_wallet: Optional[str],
    x_class_id: Optional[str], x_user_name: Optional[str],
) -> Optional[dict]:
    """兼容层：从旧 X-* 自报头构造身份上下文（仅开发回退开关开启时使用）。"""
    if not x_user_id:
        return None
    try:
        rid = int(x_role_id) if x_role_id and str(x_role_id).isdigit() else 0
    except (TypeError, ValueError):
        rid = 0
    uname = x_user_name or ""
    try:
        uname = unquote(uname)
    except Exception:
        pass
    return {
        "user_id": x_user_id,
        "role_id": rid,
        "wallet": x_wallet or x_user_id,
        "class_id": x_class_id or "",
        "user_name": uname,
    }


def resolve_identity(
    authorization: Optional[str],
    x_user_id: Optional[str], x_role_id: Optional[str], x_wallet: Optional[str],
    x_class_id: Optional[str], x_user_name: Optional[str],
) -> Optional[dict]:
    """JWT 解析核心（任务 #18 抽取，供 get_current_user / optional_user /
    tenant 中间件 / tenant.parse_context 复用）：Bearer 验签优先；无 token 时
    仅在回退开关开启时读 X-* 头。失败返回 None（不抛 401，由调用方决策）。"""
    token = _parse_bearer(authorization)
    if token:
        return decode_token(token)
    if settings.auth_dev_header_fallback:
        return _ctx_from_legacy_headers(x_user_id, x_role_id, x_wallet, x_class_id, x_user_name)
    return None


# 兼容别名：抽取前的内部函数名，供潜在历史引用平滑过渡
_resolve_user = resolve_identity


def identity_from_request(request: Request) -> Optional[dict]:
    """从 Request 对象提取鉴权头并解析身份（tenant 中间件 / tenant.py 复用入口）。

    与 get_current_user 的 Header 依赖同口径：Bearer JWT 优先，
    AUTH_DEV_HEADER_FALLBACK 开启时回退 X-* 自报头。
    """
    h = request.headers
    return resolve_identity(
        h.get("authorization"),
        h.get("x-user-id"), h.get("x-role-id"), h.get("x-wallet"),
        h.get("x-class-id"), h.get("x-user-name"),
    )


# ===========================================================================
# FastAPI 依赖
# ===========================================================================
def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(default=None, description="Bearer <JWT>"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_role_id: Optional[str] = Header(default=None, alias="X-Role-Id"),
    x_wallet: Optional[str] = Header(default=None, alias="X-Wallet"),
    x_class_id: Optional[str] = Header(default=None, alias="X-Class-Id"),
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
) -> dict:
    """必须登录：解析 Authorization: Bearer 并验签，失败 / 过期返回 401。

    返回身份上下文：{ user_id, role_id, wallet, class_id, user_name }

    任务 #18：优先复用 request.state._current_user（租户中间件预解析的
    验签结果），全请求生命周期内只验签一次；无缓存时走原路径并回填缓存。
    对外行为（返回结构 / 401 语义）与抽取前完全一致。
    """
    cached = getattr(request.state, "_current_user", None)
    if cached is not None:
        return cached
    ctx = resolve_identity(authorization, x_user_id, x_role_id, x_wallet, x_class_id, x_user_name)
    if ctx is None:
        raise HTTPException(
            status_code=401, detail="未登录或登录已过期，请先登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    request.state._current_user = ctx
    return ctx


def optional_user(
    request: Request,
    authorization: Optional[str] = Header(default=None, description="Bearer <JWT>"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_role_id: Optional[str] = Header(default=None, alias="X-Role-Id"),
    x_wallet: Optional[str] = Header(default=None, alias="X-Wallet"),
    x_class_id: Optional[str] = Header(default=None, alias="X-Class-Id"),
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
) -> Optional[dict]:
    """可选登录：携带有效 token 时返回身份上下文，未登录返回 None。

    任务 #18：与 get_current_user 同样优先读 request.state 缓存（只验签一次）。
    """
    cached = getattr(request.state, "_current_user", None)
    if cached is not None:
        return cached
    ctx = resolve_identity(authorization, x_user_id, x_role_id, x_wallet, x_class_id, x_user_name)
    if ctx is not None:
        request.state._current_user = ctx
    return ctx


def require_role(*role_ids: int):
    """角色受限依赖工厂：仅允许指定角色访问，否则 403。

    用法：user: dict = Depends(require_role(1, 3))  # 仅管理员 / 教师
    """
    allowed = {int(r) for r in role_ids}

    def _dep(user: dict = Depends(get_current_user)) -> dict:
        if int(user.get("role_id") or 0) not in allowed:
            raise HTTPException(status_code=403, detail="角色权限不足，禁止访问该接口")
        return user

    return _dep


# ===========================================================================
# 操作者身份解析辅助（写接口统一从 JWT 上下文解析身份）
# ===========================================================================
# 学生演示钱包（写路径默认身份）：教程进度 / eco 埋点 / 能量发放等
# 历史数据以此口径落库，读侧统计必须并入候选集兼容（见 resolve_wallet_candidates）
LEARNER_WALLET = "0xlearner"


# ===========================================================================
# 钱包候选集助手（一人一钱包隔离：请求钱包 + userId + user_info 登记钱包）
# ===========================================================================
def resolve_wallet_candidates(conn, wallet: str, user_id: str = "") -> list[str]:
    """构造钱包候选集，返回 [wallet 原值, user_id, user_info 登记钱包] 去重。

    口径（一人一钱包隔离）：登录时学生发放专属钱包 stu:{userId}（写回
    user_info.wallet），前端登录后切到本人钱包，写/读路径都以此为口径。
    候选集只并入与请求身份直接相关的钱包：
      - 请求钱包原值；
      - 登录 user_id（JWT wallet=userId 口径）；
      - user_info 中登记的钱包（如学生 stu: 别名）。
    演示学习者钱包 0xlearner 仅在未登录降级（请求钱包为空）时并入；
    **不再无条件并入**——否则不同学生的进度/资产都会混入同一份 0xlearner
    演示数据（跨账号数据相同的根源）。调用方用 `lower(col) IN (...)`
    参数化匹配即可。

    参数：
      conn     已打开的 sqlite 连接（查 user_info 失败时静默降级为基本候选）
      wallet   请求参数 / JWT 上下文中的钱包（通常为 userId 或 '0xlearner'）
      user_id  可选。读参数为演示钱包（如 missions 读 currentWallet）而埋点
               写入用 JWT wallet（userId）时，传入登录 user_id 可把该用户的
               userId 口径数据并入候选（missions T10 场景）。
    """
    raw = (wallet or "").strip()
    seen: list[str] = []

    def _add(v: str) -> None:
        v = (v or "").strip()
        if v and v not in seen:
            seen.append(v)

    _add(raw)
    if user_id:
        # JWT wallet 口径（userId）本身也是合法钱包口径（可能尚未落 user_info）
        _add(user_id)
    # wallet/user_id 可能是 user_id：查其 user_info 登记的钱包一并纳入
    for uid in (user_id, raw):
        u = (uid or "").strip()
        if not u:
            continue
        try:
            row = conn.execute(
                "SELECT wallet FROM user_info WHERE user_id=?", (u,)
            ).fetchone()
            if row:
                _add(str(row[0] or ""))
        except Exception:
            pass  # 表不存在 / 库异常：降级为基本候选，不阻塞统计
    if not raw:
        _add(LEARNER_WALLET)  # 仅未登录降级（请求钱包为空）并入演示钱包
    return seen


def lower_wallet_in(cands: list[str]) -> tuple[str, list[str]]:
    """把候选集转为 `lower(col) IN (?,?,...)` 可用的 (占位符片段, 小写参数列表)。

    用法：h, params = lower_wallet_in(cands)
          sql = f"... WHERE lower(wallet) IN ({h})"  →  execute(sql, params)
    """
    lc = [c.strip().lower() for c in (cands or []) if (c or "").strip()]
    return ",".join("?" * len(lc)), lc


def _is_own_student_alias(user: dict, provided: str) -> bool:
    """是否当前用户本人的学生专属钱包别名（stu:{user_id}，大小写不敏感）。
    登录时由 auth._ensure_student_wallet 发放，与密钥库 / user_info.wallet 同口径。"""
    uid = (user.get("user_id") or "").strip()
    return bool(uid) and (provided or "").strip().lower() == f"stu:{uid}".lower()


def assert_actor_wallet(user: dict, provided: Optional[str], field: str = "wallet") -> str:
    """校验并返回写接口的操作者身份（链上操作钱包）。

    规则（防止伪造他人身份，同时不破坏联盟角色钱包的教学业务）：
      - 请求体未携带身份 → 使用 JWT 上下文钱包；
      - 身份 == 本人（JWT wallet / user_id）→ 通过；
      - 身份为平台内置生态钱包（0xadmin / 0xmetro 等）→ 通过（链上角色操作）；
      - 教师 / 管理员可代任意身份操作（演示 / 管理场景）；
      - 其余情况视为伪造他人身份 → 403。
    """
    p = (provided or "").strip()
    if not p:
        return user.get("wallet") or user.get("user_id") or ""
    if p in (user.get("wallet"), user.get("user_id")):
        return p
    if _is_own_student_alias(user, p):
        return p  # 本人学生专属钱包别名（一人一钱包）
    if p.lower() in BUILTIN_WALLETS:
        return p
    if int(user.get("role_id") or 0) in PRIVILEGED_ROLES:
        return p
    raise HTTPException(status_code=403, detail=f"禁止冒用他人身份：{field} 与当前登录身份不一致")


def ensure_own_wallet(user: dict, provided: Optional[str], field: str = "wallet") -> str:
    """校验钱包归属（学生仅能访问自己的钱包；教师 / 管理员不受限）。

    用于 /grades/my、/grades/auto-draft 等按钱包查询/写入个人数据的接口。
    """
    p = (provided or "").strip()
    if int(user.get("role_id") or 0) in PRIVILEGED_ROLES:
        return p
    if p and p in (user.get("wallet"), user.get("user_id")):
        return p
    if p and _is_own_student_alias(user, p):
        return p  # 本人学生专属钱包别名（一人一钱包）
    raise HTTPException(status_code=403, detail=f"仅能操作本人钱包：{field} 与当前登录身份不一致")
