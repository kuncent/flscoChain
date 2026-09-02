"""pytest 全局夹具（任务 #16 测试基建）。

DB 注入点：db.get_conn() 每次调用都实时读取 settings.db_path，因此只需把
config.settings 单例的 db_path 指向 tmp_path 临时库，全部数据层
（learning.events / learning.tutorial_engine / learning.alliance_roles /
routers.grades）即自动落到隔离库，无需改动任何业务代码。
链模式：CHAIN_MODE=mock（MockChainClient 纯内存，无网络 / 无 docker 依赖）。
注意 backend/.env 里 CHAIN_MODE=evm 会被 pydantic-settings 以 dotenv 优先级
覆盖字段默认值，所以除设置环境变量（供 config.py 导入期读取）外，fixture
内还需直接覆写 settings.chain_mode 单例。

client fixture 说明：TestClient 刻意不进入 with 上下文（不触发 lifespan）——
建表动作由 temp_db fixture 显式调用 init_db() + init_eco_db() 完成（与
lifespan 等价），从而避开 seed_init_data 内 solc 合约编译的不确定性。
"""
import os
import sys
from pathlib import Path

# 必须先于任何 app.* 导入设置（app.config 在导入期读取环境变量）
os.environ["CHAIN_MODE"] = "mock"

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import init_db
from app.main import app as fastapi_app
from app.routers.eco import init_eco_db


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """隔离的临时 SQLite 库 + mock 链模式（每个测试独立）。"""
    db_file = tmp_path / "test_chain.sqlite3"
    monkeypatch.setattr(settings, "db_path", db_file)
    monkeypatch.setattr(settings, "chain_mode", "mock")
    init_db()      # 平台业务表（learning_events / deployed_contracts / ...）
    init_eco_db()  # eco_* 表（events.aggregate 查 eco_energy_records 无容错）
    return db_file


@pytest.fixture
def client(temp_db):
    """FastAPI TestClient（CHAIN_MODE=mock，依赖 temp_db 的隔离库）。"""
    return TestClient(fastapi_app)
