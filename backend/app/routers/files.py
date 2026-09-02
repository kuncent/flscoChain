"""文件存储 API（NFT 元数据下载等）。

安全加固（上传白名单 / 大小上限 / 魔数校验 / 归属校验）：
  - 扩展名白名单：.png / .jpg / .jpeg / .webp / .json，其余 415；
  - 大小上限 5MB，超出 413；
  - 魔数校验：图片文件头与扩展名一致，JSON 必须可解析，不符 400；
  - 上传必须登录（JWT），上传者记录在 uploads_meta 表（本模块自建，不动 db.py）；
  - 下载 / 元数据接口校验归属：上传者本人或教师 / 管理员可访问，其余 403；
  - 文件不存在统一 404，不再返回伪造示例元数据。
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from ..config import settings
from ..db import get_conn, now
from ..security import get_current_user, PRIVILEGED_ROLES

router = APIRouter(prefix="/api/files", tags=["files"])

# ---------------------------------------------------------------------------
# 上传安全策略
# ---------------------------------------------------------------------------
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".json"}
MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5MB

# 下载 / 元数据接口允许的文件名（防路径穿越：仅字母数字与 . _ -，禁止 .. 与 /）
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


def _check_extension(filename: str) -> str:
    """扩展名白名单校验，返回小写扩展名（含点）；不在白名单抛 415。"""
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"不支持的文件类型：仅允许 {'/'.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    return ext


def _check_magic(ext: str, data: bytes) -> None:
    """魔数校验：文件内容必须与扩展名声明的类型一致，否则 400。"""
    if ext == ".png":
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(400, "文件内容与扩展名不符：不是有效的 PNG 图片")
    elif ext in (".jpg", ".jpeg"):
        if not data.startswith(b"\xff\xd8\xff"):
            raise HTTPException(400, "文件内容与扩展名不符：不是有效的 JPEG 图片")
    elif ext == ".webp":
        if not (data[:4] == b"RIFF" and data[8:12] == b"WEBP"):
            raise HTTPException(400, "文件内容与扩展名不符：不是有效的 WEBP 图片")
    elif ext == ".json":
        try:
            json.loads(data.decode("utf-8"))
        except Exception:
            raise HTTPException(400, "文件内容不是合法的 JSON")


def validate_upload(filename: str, data: bytes) -> str:
    """统一的上传校验入口（files / nft 上传共用）：白名单 → 大小 → 魔数。

    返回规范化的小写扩展名（含点）；不合规直接抛 415 / 413 / 400。
    """
    ext = _check_extension(filename)
    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="文件过大：上传上限 5MB")
    if not data:
        raise HTTPException(400, "文件内容为空")
    _check_magic(ext, data)
    return ext


# ---------------------------------------------------------------------------
# 上传元数据表（本模块自建，上传者归属记录；刻意不改动 db.py）
# ---------------------------------------------------------------------------
def _ensure_uploads_meta(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS uploads_meta (
            name TEXT PRIMARY KEY,            -- 存储文件名（随机 uuid 名）
            original_filename TEXT NOT NULL DEFAULT '',
            content_type TEXT NOT NULL DEFAULT '',
            size INTEGER NOT NULL DEFAULT 0,
            uploaded_by TEXT NOT NULL DEFAULT '',     -- 上传者 user_id
            uploader_wallet TEXT NOT NULL DEFAULT '', -- 上传者钱包
            uploader_name TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )"""
    )


def _get_upload_meta(name: str):
    with get_conn() as conn:
        _ensure_uploads_meta(conn)
        return conn.execute(
            "SELECT * FROM uploads_meta WHERE name=?", (name,)
        ).fetchone()


def _check_name(name: str) -> str:
    """文件名安全校验：防路径穿越。"""
    if not name or not _SAFE_NAME.match(name) or ".." in name:
        raise HTTPException(400, "非法文件名")
    return name


def _assert_can_access(name: str, user: dict) -> None:
    """归属校验：上传者本人或教师 / 管理员可访问，其余 403。"""
    if int(user.get("role_id") or 0) in PRIVILEGED_ROLES:
        return
    meta = _get_upload_meta(name)
    uid = user.get("user_id") or ""
    wallet = user.get("wallet") or ""
    if meta and uid and (meta["uploaded_by"] == uid or meta["uploader_wallet"] == uid
                         or (wallet and meta["uploader_wallet"] == wallet)):
        return
    raise HTTPException(status_code=403, detail="无权访问他人上传的文件")


# ---------------------------------------------------------------------------
# 接口
# ---------------------------------------------------------------------------
@router.post("/upload")
async def upload(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """上传文件：白名单 + 5MB 上限 + 魔数校验；上传者身份从 JWT 解析并落库。"""
    content = await file.read()
    ext = validate_upload(file.filename or "", content)
    name = f"{uuid.uuid4().hex}{ext}"
    p = settings.uploads_dir / name
    p.write_bytes(content)
    with get_conn() as conn:
        _ensure_uploads_meta(conn)
        conn.execute(
            "INSERT INTO uploads_meta(name,original_filename,content_type,size,"
            "uploaded_by,uploader_wallet,uploader_name,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (name, file.filename or "", file.content_type or "", len(content),
             user.get("user_id") or "", user.get("wallet") or "",
             user.get("user_name") or "", now()),
        )
    return {"url": f"/static/{name}", "filename": name}


@router.get("/download/{name}")
def download(name: str, user: dict = Depends(get_current_user)):
    """下载文件：仅上传者本人或教师 / 管理员可访问。"""
    name = _check_name(name)
    p = settings.uploads_dir / name
    if not p.exists():
        raise HTTPException(404, "file not found")
    _assert_can_access(name, user)
    return FileResponse(str(p), filename=name)


@router.get("/meta/{name}")
def meta(name: str, user: dict = Depends(get_current_user)):
    """返回 NFT 元数据 JSON（content-data）。文件不存在返回 404，不再伪造示例数据。"""
    name = _check_name(name)
    p = settings.uploads_dir / name
    if not p.exists():
        raise HTTPException(404, "meta not found")
    _assert_can_access(name, user)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        raise HTTPException(400, "元数据文件不是合法 JSON")
