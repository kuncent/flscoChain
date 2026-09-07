"""身份归一与成绩归并一次性脚本（P0-2「一个学生四套钱包口径」的收口动作）。

用途（三件事，全部默认 dry-run，加 --apply 才写库）：
  1) 别名登记：把 user_info 中每个用户的合法钱包口径（user_id / user_info.wallet /
     stu: 专属别名 / 密钥库真实 0x 地址）写入 wallet_alias 归属表，使
     security.resolve_wallet_candidates() 在没有重新登录的情况下也能立刻拿到
     完整候选集（读侧统计、报告取数、成绩册匹配都依赖它）。
  2) 历史共享钱包认领：--claim 0xlearner --for tzs001 把一人一钱包上线前写在
     公共演示钱包名下的历史数据显式归回某个学生（写 claimed_by 审计列）。
     **不做任何自动认领**：内置演示钱包只有被显式认领才会进入该生候选集，
     否则会把全班数据互相污染。
  3) 成绩册重复行归并：同一 (课程, 学生) 因四套口径产生的多行（教师正式行 +
     系统草稿行 + W0xlearner 造主键行）归并为唯一有效行；被下线的行**先整行
     原文写入 grade_merge_archive 再删除**，任何一步都可人工恢复。

安全边界（重要）：
  - 一个分组里出现 ≥2 条「教师亲手录入」的行（不同教师给同一学生打了不同分）
    → 一律不动，只报告为需人工裁决；
  - student_id 是 `W{wallet[:10]}` 造出来的、且其钱包未被认领 → 身份不可识别，
    只报告不归并（认领之后再跑一次即可归并）；
  - 内置演示钱包（0xlearner / 0xadmin / default …）不会被步骤 1 自动归属。

用法（项目根目录，推荐 backend/.venv；执行前建议先停后端服务）：
    backend/.venv/Scripts/python scripts/normalize_identity.py
    backend/.venv/Scripts/python scripts/normalize_identity.py --apply
    backend/.venv/Scripts/python scripts/normalize_identity.py --claim 0xlearner --for tzs001 --by admin001 --apply
    backend/.venv/Scripts/python scripts/normalize_identity.py --merge-grades --apply
    # 指定库 / 密钥库（自测 / 异机恢复场景）：
    backend/.venv/Scripts/python scripts/normalize_identity.py --db <sqlite路径> --keystore <keystore路径>

脚本启动时会先调用 app.db.init_db() 同步建表（幂等），因此可直接在刚复制
出来、还没跑过新版后端的备份库上做 dry-run 演练。
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 允许从项目根直接导入 backend.app 包
ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app import keystore as ks  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import init_db, now  # noqa: E402
from app.roster import norm_class  # noqa: E402
from app.security import (  # noqa: E402
    BUILTIN_WALLETS,
    alias_kind,
    claim_legacy_alias,
    is_placeholder_student_id,
    principal_of,
    register_wallet_aliases,
    resolve_wallet_candidates,
)

STUDENT_ROLE_ID = 4


# ---------------------------------------------------------------------------
# 1) 别名登记
# ---------------------------------------------------------------------------
def aliases_of_user(conn, uid: str, wallet: str, role_id: int) -> Dict[str, str]:
    """该用户当前所有可确认的钱包口径 → {别名: kind}（小写由下层规范化）。"""
    out: Dict[str, str] = {uid: "user_id"}
    w = (wallet or "").strip()
    if w:
        out[w] = alias_kind(w, uid)
    sa = ks.student_alias(uid)
    if sa:
        out[sa] = "student_alias"
    addr = ks.get_account_address(sa) if sa else None
    if addr:
        out[addr] = "evm_addr"
    if int(role_id or 0) != STUDENT_ROLE_ID:
        # 教师 / 管理员无专属学生钱包：不注册 stu: 与 evm 口径，避免越权认领
        out.pop(sa, None)
        if addr:
            out.pop(addr, None)
    return out


def step_register_aliases(conn, apply_changes: bool) -> Tuple[int, int]:
    """为 user_info 全量用户登记别名。返回 (用户数, 新增别名行数)。"""
    rows = conn.execute(
        "SELECT user_id, COALESCE(wallet,'') AS wallet, COALESCE(role_id,0) AS role_id "
        "FROM user_info WHERE TRIM(COALESCE(user_id,''))<>'' ORDER BY user_id"
    ).fetchall()
    users = added = 0
    for r in rows:
        uid = str(r["user_id"] or "").strip()
        if not uid:
            continue
        users += 1
        aliases = aliases_of_user(conn, uid, r["wallet"], r["role_id"])
        if apply_changes:
            added += register_wallet_aliases(conn, uid, aliases, claimed_by="script")
        else:
            known = {
                str(x[0]) for x in conn.execute(
                    "SELECT alias FROM wallet_alias WHERE user_id=?", (uid,)
                ).fetchall()
            }
            new = [a for a in (x.lower() for x in aliases if x) if a not in known
                   and a not in BUILTIN_WALLETS]
            if new:
                print(f"  [dry-run] {uid:<20} 将登记别名 {new}")
            added += len(new)
    return users, added


# ---------------------------------------------------------------------------
# 2) 历史共享钱包认领
# ---------------------------------------------------------------------------
def step_claim(conn, alias: str, for_uid: str, by: str, apply_changes: bool) -> int:
    if not apply_changes:
        print(f"  [dry-run] 将把 {alias} 认领给 {for_uid}（操作人 {by or '未记录'}）")
        return 0
    res = claim_legacy_alias(conn, alias, for_uid, by or "script")
    print(f"  [ok] 认领 {res['alias']} → {res['user_id']}"
          f"（原归属 {res['previous_owner'] or '无'}，操作人 {res['claimed_by']}）")
    return 1


# ---------------------------------------------------------------------------
# 3) 成绩册重复行归并
# ---------------------------------------------------------------------------
# 主体口径直接复用 security.principal_of（与成绩看板 /stats 的去重键同一函数），
# 避免脚本与线上对「同一人」判定不一致。


def _is_teacher_row(teacher_id) -> bool:
    """教师亲手录入的行（系统一律不得改写，与 grades.SYSTEM_TEACHER_IDS 同口径）。"""
    return str(teacher_id if teacher_id is not None else "").strip() not in ("system", "")


def step_merge_grades(conn, apply_changes: bool) -> Dict[str, int]:
    """按 (课程, 主体) 归并重复成绩行；被下线行先入 grade_merge_archive。"""
    stats = {"groups": 0, "merged": 0, "conflicts": 0, "unknown": 0, "rewritten": 0}
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM student_grades ORDER BY course, student_id, id").fetchall()]
    groups: Dict[Tuple[str, str], List[dict]] = {}
    for r in rows:
        p = principal_of(conn, str(r.get("wallet") or ""), str(r.get("student_id") or ""))
        if not p:
            stats["unknown"] += 1
            print(f"  [skip] 身份未识别：id={r['id']} student_id={r['student_id']!r} "
                  f"wallet={r['wallet']!r}（可先 --claim 其历史钱包再跑一次）")
            continue
        groups.setdefault((str(r.get("course") or ""), p), []).append(r)

    for (course, principal), grp in sorted(groups.items()):
        stats["groups"] += 1
        if len(grp) < 2:
            continue
        teacher_rows = [r for r in grp if _is_teacher_row(r.get("teacher_id"))]
        if len(teacher_rows) > 1:
            stats["conflicts"] += 1
            print(f"  [conflict] {course} / {principal}：{len(teacher_rows)} 条教师正式行"
                  f"（id={[r['id'] for r in teacher_rows]}）需人工裁决，脚本不动")
            continue
        # 有效行：教师行优先，其次更新时间最新，最后 id 最小（稳定）
        keeper = sorted(
            grp,
            key=lambda r: (1 if _is_teacher_row(r.get("teacher_id")) else 0,
                           str(r.get("updated_at") or ""), -int(r["id"])),
        )[-1]
        drop = [r for r in grp if int(r["id"]) != int(keeper["id"])]

        u = conn.execute(
            "SELECT name, student_id, class_id, school_id FROM user_info WHERE user_id=?",
            (principal,),
        ).fetchone()
        # 学号只朝「更像人的真实学号」方向收敛，三条按优先级：
        #   ① user_info 有权威学号 → 用它；
        #   ② 保留行当前学号是系统造的占位主键（W+钱包前缀）→ 收敛为主体 user_id；
        #   ③ 其余一律不动 —— 没有 user_info 佐证时把教师行的真实 SSO 学号
        #      （如 19898800030）改写成 tzs001，反而又造出一套新口径，正是 P0-2 要消利的。
        cur_sid = str(keeper.get("student_id") or "")
        auth_sid = str((u["student_id"] if u else "") or "").strip()
        if auth_sid:
            want_sid = auth_sid
        elif is_placeholder_student_id(cur_sid, str(keeper.get("wallet") or "")):
            want_sid = principal
        else:
            want_sid = cur_sid
        want_sname = str((u["name"] if u else "") or "") or str(keeper.get("student_name") or "")
        want_class = norm_class(str((u["class_id"] if u else "") or ""))
        want_school = str((u["school_id"] if u else "") or "")

        if apply_changes:
            ts = now()
            for r in drop:
                conn.execute(
                    "INSERT INTO grade_merge_archive(grade_id,payload,merged_into,reason,created_at)"
                    " VALUES(?,?,?,?,?)",
                    (int(r["id"]), json.dumps(dict(r), ensure_ascii=False, default=str),
                     int(keeper["id"]),
                     f"P0-2 归并：同一 ({course}, {principal}) 的重复口径行", ts),
                )
                conn.execute("DELETE FROM student_grades WHERE id=?", (int(r["id"]),))
            if (str(keeper.get("student_id") or "") != want_sid
                    or (want_class and str(keeper.get("class_id") or "") != want_class)):
                conn.execute(
                    "UPDATE student_grades SET student_id=?, student_name=?, class_id=?, "
                    "school_id=COALESCE(NULLIF(?, ''), school_id) WHERE id=?",
                    (want_sid, want_sname, want_class, want_school, int(keeper["id"])),
                )
                stats["rewritten"] += 1
        stats["merged"] += len(drop)
        print(f"  [{'ok' if apply_changes else 'dry-run'}] {course} / {principal}："
              f"保留 id={keeper['id']}（{'教师行' if _is_teacher_row(keeper.get('teacher_id')) else '系统行'}"
              f"，student_id {keeper['student_id']!r} → {want_sid!r}），"
              f"下线 {[int(r['id']) for r in drop]}")
    return stats


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="身份归一（wallet_alias 登记 / 历史钱包认领）+ 成绩册重复行归并（P0-2）"
    )
    ap.add_argument("--apply", action="store_true", help="真实写库（默认只输出计划）")
    ap.add_argument("--skip-aliases", action="store_true", help="跳过别名登记步骤")
    ap.add_argument("--merge-grades", action="store_true", help="执行成绩册重复行归并")
    ap.add_argument("--claim", default="", help="认领历史共享钱包（如 0xlearner）")
    ap.add_argument("--for", dest="for_uid", default="", help="认领归属的 user_id")
    ap.add_argument("--by", default="", help="认领操作人（审计用）")
    ap.add_argument("--db", default="", help="SQLite 库路径（默认 CHAIN_DB_PATH / backend 配置）")
    ap.add_argument("--keystore", default="", help="密钥库文件路径")
    args = ap.parse_args()

    if args.keystore:
        ks.KEYSTORE_FILE = Path(args.keystore).resolve()
        ks._cache.clear()

    db_path = Path(args.db).resolve() if args.db else Path(settings.db_path)
    if not db_path.exists():
        print(f"[identity] 数据库不存在: {db_path}")
        return 1
    print(f"[identity] 数据库  : {db_path}")
    print(f"[identity] 模式    : {'真实执行' if args.apply else 'DRY-RUN（不落盘）'}")

    # 先走一遍应用建表迁移，保证 wallet_alias / grade_merge_archive 等新表存在。
    #   不重复写 DDL：本脚本与后端共用 app.db.init_db（全量 CREATE IF NOT EXISTS
    #   + 在线补列，幂等），否则在未跑过新版后端的库（刚复制的备份）上
    #   连 dry-run 都会因 “no such table: wallet_alias” 直接失败。
    #   pydantic settings 字段可直接赋值，get_conn() 按新路径重建连接。
    settings.db_path = db_path
    init_db()

    conn: Optional[sqlite3.Connection] = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rc = 0
    try:
        if args.claim:
            if not args.for_uid:
                print("[identity] --claim 必须同时给 --for <user_id>")
                return 2
            step_claim(conn, args.claim, args.for_uid, args.by, args.apply)
        if not args.skip_aliases:
            users, added = step_register_aliases(conn, args.apply)
            print(f"[identity] 别名登记：用户 {users} 个，{'新增' if args.apply else '待新增'} {added} 条")
        if args.merge_grades:
            st = step_merge_grades(conn, args.apply)
            print(f"[identity] 成绩归并：分组 {st['groups']}，下线 {st['merged']}，"
                  f"教师冲突待裁决 {st['conflicts']}，身份未识别 {st['unknown']}，"
                  f"主键改写 {st['rewritten']}")
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[identity] 执行失败已回滚: {type(e).__name__}: {e}")
        rc = 1
    finally:
        conn.close()

    if args.apply:
        print("[identity] 完成。抽样核对候选集：")
        c2 = sqlite3.connect(str(db_path))
        c2.row_factory = sqlite3.Row
        try:
            for r in c2.execute(
                "SELECT user_id FROM user_info WHERE role_id=? ORDER BY user_id LIMIT 5",
                (STUDENT_ROLE_ID,),
            ).fetchall():
                uid = str(r["user_id"])
                print(f"  - {uid}: {resolve_wallet_candidates(c2, uid, uid)}")
        finally:
            c2.close()
    else:
        print("[identity] dry-run 结束：未写数据库。加 --apply 生效。")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
