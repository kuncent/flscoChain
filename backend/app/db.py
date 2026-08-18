"""SQLite 数据层（持久化合约工程、监听记录、NFT、钱包流水等）。

使用原生 sqlite3 避免引入额外 ORM 依赖，便于教学阅读。

---
### 多租户 / 多班级隔离设计（骨架已到位，查询过滤可逐步接入）
所有业务表已预留三个隔离字段：
    tenant_id   TEXT   -- 班级/机构 ID（学校/企业租户）
    user_id     TEXT   -- 学生/用户 ID
    session_id  TEXT   -- 本次实验会话 ID（防止多次实验串数据）

建议在 FastAPI 中间件或 BaseReq 中自动注入（从 JWT 或 Header），
查询时统一加 `WHERE tenant_id=? AND user_id=?` 即可实现完全隔离。
每表默认值均为 ''，不影响现有单实例使用。
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from .config import settings

_lock = threading.Lock()


# 多租户字段模板（CREATE TABLE 末尾统一追加，保持结构一致）
_TENANT_COLS = """
    tenant_id TEXT NOT NULL DEFAULT '',
    user_id   TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL DEFAULT ''
"""


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(settings.db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _lock, get_conn() as conn:
        c = conn.cursor()
        # 合约工程
        c.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            """ + _TENANT_COLS + """
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS project_files (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            path TEXT NOT NULL,
            content TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            """ + _TENANT_COLS + """,
            UNIQUE(project_id, path)
        )""")
        # 已部署合约
        c.execute("""
        CREATE TABLE IF NOT EXISTS deployed_contracts (
            address TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            abi TEXT NOT NULL,
            bytecode TEXT,
            source TEXT,
            deployer TEXT,
            tx_hash TEXT,
            standard TEXT,
            created_at TEXT NOT NULL,
            """ + _TENANT_COLS + """
        )""")
        # 合约调用监听
        c.execute("""
        CREATE TABLE IF NOT EXISTS contract_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_address TEXT NOT NULL,
            method TEXT NOT NULL,
            args TEXT,
            result TEXT,
            caller TEXT,
            tx_hash TEXT,
            block_number INTEGER,
            status TEXT,
            created_at TEXT NOT NULL,
            """ + _TENANT_COLS + """
        )""")
        # 区块/交易缓存（mock 模式数据源）
        c.execute("""
        CREATE TABLE IF NOT EXISTS blocks (
            number INTEGER PRIMARY KEY,
            hash TEXT NOT NULL,
            parent_hash TEXT,
            timestamp INTEGER NOT NULL,
            tx_count INTEGER DEFAULT 0,
            miner TEXT,
            size INTEGER DEFAULT 0,
            """ + _TENANT_COLS + """
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            hash TEXT PRIMARY KEY,
            block_number INTEGER NOT NULL,
            from_addr TEXT,
            to_addr TEXT,
            value TEXT,
            input TEXT,
            output TEXT,
            status INTEGER DEFAULT 1,
            timestamp INTEGER NOT NULL,
            contract_address TEXT,
            method TEXT,
            parsed_args TEXT,
            """ + _TENANT_COLS + """
        )""")
        # NFT
        c.execute("""
        CREATE TABLE IF NOT EXISTS nfts (
            token_id TEXT PRIMARY KEY,
            standard TEXT NOT NULL,        -- ERC721 | ERC1155
            contract_address TEXT NOT NULL,
            author TEXT NOT NULL,
            title TEXT,
            description TEXT,
            image_url TEXT,
            meta_url TEXT,
            price TEXT,
            owner TEXT NOT NULL,
            created_at TEXT NOT NULL,
            """ + _TENANT_COLS + """
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS nft_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_id TEXT NOT NULL,
            from_addr TEXT,
            to_addr TEXT,
            price TEXT,
            token_contract TEXT,
            tx_hash TEXT,
            created_at TEXT NOT NULL,
            """ + _TENANT_COLS + """
        )""")
        # ERC20 钱包
        c.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            address TEXT PRIMARY KEY,
            name TEXT, symbol TEXT, decimals INTEGER,
            total_supply TEXT, owner TEXT, created_at TEXT,
            """ + _TENANT_COLS + """
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS wallet_balances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet TEXT NOT NULL,
            token_address TEXT NOT NULL,
            balance TEXT NOT NULL,
            """ + _TENANT_COLS + """,
            UNIQUE(wallet, token_address)
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS wallet_transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_address TEXT,
            from_addr TEXT, to_addr TEXT,
            amount TEXT, tx_hash TEXT,
            created_at TEXT NOT NULL,
            """ + _TENANT_COLS + """
        )""")
        # -- 未来可扩展：users / classes / assignments / exam_results 表直接沿用同样租户字段即可 --

        # 用户信息表（登录成功后持久化，用于教师按班级查看学生成绩 / 班级整体进度）
        c.execute("""
        CREATE TABLE IF NOT EXISTS user_info (
            user_id      TEXT PRIMARY KEY,         -- userId（学号/工号）
            username     TEXT NOT NULL DEFAULT '',  -- 登录账号
            name         TEXT NOT NULL DEFAULT '',  -- 姓名
            role_id      INTEGER NOT NULL DEFAULT 0,-- 1=管理员 3=教师 4=学生
            role_name    TEXT NOT NULL DEFAULT '',  -- 角色名
            student_id   TEXT NOT NULL DEFAULT '',  -- 学号（学生）
            class_id     TEXT NOT NULL DEFAULT '',  -- 班级 ID（学生所属班级 / 教师管理班级）
            school_id    TEXT NOT NULL DEFAULT '',  -- 学校 ID
            school_name  TEXT NOT NULL DEFAULT '',  -- 学校名称
            college_id   TEXT NOT NULL DEFAULT '',  -- 学院 ID
            major_id     TEXT NOT NULL DEFAULT '',  -- 专业 ID
            wallet       TEXT NOT NULL DEFAULT '',  -- 学生链上钱包（默认 0xlearner）
            login_count  INTEGER NOT NULL DEFAULT 0,-- 累计登录次数
            last_login_at TEXT NOT NULL DEFAULT '', -- 最近登录时间
            created_at   TEXT NOT NULL DEFAULT '',
            updated_at   TEXT NOT NULL DEFAULT ''
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_user_info_class ON user_info(class_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_user_info_role ON user_info(role_id)")

        # 学习行为追踪（用于 I 项"综合拓展题"评分 & 学生行为分析）
        c.execute("""
        CREATE TABLE IF NOT EXISTS learning_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet TEXT NOT NULL DEFAULT '',
            event_type TEXT NOT NULL,           -- ide_open_builtin / ide_save_project / contract_compile_ok / contract_compile_fail / interface_invoke / eco_role_switch / nft_mint_ok / report_view
            target TEXT NOT NULL DEFAULT '',    -- 合约名 / 方法名 / 项目ID
            ref_id TEXT NOT NULL DEFAULT '',    -- 关联 ID（tx_hash、project_id 等）
            extra TEXT,                          -- JSON 存拓展字段
            created_at TEXT NOT NULL,
            """ + _TENANT_COLS + """
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_learning_events_wallet_time ON learning_events(wallet, created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_learning_events_type ON learning_events(event_type)")

        # 学生成绩表（教师录入 / 管理）
        c.execute("""
        CREATE TABLE IF NOT EXISTS student_grades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id   TEXT NOT NULL,            -- 学号
            student_name TEXT NOT NULL,            -- 学生姓名
            course       TEXT NOT NULL,            -- 课程名称
            score        REAL NOT NULL,            -- 成绩（支持小数）
            teacher_id   TEXT NOT NULL DEFAULT '', -- 录入教师 userId
            teacher_name TEXT NOT NULL DEFAULT '', -- 录入教师姓名
            class_id     TEXT NOT NULL DEFAULT '', -- 班级 ID（隔离用）
            school_id    TEXT NOT NULL DEFAULT '', -- 学校 ID（隔离用）
            remark       TEXT NOT NULL DEFAULT '', -- 备注
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL,
            UNIQUE(student_id, course)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_student_grades_student ON student_grades(student_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_student_grades_class ON student_grades(class_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_student_grades_teacher ON student_grades(teacher_id)")

        # === 学生成绩表增量列（在线迁移：ADD COLUMN 不支持 IF NOT EXISTS，需先查 PRAGMA） ===
        # wallet           学生链上钱包（与 learning_events/contracts 等关联，用于自动计算实训成绩）
        # training_score   实训成绩（由平台数据自动计算：链搭建/合约/链上验证/联盟治理 4 维加权）
        # final_score      综合成绩（= 训练成绩 × 0.6 + 教师评分 × 0.4，由系统合成）
        # training_detail  实训成绩明细 JSON（4 维各项得分 + 原始计数，便于前端可视化展示）
        _GRADE_COLS = {
            "wallet":          "TEXT NOT NULL DEFAULT ''",
            "training_score":  "REAL NOT NULL DEFAULT 0",
            "final_score":      "REAL NOT NULL DEFAULT 0",
            "training_detail":  "TEXT NOT NULL DEFAULT '{}'",
        }
        existing = {row["name"] for row in c.execute("PRAGMA table_info(student_grades)")}
        for col, decl in _GRADE_COLS.items():
            if col not in existing:
                c.execute(f"ALTER TABLE student_grades ADD COLUMN {col} {decl}")
        # wallet 索引必须在列存在之后才能创建
        c.execute("CREATE INDEX IF NOT EXISTS idx_student_grades_wallet ON student_grades(wallet)")


def now() -> str:
    return datetime.utcnow().isoformat()

