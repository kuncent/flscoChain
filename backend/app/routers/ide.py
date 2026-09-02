"""智能合约在线编辑器工程管理 API。

支持多工程、多文件、云端保存、自动生成接口（ABI）。
"""
from __future__ import annotations

import re
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..db import get_conn, now
from ..security import get_current_user, PRIVILEGED_ROLES
from ..tenant import request_uid, scope_filter
# 学习行为埋点统一收口至 learning.events（EventType 常量 + track 唯一写入实现）
from ..learning.events import EventType, track as _track

router = APIRouter(prefix="/api/ide", tags=["ide"])


# 任务 #18 逐端点鉴权口径（详见各端点 docstring）：
#   - 读接口（projects / files / interfaces）：optional 鉴权 + 租户 scope 过滤
#     （登录=本人归属行 + 未登记旧行；未登录=仅未登记旧行，内置演示工程
#     user_id='' 始终可见，tenant.scope_filter 统一构造）；
#   - 写接口（create / save / delete）：保持 Depends(get_current_user)，
#     写路径补填归属（projects.user_id / project_files.user_id），隔离随
#     写入自动收紧（见 db._TENANT_COLS 设计）；删除另加归属校验
#     （学生仅可删本人创建 / 未归属旧行，教师 / 管理员不受限）。


class Project(BaseModel):
    id: Optional[str] = None
    name: str


class FileItem(BaseModel):
    id: Optional[str] = None
    project_id: str
    path: str
    content: str = ""


# ---------- 工程 ----------
@router.get("/projects")
def list_projects(request: Request):
    """工程列表：optional 鉴权 + 租户 scope 过滤（登录=本人+旧行，未登录=仅旧行）。

    内置工程（is_builtin=1，user_id=''）属未登记旧行，登录 / 未登录均可见。
    """
    cond, sp = scope_filter("projects", request_uid(request))
    with get_conn() as conn:
        # 内置「系统内置合约」工程始终排最前，其余按最近编辑时间倒序
        rows = conn.execute(
            "SELECT * FROM projects"
            + (" WHERE " + cond if cond else "")
            + " ORDER BY is_builtin DESC, updated_at DESC",
            sp,
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/projects")
def create_project(p: Project, request: Request, user: dict = Depends(get_current_user)):
    name = (p.name or "").strip()
    if not name:
        raise HTTPException(400, "工程名称不能为空")
    if len(name) > 30:
        raise HTTPException(400, "工程名称过长：请控制在 30 个字符以内")
    # 命名规范：仅允许中文 / 字母 / 数字 / 下划线 / 中划线 / 空格
    if re.search(r"[^\w\u4e00-\u9fa5\- ]", name):
        raise HTTPException(400, "工程名称包含非法字符：仅支持中文、字母、数字、下划线、中划线")
    with get_conn() as conn:
        clash = conn.execute(
            "SELECT 1 FROM projects WHERE name=? AND id IS NOT ?", (name, p.id or "")
        ).fetchone()
        if clash:
            raise HTTPException(400, f"已存在同名工程「{name}」，请更换名称")
    pid = p.id or uuid.uuid4().hex[:12]
    # 任务 #18：写路径补填归属（projects.user_id = 登录人），隔离随写入自动收紧；
    # tenant_id 暂留默认 ''（JWT 载荷无机构字段，待登录侧写入后再接入）
    uid = user.get("user_id") or ""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO projects(id,name,created_at,updated_at,is_builtin,user_id) "
            "VALUES(?,?,?,?,0,?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, updated_at=excluded.updated_at",
            (pid, name, now(), now(), uid),
        )
    return {"id": pid, "name": name}


@router.delete("/projects/{pid}")
def delete_project(pid: str, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute("SELECT is_builtin, user_id FROM projects WHERE id=?", (pid,)).fetchone()
        if row and row["is_builtin"]:
            raise HTTPException(403, "内置工程「系统内置合约」不可删除，仅供学习参考")
        # 任务 #18：归属校验 —— 明确归属他人的工程仅本人 / 教师 / 管理员可删
        # （未归属旧行 user_id='' 保持现状可删，不破坏既有数据操作）
        if (
            row and (row["user_id"] or "")
            and row["user_id"] != (user.get("user_id") or "")
            and int(user.get("role_id") or 0) not in PRIVILEGED_ROLES
        ):
            raise HTTPException(403, "仅能删除本人创建的工程")
        conn.execute("DELETE FROM project_files WHERE project_id=?", (pid,))
        conn.execute("DELETE FROM projects WHERE id=?", (pid,))
    return {"ok": True}


# ---------- 文件 ----------
@router.get("/projects/{pid}/files")
def list_files(pid: str, request: Request):
    """工程文件列表：optional 鉴权 + 租户 scope 过滤（口径同 list_projects）。"""
    cond, sp = scope_filter("project_files", request_uid(request))
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id,path,updated_at FROM project_files WHERE project_id=?"
            + (" AND " + cond if cond else "")
            + " ORDER BY path",
            (pid, *sp),
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/files/{fid}")
def get_file(fid: str, request: Request):
    """文件内容：optional 鉴权 + 租户 scope 过滤（他人私有文件 404）。"""
    cond, sp = scope_filter("project_files", request_uid(request))
    with get_conn() as conn:
        r = conn.execute(
            "SELECT * FROM project_files WHERE id=?"
            + (" AND " + cond if cond else ""),
            (fid, *sp),
        ).fetchone()
    if not r:
        raise HTTPException(404, "file not found")
    return dict(r)


@router.post("/files")
def save_file(f: FileItem, user: dict = Depends(get_current_user)):
    fid = f.id or uuid.uuid4().hex[:12]
    with get_conn() as conn:
        # 任务 #18：写路径补填归属（project_files.user_id = 登录人）；
        # 内置共享工程（is_builtin=1）的文件保持不归属（user_id=''，
        # scope 旧行通配 → 全体学生可见可改，维持协作演示语义），
        # 私有工程文件归属首次保存人，ON CONFLICT 更新不覆盖既有归属。
        prow = conn.execute(
            "SELECT is_builtin FROM projects WHERE id=?", (f.project_id,)
        ).fetchone()
        owner = "" if (prow and prow["is_builtin"]) else (user.get("user_id") or "")
        conn.execute(
            "INSERT INTO project_files(id,project_id,path,content,updated_at,user_id) "
            "VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(project_id,path) DO UPDATE SET content=excluded.content, updated_at=excluded.updated_at, id=excluded.id",
            (fid, f.project_id, f.path, f.content, now(), owner),
        )
        conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (now(), f.project_id))
    # 行为埋点：保存 Solidity 源码（识别"学生真的在动手写合约"）；归属以 JWT 身份为准
    if f.path.endswith(".sol"):
        _track(EventType.IDE_SAVE_PROJECT, target=f"{f.project_id}/{f.path}", ref_id=fid,
               wallet=user.get("wallet") or "",
               extra={"content_len": len(f.content or "")})
    return {"id": fid, "ok": True}


@router.delete("/files/{fid}")
def delete_file(fid: str, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        # 任务 #18：归属校验（口径同 delete_project；未归属旧行保持可删）
        row = conn.execute("SELECT user_id FROM project_files WHERE id=?", (fid,)).fetchone()
        if (
            row and (row["user_id"] or "")
            and row["user_id"] != (user.get("user_id") or "")
            and int(user.get("role_id") or 0) not in PRIVILEGED_ROLES
        ):
            raise HTTPException(403, "仅能删除本人创建的文件")
        conn.execute("DELETE FROM project_files WHERE id=?", (fid,))
    return {"ok": True}


# ---------- 自动生成接口 ----------
@router.get("/projects/{pid}/interfaces")
def gen_interfaces(pid: str, request: Request):
    """读取工程下所有 .sol 文件，提取函数签名生成接口文档（scope 过滤）。"""
    import re
    cond, sp = scope_filter("project_files", request_uid(request))
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT path,content FROM project_files WHERE project_id=? AND path LIKE '%.sol'"
            + (" AND " + cond if cond else ""),
            (pid, *sp),
        ).fetchall()
    out = []
    fn_re = re.compile(r"function\s+(\w+)\s*\(([^)]*)\)\s*(?:public|external|internal|private)?\s*(?:view|pure|constant)?\s*(?:returns\s*\(([^)]*)\))?")
    for r in rows:
        for m in fn_re.finditer(r["content"]):
            name = m.group(1)
            inputs = [a.strip() for a in (m.group(2) or "").split(",") if a.strip()]
            outputs = [a.strip() for a in (m.group(3) or "").split(",") if a.strip()]
            out.append({"file": r["path"], "name": name, "inputs": inputs, "outputs": outputs})
    return {"interfaces": out}
