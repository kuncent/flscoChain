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
import re
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


def _to_addr(value: str, *, create: bool = False) -> str:
    """归一为真实链上地址（延迟 import 以免 keystore / security 循环依赖）。"""
    try:
        from .wallet_id import to_address
        return to_address(value, create=create)
    except Exception:
        return (value or "").strip().lower()


def _is_addr(value: str) -> bool:
    try:
        from .wallet_id import is_address
        return is_address(value)
    except Exception:
        return False


_builtin_addrs_cache: Optional[frozenset] = None


def builtin_addresses() -> frozenset:
    """内置演示 / 机构钱包在链上的真实地址（与别名同等放行）。

    资产台账现在统一按真实地址归属，前端选「地地铁集团」时携带的就是它的地址；
    若只认别名字符串，学生一切到机构钱包就会被 assert_actor_wallet 403。
    """
    global _builtin_addrs_cache
    if _builtin_addrs_cache is None:
        _builtin_addrs_cache = frozenset(
            a for a in (_to_addr(w) for w in BUILTIN_WALLETS) if _is_addr(a)
        )
    return _builtin_addrs_cache

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

    **本函数是中间件入口，任何情况下都不抛异常**：token 无效 / 过期一律视为
    未登录返回 None。旧版在此直接透传 `decode_token` 的 HTTPException(401)，而
    Starlette 的 HTTPException 处理器（ExceptionMiddleware）位于用户中间件**之内**，
    从中间件抛出的 401 会被外层当成未捕获异常 —— 客户端拿到的是
    `500 text/plain "Internal Server Error"`，前端 401 拦截器（跳登录页）永不触发，
    用户在 JWT 过期后只能看到报错、无法自助恢复。改为返回 None 后，401 由
    依赖层（get_current_user）在 ExceptionMiddleware 之内抛出，响应恢复正常。
    """
    h = request.headers
    try:
        return resolve_identity(
            h.get("authorization"),
            h.get("x-user-id"), h.get("x-role-id"), h.get("x-wallet"),
            h.get("x-class-id"), h.get("x-user-name"),
        )
    except HTTPException:
        return None


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
# 钱包候选集助手（一人一钱包隔离：请求钱包 + userId + user_info 登记钱包 + 全部注册别名）
# ===========================================================================
# 以下四个助手是 P0-2（钱包标识四套并存）的收口点：写入侧统一注册别名，
# 读取侧统一按候选集并集匹配，业务 SQL 不再出现 `wallet = ?` 单值等值。


def _student_evm_addr(user_id: str) -> str:
    """取学生专属钱包在密钥库里的真实 0x 地址（链上 from_addr 就是这个值）。

    历史缺口：resolve_wallet_candidates 只返回 [请求值, user_id, user_info.wallet]，
    不含密钥库真实地址，导致链上数据（transactions.from_addr）永远匹配不上（P0-3）。
    任何异常（密钥库不可读 / 未发放钱包）均降级为空串，不阻塞统计。
    """
    uid = (user_id or "").strip()
    if not uid:
        return ""
    try:
        from . import keystore as _ks
        return _ks.get_account_address(_ks.student_alias(uid)) or ""
    except Exception:
        return ""


def _alias_owner(conn, alias: str) -> str:
    """按别名反查归属 user_id（wallet_alias 表）；未登记返回空串。"""
    a = (alias or "").strip().lower()
    if not a:
        return ""
    try:
        row = conn.execute(
            "SELECT user_id FROM wallet_alias WHERE alias=?", (a,)
        ).fetchone()
        return str(row["user_id"] or "") if row else ""
    except Exception:
        return ""  # 表不存在（旧库首次启动）：降级为原行为


def _aliases_of(conn, user_id: str) -> list[str]:
    """取某用户已登记的全部钱包别名（小写）；表不可用时返回空列表。"""
    uid = (user_id or "").strip()
    if not uid:
        return []
    try:
        return [str(r["alias"] or "") for r in conn.execute(
            "SELECT alias FROM wallet_alias WHERE user_id=?", (uid,)
        ).fetchall()]
    except Exception:
        return []


def alias_kind(alias: str, user_id: str) -> str:
    """按别名形态推断 kind（写入 wallet_alias 时记录口径来源）。"""
    a = (alias or "").strip().lower()
    if a.startswith("stu:"):
        return "student_alias"
    if a.startswith("0x") and len(a) == 42:
        return "evm_addr"
    if user_id and a == (user_id or "").strip().lower():
        return "user_id"
    return "other"


def register_wallet_aliases(
    conn, user_id: str, aliases: dict, claimed_by: str = ""
) -> int:
    """注册「别名 → 用户」归属关系（幂等，不越权改写已有归属）。

    aliases: {别名: kind}，kind 取 user_id | student_alias | evm_addr | legacy
    （可用 alias_kind() 自动推断）。传 None / 空串的 kind 会被推断。

    两道安全约束（不能省）：
      - 平台内置演示钱包（BUILTIN_WALLETS：0xlearner / 0xadmin / default …）
        **绝不自动注册**——否则第一个登录的学生就把公共演示钱包的历史数据
        “抢”到自己名下（跳账号数据相同的根源）；此类归属只能走
        claim_legacy_alias（仅特权角色）；
      - 同别名列已属其他用户时 **不覆盖**（INSERT OR IGNORE）：否则一个学生
        登录就能改写别人的归属；重新认领请用 claim_legacy_alias。
    返回新增行数。本函数不提交，由调用方的 get_conn() 上下文统一 commit。
    """
    uid = (user_id or "").strip()
    if not uid or not aliases:
        return 0
    from .db import now as _now
    added = 0
    for raw_alias, kind in dict(aliases).items():
        a = (str(raw_alias or "")).strip().lower()
        if not a or a in BUILTIN_WALLETS:
            continue  # 内置演示钱包不自动归属（只能显式认领）
        cur = conn.execute(
            "INSERT OR IGNORE INTO wallet_alias(alias, user_id, kind, created_at, claimed_by) "
            "VALUES (?,?,?,?,?)",
            (a, uid, str(kind or "") or alias_kind(a, uid), _now(),
             (claimed_by or "").strip()),
        )
        added += int(cur.rowcount or 0)
    return added


def claim_legacy_alias(conn, alias: str, user_id: str, claimed_by: str) -> dict:
    """管理员显式认领历史共享钱包（如演示钱包 0xlearner）归属。

    与 register_wallet_aliases 的区别：本函数 **可改写已有归属**（因此仅限
    特权角色调用，并落 claimed_by / 时间审计）。用于把一人一钱包上线前写在
    公共演示钱包名下的历史数据归回真实学生。
    """
    a = (alias or "").strip().lower()
    uid = (user_id or "").strip()
    if not a or not uid:
        raise ValueError("alias / user_id 不能为空")
    from .db import now as _now
    prev = _alias_owner(conn, a)
    conn.execute(
        "INSERT INTO wallet_alias(alias, user_id, kind, created_at, claimed_by) "
        "VALUES (?,?,'legacy',?,?) "
        "ON CONFLICT(alias) DO UPDATE SET user_id=excluded.user_id, "
        "kind='legacy', claimed_by=excluded.claimed_by",
        (a, uid, _now(), (claimed_by or "").strip()),
    )
    return {
        "alias": a, "user_id": uid, "previous_owner": prev,
        "claimed_by": (claimed_by or "").strip(),
    }


# 详情字段中不得入库的凭据类键名（P1-27：前端上报 axios error.config 时含完整 JWT）
_SECRET_KEYS = (
    "authorization", "proxy-authorization", "cookie", "set-cookie",
    "x-user-id", "x-user-name", "x-wallet", "x-class-id", "x-role-id",
    "token", "accesstoken", "refreshtoken", "jwt", "secret", "password",
    "passwordencode", "privatekey", "apikey", "accesskey",
)
_SECRET_KEY_RE = re.compile(
    r'("(?:' + "|".join(_SECRET_KEYS) + r')")\s*:\s*"(?:\\.|[^"\\])*"',
    re.IGNORECASE,
)
_BEARER_RE = re.compile(r'(bearer\s+)[a-z0-9._~+/-]+=*', re.IGNORECASE)


def redact_secrets(text: str, limit: int = 2000) -> str:
    """入库 / 回显前把凭据类内容打码（P1-27）。

    覆盖两类泄露：① JSON 形式自报头/配置（`"Authorization": "Bearer x.y.z"`、
    `"X-User-Id": "<uuid>"` 等）；② 裸 `Bearer x.y.z` 片段（日志 / 堆栈文本）。
    非字符串入参先转 str；结果为空则返回空串。只做字面打码，不试图解析结构。
    """
    if text is None:
        return ""
    s = text if isinstance(text, str) else str(text)
    if not s:
        return ""
    s = _SECRET_KEY_RE.sub(lambda m: f'{m.group(1)}: "***"', s)
    s = _BEARER_RE.sub(lambda m: m.group(1) + "***", s)
    return s[:limit]


def decode_claims_unverified(token: str) -> dict:
    """不验签解 JWT 载荷（仅用于存量日志的操作人回填 / 审计，不作任何鉴权判断）。

    失败 / 非 JWT 返回空 dict。注：不验签意味着载荷可被伪造，因此本函数的结果
    只用于离线归因（且需 user_id 能在 user_info / wallet_alias 中对上人才生效），
    绝不得用于权限判定。
    """
    t = (token or "").strip()
    if not t:
        return {}
    try:
        data = jwt.decode(t, options={"verify_signature": False})
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def resolve_wallet_candidates(conn, wallet: str, user_id: str = "") -> list[str]:
    """构造钱包候选集（本人全部口径并集，去重保序）。

    口径（一人一钱包隔离）：登录时学生发放专属钱包 stu:{userId}（写回
    user_info.wallet），前端登录后切到本人钱包，写/读路径都以此为口径。
    候选集只并入与请求身份直接相关的钱包：
      - 请求钱包原值；
      - 登录 user_id（JWT wallet=userId 口径）；
      - user_info 中登记的钱包（如学生 stu: 别名）；
      - **wallet_alias 表中该用户注册的全部别名**（P0-2）；
      - **该学生密钥库里的真实 0x 地址**（P0-3：链上 from_addr 就是这个值）。
    演示学习者钱包 0xlearner 仅在未登录降级（请求钱包为空）或管理员显式
    认领（claim_legacy_alias）后并入；**不再无条件并入**——否则不同学生的
    进度/资产都会混入同一份 0xlearner 演示数据（跳账号数据相同的根源）。
    调用方用 `lower(col) IN (...)` 参数化匹配即可。

    参数：
      conn     已打开的 sqlite 连接（查 user_info / wallet_alias 失败时静默降级）
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
    # P0-2：以 user_id 为稳定主键，先把“请求别名 → 归属用户”反查出来，
    # 再把该用户已注册的全部别名 + 密钥库真实地址并入（候选集对等）
    principal = (user_id or "").strip() or _alias_owner(conn, raw) \
        or _owner_in_user_info(conn, raw)
    if principal:
        for a in _aliases_of(conn, principal):
            _add(a)
        _add(_student_evm_addr(principal))
    if not raw:
        _add(LEARNER_WALLET)  # 仅未登录降级（请求钱包为空）并入演示钱包
    # 资产台账已统一按真实地址落库：候选集必须同时覆盖本人各别名的地址，
    # 否则会出现「以别名发行得、以地址查不到余额」的分裂。
    # 只对能唯一指向本人的口径做地址化：公共演示钱包的地址属于共享账户，
    # 未被显式认领时并入会把全班数据混到一人身上（P0-2 同口径）。
    # 例外：调用方**显式**以该演示钱包作为请求钱包（raw 就是它），别名与其
    # 地址本就是同一账户的两套标识，不并入反而让地址口径写入的数据读不到。
    _raw_low = raw.lower()
    for c in list(seen):
        s = (c or "").strip().lower()
        if not s or _is_addr(s):
            continue
        if s in BUILTIN_WALLETS and s != _raw_low:
            continue
        if s != _raw_low and principal and _alias_owner(conn, s) != principal:
            continue  # 不是本人的别名：不地址化，避免把机构钱包摸进学生候选集
        addr = _to_addr(s)
        if addr and addr != s:
            _add(addr)
    return seen


def identifying_wallets(conn, wallet: str = "", user_id: str = "") -> list[str]:
    """候选集中「能唯一指向一个人」的那部分（用于跨表**定位/改写某一行**）。

    resolve_wallet_candidates 是为「统计并集」设计的：请求值原样入候选，因此
    共享演示钱包（0xlearner 等）也会进去。读统计没关系，但拿它去 UPDATE 或
    接管某一行的归属时，0xlearner 名下可能挂着几十个学生的记录，命中任意一条
    都是张冠李戴 —— 所以必须剔除。已被管理员显式认领（wallet_alias 登记到本人）
    的别名除外，那是明确的数据归属决定。
    """
    uid = (user_id or "").strip()
    owned = {a.strip().lower() for a in _aliases_of(conn, uid) if a}
    out: list[str] = []
    for c in resolve_wallet_candidates(conn, wallet, uid):
        s = (c or "").strip()
        if not s or s in out:
            continue
        if s.lower() in BUILTIN_WALLETS and s.lower() not in owned:
            continue
        out.append(s)
    return out


def _owner_in_user_info(conn, alias: str) -> str:
    """user_info 里按登记钱包反查 user_id（wallet_alias 未命中时的兼容路径）。

    旧库 / 未重跑登录的用户可能只有 user_info 一行，而候选集要能对他生效。
    """
    a = (alias or "").strip()
    if not a:
        return ""
    try:
        row = conn.execute(
            "SELECT user_id FROM user_info WHERE lower(wallet)=lower(?) OR user_id=? LIMIT 1",
            (a, a),
        ).fetchone()
        return str(row["user_id"] or "") if row else ""
    except Exception:
        return ""


def resolve_principal(conn, wallet: str, user_id: str = "") -> str:
    """解析一个钱包标识背后的稳定主体 ID（P0-2 读写收口入口）。

    优先 JWT user_id → wallet_alias 归属 → user_info 反查；都查不到返回空串
    （调用方应回退到钱包原值，不注入任何默认身份）。
    """
    uid = (user_id or "").strip()
    if uid:
        return uid
    return _alias_owner(conn, wallet) or _owner_in_user_info(conn, wallet)


def principal_of(conn, wallet: str = "", student_id: str = "") -> str:
    """一行数据到底属于哪个稳定主体（P0-2 归并 / 去重的唯一判据）。

    为什么不能拿 student_id 字符串当“一人的主键”：一人一钱包上线前，系统
    草稿用 `W{wallet[:10]}` 造学号（库里因此有 W0xlearner / Wstu:0ae778 这种行），
    而教师录的是真实学号 —— student_grades 带 UNIQUE(student_id, course)，
    所以上述两行能共存，统计上不归并就会把一个人算两次。

    查找顺序：非内置钱包反查别名表 / user_info → 学号反查 → 钱包原值反查。
    内置演示钱包（0xlearner 等）**不参与钱包反查**：它在被管理员显式认领前
    不属于任何一人，否则会把全班数据归到同一个人名下。
    都查不到返回空串（调用方应保持原样，不猜身份）。
    """
    w = (wallet or "").strip()
    if w and w.lower() not in BUILTIN_WALLETS:
        p = _alias_owner(conn, w) or _owner_in_user_info(conn, w)
        if p:
            return p
    for k in ((student_id or "").strip(), w):
        if k:
            p = _alias_owner(conn, k) or _owner_in_user_info(conn, k)
            if p:
                return p
    return ""


def is_placeholder_student_id(sid: str, wallet: str = "") -> bool:
    """该学号是不是系统合成的**占位主键**（`W` + 钱包前缀，见 grades._refresh_draft）。

    占位学号只携带钱包信息、不携带人的信息，匹配 / 覆盖 / 排名都得降级处理。
    库里同时出现过 `W0xlearner` / `Wstu:0ae778` / `W0ae7783d-d` 三种截断长度，
    故判定按「W 后段是否为该钱包的前缀」而不是硬拼 10 位。

    **无从对照钱包时一律判 False**：真实学号也可能以 W 开头（如姓拼音），
    误判会把人的数据当垃圾改写 —— 宁可保守。调用方请尽量传 wallet 口径。
    """
    s = str(sid or "").strip()
    w = str(wallet or "").strip()
    if not s or not w or s[0] not in ("W", "w"):
        return False
    body = s[1:].strip()
    return bool(body) and w.startswith(body)


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

    返回值一律是**真实链上地址**（0x + 40 hex）：资产归属、能量流水、角色绑定
    从此只有一套路数，不会再把 `stu:0ae7783d-d59d-…` 这种内部别名写进资产表。

    规则（防止伪造他人身份，同时不破坏联盟角色钱包的教学业务）：
      - 请求体未携带身份 → 使用 JWT 上下文钱包；
      - 身份 == 本人（JWT wallet / user_id / stu: 专属别名）→ 通过；
      - 身份为平台内置生态钱包（0xadmin / 0xmetro 或其真实地址）→ 通过（链上角色操作）；
      - 教师 / 管理员可代任意身份操作（演示 / 管理场景）；
      - 其余情况视为伪造他人身份 → 403。
    """
    p = (provided or "").strip()
    if not p:
        base = user.get("wallet") or user.get("user_id") or ""
        return _to_addr(base, create=True) or base
    pl = p.lower()
    pc = _to_addr(p, create=True)
    if pl in BUILTIN_WALLETS or pc in builtin_addresses():
        return pc  # 内置演示 / 机构钱包（别名与真实地址同等放行）
    uid = (user.get("user_id") or "").strip()
    own = {user.get("wallet") or "", uid, f"stu:{uid}" if uid else ""}
    own_addrs = {_to_addr(x, create=True) for x in own if x}
    if pc in own_addrs:
        return pc
    if int(user.get("role_id") or 0) in PRIVILEGED_ROLES:
        return pc
    raise HTTPException(status_code=403, detail=f"禁止冒用他人身份：{field} 与当前登录身份不一致")


def owns_wallet(user: dict, provided: str) -> bool:
    """provided 是否落在本人候选集内（含注册别名 / 密钥库真实地址 / 已认领历史钱包）。

    P0-2 配套：身份判定不能再只比 user_id / stu: 两个硬口径，否则学生以自己
    的真实链上地址访问个资接口会被误判 403。
    """
    p = (provided or "").strip()
    if not p:
        return False
    uid = (user.get("user_id") or "").strip()
    try:
        from .db import get_conn
        with get_conn() as conn:
            cands = resolve_wallet_candidates(conn, user.get("wallet") or "", uid)
    except Exception:
        cands = []
    lowered = {str(c).strip().lower() for c in cands if str(c or "").strip()}
    if p.lower() in lowered:
        return True
    # 资产口径已地址化：本人别名的真实地址同样算本人
    return _to_addr(p) in {_to_addr(x) for x in lowered}


def ensure_own_wallet(user: dict, provided: Optional[str], field: str = "wallet") -> str:
    """校验钱包归属（学生仅能访问自己的钱包；教师 / 管理员不受限）。

    用于 /grades/my、/grades/auto-draft 等按钱包查询/写入个人数据的接口。
    硬口径（user_id / JWT wallet / stu: 专属别名）未命中时，再查一次本人
    候选集（P0-2：注册别名 / 密钥库地址 / 已认领的历史演示钱包）。

    空钱包 = 「看本人」：由 JWT 身份派生本人真实地址（前端不再写死 0xlearner
    作默认值，未登录 / 刚切换账号时不能因为传空就 403）。
    """
    p = (provided or "").strip()
    if not p:
        return assert_actor_wallet(user, "", field)
    if int(user.get("role_id") or 0) in PRIVILEGED_ROLES:
        return p
    if p and p in (user.get("wallet"), user.get("user_id")):
        return p
    if p and _is_own_student_alias(user, p):
        return p  # 本人学生专属钱包别名（一人一钱包）
    if p and owns_wallet(user, p):
        return p  # 本人其余口径（P0-2 收口）
    raise HTTPException(status_code=403, detail=f"仅能操作本人钱包：{field} 与当前登录身份不一")
