"""智能合约在线编辑器工程管理 API。

支持多工程、多文件、云端保存、自动生成接口（ABI）。
"""
from __future__ import annotations

import json
import re
import uuid
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

from ..db import get_conn, now

router = APIRouter(prefix="/api/ide", tags=["ide"])


def _track(event_type: str, target: str = "", ref_id: str = "", wallet: str = "", extra: dict | None = None):
    """轻量学习行为埋点，写入 learning_events（不阻塞主流程）。"""
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO learning_events(wallet,event_type,target,ref_id,extra,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (wallet, event_type, target, ref_id,
                 json.dumps(extra or {}, ensure_ascii=False), now()),
            )
    except Exception:
        # 埋点失败不影响主业务（兼容性：如果 DB 没升级，learning_events 表还不存在）
        pass


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
def list_projects():
    with get_conn() as conn:
        # 内置「系统内置合约」工程始终排最前，其余按最近编辑时间倒序
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY is_builtin DESC, updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/projects")
def create_project(p: Project):
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
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO projects(id,name,created_at,updated_at,is_builtin) VALUES(?,?,?,?,0) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, updated_at=excluded.updated_at",
            (pid, name, now(), now()),
        )
    return {"id": pid, "name": name}


@router.delete("/projects/{pid}")
def delete_project(pid: str):
    with get_conn() as conn:
        row = conn.execute("SELECT is_builtin FROM projects WHERE id=?", (pid,)).fetchone()
        if row and row["is_builtin"]:
            raise HTTPException(403, "内置工程「系统内置合约」不可删除，仅供学习参考")
        conn.execute("DELETE FROM project_files WHERE project_id=?", (pid,))
        conn.execute("DELETE FROM projects WHERE id=?", (pid,))
    return {"ok": True}


# ---------- 文件 ----------
@router.get("/projects/{pid}/files")
def list_files(pid: str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id,path,updated_at FROM project_files WHERE project_id=? ORDER BY path", (pid,)
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/files/{fid}")
def get_file(fid: str):
    with get_conn() as conn:
        r = conn.execute("SELECT * FROM project_files WHERE id=?", (fid,)).fetchone()
    if not r:
        raise HTTPException(404, "file not found")
    return dict(r)


@router.post("/files")
def save_file(f: FileItem, x_wallet: Optional[str] = Header(default=None, alias="X-Wallet")):
    fid = f.id or uuid.uuid4().hex[:12]
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO project_files(id,project_id,path,content,updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(project_id,path) DO UPDATE SET content=excluded.content, updated_at=excluded.updated_at, id=excluded.id",
            (fid, f.project_id, f.path, f.content, now()),
        )
        conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (now(), f.project_id))
    # 行为埋点：保存 Solidity 源码（识别"学生真的在动手写合约"）
    if f.path.endswith(".sol"):
        _track("ide_save_project", target=f"{f.project_id}/{f.path}", ref_id=fid,
               wallet=x_wallet or "",
               extra={"content_len": len(f.content or "")})
    return {"id": fid, "ok": True}


@router.delete("/files/{fid}")
def delete_file(fid: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM project_files WHERE id=?", (fid,))
    return {"ok": True}


# ---------- 自动生成接口 ----------
@router.get("/projects/{pid}/interfaces")
def gen_interfaces(pid: str):
    """读取工程下所有 .sol 文件，提取函数签名生成接口文档。"""
    import re
    with get_conn() as conn:
        rows = conn.execute("SELECT path,content FROM project_files WHERE project_id=? AND path LIKE '%.sol'", (pid,)).fetchall()
    out = []
    fn_re = re.compile(r"function\s+(\w+)\s*\(([^)]*)\)\s*(?:public|external|internal|private)?\s*(?:view|pure|constant)?\s*(?:returns\s*\(([^)]*)\))?")
    for r in rows:
        for m in fn_re.finditer(r["content"]):
            name = m.group(1)
            inputs = [a.strip() for a in (m.group(2) or "").split(",") if a.strip()]
            outputs = [a.strip() for a in (m.group(3) or "").split(",") if a.strip()]
            out.append({"file": r["path"], "name": name, "inputs": inputs, "outputs": outputs})
    return {"interfaces": out}
