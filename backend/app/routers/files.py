"""文件存储 API（NFT 元数据下载等）。"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from ..config import settings

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    ext = file.filename.split(".")[-1] if file.filename else "bin"
    name = f"{uuid.uuid4().hex}.{ext}"
    p = settings.uploads_dir / name
    p.write_bytes(await file.read())
    return {"url": f"/static/{name}", "filename": name}


@router.get("/download/{name}")
def download(name: str):
    p = settings.uploads_dir / name
    if not p.exists():
        raise HTTPException(404, "file not found")
    return FileResponse(str(p), filename=name)


@router.get("/meta/{name}")
def meta(name: str):
    """返回 NFT 元数据 JSON（content-data）。"""
    import json
    p = settings.uploads_dir / name
    if not p.exists():
        # 生成示例元数据
        return {
            "name": name,
            "description": "FISCO 联盟链实训 NFT 元数据",
            "image": f"/static/{name}",
        }
    return json.loads(p.read_text(encoding="utf-8"))
