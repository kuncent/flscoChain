"""学生钱包一次性回填脚本（任务 #19：一人一钱包）。

用途：
    为 user_info 中有 user_id 但钱包为空 / 仍为演示别名 0xlearner /
    登录默认口径（wallet == user_id）的学生，发放专属钱包别名
    stu:{user_id}（如 stu:stu001），并把别名写回 user_info.wallet。

边界（重要）：
    - 仅回填 user_info.wallet（身份归属字段）+ 在密钥库发放钱包；
      **不迁移任何历史行为数据**（链上余额 / 搭链教程进度 / 学习事件 /
      成绩等）：读侧统计已统一走 security.resolve_wallet_candidates 候选集
      （[wallet, user_id, user_info.wallet, '0xlearner']），历史 0xlearner /
      userId 口径数据依旧可见，无需搬数据；
    - 幂等：wallet 已是 stu: 别名（已迁移）或已有真实钱包（非演示别名、
      非登录默认口径）的行自动跳过，可重复执行；
    - --dry-run：只输出将要发生的变更，不写数据库、不写密钥库。

用法（项目根目录，推荐 backend/.venv）：
    backend/.venv/Scripts/python scripts/migrate_wallets.py --dry-run
    backend/.venv/Scripts/python scripts/migrate_wallets.py
    # 指定库 / 密钥库（自测 / 异机恢复场景）：
    backend/.venv/Scripts/python scripts/migrate_wallets.py --db <sqlite路径> --keystore <keystore路径>

注意：
    - 默认库路径取 CHAIN_DB_PATH 环境变量 / backend 默认配置
      （backend/app/storage/db/chain.sqlite3）；执行前建议停止后端服务，
      避免与运行中进程的写并发冲突；
    - 密钥库加密口令来自环境变量 KEYSTORE_PASSWORD（与后端 .env 保持一致，
      未配置时与后端同样使用开发兜底口令）。
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import List, Tuple

# 允许从项目根直接导入 backend.app 包
ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app import keystore as ks  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import now  # noqa: E402

# 与 auth.py / keystore.py 保持一致的口径
DEMO_LEARNER_WALLET = "0xlearner"
STUDENT_ROLE_ID = 4

# 迁移类别说明：
#   todo      → 需要发放钱包并回填（空 / 0xlearner / == user_id）
#   already   → 已是 stu: 别名，跳过（幂等）
#   protected → 已有真实钱包 / 教师管理员配置，跳过（不覆盖）
CATEGORY_LABELS = {
    "todo": "待迁移",
    "already": "已迁移",
    "protected": "保留现状",
}


def classify(wallet: str, uid: str) -> str:
    """判定某行 user_info.wallet 的迁移类别：todo / already / protected。"""
    cur = (wallet or "").strip()
    cur_l = cur.lower()
    if cur_l.startswith(ks.STUDENT_ALIAS_PREFIX):
        return "already"
    if cur and cur_l != DEMO_LEARNER_WALLET and cur != uid:
        return "protected"
    return "todo"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="学生钱包一次性回填：provision stu:{user_id} 并写回 user_info.wallet"
    )
    ap.add_argument("--dry-run", action="store_true",
                    help="演练模式：只输出计划，不写数据库、不写密钥库")
    ap.add_argument("--db", default="",
                    help="SQLite 库路径（默认 CHAIN_DB_PATH / backend 默认配置）")
    ap.add_argument("--keystore", default="",
                    help="密钥库文件路径（默认 backend/app/storage/keystore.json）")
    args = ap.parse_args()

    # 覆盖密钥库位置需在首次使用前设置（自测 / 异机场景）
    if args.keystore:
        ks.KEYSTORE_FILE = Path(args.keystore).resolve()
        ks._cache.clear()

    db_path = Path(args.db).resolve() if args.db else Path(settings.db_path)
    if not db_path.exists():
        print(f"[migrate] 数据库不存在: {db_path}")
        return 1
    print(f"[migrate] 数据库  : {db_path}")
    print(f"[migrate] 密钥库  : {ks.KEYSTORE_FILE}")
    print(f"[migrate] 模式    : {'DRY-RUN（不落盘）' if args.dry_run else '真实执行'}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT user_id, COALESCE(wallet,'') AS wallet, COALESCE(name,'') AS name "
            "FROM user_info WHERE role_id=? AND TRIM(COALESCE(user_id,''))<>'' "
            "ORDER BY user_id",
            (STUDENT_ROLE_ID,),
        ).fetchall()
    except sqlite3.OperationalError as e:
        print(f"[migrate] user_info 表不可用: {e}")
        return 1

    stats = {"todo": 0, "already": 0, "protected": 0}
    todos: List[Tuple[str, str]] = []
    for r in rows:
        uid = (r["user_id"] or "").strip()
        if not uid:
            continue
        wallet = (r["wallet"] or "").strip()
        cat = classify(wallet, uid)
        stats[cat] += 1
        if cat == "todo":
            todos.append((uid, wallet))
        print(f"  - {uid:<20} {r['name']:<10} wallet={wallet!r:<14} → {CATEGORY_LABELS[cat]}")

    print(
        f"[migrate] 学生总数 {len(rows)}：待迁移 {stats['todo']}，"
        f"已迁移 {stats['already']}，保留现状（真实钱包/配置） {stats['protected']}"
    )

    if args.dry_run:
        for uid, wallet in todos:
            print(f"  [dry-run] 将 provision {ks.student_alias(uid)}"
                  f"（原 wallet={wallet!r}）并写回 user_info.wallet")
        print("[migrate] dry-run 结束：未写数据库、未写密钥库。")
        return 0

    if not todos:
        print("[migrate] 无需迁移。")
        return 0

    updated = 0
    try:
        for uid, wallet in todos:
            alias, addr = ks.provision_student_wallet(uid)
            conn.execute(
                "UPDATE user_info SET wallet=?, updated_at=? WHERE user_id=?",
                (alias, now(), uid),
            )
            updated += 1
            print(f"  [ok] {uid:<20} {wallet!r:<14} → {alias} ({addr})")
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[migrate] 执行失败已回滚: {e}")
        return 1
    finally:
        conn.close()

    print(
        f"[migrate] 完成：回填 {updated} 个学生钱包；历史行为数据未迁移"
        f"（读侧钱包候选集已兼容 0xlearner / userId 口径）。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
