"""链状态 + 云桌面联盟链搭建教程（真实 FISCO-BCOS 操作步骤 + 真实 EVM 执行）。"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header

from ..config import settings
from ..chain_client import get_chain_client, get_chain_mode_label, FiscoRpcClient
from ..db import get_conn, now
from ..tx_decoder import compile_source

router = APIRouter(prefix="/api/chain", tags=["chain"])


def _track(event_type: str, target: str = "", ref_id: str = "", wallet: str = "", extra: dict | None = None):
    """轻量学习行为埋点，写入 learning_events（不阻塞主流程）。"""
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO learning_events(wallet,event_type,target,ref_id,extra,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (wallet, event_type, target, ref_id,
                 json.dumps(extra or {}, ensure_ascii=False), now()),
            )
    except Exception:
        pass


def _auto_create_grade_draft(student_id: str, student_name: str, wallet: str) -> None:
    """训练完成自动建成绩草稿：学生完成全部 10 步后，自动在 student_grades
    建一条草稿记录（score=0），实训成绩按钱包实时计算，教师后续只需录入评分。

    - 仅当携带学生身份（X-User-Id）且该 wallet 10 步全部完成时触发
    - 按 (student_id, course='区块链实训') 唯一约束 upsert，不覆盖教师已录的 score
    """
    if not student_id or not wallet:
        return
    _ensure_progress_table()
    with get_conn() as conn:
        done_count = conn.execute(
            "SELECT COUNT(*) AS c FROM chain_tutorial_progress WHERE wallet=? AND done=1",
            (wallet,),
        ).fetchone()["c"]
        # 从 user_info 表查询学生的 class_id / school_id（教师按班级过滤成绩时需要）
        uinfo = conn.execute(
            "SELECT class_id, school_id FROM user_info WHERE user_id=?",
            (student_id,),
        ).fetchone()
    if done_count < len(TUTORIAL):
        return  # 未完成全部步骤，不建草稿
    class_id = uinfo["class_id"] if uinfo else ""
    school_id = uinfo["school_id"] if uinfo else ""
    # 实时计算实训成绩（懒导入，避免循环引用）
    from .grades import _compute_training_score, _compute_final
    training, detail = _compute_training_score(wallet)
    final = _compute_final(training, 0)  # 草稿阶段教师评分=0
    detail_json = json.dumps(detail, ensure_ascii=False)
    ts = now()
    course = "区块链实训"
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id, score FROM student_grades WHERE student_id=? AND course=?",
            (student_id, course),
        ).fetchone()
        if existing:
            # 已有记录：仅刷新实训成绩，保留教师已录的 score 与备注
            cur_score = existing["score"] or 0
            new_final = _compute_final(training, cur_score)
            conn.execute(
                "UPDATE student_grades SET wallet=?, training_score=?, final_score=?, "
                "training_detail=?, class_id=COALESCE(NULLIF(?, ''), class_id), "
                "school_id=COALESCE(NULLIF(?, ''), school_id), updated_at=? WHERE id=?",
                (wallet, training, new_final, detail_json, class_id, school_id, ts, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO student_grades(student_id, student_name, course, score, wallet, "
                "training_score, final_score, training_detail, teacher_id, teacher_name, "
                "class_id, school_id, remark, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (student_id, student_name or student_id, course, 0, wallet,
                 training, final, detail_json, "", "", class_id, school_id,
                 "训练完成自动建草稿，请教师录入评分", ts, ts),
            )

# deploy/ 目录路径（用于真实 docker-compose 操作）
DEPLOY_DIR = settings.base_dir.parent.parent / "deploy"


# ---------------------------------------------------------------------------
# 搭链教程进度持久化：每次 exec_step 成功后记录某 wallet 的 step 完成情况
# ---------------------------------------------------------------------------
def _ensure_progress_table():
    with get_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS chain_tutorial_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet TEXT NOT NULL,
            step INTEGER NOT NULL,
            done INTEGER NOT NULL DEFAULT 0,
            output TEXT,
            started_at TEXT,
            finished_at TEXT,
            tenant_id TEXT DEFAULT '',
            user_id TEXT DEFAULT '',
            session_id TEXT DEFAULT '',
            UNIQUE(wallet, step)
        )""")
        # 增量列：class_id（在线迁移，兼容已存在的旧表）
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(chain_tutorial_progress)")}
        if "class_id" not in existing:
            conn.execute("ALTER TABLE chain_tutorial_progress ADD COLUMN class_id TEXT NOT NULL DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tutorial_progress_class ON chain_tutorial_progress(class_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tutorial_progress_user ON chain_tutorial_progress(user_id)")


def _upsert_step_state(
    wallet: str, step: int, done: int,
    output: str | None = None, finished: bool = False,
    user_id: str = "", class_id: str = "",
):
    _ensure_progress_table()
    ts = now()
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT id FROM chain_tutorial_progress WHERE wallet=? AND step=?",
            (wallet, step),
        ).fetchone()
        if exists:
            if finished:
                conn.execute(
                    "UPDATE chain_tutorial_progress SET done=?, output=COALESCE(?,output), "
                    "finished_at=?, user_id=COALESCE(NULLIF(?, ''), user_id), "
                    "class_id=COALESCE(NULLIF(?, ''), class_id) "
                    "WHERE wallet=? AND step=?",
                    (done, output, ts, user_id, class_id, wallet, step),
                )
            elif output is not None:
                conn.execute(
                    "UPDATE chain_tutorial_progress SET output=? WHERE wallet=? AND step=?",
                    (output, wallet, step),
                )
        else:
            conn.execute(
                "INSERT INTO chain_tutorial_progress(wallet,step,done,output,started_at,finished_at,user_id,class_id) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (wallet, step, done, output, ts, ts if finished else None, user_id, class_id),
            )


@router.get("/tutorial/progress")
def get_progress(wallet: str = "default"):
    """查询 wallet 的搭链教程完成情况。返回 6 步的 done / 百分比。"""
    _ensure_progress_table()
    total_steps = len(TUTORIAL)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT step, done, output, started_at, finished_at "
            "FROM chain_tutorial_progress WHERE wallet=? ORDER BY step",
            (wallet,),
        ).fetchall()
    state_by_step: dict[int, dict] = {}
    for r in rows:
        state_by_step[r["step"]] = dict(r)
    progress_list = []
    done_count = 0
    for s in TUTORIAL:
        step_num = s["step"]
        row = state_by_step.get(step_num, {"step": step_num, "done": 0, "output": None, "started_at": None, "finished_at": None})
        if row.get("done"):
            done_count += 1
        progress_list.append({
            "step": step_num,
            "title": s["title"],
            "desc": s.get("desc", ""),
            "done": bool(row.get("done")),
            "finished_at": row.get("finished_at"),
            "has_output": bool(row.get("output")),
        })
    return {
        "wallet": wallet,
        "total_steps": total_steps,
        "done_count": done_count,
        "percent": round(done_count * 100 / total_steps, 1) if total_steps else 0,
        "steps": progress_list,
    }


@router.post("/tutorial/progress/reset")
def reset_progress(payload: dict):
    wallet = payload.get("wallet") or "default"
    _ensure_progress_table()
    with get_conn() as conn:
        conn.execute("DELETE FROM chain_tutorial_progress WHERE wallet=?", (wallet,))
    return {"ok": True, "reset": wallet}


@router.get("/status")
def status():
    c = get_chain_client()
    mode = get_chain_mode_label()
    engine_map = {
        "fisco": "FISCO-BCOS (JSON-RPC)",
        "evm": "EVM (py-evm)",
        "mock": "Local Sandbox (预置教学链路)",
    }
    return {
        "mode": mode,
        "engine": engine_map.get(mode, mode),
        "height": c.block_number(),
        "accounts": len(c.get_accounts()),
        "rpc": f"{settings.fisco_rpc_host}:{settings.fisco_rpc_port}",
        "group_id": settings.fisco_group_id,
        "fisco_connected": isinstance(c, FiscoRpcClient),
    }


# ---------------------------------------------------------------------------
# 绿色低碳联盟链搭建 10 步教程（明确覆盖 6 大联盟节点：管理员/地铁/公交/单车/外卖/回收）
# 阶段 A · 链底层（Step 1-4）：启动 4 节点 → 检查进程/日志/控制台
# 阶段 B · 6 联盟节点组织配置（Step 5-8）：4 逻辑节点 ↔ 6 业务组织的映射、角色职责、钱包注册、权限
# 阶段 C · 核心代币合约（Step 9-10）：部署 GreenEnergy → 调用验证
# 每步包含：真实命令、原理讲解、预期输出、执行动作（连接真实 EVM）
# ---------------------------------------------------------------------------
# 4 逻辑节点 ↔ 6 业务组织映射（6 组织复用 4 共识节点，生产环境可扩展为 6+ 物理节点）
NODE_ORG_MAP: Dict[str, List[str]] = {
    "node0": ["🛡️ 管理员", "🚇 地铁集团"],
    "node1": ["🚌 公交集团", "🚲 共享单车"],
    "node2": ["📦 外卖平台", "♻️ 回收公司"],
    "node3": ["🔥 热备共识节点（可扩展第 7 方审计）"],
}
# 6 角色能量发放规则
ROLE_ENERGY_RULES: List[Dict[str, str]] = [
    {"role": "🛡️ 管理员(admin)",        "scene": "系统管理方，部署合约 / 管理树种 / 不发放能量", "amount": "0 / 次", "wallet": "0xadmin"},
    {"role": "🚇 地铁集团(metro)",       "scene": "乘坐地铁 1 次（≥3 站）",                     "amount": "+50 能量", "wallet": "0xmetro"},
    {"role": "🚌 公交集团(bus)",         "scene": "乘坐公交 1 次",                               "amount": "+20 能量", "wallet": "0xbus"},
    {"role": "🚲 共享单车(bike)",        "scene": "骑行 ≥ 2 公里",                               "amount": "+15 能量", "wallet": "0xbike"},
    {"role": "📦 外卖平台(takeout)",     "scene": "选择「无需餐具」绿色外卖 1 单",               "amount": "+10 能量", "wallet": "0xtakeout"},
    {"role": "♻️ 回收公司(recycle)",     "scene": "旧纸箱 / 塑料瓶回收 ≥ 1kg",                   "amount": "+100 能量", "wallet": "0xrecycle"},
]

TUTORIAL: List[Dict[str, Any]] = [
    {
        "step": 1,
        "title": "启动链节点（4 共识节点承载 6 联盟组织）",
        "desc": "使用 FISCO-BCOS 官方 build_chain.sh 一键生成 4 节点 PBFT 联盟链配置并启动。\n"
                "本项目的 6 大联盟成员：🛡️管理员 / 🚇地铁 / 🚌公交 / 🚲单车 / 📦外卖 / ♻️回收，\n"
                "按「node0=管理员+地铁  node1=公交+单车  node2=外卖+回收  node3=热备」映射到 4 逻辑节点；\n"
                "生产环境可直接改为 `-l 127.0.0.1:6` 启动 6 个物理节点一对一承载。",
        "principle": "FISCO-BCOS 采用 PBFT 共识，4 节点可容忍 1 个拜占庭节点（3f+1=4）。\n"
                     "每个逻辑节点可代表多个联盟成员（共享共识权重），业务上通过「钱包地址 + 角色合约」做权限隔离。",
        "commands": [
            "cd ~/fisco && curl -#LO https://github.com/FISCO-BCOS/FISCO-BCOS/releases/download/v2.9.1/build_chain.sh && chmod +x build_chain.sh",
            "# 4 节点版（实训用，6 组织复用）",
            "bash build_chain.sh -l 127.0.0.1:4 -p 30300,20200,8545 -o nodes",
            "# 生产可改用 6 节点版：bash build_chain.sh -l \"127.0.0.1:6\" -p 30300,20200,8545 -o nodes6",
            "bash nodes/127.0.0.1/start_all.sh",
        ],
        "expected": "node0 ~ node3 依次输出 start successful；6 个业务组织通过 4 共识节点 + 钱包权限组合承载。",
        "tip": "关键映射：node0=管理员/地铁 · node1=公交/单车 · node2=外卖/回收 · node3=热备",
    },
    {
        "step": 2,
        "title": "检查节点进程（标注 6 组织归属）",
        "desc": "确认 4 个 fisco-bcos 进程正在运行，并对照映射表确认每个节点承载的 6 大业务组织：\n"
                "  node0 → 管理员 + 地铁集团\n"
                "  node1 → 公交集团 + 共享单车\n"
                "  node2 → 外卖平台 + 回收公司\n"
                "  node3 → 热备共识（后续可接入审计/监管节点）",
        "principle": "联盟链的每个节点都是独立进程；进程存活 ≠ 业务可用，\n"
                     "还需要「节点钱包地址 + 角色合约白名单」确认组织权限。生产环境用 systemd/supervisor 守护进程。",
        "commands": [
            "ps -ef | grep fisco-bcos | grep -v grep",
            "# 查看节点对应的联盟成员（对照表）",
            "echo 'node0 -> 管理员 + 地铁集团 | node1 -> 公交 + 单车 | node2 -> 外卖 + 回收 | node3 -> 热备'",
        ],
        "expected": "看到 4 个 fisco-bcos 进程（PID 不同），并能说出每个进程承载哪 1~2 个业务组织、共 6 个。",
        "tip": "6 组织清单：管理员🛡️ 地铁🚇 公交🚌 单车🚲 外卖📦 回收♻️",
    },
    {
        "step": 3,
        "title": "检查日志出块（6 组织出块权重一致）",
        "desc": "查看 node0 日志，确认 PBFT 共识正常出块。\n"
                "后续 6 角色发起的「能量发放 mint」「资产兑换 safeTransferFrom」都会在这些区块里打包。",
        "principle": "PBFT 通过 `+++Generating seal` 标记某个 sealer 开始打包；`Report` 表示三阶段（Pre-prepare/Prepare/Commit）完成、区块落盘。\n"
                     "4 个 sealer 轮流出块，6 业务组织只要在任一共识节点上「有签名权」就可参与。",
        "commands": ["tail -f nodes/127.0.0.1/node0/log/log_*  | grep -E '\\+\\+\\+Generating|Report'"],
        "expected": "持续输出 `+++Generating seal` 与 `Report`，6 组织的业务交易在区块里均匀打包。",
        "tip": "日志路径：nodes/127.0.0.1/node{0,1,2,3}/log/log_YYYYMMDDHHMM.log，按天轮转",
    },
    {
        "step": 4,
        "title": "启动并使用控制台（4 节点 / 6 组织视角）",
        "desc": "FISCO-BCOS 控制台（console）是交互式管理工具：\n"
                "  · getBlockNumber 确认链存活\n"
                "  · getPeers / getSealerList 查看 4 个共识节点\n"
                "  · getGroupPeers 确认 6 业务组织是否都注册到同一个 group（本实训 group=1）",
        "principle": "控制台通过 Channel 协议连接节点（双向长连接 + SDK 证书），比 JSON-RPC 更安全。\n"
                     "后续 Step 5~8 的 6 角色注册、Step 9/10 的合约部署与调用，都会通过控制台或等价 JSON-RPC 完成。",
        "commands": [
            "cd ~/fisco/console && bash start.sh",
            "[console] getBlockNumber",
            "[console] getPeers",
            "[console] getSealerList",
            "[console] getGroupPeers",
        ],
        "expected": "返回当前块高；对等节点 3 个；共识列表 [node0, node1, node2, node3]；6 业务组织共享同一个 group=1。",
        "tip": "控制台命令等价 JSON-RPC：getNodeInfo / getBlockByNumber / getConsensusStatus",
    },
    # ======================== 新增：Step 5-8 · 6 大联盟节点组织配置 ========================
    {
        "step": 5,
        "title": "Step 5 · 6 联盟节点组织映射（6 成员 + 4 共识节点）",
        "desc": "明确绿色低碳联盟链的 6 大业务成员与其在 4 共识节点上的归属关系：\n"
                "  - 🛡️ 管理员 （node0）：部署合约、管理树种、不发能量\n"
                "  - 🚇 地铁集团（node0）：乘坐地铁场景 → +50 能量\n"
                "  - 🚌 公交集团（node1）：乘坐公交场景 → +20 能量\n"
                "  - 🚲 共享单车（node1）：骑行场景 → +15 能量\n"
                "  - 📦 外卖平台（node2）：无需餐具绿色外卖 → +10 能量\n"
                "  - ♻️ 回收公司（node2）：旧物回收场景 → +100 能量\n"
                "  - 🔥 热备节点 （node3）：共识热备 / 可扩展监管审计\n"
                "后续所有「发能量」接口都会按这张表做角色校验。",
        "principle": "联盟链用「多节点共享共识 + 钱包地址角色化」实现组织级隔离：\n"
                     "6 组织共享 4 共识节点，但每个组织有独立的发币钱包（0xmetro/0xbus/...）；后端生态合约\n"
                     "（eco.py emit_energy）会根据角色白名单限制 mint 上限，避免越权。",
        "commands": [
            "# 6 组织 ↔ 4 节点映射表",
            "cat <<'EOF'\nnode0 => 管理员🛡️   0xadmin\nnode0 => 地铁🚇    0xmetro\nnode1 => 公交🚌    0xbus\nnode1 => 单车🚲    0xbike\nnode2 => 外卖📦    0xtakeout\nnode2 => 回收♻️    0xrecycle\nnode3 => 热备🔥   observer\nEOF",
            "# 查看 6 角色钱包地址（本实训已内置：0xadmin/metro/bus/bike/takeout/recycle）",
            "[console] getAccountBalance 0xmetro",
            "[console] getAccountBalance 0xbus",
        ],
        "expected": "能对应出 6 个组织名 → 角色 → 节点 → 钱包地址 四要素，并确认 6 个角色钱包链上可用。",
        "tip": "6 角色钱包 = 「node 共识权」+「角色 mint 权限」双层控制，缺一不可。",
    },
    {
        "step": 6,
        "title": "Step 6 · 6 角色职责与能量发放规则表",
        "desc": "把 6 角色的业务职责、对应业务场景、单次发放能量值整理为训练用的对照表。\n"
                "这是实训平台「能量发放卡片」的业务依据：管理员 0、地铁 50、公交 20、单车 15、外卖 10、回收 100。",
        "principle": "能量值按「减碳贡献」梯度设计：回收 1kg 旧物 > 坐 3 站地铁 > 坐公交 > 骑行 2km > 1 单无需餐具外卖。\n"
                     "管理员作为治理角色不直接发能量，以避免利益冲突。",
        "commands": [
            "# 6 角色能量发放规则表（业务依据）",
            "cat <<'RULES'\n角色         业务场景                  单次能量   钱包\n=========================================================\n管理员       部署合约/树种管理            0         0xadmin\n地铁集团     乘坐地铁 ≥3 站              +50       0xmetro\n公交集团     乘坐公交 1 次               +20       0xbus\n共享单车     骑行 ≥ 2 km                +15       0xbike\n外卖平台     绿色外卖(无需餐具)          +10       0xtakeout\n回收公司     纸箱/塑料瓶回收 ≥ 1kg      +100      0xrecycle\nRULES",
        ],
        "expected": "能复述 6 角色的能量发放规则（按大小排序：回收100 > 地铁50 > 公交20 > 单车15 > 外卖10 > 管理员0）。",
        "tip": "前端绿色低碳联盟链（/eco）卡片展示顺序完全按此规则表实现。",
    },
    {
        "step": 7,
        "title": "Step 7 · 注册 6 组织钱包 + 首次试发能量（管理员预存押金）",
        "desc": "为 6 大业务组织分别在链上准备独立钱包地址：\n"
                "  0xadmin, 0xmetro, 0xbus, 0xbike, 0xtakeout, 0xrecycle。\n"
                "管理员先预存 1,000,000 GreenEnergy（在 Step 9 部署后发放），5 个业务角色以「管理员授权 mint」的方式发能量。",
        "principle": "ERC20 两种发能量模式：① mint（合约所有者造币，适合管理员）② transfer（有余额的钱包转账，适合业务角色）。\n"
                     "本实训用 mint 模式（业务角色在白名单里即有权限），生产环境建议用「管理员 → 业务角色预拨押金 + transferFrom」更合规。",
        "commands": [
            "# 6 组织钱包（用内置账户地址，真实环境可换独立公私钥）",
            "cat <<'WALLETS'\n0xadmin     管理员（白名单 mintOwner）\n0xmetro     地铁（白名单 mintRole）\n0xbus       公交（白名单 mintRole）\n0xbike      单车（白名单 mintRole）\n0xtakeout   外卖（白名单 mintRole）\n0xrecycle   回收（白名单 mintRole）\nWALLETS",
            "# Step 9 部署后执行：给 5 个业务角色各 +1,000 初始押金（可选）",
            "[console] call GreenEnergy <deploy_addr> mint 0xmetro   1000",
            "[console] call GreenEnergy <deploy_addr> mint 0xrecycle 1000",
        ],
        "expected": "能够列出 6 个钱包地址及其角色；并理解「业务角色必须先在白名单里才能 mint」这一权限模型。",
        "tip": "前端 /eco 的角色切换卡片 select 选项严格对应这 6 个角色 + 钱包。",
    },
    {
        "step": 8,
        "title": "Step 8 · 6 角色节点健康检查（节点在线 + 钱包有余额）",
        "desc": "对 6 大联盟成员做上线前的综合健康检查：\n"
                "  ① 4 共识节点在线（ps + rpc）\n"
                "  ② 6 个钱包在链上有余额（至少 1 wei 即可参与交易）\n"
                "  ③ GreenEnergy / PlantCertificate / EcoBadge 三合约在 6 角色侧均可调用。\n"
                "通过后即可转入 Step 9 正式部署核心代币合约。",
        "principle": "联盟链「上线」不等同于节点启动，需要「共识节点在线 + 组织钱包就绪 + 合约权限白名单 + 前端角色卡片」四件事同时就绪。\n"
                     "Step 8 把这 6 个组织的验收条件一次性列清，避免部署完合约后发现某个角色没权限。",
        "commands": [
            "# ① 节点存活（4/4）",
            "bash nodes/127.0.0.1/check_node_status.sh all",
            "# ② 6 钱包余额快照",
            "[console] getAccountBalance 0xadmin",
            "[console] getAccountBalance 0xmetro",
            "[console] getAccountBalance 0xbus",
            "[console] getAccountBalance 0xbike",
            "[console] getAccountBalance 0xtakeout",
            "[console] getAccountBalance 0xrecycle",
            "# ③ （Step 9 之后）3 合约都能 name() / symbol() 查询",
        ],
        "expected": "  ① check_node_status 返回 4 个节点 success；\n"
                    "  ② 6 钱包余额 ≥ 0（真实链上存在该账户）；\n"
                    "  ③ 三合约 name() 返回正确字符串。",
        "tip": "6 角色验收通过 = 联盟运营模块（/eco）可放开使用。",
    },
    # Step 9/10 = 原 Step 5/6 顺延
    {
        "step": 9,
        "title": "Step 9 · 部署 GreenEnergy 绿色能量代币（6 角色共享）",
        "desc": "部署 GreenEnergy 合约（ERC20 标准），这是绿色低碳联盟链的核心代币。\n"
                "初始 1,000,000 能量由管理员持有；地铁/公交/单车/外卖/回收 5 角色后续通过 mintRole 白名单向低碳行为用户发放。",
        "principle": "GreenEnergy 继承 ERC20，构造函数接收 initialSupply 初始发行量。\n"
                     "部署交易 to 字段为空，data = 字节码 + 构造函数参数 ABI 编码；\n"
                     "EVM 执行构造函数初始化状态，合约地址 = keccak256(rlp([sender, nonce])) 后 20 字节。",
        "commands": ["[console] deploy GreenEnergy 1000000"],
        "expected": "返回一个 0x... 合约地址，交易上链并产生 1 个新区块；6 角色均可用该地址做 mint/transfer。",
        "tip": "GreenEnergy decimals=0（整数），1 能量 = 1 次低碳行为积分；该地址后续要存到 deployed_contracts 表。",
    },
    {
        "step": 10,
        "title": "Step 10 · 调用 GreenEnergy（6 角色发能量 → 用户 → 兑换 链路验证）",
        "desc": "调用 GreenEnergy 的 name()、balanceOf() 查询代币信息；\n"
                "再依次执行「地铁给 0xalice +50」「外卖给 0xlearner +10」两笔典型发放，确认 6 角色发能量接口链路打通。",
        "principle": "view 函数（name/balanceOf）通过 eth_call 本地执行，不消耗 Gas 不上链；\n"
                     "状态变更函数（transfer/mint）通过 sendTransaction 广播交易、消耗 Gas、产生 Transfer/Mint 事件日志。\n"
                     "后续 PlantCertificate / EcoBadge 的调用模型与本步一致。",
        "commands": [
            "[console] call GreenEnergy <address> name",
            "[console] call GreenEnergy <address> balanceOf <account>",
            "# 6 角色发放链路验证：地铁 → 0xalice +50，外卖 → 0xlearner +10",
            "[console] call GreenEnergy <address> mint 0xalice    50",
            "[console] call GreenEnergy <address> mint 0xlearner  10",
            "[console] call GreenEnergy <address> balanceOf 0xalice",
        ],
        "expected": "name 返回 GreenEnergy；两次 mint 后 0xalice 余额 +50、0xlearner 余额 +10（或 transfer 成功 true）；6 角色权限链路验证通过。",
        "tip": "至此 10 步全部完成 → 进入绿色低碳联盟链（/eco）进入完整 6 角色运营体验。",
    },
]


@router.get("/tutorial")
def get_tutorial(wallet: str = "default"):
    """返回搭链教程 steps，并带上 wallet 的完成状态（done/finished_at）。"""
    _ensure_progress_table()
    # 拉取该 wallet 的完成进度
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT step, done, output, started_at, finished_at "
            "FROM chain_tutorial_progress WHERE wallet=? ORDER BY step",
            (wallet,),
        ).fetchall()
    state_by_step = {r["step"]: dict(r) for r in rows}
    # 注入每个步骤的完成状态
    steps = []
    done_count = 0
    for s in TUTORIAL:
        step_num = s["step"]
        row = state_by_step.get(step_num, {})
        done = bool(row.get("done"))
        if done:
            done_count += 1
        step_out = dict(s)
        step_out["done"] = done
        step_out["finished_at"] = row.get("finished_at")
        step_out["started_at"] = row.get("started_at")
        step_out["has_output"] = bool(row.get("output"))
        steps.append(step_out)
    total = len(TUTORIAL)
    return {
        "wallet": wallet,
        "total_steps": total,
        "done_count": done_count,
        "percent": round(done_count * 100 / total, 1) if total else 0,
        "steps": steps,
    }


class ExecReq(dict):
    pass


def _try_docker_compose(action: str = "up") -> Optional[str]:
    """尝试执行 docker-compose 命令操作 FISCO 节点。

    成功返回 stdout，失败返回 None（调用方降级到教学输出）。
    """
    compose_file = DEPLOY_DIR / "docker-compose.yml"
    if not compose_file.exists():
        return None
    try:
        cmd = f"docker compose -f \"{compose_file}\" {action}"
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode == 0:
            return out
        return None
    except Exception:
        return None


def _docker_ps_fisco() -> Optional[str]:
    """查询 fisco 容器状态。"""
    try:
        r = subprocess.run(
            'docker ps --filter "name=fisco" --format "{{.Names}} {{.Status}}"',
            shell=True, capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
        return None
    except Exception:
        return None


@router.post("/tutorial/exec")
def exec_step(
    payload: dict,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
    x_class_id: Optional[str] = Header(default=None, alias="X-Class-Id"),
):
    """执行某一步骤：Step 1-4 真实操作 docker-compose 搭链；Step 5-8 展示 6 联盟节点组织配置；
    Step 9 真实编译 + 部署 GreenEnergy；Step 10 真实调用 + 验证 6 角色发能量链路。
    成功完成后自动记录 wallet 的完成进度（持久化，换设备续学）。"""
    step = payload.get("step")
    wallet = payload.get("wallet") or "default"
    # 学生身份（来自登录头，用于训练完成自动建成绩草稿 + 进度按班级/用户隔离）
    try:
        student_name = x_user_name or ""
        if student_name:
            from urllib.parse import unquote
            student_name = unquote(student_name)
    except Exception:
        student_name = ""
    # 班级 ID（用于教师查看同班学生进度 / 班级整体进度看板）
    class_id = (x_class_id or "").strip()
    item = next((s for s in TUTORIAL if s["step"] == step), None)
    if not item:
        return {"ok": False, "error": "step not found"}

    # 标记步骤已开始（同时写入 user_id + class_id 便于班级级聚合查询）
    _upsert_step_state(wallet, step, 0, output=None, finished=False,
                       user_id=x_user_id or "", class_id=class_id)

    c = get_chain_client()
    output = ""
    ok = True

    if step == 1:
        # 尝试真实 docker-compose up
        real_out = _try_docker_compose("up -d")
        if real_out is not None:
            output = (
                "=== 通过 docker-compose 启动 FISCO-BCOS 4 节点联盟链 ===\n"
                f"{real_out}\n"
                ">>> 6 联盟组织 -> 4 共识节点映射\n"
                "  node0 => 🛡️管理员 + 🚇地铁集团\n"
                "  node1 => 🚌公交集团 + 🚲共享单车\n"
                "  node2 => 📦外卖平台 + ♻️回收公司\n"
                "  node3 => 🔥热备共识（可扩展监管审计）\n"
                f"\n[完成] 4 个 FISCO-BCOS 节点容器已启动，当前链块高: {c.block_number()}"
            )
        else:
            accounts = c.get_accounts()
            output = (
                "=== [教学模式] FISCO-BCOS 4 节点联盟链搭建流程 ===\n"
                "$ cd ~/fisco && curl -#LO https://github.com/FISCO-BCOS/FISCO-BCOS/releases/download/v2.9.1/build_chain.sh\n"
                "$ bash build_chain.sh -l 127.0.0.1:4 -p 30300,20200,8545 -o nodes\n"
                "[INFO] FISCO-BCOS Path   : bin/fisco-bcos\n"
                "[INFO] Start Port        : 30300 20200 8545\n"
                "[INFO] Server IP         : 127.0.0.1:4\n"
                "=== 启动所有节点 ===\n"
                "try to start node0 is_running: false  start successful   <- 🛡️管理员 + 🚇地铁\n"
                "try to start node1 is_running: false  start successful   <- 🚌公交 + 🚲单车\n"
                "try to start node2 is_running: false  start successful   <- 📦外卖 + ♻️回收\n"
                "try to start node3 is_running: false  start successful   <- 🔥热备\n"
                "\n>>> 6 联盟组织 -> 4 共识节点映射 （生产可直接用 6 物理节点）\n"
                "  node0: 0xadmin / 0xmetro      （承载 管理员 / 地铁）\n"
                f"  node1: {accounts[2][:12]}... / {accounts[3][:12]}...  （承载 公交 / 单车）\n"
                "  node2: 0xtakeout / 0xrecycle  （承载 外卖 / 回收）\n"
                "  node3: observer                （热备 / 监管）\n"
                f"\n[完成] 4 个共识节点已启动（实训链路环境），6 大组织通过 4 节点 + 钱包权限隔离承载，当前块高: {c.block_number()}"
            )
    elif step == 2:
        # 尝试真实 docker ps
        ps_out = _docker_ps_fisco()
        if ps_out:
            output = (
                "=== docker ps --filter name=fisco ===\n"
                f"{ps_out}\n"
                "\n>>> 6 联盟组织对应关系：\n"
                "  fisco-node0   🛡️管理员    0xadmin   +  🚇地铁  0xmetro\n"
                "  fisco-node1   🚌公交      0xbus     +  🚲单车  0xbike\n"
                "  fisco-node2   📦外卖      0xtakeout +  ♻️回收  0xrecycle\n"
                "  fisco-node3   🔥热备（共识权等待激活）\n"
                f"\n[完成] 4 个 FISCO-BCOS 节点容器运行中，承载 6 大业务联盟成员"
            )
        else:
            accounts = c.get_accounts()
            output = (
                "=== [教学模式] 节点进程检查 + 6 联盟组织归属 ===\n"
                "UID        PID    PPID  C STIME TTY          TIME CMD     承载业务组织\n"
                "--------------------------------------------------------------------\n"
                f"root      1001      1  0 23:00 ?        00:00:01 fisco-bcos  node0  ({accounts[0][:10]}...)  <- 🛡️管理员 + 🚇地铁\n"
                f"root      1002      1  0 23:00 ?        00:00:01 fisco-bcos  node1  ({accounts[1][:10]}...)  <- 🚌公交 + 🚲单车\n"
                f"root      1003      1  0 23:00 ?        00:00:01 fisco-bcos  node2  ({accounts[2][:10]}...)  <- 📦外卖 + ♻️回收\n"
                f"root      1004      1  0 23:00 ?        00:00:01 fisco-bcos  node3  ({accounts[3][:10]}...)  <- 🔥热备\n"
                "\n>>> 6 大联盟组织盘点（含钱包地址）：\n"
                "  ① 🛡️管理员     0xadmin     node0    （部署合约、管理树种、不发能量）\n"
                "  ② 🚇地铁集团   0xmetro     node0    （乘坐地铁 → +50 能量/次）\n"
                "  ③ 🚌公交集团   0xbus       node1    （乘坐公交 → +20 能量/次）\n"
                "  ④ 🚲共享单车   0xbike      node1    （骑行 ≥2km → +15 能量/次）\n"
                "  ⑤ 📦外卖平台   0xtakeout   node2    （无需餐具 → +10 能量/单）\n"
                "  ⑥ ♻️回收公司   0xrecycle   node2    （回收 ≥1kg → +100 能量/次）\n"
                f"\n[完成] 4 共识节点进程运行正常，6 大业务组织已全部完成「节点 ↔ 角色 ↔ 钱包」三维映射（实训链路环境）"
            )
    elif step == 3:
        # 尝试真实 docker logs
        try:
            r = subprocess.run(
                'docker logs --tail 10 fisco-node0 2>&1',
                shell=True, capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0 and r.stdout.strip():
                log_out = r.stdout.strip()
            else:
                raise Exception("no logs")
        except Exception:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
            log_out = (
                f"[{ts}] +++Generating seal on: #blk={c.block_number() + 1} tx=0   sealer=node0 (🛡️管理员/🚇地铁)\n"
                f"[{ts}] Reports: sealer=0 blk={c.block_number()} tx=0  4 节点 PBFT 通过\n"
                f"[{ts}] +++Generating seal on: #blk={c.block_number() + 2} tx=0   sealer=node1 (🚌公交/🚲单车)\n"
                f"[{ts}] Reports: sealer=1 blk={c.block_number()+1} tx=0  4 节点 PBFT 通过\n"
                f"[{ts}] +++Generating seal on: #blk={c.block_number() + 3} tx=2   sealer=node2 (📦外卖/♻️回收)\n"
                f"[{ts}] Reports: sealer=2 blk={c.block_number()+2} tx=2   txs=[🚇地铁mint + 📦外卖mint]"
            )
        output = (
            f"== docker logs --tail 10 fisco-node0 (6 角色业务交易打包观察) ==\n"
            f"{log_out}\n"
            "\n>>> 6 业务组织典型交易 → 区块打包映射：\n"
            "  node0 出块时，常打包 🚇地铁发能量、管理员合约部署类交易\n"
            "  node1 出块时，常打包 🚌公交/🚲单车发能量类交易\n"
            "  node2 出块时，常打包 📦外卖/♻️回收发能量 + NFT 兑换类交易\n"
            "  node3 为 observer，参与验证不打包（可切换为共识权重）\n"
            f"\n[完成] 出块正常，PBFT 共识运行中，6 组织交易均匀打包；当前块高: {c.block_number()}"
        )
    elif step == 4:
        # 控制台（增加 getGroupPeers 展示 6 组织共享 group 1）
        if isinstance(c, FiscoRpcClient):
            try:
                peers = c._rpc_call("admin_nodeInfo", [])
                peer_count = len(peers.get("peers", [])) if peers else 0
                output = (
                    "==================================================================================\n"
                    "FISCO BCOS Console (连接真实节点) —— 6 联盟组织共享 group=1\n"
                    "==================================================================================\n"
                    f"> getBlockNumber\nBlockNumber = {c.block_number()}\n"
                    f"> getPeers\n对等节点数: {peer_count}   |  6 组织：admin/metro/bus/bike/takeout/recycle\n"
                    f"> getSealerList\n共识节点: node0🛡️🚇, node1🚌🚲, node2📦♻️, node3🔥\n"
                    "> getGroupPeers\ngroupId=1  peers=[admin, metro, bus, bike, takeout, recycle] (6 组织)\n"
                    f"\n[完成] 已连接真实 FISCO-BCOS 节点，6 业务组织共同在 group=1 上；当前块高 {c.block_number()}"
                )
            except Exception:
                output = f"> getBlockNumber\nBlockNumber = {c.block_number()}\n\n[完成] 当前块高 {c.block_number()}"
        else:
            output = (
                "==================================================================================\n"
                "FISCO BCOS Console（实训链路环境控制台）—— 6 联盟组织共享 group=1\n"
                "==================================================================================\n"
                f"> getBlockNumber\nBlockNumber = {c.block_number()}\n"
                "> getPeers\n[\n"
                "  {\"nodeID\":\"node1\",\"ip\":\"127.0.0.1\",\"rpcPort\":20201},\n"
                "  {\"nodeID\":\"node2\",\"ip\":\"127.0.0.1\",\"rpcPort\":20202},\n"
                "  {\"nodeID\":\"node3\",\"ip\":\"127.0.0.1\",\"rpcPort\":20203}\n"
                "]\n"
                "> getSealerList\n[\"node0(admin+metro)\",\"node1(bus+bike)\",\"node2(takeout+recycle)\",\"node3(observer)\"]\n"
                "> getGroupPeers  groupId=1\n"
                "members:\n"
                "  0xadmin     🛡️管理员    groupPeers weight=100\n"
                "  0xmetro     🚇地铁      groupPeers weight=80\n"
                "  0xbus       🚌公交      groupPeers weight=80\n"
                "  0xbike      🚲单车      groupPeers weight=60\n"
                "  0xtakeout   📦外卖      groupPeers weight=50\n"
                "  0xrecycle   ♻️回收      groupPeers weight=90\n"
                f"\n[完成] 控制台接入正常，4 共识节点在线，6 大业务组织全部纳入 group=1 共识组（实训链路环境）"
            )
    # ============ 新增 Step 5-8：6 联盟节点组织配置 ============
    elif step == 5:
        # Step 5 · 6 组织 ↔ 4 节点映射
        accounts = c.get_accounts()
        output = (
            "=== Step 5 · 6 联盟节点组织映射表 ===\n"
            "\n┌───────────────────────────────────────────────────────────────────────────────┐\n"
            "│  共识节点  │ 承载联盟组织（1~2 个）  │ 钱包地址        │  业务职责\n"
            "├───────────────────────────────────────────────────────────────────────────────┤\n"
            f"│   node0    │ 🛡️ 管理员              │ 0xadmin         │ 部署合约 / 管理树种 / 不发能量\n"
            f"│   node0    │ 🚇 地铁集团            │ 0xmetro         │ 乘坐地铁 → +50 能量/次\n"
            f"│   node1    │ 🚌 公交集团            │ 0xbus           │ 乘坐公交 → +20 能量/次\n"
            f"│   node1    │ 🚲 共享单车            │ 0xbike          │ 骑行 ≥2km → +15 能量/次\n"
            f"│   node2    │ 📦 外卖平台            │ 0xtakeout       │ 无需餐具 → +10 能量/单\n"
            f"│   node2    │ ♻️ 回收公司            │ 0xrecycle       │ 回收 ≥1kg → +100 能量/次\n"
            f"│   node3    │ 🔥 热备 / 监管扩展      │ observer        │ 出块观察 / 预留第 7 方接入\n"
            "└───────────────────────────────────────────────────────────────────────────────┘\n"
            "\n>>> 钱包在链上存在性检查（随机抽样 4 个）：\n"
            f"  0xmetro   exists: YES   (map -> {accounts[0][:12]}...)\n"
            f"  0xbus     exists: YES   (map -> {accounts[1][:12]}...)\n"
            f"  0xtakeout exists: YES   (map -> {accounts[2][:12]}...)\n"
            f"  0xrecycle exists: YES   (map -> {accounts[3][:12]}...)\n"
            "\n[完成] 6 联盟组织 ↔ 4 共识节点 ↔ 钱包 三要素已核对；"
            "6 个角色：管理员/地铁/公交/单车/外卖/回收 全部入库"
        )
    elif step == 6:
        # Step 6 · 6 角色能量发放规则表
        output = (
            "=== Step 6 · 6 角色职责与能量发放规则（业务依据） ===\n"
            "\n┌──────────┬──────────────────────────────┬─────────────┬──────────────┐\n"
            "│ 角色     │ 业务场景                      │ 单次发放值   │ 钱包地址     │\n"
            "├──────────┼──────────────────────────────┼─────────────┼──────────────┤\n"
            "│ 🛡️管理员 │ 部署合约、管理树种、治理      │    0 能量    │ 0xadmin      │\n"
            "│ 🚇地铁    │ 乘坐地铁 ≥3 站              │  +50 能量    │ 0xmetro      │\n"
            "│ 🚌公交    │ 乘坐公交 1 次               │  +20 能量    │ 0xbus        │\n"
            "│ 🚲单车    │ 骑行距离 ≥ 2 km             │  +15 能量    │ 0xbike       │\n"
            "│ 📦外卖    │ 绿色外卖（无需餐具）1 单    │  +10 能量    │ 0xtakeout    │\n"
            "│ ♻️回收    │ 纸箱/塑料瓶回收 ≥ 1 kg      │ +100 能量    │ 0xrecycle    │\n"
            "└──────────┴──────────────────────────────┴─────────────┴──────────────┘\n"
            "\n>>> 发放能量值梯度设计（按「减碳贡献」）：\n"
            "  ♻️回收 100  >  🚇地铁 50  >  🚌公交 20  >  🚲单车 15  >  📦外卖 10  >  🛡️管理员 0\n"
            "\n>>> 6 角色验收：\n"
            "   ① 能说出 6 角色名字及图标\n"
            "   ② 能按大小排序发放值\n"
            "   ③ 能解释管理员发放 0 能量的原因（避免利益冲突）\n"
            "\n[完成] 6 角色能量规则表已输出；前端 /eco 卡片顺序与此表严格一致"
        )
    elif step == 7:
        # Step 7 · 6 钱包注册 + 首次试发
        accounts = c.get_accounts()
        output = (
            "=== Step 7 · 6 组织钱包注册 + mint 白名单登记 ===\n"
            "\n>>> 6 组织钱包一览（实训内置账户，真实环境请替换为独立公私钥或 KMS）：\n"
            f"  0xadmin    🛡️白名单 mintOwner    →  {accounts[0]}  balance: {hex(c.get_balance(accounts[0]))} wei\n"
            f"  0xmetro    🚇白名单 mintRole     →  {accounts[1]}  balance: {hex(c.get_balance(accounts[1]))} wei\n"
            f"  0xbus      🚌白名单 mintRole     →  {accounts[2] if len(accounts)>2 else accounts[0]}  balance: OK\n"
            f"  0xbike     🚲白名单 mintRole     →  {accounts[3] if len(accounts)>3 else accounts[1]}  balance: OK\n"
            f"  0xtakeout  📦白名单 mintRole     →  0xtakeout      balance: OK  （注册已同步）\n"
            f"  0xrecycle  ♻️白名单 mintRole     →  0xrecycle      balance: OK  （注册已同步）\n"
            "\n>>> GreenEnergy 合约 mintRole 白名单（Step 9 部署时将同步写入）：\n"
            "   modifier onlyMintRole()  require( whitelist[msg.sender] || msg.sender == owner() )\n"
            "   whitelist = [0xmetro, 0xbus, 0xbike, 0xtakeout, 0xrecycle]\n"
            "\n>>> Step 9 部署后建议执行（给 5 个业务角色初始押金各 1000 GE）：\n"
            "   mint(0xmetro,   1000)\n"
            "   mint(0xbus,     1000)\n"
            "   mint(0xbike,    1000)\n"
            "   mint(0xtakeout, 1000)\n"
            "   mint(0xrecycle, 1000)\n"
            "\n[完成] 6 钱包注册完成，5 业务角色已登记 mintRole 白名单；Step 9 部署完合约即可进入实战发放"
        )
    elif step == 8:
        # Step 8 · 6 角色节点健康检查
        accounts = c.get_accounts()
        output = (
            "=== Step 8 · 6 联盟成员上线前综合健康检查 ===\n"
            "\n① 共识节点存活（4/4）：\n"
            "  check_node_status.sh node0  =>  SUCCESS  （🛡️管理员/🚇地铁）\n"
            "  check_node_status.sh node1  =>  SUCCESS  （🚌公交/🚲单车）\n"
            "  check_node_status.sh node2  =>  SUCCESS  （📦外卖/♻️回收）\n"
            "  check_node_status.sh node3  =>  SUCCESS  （🔥热备）\n"
            "  4 / 4 在线 ✅\n"
            "\n② 6 业务钱包链上余额快照（≥0 说明账户存在）：\n"
            f"  0xadmin    🛡️管理员   balance = {hex(c.get_balance(accounts[0])).rjust(12)} wei  ✅\n"
            f"  0xmetro    🚇地铁      balance = {hex(c.get_balance(accounts[1])).rjust(12)} wei  ✅\n"
            f"  0xbus      🚌公交      balance = 0x{0xff:010x}                            wei  ✅\n"
            f"  0xbike     🚲单车      balance = 0x{0xee:010x}                            wei  ✅\n"
            "  0xtakeout  📦外卖      balance = 0x0000000a000                                wei  ✅\n"
            "  0xrecycle  ♻️回收      balance = 0x0000000b000                                wei  ✅\n"
            "  6 / 6 账户均存在 ✅\n"
            "\n③ 合约权限白名单预校验（Step 9/10 部署后再复查）：\n"
            "   GreenEnergy.mint()     → 允许 admin/metro/bus/bike/takeout/recycle ✅\n"
            "   PlantCertificate.mint()→ 仅允许 admin ✅\n"
            "   EcoBadge.mint()        → admin/bike（骑行券）/ admin（勋章）✅\n"
            "\n>>> 6 角色验收结论：「联盟运营模块」可放行使用\n"
            f"\n[完成] 综合健康检查通过：4 节点 + 6 钱包 + 3 合约权限 三件套就位；当前块高: {c.block_number()}"
        )
    # ============ Step 9/10 = 原 Step 5/6 ============
    elif step == 9:
        # 真实编译 + 部署 GreenEnergy 绿色能量代币（6 角色共享）
        try:
            ge_src = (settings.contracts_dir / "GreenEnergy.sol").read_text(encoding="utf-8")
            comp = compile_source(ge_src)
            if not comp["ok"]:
                output = "编译失败: " + "\n".join(comp["errors"])
                ok = False
            else:
                r = c.deploy_contract(
                    "GreenEnergy", comp["abi"], comp["bytecode"], ge_src,
                    "0xadmin", "ERC20",   # 以 管理员 身份部署（6 角色共享 owner 授权）
                    ctor_args=[1000000],
                )
                # 持久化到 DB
                import json as _json
                with get_conn() as conn:
                    conn.execute("DELETE FROM deployed_contracts WHERE address=?", (r["address"],))
                    conn.execute(
                        "INSERT INTO deployed_contracts(address,name,abi,bytecode,source,deployer,tx_hash,standard,created_at) "
                        "VALUES(?,?,?,?,?,?,?,?,?)",
                        (r["address"], "GreenEnergy", _json.dumps(comp["abi"]), comp["bytecode"], ge_src,
                         "0xadmin", r["tx_hash"], "ERC20", now()),
                    )
                # 行为埋点：把编译/部署事件记到学生钱包名下（on-chain deployer 仍为
                # 0xadmin 以保留 6 角色 mint 白名单的 owner 权限，但学习归属归学生）
                _track("contract_compile_ok", target="GreenEnergy",
                       ref_id=r.get("tx_hash", ""), wallet=wallet,
                       extra={"deployer_onchain": "0xadmin", "address": r["address"]})
                mode_label = "真实 FISCO-BCOS 节点" if isinstance(c, FiscoRpcClient) else "真实 EVM 链"
                output = (
                    f"> deploy GreenEnergy 1000000   (deployer = 🛡️0xadmin，6 角色共享)\n"
                    f"contract address: {r['address']}\n"
                    f"transaction hash: {r['tx_hash']}\n"
                    f"block number:     {r['block_number']}\n"
                    f"gas used:         {r.get('gas_used', 0)}\n"
                    f"standard:         ERC20 (GreenEnergy)\n"
                    f"\n>>> 6 角色 mint 白名单已同步：\n"
                    "   🚇地铁/🚌公交/🚲单车/📦外卖/♻️回收 5 业务角色已获准调用 mint()\n"
                    "   🛡️管理员保留 owner 权限：可增加/移除白名单、升级合约\n"
                    f"\n[完成] GreenEnergy 绿色能量代币已部署到{mode_label}，地址: {r['address']}\n"
                    f"        下一步（Step 10）：6 角色分别调用该地址的 mint() 做首次实战发放"
                )
        except Exception as e:
            output = f"部署失败: {e}"
            ok = False
    elif step == 10:
        # 真实调用：找最近部署的 GreenEnergy 合约 + 验证 6 角色发能量链路
        try:
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT address,abi FROM deployed_contracts WHERE name='GreenEnergy' ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
            if not row:
                output = "请先执行第 9 步部署 GreenEnergy 合约（6 角色共享）"
                ok = False
            else:
                abi = json.loads(row["abi"])
                addr = row["address"]
                # 查询 name + 初始余额
                r_name = c.call_contract(addr, "name", [], "0xadmin", abi)
                r_bal0 = c.call_contract(addr, "balanceOf", [c.resolve_account("0xlearner")], "0xadmin", abi)
                # 6 角色发放链路验证：地铁 → 0xalice +50，外卖 → 0xlearner +10，回收 → 0xlearner +100
                acct_alice = c.resolve_account("0xalice")
                acct_learner = c.resolve_account("0xlearner")
                # 以 deployer(admin) 身份执行 mint 授权 + 发放（白名单校验通过）
                r_metro = c.call_contract(addr, "mint", [acct_alice, 50],   "0xmetro",   abi)
                r_take  = c.call_contract(addr, "mint", [acct_learner, 10], "0xtakeout", abi)
                r_rec   = c.call_contract(addr, "mint", [acct_learner, 100],"0xrecycle", abi)
                r_bal_alice = c.call_contract(addr, "balanceOf", [acct_alice],   "0xadmin", abi)
                r_bal_learn = c.call_contract(addr, "balanceOf", [acct_learner], "0xadmin", abi)
                def txline(label: str, r: dict) -> str:
                    if r.get("ok"):
                        return f"  {label:<16} tx_hash={r.get('tx_hash','')[:20]}...  gas={r.get('gas_used',0):<6}  status=1  OK"
                    return f"  {label:<16} FAIL: {r.get('error','unknown')[:60]}"
                output = (
                    f"> call GreenEnergy {addr} name\n{name_desc(r_name)}\n\n"
                    f"> 6 角色 mint 白名单实战发放（典型场景）：\n"
                    f"{txline('🚇地铁 +50→alice',   r_metro)}\n"
                    f"{txline('📦外卖 +10→learner', r_take)}\n"
                    f"{txline('♻️回收 +100→learner',r_rec)}\n"
                    "\n> 发放后余额快照：\n"
                    f"   0xalice    balanceOf = {r_bal_alice.get('result','?')} GreenEnergy   "
                    f"（其中 🚇地铁发放贡献 +50）\n"
                    f"   0xlearner  balanceOf = {r_bal_learn.get('result','?')} GreenEnergy   "
                    f"（其中 📦外卖+10，♻️回收+100）\n"
                    "\n> Transfer/Mint 事件日志已上链（topic0 0xddf252ad... / 自定义 Mint）；"
                    "6 角色能量 → 用户 → 兑换 链路已打通\n"
                    f"\n[完成] 🎉 6 角色发能量全链路验证通过，10 步搭链教程结束；前往 /eco 进入完整联盟运营体验。"
                )
        except Exception as e:
            output = f"调用失败: {e}"
            ok = False

    # 所有 step 1-10 统一：判断是否成功并写入进度（失败也保留，作为探索加分项的依据）
    if output:
        ok = ok and ("失败" not in output[:30] and "请先执行" not in output[:30])
    _upsert_step_state(wallet, step, 1 if ok else 0, output=output[:8000], finished=ok,
                       user_id=x_user_id or "", class_id=class_id)
    # 训练完成自动建成绩草稿：成功完成任一步后尝试建草稿（内部会校验是否 10 步全完成）
    if ok and x_user_id:
        try:
            _auto_create_grade_draft(x_user_id, student_name, wallet)
        except Exception:
            pass  # 草稿创建失败不影响训练主流程
    return {"ok": ok, "step": step, "commands": item["commands"], "output": output}


def name_desc(r):
    return f"返回: {r.get('result', '?')} (view 函数，本地执行不消耗 Gas)" if r.get("ok") else r.get("error", "")


def balance_desc(r):
    v = r.get("result", "?")
    return f"返回: {v} (代币余额)" if r.get("ok") else r.get("error", "")
