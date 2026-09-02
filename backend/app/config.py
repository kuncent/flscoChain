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

    # JWT 鉴权兼容层：仅当为 true 时才允许无 Bearer token 时回退读取旧 X-* 自报头
    # （开发调试用；生产环境保持默认 false，身份一律以 JWT 验签为准）
    auth_dev_header_fallback: bool = os.getenv(
        "AUTH_DEV_HEADER_FALLBACK", "false"
    ).strip().lower() in ("1", "true", "yes", "on")

    # FISCO-BCOS
    fisco_rpc_host: str = os.getenv("FISCO_RPC_HOST", "127.0.0.1")
    fisco_rpc_port: int = int(os.getenv("FISCO_RPC_PORT", "8545"))  # JSON-RPC 端口
    fisco_group_id: int = int(os.getenv("FISCO_GROUP_ID", "1"))
    # 班级 → FISCO groupId 确定性映射区间（任务 #20）：格式 "lo-hi" 或单个 "n"；
    # 默认 "1-1"（全部班级映射到组 1，行为与单组部署完全一致），
    # 多组部署时可配 "1-8" 启用按班级分组隔离；区间必须包含 1。
    fisco_group_range: str = os.getenv("FISCO_GROUP_RANGE", "1-1")
    # FISCO 链上 chainId（v2 交易签名的 v 字段）；留空/0 时启动通过 getClientVersion 自动获取
    fisco_chain_id: int = int(os.getenv("FISCO_CHAIN_ID", "0") or "0")
    fisco_cert_dir: str = os.getenv("FISCO_CERT_DIR", "")

    # evm 模式批量出块：后台线程每 interval 秒把交易池内多笔交易合并产出新块（任务 #20）。
    # 关键路径（部署/转账）仍同步等待回执，不影响调用方语义。
    evm_block_interval: float = float(os.getenv("EVM_BLOCK_INTERVAL", "2.0") or "2.0")

    # 路径
    base_dir: Path = Path(__file__).resolve().parent
    storage_dir: Path = base_dir / "storage"
    uploads_dir: Path = storage_dir / "uploads"
    # 任务 #20：evm 班级链实例逐出时状态快照落盘目录（{chains_dir}/{class_id}/snapshot.json）
    chains_dir: Path = storage_dir / "chains"
    # 任务 #20：Solidity 编译产物缓存目录（键 sha256(source)+solc 版本）
    compile_cache_dir: Path = storage_dir / "compile_cache"
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

    @property
    def fisco_group_bounds(self) -> tuple:
        """解析 FISCO_GROUP_RANGE 为 (lo, hi) 闭区间；单个数字视为 lo==hi。"""
        raw = (self.fisco_group_range or "1-1").strip()
        try:
            if "-" in raw:
                lo_s, hi_s = raw.split("-", 1)
                lo, hi = int(lo_s.strip()), int(hi_s.strip())
            else:
                lo = hi = int(raw)
        except ValueError as e:
            raise ValueError(
                f"FISCO_GROUP_RANGE 配置非法: {raw!r}（期望 'lo-hi' 或 'n'，如 '1-8'）"
            ) from e
        if lo < 1 or hi < lo:
            raise ValueError(f"FISCO_GROUP_RANGE 配置非法: {raw!r}（需 1 <= lo <= hi）")
        return lo, hi


settings = Settings()

# 初始化目录
for _d in (settings.storage_dir, settings.uploads_dir, settings.db_path.parent,
           settings.chains_dir, settings.compile_cache_dir):
    _d.mkdir(parents=True, exist_ok=True)
