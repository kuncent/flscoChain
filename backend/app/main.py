"""FastAPI 应用入口与路由聚合。"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import init_db
from .tenant import register_tenant_middleware
from .routers import (
    chain, cloud, contracts, ide, explorer, monitor,
    nft, wallet, files, report, eco,
    auth, grades, achievements, missions,
    notify,  # 任务 #21：事件通知（SSE 推送 + 历史分页）
)
from .routers import sandbox  # 任务 #22：运营沙盘（故障演练 + KPI 记分板）
from .seed import seed_init_data
from .learning.paths import router as learning_paths_router


def _cors_origins() -> list[str]:
    """读取环境变量 CORS_ORIGINS（逗号分隔）；兼容 backend/.env 文件；
    默认仅允许前端开发地址，不再使用 allow_origins=["*"]。"""
    raw = os.getenv("CORS_ORIGINS", "")
    if not raw:
        # 兼容：从 backend/.env 中解析（os.getenv 不会自动加载 .env 文件）
        try:
            env_file = Path(__file__).resolve().parent.parent / ".env"
            if env_file.exists():
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    s = line.strip()
                    if s.startswith("CORS_ORIGINS="):
                        raw = s.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except Exception:
            pass
    raw = raw or "http://localhost:5173,http://127.0.0.1:5173"
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or ["http://localhost:5173", "http://127.0.0.1:5173"]


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
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 租户上下文中间件（任务 #18，在 CORS 之后注册）：对每个请求预解析一次
# JWT 身份挂 request.state（复用 security.resolve_identity，全请求只验签
# 一次；无 Authorization 头的请求近乎零成本），供 get_current_user /
# optional_user / tenant.ctx 全链路复用，不做 DB 查询。
register_tenant_middleware(app)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """静态资源安全头：/static 上传文件禁用 MIME 类型嗅探，防 XSS / 内容伪装。"""
    response = await call_next(request)
    if request.url.path.startswith("/static"):
        response.headers["X-Content-Type-Options"] = "nosniff"
    return response

# 静态资源（NFT 图片等上传文件）
app.mount("/static", StaticFiles(directory=str(settings.uploads_dir)), name="static")

# 路由挂载
for r in (
    chain.router, cloud.router, contracts.router, ide.router,
    explorer.router, monitor.router, nft.router, wallet.router, files.router,
    report.router, eco.router, auth.router, grades.router, achievements.router,
    missions.router, learning_paths_router, notify.router, sandbox.router,
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
