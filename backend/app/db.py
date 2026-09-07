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

# 任务 #20：线程级连接缓存（连接复用，避免每次 get_conn 新建/关闭的开销）。
# 注意与全局锁 _lock 共存：写路径仍由调用方/ init_db 等走 _lock 串行化；
# 读路径直接复用线程内连接（SELECT 无长事务，WAL 下读到最新已提交状态）。
# 缓存键绑定 db_path：测试（conftest monkeypatch settings.db_path 指向临时库）
# 或运行期改库路径时自动切换并关闭旧连接，不产生跨库串数据。
_local = threading.local()


# 多租户字段模板（CREATE TABLE 末尾统一追加，保持结构一致）
_TENANT_COLS = """
    tenant_id TEXT NOT NULL DEFAULT '',
    user_id   TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL DEFAULT ''
"""


def has_table(conn: sqlite3.Connection, name: str) -> bool:
    """表是否已存在（跨模块建表时机不一时的降级判定）。

    典型场景：chain_tutorial_progress 由教程首次执行时才建（tutorial_engine.
    _ensure_progress_table），而学情看板 / 报告在任意时刻都可能被访问——
    表不存在应等价于“还没人做过”（空数据），而不是一个 500。
    """
    try:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (name,),
        ).fetchone() is not None
    except Exception:
        return False


def scope_where(alias: str, user_id: str | None = None,
                tenant_id: str | None = None) -> tuple[str, list]:
    """构造多租户 scope 过滤片段，返回 (WHERE 条件片段, 参数列表)。

    用法（贴合现有手写 SQL 拼接风格，最小侵入，不重写既有查询）：
        cond, sp = scope_where("learning_events", user_id=uid)
        sql += (" AND " + cond) if cond else ""
        params = params + sp

    语义（兼容优先：不允许新增过滤导致历史数据"丢失"）：
      - user_id / tenant_id 传 None（或空串）→ 返回 ('', [])，
        等价于不过滤，与既有行为完全一致（空值通配）；
      - 非 None → `{alias}.user_id = ?` OR `COALESCE({alias}.user_id,'') = ''`，
        即命中「已归属本用户的行」+「尚未登记归属的旧行」：
          * 业务表 _TENANT_COLS 为 NOT NULL DEFAULT ''，旧行 user_id=''；
          * chain_tutorial_progress 等表历史行可能为 NULL；
        COALESCE 把两种"未登记"状态一并放行，旧行永远查得到；
        后续写入路径补填 user_id 后，隔离随之自动收紧，无需再改查询。

    注意：调用方需确认目标表确实拥有对应列（业务表均带 _TENANT_COLS；
    student_grades 等历史表由 init_db 在线迁移补齐，见下方迁移块）。
    """
    conds: list[str] = []
    params: list = []
    if user_id:
        conds.append(f"({alias}.user_id = ? OR COALESCE({alias}.user_id, '') = '')")
        params.append(user_id)
    if tenant_id:
        conds.append(f"({alias}.tenant_id = ? OR COALESCE({alias}.tenant_id, '') = '')")
        params.append(tenant_id)
    return " AND ".join(conds), params


def _tune_conn(conn: sqlite3.Connection) -> None:
    """SQLite 连接级/库级调优（任务 #20），幂等：

    - journal_mode=WAL  ：库级持久属性，重复设置无害（返回当前模式）；
                          写不阻塞读，多线程并发读写性能大幅提升；
    - busy_timeout=5000 ：连接级，写冲突时最多等 5s 而非立即报 SQLITE_BUSY；
    - synchronous=NORMAL：连接级，WAL 推荐搭配（性能与安全平衡，掉电最多丢最后一个事务）。
    """
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error:
        # 个别文件系统/内存库可能不支持 WAL，保持默认 journal 模式继续工作
        pass
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """获取 SQLite 连接（线程内复用）。

    行为与旧实现完全兼容：`with get_conn() as conn:` 使用后自动 commit；
    差异仅在：连接不再每次关闭，而是缓存在线程内复用（直到 db_path 变化）。
    异常路径追加 rollback，防止复用连接把未提交的脏状态带进后续调用。
    """
    conn: sqlite3.Connection | None = getattr(_local, "conn", None)
    conn_path: str | None = getattr(_local, "conn_path", None)
    want_path = str(settings.db_path)
    if conn is None or conn_path != want_path:
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass
        conn = sqlite3.connect(want_path, check_same_thread=False, timeout=5.0)
        conn.row_factory = sqlite3.Row
        _tune_conn(conn)
        _local.conn = conn
        _local.conn_path = want_path
    try:
        yield conn
        conn.commit()
    except BaseException:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise


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
        # 内置系统工程标识（在线迁移：旧库加列）
        _prj_cols = {row["name"] for row in c.execute("PRAGMA table_info(projects)")}
        if "is_builtin" not in _prj_cols:
            c.execute("ALTER TABLE projects ADD COLUMN is_builtin INTEGER NOT NULL DEFAULT 0")
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
        # === 任务 #20：blocks 在线迁移加 class_id ===
        # 注意：blocks 以 number 为主键，仅全局/默认链实例（class_id=''）写入；
        # 班级级链实例各有独立块号空间，写同表必然主键冲突，故班级实例
        # 只持久化 transactions（hash 全局唯一，无冲突），块数据仍驻留内存。
        _blk_cols = {row["name"] for row in c.execute("PRAGMA table_info(blocks)")}
        if "class_id" not in _blk_cols:
            c.execute("ALTER TABLE blocks ADD COLUMN class_id TEXT NOT NULL DEFAULT ''")
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
        # === 任务 #20：交易持久化索引在线迁移 ===
        # class_id 列：班级级链空间（chain_client.get_chain_client(class_id) 写入）。
        # 历史行 DEFAULT ''（全局/默认链实例交易），不影响既有查询。
        _tx_cols = {row["name"] for row in c.execute("PRAGMA table_info(transactions)")}
        if "class_id" not in _tx_cols:
            c.execute("ALTER TABLE transactions ADD COLUMN class_id TEXT NOT NULL DEFAULT ''")
        # 旧库的 transactions 可能建于多租户改造之前（无 _TENANT_COLS 三列），
        # 下方索引依赖 tenant_id/user_id，先在线补齐再建索引
        # （迁移范本同 student_grades；ADD COLUMN 不支持 IF NOT EXISTS，需先查 PRAGMA）。
        for _tx_col in ("tenant_id", "user_id", "session_id"):
            if _tx_col not in _tx_cols:
                c.execute(f"ALTER TABLE transactions ADD COLUMN {_tx_col} TEXT NOT NULL DEFAULT ''")
        # 复合索引（地址/租户维度的分页扫描，配合 ORDER BY timestamp DESC）。
        # 注：任务要求的 (wallet, created_at) / (tenant_id, user_id, created_at)
        # 在 transactions 表中对应 (from_addr, timestamp) 与 (tenant_id, user_id, timestamp)。
        c.execute("CREATE INDEX IF NOT EXISTS idx_tx_from_ts ON transactions(from_addr, timestamp)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_tx_to_ts ON transactions(to_addr, timestamp)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_tx_tenant_user_ts ON transactions(tenant_id, user_id, timestamp)")
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
            amount INTEGER NOT NULL DEFAULT 1,   -- 发行数量：ERC721 恒为 1，ERC1155 可多份（半同质化特性）
            owner TEXT NOT NULL,
            created_at TEXT NOT NULL,
            """ + _TENANT_COLS + """
        )""")
        # nfts 在线迁移：amount 为 ERC1155 发行数量（ERC721 恒为 1），旧库无此列时补默认 1。
        _nft_cols = {row["name"] for row in c.execute("PRAGMA table_info(nfts)")}
        if "amount" not in _nft_cols:
            c.execute("ALTER TABLE nfts ADD COLUMN amount INTEGER NOT NULL DEFAULT 1")
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

        # 用户信息表（登录成功后持久化，用于教师查看**本校**学生成绩 / 整体进度）
        # 列含义以 SSO 实测为准（勿按列名想当然，完整映射见 roster.SCHOOL_FIELD_MAP）：
        #   username 存的是姓名、student_id 存的是登录账号，两者与字面意思相反。
        c.execute("""
        CREATE TABLE IF NOT EXISTS user_info (
            user_id      TEXT PRIMARY KEY,         -- userId（UUID，不是学号）
            username     TEXT NOT NULL DEFAULT '',  -- ※ 实测存姓名（非登录账号）
            name         TEXT NOT NULL DEFAULT '',  -- 姓名
            role_id      INTEGER NOT NULL DEFAULT 0,-- 1=管理员 3=教师 4=学生
            role_name    TEXT NOT NULL DEFAULT '',  -- 角色名
            student_id   TEXT NOT NULL DEFAULT '',  -- ※ 实测存登录账号（手机号 / 工号）
            class_id     TEXT NOT NULL DEFAULT '',  -- 班级 ID（展示与筛选，不是权限边界）
            school_id    TEXT NOT NULL DEFAULT '',  -- ★ 成绩归档边界（学校 ID）
            school_name  TEXT NOT NULL DEFAULT '',  -- 学校名称（仅回显，比较用 ID）
            college_id   TEXT NOT NULL DEFAULT '',  -- 学院 ID（SSO 常为 0=无，不参与归档）
            major_id     TEXT NOT NULL DEFAULT '',  -- 专业 ID（同上，仅登记）
            wallet       TEXT NOT NULL DEFAULT '',  -- 本人真实链上地址（一人一钱包）
            login_count  INTEGER NOT NULL DEFAULT 0,-- 累计登录次数
            last_login_at TEXT NOT NULL DEFAULT '', -- 最近登录时间
            created_at   TEXT NOT NULL DEFAULT '',
            updated_at   TEXT NOT NULL DEFAULT ''
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_user_info_class ON user_info(class_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_user_info_role ON user_info(role_id)")
        # 归档边界改成学校后，“取本校名单”是高频查询（学校列由在线迁移补上）
        c.execute("CREATE INDEX IF NOT EXISTS idx_user_info_school ON user_info(school_id)")

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
        # 成绩按学校归档：边界筛选与花名册回查都走 school_id，补一个索引避免全表扫
        c.execute("CREATE INDEX IF NOT EXISTS idx_student_grades_school ON student_grades(school_id)")

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

        # === student_grades 多租户增量列（在线迁移，范本同上方 _GRADE_COLS） ===
        # 该表历史建表无租户三列（以 class_id/school_id + wallet 承担归属）。
        # 按 _TENANT_COLS 口径补齐 user_id/tenant_id/session_id，供 grades.py
        # 的按钱包读统计（/my）叠加 db.scope_where 过滤；旧行 DEFAULT ''
        # （未登记归属），scope 兼容语义下仍可查到，既有行为不变。
        _g_existing = {row["name"] for row in c.execute("PRAGMA table_info(student_grades)")}
        for _g_col in ("user_id", "tenant_id", "session_id"):
            if _g_col not in _g_existing:
                c.execute(f"ALTER TABLE student_grades ADD COLUMN {_g_col} TEXT NOT NULL DEFAULT ''")

        # ==================== 方向四：成就系统 ====================
        # 成就定义表
        c.execute("""
        CREATE TABLE IF NOT EXISTS achievements (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            icon TEXT NOT NULL DEFAULT '🏆',
            category TEXT NOT NULL DEFAULT 'general',
            condition_type TEXT NOT NULL,
            condition_value INTEGER NOT NULL DEFAULT 1,
            points INTEGER NOT NULL DEFAULT 10,
            created_at TEXT NOT NULL
        )""")

        # 用户成就记录表
        c.execute("""
        CREATE TABLE IF NOT EXISTS user_achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet TEXT NOT NULL,
            achievement_id TEXT NOT NULL,
            earned_at TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            completed INTEGER NOT NULL DEFAULT 0,
            """ + _TENANT_COLS + """,
            UNIQUE(wallet, achievement_id)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_user_achievements_wallet ON user_achievements(wallet)")

        # 挑战任务表
        c.execute("""
        CREATE TABLE IF NOT EXISTS challenges (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            difficulty TEXT NOT NULL DEFAULT 'easy',
            points INTEGER NOT NULL DEFAULT 20,
            condition_type TEXT NOT NULL,
            condition_value INTEGER NOT NULL DEFAULT 1,
            expires_at TEXT,
            created_at TEXT NOT NULL
        )""")

        # 用户挑战任务进度表
        c.execute("""
        CREATE TABLE IF NOT EXISTS user_challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet TEXT NOT NULL,
            challenge_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            completed INTEGER NOT NULL DEFAULT 0,
            completed_at TEXT,
            """ + _TENANT_COLS + """,
            UNIQUE(wallet, challenge_id)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_user_challenges_wallet ON user_challenges(wallet)")

        # ==================== 任务 #21：五级任务验证流水线 + 事件通知 ====================
        # task_runs：验证流水线运行台账（成功/失败均落一行，失败 status='failed'）。
        # stage_results 存五级结果 JSON：[{stage, ok, detail, latency_ms, skipped?}, ...]。
        # 注：本表自带 user_id/tenant_id/class_id（任务书口径），不再追加 _TENANT_COLS
        # （避免重名列），仅补 session_id 与其他表隔离口径保持一致。
        c.execute("""
        CREATE TABLE IF NOT EXISTS task_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet TEXT NOT NULL DEFAULT '',
            user_id TEXT NOT NULL DEFAULT '',
            tenant_id TEXT NOT NULL DEFAULT '',
            class_id TEXT NOT NULL DEFAULT '',
            task_type TEXT NOT NULL DEFAULT '',   -- compile | deploy | energy_issue | tutorial_command
            task_ref TEXT NOT NULL DEFAULT '',    -- 关联引用（run_id / proof_no / stepN 等）
            stage_results TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT '',      -- success | failed
            latency_ms REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            session_id TEXT NOT NULL DEFAULT ''
        )""")
        # 在线迁移补列（范本同 student_grades：ADD COLUMN 不支持 IF NOT EXISTS，先查 PRAGMA）：
        # 旧库若已有早期版本的 task_runs（列漂移），补齐后不丢历史行。
        _tr_cols = {row["name"] for row in c.execute("PRAGMA table_info(task_runs)")}
        for _tr_col, _tr_decl in (
            ("task_ref", "TEXT NOT NULL DEFAULT ''"),
            ("session_id", "TEXT NOT NULL DEFAULT ''"),
        ):
            if _tr_col not in _tr_cols:
                c.execute(f"ALTER TABLE task_runs ADD COLUMN {_tr_col} {_tr_decl}")
        c.execute("CREATE INDEX IF NOT EXISTS idx_task_runs_wallet_time ON task_runs(wallet, created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_task_runs_type ON task_runs(task_type)")

        # notifications：events_bus 事件镜像（publish 时写入，失败容错），
        # 供 /api/notify/history 分页补看（SSE 断线期间的事件不丢）。
        # user_id='' 表示广播事件（全员可见）；非空为定向事件（仅本人可见）。
        c.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL DEFAULT '',
            tenant_id TEXT NOT NULL DEFAULT '',
            class_id TEXT NOT NULL DEFAULT '',
            event_type TEXT NOT NULL DEFAULT '',  -- tx_confirmed / deployed / compiled / energy_issued / tutorial_step_done / sandbox_*
            payload TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            session_id TEXT NOT NULL DEFAULT ''
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user_time ON notifications(user_id, created_at)")

        # ==================== 任务 #22：运营沙盘（ops 三表） ====================
        # ops_scenarios：教师配置的场景（目标 TPS / 故障脚本类型 / 持续时长）。
        # ops_rounds   ：每轮演练台账（启停时间 + 结束时 KPI 汇总 result）。
        # ops_kpis     ：KPI 样本（MTTD/MTTR/处置率/成功率）+ 处置动作流水（metric='action'，
        #                时间戳口径落 value，供 MTTD/MTTR 计算）。
        # 均带 _TENANT_COLS，class_id 列承担班级隔离（与任务书口径一致）。
        c.execute("""
        CREATE TABLE IF NOT EXISTS ops_scenarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '',
            class_id TEXT NOT NULL DEFAULT '',
            scenario_type TEXT NOT NULL DEFAULT '',   -- node_down | consensus_stall | replay_attack | gas_spike
            config TEXT NOT NULL DEFAULT '{}',        -- JSON：target_tps / duration_s / quota / fault 参数
            status TEXT NOT NULL DEFAULT 'ready',     -- ready | used
            created_by TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            """ + _TENANT_COLS + """
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_ops_scenarios_class ON ops_scenarios(class_id)")
        c.execute("""
        CREATE TABLE IF NOT EXISTS ops_rounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_id INTEGER NOT NULL,
            class_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'running',   -- running | stopped
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL DEFAULT '',
            result TEXT NOT NULL DEFAULT '{}',        -- JSON：轮次结束时的 KPI 汇总 + 停止方式
            """ + _TENANT_COLS + """
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_ops_rounds_class_status ON ops_rounds(class_id, status)")
        c.execute("""
        CREATE TABLE IF NOT EXISTS ops_kpis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_id INTEGER NOT NULL,
            class_id TEXT NOT NULL DEFAULT '',
            metric TEXT NOT NULL DEFAULT '',          -- mttd_seconds | mttr_seconds | handle_rate | success_rate | action
            value REAL NOT NULL DEFAULT 0,
            detail TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            """ + _TENANT_COLS + """
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_ops_kpis_round ON ops_kpis(round_id)")

        # ==================== 产品与逻辑问题修复（P0-1 / P0-2 / P1-25）新增三表 ====================
        # wallet_alias：钱包别名 → 用户 的唯一归属表（P0-2「一人多口径」的收口）。
        #   历史成因：登录写 wallet=userId、学生专属钱包 stu:{userId}、密钥库真实
        #   0x 地址、演示钱包 0xlearner 四种口径分别落库，任何 WHERE wallet=? 的
        #   统计都只在「半个学生」上算。此后所有读写统一经
        #   security.resolve_wallet_candidates() 取本人别名并集，SQL 不再写单值等值。
        #   kind：user_id（登录默认口径）| student_alias（stu: 专属别名）
        #        | evm_addr（密钥库真实地址）| legacy（管理员显式认领的历史共享钱包）
        #   注：内置演示钱包（0xlearner 等）只有在管理员显式认领后才挂到某个用户，
        #   绝不无条件并入候选集——那会让全班学生的资产/进度互相污染。
        c.execute("""
        CREATE TABLE IF NOT EXISTS wallet_alias (
            alias       TEXT PRIMARY KEY,          -- 小写规范化的钱包标识
            user_id     TEXT NOT NULL DEFAULT '',  -- 归属用户（user_info.user_id）
            kind        TEXT NOT NULL DEFAULT '',  -- user_id | student_alias | evm_addr | legacy
            created_at  TEXT NOT NULL DEFAULT '',
            claimed_by  TEXT NOT NULL DEFAULT ''   -- legacy 认领操作人（审计用）
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wallet_alias_user ON wallet_alias(user_id)")

        # class_teacher_bind：教师 → 任教范围 的人工绑定（P0-1）。
        #   外部 SSO 对教师不返 classId / schoolId（或返回 "0"），而看板与成绩册都以
        #   「教师所属范围」为过滤条件，无绑定时只能返回空列表。本表提供
        #   一条不依赖 SSO 的绑定通道（教师自助 / 管理员代绑）。
        #   school_id：成绩归档边界（本校可看 / 可改）；class_id：可选的单班聚焦。
        c.execute("""
        CREATE TABLE IF NOT EXISTS class_teacher_bind (
            teacher_user_id TEXT PRIMARY KEY,      -- 教师 userId
            class_id        TEXT NOT NULL DEFAULT '',
            school_id       TEXT NOT NULL DEFAULT '',  -- 任教学校 ID（成绩按学校归档）
            bound_by        TEXT NOT NULL DEFAULT '',  -- 绑定操作人（本人或管理员）
            bound_at        TEXT NOT NULL DEFAULT ''
        )""")
        # 在线迁移：旧库该表无 school_id 列（ADD COLUMN 不支持 IF NOT EXISTS）
        _bind_cols = {row["name"] for row in c.execute("PRAGMA table_info(class_teacher_bind)")}
        if "school_id" not in _bind_cols:
            c.execute("ALTER TABLE class_teacher_bind ADD COLUMN school_id TEXT NOT NULL DEFAULT ''")

        # grade_draft：实训成绩草稿表（P1-8 / P1-25）。
        #   草稿原先与教师正式成绩同表（student_grades，teacher_id='system'），
        #   且由 GET /api/report/aggregate 的隐藏副作用写入；一旦花名册里有该生
        #   真实学号，草稿的 UPDATE 就会命中教师正式行，把综合分重算成
        #   「教师分按 0 计」（在库副本上实测 84.3 → 0.6）。草稿从此独立成表，
        #   成绩册只放教师录入的行，教师显式动作才把草稿落到正式成绩。
        c.execute("""
        CREATE TABLE IF NOT EXISTS grade_draft (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         TEXT NOT NULL DEFAULT '',   -- 归属用户（稳定主键）
            wallet          TEXT NOT NULL DEFAULT '',   -- 草稿计算口径钱包
            student_id      TEXT NOT NULL DEFAULT '',   -- 学号
            student_name    TEXT NOT NULL DEFAULT '',
            course          TEXT NOT NULL DEFAULT '区块链实训',
            class_id        TEXT NOT NULL DEFAULT '',
            school_id       TEXT NOT NULL DEFAULT '',
            training_score  REAL NOT NULL DEFAULT 0,
            training_detail TEXT NOT NULL DEFAULT '{}',
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL,
            UNIQUE(user_id, course)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_grade_draft_course ON grade_draft(course)")

        # grade_merge_archive：成绩重复行归并留档（P0-2 一次性归并脚本的退路）。
        #   归并脚本默认 dry-run，--apply 时先把被下线的手稿行原文存进来，
        #   再删除/失活，保证任何一步都可人工恢复，不出现“归并丢数据”。
        c.execute("""
        CREATE TABLE IF NOT EXISTS grade_merge_archive (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            grade_id     INTEGER NOT NULL,
            payload      TEXT NOT NULL,                 -- 被归并行的完整原值 JSON
            merged_into  INTEGER NOT NULL DEFAULT 0,    -- 保留下来的那一行 id
            reason       TEXT NOT NULL DEFAULT '',
            created_at   TEXT NOT NULL
        )""")

        # === 任务 #22 热修：租户三列在线迁移（修复真实库 /api/explorer/overview 500） ===
        # 早期建库早于 _TENANT_COLS 引入，CREATE TABLE IF NOT EXISTS 不会给已存在的表
        # 补列；而 tenant.scope_filter 生成的条件引用 {表}.user_id，旧库缺列即报
        # sqlite3.OperationalError: no such column（explorer/monitor/ide 全线 500）。
        # 对 scope_filter 会触及的业务表全量核对：PRAGMA table_info 检测 +
        # ALTER ADD 补列（幂等容错，与 student_grades 迁移同范式），旧行 DEFAULT ''
        # （未登记归属），在 scope_where 的「空值通配」语义下仍可查到，既有行为不变。
        # 放在所有 CREATE 之后，保证首次初始化与旧库重入都一次性补齐。
        _SCOPE_TABLES = (
            "deployed_contracts", "contract_calls", "transactions",
            "projects", "project_files",
            "blocks", "nfts", "nft_trades",
            "tokens", "wallet_balances", "wallet_transfers",
            "learning_events", "achievements", "user_achievements",
            "challenges", "user_challenges",
        )
        for _st in _SCOPE_TABLES:
            _st_cols = {row["name"] for row in c.execute(f"PRAGMA table_info({_st})")}
            if not _st_cols:
                continue  # 表不存在：跳过（容错）
            for _st_col in ("tenant_id", "user_id", "session_id"):
                if _st_col not in _st_cols:
                    c.execute(f"ALTER TABLE {_st} ADD COLUMN {_st_col} TEXT NOT NULL DEFAULT ''")


def now() -> str:
    return datetime.utcnow().isoformat()
