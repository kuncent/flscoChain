"""任务 #22 热修回归：旧库业务表缺租户三列时，init_db 在线迁移自动补列。

复现真实库缺陷路径：早期建库早于 _TENANT_COLS 引入，
deployed_contracts 等表无 user_id 列，tenant.scope_filter 生成的条件
引用该列 -> sqlite3.OperationalError: no such column -> explorer/monitor/ide 500。
"""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_conn, init_db
from app.main import app as fastapi_app
from app.routers.eco import init_eco_db
from app.tenant import scope_filter

# 旧库形态：无租户三列（仅保留当年建表的原生列）
LEGACY_DDL = {
    "deployed_contracts": (
        "CREATE TABLE deployed_contracts (address TEXT PRIMARY KEY, name TEXT NOT NULL,"
        " abi TEXT NOT NULL, bytecode TEXT, source TEXT, deployer TEXT, tx_hash TEXT,"
        " standard TEXT, created_at TEXT NOT NULL)"
    ),
    "contract_calls": (
        "CREATE TABLE contract_calls (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " contract_address TEXT NOT NULL, method TEXT NOT NULL, args TEXT, result TEXT,"
        " caller TEXT, tx_hash TEXT, block_number INTEGER, status TEXT, created_at TEXT NOT NULL)"
    ),
    "projects": (
        "CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL,"
        " created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
    ),
}


@pytest.fixture
def legacy_db(tmp_path, monkeypatch):
    """旧库（缺租户三列）+ mock 链；init_db 执行在线迁移补列。"""
    db_file = tmp_path / "legacy_chain.sqlite3"
    monkeypatch.setattr(settings, "db_path", db_file)
    monkeypatch.setattr(settings, "chain_mode", "mock")
    con = sqlite3.connect(db_file)
    for ddl in LEGACY_DDL.values():
        con.execute(ddl)
    # 旧行：未登记归属（历史公共数据）
    con.execute(
        "INSERT INTO deployed_contracts(address,name,abi,created_at)"
        " VALUES('0xlegacy1','GreenEnergy','[]','2020-01-01T00:00:00')"
    )
    con.commit()
    con.close()
    init_db()       # 在线迁移：补齐租户三列 + 全部新表
    init_eco_db()
    return db_file


def test_tenant_cols_migrated_on_legacy_db(legacy_db):
    with get_conn() as conn:
        for table in ("deployed_contracts", "contract_calls", "projects"):
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            assert {"tenant_id", "user_id", "session_id"} <= cols, f"{table} 租户列缺失"


def test_scope_filter_query_no_longer_500(legacy_db):
    """scope_filter 条件可直接执行；旧行（user_id=''）在空值通配语义下仍可查到。"""
    with get_conn() as conn:
        for table in ("deployed_contracts", "contract_calls", "projects"):
            cond, sp = scope_filter(table, "some_user")
            rows = conn.execute(f"SELECT * FROM {table} WHERE {cond}", sp).fetchall()
            if table == "deployed_contracts":
                assert len(rows) == 1 and rows[0]["address"] == "0xlegacy1"
        # 未登录口径同样可执行
        cond, sp = scope_filter("deployed_contracts", "")
        rows = conn.execute(f"SELECT * FROM deployed_contracts WHERE {cond}", sp).fetchall()
        assert len(rows) == 1


def test_explorer_overview_ok_on_legacy_db(legacy_db):
    """真实缺陷复现端点：/api/explorer/overview 不再因 no such column 500。"""
    client = TestClient(fastapi_app)
    r = client.get("/api/explorer/overview")
    assert r.status_code == 200, r.text
    # monitor / explorer 合约列表同链路验证
    r2 = client.get("/api/explorer/contracts")
    assert r2.status_code == 200, r2.text
    r3 = client.get("/api/monitor/0xlegacy1")
    assert r3.status_code == 200, r3.text
