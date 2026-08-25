"""FastAPI 应用入口与路由聚合。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import init_db
from .routers import (
    chain, cloud, contracts, ide, explorer, monitor,
    nft, wallet, files, report, eco,
    auth, grades, achievements,
)
from .seed import seed_init_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    eco.init_eco_db()
    seed_init_data()
    yield


app = FastAPI(
    title="FISCO 联盟链学习平台 API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态资源（NFT 图片等上传文件）
app.mount("/static", StaticFiles(directory=str(settings.uploads_dir)), name="static")

# 路由挂载
for r in (
    chain.router, cloud.router, contracts.router, ide.router,
    explorer.router, monitor.router, nft.router, wallet.router, files.router,
    report.router, eco.router, auth.router, grades.router, achievements.router,
):
    app.include_router(r)


@app.get("/")
def root():
    return {
        "name": "FISCO 联盟链学习平台 API",
        "mode": settings.chain_mode,
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok", "mode": settings.chain_mode}
