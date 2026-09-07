"""资产钱包口径归一：把库里的内部别名（stu:uuid / 裸 uuid / 0xmetro 等）统一改写为
**真实链上地址**（0x + 40 位十六进制，不含冒号 / 连字符）。

对应缺陷：「所有涉及到资产的钱包地址，都改为真实的钱包地址，不要有符号-之类的」。
历史写入把登录体系的内部标识直接当钱包落库，导致：
  - 能量台账 / 证书归属 / 勋章持有 / 市场挂牌里出现
    `stu:0ae7783d-d59d-40e1-8fcc-001d752ee3fb` 这种带冒号连字符的值；
  - 同一个人有 3~4 套归属口径（P0-2），前端「我的钱包」无法复制 / 上链核对；
  - 资产表的钱包与链上交易 from_addr（本来就是真实地址）永远对不上（P0-3）。

口径（与 backend/app/wallet_id.py 完全一致，脚本不另起一套规则）：
  - 别名 → 地址走密钥库解析：机构钱包取 `0xmetro` 等别名自己的地址，
    学生取「一人一钱包」的 `stu:{user_id}` 地址（优先于早期残留的裸 user_id 账户）；
  - **只改写能解析出真实地址的值**：`alice` / `e2e_tutorial_verify` / `0xstua`
    这类密钥库里不存在的脏值保持原样并在报告里列出，绝不凭空建号；
  - 空串 / NULL 不动（ issuer_wallet 的历史空值属于「未溯源」而非「别名词」）；
  - 撞 UNIQUE 时按表策略合并（余额相加 / 取更优行），不丢数据也不留重复归属。

用法（项目根目录，推荐 backend/.venv）：
    backend/.venv/Scripts/python scripts/normalize_asset_wallets.py            # 预演（只读）
    backend/.venv/Scripts/python scripts/normalize_asset_wallets.py --apply    # 真改写
    backend/.venv/Scripts/python scripts/normalize_asset_wallets.py --only-asset
注意：执行前建议停止后端服务；脚本自带一次 schema 初始化（补 eco_energy_flows
      等新表新列），因此必须在后端代码更新后、重启前跑一次、重启后再核对。
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402
from app.db import now  # noqa: E402
from app.wallet_id import is_address, to_address  # noqa: E402

ADDR_RE = re.compile(r"^0x[0-9a-f]{40}$")

# 资产台账：证书 / 勋章 / 能量 / 市场 / 角色绑定 / 审计 + 通用代币与 NFT 表
ASSET_TARGETS: List[Tuple[str, str]] = [
    ("eco_energy_records", "wallet"),
    ("eco_energy_records", "issuer_wallet"),
    ("eco_energy_records", "operator_wallet"),
    ("eco_energy_flows", "wallet"),
    ("eco_energy_burns", "operator"),
    ("eco_certificates", "owner"),
    ("eco_certificates", "exchanged_by"),
    ("eco_badges", "owner"),
    ("eco_badges", "issued_by"),
    ("eco_badges", "exchanged_by"),
    ("eco_market_listings", "seller"),
    ("eco_market_listings", "buyer"),
    ("eco_role_selections", "wallet"),
    ("eco_operation_logs", "wallet"),
    ("eco_operation_logs", "actor_wallet"),
    ("nfts", "owner"),
    # 铸造方 / 合约部署方同样是资产口径（页面直接展示，实测残留 0xbus / 0xlearner）
    ("nfts", "author"),
    ("deployed_contracts", "deployer"),
    ("nft_trades", "from_addr"),
    ("nft_trades", "to_addr"),
    ("tokens", "owner"),
    ("wallet_balances", "wallet"),
    ("wallet_transfers", "from_addr"),
    ("wallet_transfers", "to_addr"),
    ("uploads_meta", "uploader_wallet"),
]

# 身份 / 学习行为表：列名同样叫 wallet，混用两套口径是 P0-2 的直接来源，
# 一并收敛（读侧走候选集，迁移后新旧口径都能命中，可分次执行）
LEARNING_TARGETS: List[Tuple[str, str]] = [
    ("user_info", "wallet"),
    ("student_grades", "wallet"),
    ("grade_draft", "wallet"),
    ("user_achievements", "wallet"),
    ("learning_events", "wallet"),
    ("task_runs", "wallet"),
    ("chain_tutorial_progress", "wallet"),
]

# 撞 UNIQUE 时的合并策略：
#   sum      → 数值相加（余额）
#   pick_best→ 按指标元组取更优的一行整体覆盖目标行（进度 / 成就 / 角色绑定）
MERGE_SPEC: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "wallet_balances": {"sum": ("balance",)},
    "eco_role_selections": {"pick_best": ("selected_at",)},
    "chain_tutorial_progress": {"pick_best": ("done", "finished_at")},
    "user_achievements": {"pick_best": ("completed", "progress", "earned_at")},
}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [c["name"] for c in conn.execute(f'PRAGMA table_info("{table}")')]


def _unique_keys(conn: sqlite3.Connection, table: str, col: str) -> List[List[str]]:
    """含 col 的 UNIQUE 索引列组（决定改写后是否可能撞唯一约束）。"""
    out: List[List[str]] = []
    for idx in conn.execute(f'PRAGMA index_list("{table}")'):
        if not idx["unique"]:
            continue
        cols = [r["name"] for r in conn.execute(f'PRAGMA index_info("{idx["name"]}")')]
        if col in cols:
            out.append(cols)
    return out


def _better(a: dict, b: dict, metrics: Tuple[str, ...]) -> bool:
    """a 是否优于 b（按指标元组逐个比较；None 视为最小）。"""
    for m in metrics:
        av, bv = a.get(m), b.get(m)
        if av is None and bv is None:
            continue
        if av is None:
            return False
        if bv is None:
            return True
        try:
            if av > bv:
                return True
            if av < bv:
                return False
        except TypeError:
            continue
    return False


def _merge_conflict(
    conn: sqlite3.Connection, table: str, pk_cols: List[str],
    target_rowid: int, source_rowid: int,
) -> str:
    """把 source 行并入 target 行（同唯一键），随后删除 source。返回动作描述。"""
    spec = MERGE_SPEC.get(table, {})
    t = conn.execute(f'SELECT rowid AS _rid, * FROM "{table}" WHERE rowid=?',
                     (target_rowid,)).fetchone()
    s = conn.execute(f'SELECT rowid AS _rid, * FROM "{table}" WHERE rowid=?',
                     (source_rowid,)).fetchone()
    if t is None or s is None:
        return "跳过（行已不存在）"
    td, sd = dict(t), dict(s)
    # 表自身主键列（id INTEGER PRIMARY KEY 是 rowid 的别名）不能参与“整行覆盖”，
    # 否则会把 target 行的 id 改成 source 的 → UNIQUE constraint failed: <table>.id
    id_cols = {c["name"] for c in conn.execute(f'PRAGMA table_info("{table}")') if c["pk"]}
    for col in spec.get("sum", ()):
        new = (td.get(col) or 0) + (sd.get(col) or 0)
        conn.execute(f'UPDATE "{table}" SET "{col}"=? WHERE rowid=?', (new, target_rowid))
    picked = spec.get("pick_best") or ()
    if picked and _better(sd, td, picked):
        cols = [c for c in sd if c != "_rid" and c not in pk_cols and c not in id_cols]
        sets = ", ".join(f'"{c}"=?' for c in cols)
        conn.execute(
            f'UPDATE "{table}" SET {sets} WHERE rowid=?',
            [sd[c] for c in cols] + [target_rowid],
        )
        conn.execute(f'DELETE FROM "{table}" WHERE rowid=?', (source_rowid,))
        return "合并（取更优行）"
    conn.execute(f'DELETE FROM "{table}" WHERE rowid=?', (source_rowid,))
    return "合并（保留目标行）" if spec else "删除冗余行"


def migrate(
    conn: sqlite3.Connection, targets: List[Tuple[str, str]], *, apply: bool,
    verbose: bool,
) -> Tuple[int, int, List[str]]:
    """返回 (改写行数, 合并删除行数, 未解析值列表)。"""
    changed = merged = 0
    unresolved: List[str] = []
    for table, col in targets:
        if not _table_exists(conn, table):
            unresolved.append(f"{table}.{col}：表不存在（重启后由 init 建表）")
            continue
        if col not in _columns(conn, table):
            unresolved.append(f"{table}.{col}：列不存在（旧库未跑过 schema 迁移）")
            continue
        pk_cols_list = _unique_keys(conn, table, col)
        # 预演模式不会真写库，后续行看不到前面已改的地址，因此用内存集补上
        # 「改写后会存在的唯一键」；已有真实地址行直接当作初始集
        seen_keys: set = set()
        if pk_cols_list:
            for row in conn.execute(f'SELECT * FROM "{table}"').fetchall():
                d = dict(row)
                cur = str(d.get(col) or "").strip().lower()
                if not ADDR_RE.match(cur):
                    continue
                for pk in pk_cols_list:
                    seen_keys.add((tuple(pk), tuple(str(d.get(c) or "").lower() for c in pk)))
        rows = conn.execute(
            f'SELECT rowid AS _rid, "{col}" AS v FROM "{table}"').fetchall()
        table_changed = 0
        for r in rows:
            raw = (r["v"] or "").strip()
            if not raw:
                continue
            low = raw.lower()
            if ADDR_RE.match(low):
                continue                       # 已是真实地址
            addr = to_address(low)             # create=False：只认已有密钥
            if not is_address(addr):
                unresolved.append(f"{table}.{col}={raw!r}")
                continue
            if pk_cols_list:
                src = conn.execute(
                    f'SELECT rowid AS _rid, * FROM "{table}" WHERE rowid=?',
                    (r["_rid"],)).fetchone()
                sd = dict(src or {})
                for pk in pk_cols_list:
                    # 除被改写的列取新地址外，其余唯一键列沿用本源行原值
                    vals = [addr if c == col else (sd.get(c) or "") for c in pk]
                    key = (tuple(pk), tuple(str(v).lower() for v in vals))
                    cond = " AND ".join(f'lower("{c}")=lower(?)' for c in pk)
                    if apply:
                        # 别名列名写死 rowid 会踩坑：id INTEGER PRIMARY KEY 是 rowid 的
                        # 别名，SELECT rowid 回来时列名叫 id（sqlite3.Row 取 rowid 直接
                        # IndexError），统一 AS _rid 取法
                        hits = [h["_rid"] for h in conn.execute(
                            f'SELECT rowid AS _rid FROM "{table}" WHERE {cond} AND rowid<>?',
                            vals + [r["_rid"]]).fetchall()]
                    else:
                        hits = [-1] if key in seen_keys else []
                    seen_keys.add(key)
                    for hid in hits:
                        if apply:
                            act = _merge_conflict(conn, table, pk, hid, r["_rid"])
                        else:
                            act = "合并（预演）"
                        merged += 1
                        if verbose:
                            print(f"    · {table}#{r['_rid']} → #{hid} {act}")
            if apply:
                conn.execute(
                    f'UPDATE "{table}" SET "{col}"=? WHERE rowid=?', (addr, r["_rid"]))
            table_changed += 1
            if verbose:
                print(f"    {table}#{r['_rid']}  {raw}  →  {addr}")
        if table_changed:
            changed += table_changed
            print(f"  [{'APPLY' if apply else 'DRY '}] {table}.{col}: {table_changed} 行")
    return changed, merged, unresolved


def register_address_aliases(conn: sqlite3.Connection, apply: bool) -> int:
    """把「别名 → 真实地址」的归属补进 wallet_alias（P0-2 读侧候选集的事实源）。

    否则迁移后新账号（JWT 已带真实地址）在 wallet_alias 里查不到自己的地址口径，
    教师按班级 / 成绩取数会漏人。
    """
    if not _table_exists(conn, "wallet_alias"):
        return 0
    have = {r["alias"].strip().lower() for r in conn.execute("SELECT alias FROM wallet_alias")}
    added = 0
    ts = now()
    for r in conn.execute("SELECT alias, user_id, kind, claimed_by FROM wallet_alias"):
        alias = str(r["alias"] or "").strip().lower()
        if not alias or alias in have:
            continue
        addr = to_address(alias)
        if not is_address(addr) or addr in have:
            continue
        if apply:
            conn.execute(
                "INSERT OR IGNORE INTO wallet_alias(alias,user_id,kind,created_at,claimed_by)"
                " VALUES(?,?,?,?,?)",
                (addr, r["user_id"], "evm_addr", ts, r["claimed_by"]),
            )
        have.add(addr)
        added += 1
    # user_info 本人的地址口径同样登记一次（教师 / 管理员只有 wallet 列）
    if _table_exists(conn, "user_info"):
        for r in conn.execute("SELECT user_id, wallet FROM user_info"):
            uid, w = str(r["user_id"] or ""), str(r["wallet"] or "").strip().lower()
            if not w or w in have:
                continue
            addr = to_address(w)
            if not is_address(addr) or addr in have:
                continue
            if apply:
                conn.execute(
                    "INSERT OR IGNORE INTO wallet_alias(alias,user_id,kind,created_at)"
                    " VALUES(?,?,?,?)", (addr, uid, "evm_addr", ts))
            have.add(addr)
            added += 1
    return added


def backfill_issuer_from_role(conn: sqlite3.Connection, apply: bool) -> int:
    """补齐历史能量行的发放方钱包（role_key → 机构钱包真实地址）。

    旧版本 issuer_wallet 大量留空（17/29 行），“谁发的”在审计面提问不了。
    role_key 本身就在行上，机构钱包地址由密钥库给出，补上后能量台账每一行
    都有真实发行方地址（无冒号 / 连字符）。
    """
    if not _table_exists(conn, "eco_energy_records"):
        return 0
    cols = _columns(conn, "eco_energy_records")
    if "issuer_wallet" not in cols or "role_key" not in cols:
        return 0
    from app.learning.alliance_roles import wallet_address
    rows = conn.execute(
        "SELECT rowid AS _rid, role_key FROM eco_energy_records "
        "WHERE COALESCE(issuer_wallet,'')='' AND COALESCE(role_key,'')<>''"
    ).fetchall()
    done = 0
    for r in rows:
        addr = wallet_address(str(r["role_key"] or ""))
        if not is_address(addr):
            continue
        if apply:
            conn.execute("UPDATE eco_energy_records SET issuer_wallet=? WHERE rowid=?",
                         (addr, r["_rid"]))
        done += 1
    if done:
        print(f"  [{'APPLY' if apply else 'DRY '}] eco_energy_records.issuer_wallet"
              f"（按 role_key 补齐）: {done} 行")
    return done


def drop_mismatched_org_bindings(conn: sqlite3.Connection, apply: bool) -> int:
    """删掉「机构地址 ↔ 非本机构角色」的错位绑定行（eco_role_selections）。

    旧版前端在切换角色时把「当前钱包」与「角色 key」分开提交，出现过
    `0xmetro ↔ recycling`、`0xrecycle ↔ bus` 这种错位绑定；地址化后这类行
    不会被唯一键合并（两个字段都不同），只能按「机构钱包只能绑自身角色」硬规则剔除。
    """
    if not _table_exists(conn, "eco_role_selections"):
        return 0
    cols = _columns(conn, "eco_role_selections")
    if "wallet" not in cols or "role_key" not in cols:
        return 0
    from app.learning.alliance_roles import ROLES, wallet_address
    # 真实地址 → 该机构唯一角色 key（地址化后角色绑定的唯一合法组合）
    by_addr: Dict[str, str] = {}
    for r in ROLES:
        addr = wallet_address(str(r.get("key") or ""))
        if is_address(addr):
            by_addr[addr.lower()] = str(r["key"])
    if not by_addr:
        return 0
    rows = conn.execute(
        "SELECT rowid AS _rid, wallet, role_key FROM eco_role_selections"
    ).fetchall()
    dropped = 0
    for r in rows:
        w = str(r["wallet"] or "").strip().lower()
        owner_role = by_addr.get(w)
        if not owner_role:
            continue                       # 非机构地址（个人钱包）：可以扮演任意角色
        if str(r["role_key"] or "") == owner_role:
            continue
        dropped += 1
        if apply:
            conn.execute("DELETE FROM eco_role_selections WHERE rowid=?", (r["_rid"],))
    if dropped:
        print(f"  [{'APPLY' if apply else 'DRY '}] eco_role_selections 机构地址错位绑定剔除: {dropped} 行")
    return dropped


def main() -> int:
    ap = argparse.ArgumentParser(description="资产钱包口径归一为真实链上地址")
    ap.add_argument("--apply", action="store_true", help="真正写库（默认只做预演）")
    ap.add_argument("--db", default=str(settings.db_path), help="SQLite 路径")
    ap.add_argument("--only-asset", action="store_true", help="只迁移资产表")
    ap.add_argument("--skip-schema", action="store_true", help="不做 eco 建表建列")
    ap.add_argument("-v", "--verbose", action="store_true", help="逐行输出")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"[ERR] 数据库不存在：{db}")
        return 2
    if not args.skip_schema:
        # 新表新列（eco_energy_flows / operator_wallet / exchanged_by …）先补齐，
        # 否则这些列的存量值本轮迁不到、重启后又以别名口径继续写入。
        from app import db as appdb
        from app.routers import eco
        appdb.init_db()
        eco.init_eco_db()
        print("[schema] init_db / init_eco_db 已执行（缺表缺列补齐）")

    targets = ASSET_TARGETS + ([] if args.only_asset else LEARNING_TARGETS)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    print(f"{'== APPLY ==' if args.apply else '== DRY-RUN =='}  {db}")
    try:
        changed, merged, unresolved = migrate(
            conn, targets, apply=args.apply, verbose=args.verbose)
        filled = backfill_issuer_from_role(conn, args.apply)
        aliases = register_address_aliases(conn, args.apply)
        mismatched = drop_mismatched_org_bindings(conn, args.apply)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    finally:
        conn.close()

    print(f"\n改写列数：{len(targets)}  改写行数：{changed}  唯一键合并删除：{merged}  "
          f"发放方补齐：{filled}  wallet_alias 补登记：{aliases}  错位绑定剔除：{mismatched}")
    if unresolved:
        print(f"未解析（保持原样，需人工确认）{len(unresolved)} 项：")
        for u in sorted(set(unresolved))[:30]:
            print(f"  - {u}")
    if not args.apply:
        print("\n预演结束：未写库。确认无误后加 --apply 执行。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
