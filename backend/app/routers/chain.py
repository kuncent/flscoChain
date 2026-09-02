"""链状态 + 云桌面联盟链搭建教程路由（薄壳）。

教程数据（TUTORIAL / ROLE_ENERGY_RULES）与执行引擎（命令匹配 / 执行 / 进度持久化、
/tutorial/exec 与 /tutorial/command 的实现主体）已抽离至 app/learning/ 包：
- app/learning/tutorial_steps.py : 教程数据（ROLE_ENERGY_RULES 从 alliance_roles.ROLES 派生）
- app/learning/tutorial_engine.py: 执行引擎（移动代码不改行为；响应新增 source 字段）
- app/learning/alliance_roles.py : 联盟角色权威定义（ROLES / ROLE_ALIAS / 权限助手）

本模块仅保留薄路由与只读端点：Depends、参数解析、调 engine、原样返回。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException

from ..config import settings
from ..chain_client import get_chain_client, get_chain_mode_label, FiscoRpcClient
from ..db import get_conn
from ..security import (
    assert_actor_wallet,
    get_current_user,
    require_role,
    lower_wallet_in,
    resolve_wallet_candidates,
    BUILTIN_WALLETS,
    PRIVILEGED_ROLES,
)
from ..learning.alliance_roles import ROLES as ECO_ROLES
from ..learning.tutorial_steps import TUTORIAL, ROLE_ENERGY_RULES  # noqa: F401  (数据保持从本模块可引用)
from ..learning.tutorial_engine import exec_step_impl, exec_command_impl, _ensure_progress_table

router = APIRouter(prefix="/api/chain", tags=["chain"])


def _scoped_candidates(conn, user: dict, wallet: str) -> list[str]:
    """教程进度读侧的钱包归属收敛（IDOR 修复，任务 #18）。

    - 教师 / 管理员（PRIVILEGED_ROLES）：不收敛，保留请求钱包口径
      （班级教学管理场景，配额 / 卡点分析需要查任意学生）；
    - 学生：请求钱包必须落在本人候选集（resolve_wallet_candidates：请求钱包 /
      JWT wallet / user_id + user_info 登记钱包，如学生 stu: 别名）或平台内置
      生态演示钱包（BUILTIN_WALLETS，eco 角色切换场景）内；越出范围时不
      报 403 而是强制回落为本人候选集 —— Dashboard / CloudDesktop 现有
      调用（wallet = currentWallet / userId / 0xlearner）全部命中本人
      候选集，页面零感知，传他人钱包也只会得到本人进度数据。
    """
    req = (wallet or "").strip() or "default"
    uid = user.get("user_id") or ""
    if int(user.get("role_id") or 0) in PRIVILEGED_ROLES:
        return resolve_wallet_candidates(conn, req)
    mine = resolve_wallet_candidates(conn, user.get("wallet") or "", uid)
    if req in mine or req.lower() in BUILTIN_WALLETS:
        return resolve_wallet_candidates(conn, req, uid)
    return mine


@router.get("/tutorial/progress")
def get_progress(
    wallet: str = "default",
    user: dict = Depends(get_current_user),
):
    """查询 wallet 的搭链教程完成情况。返回 6 步的 done / 百分比。

    读侧按钱包候选集匹配（写路径可能是演示钱包 0xlearner，也可能是
    JWT wallet=userId），避免单值查询口径错位导致进度恒 0。
    任务 #18：强制登录（Depends(get_current_user)），学生经
    _scoped_candidates 收敛到本人候选集（历史 IDOR：任意 wallet 可查
    任意人进度，现越出候选集强制回落本人数据）。
    """
    _ensure_progress_table()
    total_steps = len(TUTORIAL)
    with get_conn() as conn:
        h, lc = lower_wallet_in(_scoped_candidates(conn, user, wallet))
        rows = conn.execute(
            f"SELECT step, done, cmd_idx, output, started_at, finished_at "
            f"FROM chain_tutorial_progress WHERE lower(wallet) IN ({h}) ORDER BY step",
            lc,
        ).fetchall()
    state_by_step: dict[int, dict] = {}
    for r in rows:
        state_by_step[r["step"]] = dict(r)
    progress_list = []
    done_count = 0
    for s in TUTORIAL:
        step_num = s["step"]
        row = state_by_step.get(step_num, {"step": step_num, "done": 0, "cmd_idx": -1, "output": None, "started_at": None, "finished_at": None})
        if row.get("done"):
            done_count += 1
        progress_list.append({
            "step": step_num,
            "title": s["title"],
            "desc": s.get("desc", ""),
            "done": bool(row.get("done")),
            "cmd_idx": int(row.get("cmd_idx") or -1),
            "cmd_total": len(s.get("commands", [])),
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
def reset_progress(payload: dict, user: dict = Depends(get_current_user)):
    wallet = assert_actor_wallet(user, payload.get("wallet") or "", "wallet") or "default"
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
# ROLE_ENERGY_RULES / TUTORIAL 已迁至 app/learning/tutorial_steps.py（ROLE_ENERGY_RULES 由
# alliance_roles.ROLES 派生，单一代码来源；本文件经顶部 import 保持原引用入口不变）
@router.get("/tutorial")
def get_tutorial(
    wallet: str = "default",
    user: dict = Depends(get_current_user),
):
    """返回搭链教程 steps，并带上 wallet 的完成状态（done/finished_at）。

    进度查询与 /tutorial/progress 同口径（钱包候选集），避免两处展示不一致。
    任务 #18：强制登录 + 学生候选集收敛（同 _scoped_candidates 说明）。
    """
    _ensure_progress_table()
    # 拉取该 wallet 的完成进度（候选集兼容双轨口径 + 归属收敛）
    with get_conn() as conn:
        h, lc = lower_wallet_in(_scoped_candidates(conn, user, wallet))
        rows = conn.execute(
            f"SELECT step, done, cmd_idx, output, started_at, finished_at "
            f"FROM chain_tutorial_progress WHERE lower(wallet) IN ({h}) ORDER BY step",
            lc,
        ).fetchall()
    state_by_step = {r["step"]: dict(r) for r in rows}
    # 注入每个步骤的完成状态与命令执行进度
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
        step_out["cmd_idx"] = int(row.get("cmd_idx") or -1)
        step_out["cmd_total"] = len(s.get("commands", []))
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


@router.get("/tutorial/rolematrix")
def tutorial_rolematrix():
    """组织-节点-角色矩阵：4 逻辑节点 ↔ 6 联盟组织映射 + 各角色职责摘要。

    角色数据从 eco.ROLES 只读引用（key/name/desc/权限位组合），与生态模块同源维护，
    此处不复制第二份角色定义；能量规则仅返回摘要字段，完整凭证字段见 GET /api/eco/roles。
    鉴权风格与相邻的 GET /tutorial 一致（公开只读）。
    """
    roles = []
    for r in ECO_ROLES:
        rule = r.get("energy_rule") or None
        roles.append({
            "key": r.get("key", ""),
            "name": r.get("name", ""),
            "icon": r.get("icon", ""),
            "wallet": r.get("wallet", ""),
            "desc": r.get("desc", ""),
            "perm": {
                "can_issue_badge": bool(r.get("can_issue_badge")),
                "can_issue_voucher": bool(r.get("can_issue_voucher")),
                "can_manage_trees": bool(r.get("can_manage_trees")),
            },
            "energy_rule": ({
                "action": rule.get("action"),
                "points": rule.get("points"),
                "min": rule.get("min"),
                "unit": rule.get("unit"),
            } if rule else None),
        })
    return {
        "nodes": NODE_ORG_MAP,
        "roles": roles,
    }


@router.get("/tutorial/progress/class")
def tutorial_progress_class(
    class_id: str = "",
    user: dict = Depends(require_role(1, 3)),
):
    """班级搭链进度聚合（仅管理员 / 教师）。

    - 参数 class_id 为空时：教师取自身 class_id（定位逻辑与 auth.py class-students 一致），
      管理员返回全部学生；教师无 class_id 返回空（避免越权）
    - 每生聚合 chain_tutorial_progress：done 步数、首个未 done 步骤（卡点）、
      平均步骤耗时（由 started_at/finished_at 时间戳差推导，表无耗时数值字段；
      解析失败或缺失时跳过，无可用样本则该指标为 None）
    SQL 风格仿照 auth.py class-students（逐生查询后 Python 聚合）。
    """
    _ensure_progress_table()
    rid = int(user.get("role_id") or 0)
    x_user_id = user.get("user_id") or ""

    def _parse_ts(ts: str | None):
        if not ts:
            return None
        try:
            return datetime.fromisoformat(str(ts).replace(" ", "T").replace("Z", ""))
        except Exception:
            return None

    with get_conn() as conn:
        # 1) 定位当前用户自身班级（user_info 优先，JWT class_id 兕底）
        my_class = ""
        if x_user_id:
            row = conn.execute(
                "SELECT class_id FROM user_info WHERE user_id=?", (x_user_id,)
            ).fetchone()
            if row:
                my_class = row["class_id"] or ""
        if not my_class:
            my_class = str(user.get("class_id") or "")
        # 越权防护：教师（rid=3）传入的 class_id 必须等于自身班级（JWT/user_info），
        # 不匹配返回 403；未传时用自己的班级。管理员（rid=1）不限。
        if rid == 3:
            req_class = (class_id or "").strip()
            if req_class and req_class != my_class:
                raise HTTPException(status_code=403, detail="教师仅能查看本人班级的搭链进度")
            class_id = my_class
        elif not class_id:
            # 管理员未传 class_id：按自身 user_info 班级（通常为空 → 返回全部学生）
            class_id = my_class
        # 2) 学生名单（role_id=4；教师限定同班，管理员可跨班）
        if class_id:
            students = conn.execute(
                "SELECT user_id, name, student_id, class_id, wallet FROM user_info "
                "WHERE role_id=4 AND class_id=? ORDER BY student_id",
                (class_id,),
            ).fetchall()
        elif rid == 1:
            students = conn.execute(
                "SELECT user_id, name, student_id, class_id, wallet FROM user_info "
                "WHERE role_id=4 ORDER BY class_id, student_id"
            ).fetchall()
        else:
            students = []
        # 3) 逐生聚合进度（范本：auth.py class-students 进度统计段）。
        #    按生构造钱包候选集：user_info.wallet=userId 而教程进度写路径
        #    多落在演示钱包 0xlearner，单值查询恒 0。
        total_steps = len(TUTORIAL)
        items = []
        total_done = 0
        for s in students:
            w = s["wallet"] or "0xlearner"
            h, lc = lower_wallet_in(resolve_wallet_candidates(conn, w, s["user_id"] or ""))
            rows = conn.execute(
                f"SELECT step, done, started_at, finished_at FROM chain_tutorial_progress "
                f"WHERE lower(wallet) IN ({h}) ORDER BY step",
                lc,
            ).fetchall()
            done_set = {r["step"] for r in rows if r["done"]}
            done_count = len(done_set)
            total_done += done_count
            stuck_step = next((st for st in range(1, total_steps + 1) if st not in done_set), None)
            stuck_title = ""
            if stuck_step:
                t = next((x for x in TUTORIAL if x["step"] == stuck_step), None)
                stuck_title = (t or {}).get("title", "")
            durations = []
            for r in rows:
                st, ft = _parse_ts(r["started_at"]), _parse_ts(r["finished_at"])
                if st and ft and ft > st:
                    durations.append((ft - st).total_seconds())
            items.append({
                "user_id": s["user_id"],
                "name": s["name"],
                "student_id": s["student_id"],
                "class_id": s["class_id"],
                "wallet": w,
                "done_steps": done_count,
                "total_steps": total_steps,
                "progress_pct": round(done_count * 100 / total_steps, 1) if total_steps else 0,
                "stuck_step": stuck_step,
                "stuck_title": stuck_title,
                "avg_duration_seconds": round(sum(durations) / len(durations), 1) if durations else None,
            })
        # 恒 0 可疑告警：全班进度均为 0 但表中确有数据，多为钱包口径错位，提示排查
        if items and all(it["done_steps"] == 0 for it in items):
            try:
                any_rows = conn.execute(
                    "SELECT COUNT(*) AS c FROM chain_tutorial_progress"
                ).fetchone()["c"]
            except Exception:
                any_rows = 0
            if any_rows:
                logging.warning(
                    "chain: 班级 %s 搭链进度全部为 0，但 chain_tutorial_progress 表有 "
                    "%s 条记录，可能存在钱包口径错位（查询者=%s），请核对候选集归一是否命中",
                    class_id, any_rows, x_user_id,
                )
    return {
        "class_id": class_id,
        "total": len(items),
        "avg_done_steps": round(total_done / len(items), 1) if items else 0,
        "items": items,
    }


@router.post("/tutorial/exec")
def exec_step(
    payload: dict,
    user: dict = Depends(get_current_user),
):
    """执行某一步骤（薄路由：实现主体已迁至 app/learning/tutorial_engine.exec_step_impl）。

    Step 1-4 真实操作 docker-compose 搭链；Step 5-8 展示 6 联盟节点组织配置；
    Step 9 真实编译 + 部署 GreenEnergy；Step 10 真实调用 + 验证 6 角色发能量链路。
    成功完成后自动记录 wallet 的完成进度（持久化，换设备续学）。
    响应新增 source 字段（"real"=真实 docker/链上执行 / "simulated"=教学模式模拟输出），
    既有字段不变。
    """
    return exec_step_impl(payload, user)








@router.post("/tutorial/command")
def exec_command(
    payload: dict,
    user: dict = Depends(get_current_user),
):
    """学生手动输入命令执行接口（薄路由：实现主体已迁至 app/learning/tutorial_engine.exec_command_impl）。

    严格记录并校验命令执行顺序。请求体: {"step": int, "command": str, "wallet": str}
    返回: {
        "ok": bool,             # 命令是否执行成功
        "output": str,          # 执行输出（成功=真实链/真实工具返回，失败=具体提示）
        "error_type": str,      # syntax / order / compile / deploy / call / prerequisite / null
        "step_completed": bool, # 该步骤最后一条命令执行完毕才为 true
        "cmd_index": int,       # 当前命令在本步骤命令列表中的索引（0 起）
        "cmd_total": int,       # 本步骤命令总数
        "progress": int,        # 已完成的命令数（1..cmd_total）
        "source": str,          # 唯一新增字段："real"=真实链/工具执行，"simulated"=教学模式模拟
    }
    """
    return exec_command_impl(payload, user)
