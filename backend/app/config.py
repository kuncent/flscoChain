"""全局配置与运行环境变量加载。"""
from __future__ import annotations

import os
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    # 链模式: fisco（真实 FISCO-BCOS 节点）| evm（py-evm 单例）| mock（模拟兜底）
    chain_mode: str = os.getenv("CHAIN_MODE", "evm")

    backend_host: str = os.getenv("BACKEND_HOST", "0.0.0.0")
    backend_port: int = int(os.getenv("BACKEND_PORT", "8000"))

    # 跨专业综合实训平台 SSO API（对接外部登录 / 智云 Token）
    external_api_base: str = os.getenv(
        "EXTERNAL_API_BASE", "https://ecosim.sztzjy.com:166/server"
    )

    # FISCO-BCOS
    fisco_rpc_host: str = os.getenv("FISCO_RPC_HOST", "127.0.0.1")
    fisco_rpc_port: int = int(os.getenv("FISCO_RPC_PORT", "8545"))  # JSON-RPC 端口
    fisco_group_id: int = int(os.getenv("FISCO_GROUP_ID", "1"))
    fisco_cert_dir: str = os.getenv("FISCO_CERT_DIR", "")

    # 路径
    base_dir: Path = Path(__file__).resolve().parent
    storage_dir: Path = base_dir / "storage"
    uploads_dir: Path = storage_dir / "uploads"
    # 使用 CHAIN_DB_PATH 而非 DB_PATH，避免与系统级 DB_PATH 环境变量冲突
    db_path: Path = Field(
        default=storage_dir / "db" / "chain.sqlite3",
        validation_alias="CHAIN_DB_PATH",
    )
    # base_dir = backend/app/，需上溯两级到项目根 chain/
    contracts_dir: Path = base_dir.parent.parent / "contracts"

    @property
    def is_mock(self) -> bool:
        return self.chain_mode.lower() == "mock"

    @property
    def is_fisco(self) -> bool:
        return self.chain_mode.lower() == "fisco"

    @property
    def fisco_rpc_url(self) -> str:
        return f"http://{self.fisco_rpc_host}:{self.fisco_rpc_port}"

    @property
    def fisco_channel_url(self) -> str:
        return f"http://{self.fisco_rpc_host}:8545"


settings = Settings()

# 初始化目录
for _d in (settings.storage_dir, settings.uploads_dir, settings.db_path.parent):
    _d.mkdir(parents=True, exist_ok=True)
