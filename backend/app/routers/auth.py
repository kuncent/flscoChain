"""跨专业综合实训平台 登录代理。

对接外部 API 基址：https://ecosim.sztzjy.com:166/server
提供接口：
  1. GET  /api/auth/encrypt?pwd=xxx          明文密码 RSA 加密
  2. POST /api/auth/login                     用户登录（账号密码 / 智云 SSO）
  3. GET  /api/auth/zhiyun-token              生成智云 JWT Token（调试用，保留）
  4. GET  /api/auth/session                   单点登录会话校验（仅校验是否保持登录态）

前端不直接调用外部 SSO 服务（避免跨域 + 暴露外部域名），
统一由本路由转发；同时本路由不存储 Token，由前端 localStorage 自行保存。
"""
from __future__ import annotations

from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel

from ..config import settings
from ..db import get_conn, now, init_db

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 确保 user_info 表已创建（init_db 在应用启动时已调用，这里做防御性初始化）
init_db()


def _upsert_user_info(data: dict) -> None:
    """登录成功后把用户信息持久化到 user_info 表。

    - 按 user_id 主键 upsert（不存在则新增，存在则更新 + login_count +1）
    - 教师和学生的 class_id 含义不同：学生=所属班级，教师=管理班级
    - 学生 wallet 默认 0xlearner（首次登录写入，后续不覆盖已绑定的真实钱包）
    """
    uid = str(data.get("userId") or "")
    if not uid:
        return
    ts = now()
    role_id = int(data.get("roleId") or 0)
    role_map = {1: "管理员", 3: "教师", 4: "学生"}
    role_name = data.get("roleName") or role_map.get(role_id, "未知")
    class_id = str(data.get("classId") or "")
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT wallet, login_count FROM user_info WHERE user_id=?", (uid,)
        ).fetchone()
        if existing:
            # 已有记录：保留 wallet（学生可能已绑定真实链上钱包），更新其余字段
            conn.execute(
                """UPDATE user_info SET username=?, name=?, role_id=?, role_name=?,
                   student_id=?, class_id=?, school_id=?, school_name=?,
                   college_id=?, major_id=?, login_count=login_count+1,
                   last_login_at=?, updated_at=? WHERE user_id=?""",
                (str(data.get("username") or ""), str(data.get("name") or ""),
                 role_id, role_name, str(data.get("studentId") or ""),
                 class_id, str(data.get("schoolId") or ""),
                 str(data.get("schoolName") or ""),
                 str(data.get("collegeId") or ""),
                 str(data.get("majorId") or ""),
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
                 "0xlearner",  # 学生默认钱包，首次登录写入
                 ts, ts, ts),
            )

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
# 1. 明文密码加密
# ===========================================================================
@router.get("/encrypt")
async def encrypt_pwd(pwd: str = Query(..., description="明文密码")):
    """对应外部 GET /api/user/encrypt?pwd=xxx"""
    base = _external_base()
    if not base:
        raise HTTPException(status_code=500, detail="EXTERNAL_API_BASE 未配置")
    async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
        try:
            r = await client.get(f"{base}/api/user/encrypt", params={"pwd": pwd})
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
    - 智云 SSO 登录：传 TOKEN（通过 /zhiyun-token 生成或外部获取）
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

    async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
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
    # 持久化用户信息到 user_info 表（用于教师按班级查看学生成绩 / 班级整体进度）
    try:
        _upsert_user_info(data)
    except Exception:
        pass  # 持久化失败不影响登录主流程
    return data


# ===========================================================================
# 3. 生成智云登录 Token（调试用，保留以便后续联调）
# ===========================================================================
@router.get("/zhiyun-token")
async def generate_zhiyun_token(
    username: str = Query(..., description="用户名/学号"),
    password: str = Query(..., description="明文密码"),
):
    """对应外部 GET /api/user/generateZhiYunToken?username=xxx&password=xxx"""
    base = _external_base()
    if not base:
        raise HTTPException(status_code=500, detail="EXTERNAL_API_BASE 未配置")
    async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
        try:
            r = await client.get(
                f"{base}/api/user/fsoc/generateZhiYunToken",
                params={"username": username, "password": password},
            )
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"无法连接 SSO 服务：{e}")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"SSO Token 生成接口 HTTP {r.status_code}")
    data = _unwrap(r.json())
    return {"msg": data.get("msg"), "data": data.get("data")}


# ===========================================================================
# 4. 单点登录 · 会话校验（仅校验是否保持登录态）
# ===========================================================================
@router.get("/session")
async def check_session(
    authorization: Optional[str] = Header(default=None, description="Bearer <accessToken>"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_role_id: Optional[str] = Header(default=None, alias="X-Role-Id"),
):
    """单点登录会话校验。

    不再请求外部智云 SSO，仅判断当前请求是否携带有效登录会话：
      - 请求头 Authorization: Bearer <token> 由前端 http 拦截器从 localStorage 注入
      - 同时携带 X-User-Id / X-Role-Id 身份头

    只要存在非空 token + userId 即视为会话保持，返回 active=true 及身份摘要；
    否则返回 active=false，前端据此引导用户改用账号密码登录。
    本接口不调用任何外部服务，零外部依赖、无网络副作用。
    """
    token = None
    if authorization:
        parts = authorization.split(None, 1)
        token = parts[1].strip() if len(parts) == 2 and parts[0].lower() == "bearer" else authorization.strip()

    if token and x_user_id:
        role_map = {1: "管理员", 3: "教师", 4: "学生"}
        rid = int(x_role_id) if x_role_id and str(x_role_id).isdigit() else 0
        return {
            "active": True,
            "userId": x_user_id,
            "roleId": rid or None,
            "roleName": role_map.get(rid, "未知"),
            "message": "已检测到保持登录的会话，正在恢复登录态",
        }

    return {
        "active": False,
        "userId": None,
        "roleId": None,
        "roleName": None,
        "message": "未检测到登录会话，请使用账号密码登录",
    }


# ===========================================================================
# 5. 班级学生列表（教师查看同班学生 + 实训进度）
# ===========================================================================
@router.get("/class-students")
def class_students(
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_role_id: Optional[str] = Header(default=None, alias="X-Role-Id"),
):
    """查询当前教师/管理员所在班级的学生列表 + 实训进度概要。

    - 教师：返回与自身 class_id 相同的所有学生（role_id=4）
    - 管理员：返回全部学生（class_id 为空时不过滤）
    - 学生：仅返回自己（用于查看自己在班级中的排名）
    每位学生附带 chain_tutorial_progress 完成步数、learning_events 计数、
    student_grades 实训/综合成绩（若有），供前端渲染班级进度看板。
    """
    init_db()
    rid = int(x_role_id) if x_role_id and str(x_role_id).isdigit() else 0
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
        # 3) 为每位学生补充进度数据
        out = []
        for s in students:
            w = s.get("wallet") or "0xlearner"
            # 搭链进度
            prog = conn.execute(
                "SELECT COUNT(*) AS done FROM chain_tutorial_progress WHERE wallet=? AND done=1",
                (w,),
            ).fetchone()
            done_steps = prog["done"] if prog else 0
            # 学习事件总数
            ev = conn.execute(
                "SELECT COUNT(*) AS c FROM learning_events WHERE wallet=?", (w,)
            ).fetchone()
            event_count = ev["c"] if ev else 0
            # 成绩（若有）
            gr = conn.execute(
                "SELECT training_score, final_score, score FROM student_grades WHERE wallet=? "
                "ORDER BY updated_at DESC LIMIT 1",
                (w,),
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
# 6. 平台整体实训进度概览（登录后首页展示）
# ===========================================================================
@router.get("/platform-progress")
def platform_progress(
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_role_id: Optional[str] = Header(default=None, alias="X-Role-Id"),
):
    """平台整体实训进度概览：按角色返回不同粒度的聚合数据。

    - 学生：个人进度（10 步完成数 / 学习事件数 / 实训成绩 / 班级排名）
    - 教师：班级整体进度（班级人数 / 平均完成步数 / 平均成绩 / 各步完成率）
    - 管理员：全校概览（总学生数 / 总班级数 / 平均进度 / 各步完成率）
    """
    init_db()
    rid = int(x_role_id) if x_role_id and str(x_role_id).isdigit() else 0
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
            # 学生视角：个人进度 + 班级排名
            prog = conn.execute(
                "SELECT COUNT(*) AS done FROM chain_tutorial_progress WHERE wallet=? AND done=1",
                (my_wallet,),
            ).fetchone()
            done = prog["done"] if prog else 0
            ev = conn.execute(
                "SELECT COUNT(*) AS c FROM learning_events WHERE wallet=?", (my_wallet,)
            ).fetchone()
            ev_count = ev["c"] if ev else 0
            gr = conn.execute(
                "SELECT training_score, final_score FROM student_grades WHERE wallet=? "
                "ORDER BY updated_at DESC LIMIT 1", (my_wallet,)
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
                    cp = conn.execute(
                        "SELECT COUNT(*) AS d FROM chain_tutorial_progress WHERE wallet=? AND done=1",
                        (cw,),
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
                prog = conn.execute(
                    "SELECT step, done FROM chain_tutorial_progress WHERE wallet=?",
                    (w,),
                ).fetchall()
                done_set = {p["step"] for p in prog if p["done"]}
                done_count = len(done_set)
                total_done += done_count
                for s in range(1, 11):
                    if s in done_set:
                        step_completion[s - 1] += 1
                gr = conn.execute(
                    "SELECT training_score, final_score FROM student_grades WHERE wallet=? "
                    "ORDER BY updated_at DESC LIMIT 1", (w,)
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
                prog = conn.execute(
                    "SELECT step, done FROM chain_tutorial_progress WHERE wallet=?",
                    (w,),
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
