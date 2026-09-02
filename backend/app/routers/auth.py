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

from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel

from .. import keystore as ks
from ..config import settings
from ..db import get_conn, now, init_db
from ..security import (
    create_token,
    decode_token,
    get_current_user,
    lower_wallet_in,
    resolve_wallet_candidates,
    _parse_bearer,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 确保 user_info 表已创建（init_db 在应用启动时已调用，这里做防御性初始化）
init_db()


def _upsert_user_info(data: dict) -> None:
    """登录成功后把用户信息持久化到 user_info 表。

    - 按 user_id 主键 upsert（不存在则新增，存在则更新 + login_count +1）
    - 教师和学生的 class_id 含义不同：学生=所属班级，教师=管理班级
    - wallet 用 userId（学习行为/实训进度/成绩按用户隔离，不随角色钱包切换变化）
    """
    uid = str(data.get("userId") or "")
    if not uid:
        return
    ts = now()
    role_id = int(data.get("roleId") or 0)
    role_map = {1: "管理员", 3: "教师", 4: "学生"}
    role_name = data.get("roleName") or role_map.get(role_id, "未知")
    class_id = str(data.get("classId") or "")
    # wallet 用 userId 作为学习行为追踪标识，确保每个用户有独立的实训进度和成绩
    wallet = uid
    # wallet 身份口径说明（一人一钱包，勿改成每次登录都覆盖）：
    #   - 学生登录时发放专属钱包 stu:{userId}（_ensure_student_wallet 写回
    #     user_info.wallet），前端登录后切到本人钱包，写/读路径都以此为口径；
    #   - 读路径（成绩 / 成就 / 班级看板）走 security.resolve_wallet_candidates
    #     候选集（请求钱包 + userId + user_info 登记钱包，不再无条件并入 0xlearner）；
    #   - 本函数恢复旧语义：首次登录写 wallet=userId；已有记录不覆盖
    #     （仅当现有 wallet 为空时补写 userId），保留历史演示钱包/旧值不迁移。
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT wallet, login_count FROM user_info WHERE user_id=?", (uid,)
        ).fetchone()
        if existing:
            # 已有记录：wallet 不覆盖（仅空值补写 userId），其余字段照常更新
            wallet = (existing["wallet"] or "").strip() or wallet
            conn.execute(
                """UPDATE user_info SET username=?, name=?, role_id=?, role_name=?,
                   student_id=?, class_id=?, school_id=?, school_name=?,
                   college_id=?, major_id=?, wallet=?, login_count=login_count+1,
                   last_login_at=?, updated_at=? WHERE user_id=?""",
                (str(data.get("username") or ""), str(data.get("name") or ""),
                 role_id, role_name, str(data.get("studentId") or ""),
                 class_id, str(data.get("schoolId") or ""),
                 str(data.get("schoolName") or ""),
                 str(data.get("collegeId") or ""),
                 str(data.get("majorId") or ""),
                 wallet,
                 ts, ts, uid),
            )
        else:
            conn.execute(
                """INSERT INTO user_info
                   (user_id, username, name, role_id, role_name, student_id, class_id,
                    school_id, school_name, college_id, major_id, wallet,
                    login_count, last_login_at, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?)""",
                (uid, str(data.get("username") or ""), str(data.get("name") or ""),
                 role_id, role_name, str(data.get("studentId") or ""),
                 class_id, str(data.get("schoolId") or ""),
                 str(data.get("schoolName") or ""),
                 str(data.get("collegeId") or ""),
                 str(data.get("majorId") or ""),
                 wallet,  # userId 作为学习行为追踪标识
                 ts, ts, ts),
            )

# ===========================================================================
# 学生钱包（一人一钱包）自动发放
# ===========================================================================
# 演示学习钱包（写路径历史口径）：仅它被视为"可被学生专属钱包替换"的演示别名
_DEMO_LEARNER_WALLET = "0xlearner"


def _ensure_student_wallet(user_id: str, role_id: int) -> tuple:
    """登录 / 会话恢复后为学生发放专属钱包别名 stu:{user_id} 并写回 user_info.wallet。

    写入策略（不得覆盖已有真实钱包 / 教师管理员配置）：
      - 仅学生角色（role_id=4）自动发放；教师 / 管理员沿用 0xadmin 等
        角色钱包语义，不做 provision、不改 user_info.wallet；
      - user_info.wallet 已是 stu: 别名 → 幂等返回，不重复 provision；
      - user_info.wallet 为空 / 演示别名 0xlearner / 登录默认口径（== user_id）
        → provision 学生钱包并把别名写回 user_info.wallet。
        （== user_id 也覆盖：首次登录 upsert 会写 wallet=userId，若不覆盖
         则学生别名永远无法写入；读侧 resolve_wallet_candidates 候选集恒含
         userId 本身，历史 userId 口径数据不受影响，读路径自然对齐）；
      - 其余非空值（学生已有真实钱包 / 外部配置）→ 视为已有真实钱包：
        不覆盖、不发放新钱包；
      - user_info 无记录（登录持久化失败等）→ 仅 provision 密钥库钱包，
        不写库（下次登录 upsert 后幂等补写）。

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
    cur_l = current.lower()
    # 已是学生专属钱包别名：幂等返回（不重复 provision / 不写库）
    if cur_l.startswith(ks.STUDENT_ALIAS_PREFIX):
        info = ks.get_student_wallet(uid)
        return (info[0], info[1]) if info else (alias, None)
    # 已有真实钱包（非演示别名且非登录默认口径）：不覆盖
    if current and cur_l != _DEMO_LEARNER_WALLET and current != uid:
        return alias, None
    # 发放 / 补齐学生钱包（幂等），并把别名写回 user_info.wallet
    try:
        new_alias, addr = ks.provision_student_wallet(uid)
    except Exception:
        return alias, None
    if row:
        try:
            with get_conn() as conn:
                conn.execute(
                    "UPDATE user_info SET wallet=?, updated_at=? WHERE user_id=?",
                    (new_alias, now(), uid),
                )
        except Exception:
            pass  # 写库失败不影响登录，下次登录幂等重试
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
    # wallet 用 userId 作为学习行为追踪标识（前端可据此关联实训进度/成绩）
    data["wallet"] = str(data.get("userId") or "")
    # 持久化用户信息到 user_info 表（用于教师按班级查看学生成绩 / 班级整体进度）
    try:
        _upsert_user_info(data)
    except Exception:
        pass  # 持久化失败不影响登录主流程
    # 学生钱包（一人一钱包）：登录成功后自动发放 / 解析学生专属钱包别名。
    # 注意 data["wallet"] 保持 userId 口径不变（JWT 载荷语义不动，避免破坏
    # 读侧钱包候选集），学生专属别名通过 student_wallet 字段返回供前端切换。
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
    # 签发平台 JWT（24h 有效）：后续所有接口的身份凭据，前端存入 localStorage 后由拦截器注入
    try:
        data["token"] = create_token({
            "user_id": str(data.get("userId") or ""),
            "role_id": int(rid or 0),
            "wallet": str(data.get("userId") or ""),
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

      - 验签成功：返回 active=true 及载荷中的身份信息（保持原响应字段结构）；
      - 无 token / 验签失败 / 过期：返回 active=false，前端据此引导账号密码登录。
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
            return {
                "active": True,
                "userId": ctx["user_id"],
                "roleId": rid or None,
                "roleName": role_map.get(rid, "未知"),
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
@router.get("/class-students")
def class_students(user: dict = Depends(get_current_user)):
    """查询当前教师/管理员所在班级的学生列表 + 实训进度概要。

    - 教师：返回与自身 class_id 相同的所有学生（role_id=4）
    - 管理员：返回全部学生（class_id 为空时不过滤）
    - 学生：仅返回自己（用于查看自己在班级中的排名）
    每位学生附带 chain_tutorial_progress 完成步数、learning_events 计数、
    student_grades 实训/综合成绩（若有），供前端渲染班级进度看板。
    """
    init_db()
    rid = int(user.get("role_id") or 0)
    x_user_id = user.get("user_id") or ""
    with get_conn() as conn:
        # 1) 定位当前用户的 class_id
        my_class = ""
        if x_user_id:
            row = conn.execute(
                "SELECT class_id FROM user_info WHERE user_id=?", (x_user_id,)
            ).fetchone()
            if row:
                my_class = row["class_id"] or ""
        # 2) 查询学生列表
        if rid == 1:
            # 管理员：全部学生
            students = [dict(r) for r in conn.execute(
                "SELECT user_id, username, name, student_id, class_id, school_name, "
                "wallet, login_count, last_login_at FROM user_info WHERE role_id=4 "
                "ORDER BY class_id, student_id"
            ).fetchall()]
        elif rid == 3:
            # 教师：同班学生
            if my_class:
                students = [dict(r) for r in conn.execute(
                    "SELECT user_id, username, name, student_id, class_id, school_name, "
                    "wallet, login_count, last_login_at FROM user_info "
                    "WHERE role_id=4 AND class_id=? ORDER BY student_id",
                    (my_class,),
                ).fetchall()]
            else:
                # 教师无 class_id 时返回空（避免越权看到全部学生）
                students = []
        elif rid == 4:
            # 学生：仅自己
            students = [dict(r) for r in conn.execute(
                "SELECT user_id, username, name, student_id, class_id, school_name, "
                "wallet, login_count, last_login_at FROM user_info WHERE user_id=?",
                (x_user_id or "",),
            ).fetchall()]
        else:
            students = []
        # 3) 为每位学生补充进度数据（钱包候选集兼容：写路径 0xlearner / 读路径 userId）
        out = []
        for s in students:
            w = s.get("wallet") or "0xlearner"
            h, lc = lower_wallet_in(resolve_wallet_candidates(conn, w, s.get("user_id") or ""))
            # 搭链进度
            prog = conn.execute(
                f"SELECT COUNT(*) AS done FROM chain_tutorial_progress "
                f"WHERE lower(wallet) IN ({h}) AND done=1",
                lc,
            ).fetchone()
            done_steps = prog["done"] if prog else 0
            # 学习事件总数
            ev = conn.execute(
                f"SELECT COUNT(*) AS c FROM learning_events WHERE lower(wallet) IN ({h})",
                lc,
            ).fetchone()
            event_count = ev["c"] if ev else 0
            # 成绩（若有）
            gr = conn.execute(
                f"SELECT training_score, final_score, score FROM student_grades "
                f"WHERE lower(wallet) IN ({h}) ORDER BY updated_at DESC LIMIT 1",
                lc,
            ).fetchone()
            s["done_steps"] = done_steps
            s["total_steps"] = 10
            s["progress_pct"] = round(done_steps * 100 / 10, 1) if 10 else 0
            s["event_count"] = event_count
            s["training_score"] = gr["training_score"] if gr else 0
            s["final_score"] = gr["final_score"] if gr else 0
            s["teacher_score"] = gr["score"] if gr else 0
            out.append(s)
    return {
        "class_id": my_class,
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
    - 教师：班级整体进度（班级人数 / 平均完成步数 / 平均成绩 / 各步完成率）
    - 管理员：全校概览（总学生数 / 总班级数 / 平均进度 / 各步完成率）
    """
    init_db()
    rid = int(user.get("role_id") or 0)
    x_user_id = user.get("user_id") or ""
    with get_conn() as conn:
        # 1) 定位当前用户的 class_id
        my_class = ""
        if x_user_id:
            row = conn.execute(
                "SELECT class_id, wallet FROM user_info WHERE user_id=?", (x_user_id,)
            ).fetchone()
            if row:
                my_class = row["class_id"] or ""
                my_wallet = row["wallet"] or "0xlearner"
            else:
                my_wallet = "0xlearner"
        else:
            my_wallet = "0xlearner"

        # 2) 按角色聚合
        if rid == 4:
            # 学生视角：个人进度 + 班级排名（钱包候选集兼容双轨口径）
            h, lc = lower_wallet_in(resolve_wallet_candidates(conn, my_wallet, x_user_id))
            prog = conn.execute(
                f"SELECT COUNT(*) AS done FROM chain_tutorial_progress "
                f"WHERE lower(wallet) IN ({h}) AND done=1",
                lc,
            ).fetchone()
            done = prog["done"] if prog else 0
            ev = conn.execute(
                f"SELECT COUNT(*) AS c FROM learning_events WHERE lower(wallet) IN ({h})",
                lc,
            ).fetchone()
            ev_count = ev["c"] if ev else 0
            gr = conn.execute(
                f"SELECT training_score, final_score FROM student_grades "
                f"WHERE lower(wallet) IN ({h}) ORDER BY updated_at DESC LIMIT 1",
                lc,
            ).fetchone()
            # 班级排名：同班中完成步数 >= 自己的学生数
            rank = 0
            class_total = 0
            if my_class:
                cls_students = conn.execute(
                    "SELECT user_id, wallet FROM user_info WHERE role_id=4 AND class_id=?",
                    (my_class,),
                ).fetchall()
                class_total = len(cls_students)
                my_done = done
                ahead = 0
                for cs in cls_students:
                    cw = cs["wallet"] or "0xlearner"
                    cc_h, cc_lc = lower_wallet_in(
                        resolve_wallet_candidates(conn, cw, cs["user_id"] or "")
                    )
                    cp = conn.execute(
                        f"SELECT COUNT(*) AS d FROM chain_tutorial_progress "
                        f"WHERE lower(wallet) IN ({cc_h}) AND done=1",
                        cc_lc,
                    ).fetchone()
                    cd = cp["d"] if cp else 0
                    if cd > my_done:
                        ahead += 1
                rank = ahead + 1
            return {
                "scope": "personal",
                "class_id": my_class,
                "done_steps": done,
                "total_steps": 10,
                "progress_pct": round(done * 100 / 10, 1),
                "event_count": ev_count,
                "training_score": gr["training_score"] if gr else 0,
                "final_score": gr["final_score"] if gr else 0,
                "class_rank": rank,
                "class_total": class_total,
            }
        elif rid == 3:
            # 教师视角：班级整体进度
            if not my_class:
                return {"scope": "class", "class_id": "", "items": [], "total": 0}
            cls_students = conn.execute(
                "SELECT user_id, name, student_id, wallet FROM user_info "
                "WHERE role_id=4 AND class_id=? ORDER BY student_id",
                (my_class,),
            ).fetchall()
            items = []
            step_completion = [0] * 10  # 各步完成人数
            total_done = 0
            total_training = 0.0
            for cs in cls_students:
                w = cs["wallet"] or "0xlearner"
                h, lc = lower_wallet_in(resolve_wallet_candidates(conn, w, cs["user_id"] or ""))
                prog = conn.execute(
                    f"SELECT step, done FROM chain_tutorial_progress "
                    f"WHERE lower(wallet) IN ({h})",
                    lc,
                ).fetchall()
                done_set = {p["step"] for p in prog if p["done"]}
                done_count = len(done_set)
                total_done += done_count
                for s in range(1, 11):
                    if s in done_set:
                        step_completion[s - 1] += 1
                gr = conn.execute(
                    f"SELECT training_score, final_score FROM student_grades "
                    f"WHERE lower(wallet) IN ({h}) ORDER BY updated_at DESC LIMIT 1",
                    lc,
                ).fetchone()
                items.append({
                    "user_id": cs["user_id"], "name": cs["name"],
                    "student_id": cs["student_id"], "wallet": w,
                    "done_steps": done_count, "progress_pct": round(done_count * 100 / 10, 1),
                    "training_score": gr["training_score"] if gr else 0,
                    "final_score": gr["final_score"] if gr else 0,
                })
                if gr:
                    total_training += gr["training_score"] or 0
            n = len(cls_students)
            return {
                "scope": "class",
                "class_id": my_class,
                "total_students": n,
                "avg_done_steps": round(total_done / n, 1) if n else 0,
                "avg_progress_pct": round(total_done * 100 / (n * 10), 1) if n else 0,
                "avg_training_score": round(total_training / n, 1) if n else 0,
                "step_completion": step_completion,  # 每步完成人数 [s1, s2, ..., s10]
                "items": items,
            }
        else:
            # 管理员视角：全校概览
            all_students = conn.execute(
                "SELECT user_id, wallet, class_id FROM user_info WHERE role_id=4"
            ).fetchall()
            n = len(all_students)
            total_done = 0
            step_completion = [0] * 10
            class_ids = set()
            for s in all_students:
                if s["class_id"]:
                    class_ids.add(s["class_id"])
                w = s["wallet"] or "0xlearner"
                h, lc = lower_wallet_in(resolve_wallet_candidates(conn, w, s["user_id"] or ""))
                prog = conn.execute(
                    f"SELECT step, done FROM chain_tutorial_progress "
                    f"WHERE lower(wallet) IN ({h})",
                    lc,
                ).fetchall()
                done_set = {p["step"] for p in prog if p["done"]}
                total_done += len(done_set)
                for st in range(1, 11):
                    if st in done_set:
                        step_completion[st - 1] += 1
            return {
                "scope": "global",
                "total_students": n,
                "total_classes": len(class_ids),
                "avg_done_steps": round(total_done / n, 1) if n else 0,
                "avg_progress_pct": round(total_done * 100 / (n * 10), 1) if n else 0,
                "step_completion": step_completion,
            }
