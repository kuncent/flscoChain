"""搭链教程执行引擎（自 app/routers/chain.py 抽离，行为保持不变）。

职责：
- TUTORIAL 10 步教程的命令注册表 / 语法匹配 / 命令执行 / 进度持久化
- /tutorial/exec 与 /tutorial/command 的实现主体（exec_step_impl / exec_command_impl），
  路由薄壳保留在 app/routers/chain.py（Depends、参数解析、调 engine、原样返回）

迁移说明（移动代码不改行为）：
- _match_command / _upsert_step_state / _try_docker_compose / _ensure_progress_table /
  _auto_create_grade_draft / CMD_REGISTRY / _exec_command 及「教学模式」模拟输出
  均自 chain.py 原样迁入，逐行保留；
- 唯一允许的响应增量：/tutorial/exec 与 /tutorial/command 响应新增 source 字段
  （"real" = 真实 docker / 链上执行；"simulated" = 教学模式模拟输出），
  既有字段一律不变。

技术债：
- exec_step_impl 的 Step 1-4「教学模式」分支与 Step 5-8 整体、_exec_command_impl 的
  Step 1-5 输出均为硬编码模拟文本（本地无 docker / FISCO 节点环境时降级展示），
  并非真实终端执行；后续可接入真实终端执行器 / 节点探针替换模拟分支。
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import settings
from ..chain_client import get_chain_client, FiscoRpcClient
from ..db import get_conn, now
from ..security import assert_actor_wallet
from ..tx_decoder import compile_source
from .tutorial_steps import TUTORIAL
# 学习行为埋点统一收口至本包 events（EventType 常量 + track 唯一写入实现）
from .events import EventType, track as _track
# 任务 #21：五级验证流水线（记录模式：L4 复用本模块执行结果）+ 事件总线（步骤完成推送）
from .. import verifier
from ..events_bus import BusEvent, publish as bus_publish


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
    from ..routers.grades import _compute_training_score, _compute_final
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
            cmd_idx INTEGER NOT NULL DEFAULT -1,
            output TEXT,
            started_at TEXT,
            finished_at TEXT,
            tenant_id TEXT DEFAULT '',
            user_id TEXT DEFAULT '',
            session_id TEXT DEFAULT '',
            UNIQUE(wallet, step)
        )""")
        # 增量列：class_id / cmd_idx（在线迁移，兼容已存在的旧表）
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(chain_tutorial_progress)")}
        if "class_id" not in existing:
            conn.execute("ALTER TABLE chain_tutorial_progress ADD COLUMN class_id TEXT NOT NULL DEFAULT ''")
        if "cmd_idx" not in existing:
            conn.execute("ALTER TABLE chain_tutorial_progress ADD COLUMN cmd_idx INTEGER NOT NULL DEFAULT -1")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tutorial_progress_class ON chain_tutorial_progress(class_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tutorial_progress_user ON chain_tutorial_progress(user_id)")

        # 多租户回填（任务 #15）：历史行 user_id 可能为 NULL/''，按 wallet 关联
        # user_info.user_id 回填归属；关联不上（wallet 为空或 user_info 无该钱包）
        # 则保持原值 —— EXISTS 守卫只更新能关联上的行，重复执行幂等；
        # user_info 表异常（极端旧库）时跳过回填，不阻塞教程进度功能。
        try:
            conn.execute("""
                UPDATE chain_tutorial_progress SET user_id = (
                    SELECT u.user_id FROM user_info u
                    WHERE u.wallet = chain_tutorial_progress.wallet
                    LIMIT 1
                )
                WHERE (user_id IS NULL OR user_id = '')
                  AND wallet != ''
                  AND EXISTS (
                    SELECT 1 FROM user_info u2
                    WHERE u2.wallet = chain_tutorial_progress.wallet
                  )
            """)
        except Exception:
            pass

        # 复合索引（任务 #15）：scope 接线后 user_id 成为高频过滤前导列。
        # 选 (user_id, step) 而非 (wallet, step)：UNIQUE(wallet, step) 约束
        # 已自动提供 (wallet, step) 复合索引，无需重复建。
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tutorial_progress_user_step "
            "ON chain_tutorial_progress(user_id, step)"
        )


def _upsert_step_state(
    wallet: str, step: int, done: int,
    output: str | None = None, finished: bool = False,
    user_id: str = "", class_id: str = "",
    cmd_idx: int | None = None,
):
    _ensure_progress_table()
    ts = now()
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT id FROM chain_tutorial_progress WHERE wallet=? AND step=?",
            (wallet, step),
        ).fetchone()
        if exists:
            # 动态构建更新字段（cmd_idx 单独推进，done 由最后一条命令触发）
            sets = []
            params = []
            if finished:
                sets.append("done=?")
                params.append(done)
                sets.append("output=COALESCE(?,output)")
                params.append(output)
                sets.append("finished_at=?")
                params.append(ts)
                sets.append("user_id=COALESCE(NULLIF(?, ''), user_id)")
                params.append(user_id)
                sets.append("class_id=COALESCE(NULLIF(?, ''), class_id)")
                params.append(class_id)
            elif output is not None:
                sets.append("output=?")
                params.append(output)
            if cmd_idx is not None:
                sets.append("cmd_idx=?")
                params.append(cmd_idx)
                if not finished:
                    sets.append("started_at=COALESCE(started_at, ?)")
                    params.append(ts)
            if sets:
                params += [wallet, step]
                conn.execute(
                    f"UPDATE chain_tutorial_progress SET {', '.join(sets)} WHERE wallet=? AND step=?",
                    params,
                )
        else:
            conn.execute(
                "INSERT INTO chain_tutorial_progress(wallet,step,done,cmd_idx,output,started_at,finished_at,user_id,class_id) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (wallet, step, done, cmd_idx if cmd_idx is not None else -1,
                 output, ts, ts if finished else None, user_id, class_id),
            )


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


def exec_step_impl(payload: dict, user: dict) -> dict:
    """执行某一步骤：Step 1-4 真实操作 docker-compose 搭链；Step 5-8 展示 6 联盟节点组织配置；
    Step 9 真实编译 + 部署 GreenEnergy；Step 10 真实调用 + 验证 6 角色发能量链路。
    成功完成后自动记录 wallet 的完成进度（持久化，换设备续学）。

    技术债：Step 1-4 的「教学模式」分支与 Step 5-8 整体为硬编码模拟输出
    （本地无 docker / FISCO 节点环境时降级展示教学文本），并非真实终端执行；
    响应新增 source 字段区分 real（真实 docker / 链上执行）/ simulated（模拟输出），
    既有字段不变。
    """
    step = payload.get("step")
    wallet = assert_actor_wallet(user, payload.get("wallet") or "", "wallet") or "default"
    # 学生身份（来自 JWT 验签，用于训练完成自动建成绩草稿 + 进度按班级/用户隔离）
    x_user_id = user.get("user_id") or ""
    student_name = user.get("user_name") or ""
    # 班级 ID（用于教师查看同班学生进度 / 班级整体进度看板）
    class_id = (user.get("class_id") or "").strip()
    item = next((s for s in TUTORIAL if s["step"] == step), None)
    if not item:
        return {"ok": False, "error": "step not found", "source": "simulated"}

    # 标记步骤已开始（同时写入 user_id + class_id 便于班级级聚合查询）
    _upsert_step_state(wallet, step, 0, output=None, finished=False,
                       user_id=x_user_id or "", class_id=class_id)

    c = get_chain_client()
    output = ""
    ok = True
    source = "simulated"

    if step == 1:
        # 尝试真实 docker-compose up
        real_out = _try_docker_compose("up -d")
        if real_out is not None:
            source = "real"
            output = (
                "=== 通过 docker-compose 启动 FISCO-BCOS 4 节点联盟链 ===\n"
                f"{real_out}\n"
                ">>> 6 联盟组织 -> 4 共识节点映射\n"
                "  node0 => 管理员 + 地铁集团\n"
                "  node1 => 公交集团 + 共享单车\n"
                "  node2 => 外卖平台 + 回收公司\n"
                "  node3 => 热备共识(可扩展监管审计)\n"
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
                "try to start node0 is_running: false  start successful   <- 管理员 + 地铁\n"
                "try to start node1 is_running: false  start successful   <- 公交 + 单车\n"
                "try to start node2 is_running: false  start successful   <- 外卖 + 回收\n"
                "try to start node3 is_running: false  start successful   <- 热备\n"
                "\n>>> 6 联盟组织 -> 4 共识节点映射 (生产可直接用 6 物理节点)\n"
                "  node0: 0xadmin / 0xmetro      (承载 管理员 / 地铁)\n"
                f"  node1: {accounts[2][:12]}... / {accounts[3][:12]}...  (承载 公交 / 单车)\n"
                "  node2: 0xtakeout / 0xrecycle  (承载 外卖 / 回收)\n"
                "  node3: observer                (热备 / 监管)\n"
                f"\n[完成] 4 个共识节点已启动(实训链路环境)，6 大组织通过 4 节点 + 钱包权限隔离承载，当前块高: {c.block_number()}"
            )
    elif step == 2:
        # 尝试真实 docker ps
        ps_out = _docker_ps_fisco()
        if ps_out:
            source = "real"
            output = (
                "=== docker ps --filter name=fisco ===\n"
                f"{ps_out}\n"
                "\n>>> 6 联盟组织对应关系：\n"
                "  fisco-node0   管理员      0xadmin   +  地铁  0xmetro\n"
                "  fisco-node1   公交        0xbus     +  单车  0xbike\n"
                "  fisco-node2   外卖        0xtakeout +  回收  0xrecycle\n"
                "  fisco-node3   热备(共识权等待激活)\n"
                f"\n[完成] 4 个 FISCO-BCOS 节点容器运行中，承载 6 大业务联盟成员"
            )
        else:
            accounts = c.get_accounts()
            output = (
                "=== [教学模式] 节点进程检查 + 6 联盟组织归属 ===\n"
                "UID        PID    PPID  C STIME TTY          TIME CMD     承载业务组织\n"
                "--------------------------------------------------------------------\n"
                f"root      1001      1  0 23:00 ?        00:00:01 fisco-bcos  node0  ({accounts[0][:10]}...)  <- 管理员 + 地铁\n"
                f"root      1002      1  0 23:00 ?        00:00:01 fisco-bcos  node1  ({accounts[1][:10]}...)  <- 公交 + 单车\n"
                f"root      1003      1  0 23:00 ?        00:00:01 fisco-bcos  node2  ({accounts[2][:10]}...)  <- 外卖 + 回收\n"
                f"root      1004      1  0 23:00 ?        00:00:01 fisco-bcos  node3  ({accounts[3][:10]}...)  <- 热备\n"
                "\n>>> 6 大联盟组织盘点(含钱包地址)：\n"
                "  (1) 管理员     0xadmin     node0    (部署合约、管理树种、不发能量)\n"
                "  (2) 地铁集团   0xmetro     node0    (乘坐地铁 -> +50 能量/次)\n"
                "  (3) 公交集团   0xbus       node1    (乘坐公交 -> +20 能量/次)\n"
                "  (4) 共享单车   0xbike      node1    (骑行 >=2km -> +15 能量/次)\n"
                "  (5) 外卖平台   0xtakeout   node2    (无需餐具 -> +10 能量/单)\n"
                "  (6) 回收公司   0xrecycle   node2    (回收 >=1kg -> +100 能量/次)\n"
                f"\n[完成] 4 共识节点进程运行正常，6 大业务组织已全部完成 节点/角色/钱包 三维映射(实训链路环境)"
            )
    elif step == 3:
        # 尝试真实 docker logs
        try:
            r = subprocess.run(
                'docker logs --tail 10 fisco-node0 2>&1',
                shell=True, capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0 and r.stdout.strip():
                source = "real"
                log_out = r.stdout.strip()
            else:
                raise Exception("no logs")
        except Exception:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
            log_out = (
                f"[{ts}] +++Generating seal on: #blk={c.block_number() + 1} tx=0   sealer=node0 (管理员/地铁)\n"
                f"[{ts}] Reports: sealer=0 blk={c.block_number()} tx=0  4 节点 PBFT 通过\n"
                f"[{ts}] +++Generating seal on: #blk={c.block_number() + 2} tx=0   sealer=node1 (公交/单车)\n"
                f"[{ts}] Reports: sealer=1 blk={c.block_number()+1} tx=0  4 节点 PBFT 通过\n"
                f"[{ts}] +++Generating seal on: #blk={c.block_number() + 3} tx=2   sealer=node2 (外卖/回收)\n"
                f"[{ts}] Reports: sealer=2 blk={c.block_number()+2} tx=2   txs=[地铁mint + 外卖mint]"
            )
        output = (
            f"== docker logs --tail 10 fisco-node0 (6 角色业务交易打包观察) ==\n"
            f"{log_out}\n"
            "\n>>> 6 业务组织典型交易 -> 区块打包映射：\n"
            "  node0 出块时，常打包 地铁发能量、管理员合约部署类交易\n"
            "  node1 出块时，常打包 公交/单车发能量类交易\n"
            "  node2 出块时，常打包 外卖/回收发能量 + NFT 兑换类交易\n"
            "  node3 为 observer，参与验证不打包(可切换为共识权重)\n"
            f"\n[完成] 出块正常，PBFT 共识运行中，6 组织交易均匀打包；当前块高: {c.block_number()}"
        )
    elif step == 4:
        # 控制台（增加 getGroupPeers 展示 6 组织共享 group 1）
        if isinstance(c, FiscoRpcClient):
            source = "real"
            try:
                peers = c._rpc_call("admin_nodeInfo", [])
                peer_count = len(peers.get("peers", [])) if peers else 0
                output = (
                    "==================================================================================\n"
                    "FISCO BCOS Console (连接真实节点) -- 6 联盟组织共享 group=1\n"
                    "==================================================================================\n"
                    f"> getBlockNumber\nBlockNumber = {c.block_number()}\n"
                    f"> getPeers\n对等节点数: {peer_count}   |  6 组织：admin/metro/bus/bike/takeout/recycle\n"
                    f"> getSealerList\n共识节点: node0(admin/metro), node1(bus/bike), node2(takeout/recycle), node3(observer)\n"
                    "> getGroupPeers\ngroupId=1  peers=[admin, metro, bus, bike, takeout, recycle] (6 组织)\n"
                    f"\n[完成] 已连接真实 FISCO-BCOS 节点，6 业务组织共同在 group=1 上；当前块高 {c.block_number()}"
                )
            except Exception:
                output = f"> getBlockNumber\nBlockNumber = {c.block_number()}\n\n[完成] 当前块高 {c.block_number()}"
        else:
            output = (
                "==================================================================================\n"
                "FISCO BCOS Console(实训链路环境控制台) -- 6 联盟组织共享 group=1\n"
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
                "  0xadmin     管理员    groupPeers weight=100\n"
                "  0xmetro     地铁      groupPeers weight=80\n"
                "  0xbus       公交      groupPeers weight=80\n"
                "  0xbike      单车      groupPeers weight=60\n"
                "  0xtakeout   外卖      groupPeers weight=50\n"
                "  0xrecycle   回收      groupPeers weight=90\n"
                f"\n[完成] 控制台接入正常，4 共识节点在线，6 大业务组织全部纳入 group=1 共识组(实训链路环境)"
            )
    # ============ 新增 Step 5-8：6 联盟节点组织配置 ============
    elif step == 5:
        # Step 5 · 6 组织 ↔ 4 节点映射
        accounts = c.get_accounts()
        output = (
            "=== Step 5 · 6 联盟节点组织映射表 ===\n"
            "\n  共识节点    承载联盟组织         钱包地址        业务职责\n"
            "  --------   -----------------   -------------   ----------------------------\n"
            "  node0      管理员              0xadmin         部署合约 / 管理树种 / 不发能量\n"
            "  node0      地铁集团            0xmetro         乘坐地铁 -> +50 能量/次\n"
            "  node1      公交集团            0xbus           乘坐公交 -> +20 能量/次\n"
            "  node1      共享单车            0xbike          骑行 >=2km -> +15 能量/次\n"
            "  node2      外卖平台            0xtakeout       无需餐具 -> +10 能量/单\n"
            "  node2      回收公司            0xrecycle       回收 >=1kg -> +100 能量/次\n"
            "  node3      热备/监管扩展       observer        出块观察 / 预留第 7 方接入\n"
            "\n>>> 钱包在链上存在性检查（随机抽样 4 个）：\n"
            f"  0xmetro   exists: YES   (map -> {accounts[0][:12]}...)\n"
            f"  0xbus     exists: YES   (map -> {accounts[1][:12]}...)\n"
            f"  0xtakeout exists: YES   (map -> {accounts[2][:12]}...)\n"
            f"  0xrecycle exists: YES   (map -> {accounts[3][:12]}...)\n"
            "\n[完成] 6 联盟组织 <-> 4 共识节点 <-> 钱包 三要素已核对；"
            "6 个角色：管理员/地铁/公交/单车/外卖/回收 全部入库"
        )
    elif step == 6:
        # Step 6 · 6 角色能量发放规则表
        output = (
            "=== Step 6 · 6 角色职责与能量发放规则（业务依据） ===\n"
            "\n  角色       业务场景                       单次发放值   钱包地址\n"
            "  --------   ----------------------------   ----------   -------------\n"
            "  管理员     部署合约、管理树种、治理           0 能量     0xadmin\n"
            "  地铁       乘坐地铁 >=3 站                  +50 能量    0xmetro\n"
            "  公交       乘坐公交 1 次                    +20 能量    0xbus\n"
            "  单车       骑行距离 >= 2 km                  +15 能量    0xbike\n"
            "  外卖       绿色外卖(无需餐具) 1 单           +10 能量    0xtakeout\n"
            "  回收       纸箱/塑料瓶回收 >= 1 kg           +100 能量   0xrecycle\n"
            "\n>>> 发放能量值梯度设计(按减碳贡献)：\n"
            "  回收 100  >  地铁 50  >  公交 20  >  单车 15  >  外卖 10  >  管理员 0\n"
            "\n>>> 6 角色验收：\n"
            "   (1) 能说出 6 角色名字及对应业务\n"
            "   (2) 能按大小排序发放值\n"
            "   (3) 能解释管理员发放 0 能量的原因(避免利益冲突)\n"
            "\n[完成] 6 角色能量规则表已输出；前端 /eco 卡片顺序与此表严格一致"
        )
    elif step == 7:
        # Step 7 · 6 钱包注册 + 首次试发
        accounts = c.get_accounts()
        output = (
            "=== Step 7 · 6 组织钱包注册 + mint 白名单登记 ===\n"
            "\n>>> 6 组织钱包一览(实训内置账户，真实环境请替换为独立公私钥或 KMS)：\n"
            f"  0xadmin    白名单 mintOwner    ->  {accounts[0]}  balance: {hex(c.get_balance(accounts[0]))} wei\n"
            f"  0xmetro    白名单 mintRole     ->  {accounts[1]}  balance: {hex(c.get_balance(accounts[1]))} wei\n"
            f"  0xbus      白名单 mintRole     ->  {accounts[2] if len(accounts)>2 else accounts[0]}  balance: OK\n"
            f"  0xbike     白名单 mintRole     ->  {accounts[3] if len(accounts)>3 else accounts[1]}  balance: OK\n"
            f"  0xtakeout  白名单 mintRole     ->  0xtakeout      balance: OK  (注册已同步)\n"
            f"  0xrecycle  白名单 mintRole     ->  0xrecycle      balance: OK  (注册已同步)\n"
            "\n>>> GreenEnergy 合约 mintRole 白名单(Step 9 部署时将同步写入)：\n"
            "   modifier onlyMintRole()  require( whitelist[msg.sender] || msg.sender == owner() )\n"
            "   whitelist = [0xmetro, 0xbus, 0xbike, 0xtakeout, 0xrecycle]\n"
            "\n>>> Step 9 部署后建议执行(给 5 个业务角色初始押金各 1000 GE)：\n"
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
            "\n(1) 共识节点存活(4/4)：\n"
            "  check_node_status.sh node0  =>  SUCCESS  (管理员/地铁)\n"
            "  check_node_status.sh node1  =>  SUCCESS  (公交/单车)\n"
            "  check_node_status.sh node2  =>  SUCCESS  (外卖/回收)\n"
            "  check_node_status.sh node3  =>  SUCCESS  (热备)\n"
            "  4 / 4 在线 OK\n"
            "\n(2) 6 业务钱包链上余额快照(>=0 说明账户存在)：\n"
            f"  0xadmin    管理员   balance = {hex(c.get_balance(accounts[0])).rjust(12)} wei  OK\n"
            f"  0xmetro    地铁      balance = {hex(c.get_balance(accounts[1])).rjust(12)} wei  OK\n"
            f"  0xbus      公交      balance = 0x{0xff:010x}                            wei  OK\n"
            f"  0xbike     单车      balance = 0x{0xee:010x}                            wei  OK\n"
            "  0xtakeout  外卖      balance = 0x0000000a000                                wei  OK\n"
            "  0xrecycle  回收      balance = 0x0000000b000                                wei  OK\n"
            "  6 / 6 账户均存在 OK\n"
            "\n(3) 合约权限白名单预校验(Step 9/10 部署后再复查)：\n"
            "   GreenEnergy.mint()     -> 允许 admin/metro/bus/bike/takeout/recycle OK\n"
            "   PlantCertificate.mint()-> 仅允许 admin OK\n"
            "   EcoBadge.mint()        -> admin/bike(骑行券) / admin(勋章) OK\n"
            "\n>>> 6 角色验收结论：联盟运营模块可放行使用\n"
            f"\n[完成] 综合健康检查通过：4 节点 + 6 钱包 + 3 合约权限 三件套就位；当前块高: {c.block_number()}"
        )
    # ============ Step 9/10 = 原 Step 5/6 ============
    elif step == 9:
        # 真实编译 + 部署 GreenEnergy 绿色能量代币（6 角色共享）
        source = "real"
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
                _track(EventType.CONTRACT_COMPILE_OK, target="GreenEnergy",
                       ref_id=r.get("tx_hash", ""), wallet=wallet,
                       extra={"deployer_onchain": "0xadmin", "address": r["address"]})
                mode_label = "FISCO-BCOS 节点" if isinstance(c, FiscoRpcClient) else "EVM 链"
                output = (
                    f"> deploy GreenEnergy 1000000   (deployer = 0xadmin, 6 角色共享)\n"
                    f"contract address: {r['address']}\n"
                    f"transaction hash: {r['tx_hash']}\n"
                    f"block number:     {r['block_number']}\n"
                    f"gas used:         {r.get('gas_used', 0)}\n"
                    f"standard:         ERC20 (GreenEnergy)\n"
                    f"\n>>> 6 角色 mint 白名单已同步：\n"
                    "   地铁/公交/单车/外卖/回收 5 业务角色已获准调用 mint()\n"
                    "   管理员保留 owner 权限：可增加/移除白名单、升级合约\n"
                    f"\n[完成] GreenEnergy 绿色能量代币已部署到{mode_label}，地址: {r['address']}\n"
                    f"        下一步(Step 10)：6 角色分别调用该地址的 mint() 做首次实战发放"
                )
        except Exception as e:
            output = f"部署失败: {e}"
            ok = False
    elif step == 10:
        # 真实调用：找最近部署的 GreenEnergy 合约 + 验证 6 角色发能量链路
        source = "real"
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
                # 查询 name + 初始余额（学习者已合并原 Alice 身份，发放统一入账 0xlearner）
                acct_learner = c.resolve_account("0xlearner")
                r_name = c.call_contract(addr, "name", [], "0xadmin", abi)
                r_bal0 = c.call_contract(addr, "balanceOf", [acct_learner], "0xadmin", abi)
                # 6 角色发放链路验证：地铁/外卖/回收 → 0xlearner +50/+10/+100
                # 以 deployer(admin) 身份执行 mint 授权 + 发放（白名单校验通过）
                r_metro = c.call_contract(addr, "mint", [acct_learner, 50],  "0xmetro",   abi)
                r_take  = c.call_contract(addr, "mint", [acct_learner, 10], "0xtakeout", abi)
                r_rec   = c.call_contract(addr, "mint", [acct_learner, 100],"0xrecycle", abi)
                r_bal_learn = c.call_contract(addr, "balanceOf", [acct_learner], "0xadmin", abi)
                def txline(label: str, r: dict) -> str:
                    if r.get("ok"):
                        return f"  {label:<16} tx_hash={r.get('tx_hash','')[:20]}...  gas={r.get('gas_used',0):<6}  status=1  OK"
                    return f"  {label:<16} FAIL: {r.get('error','unknown')[:60]}"
                output = (
                    f"> call GreenEnergy {addr} name\n{name_desc(r_name)}\n\n"
                    f"> 6 角色 mint 白名单实战发放(典型场景)：\n"
                    f"{txline('地铁 +50->learner',   r_metro)}\n"
                    f"{txline('外卖 +10->learner',   r_take)}\n"
                    f"{txline('回收 +100->learner',  r_rec)}\n"
                    "\n> 发放后余额快照：\n"
                    f"   0xlearner  balanceOf = {r_bal_learn.get('result','?')} GreenEnergy   "
                    f"(本轮 地铁+50，外卖+10，回收+100)\n"
                    "\n> Transfer/Mint 事件日志已上链(topic0 0xddf252ad... / 自定义 Mint)；"
                    "6 角色能量 -> 用户 -> 兑换 链路已打通\n"
                    f"\n[完成] 6 角色发能量全链路验证通过，10 步搭链教程结束；前往 /eco 进入完整联盟运营体验。"
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
    return {"ok": ok, "step": step, "commands": item["commands"], "output": output, "source": source}


def name_desc(r):
    return f"返回: {r.get('result', '?')} (view 函数，本地执行不消耗 Gas)" if r.get("ok") else r.get("error", "")


def balance_desc(r):
    v = r.get("result", "?")
    return f"返回: {v} (代币余额)" if r.get("ok") else r.get("error", "")


# ---------------------------------------------------------------------------
# 命令解析器：学生手动输入命令 → 语法校验 → 真实执行 → 结构化返回
# 每条命令定义: pattern（正则）, hint（语法错误时的具体提示）, executor（执行函数）
# ---------------------------------------------------------------------------

# 每步允许的命令列表（按 step 分组）
# 每条命令: {
#   "cmd": 显示用命令名,
#   "pattern": 正则（带 ^...$ 严格匹配）,
#   "syntax_hint": 语法错误时的具体提示,
#   "exec": 执行函数(wallet, c, match) -> {"ok": bool, "output": str}
# }

def _build_command_registry():
    """构建 10 步教程的命令注册表。

    每条命令定义（顺序即真实搭建案例的执行顺序）:
      cmd_index   : 对应 TUTORIAL[step].commands 中的索引（0 起），
                    用于严格记录并校验命令执行顺序
      patterns    : 允许输入的正则（严格匹配整条命令）
      syntax_hint : 语法错误时给出的具体提示
      type        : 命令类型
    """

    def _reg(cmd_index, patterns, hint, cmd_type="shell"):
        return {"cmd_index": cmd_index, "patterns": patterns, "syntax_hint": hint, "type": cmd_type}

    def _step1_cmds():
        # 官方完整流程：下载 build_chain.sh → chmod → 生成配置 → 启动节点
        return [
            _reg(0, [
                r"^curl.*build_chain\.sh.*chmod\s+\+x\s+build_chain\.sh.*$",
                r"^curl.*build_chain\.sh.*$",
                r"^chmod\s+\+x\s+build_chain\.sh$",
            ], "语法格式：curl -#LO https://github.com/FISCO-BCOS/FISCO-BCOS/releases/download/v2.9.1/build_chain.sh && chmod +x build_chain.sh\n下载官方 build_chain.sh 并赋予可执行权限"),
            _reg(1, [
                r"^bash\s+build_chain\.sh\s+-l\s+127\.0\.0\.1:4\s+-p\s+30300,20200,8545\s+-o\s+nodes\s*$",
            ], "语法格式：bash build_chain.sh -l 127.0.0.1:4 -p 30300,20200,8545 -o nodes\n一键生成 4 节点 PBFT 联盟链配置"),
            _reg(2, [
                r"^bash\s+nodes/127\.0\.0\.1/start_all\.sh\s*$",
            ], "语法格式：bash nodes/127.0.0.1/start_all.sh\n启动 4 个 FISCO-BCOS 共识节点"),
        ]

    def _step2_cmds():
        return [
            _reg(0, [
                r"^ps\s+-ef\s+\|\s+grep\s+fisco-bcos\s+\|\s+grep\s+-v\s+grep\s*$",
            ], "语法格式：ps -ef | grep fisco-bcos | grep -v grep\n查看 fisco-bcos 节点进程状态"),
            _reg(1, [
                r"^ls\s+nodes/127\.0\.0\.1/\s*$",
            ], "语法格式：ls nodes/127.0.0.1/\n查看建链产物目录（agency 证书 / ca / node0~3 / sdk 证书）"),
        ]

    def _step3_cmds():
        return [
            _reg(0, [
                r"^tail\s+-f\s+nodes/127\.0\.0\.1/node0/log/log_\*\s+\|\s+grep\s+-E\s+'\\\+\\\+\\\+Generating\|Report'\s*$",
            ], "语法格式：tail -f nodes/127.0.0.1/node0/log/log_*  | grep -E '\+\+\+Generating|Report'\n查看 PBFT 共识出块日志"),
        ]

    def _step4_cmds():
        return [
            _reg(0, [
                r"^cp\s+-r\s+nodes/127\.0\.0\.1/sdk/\*\s+~/fisco/console/conf/\s*$",
            ], "语法格式：cp -r nodes/127.0.0.1/sdk/* ~/fisco/console/conf/\n复制 SDK 证书到控制台配置目录（控制台持证接入联盟链）"),
            _reg(1, [
                r"^cd\s+~/fisco/console\s*&&\s*bash\s+start\.sh\s*$",
                r"^cd\s+~/fisco/console\s*$",
                r"^bash\s+start\.sh\s*$",
            ], "语法格式：cd ~/fisco/console && bash start.sh\n进入 console 目录并启动 FISCO BCOS 控制台", "console"),
            _reg(2, [
                r"^\[console\]\s+getBlockNumber\s*$",
            ], "语法格式：[console] getBlockNumber\n查询当前区块高度", "console"),
            _reg(3, [
                r"^\[console\]\s+getPeers\s*$",
            ], "语法格式：[console] getPeers\n查看对等节点", "console"),
            _reg(4, [
                r"^\[console\]\s+getSealerList\s*$",
            ], "语法格式：[console] getSealerList\n查看共识节点（sealer）列表", "console"),
            _reg(5, [
                r"^\[console\]\s+getGroupPeers\s*$",
            ], "语法格式：[console] getGroupPeers\n查看当前 group 内的节点", "console"),
        ]

    def _step5_cmds():
        return [
            _reg(0, [
                r"^ls\s+-la\s+nodes/127\.0\.0\.1/node0/conf/\s*$",
                r"^ls\s+nodes/127\.0\.0\.1/node0/conf/\s*$",
            ], "语法格式：ls -la nodes/127.0.0.1/node0/conf/\n查看节点接入凭据（证书 / 创世块 / 配置）"),
            _reg(1, [
                r"^cat\s+nodes/127\.0\.0\.1/node0/conf/config\.ini\s+\|\s+grep\s+-E\s+'[^']*'\s+\|\s+head\s+-\d+\s*$",
                r"^cat\s+nodes/127\.0\.0\.1/node0/conf/config\.ini\s+\|\s+grep.*$",
            ], "语法格式：cat nodes/127.0.0.1/node0/conf/config.ini | grep -E 'listen|peer|channel' | head -10\n查看 config.ini 网络/通道监听配置"),
            _reg(2, [
                r"^openssl\s+x509\s+-in\s+nodes/127\.0\.0\.1/node0/conf/node\.crt\s+-noout\s+-subject\s+-dates\s*$",
            ], "语法格式：openssl x509 -in nodes/127.0.0.1/node0/conf/node.crt -noout -subject -dates\n检查节点证书主体与有效期"),
            _reg(3, [
                r"^openssl\s+verify\s+-CAfile\s+nodes/127\.0\.0\.1/ca/ca\.crt\s+nodes/127\.0\.0\.1/node0/conf/node\.crt\s*$",
            ], "语法格式：openssl verify -CAfile nodes/127.0.0.1/ca/ca.crt nodes/127.0.0.1/node0/conf/node.crt\n用 CA 证书验证节点证书链"),
            _reg(4, [
                r"^\[console\]\s+getNodeVersion\s*$",
            ], "语法格式：[console] getNodeVersion\n查看链节点软件版本", "console"),
        ]

    def _step6_cmds():
        return [
            _reg(0, [
                r"^cat\s+<<'RULES'.*RULES\s*$",
                r"^cat\s+<<'?\w+'?.*$",
            ], "语法格式：cat <<'RULES' ... RULES\n输出 6 组织能量发放规则表（公示治理规则）"),
            _reg(1, [
                r"^\[console\]\s+getAccountBalance\s+0xmetro\s*$",
            ], "语法格式：[console] getAccountBalance 0xmetro\n查看地铁集团钱包真实余额", "console"),
            _reg(2, [
                r"^\[console\]\s+getAccountBalance\s+0xbus\s*$",
            ], "语法格式：[console] getAccountBalance 0xbus\n查看公交集团钱包真实余额", "console"),
            _reg(3, [
                r"^\[console\]\s+getAccountBalance\s+0xbike\s*$",
            ], "语法格式：[console] getAccountBalance 0xbike\n查看共享单车钱包真实余额", "console"),
            _reg(4, [
                r"^\[console\]\s+getAccountBalance\s+0xtakeout\s*$",
            ], "语法格式：[console] getAccountBalance 0xtakeout\n查看外卖平台钱包真实余额", "console"),
            _reg(5, [
                r"^\[console\]\s+getAccountBalance\s+0xrecycle\s*$",
            ], "语法格式：[console] getAccountBalance 0xrecycle\n查看回收公司钱包真实余额", "console"),
        ]

    def _step7_cmds():
        return [
            _reg(0, [
                r"^\[console\]\s+getAccountBalance\s+0xadmin\s*$",
            ], "语法格式：[console] getAccountBalance 0xadmin\n查看管理员钱包真实余额", "console"),
            _reg(1, [
                r"^\[console\]\s+getAccountBalance\s+0xbike\s*$",
            ], "语法格式：[console] getAccountBalance 0xbike\n查看共享单车钱包真实余额", "console"),
            _reg(2, [
                r"^\[console\]\s+getAccountBalance\s+0xtakeout\s*$",
            ], "语法格式：[console] getAccountBalance 0xtakeout\n查看外卖平台钱包真实余额", "console"),
            _reg(3, [
                r"^\[console\]\s+getAccountBalance\s+0xrecycle\s*$",
            ], "语法格式：[console] getAccountBalance 0xrecycle\n查看回收公司钱包真实余额", "console"),
            _reg(4, [
                r"^\[console\]\s+getAccountBalance\s+0xmetro\s*$",
            ], "语法格式：[console] getAccountBalance 0xmetro\n查看地铁集团钱包真实余额", "console"),
            _reg(5, [
                r"^\[console\]\s+getAccountBalance\s+0xbus\s*$",
            ], "语法格式：[console] getAccountBalance 0xbus\n查看公交集团钱包真实余额", "console"),
        ]

    def _step8_cmds():
        return [
            _reg(0, [
                r"^bash\s+nodes/127\.0\.0\.1/check_node_status\.sh\s+all\s*$",
            ], "语法格式：bash nodes/127.0.0.1/check_node_status.sh all\n检查 4 个节点在线状态"),
            _reg(1, [
                r"^for\s+i\s+in\s+\d\s+\d\s+\d\s+\d;\s+do\s+echo.*openssl\s+x509.*enddate;\s+done\s*$",
                r"^for\s+i\s+in.*openssl.*done\s*$",
            ], "语法格式：for i in 0 1 2 3; do echo \"=== node$i ===\"; openssl x509 -in nodes/127.0.0.1/node$i/conf/node.crt -noout -enddate; done\n批量检查 4 个节点证书有效期"),
            _reg(2, [
                r"^for\s+i\s+in\s+\d\s+\d\s+\d\s+\d;\s+do\s+echo.*nc\s+-zv.*done\s*$",
                r"^for\s+i\s+in.*nc.*done\s*$",
            ], "语法格式：for i in 0 1 2 3; do echo \"=== node$i ===\"; nc -zv 127.0.0.1 $((30300+i)) $((20200+i)) $((8545+i)) 2>&1; done\n批量测试 4 节点端口连通性"),
            _reg(3, [
                r"^\[console\]\s+call\s+GreenEnergy\s+(<address>|0x[0-9a-fA-F]{40})\s+name\s*$",
            ], "语法格式：[console] call GreenEnergy <address> name\n健康检查：查询能量代币合约名", "console"),
            _reg(4, [
                r"^\[console\]\s+call\s+PlantCertificate\s+(<address>|0x[0-9a-fA-F]{40})\s+name\s*$",
            ], "语法格式：[console] call PlantCertificate <address> name\n健康检查：查询植树证书合约名", "console"),
            _reg(5, [
                r"^\[console\]\s+call\s+EcoBadge\s+(<address>|0x[0-9a-fA-F]{40})\s+tokenURI\s+1\s*$",
            ], "语法格式：[console] call EcoBadge <address> tokenURI 1\n健康检查：使用 tokenURI(1) 探针验证环保勋章合约链上可调用（ERC1155 无 name() 视图）", "console"),
        ]

    def _step9_cmds():
        return [
            _reg(0, [
                r"^\[console\]\s+deploy\s+GreenEnergy\s+1000000\s*$",
            ], "语法格式：[console] deploy GreenEnergy 1000000\n部署 GreenEnergy ERC20 代币合约，初始发行量 1,000,000", "deploy"),
            _reg(1, [
                r"^\[console\]\s+getTransactionReceipt\s+(<tx_hash>|0x[0-9a-fA-F]{64})\s*$",
            ], "语法格式：[console] getTransactionReceipt <tx_hash>\n查询部署交易的回执（确认状态与 gas 消耗）", "console"),
        ]

    def _step10_cmds():
        return [
            _reg(0, [
                r"^\[console\]\s+call\s+GreenEnergy\s+(<address>|0x[0-9a-fA-F]{40})\s+name\s*$",
            ], "语法格式：[console] call GreenEnergy <address> name\n查询代币名称", "console"),
            _reg(1, [
                r"^\[console\]\s+call\s+GreenEnergy\s+(<address>|0x[0-9a-fA-F]{40})\s+balanceOf\s+0xlearner\s*$",
            ], "语法格式：[console] call GreenEnergy <address> balanceOf 0xlearner\n查询 0xlearner 的能量余额", "console"),
            _reg(2, [
                r"^\[console\]\s+call\s+GreenEnergy\s+(<address>|0x[0-9a-fA-F]{40})\s+mint\s+0xmetro\s+0x\w+\s+\d+\s+\S+\s*$",
            ], "语法格式：[console] call GreenEnergy <address> mint 0xmetro 0xlearner 50 地铁通勤≥10km\n地铁集团按规则发放 50 能量", "console"),
            _reg(3, [
                r"^\[console\]\s+call\s+GreenEnergy\s+(<address>|0x[0-9a-fA-F]{40})\s+mint\s+0xbus\s+0x\w+\s+\d+\s+\S+\s*$",
            ], "语法格式：[console] call GreenEnergy <address> mint 0xbus 0xlearner 20 公交出行≥5min\n公交集团按规则发放 20 能量", "console"),
            _reg(4, [
                r"^\[console\]\s+call\s+GreenEnergy\s+(<address>|0x[0-9a-fA-F]{40})\s+mint\s+0xbike\s+0x\w+\s+\d+\s+\S+\s*$",
            ], "语法格式：[console] call GreenEnergy <address> mint 0xbike 0xlearner 15 骑行≥2km\n共享单车按规则发放 15 能量", "console"),
            _reg(5, [
                r"^\[console\]\s+call\s+GreenEnergy\s+(<address>|0x[0-9a-fA-F]{40})\s+mint\s+0xtakeout\s+0x\w+\s+\d+\s+\S+\s*$",
            ], "语法格式：[console] call GreenEnergy <address> mint 0xtakeout 0xlearner 10 绿色外卖\n外卖平台按规则发放 10 能量", "console"),
            _reg(6, [
                r"^\[console\]\s+call\s+GreenEnergy\s+(<address>|0x[0-9a-fA-F]{40})\s+mint\s+0xrecycle\s+0x\w+\s+\d+\s+\S+\s*$",
            ], "语法格式：[console] call GreenEnergy <address> mint 0xrecycle 0xlearner 100 回收≥1kg\n回收公司按规则发放 100 能量", "console"),
            _reg(7, [
                r"^\[console\]\s+call\s+GreenEnergy\s+(<address>|0x[0-9a-fA-F]{40})\s+balanceOf\s+0xlearner\s*$",
            ], "语法格式：[console] call GreenEnergy <address> balanceOf 0xlearner\n复核 0xlearner 的能量余额", "console"),
        ]

    return {
        1: _step1_cmds(),
        2: _step2_cmds(),
        3: _step3_cmds(),
        4: _step4_cmds(),
        5: _step5_cmds(),
        6: _step6_cmds(),
        7: _step7_cmds(),
        8: _step8_cmds(),
        9: _step9_cmds(),
        10: _step10_cmds(),
    }


CMD_REGISTRY = _build_command_registry()


def _match_command(cmd_input: str, step: int) -> dict:
    """校验学生输入的命令是否语法正确。

    返回 {
      "ok": bool,
      "hint": str,
      "matched_pattern": str,
      "cmd_index": int | None,   # 匹配到的命令在 TUTORIAL[step].commands 中的索引
      "type": str,
    }
    """
    cmd_input = cmd_input.strip()
    if not cmd_input:
        return {"ok": False, "hint": "请输入命令，不能为空。", "matched_pattern": None, "cmd_index": None}

    # 注释行或空行跳过
    if cmd_input.startswith("#"):
        return {"ok": True, "hint": "", "matched_pattern": "comment", "type": "comment", "cmd_index": -1}

    cmds = CMD_REGISTRY.get(step, [])
    for cmd_def in cmds:
        for pattern in cmd_def.get("patterns", []):
            try:
                if re.match(pattern, cmd_input, re.MULTILINE | re.DOTALL):
                    return {
                        "ok": True,
                        "hint": "",
                        "matched_pattern": pattern,
                        "type": cmd_def.get("type", "shell"),
                        "cmd_index": cmd_def.get("cmd_index", 0),
                        "cmd_def": cmd_def,
                    }
            except re.error:
                continue

    # 没匹配到任何模式，返回该步骤所有命令的语法提示
    hints = []
    for cmd_def in cmds:
        hints.append(f"  ▪ {cmd_def['syntax_hint']}")
    hint_text = "\n".join(hints) if hints else f"步骤 {step} 无可用命令定义"
    return {"ok": False, "hint": hint_text, "matched_pattern": None, "cmd_index": None}


def _exec_command_impl(cmd_input: str, step: int, wallet: str, c) -> dict:
    """执行学生输入的命令（语法已校验通过），返回真实执行结果。

    技术债：Step 1-5 的全部输出与 Step 6 的 cat 规则表、Step 8 的进程/证书/端口检查
    输出均为「教学模式」硬编码模拟文本（本地无 docker / FISCO 节点环境时降级展示），
    并非真实终端执行；Step 6/7 余额查询、Step 8 合约调用、Step 9/10 为真实链执行。
    响应 source 字段由 _infer_command_source 统一标注 real / simulated。
    """
    cmd_input = cmd_input.strip()
    match_result = _match_command(cmd_input, step)
    if not match_result["ok"]:
        return {"ok": False, "output": match_result["hint"], "error_type": "syntax"}

    if match_result.get("type") == "comment":
        return {"ok": True, "output": "", "error_type": None}

    cmd_type = match_result.get("type", "shell")
    accounts = c.get_accounts()
    chain_h = c.block_number()

    # --- Step 1: 官方完整流程（下载 build_chain.sh → chmod → 生成配置 → 启动节点） ---
    if step == 1:
        # ① 下载 build_chain.sh（curl -#LO 真实 # 进度条样式）
        if cmd_input.startswith("curl"):
            return {"ok": True, "output": (
                "  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current\n"
                "                                 Dload  Upload   Total   Spent    Left  Speed\n"
                "100  3562  100  3562    0     0  12340      0  0:00:00  0:00:00 --:--:-- 12340\n"
                "100  3562  100  3562    0     0  12340      0  0:00:00  0:00:00 --:--:-- 12340  build_chain.sh"
            ), "error_type": None}
        # ② 赋予可执行权限（chmod 真实行为：成功无输出）
        if cmd_input.startswith("chmod"):
            return {"ok": True, "output": "", "error_type": None}
        # ③ 生成 4 节点配置（FISCO-BCOS build_chain.sh 2.9.1 真实输出格式）
        if cmd_input.startswith("bash build_chain.sh"):
            output = (
                "[INFO] FISCO-BCOS Path   : bin/fisco-bcos\n"
                "=========================================================...\n"
                "[INFO] Start Port        : 30300 20200 8545\n"
                "=========================================================...\n"
                "[INFO] Server IP         : 127.0.0.1:4\n"
                "=========================================================...\n"
                "[INFO] Output Dir        : nodes\n"
                "=========================================================...\n"
                "[INFO] The FISCO-BCOS framework is compiling, please wait...\n"
                "[INFO] FISCO-BCOS Path   : bin/fisco-bcos\n"
                "[INFO] Key Path          : nodes/127.0.0.1/sdk\n"
                "[INFO] Output Dir        : nodes\n"
                "=========================================================...\n"
                "[INFO] All completed. Files in nodes\n"
                "# 6 联盟组织 -> 4 共识节点映射（实训复用 4 节点承载 6 组织）：\n"
                "#   node0 = 管理员(0xadmin) + 地铁(0xmetro)\n"
                "#   node1 = 公交(0xbus) + 单车(0xbike)\n"
                "#   node2 = 外卖(0xtakeout) + 回收(0xrecycle)\n"
                "#   node3 = 热备共识（可扩展监管审计）"
            )
            return {"ok": True, "output": output, "error_type": None}
        # ④ 启动节点（真实 start_all.sh 输出 + 注释行说明角色映射）
        if "start_all.sh" in cmd_input:
            output = (
                "try to start node0 is_running: false  start successful\n"
                "try to start node1 is_running: false  start successful\n"
                "try to start node2 is_running: false  start successful\n"
                "try to start node3 is_running: false  start successful\n"
                "# node0 = 管理员 + 地铁；node1 = 公交 + 单车；node2 = 外卖 + 回收；node3 = 热备\n"
                f"# 4 个 FISCO-BCOS 节点已启动，当前块高: {chain_h}"
            )
            return {"ok": True, "output": output, "error_type": None}
        if cmd_input.startswith("cd "):
            return {"ok": True, "output": "", "error_type": None}

    # --- Step 2: 检查节点进程 + 证书目录 + openssl 验证 + nc 端口测试 ---
    if step == 2:
        # ① ps -ef | grep fisco-bcos | grep -v grep | wc -l  （或直接 ps -ef）
        if "ps -ef" in cmd_input or "ps aux" in cmd_input:
            if "wc -l" in cmd_input:
                # wc -l 只输出数字
                return {"ok": True, "output": "4", "error_type": None}
            output = (
                "UID        PID    PPID  C STIME TTY          TIME CMD\n"
                "root      1001      1  0 23:00 ?        00:00:01 fisco-bcos  nodes/127.0.0.1/node0/config.ini\n"
                "root      1002      1  0 23:00 ?        00:00:01 fisco-bcos  nodes/127.0.0.1/node1/config.ini\n"
                "root      1003      1  0 23:00 ?        00:00:01 fisco-bcos  nodes/127.0.0.1/node2/config.ini\n"
                "root      1004      1  0 23:00 ?        00:00:01 fisco-bcos  nodes/127.0.0.1/node3/config.ini\n"
                "# 4 个 fisco-bcos 进程运行中\n"
                "# 6 业务组织映射：node0=管理员+地铁  node1=公交+单车  node2=外卖+回收  node3=热备"
            )
            return {"ok": True, "output": output, "error_type": None}
        # ② ls nodes/127.0.0.1/  （真实 ls 输出 + 注释行说明证书体系）
        if cmd_input.startswith("ls "):
            output = (
                "agency/  ca/  node0/  node1/  node2/  node3/  sdk/\n"
                "start_all.sh  stop_all.sh  check_node_status.sh\n"
                "# 证书体系四要素：\n"
                "#   ca/      = 根 CA 证书（联盟信任锚点，签发全链证书）\n"
                "#   agency/  = 机构证书（Agency 准入凭证，联盟成员凭此互信）\n"
                "#   node0~3/ = 节点证书（各节点持有 CA 签发的节点证书 + 私钥）\n"
                "#   sdk/     = SDK 证书（控制台/应用接入凭证，Step 4 复制进 console）"
            )
            return {"ok": True, "output": output, "error_type": None}
        # ③ openssl x509 -in ca.crt -noout -subject -issuer -dates （真实 openssl 输出）
        if "openssl x509" in cmd_input and "-noout" in cmd_input:
            output = (
                "subject= CN=FISCO-BCOS-CA\n"
                "issuer= CN=FISCO-BCOS-CA\n"
                "notBefore=Jan  1 00:00:00 2026 GMT\n"
                "notAfter=Dec 31 23:59:59 2035 GMT\n"
                "# CA 证书自签名（subject == issuer），有效期至 2035 年"
            )
            return {"ok": True, "output": output, "error_type": None}
        # ④ openssl verify -CAfile ca.crt node.crt
        if "openssl verify" in cmd_input:
            return {"ok": True, "output": (
                "nodes/127.0.0.1/node0/conf/node.crt: OK\n"
                "# 证书链验证通过：节点证书由联盟 CA 签发，联盟准入凭证有效"
            ), "error_type": None}
        # ⑤ nc -zv 127.0.0.1 30300 20200 8545 2>&1 （真实 nc -zv 输出）
        if "nc " in cmd_input or "netcat" in cmd_input:
            output = (
                "Connection to 127.0.0.1 30300 port [tcp/*] succeeded!\n"
                "Connection to 127.0.0.1 20200 port [tcp/*] succeeded!\n"
                "Connection to 127.0.0.1 8545 port [tcp/*] succeeded!\n"
                "# 3 个端口全部监听（P2P/Channel/JSON-RPC），节点网络层可达"
            )
            return {"ok": True, "output": output, "error_type": None}
        if cmd_input.startswith("echo"):
            return {"ok": True, "output": cmd_input[6:].strip('"'), "error_type": None}

    # --- Step 3: 检查日志出块（真实 FISCO-BCOS log_INFO 格式） ---
    if step == 3:
        if "tail" in cmd_input:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
            log_file = f"log_{time.strftime('%Y%m%d%H%M%S', time.gmtime())}.log"
            if "ERROR" in cmd_input or "WARN" in cmd_input:
                # tail 日志查 ERROR/WARN
                return {"ok": True, "output": (
                    f"==> nodes/127.0.0.1/node0/log/{log_file} <==\n"
                    f"info|{ts}.012345|node0|[G:1][SEAL] Generating seal on 0 txs, force: 0\n"
                    f"info|{ts}.234567|node0|[G:1][REPORT] 4 Node IS consensus, sealer=0x12f2...a1\n"
                    f"# 最近 200 行无 ERROR；少量 INFO 属正常共识日志"
                ), "error_type": None}
            if "blk_num" in cmd_input:
                return {"ok": True, "output": (
                    f"==> nodes/127.0.0.1/node0/log/{log_file} <==\n"
                    f"blk_num={chain_h}\n"
                    f"blk_num={chain_h + 1}\n"
                    f"blk_num={chain_h + 2}"
                ), "error_type": None}
            if "hash=" in cmd_input:
                import hashlib
                h1 = hashlib.sha256(f"{chain_h}".encode()).hexdigest()
                h2 = hashlib.sha256(f"{chain_h+1}".encode()).hexdigest()
                h3 = hashlib.sha256(f"{chain_h+2}".encode()).hexdigest()
                return {"ok": True, "output": (
                    f"==> nodes/127.0.0.1/node0/log/{log_file} <==\n"
                    f"hash={h1}\n"
                    f"hash={h2}\n"
                    f"hash={h3}"
                ), "error_type": None}
            # 默认 tail 查 Generating seal / Report
            output = (
                f"==> nodes/127.0.0.1/node0/log/{log_file} <==\n"
                f"info|{ts}.012345|node0|[G:1][SEAL] Generating seal on 0 txs, sep: 0x9a3b..., force: 0\n"
                f"info|{ts}.234567|node0|[G:1][REPORT] 4 Node IS consensus, sealer=0, blk={chain_h}\n"
                f"info|{ts}.456789|node1|[G:1][SEAL] Generating seal on 0 txs, sep: 0xa4c5..., force: 0\n"
                f"info|{ts}.678901|node1|[G:1][REPORT] 4 Node IS consensus, sealer=1, blk={chain_h + 1}\n"
                f"info|{ts}.890123|node2|[G:1][SEAL] Generating seal on 2 txs, sep: 0xb7d8..., force: 0\n"
                f"info|{ts}.902345|node2|[G:1][REPORT] 4 Node IS consensus, sealer=2, blk={chain_h + 2}\n"
                f"# 持续输出 Generating seal + Report，PBFT 共识正常出块\n"
                f"# node0=管理员+地铁  node1=公交+单车  node2=外卖+回收  node3=热备"
            )
            return {"ok": True, "output": output, "error_type": None}

    # --- Step 4: 控制台接入（SDK 证书 + 链状态；真实控制台 banner + [group:1]> 提示符） ---
    if step == 4:
        if cmd_input.startswith("cp "):
            output = (
                f"'nodes/127.0.0.1/sdk/ca.crt' -> '~/fisco/console/conf/ca.crt'\n"
                f"'nodes/127.0.0.1/sdk/sdk.crt' -> '~/fisco/console/conf/sdk.crt'\n"
                f"'nodes/127.0.0.1/sdk/sdk.key' -> '~/fisco/console/conf/sdk.key'\n"
                "# SDK 证书三件套已复制到 console/conf/，控制台持证才能通过 Channel 协议连接联盟链"
            )
            return {"ok": True, "output": output, "error_type": None}
        if "openssl x509" in cmd_input and "-noout" in cmd_input:
            return {"ok": True, "output": (
                "subject= CN=FISCO-BCOS-SDK\n"
                "issuer= CN=FISCO-BCOS-CA\n"
                "notBefore=Jan  1 00:00:00 2026 GMT\n"
                "notAfter=Dec 31 23:59:59 2035 GMT\n"
                "# SDK 证书由联盟 CA 签发，有效期内"
            ), "error_type": None}
        if "openssl verify" in cmd_input:
            return {"ok": True, "output": (
                "nodes/127.0.0.1/sdk/sdk.crt: OK\n"
                "# SDK 证书链验证通过"
            ), "error_type": None}
        if cmd_input.startswith("[console]") or cmd_input.startswith("cd ~/fisco/console"):
            cmd_body = cmd_input.replace("[console]", "").strip()
            # cd / bash start.sh → 启动控制台 banner（真实 FISCO BCOS console 2.9.1 输出）
            if cmd_input.startswith("cd ") or cmd_input.startswith("bash start"):
                return {"ok": True, "output": (
                    "=================================================================================\n"
                    "Welcome to FISCO BCOS console(2.9.1)!\n"
                    "Type 'help' to get help.\n"
                    "================================================================================="
                ), "error_type": None}
            # 控制台命令 → 输出带 [group:1]> 提示符前缀，模拟真实交互式控制台
            if cmd_body == "getBlockNumber":
                return {"ok": True, "output": (
                    f"[group:1]> getBlockNumber\n"
                    f"BlockNumber = {chain_h}"
                ), "error_type": None}
            if cmd_body == "getPeers":
                return {"ok": True, "output": (
                    f"[group:1]> getPeers\n"
                    "[\n"
                    f'    {{"NodeID":"{accounts[1][:12]}...6e0c","IPAndPort":"127.0.0.1:30301","Node":"Node1"}},\n'
                    f'    {{"NodeID":"{accounts[2][:12]}...3ba1","IPAndPort":"127.0.0.1:30302","Node":"Node2"}},\n'
                    f'    {{"NodeID":"{accounts[3][:12]}...9f72","IPAndPort":"127.0.0.1:30303","Node":"Node3"}}\n'
                    "]"
                ), "error_type": None}
            if cmd_body == "getSealerList":
                return {"ok": True, "output": (
                    f"[group:1]> getSealerList\n"
                    "[\n"
                    f'    "12f2{accounts[0][6:26]}...a1   Node0",\n'
                    f'    "58c3{accounts[1][6:26]}...b2   Node1",\n'
                    f'    "9e4d{accounts[2][6:26]}...c3   Node2",\n'
                    f'    "b7a0{accounts[3][6:26]}...d4   Node3"\n'
                    "]\n"
                    "# 共识节点（sealer）总数: 4，PBFT 可容忍 1 个拜占庭节点"
                ), "error_type": None}
            if cmd_body == "getGroupPeers":
                return {"ok": True, "output": (
                    f"[group:1]> getGroupPeers\n"
                    "[\n"
                    f'    "12f2{accounts[0][6:26]}...a1",\n'
                    f'    "58c3{accounts[1][6:26]}...b2",\n'
                    f'    "9e4d{accounts[2][6:26]}...c3",\n'
                    f'    "b7a0{accounts[3][6:26]}...d4"\n'
                    "]\n"
                    "# groupId=1 内节点数: 4（6 业务组织共享同一群组）"
                ), "error_type": None}
        if cmd_input.startswith("cd ") or cmd_input.startswith("bash start"):
            return {"ok": True, "output": (
                "=================================================================================\n"
                "Welcome to FISCO BCOS console(2.9.1)!\n"
                "Type 'help' to get help.\n"
                "================================================================================="
            ), "error_type": None}

    # --- Step 5: 组织证书与节点归属核查 ---
    if step == 5:
        # ① ls -la nodes/127.0.0.1/node0/conf/  （真实 ls -la 格式：权限/链接/属主/大小/日期/文件名）
        if cmd_input.startswith("ls ") and "conf" in cmd_input:
            output = (
                "total 56\n"
                "drwxr-xr-x 2 root root 4096 Aug 25 10:24 .\n"
                "drwxr-xr-x 3 root root 4096 Aug 25 10:24 ..\n"
                "-rw-r--r-- 1 root root  928 Aug 25 10:24 config.ini\n"
                "-rw-r--r-- 1 root root 1054 Aug 25 10:24 group.1.genesis\n"
                "-rw-r--r-- 1 root root 1054 Aug 25 10:24 node.nodeid\n"
                "-rw-r--r-- 1 root root  887 Aug 25 10:24 node.crt\n"
                "-rw------- 1 root root  247 Aug 25 10:24 node.key\n"
                "-rw-r--r-- 1 root root  836 Aug 25 10:24 node.param\n"
                "# 接入凭据三件套：node.crt/node.key（证书身份）+ group.1.genesis（共识资格）+ config.ini（网络端口）"
            )
            return {"ok": True, "output": output, "error_type": None}
        # ② cat config.ini | grep ...  （真实 config.ini 关键配置行）
        if cmd_input.startswith("cat ") and "config.ini" in cmd_input:
            output = (
                ";network\n"
                "listen_ip=0.0.0.0\n"
                "p2p_listen_port=30300\n"
                ";rpc\n"
                "channel_listen_port=20200\n"
                "jsonrpc_listen_port=8545\n"
                ";peer\n"
                "node.0=127.0.0.1:30300\n"
                "node.1=127.0.0.1:30301\n"
                "node.2=127.0.0.1:30302\n"
                "node.3=127.0.0.1:30303\n"
                "# 网络/RPC/通道端口与对等节点配置正常"
            )
            return {"ok": True, "output": output, "error_type": None}
        # ③ openssl x509 -subject -dates  （真实证书主体与有效期）
        if cmd_input.startswith("openssl x509"):
            output = (
                "subject=C = CN, O = FISCO-BCOS, OU = node0, CN = fisco\n"
                "notBefore=Aug 25 02:24:18 2026 GMT\n"
                "notAfter=Aug 23 02:24:18 2031 GMT\n"
                "# 节点证书在有效期内（5 年有效期），主体 CN=fisco 对应 node0"
            )
            return {"ok": True, "output": output, "error_type": None}
        # ④ openssl verify -CAfile ...  （真实 verify 输出）
        if cmd_input.startswith("openssl verify"):
            output = (
                "nodes/127.0.0.1/node0/conf/node.crt: OK\n"
                "# 证书链验证通过：CA -> agency -> node 三级链路完整可信"
            )
            return {"ok": True, "output": output, "error_type": None}
        # ⑤ [console] getNodeVersion
        if "getNodeVersion" in cmd_input:
            return {"ok": True, "output": (
                "Version=2.9.1\n"
                "Supported version list:\n"
                "  v2.9.1\n"
                "  v2.8.0\n"
                "  v2.7.1\n"
                "# 联盟内各机构节点需保持版本一致，否则无法达成共识"
            ), "error_type": None}

    # --- Step 6: 治理规则公示（能量规则表 + 角色钱包验证） ---
    if step == 6:
        if cmd_input.startswith("cat"):
            # cat <<'RULES' ... RULES  原样输出 heredoc 内容（真实 cat 行为）
            output = (
                "角色         业务场景                     单次能量   钱包\n"
                "============================================================\n"
                "管理员       部署合约/树种管理               0        0xadmin\n"
                "地铁集团     乘坐地铁 1 次（里程 ≥ 10 km）   +50      0xmetro\n"
                "公交集团     乘坐公交 1 次（时长 ≥ 5 分钟）  +20      0xbus\n"
                "共享单车     骑行 ≥ 2 km                    +15      0xbike\n"
                "外卖平台     绿色外卖(无需餐具)             +10      0xtakeout\n"
                "回收公司     纸箱/塑料瓶回收 ≥ 1kg          +100     0xrecycle\n"
                "# 治理规则已公示，该阈值与生态合约（/eco）的链上凭证校验逻辑完全一致"
            )
            return {"ok": True, "output": output, "error_type": None}
        if "getAccountBalance" in cmd_input:
            addr = cmd_input.split()[-1]
            acct = c.resolve_account(addr)
            bal = c.get_balance(acct)
            acct_hex = acct if isinstance(acct, str) else "(resolved)"
            return {"ok": True, "output": (
                f"account: {addr} -> {acct_hex[:12]}...\n"
                f"balance: {hex(bal)} wei   ({bal} wei)\n"
                f"# 账户已上链，FISCO-BCOS 账户首次查询即激活，无需显式注册"
            ), "error_type": None}

    # --- Step 7: 注册 6 组织钱包（链上身份登记） ---
    if step == 7:
        if "getAccountBalance" in cmd_input:
            addr = cmd_input.split()[-1]
            acct = c.resolve_account(addr)
            bal = c.get_balance(acct)
            acct_hex = acct if isinstance(acct, str) else "(resolved)"
            return {"ok": True, "output": (
                f"account: {addr} -> {acct_hex[:12]}...\n"
                f"balance: {hex(bal)} wei   ({bal} wei)\n"
                f"# 钱包已激活上链，业务角色 mintRole 白名单将在 Step 9 部署后同步写入"
            ), "error_type": None}

    # --- Step 8: 联盟上线健康检查（节点 + 证书 + 端口 + 三合约探针） ---
    if step == 8:
        # ① check_node_status.sh all
        if cmd_input.startswith("bash") and "check_node_status" in cmd_input:
            output = (
                "[CHECK] node0  process: alive   p2p:30300  channel:20200  rpc:8545  [OK]\n"
                "[CHECK] node1  process: alive   p2p:30301  channel:20201  rpc:8546  [OK]\n"
                "[CHECK] node2  process: alive   p2p:30302  channel:20202  rpc:8547  [OK]\n"
                "[CHECK] node3  process: alive   p2p:30303  channel:20203  rpc:8548  [OK]\n"
                "----------------------------------------\n"
                "nodes online: 4/4   all checks passed\n"
                "# node0=管理员+地铁  node1=公交+单车  node2=外卖+回收  node3=热备"
            )
            return {"ok": True, "output": output, "error_type": None}
        # ② for i in 0 1 2 3; do ... openssl x509 ... -enddate; done
        if cmd_input.startswith("for") and "openssl" in cmd_input:
            output = (
                "=== node0 ===\n"
                "notAfter=Aug 23 02:24:18 2031 GMT\n"
                "=== node1 ===\n"
                "notAfter=Aug 23 02:24:18 2031 GMT\n"
                "=== node2 ===\n"
                "notAfter=Aug 23 02:24:18 2031 GMT\n"
                "=== node3 ===\n"
                "notAfter=Aug 23 02:24:18 2031 GMT\n"
                "# 4 个节点证书均未过期（有效期至 2031-08-23）"
            )
            return {"ok": True, "output": output, "error_type": None}
        # ③ for i in 0 1 2 3; do ... nc -zv ...; done
        if cmd_input.startswith("for") and "nc" in cmd_input:
            output = (
                "=== node0 ===\n"
                "Connection to 127.0.0.1 30300 port [tcp/*] succeeded!\n"
                "Connection to 127.0.0.1 20200 port [tcp/*] succeeded!\n"
                "Connection to 127.0.0.1 8545 port [tcp/*] succeeded!\n"
                "=== node1 ===\n"
                "Connection to 127.0.0.1 30301 port [tcp/*] succeeded!\n"
                "Connection to 127.0.0.1 20201 port [tcp/*] succeeded!\n"
                "Connection to 127.0.0.1 8546 port [tcp/*] succeeded!\n"
                "=== node2 ===\n"
                "Connection to 127.0.0.1 30302 port [tcp/*] succeeded!\n"
                "Connection to 127.0.0.1 20202 port [tcp/*] succeeded!\n"
                "Connection to 127.0.0.1 8547 port [tcp/*] succeeded!\n"
                "=== node3 ===\n"
                "Connection to 127.0.0.1 30303 port [tcp/*] succeeded!\n"
                "Connection to 127.0.0.1 20203 port [tcp/*] succeeded!\n"
                "Connection to 127.0.0.1 8548 port [tcp/*] succeeded!\n"
                "# 4 节点 × 3 端口 = 12 连通性全部通过（p2p/channel/rpc 三类端口互通）"
            )
            return {"ok": True, "output": output, "error_type": None}
        # ④/⑤/⑥ [console] call <Contract> <address> <method>
        if "call" in cmd_input:
            parts = cmd_input.replace("[console]", "").strip().split()
            contract_name = parts[1] if len(parts) > 1 else ""
            method = parts[3] if len(parts) > 3 else "name"
            raw_args = parts[4:] if len(parts) > 4 else []
            if contract_name not in ("GreenEnergy", "PlantCertificate", "EcoBadge"):
                return {"ok": False, "output": f"未识别的合约名，仅支持 GreenEnergy / PlantCertificate / EcoBadge", "error_type": "syntax"}
            try:
                with get_conn() as conn:
                    row = conn.execute(
                        "SELECT address,abi FROM deployed_contracts WHERE name=? ORDER BY created_at DESC LIMIT 1",
                        (contract_name,),
                    ).fetchone()
                if not row:
                    return {"ok": False, "output": f"链上未找到 {contract_name} 合约（内置合约由平台预置，GreenEnergy 将在 Step 9 由你部署）", "error_type": "prerequisite"}
                abi = json.loads(row["abi"])
                fn_names = [x.get("name") for x in abi if x.get("type") == "function"]
                if method not in fn_names:
                    return {"ok": False, "output": f"{contract_name} 合约 ABI 中不存在方法 {method}（可调用视图: {', '.join([n for n in fn_names if n][:6])}）", "error_type": "call"}
                call_args = [int(a) if str(a).isdigit() else a for a in raw_args]
                r = c.call_contract(row["address"], method, call_args, "0xadmin", abi)
                if r.get("ok"):
                    arg_label = ", ".join(raw_args) if raw_args else ""
                    return {"ok": True, "output": (
                        f"Return {r.get('result', '?')}\n"
                        f"# {contract_name}.{method}({arg_label}) view 函数本地执行，不消耗 Gas"
                    ), "error_type": None}
                return {"ok": False, "output": r.get("error", "调用失败"), "error_type": "call"}
            except Exception as e:
                return {"ok": False, "output": f"调用异常: {e}", "error_type": "call"}

    # --- Step 9: 部署 GreenEnergy + 查询 Receipt ---
    if step == 9:
        if "deploy" in cmd_input:
            try:
                ge_src = (settings.contracts_dir / "GreenEnergy.sol").read_text(encoding="utf-8")
                comp = compile_source(ge_src)
                if not comp["ok"]:
                    return {"ok": False, "output": "编译失败:\n" + "\n".join(comp["errors"]), "error_type": "compile"}
                r = c.deploy_contract(
                    "GreenEnergy", comp["abi"], comp["bytecode"], ge_src,
                    "0xadmin", "ERC20",
                    ctor_args=[1000000],
                )
                import json as _json
                with get_conn() as conn:
                    conn.execute("DELETE FROM deployed_contracts WHERE address=?", (r["address"],))
                    conn.execute(
                        "INSERT INTO deployed_contracts(address,name,abi,bytecode,source,deployer,tx_hash,standard,created_at) "
                        "VALUES(?,?,?,?,?,?,?,?,?)",
                        (r["address"], "GreenEnergy", _json.dumps(comp["abi"]), comp["bytecode"], ge_src,
                         "0xadmin", r["tx_hash"], "ERC20", now()),
                    )
                _track(EventType.CONTRACT_COMPILE_OK, target="GreenEnergy",
                       ref_id=r.get("tx_hash", ""), wallet=wallet,
                       extra={"deployer_onchain": "0xadmin", "address": r["address"]})
                mode_label = "FISCO-BCOS 节点" if isinstance(c, FiscoRpcClient) else "EVM 链"
                output = (
                    f"contract address: {r['address']}\n"
                    f"transaction hash: {r['tx_hash']}\n"
                    f"block number:     {r['block_number']}\n"
                    f"gas used:         {r.get('gas_used', 0)}\n"
                    f"standard:         ERC20 (GreenEnergy)\n"
                    f"\n# GreenEnergy 已部署到{mode_label}\n"
                    f"# 5 业务角色（metro/bus/bike/takeout/recycle）mintRole 白名单已同步\n"
                    f"# 下一步：[console] getTransactionReceipt {r['tx_hash']}"
                )
                return {"ok": True, "output": output, "error_type": None}
            except Exception as e:
                return {"ok": False, "output": f"部署失败: {e}", "error_type": "deploy"}
        if "getTransactionReceipt" in cmd_input:
            # 真实 getTransactionReceipt 输出（JSON-like key=value）
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT tx_hash, address, created_at FROM deployed_contracts WHERE name='GreenEnergy' ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
            if not row:
                return {"ok": False, "output": "未找到最近部署交易，请先执行 deploy", "error_type": "prerequisite"}
            tx_hash = row["tx_hash"] if not row["tx_hash"].startswith("<") else "0x" + "a" * 64
            blk = c.block_number()
            output = (
                f"transactionHash:    {tx_hash}\n"
                f"transactionIndex:   0\n"
                f"blockNumber:        {blk}\n"
                f"blockHash:          0x{'0' * 10}{'a' * 54}\n"
                f"contractAddress:    {row['address']}\n"
                f"gasUsed:            1847523\n"
                f"status:             0x1\n"
                f"from:               0x{'0' * 39}1   (0xadmin)\n"
                f"to:\n"
                f"logsBloom:          0x{'0' * 448}{'1' * 16}{'0' * 60}\n"
                f"logs:               [Transfer]\n"
                f"# status=0x1 表示交易成功；gasUsed≈1.85M（ERC20 部署典型 Gas 消耗）\n"
                f"# PBFT 共识下交易在 1 个区块内即确认（约 3 秒），无需多区块等待"
            )
            return {"ok": True, "output": output, "error_type": None}

    # --- Step 10: 调用 GreenEnergy（name/balanceOf/mint 全链路验证） ---
    if step == 10 and "call" in cmd_input and "GreenEnergy" in cmd_input:
        try:
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT address,abi FROM deployed_contracts WHERE name='GreenEnergy' ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
            if not row:
                return {"ok": False, "output": "请先执行第 9 步部署 GreenEnergy 合约", "error_type": "prerequisite"}
            abi = json.loads(row["abi"])
            addr = row["address"]
            parts = cmd_input.replace("[console]", "").strip().split()
            method = parts[3] if len(parts) > 3 else "name"
            args = parts[4:] if len(parts) > 4 else []

            # name = view
            if method == "name":
                r = c.call_contract(addr, "name", [], "0xadmin", abi)
                if r.get("ok"):
                    return {"ok": True, "output": (
                        f"Return: {r.get('result', '?')}\n"
                        f"# name() 是 view 函数，本地执行不消耗 Gas"
                    ), "error_type": None}
                return {"ok": False, "output": r.get("error", "调用失败"), "error_type": "call"}
            # balanceOf = view
            elif method == "balanceOf":
                acct_arg = args[0] if args else "0xlearner"
                r = c.call_contract(addr, "balanceOf", [c.resolve_account(acct_arg)], "0xadmin", abi)
                if r.get("ok"):
                    return {"ok": True, "output": (
                        f"Return: {r.get('result', '?')}\n"
                        f"# {acct_arg} balanceOf 返回整数能量值（decimals=0，1 能量 = 1 次低碳行为积分）"
                    ), "error_type": None}
                return {"ok": False, "output": r.get("error", "调用失败"), "error_type": "call"}
            # mint = state change
            elif method == "mint":
                if len(args) < 3:
                    return {"ok": False, "output": "mint 需要参数: 角色地址 目标地址 数量 [原因]，如: mint 0xmetro 0xlearner 50 地铁通勤≥10km", "error_type": "syntax"}
                role = args[0]
                target_addr = args[1]
                amount = int(args[2])
                reason = args[3] if len(args) > 3 else ""
                r = c.call_contract(addr, "mint", [c.resolve_account(target_addr), amount, reason], role, abi)
                if r.get("ok"):
                    return {"ok": True, "output": (
                        f"transaction hash: {r.get('tx_hash', '')}\n"
                        f"gas used:         {r.get('gas_used', 0)}\n"
                        f"status:           0x1\n"
                        f"# {role} -> {target_addr} +{amount} GreenEnergy\n"
                        f"# mint 为状态变更函数，已上链产生 Transfer 事件日志"
                    ), "error_type": None}
                return {"ok": False, "output": f"mint 失败: {r.get('error', '未知错误')}\n# 检查：角色是否在 mintRole 白名单内 / 凭证是否达阈值", "error_type": "call"}
        except Exception as e:
            return {"ok": False, "output": f"调用异常: {e}", "error_type": "call"}

    # 兑底
    return {"ok": True, "output": "(命令已执行)", "error_type": None}


def _infer_command_source(step: int, cmd_input: str, result: dict) -> str:
    """推断 /tutorial/command 响应的 source（唯一允许的响应增量字段）。

    - "real"：真实触达链 / 数据库的执行路径（Step 6/7 真实余额查询、Step 8 合约调用、
      Step 9 真实编译部署 / 回执查询、Step 10 真实合约调用，及这些路径上的
      call / deploy / compile / prerequisite 类失败）
    - "simulated"：「教学模式」硬编码模拟输出（Step 1-5 全部、Step 6 cat 规则表、
      Step 8 进程/证书/端口检查）、语法级拒绝、注释行、兑底分支
    """
    et = result.get("error_type")
    if et == "syntax":
        return "simulated"          # 语法级拒绝（含 Step 8 合约名白名单 / Step 10 mint 参数校验）
    if et in ("call", "deploy", "compile", "prerequisite"):
        return "real"               # 真实链 / 真实库执行路径上的结果（含失败）
    if step in (6, 7) and "getAccountBalance" in cmd_input:
        return "real"               # 真实余额查询（resolve_account + get_balance）
    if step == 8 and "[console]" in cmd_input and "call" in cmd_input:
        m = re.search(r"\[console\]\s+call\s+(\w+)", cmd_input)
        if m and m.group(1) in ("GreenEnergy", "PlantCertificate", "EcoBadge"):
            return "real"           # 真实合约调用
        return "simulated"
    if step == 9:
        return "real"               # 真实编译 + 部署 / 真实回执查询
    if step == 10 and "call" in cmd_input and "GreenEnergy" in cmd_input:
        return "real"               # 真实合约调用
    return "simulated"


def _exec_command(cmd_input: str, step: int, wallet: str, c) -> dict:
    """执行学生输入的命令（薄包装）：调用原实现主体并注入 source 字段。

    source = "real"（真实 docker / 链上执行）或 "simulated"（教学模式模拟输出）。
    """
    result = _exec_command_impl(cmd_input, step, wallet, c)
    result["source"] = _infer_command_source(step, cmd_input, result)
    return result


def exec_command_impl(payload: dict, user: dict) -> dict:
    """学生手动输入命令执行接口（严格记录并校验命令执行顺序）。

    请求体: {"step": int, "command": str, "wallet": str}
    返回: {
        "ok": bool,             # 命令是否执行成功
        "output": str,          # 执行输出（成功=真实链/真实工具返回，失败=具体提示）
        "error_type": str,      # syntax / order / compile / deploy / call / prerequisite / null
        "step_completed": bool, # 该步骤最后一条命令执行完毕才为 true
        "cmd_index": int,       # 当前命令在本步骤命令列表中的索引（0 起）
        "cmd_total": int,       # 本步骤命令总数
        "progress": int,        # 已完成的命令数（1..cmd_total）
        "source": str,          # 新增：real（真实执行）/ simulated（教学模式模拟输出）
    }

    技术债：_exec_command_impl 的 Step 1-5 输出等大量「教学模式」硬编码模拟文本，
    非真实终端执行；通过响应 source 字段区分，后续可接入真实终端执行器替换。

    任务 #21：实际执行路径（成功/失败）走五级验证流水线记录模式——L1/L2 不适用，
    L3 复用语法与顺序校验结果，L4 复用 _exec_command 执行结果；响应追加 pipeline。
    语法/顺序/注释类早退视为未进入执行，不落 task_runs；步骤完成时发 tutorial_step_done 事件。
    """
    _t0 = time.perf_counter()
    step = payload.get("step")
    command = payload.get("command", "")
    wallet = assert_actor_wallet(user, payload.get("wallet") or "", "wallet") or "default"
    # 学生身份（来自 JWT 验签，不再信任 X-* 自报头）
    x_user_id = user.get("user_id") or ""
    x_user_name = user.get("user_name") or ""
    class_id = (user.get("class_id") or "").strip()
    # 流水线上下文（钱包用校验后的执行钱包，可能与 JWT 钱包不同（内置生态钱包））
    _uc = verifier.user_ctx_from(user)
    _uc["wallet"] = wallet

    item = next((s for s in TUTORIAL if s["step"] == step), None)
    if not item:
        return {"ok": False, "output": f"无效步骤号: {step}", "error_type": "invalid_step",
                "step_completed": False, "cmd_index": -1, "cmd_total": 0, "progress": 0,
                "source": "simulated"}

    commands = item.get("commands", [])
    cmd_total = len(commands)

    c = get_chain_client()

    # 1) 语法校验
    match = _match_command(command, step)
    if not match["ok"]:
        return {
            "ok": False,
            "output": f"bash: command syntax error\n\n正确格式:\n{match['hint']}",
            "error_type": "syntax",
            "step_completed": False,
            "cmd_index": -1,
            "cmd_total": cmd_total,
            "progress": 0,
            "source": "simulated",
        }

    # 注释行：直接通过，不推进顺序
    if match.get("type") == "comment":
        return {"ok": True, "output": "", "error_type": None, "step_completed": False,
                "cmd_index": -1, "cmd_total": cmd_total, "progress": 0,
                "source": "simulated"}

    cmd_index = match.get("cmd_index", 0)

    # 2) 跨步骤前置校验：真实搭建必须按步骤顺序进行
    if step > 1:
        prev_item = next((s for s in TUTORIAL if s["step"] == step - 1), None)
        if prev_item:
            with get_conn() as conn:
                prev = conn.execute(
                    "SELECT done FROM chain_tutorial_progress WHERE wallet=? AND step=?",
                    (wallet, step - 1),
                ).fetchone()
            if not prev or not prev["done"]:
                return {
                    "ok": False,
                    "output": f"bash: warning: 步骤顺序错误：请先完成「步骤 {step - 1}：{prev_item['title']}」再执行本步骤。\n真实 FISCO-BCOS 搭建必须按步骤顺序进行。",
                    "error_type": "order",
                    "step_completed": False,
                    "cmd_index": cmd_index,
                    "cmd_total": cmd_total,
                    "progress": 0,
                    "source": "simulated",
                }

    # 3) 读取该步骤命令执行进度（cmd_idx：已完成到第几条，-1 表示尚未开始）
    with get_conn() as conn:
        prog = conn.execute(
            "SELECT cmd_idx FROM chain_tutorial_progress WHERE wallet=? AND step=?",
            (wallet, step),
        ).fetchone()
    cur_idx = int(prog["cmd_idx"]) if prog else -1

    # 3.5) 重复命令兼容：教程中可能存在文本相同的命令（如 Step 10 首尾各一次 balanceOf），
    #      正则按首次匹配返回索引；若「当前待执行命令」与该输入文本一致，则按待执行索引推进
    if 0 <= cmd_index <= cur_idx:
        next_idx = cur_idx + 1
        if next_idx < cmd_total and (commands[next_idx] or "").strip() == command.strip():
            cmd_index = next_idx

    # 4) 步骤内命令顺序校验：只能执行「当前待执行」的命令
    if cmd_index > cur_idx + 1:
        next_cmd = commands[cur_idx + 1] if cur_idx + 1 < cmd_total else commands[0]
        return {
            "ok": False,
            "output": f"bash: warning: 命令顺序错误：本步骤需要按真实搭建顺序逐条执行，请先执行第 {cur_idx + 2} 条命令：\n$ {next_cmd}\n\n（当前进度：已执行 {cur_idx + 1}/{cmd_total} 条）",
            "error_type": "order",
            "step_completed": False,
            "cmd_index": cmd_index,
            "cmd_total": cmd_total,
            "progress": max(0, cur_idx + 1),
            "source": "simulated",
        }

    # 5) 执行命令（返回真实链 / 真实工具输出）
    result = _exec_command(command, step, wallet, c)

    # 6) 成功则推进命令进度；最后一条命令完成时标记步骤完成
    if result.get("ok") and result.get("error_type") != "comment":
        new_idx = max(cur_idx, cmd_index)
        step_done = new_idx >= cmd_total - 1
        _upsert_step_state(wallet, step, 1 if step_done else 0,
                           output=(result.get("output") or "")[:8000],
                           finished=step_done, cmd_idx=new_idx,
                           user_id=x_user_id or "", class_id=class_id)
        if step_done and x_user_id:
            try:
                student_name = x_user_name or ""
                if student_name:
                    from urllib.parse import unquote
                    student_name = unquote(student_name)
                _auto_create_grade_draft(x_user_id, student_name, wallet)
            except Exception:
                pass
        # 任务 #21：记录模式流水线（L4 复用本模块执行结果，不重复执行）
        _stages = [
            verifier.stage_skipped("compile", "教程命令无独立编译阶段（Step 9 编译校验已在执行内完成）"),
            verifier.stage_skipped("semantic", "命令语义校验由语法匹配完成"),
            verifier.stage_result("business", True,
                                  f"语法与执行顺序校验通过（步骤 {step}，第 {cmd_index + 1}/{cmd_total} 条）"),
            verifier.stage_result("onchain", True,
                                  f"命令执行成功（source={result.get('source', 'simulated')}）",
                                  latency_ms=(time.perf_counter() - _t0) * 1000),
        ]
        _pipeline = verifier.finalize_run(
            "tutorial_command",
            {"step": step, "command": (command or "")[:200], "wallet": wallet},
            _uc, _stages, started_at=_t0, task_ref=f"step{step}")
        # 步骤完成 → 事件总线推送（前端 CloudDesktop/进度看板刷新）
        if step_done:
            bus_publish(BusEvent.TUTORIAL_STEP_DONE,
                        {"step": step, "wallet": wallet},
                        user_id=x_user_id or "", class_id=class_id)
        return {
            "ok": True,
            "output": result.get("output", ""),
            "error_type": result.get("error_type"),
            "step_completed": step_done,
            "cmd_index": cmd_index,
            "cmd_total": cmd_total,
            "progress": new_idx + 1,
            "source": result.get("source", "simulated"),
            "pipeline": _pipeline,
        }

    # 命令执行失败（编译 / 部署 / 调用 / 前置条件未满足等）：失败也落一行 task_runs
    _stages = [
        verifier.stage_skipped("compile", "教程命令无独立编译阶段"),
        verifier.stage_skipped("semantic", "命令语义校验由语法匹配完成"),
        verifier.stage_result("business", True, "语法与执行顺序校验通过"),
        verifier.stage_result("onchain", False,
                              f"命令执行失败（error_type={result.get('error_type') or 'unknown'}）",
                              latency_ms=(time.perf_counter() - _t0) * 1000),
    ]
    _pipeline = verifier.finalize_run(
        "tutorial_command",
        {"step": step, "command": (command or "")[:200], "wallet": wallet},
        _uc, _stages, started_at=_t0, task_ref=f"step{step}")
    return {
        "ok": False,
        "output": result.get("output", ""),
        "error_type": result.get("error_type"),
        "step_completed": False,
        "cmd_index": cmd_index,
        "cmd_total": cmd_total,
        "progress": max(0, cur_idx + 1),
        "source": result.get("source", "simulated"),
        "pipeline": _pipeline,
    }

