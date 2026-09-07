"""跨专业综合实训平台 登录代理。

对接外部 API 基址：https://ecosim.sztzjy.com:166/server
提供接口：
  1. POST /api/auth/encrypt                  明文密码 RSA 加密（密码走请求体，不再走 query）
  2. POST /api/auth/login                     用户登录（账号密码 / 智云 SSO Token），成功附带平台 JWT（token 字段）
  3. GET  /api/auth/session                   会话校验（对 Bearer JWT 真实验签，不再只看头是否存在）

登录方式说明：
  - 账号密码：传 username + passwordEncode（通过 /encrypt 获取）
  - 智云 SSO：URL 携带 token 参数时优先用 token 登录（POST body 传 TOKEN 字段）

鉴权说明：
  - 登录成功后返回平台自签 JWT（24h 有效），前端存 localStorage 并由拦截器注入 Authorization: Bearer；
  - 后端全部写接口基于该 JWT 验签（见 app/security.py），不再信任前端自报的 X-* 身份头。
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel

from .. import keystore as ks
from ..config import settings
from ..db import get_conn, has_table, init_db, now
from ..roster import (
    HINT_ROSTER_EMPTY,
    bind_teacher_scope,
    candidates_for_student,
    class_allowed_in_scope,
    current_identity,
    norm_class,
    norm_school,
    resolve_class_scope,
    roster_students,
    self_student_row,
    teacher_scope,
)
from ..security import (
    claim_legacy_alias,
    create_token,
    decode_token,
    get_current_user,
    lower_wallet_in,
    register_wallet_aliases,
    require_role,
    resolve_wallet_candidates,
    _parse_bearer,
)
from ..wallet_id import is_address, to_address

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 搭链教程总步数（chain_tutorial_progress.step 1..10）：看板百分比的唯一口径
# （旧实现三处各写一份字面量 10，其中一处还写成 `... if 10 else 0` 恒真分支）
TUTORIAL_TOTAL_STEPS = 10

# 确保 user_info 表已创建（init_db 在应用启动时已调用，这里做防御性初始化）
init_db()


def _upsert_user_info(data: dict) -> bool:
    """登录成功后把用户信息持久化到 user_info 表（问题清单 P0-4 修复点）。

    字段对应（SSO `data` → 列）：userId→user_id（主键）、name→name、
    username→username、studentId→student_id、roleId→role_id、classId→class_id、
    **schoolId→school_id（成绩归档的唯一边界字段）**、schoolName→school_name、
    collegeId→college_id、majorId→major_id；accessToken 不落库（平台自签 JWT）。

    ⚠ 实测口径与设计不一致（勿按列名想当然）：SSO 对体验账号返的
    `username` 是**姓名**（“赵佳正”/“老师1号”），`studentId` 是**登录账号**
    （手机号 / 工号）。所以“按登录账号找人”只能查 `student_id` 列，
    查 `username` 会恒空（旧版“取错字段”就出在这里）。

    - 按 user_id 主键 upsert（不存在则新增，存在则更新 + login_count +1）
    - 教师和学生的 class_id 含义不同：学生=所属班级，教师=管理班级
    - wallet 用 userId（学习行为/实训进度/成绩按用户隔离，不随角色钱包切换变化）
    - 班级经 roster.norm_class 规整（SSO 以 "0" 表示“无班级”，P0-1）；本次未返
      回班级时**沿用库中原值**，不把已绑定的班级抹成空串
    - 学校同理走 norm_school（"0" / 0.0 / 带空格都是“无学校”占位，不能当成
      一个真学校写进去）；SSO 本次没返学校时**沿用库中原值**，否则教师
      的归档边界会凭空退化（成绩按学校归档全靠这一列）
    - 同步注册钱包别名（P0-2）：后续所有读写由 resolve_wallet_candidates
      从 wallet_alias 取本人口径并集

    异常向上抛出，由调用方记录并暴露——旧版在 login 里用
    `except Exception: pass` 把 “17 values for 16 columns” 静默吞了一整个版本，
    导致 user_info 全库 0 行（P0-4），是三块看板恒空的直接原因。
    """
    uid = str(data.get("userId") or "")
    if not uid:
        return False
    ts = now()
    role_id = int(data.get("roleId") or 0)
    role_map = {1: "管理员", 3: "教师", 4: "学生"}
    role_name = data.get("roleName") or role_map.get(role_id, "未知")
    class_id = norm_class(data.get("classId"))
    # 归档边界字段：SSO 的 schoolId → school_id（与 classId 同一套占位清洗）
    school_id = norm_school(data.get("schoolId"))
    school_name = str(data.get("schoolName") or "").strip()
    # 钱包口径：登录账号本人的**真实链上地址**（0x + 40 hex）。
    #   历史上这里直写 userId（或学生 stu: 别名），导致资产表里出现
    #   `stu:0ae7783d-d59d-40e1-…` 这种带冒号 / 连字符的内部别名：同一人多套
    #   归属（P0-2）、前端无法复制跳转、与链上 from_addr 对不上（P0-3）。
    #   userId 本身仍在 wallet_alias / resolve_wallet_candidates 候选集里，
    #   历史行与成绩 / 进度读取口径不受影响。
    wallet = _own_wallet(uid, role_id)
    # wallet 身份口径说明（一人一钱包，勿改成每次登录都覆盖）：
    #   - 学生登录时发放专属钱包 stu:{userId}（_ensure_student_wallet 将它的
    #     真实地址写回 user_info.wallet），前端登录后切到本人钱包；
    #   - 读路径（成绩 / 成就 / 班级看板）走 security.resolve_wallet_candidates
    #     候选集（请求钱包 + userId + user_info 登记钱包 + wallet_alias 全部别名，
    #     不再无条件并入 0xlearner）；
    #   - 本函数保持旧语义：首次登录写 wallet=userId；已有记录不覆盖
    #     （仅当现有 wallet 为空时补写 userId），保留历史旧值不迁移。
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT wallet, login_count, class_id, school_id, school_name FROM user_info WHERE user_id=?",
            (uid,),
        ).fetchone()
        if existing:
            # 已有记录：钱包按「能归一就归一」处理（旧别名 / userId → 真实地址），
            # 但已是合法地址且与本人生成地址不同的（外部配置的机构钱包）不重写
            cur_w = (existing["wallet"] or "").strip()
            wallet = cur_w if is_address(cur_w) else _own_wallet(uid, role_id)
            class_id = class_id or norm_class(existing["class_id"])
            # 学校同理：SSO 这次没返（或返了占位值）就沿用库里已存的，不把已定的
            # 学校抹空 —— 抹空后教师就从 school 退到 class 口径（实测曾发生）
            school_id = school_id or norm_school(existing["school_id"])
            school_name = school_name or str(existing["school_name"] or "").strip()
            conn.execute(
                """UPDATE user_info SET username=?, name=?, role_id=?, role_name=?,
                   student_id=?, class_id=?, school_id=?, school_name=?,
                   college_id=?, major_id=?, wallet=?, login_count=login_count+1,
                   last_login_at=?, updated_at=? WHERE user_id=?""",
                (str(data.get("username") or ""), str(data.get("name") or ""),
                 role_id, role_name, str(data.get("studentId") or ""),
                 class_id, school_id, school_name,
                 norm_class(data.get("collegeId")),
                 norm_class(data.get("majorId")),
                 wallet,
                 ts, ts, uid),
            )
        else:
            # 16 列 = 15 个占位符 + 1 个常量 login_count=1（列序：前 12 列 →
            # login_count → last_login_at/created_at/updated_at）。
            # 历史事故：多写一个 ? → “17 values for 16 columns”，每次登录插入必抛，
            # 又被调用方 except: pass 吞掉 → user_info 全库 0 行（P0-4）。
            conn.execute(
                """INSERT INTO user_info
                   (user_id, username, name, role_id, role_name, student_id, class_id,
                    school_id, school_name, college_id, major_id, wallet,
                    login_count, last_login_at, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?, ?,1,?,?,?)""",
                (uid, str(data.get("username") or ""), str(data.get("name") or ""),
                 role_id, role_name, str(data.get("studentId") or ""),
                 class_id, school_id, school_name,
                 norm_class(data.get("collegeId")),
                 norm_class(data.get("majorId")),
                 wallet,  # userId 作为学习行为追踪标识
                 ts, ts, ts),
            )
        # P0-2：本次登录涉及的口径同步入别名表（内置演示钱包自动跳过）
        # 别名只注册 user_id / 钱包 / student_id 三类“可定位到人”的口径；
        # 不注册 username / 班级 / 学校（它们是属性不是身份，班级当钱包曾污染台账）
        register_wallet_aliases(conn, uid, {
            uid: "user_id",
            wallet: "evm_addr",
            str(data.get("studentId") or ""): "student_id",
        })
    return True

# ===========================================================================
# 学生钱包（一人一钱包）自动发放
# ===========================================================================
# 演示学习钱包（写路径历史口径）：仅它被视为"可被学生专属钱包替换"的演示别名
_DEMO_LEARNER_WALLET = "0xlearner"


def _own_wallet(user_id: str, role_id: int) -> str:
    """登录账号本人的真实链上地址（一人一钱包，避开同一人两套地址）。

    - 学生：直接取 / 发放 `stu:{uid}` 学生钱包地址（与 `_ensure_student_wallet` 同口径，
      不再先创建一个与 `stu:` 并行的裸 user_id 账户）；
    - 教师 / 管理员：取 / 发放与 user_id 同名的密钥库账户地址。
    """
    uid = (user_id or "").strip()
    if not uid:
        return ""
    if int(role_id or 0) == 4:
        try:
            _alias, addr = ks.provision_student_wallet(uid)
            if addr:
                return addr
        except Exception:
            logger.exception("学生钱包发放失败 uid=%s", uid)
    return to_address(uid, create=True) or uid


def _ensure_student_wallet(user_id: str, role_id: int) -> tuple:
    """登录 / 会话恢复后为学生发放专属钱包，并把它的**真实链上地址**写回 user_info.wallet。

    口径（修「资产钱包里出现 stu:xxx 别名」）：
      - 仅学生角色（role_id=4）自动发放；教师 / 管理员沿用账号钱包口径；
      - `stu:{user_id}` 只是密钥库里的**别名（键名）**，用于反查私钥与展示友好名；
        user_info.wallet 与资产表一律存它的真实地址 0x…（无冒号 / 连字符）；
      - 已有合法地址且与本人学生钱包地址不同的（外部配置的机构钱包）不覆盖；
      - 两个口径（别名 + 地址）都登记进 wallet_alias，读侧候选集才能同时命中
        历史别名行与链上地址行（P0-2 / P0-3）。

    返回 (别名或 None, 链上地址或 None)；provision / 写库失败均不抛出，
    不阻断登录主流程（下次登录幂等重试）。
    """
    uid = (user_id or "").strip()
    if not uid or int(role_id or 0) != 4:
        return None, None
    try:
        alias = ks.student_alias(uid)
    except ValueError:
        return None, None
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT wallet FROM user_info WHERE user_id=?", (uid,)
            ).fetchone()
    except Exception:
        row = None  # 表不可用等异常：降级为仅 provision，不写库
    current = (row["wallet"] or "").strip() if row else ""
    # 发放 / 补齐学生钱包（幂等：同一别名永远对应同一地址）
    try:
        new_alias, addr = ks.provision_student_wallet(uid)
    except Exception:
        return alias, None
    cur_l = current.lower()
    # 外部指定的合法地址（非本人生成地址、也不是旧 stu: 别名）：视为已有真实钱包，不覆盖
    if cur_l and cur_l != new_alias.lower() and is_address(cur_l) and cur_l != (addr or "").lower():
        return alias, current
    if row and cur_l != (addr or "").lower() and addr:
        try:
            with get_conn() as conn:
                conn.execute(
                    "UPDATE user_info SET wallet=?, updated_at=? WHERE user_id=?",
                    (addr, now(), uid),
                )
        except Exception:
            # 写库失败不影响登录（下次登录幂等重试），但必须留下痕迹：
            # 静默 pass 会让 user_info.wallet 停在旧别名而无人知晓（P0-4 同类问题）
            logger.exception("学生钱包地址写回 user_info 失败 uid=%s", uid)
    # P0-2：把本次发放的两个口径登记进别名表，读侧候选集才能覆盖到
    # 链上真实地址（stu: 别名只是密钥库键名，链上 from_addr 存的是 0x 地址）
    try:
        with get_conn() as conn:
            register_wallet_aliases(conn, uid, {
                new_alias: "student_alias",
                addr or "": "evm_addr",
            })
    except Exception:
        logger.exception("学生钱包别名登记失败 uid=%s", uid)
    return new_alias, addr


# 外部 SSO API 响应通用结构：{ code, msg, data }
# code == 200 表示成功，其余视为失败。


def _external_base() -> str:
    """返回外部 API 基址（去除尾部斜杠）。"""
    return (settings.external_api_base or "").rstrip("/")


def _unwrap(resp_json: dict) -> dict:
    """拆解外部 API 通用响应：失败抛 502，成功返回 data 字段（或整对象）。"""
    code = resp_json.get("code")
    if code != 200:
        msg = resp_json.get("msg") or "外部 SSO 服务返回错误"
        raise HTTPException(status_code=502, detail=f"[SSO {code}] {msg}")
    return resp_json


# ===========================================================================
# 1. 明文密码加密（POST：密码走请求体，避免进入 URL / 访问日志）
# ===========================================================================
class EncryptReq(BaseModel):
    pwd: str  # 明文密码（仅转发给外部 SSO 加密，不落盘 / 不记录日志）


@router.post("/encrypt")
async def encrypt_pwd(req: EncryptReq):
    """对应外部 GET /api/user/encrypt?pwd=xxx（本端改为 POST 接收密码）。"""
    base = _external_base()
    if not base:
        raise HTTPException(status_code=500, detail="EXTERNAL_API_BASE 未配置")
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.get(f"{base}/api/user/encrypt", params={"pwd": req.pwd})
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"无法连接 SSO 服务：{e}")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"SSO 加密接口 HTTP {r.status_code}")
    data = _unwrap(r.json())
    return {"msg": data.get("msg"), "data": data.get("data")}


# ===========================================================================
# 2. 用户登录（账号密码 / 智云 SSO）
# ===========================================================================
class LoginReq(BaseModel):
    """登录请求：两种登录方式二选一。

    - 账号密码登录：传 username + passwordEncode（通过 /encrypt 获取）
    - 智云 SSO 登录：传 TOKEN（URL 参数 ?token=xxx 携带时优先使用）
    """
    username: Optional[str] = None
    passwordEncode: Optional[str] = None
    TOKEN: Optional[str] = None


@router.post("/login")
async def login(req: LoginReq):
    """对应外部 POST /api/user/login（application/x-www-form-urlencoded）。

    成功返回：{ userId, name, username, studentId, accessToken, roleId, ... }
    本路由在原数据基础上回填 `roleName` 便于前端直接判断角色。
    """
    base = _external_base()
    if not base:
        raise HTTPException(status_code=500, detail="EXTERNAL_API_BASE 未配置")

    # 构造 form 表单：SSO 优先；未传 TOKEN 走账号密码
    if req.TOKEN:
        form = {"TOKEN": req.TOKEN}
    elif req.username and req.passwordEncode:
        form = {"username": req.username, "passwordEncode": req.passwordEncode}
    else:
        raise HTTPException(status_code=400, detail="请提供 TOKEN 或 (username + passwordEncode)")

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.post(
                f"{base}/api/user/fsoc/login",
                data=form,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"无法连接 SSO 服务：{e}")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"SSO 登录接口 HTTP {r.status_code}")

    body = r.json()
    if body.get("code") != 200:
        # 外部接口在登录失败时返回 401 + msg，这里把 msg 透传给前端
        msg = body.get("msg") or "登录失败"
        code = int(body.get("code") or 401)
        raise HTTPException(status_code=code if code in (400, 401, 403) else 401, detail=msg)

    data = body.get("data") or {}
    # 回填角色名（roleId: 1=管理员, 3=教师, 4=学生）
    rid = data.get("roleId")
    role_map = {1: "管理员", 3: "教师", 4: "学生"}
    data["roleName"] = role_map.get(rid, "未知")
    # P0-1：SSO 用 "0" / null 表示「无班级」，规整后再入库与签发 JWT，
    # 避免把 "0" 当成真实班级写进 user_info（后续 `WHERE class_id='0'` 恒 0 行）
    data["classId"] = norm_class(data.get("classId"))
    # 学校同样规整后再回给前端 / 入库：SSO 用 0 / "0" / null 表示「无学校」，
    # 而学校是**成绩归档的唯一边界字段**，写进一个假学校（如 "0"）会让教师
    # 边界看似存在实则对不上任何人（前端会看到“本校 0 · 0 人”）
    data["schoolId"] = norm_school(data.get("schoolId"))
    data["schoolName"] = str(data.get("schoolName") or "").strip()
    # wallet 口径：登录账号本人的真实链上地址（前端「我的钱包」与资产写入
    # 都用它；userId 仍在候选集内，历史学习行为数据不会丢）
    own_wallet = _own_wallet(str(data.get("userId") or ""), rid) \
        or str(data.get("userId") or "")
    data["wallet"] = own_wallet
    # 持久化用户信息到 user_info 表（用于教师按班级查看学生成绩 / 班级整体进度）
    # P0-4：不再 `except Exception: pass`。写库失败必须进日志，并在响应里
    # 以 roster_ok=false 显式暴露——旧版正是这里吞掉了 "17 values for 16
    # columns"，user_info 全库 0 行，三块看板恒空却无人察觉。
    try:
        roster_ok = _upsert_user_info(data)
    except Exception:
        roster_ok = False
        logger.exception("登录用户信息持久化失败 userId=%s", data.get("userId"))
    data["roster_ok"] = bool(roster_ok)
    # 学生钱包（一人一钱包）：登录成功后自动发放 / 解析学生专属钱包。
    # data["wallet"] 已是本人真实地址；student_wallet（别名）仅供展示与密钥库反查。
    sw_alias, sw_addr = None, None
    try:
        sw_alias, sw_addr = _ensure_student_wallet(
            str(data.get("userId") or ""), int(rid or 0)
        )
    except Exception:
        sw_alias, sw_addr = None, None
    if sw_alias:
        data["student_wallet"] = sw_alias
        data["student_wallet_address"] = sw_addr or ""
    # JWT 里的 wallet 必须与 user_info.wallet 完全一致（前端「我的钱包」/ 资产写入
    # / 角色绑定三处共用同一口径），学生以发放后的学生钱包地址为准
    if sw_addr:
        own_wallet = sw_addr
        data["wallet"] = own_wallet
    # 签发平台 JWT（24h 有效）：后续所有接口的身份凭据，前端存入 localStorage 后由拦截器注入
    try:
        data["token"] = create_token({
            "user_id": str(data.get("userId") or ""),
            "role_id": int(rid or 0),
            "wallet": own_wallet,
            "class_id": str(data.get("classId") or ""),
            "user_name": str(data.get("name") or data.get("username") or ""),
        })
    except Exception:
        data["token"] = ""  # 签发失败不阻断登录（前端会话恢复时会引导重新登录）
    return data


# ===========================================================================
# 3. 会话校验（对 Bearer JWT 真实验签）
# ===========================================================================
@router.get("/session")
async def check_session(
    authorization: Optional[str] = Header(default=None, description="Bearer <JWT>"),
):
    """会话校验：解析 Authorization: Bearer 并对 JWT 真实验签。

      - 验签成功：返回 active=true 及**从 user_info 回查的身份字段**（含学校 / 班级）；
      - 无 token / 验签失败 / 过期：返回 active=false，前端据此引导账号密码登录。

    为什么这里要回查库而不是只验签（P1-33）：平台 JWT 载荷只存
    user_id / role_id / wallet / class_id / user_name，**不存 school_id**（学校必须
    以库为准，避免把机构信息写进可被客户端解读的 token）。旧版本接口只回
    userId/roleId，前端会话恢复时只能拿登录时的 localStorage 缓存 ——
    一旦学校 / 班级在后台被改绑（或当初 SSO 没返），前端就永远拿着旧值或空值，
    表现为“教师端明明有学校却显示未定”。现在把权威值回显，前端据此刷新缓存。

    本接口不调用任何外部服务，零外部依赖、无网络副作用。
    """
    token = _parse_bearer(authorization)
    if token:
        try:
            ctx = decode_token(token)
        except HTTPException:
            ctx = None
        if ctx and ctx.get("user_id"):
            role_map = {1: "管理员", 3: "教师", 4: "学生"}
            rid = int(ctx.get("role_id") or 0)
            # 学生钱包别名补齐（旧会话 / 旧版本登录的用户在会话恢复时也能获得钱包）
            sw_alias, sw_addr = None, None
            try:
                sw_alias, sw_addr = _ensure_student_wallet(ctx.get("user_id") or "", rid)
            except Exception:
                sw_alias, sw_addr = None, None
            # 从花名册回查权威归档字段（查不到就退到 JWT，字段全空而非乱猜）
            ident: dict = {}
            try:
                with get_conn() as conn:
                    ident = current_identity(conn, ctx) or {}
            except Exception:
                logger.exception("会话回查 user_info 失败 userId=%s", ctx.get("user_id"))
            return {
                "active": True,
                "userId": ctx["user_id"],
                "roleId": rid or None,
                "roleName": role_map.get(rid, "未知"),
                # ↓ 身份 / 归档字段（与登录响应同名，前端可直接覆盖本地缓存）
                "name": ident.get("name") or ctx.get("user_name") or "",
                "username": ident.get("username") or "",
                "studentId": ident.get("student_id") or "",
                "classId": ident.get("class_id") or ctx.get("class_id") or "",
                "schoolId": ident.get("school_id") or "",
                "schoolName": ident.get("school_name") or "",
                "collegeId": ident.get("college_id") or "",
                "majorId": ident.get("major_id") or "",
                "wallet": sw_addr or ident.get("wallet") or ctx.get("wallet") or "",
                "student_wallet": sw_alias or "",
                "student_wallet_address": sw_addr or "",
                "message": "已检测到保持登录的会话，正在恢复登录态",
            }

    return {
        "active": False,
        "userId": None,
        "roleId": None,
        "roleName": None,
        "message": "未检测到有效登录会话，请使用账号密码登录",
    }


# ===========================================================================
# 4. 班级学生列表（教师查看同班学生 + 实训进度）
# ===========================================================================
def _progress_stats(conn, cands: list[str]) -> dict:
    """按钱包候选集取一人进度统计（P0-2 统一口径，三块看板共用）。

    返回 {done, steps, events, grade}：
      - done / steps 按 **去重后的 step 集合** 计数：候选集含多个钱包口径时，
        同一 step 在多口径各有一行不能算两次（旧 `COUNT(*)` 会超 100%）；
      - grade 取「教师录入行优先于系统行」（同库 P0-2：同一学生可能同时有
        教师行与系统草稿行，按 updated_at 取新会把系统草稿盖在教师分上）；
      - chain_tutorial_progress 是教程首次执行才建的表（本接口不得因为“还没人
        做过教程”而 500，P0-1：看板取不到数与“没人做”必须能区分）。
    """
    h, lc = lower_wallet_in(cands)
    if not lc:
        return {"done": 0, "steps": set(), "events": 0, "grade": None}
    prog = []
    if has_table(conn, "chain_tutorial_progress"):
        prog = conn.execute(
            f"SELECT step, done FROM chain_tutorial_progress WHERE lower(wallet) IN ({h})",
            lc,
        ).fetchall()
    done_set = {p["step"] for p in prog if p["done"]}
    ev = conn.execute(
        f"SELECT COUNT(*) AS c FROM learning_events WHERE lower(wallet) IN ({h})",
        lc,
    ).fetchone()
    gr = conn.execute(
        f"SELECT training_score, final_score, score FROM student_grades "
        f"WHERE lower(wallet) IN ({h}) "
        f"ORDER BY (COALESCE(teacher_id, '') IN ('system', '')) ASC, updated_at DESC LIMIT 1",
        lc,
    ).fetchone()
    return {
        "done": len(done_set), "steps": done_set,
        "events": ev["c"] if ev else 0, "grade": gr,
    }



@router.get("/class-students")
def class_students(
    class_id: str = Query("", description="按班级聚焦（可选；只能选自己归档范围内的班）"),
    user: dict = Depends(get_current_user),
):
    """查询当前教师**本校**的学生列表 + 实训进度概要（可选按班聚焦）。

    学生名单的边界与成绩册一致（**成绩按学校归档**，见 roster.teacher_scope）：
    - 教师：返回**本校全部学生**（role_id=4，跨班不限）——同校学生的成绩都能看能改；
      未定学校但定了班级时过渡期仍按班取数（scope_mode='class'）
    - 管理员：返回全部学生（传 class_id 则收窄到该班）
    - 学生：仅返回自己（用于查看自己在班级中的排名）
    每位学生附带 chain_tutorial_progress 完成步数、learning_events 计数、
    student_grades 实训/综合成绩（若有），供前端渲染进度看板。
    """
    init_db()
    rid = int(user.get("role_id") or 0)
    x_user_id = user.get("user_id") or ""
    want_class = norm_class(class_id)
    with get_conn() as conn:
        # 1) 归档范围（学生仍走班级解析链，只为自己拼排名用的行）
        scope = (
            teacher_scope(conn, user) if rid in (1, 3)
            else resolve_class_scope(conn, user)
        )
        my_class = scope["class_id"]
        if rid in (1, 3) and want_class and not class_allowed_in_scope(conn, scope, want_class):
            raise HTTPException(
                403,
                "该班级不在你的任教范围内（成绩按学校归档），不能按它取学生名单",
            )
        # 2) 花名册：user_info 有学生就用它；为空（P0-4 旧库 / 学生从未登录）
        #    降级用成绩册派生名单，并**标注来源**，不把“取不到数”伪装成“没人做”
        if rid == 4:
            me = self_student_row(conn, user)
            students = [me] if me else []
            roster_source = "user_info" if me else "empty"
        elif scope.get("mode") == "self" or scope.get("class_unbound"):
            # 教师既没学校也没班级：明确返回未绑定（而不是静默 0 行）
            students, roster_source = [], "empty"
        else:
            mode = scope.get("mode") or "class"
            students, roster_source = roster_students(
                conn,
                want_class or (my_class if mode == "class" else ""),
                school_id=(scope["school_id"] if mode == "school" else ""),
                all_classes=(mode == "all" and not want_class),
            )
        # 3) 为每位学生补充进度数据（P0-2 钱包候选集：本人全部口径并集）
        out = []
        for s in students:
            h, lc = lower_wallet_in(candidates_for_student(conn, s))
            s = dict(s)
            s["total_steps"] = TUTORIAL_TOTAL_STEPS
            if not lc:
                # 连一个可用钱包口径都没有（名单行未登录过 / 无成绩记录）：
                # 标 data_ready=False，让界面能区分“没数据”与“零进度”
                s.update({
                    "done_steps": 0, "progress_pct": 0.0, "event_count": 0,
                    "training_score": 0, "final_score": 0, "teacher_score": 0,
                    "data_ready": False,
                })
                out.append(s)
                continue
            # 搭链进度 / 事件数 / 成绩（统一走 _progress_stats）
            st = _progress_stats(conn, candidates_for_student(conn, s))
            done_steps = st["done"]
            gr = st["grade"]
            s["done_steps"] = done_steps
            s["progress_pct"] = round(done_steps * 100 / TUTORIAL_TOTAL_STEPS, 1)
            s["event_count"] = st["events"]
            s["training_score"] = gr["training_score"] if gr else 0
            s["final_score"] = gr["final_score"] if gr else 0
            s["teacher_score"] = gr["score"] if gr else 0
            s["data_ready"] = True
            out.append(s)
    hints = [scope["hint"]] if scope["hint"] else []
    if roster_source == "grade_book":
        hints.append(HINT_ROSTER_EMPTY)
    return {
        "class_id": want_class or my_class,
        "class_source": "query" if want_class else scope["class_source"],
        "class_unbound": bool(scope.get("class_unbound", False)),
        # 归档边界（新口径）：名单与成绩册同源，前端据此说“本校 N 人”而不是“本班 N 人”
        "scope_mode": scope.get("mode", ""),
        "school_id": scope.get("school_id", ""),
        "school_name": scope.get("school_name", ""),
        "school_source": scope.get("school_source", ""),
        "school_unbound": bool(scope.get("school_unbound", False)),
        "roster_source": roster_source,
        "hints": hints,
        "hint": "；".join(hints),
        "total": len(out),
        "items": out,
    }


# ===========================================================================
# 5. 平台整体实训进度概览（登录后首页展示）
# ===========================================================================
@router.get("/platform-progress")
def platform_progress(user: dict = Depends(get_current_user)):
    """平台整体实训进度概览：按角色返回不同粒度的聚合数据。

    - 学生：个人进度（10 步完成数 / 学习事件数 / 实训成绩 / 班级排名）
    - 教师：**本校**整体进度（人数 / 平均完成步数 / 平均成绩 / 各步完成率）——
      与成绩册同一个归档边界（成绩按学校归档），未定学校时过渡期仍按绑定班级
    - 管理员：全校概览（总学生数 / 总班级数 / 平均进度 / 各步完成率）
    """
    init_db()
    rid = int(user.get("role_id") or 0)
    x_user_id = user.get("user_id") or ""
    with get_conn() as conn:
        # 1) 范围：教师 / 管理员用归档边界（学校 → 过渡期班级 → 只看自己）；
        #    学生仍走班级解析链（它要的是“同班排名”而不是“同校”）
        scope = (
            teacher_scope(conn, user) if rid in (1, 3)
            else resolve_class_scope(conn, user)
        )
        my_class = scope["class_id"]
        # 学生本人花名册行（user_info 缺失时降级成绩册，P0-1）
        me = self_student_row(conn, user) if rid == 4 else {}

        # 2) 按角色聚合
        if rid == 4:
            # 学生视角：个人进度 + 班级排名（P0-2 本人全部钱包口径并集）
            my_cands = (
                candidates_for_student(conn, me) if me
                else resolve_wallet_candidates(conn, user.get("wallet") or "", x_user_id)
            )
            st = _progress_stats(conn, my_cands)
            done = st["done"]
            gr = st["grade"]
            # 班级排名：同班中完成步数 > 自己的学生数（花名册同样支持降级）
            rank = 0
            class_total = 0
            roster_source = "empty"
            if my_class and not scope["class_unbound"]:
                cls_students, roster_source = roster_students(conn, my_class)
                class_total = len(cls_students)
                ahead = 0
                for cs in cls_students:
                    if x_user_id and str(cs.get("user_id") or "") == x_user_id:
                        continue  # 自己计入班级人数，不参与「超过自己」计数
                    cd = _progress_stats(
                        conn, candidates_for_student(conn, cs)
                    )["done"]
                    if cd > done:
                        ahead += 1
                rank = ahead + 1
            hints = [scope["hint"]] if scope["hint"] else []
            if roster_source == "grade_book":
                hints.append(HINT_ROSTER_EMPTY)
            return {
                "scope": "personal",
                "class_id": my_class,
                "class_source": scope["class_source"],
                "class_unbound": scope["class_unbound"],
                "roster_source": roster_source,
                "hints": hints,
                "hint": "；".join(hints),
                "data_ready": bool(my_cands),
                "done_steps": done,
                "total_steps": TUTORIAL_TOTAL_STEPS,
                "progress_pct": round(done * 100 / TUTORIAL_TOTAL_STEPS, 1),
                "event_count": st["events"],
                "training_score": gr["training_score"] if gr else 0,
                "final_score": gr["final_score"] if gr else 0,
                "class_rank": rank,
                "class_total": class_total,
            }
        elif rid == 3:
            # 教师视角：本校整体进度（未定学校时过渡期按绑定班级）
            t_mode = scope.get("mode") or "class"
            if t_mode == "self":
                # P0-1：未确定任教范围时明确标出，不再返回一个「看起来像空班」的 0
                return {
                    "scope": "school", "class_id": "",
                    "class_source": "", "class_unbound": True,
                    "school_id": "", "school_unbound": True,
                    "roster_source": "empty",
                    "hints": [scope["hint"]], "hint": scope["hint"],
                    "total_students": 0, "avg_done_steps": 0,
                    "avg_progress_pct": 0, "avg_training_score": 0,
                    "step_completion": [0] * TUTORIAL_TOTAL_STEPS,
                    "items": [], "total": 0,
                }
            cls_students, roster_source = roster_students(
                conn,
                my_class if t_mode == "class" else "",
                school_id=(scope["school_id"] if t_mode == "school" else ""),
            )
            items = []
            step_completion = [0] * TUTORIAL_TOTAL_STEPS
            total_done = 0
            total_training = 0.0
            for cs in cls_students:
                stt = _progress_stats(conn, candidates_for_student(conn, cs))
                done_count = stt["done"]
                gr = stt["grade"]
                total_done += done_count
                for s in range(1, TUTORIAL_TOTAL_STEPS + 1):
                    if s in stt["steps"]:
                        step_completion[s - 1] += 1
                items.append({
                    "user_id": cs.get("user_id") or "", "name": cs.get("name") or "",
                    "student_id": cs.get("student_id") or "",
                    "wallet": cs.get("wallet") or "",
                    "done_steps": done_count,
                    "progress_pct": round(done_count * 100 / TUTORIAL_TOTAL_STEPS, 1),
                    "training_score": gr["training_score"] if gr else 0,
                    "final_score": gr["final_score"] if gr else 0,
                    "teacher_score": gr["score"] if gr else 0,
                })
                if gr:
                    total_training += gr["training_score"] or 0
            n = len(cls_students)
            hints = [scope["hint"]] if scope["hint"] else []
            if roster_source == "grade_book":
                hints.append(HINT_ROSTER_EMPTY)
            return {
                "scope": "school" if t_mode == "school" else "class",
                "class_id": my_class,
                "class_source": scope["class_source"],
                "class_unbound": bool(scope.get("class_unbound", False)),
                "school_id": scope.get("school_id", ""),
                "school_name": scope.get("school_name", ""),
                "school_source": scope.get("school_source", ""),
                "school_unbound": bool(scope.get("school_unbound", False)),
                "scope_mode": t_mode,
                "roster_source": roster_source,
                "hints": hints,
                "hint": "；".join(hints),
                "total_students": n,
                "class_count": len({str(s.get("class_id") or "") for s in cls_students
                                    if str(s.get("class_id") or "")}),
                "avg_done_steps": round(total_done / n, 1) if n else 0,
                "avg_progress_pct": round(
                    total_done * 100 / (n * TUTORIAL_TOTAL_STEPS), 1) if n else 0,
                "avg_training_score": round(total_training / n, 1) if n else 0,
                "step_completion": step_completion,  # 每步完成人数 [s1, s2, ..., s10]
                "items": items,
                "total": n,
            }
        else:
            # 管理员视角：全校概览（花名册同样支持成绩册降级）
            all_students, roster_source = roster_students(conn, "", all_classes=True)
            n = len(all_students)
            total_done = 0
            step_completion = [0] * TUTORIAL_TOTAL_STEPS
            class_ids = set()
            for s in all_students:
                if s.get("class_id"):
                    class_ids.add(s["class_id"])
                done_set = _progress_stats(conn, candidates_for_student(conn, s))["steps"]
                total_done += len(done_set)
                for stp in range(1, TUTORIAL_TOTAL_STEPS + 1):
                    if stp in done_set:
                        step_completion[stp - 1] += 1
            return {
                "scope": "global",
                "total_students": n,
                "total_classes": len(class_ids),
                "roster_source": roster_source,
                "avg_done_steps": round(total_done / n, 1) if n else 0,
                "avg_progress_pct": round(
                    total_done * 100 / (n * TUTORIAL_TOTAL_STEPS), 1) if n else 0,
                "step_completion": step_completion,
            }


# ===========================================================================
# 6. 班级绑定 / 花名册状态 / 历史钱包认领（P0-1 / P0-2 运维入口）
# ===========================================================================
class BindClassReq(BaseModel):
    """绑定「教师 → 任教范围」（学校 = 成绩归档边界；班级 = 可选聚焦范围）。

    - 教师：可不传 teacher_user_id（绑自己）；
    - 管理员：必须传 teacher_user_id（代绑指定教师）。
    两个字段至少传一个：只改传进来的那一列，留空的保持原值（不会把另一个绑给定掉）。
    """
    class_id: Optional[str] = None
    teacher_user_id: Optional[str] = None
    school_id: Optional[str] = None


class ClaimAliasReq(BaseModel):
    """认领历史共享钱包（如一人一钱包上线前的演示钱包 0xlearner）。"""
    alias: str
    user_id: str


@router.post("/bind-class")
def bind_class(
    req: BindClassReq,
    user: dict = Depends(require_role(1, 3)),
):
    """绑定教师的**任教范围**（P0-1：看板范围入口；成绩改按学校归档后它也是成绩边界入口）。

    外部 SSO 对教师不返 schoolId / classId（或返 "0"）时，成绩册与看板拿不到范围；
    本接口把「教师管哪些学生」从“靠登录载荷猜”改成“人写定的事实”。
    学校是硬边界（同校学生的成绩都能看能改），班级只是聚焦范围（沙盘轮次 / 班名回写）。
    教师只能绑自己的账号，管理员可代绑任意教师。
    路径名保留 /bind-class（旧前端与脚本在用），语义已是「绑定任教范围」。
    """
    init_db()
    rid = int(user.get("role_id") or 0)
    uid = (req.teacher_user_id or "").strip()
    if rid != 1 and uid and uid != (user.get("user_id") or ""):
        raise HTTPException(status_code=403, detail="仅管理员可代其他教师绑定任教范围")
    if rid != 1:
        uid = user.get("user_id") or ""
    if not uid:
        raise HTTPException(status_code=400, detail="无法确定目标教师账号")
    cls = norm_class(req.class_id)
    sch = norm_school(req.school_id)
    if not cls and not sch:
        raise HTTPException(
            status_code=400,
            detail="class_id / school_id 至少需要一个真实值（“0”/null 视为未填写）",
        )
    with get_conn() as conn:
        saved = bind_teacher_scope(
            conn, uid, class_id=cls, school_id=sch,
            bound_by=str(user.get("user_id") or ""),
        )
    return {"teacher_user_id": uid, "class_id": saved["class_id"],
            "school_id": saved["school_id"], "ok": True}


@router.get("/roster-status")
def roster_status(user: dict = Depends(get_current_user)):
    """看板与成绩册数据可用性自检（P0-1 / P0-2 / P0-4）。

    返回：**归档范围**（学校 = 成绩边界，未定学校时给出过渡期班级）及其来源、
    花名册人数与来源、本人全部钱包口径、user_info 是否已有本账号记录。
    前端可据此在看板顶部给出真话：「未确定任教学校」/「名单由成绩册派生」
    /「登录信息未落库」，而不是把“取不到数”当成“没人做”。
    """
    init_db()
    uid = user.get("user_id") or ""
    rid = int(user.get("role_id") or 0)
    with get_conn() as conn:
        # 范围与成绩册同源（教师 / 管理员按归档边界，学生按本人班级）
        scope = (
            teacher_scope(conn, user) if rid in (1, 3)
            else resolve_class_scope(conn, user)
        )
        my_row = conn.execute(
            "SELECT user_id, name, role_id, class_id, school_id, wallet, login_count, "
            "last_login_at FROM user_info WHERE user_id=?", (uid,),
        ).fetchone() if uid else None
        cands = resolve_wallet_candidates(conn, user.get("wallet") or "", uid)
        aliases = [str(r["alias"] or "") for r in conn.execute(
            "SELECT alias FROM wallet_alias WHERE user_id=? ORDER BY alias", (uid,),
        ).fetchall()] if uid else []
        students, roster_source = ([], "empty")
        if rid == 4:
            me = self_student_row(conn, user)
            students, roster_source = ([me] if me else []), ("user_info" if me else "empty")
        elif (scope.get("mode") or "class") not in ("all", "school", "class"):
            # 既没学校也没班级：不拿“无边界”当“全校”用
            students, roster_source = [], "empty"
        else:
            mode = scope.get("mode") or "class"
            students, roster_source = roster_students(
                conn,
                scope["class_id"] if mode == "class" else "",
                school_id=(scope["school_id"] if mode == "school" else ""),
                all_classes=(mode == "all"),
            )
    mode = scope.get("mode") or ""
    return {
        "user_id": uid,
        "role_id": int(user.get("role_id") or 0),
        "scope_mode": mode,
        "school_id": scope.get("school_id", ""),
        "school_name": scope.get("school_name", ""),
        "school_source": scope.get("school_source", ""),
        "school_unbound": bool(scope.get("school_unbound", False)),
        "class_id": scope["class_id"],
        "class_source": scope["class_source"],
        "class_unbound": bool(scope.get("class_unbound", False)),
        "all_classes": bool(scope.get("all_classes", mode == "all")),
        "all_schools": bool(scope.get("all_schools", False)),
        "hint": scope["hint"] or "",
        "roster_source": roster_source,
        "roster_count": len(students),
        "roster_scope_text": (
            f"本校 {scope.get('school_id')}" if mode == "school"
            else (f"班级 {scope['class_id']}" if mode == "class"
                  else ("全校" if mode == "all" else "未定范围"))),
        "user_info_registered": bool(my_row),
        "wallet_candidates": cands,
        "wallet_aliases": aliases,
        "checks": {
            "login_persist_ok": bool(my_row),
            "class_resolved": bool(scope["class_id"]) or mode == "all",
            "school_resolved": bool(scope.get("school_id")) or mode == "all",
            "roster_available": roster_source in ("user_info", "grade_book"),
        },
    }


@router.post("/wallet-alias/claim")
def claim_wallet_alias(
    req: ClaimAliasReq,
    user: dict = Depends(require_role(1)),
):
    """管理员把历史共享钱包归属到指定用户（P0-2 数据迁移入口）。

    一人一钱包上线前，大量链上/资产数据写在公共演示钱包（0xlearner 等）名下；
    不认领则候选集永远对不上，学生的报告分会凭空下降。认领后写入
    claimed_by 审计字段，再次认领可改写（仅本接口可改写，自动注册不会）。
    本接口只限管理员：认领直接改变“数据属于谁”的结论。
    """
    init_db()
    alias = (req.alias or "").strip()
    uid = (req.user_id or "").strip()
    if not alias or not uid:
        raise HTTPException(status_code=400, detail="alias / user_id 不能为空")
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM user_info WHERE user_id=?", (uid,)
        ).fetchone()
        if not exists:
            raise HTTPException(
                status_code=404,
                detail=f"user_id={uid} 不在 user_info 中（该用户需先登录一次）",
            )
        result = claim_legacy_alias(conn, alias, uid, claimed_by=str(user.get("user_id") or ""))
    logger.warning(
        "钱包认领：%s -> %s（操作人 %s，原归属 %s）",
        result["alias"], result["user_id"], result["claimed_by"],
        result["previous_owner"] or "(无)",
    )
    return {**result, "ok": True}
