"""运营沙盘（任务 #22）：故障演练场景 / 轮次启停 / 负载生成器 / KPI 记分板。

架构与取舍
----------
1. 数据层：ops_scenarios（场景配置）/ ops_rounds（轮次台账）/ ops_kpis（KPI 样本
   + 处置动作流水，metric='action' 行的 value 存「距轮次启动秒数」，
   MTTD/MTTR 直接从动作流水推算，不再单独建动作表）。
2. 故障注入（教学安全：只做内存标记与合成数据，绝不删改学生真实数据）：
   - node_down       ：内存态标记模拟节点离线（_NODE_FAULTS，云桌面/监控经
     GET /api/sandbox/nodes 或 /rounds/active 读取）；
   - consensus_stall ：【取舍】chain_client 不在本任务白名单内，无法给班级实例
     加真实暂停标志位。折中方案：沙盘层维护 _STALL_FLAGS 班级暂停状态
     （/nodes、/rounds/active 与 SANDBOX 事件对外展示「出块暂停」），同时
     负载生成器在暂停期间停止注入交易——效果上链上无新交易入块，与共识停滞
     的可观测现象一致；轮次停止时自动解除；
   - replay_attack   ：向 eco_energy_records 仅 INSERT 两条共享同一 proof_no 的
     低价值可疑记录（proof_payload 标记 suspicious + sandbox_round），
     供审计方角色按重复 proof_no 检出；不 UPDATE / DELETE 任何既有行；
   - gas_spike       ：合成一批低价值转账抬高 gas 均值（走真实 chain_client）。
3. 负载生成器：每轮次一个守护线程，令牌桶限速（目标 TPS 上限 5）+ 每轮配额
   上限（默认 200 笔，硬顶 600）+ 教师一键停止（/rounds/{id}/stop）。
   线程以 stop_event.wait(tick) 为唯一休眠手段，置位后最多一个 tick 内退出；
   停止接口 join(3s) 确保轮次停止必然终止线程。
4. KPI 记分板：轮次期间每 KPI_INTERVAL_SECONDS（10s）计算
   MTTD（故障注入→首个处置动作）/ MTTR（→首个「对症」处置动作）/
   处置率（已命中的对症动作种类 / 场景应有种类）/ 合成交易成功率，
   写 ops_kpis 并经 events_bus 推送 'sandbox_kpi'（前端订阅即实时记分板）。
5. 事件常量：events_bus.BusEvent 仅预留 SANDBOX_READY/SANDBOX_EXIT 且
   events_bus.py 不在白名单，故沙盘事件类型以本模块字符串常量发布
   （sandbox_fault_injected / sandbox_kpi / sandbox_action / sandbox_round_stopped），
   SSE 帧名与字符串逐字一致，前端按名订阅。
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..chain_client import get_chain_client
from ..db import get_conn, now
from ..events_bus import publish as bus_publish
from ..security import get_current_user, require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sandbox", tags=["sandbox"])

# ===========================================================================
# 常量与限额（安全红线：配额 + 限速 + 可停止）
# ===========================================================================
SCENARIO_TYPES = {
    "node_down": "节点宕机",
    "consensus_stall": "共识停滞",
    "replay_attack": "凭证重放攻击",
    "gas_spike": "gas 飙升",
}

ACTION_TYPES = {
    "restart_node": "重启节点",
    "audit_replay": "重放审计",
    "fix_redeploy": "修复重部署",
    "throttle_tx": "交易限流",
}

# 各场景的「对症处置动作」（命中即推进处置率 / 结算 MTTR）
RESOLUTION_ACTIONS = {
    "node_down": ["restart_node"],
    "consensus_stall": ["restart_node", "fix_redeploy"],
    "replay_attack": ["audit_replay"],
    "gas_spike": ["fix_redeploy", "throttle_tx"],
}

MAX_TARGET_TPS = 5.0          # 目标 TPS 硬顶（教学环境限速）
MAX_DURATION_S = 600          # 单轮最长 10 分钟
MAX_QUOTA = 600               # 单轮合成交易硬顶（配额上限）
DEFAULT_TARGET_TPS = 1.0
DEFAULT_DURATION_S = 120
DEFAULT_QUOTA = 200
GAS_SPIKE_TX_MIN, GAS_SPIKE_TX_MAX = 1, 40

KPI_INTERVAL_SECONDS = 10.0   # KPI 记分板采样周期（模块级变量，测试可调）
WORKER_TICK_S = 0.25          # 负载线程心跳
STOP_JOIN_TIMEOUT_S = 3.0     # 停止接口等待线程退出的最长时间

# 沙盘事件类型（events_bus.py 不在白名单，不发新 BusEvent 常量，直接发字符串）
EV_FAULT_INJECTED = "sandbox_fault_injected"
EV_KPI = "sandbox_kpi"
EV_ACTION = "sandbox_action"
EV_ROUND_STOPPED = "sandbox_round_stopped"

# ===========================================================================
# 内存运行时（轮次线程注册表 + 故障标记；进程级，重启即清）
# ===========================================================================
_LOCK = threading.Lock()
_ROUNDS: dict[int, "_RoundRuntime"] = {}
_NODE_FAULTS: dict[str, dict] = {}    # class_id -> {node_index, offline, since, round_id}
_STALL_FLAGS: dict[str, dict] = {}    # class_id -> {stalled, since, round_id}


@dataclass
class _RoundRuntime:
    """进行中轮次的运行时状态（负载线程 + 计数 + 停止标志）。"""

    round_id: int
    class_id: str
    scenario_type: str
    target_tps: float
    duration_s: float
    quota: int
    started_ts: float                       # 轮次启动（≈故障注入）时间戳
    stop_event: threading.Event = field(default_factory=threading.Event)
    thread: Optional[threading.Thread] = None
    tokens: float = 0.0                     # 令牌桶余量
    attempted: int = 0                      # 合成交易尝试数
    succeeded: int = 0                      # 合成交易成功数
    finalized: bool = False                 # 结算幂等标志


def live_round_ids() -> list[int]:
    """当前进程内仍在运行的轮次（测试 / 运维观测用）。"""
    with _LOCK:
        return [rid for rid, rt in _ROUNDS.items() if not rt.finalized]


def get_runtime(round_id: int) -> Optional[_RoundRuntime]:
    with _LOCK:
        return _ROUNDS.get(round_id)


def get_sandbox_state(class_id: str) -> dict:
    """班级沙盘故障态（内存标记，供监控/云桌面读取）。"""
    with _LOCK:
        node = dict(_NODE_FAULTS.get(class_id) or {})
        stall = dict(_STALL_FLAGS.get(class_id) or {})
    return {
        "class_id": class_id,
        "node_fault": node or None,
        "consensus_stalled": bool(stall.get("stalled")),
        "stall_info": stall or None,
    }


def _is_stalled(class_id: str) -> bool:
    with _LOCK:
        return bool((_STALL_FLAGS.get(class_id) or {}).get("stalled"))


# ===========================================================================
# 请求模型
# ===========================================================================
class ScenarioCreateReq(BaseModel):
    scenario_type: str
    title: str = ""
    target_tps: float = DEFAULT_TARGET_TPS
    duration_s: int = DEFAULT_DURATION_S
    quota: int = DEFAULT_QUOTA
    node_index: int = 0          # node_down 场景：模拟宕机的节点编号（0-3）


class RoundStartReq(BaseModel):
    scenario_id: int


class ActionReq(BaseModel):
    action_type: str
    description: str = ""


# ===========================================================================
# 鉴权 / 归属助手
# ===========================================================================
def _class_of(user: dict) -> str:
    return str(user.get("class_id") or "").strip()


def _is_privileged(user: dict) -> bool:
    return int(user.get("role_id") or 0) in (1, 3)


def _row_to_dict(row, json_cols: tuple = ()) -> dict:
    d = dict(row)
    for c in json_cols:
        try:
            d[c] = json.loads(d.get(c) or "{}")
        except (TypeError, ValueError):
            pass
    return d


def _get_round_row(round_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM ops_rounds WHERE id=?", (int(round_id),)
        ).fetchone()


def _check_round_scope(row, user: dict) -> None:
    """轮次归属校验：管理员全量；教师/学生限本班。"""
    rid_role = int(user.get("role_id") or 0)
    if rid_role == 1:
        return
    if str(row["class_id"] or "") != _class_of(user):
        raise HTTPException(status_code=403, detail="仅能访问本班的沙盘轮次")


def _recover_stale_rounds(class_id: Optional[str] = None) -> int:
    """进程重启后 DB 遗留 running 轮次（线程已不存在）标记为已停止。"""
    with _LOCK:
        live = {rid for rid, rt in _ROUNDS.items() if not rt.finalized}
    with get_conn() as conn:
        if class_id is not None:
            rows = conn.execute(
                "SELECT id FROM ops_rounds WHERE status='running' AND class_id=?",
                (class_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT id FROM ops_rounds WHERE status='running'").fetchall()
        n = 0
        for r in rows:
            if int(r["id"]) in live:
                continue
            conn.execute(
                "UPDATE ops_rounds SET status='stopped', finished_at=?, "
                "result=? WHERE id=?",
                (now(), json.dumps({"stop_reason": "stale_recovered"},
                                   ensure_ascii=False), int(r["id"])),
            )
            n += 1
    return n


# ===========================================================================
# 故障注入（教学安全：仅内存标记与合成插入，不删改学生真实数据）
# ===========================================================================
def _inject_replay_record(rt: _RoundRuntime) -> str:
    """注入两条共享同一 proof_no 的可疑能量记录（仅 INSERT，供审计方检出重放）。

    eco_energy_records 带 UNIQUE(proof_no, role_key) 防刷索引，故重放副本换用
    另一发放角色（同一业务单号跨角色重复提交——这正是审计方可检出的异常形态）。
    """
    proof_no = f"SBX-{rt.round_id}-{uuid.uuid4().hex[:8]}"
    payload = json.dumps(
        {"suspicious": True, "sandbox_round": rt.round_id,
         "note": "沙盘演练：凭证重放攻击注入的重复 proof_no"},
        ensure_ascii=False,
    )
    rows_args = [
        ("0xsandbox", "metro", "地铁集团", "沙盘演练凭证（重放注入·原件）",
         1, "", now(), "0xmetro", proof_no, payload),
        ("0xsandbox", "bus", "公交集团", "沙盘演练凭证（重放注入·可疑重放）",
         1, "", now(), "0xbus", proof_no, payload),
    ]
    try:
        with get_conn() as conn:
            for args in rows_args:
                conn.execute(
                    "INSERT INTO eco_energy_records"
                    "(wallet,role_key,role_name,action,points,tx_hash,created_at,"
                    " issuer_wallet,proof_no,proof_payload) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    args,
                )
    except Exception as e:
        # 兼容未迁移扩展列的旧库：降级为基本列（重放特征仍由重复 proof_no 承担）
        logger.warning("[sandbox] replay 注入降级: %s", e)
        try:
            with get_conn() as conn:
                for act in ("沙盘演练凭证（重放注入·原件）", "沙盘演练凭证（重放注入·可疑重放）"):
                    conn.execute(
                        "INSERT INTO eco_energy_records"
                        "(wallet,role_key,role_name,action,points,tx_hash,created_at)"
                        " VALUES(?,?,?,?,?,?,?)",
                        ("0xsandbox", "metro", "地铁集团",
                         f"{act} {proof_no}", 1, "", now()),
                    )
        except Exception:
            logger.warning("[sandbox] replay 注入失败（表不可用）", exc_info=True)
    return proof_no


def _inject_gas_spike(rt: _RoundRuntime, cfg: dict) -> int:
    """合成一批低价值交易抬高 gas 均值（走真实班级链实例）。"""
    n = max(GAS_SPIKE_TX_MIN, min(GAS_SPIKE_TX_MAX, int(cfg.get("spike_tx_count", 12))))
    try:
        client = get_chain_client(rt.class_id or None)
    except Exception as e:
        logger.warning("[sandbox] gas_spike 获取链实例失败: %s", e)
        return 0
    ok = 0
    for _ in range(n):
        try:
            client.send_tx("0xlearner", "0xadmin", 1)
            ok += 1
        except Exception:
            break
    return ok


def _inject_fault(rt: _RoundRuntime, cfg: dict) -> dict:
    """按场景类型注入故障，返回故障描述（随事件/轮次响应对外可见）。"""
    t = rt.scenario_type
    fault: dict = {"type": t, "label": SCENARIO_TYPES[t], "injected_at": now()}
    if t == "node_down":
        idx = int(cfg.get("node_index", 0)) % 4
        with _LOCK:
            _NODE_FAULTS[rt.class_id] = {
                "node_index": idx, "offline": True, "since": now(),
                "round_id": rt.round_id,
            }
        fault["node_index"] = idx
        fault["desc"] = f"模拟节点 node{idx} 离线（内存标记，轮次结束自动恢复）"
    elif t == "consensus_stall":
        with _LOCK:
            _STALL_FLAGS[rt.class_id] = {
                "stalled": True, "since": now(), "round_id": rt.round_id,
            }
        fault["desc"] = ("班级链出块暂停标记（沙盘层状态；负载生成器同步停止注入，"
                         "链上无新交易入块，轮次结束自动解除）")
    elif t == "replay_attack":
        fault["proof_no"] = _inject_replay_record(rt)
        fault["desc"] = "已注入重复 proof_no 的可疑能量记录，等待审计方检出"
    elif t == "gas_spike":
        fault["synthetic_tx"] = _inject_gas_spike(rt, cfg)
        fault["desc"] = f"已合成 {fault['synthetic_tx']} 笔低价值交易抬高 gas 均值"
    bus_publish(EV_FAULT_INJECTED,
                {"round_id": rt.round_id, "scenario_type": t, "fault": fault},
                class_id=rt.class_id)
    return fault


def _recover_fault_state(class_id: str) -> None:
    """轮次结束：清除本班的故障标记（节点恢复在线 / 解除出块暂停）。"""
    with _LOCK:
        _NODE_FAULTS.pop(class_id, None)
        _STALL_FLAGS.pop(class_id, None)


# ===========================================================================
# 负载生成器 + KPI 记分板（轮次工作线程）
# ===========================================================================
def _inject_one_tx(rt: _RoundRuntime) -> None:
    """注入一笔合成交易（令牌桶放行后调用；失败只计数不中断）。"""
    rt.attempted += 1
    try:
        client = get_chain_client(rt.class_id or None)
        client.send_tx("0xlearner", "0xadmin", 1)
        rt.succeeded += 1
    except Exception as e:
        logger.debug("[sandbox] 合成交易失败 round=%s: %s", rt.round_id, e)


def _round_actions(round_id: int) -> list:
    with get_conn() as conn:
        return conn.execute(
            "SELECT value, detail, created_at FROM ops_kpis "
            "WHERE round_id=? AND metric='action' ORDER BY id ASC",
            (int(round_id),),
        ).fetchall()


def compute_kpis(rt: _RoundRuntime) -> dict:
    """KPI 计算（口径说明）：

    - mttd_seconds  ：故障注入（≈轮次启动）→ 首个处置动作的秒数（无动作则 -1）；
    - mttr_seconds  ：故障注入 → 首个「对症」处置动作（命中场景的
                      RESOLUTION_ACTIONS）的秒数（未恢复则 -1）；
    - handle_rate   ：已提交的对症动作种类数 / 场景应有种类数 × 100；
    - success_rate  ：合成交易成功数 / 尝试数 × 100（无尝试记 100）。
    """
    rows = _round_actions(rt.round_id)
    parsed = []
    for r in rows:
        try:
            d = json.loads(r["detail"] or "{}")
        except (TypeError, ValueError):
            d = {}
        parsed.append((float(r["value"] or 0), str(d.get("action_type") or "")))
    expected = RESOLUTION_ACTIONS.get(rt.scenario_type, [])
    mttd = parsed[0][0] if parsed else -1.0
    resolve_hits = [v for v, a in parsed if a in expected]
    mttr = resolve_hits[0] if resolve_hits else -1.0
    distinct = {a for _, a in parsed if a in expected}
    handle_rate = round(len(distinct) / len(expected) * 100, 1) if expected else 0.0
    success_rate = (round(rt.succeeded / rt.attempted * 100, 1)
                    if rt.attempted else 100.0)
    return {
        "mttd_seconds": round(mttd, 2),
        "mttr_seconds": round(mttr, 2),
        "handle_rate": handle_rate,
        "success_rate": success_rate,
        "tx_attempted": rt.attempted,
        "tx_succeeded": rt.succeeded,
        "actions_submitted": len(parsed),
    }


def _persist_and_publish_kpis(rt: _RoundRuntime) -> dict:
    """KPI 落库 + 发布 'sandbox_kpi'（前端实时记分板数据源）。"""
    kpis = compute_kpis(rt)
    try:
        with get_conn() as conn:
            for metric in ("mttd_seconds", "mttr_seconds", "handle_rate", "success_rate"):
                conn.execute(
                    "INSERT INTO ops_kpis(round_id,class_id,metric,value,detail,created_at)"
                    " VALUES(?,?,?,?,?,?)",
                    (rt.round_id, rt.class_id, metric, float(kpis[metric]),
                     json.dumps({"tx_attempted": kpis["tx_attempted"],
                                 "tx_succeeded": kpis["tx_succeeded"],
                                 "actions_submitted": kpis["actions_submitted"]},
                                ensure_ascii=False),
                     now()),
                )
    except Exception:
        logger.warning("[sandbox] KPI 落库失败 round=%s", rt.round_id, exc_info=True)
    bus_publish(EV_KPI,
                {"round_id": rt.round_id, "scenario_type": rt.scenario_type,
                 "kpis": kpis},
                class_id=rt.class_id)
    return kpis


def _round_worker(rt: _RoundRuntime) -> None:
    """轮次工作线程：令牌桶注入合成负载 + 周期 KPI 采样；停止标志置位即退出。"""
    last_kpi = time.time()
    try:
        while not rt.stop_event.wait(WORKER_TICK_S):
            tick_start = time.time()
            # consensus_stall：出块暂停期间不注入负载（与「链面无新交易」现象一致）
            if not _is_stalled(rt.class_id):
                rt.tokens = min(rt.target_tps * 2.0, rt.tokens + rt.target_tps * WORKER_TICK_S)
                while rt.tokens >= 1.0 and not rt.stop_event.is_set():
                    if rt.attempted >= rt.quota:
                        break
                    rt.tokens -= 1.0
                    _inject_one_tx(rt)
            if tick_start - last_kpi >= KPI_INTERVAL_SECONDS:
                try:
                    _persist_and_publish_kpis(rt)
                except Exception:
                    logger.warning("[sandbox] KPI 采样异常", exc_info=True)
                last_kpi = tick_start
            elapsed = tick_start - rt.started_ts
            if elapsed >= rt.duration_s or rt.attempted >= rt.quota:
                break
    except Exception:
        logger.warning("[sandbox] 轮次线程异常 round=%s", rt.round_id, exc_info=True)
    finally:
        # 时长到 / 配额耗尽 / 被停止：统一结算（幂等）
        _finalize_round(rt.round_id, stop_reason="duration_or_quota"
                        if not rt.stop_event.is_set() else "stopped")


def _finalize_round(round_id: int, stop_reason: str = "stopped") -> None:
    """轮次结算（幂等）：停线程、恢复故障态、落最终 KPI、更新台账、发事件。"""
    with _LOCK:
        rt = _ROUNDS.get(int(round_id))
        if rt is None or rt.finalized:
            return
        rt.finalized = True
    rt.stop_event.set()
    if threading.current_thread() is not rt.thread and rt.thread is not None:
        rt.thread.join(STOP_JOIN_TIMEOUT_S)
    try:
        kpis = _persist_and_publish_kpis(rt)
    except Exception:
        kpis = {}
        logger.warning("[sandbox] 结算 KPI 失败 round=%s", round_id, exc_info=True)
    _recover_fault_state(rt.class_id)
    result = {"stop_reason": stop_reason, "kpis": kpis,
              "target_tps": rt.target_tps, "duration_s": rt.duration_s,
              "quota": rt.quota}
    try:
        with get_conn() as conn:
            conn.execute(
                "UPDATE ops_rounds SET status='stopped', finished_at=?, result=? "
                "WHERE id=? AND status='running'",
                (now(), json.dumps(result, ensure_ascii=False), rt.round_id),
            )
    except Exception:
        logger.warning("[sandbox] 轮次台账更新失败 round=%s", round_id, exc_info=True)
    bus_publish(EV_ROUND_STOPPED,
                {"round_id": rt.round_id, "scenario_type": rt.scenario_type,
                 "stop_reason": stop_reason, "kpis": kpis},
                class_id=rt.class_id)
    with _LOCK:
        _ROUNDS.pop(rt.round_id, None)


# ===========================================================================
# 路由：教师端（限本班）
# ===========================================================================
@router.post("/scenarios")
def create_scenario(req: ScenarioCreateReq,
                    user: dict = Depends(require_role(1, 3))):
    """创建演练场景（教师/管理员，落本班）。"""
    st = (req.scenario_type or "").strip()
    if st not in SCENARIO_TYPES:
        raise HTTPException(status_code=422,
                            detail=f"scenario_type 仅支持: {'、'.join(SCENARIO_TYPES)}")
    cfg = {
        "target_tps": max(0.1, min(MAX_TARGET_TPS, float(req.target_tps or DEFAULT_TARGET_TPS))),
        "duration_s": max(10, min(MAX_DURATION_S, int(req.duration_s or DEFAULT_DURATION_S))),
        "quota": max(1, min(MAX_QUOTA, int(req.quota or DEFAULT_QUOTA))),
        "node_index": max(0, min(3, int(req.node_index or 0))),
    }
    class_id = _class_of(user)
    title = (req.title or "").strip() or f"{SCENARIO_TYPES[st]}演练"
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO ops_scenarios(title,class_id,scenario_type,config,status,"
            "created_by,created_at,user_id,tenant_id,session_id) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (title, class_id, st, json.dumps(cfg, ensure_ascii=False), "ready",
             user.get("user_id") or "", now(), user.get("user_id") or "", "", ""),
        )
        sid = int(cur.lastrowid)
    return {"id": sid, "title": title, "class_id": class_id, "scenario_type": st,
            "config": cfg, "status": "ready"}


@router.get("/scenarios")
def list_scenarios(user: dict = Depends(require_role(1, 3))):
    """本班场景列表（教师/管理员）。"""
    class_id = _class_of(user)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM ops_scenarios WHERE class_id=? ORDER BY id DESC LIMIT 50",
            (class_id,),
        ).fetchall()
    return {"items": [_row_to_dict(r, ("config",)) for r in rows]}


@router.post("/rounds/start")
def start_round(req: RoundStartReq, user: dict = Depends(require_role(1, 3))):
    """启动一轮演练（教师/管理员，限本班；同班同时仅允许一个进行中轮次）。"""
    class_id = _class_of(user)
    _recover_stale_rounds(class_id)
    with get_conn() as conn:
        sc = conn.execute(
            "SELECT * FROM ops_scenarios WHERE id=?", (int(req.scenario_id),)
        ).fetchone()
        if not sc:
            raise HTTPException(status_code=404, detail="场景不存在")
        if str(sc["class_id"] or "") != class_id and int(user.get("role_id") or 0) != 1:
            raise HTTPException(status_code=403, detail="仅能启动本班的场景")
        busy = conn.execute(
            "SELECT id FROM ops_rounds WHERE class_id=? AND status='running' LIMIT 1",
            (class_id,),
        ).fetchone()
        if busy:
            raise HTTPException(status_code=409, detail=f"本班已有进行中的轮次 #{busy['id']}，请先停止")
        try:
            cfg = json.loads(sc["config"] or "{}")
        except (TypeError, ValueError):
            cfg = {}
        cur = conn.execute(
            "INSERT INTO ops_rounds(scenario_id,class_id,status,started_at,result,"
            "user_id,tenant_id,session_id) VALUES(?,?,?,?,?,?,?,?)",
            (int(sc["id"]), class_id, "running", now(), "{}",
             user.get("user_id") or "", "", ""),
        )
        round_id = int(cur.lastrowid)
        conn.execute("UPDATE ops_scenarios SET status='used' WHERE id=?", (int(sc["id"]),))

    rt = _RoundRuntime(
        round_id=round_id, class_id=class_id,
        scenario_type=str(sc["scenario_type"]),
        target_tps=float(cfg.get("target_tps", DEFAULT_TARGET_TPS)),
        duration_s=float(cfg.get("duration_s", DEFAULT_DURATION_S)),
        quota=int(cfg.get("quota", DEFAULT_QUOTA)),
        started_ts=time.time(),
    )
    fault = _inject_fault(rt, cfg)
    th = threading.Thread(target=_round_worker, args=(rt,),
                          name=f"sandbox-round-{round_id}", daemon=True)
    rt.thread = th
    with _LOCK:
        _ROUNDS[round_id] = rt
    th.start()
    return {"round_id": round_id, "scenario_id": int(sc["id"]),
            "scenario_type": rt.scenario_type, "status": "running",
            "fault": fault, "config": cfg}


@router.post("/rounds/{round_id}/stop")
def stop_round(round_id: int, user: dict = Depends(require_role(1, 3))):
    """停止轮次（教师/管理员）：可靠终止负载线程 + 恢复故障态 + 结算 KPI。"""
    row = _get_round_row(round_id)
    if not row:
        raise HTTPException(status_code=404, detail="轮次不存在")
    _check_round_scope(row, user)
    if str(row["status"]) != "running" or get_runtime(round_id) is None:
        # 已停止 / 进程重启遗留：幂等处理
        _recover_stale_rounds(str(row["class_id"] or ""))
        row2 = _get_round_row(round_id)
        return {"round_id": round_id, "status": str(row2["status"] if row2 else "stopped"),
                "stop_reason": "already_stopped"}
    _finalize_round(round_id, stop_reason="teacher_stopped")
    row2 = _get_round_row(round_id)
    try:
        result = json.loads(row2["result"] or "{}") if row2 else {}
    except (TypeError, ValueError):
        result = {}
    return {"round_id": round_id, "status": "stopped",
            "stop_reason": "teacher_stopped", "kpis": result.get("kpis", {})}


@router.get("/rounds")
def list_rounds(limit: int = 20, user: dict = Depends(require_role(1, 3))):
    """本班轮次台账（教师/管理员）。"""
    class_id = _class_of(user)
    _recover_stale_rounds(class_id)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT r.*, s.title AS scenario_title, s.scenario_type AS stype "
            "FROM ops_rounds r LEFT JOIN ops_scenarios s ON s.id = r.scenario_id "
            "WHERE r.class_id=? ORDER BY r.id DESC LIMIT ?",
            (class_id, max(1, min(100, int(limit)))),
        ).fetchall()
    items = []
    for r in rows:
        d = _row_to_dict(r, ("result",))
        d["scenario_type"] = r["stype"] or d.get("scenario_type", "")
        d["scenario_title"] = r["scenario_title"] or ""
        items.append(d)
    return {"items": items}


@router.get("/rounds/{round_id}/kpis")
def round_kpis(round_id: int, user: dict = Depends(require_role(1, 3))):
    """某轮次的 KPI 明细（教师/管理员；含处置动作流水）。"""
    row = _get_round_row(round_id)
    if not row:
        raise HTTPException(status_code=404, detail="轮次不存在")
    _check_round_scope(row, user)
    with get_conn() as conn:
        krows = conn.execute(
            "SELECT metric, value, detail, created_at FROM ops_kpis "
            "WHERE round_id=? AND metric != 'action' ORDER BY id DESC LIMIT 400",
            (int(round_id),),
        ).fetchall()
        arows = conn.execute(
            "SELECT value, detail, created_at FROM ops_kpis "
            "WHERE round_id=? AND metric='action' ORDER BY id ASC",
            (int(round_id),),
        ).fetchall()
    samples: dict = {}
    for r in krows:  # 每类指标只留最新一条
        if r["metric"] not in samples:
            samples[r["metric"]] = _row_to_dict(r)
    actions = []
    for r in arows:
        d = _row_to_dict(r)
        try:
            d["detail"] = json.loads(d.get("detail") or "{}")
        except (TypeError, ValueError):
            pass
        actions.append(d)
    return {"round_id": int(round_id), "status": str(row["status"]),
            "latest": samples, "actions": actions}


# ===========================================================================
# 路由：全员（本班）
# ===========================================================================
@router.get("/rounds/active")
def active_round(user: dict = Depends(get_current_user)):
    """本班进行中的轮次 + 实时 KPI + 故障态（学生端记分板数据源）。"""
    class_id = _class_of(user)
    _recover_stale_rounds(class_id)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT r.*, s.title AS scenario_title "
            "FROM ops_rounds r LEFT JOIN ops_scenarios s ON s.id = r.scenario_id "
            "WHERE r.class_id=? AND r.status='running' ORDER BY r.id DESC LIMIT 1",
            (class_id,),
        ).fetchone()
    state = get_sandbox_state(class_id)
    if not row:
        return {"round": None, "fault": state}
    rt = get_runtime(int(row["id"]))
    if rt is not None:
        kpis = compute_kpis(rt)
    else:
        kpis = None
    arows = _round_actions(int(row["id"]))
    actions = []
    for r in arows[-20:]:
        try:
            d = json.loads(r["detail"] or "{}")
        except (TypeError, ValueError):
            d = {}
        actions.append({"elapsed_s": float(r["value"] or 0),
                        "created_at": r["created_at"], **d})
    d = _row_to_dict(row)
    d["scenario_title"] = row["scenario_title"] or ""
    # scenario_type 以场景表为准（rounds 表不冗余存储）
    with get_conn() as conn:
        sc = conn.execute("SELECT scenario_type FROM ops_scenarios WHERE id=?",
                          (int(row["scenario_id"]),)).fetchone()
    stype = str(sc["scenario_type"]) if sc else ""
    d["scenario_type"] = stype
    d["resolution_actions"] = RESOLUTION_ACTIONS.get(stype, [])
    return {"round": d, "kpis": kpis, "actions": actions, "fault": state}


@router.post("/rounds/{round_id}/action")
def submit_action(round_id: int, req: ActionReq,
                  user: dict = Depends(get_current_user)):
    """提交处置动作（全员，限本班进行中轮次）：记录时间戳供 MTTD/MTTR 计算。"""
    at = (req.action_type or "").strip()
    if at not in ACTION_TYPES:
        raise HTTPException(status_code=422,
                            detail=f"action_type 仅支持: {'、'.join(ACTION_TYPES)}")
    row = _get_round_row(round_id)
    if not row:
        raise HTTPException(status_code=404, detail="轮次不存在")
    _check_round_scope(row, user)
    if str(row["status"]) != "running" or get_runtime(round_id) is None:
        raise HTTPException(status_code=409, detail="轮次已结束或不可用，无法提交处置动作")
    rt = get_runtime(round_id)
    elapsed = round(time.time() - rt.started_ts, 2)
    detail = {
        "action_type": at,
        "action_label": ACTION_TYPES[at],
        "description": (req.description or "").strip()[:200],
        "user_id": user.get("user_id") or "",
        "user_name": user.get("user_name") or "",
    }
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO ops_kpis(round_id,class_id,metric,value,detail,created_at,"
            "user_id,tenant_id,session_id) VALUES(?,?,?,?,?,?,?,?,?)",
            (int(round_id), rt.class_id, "action", elapsed,
             json.dumps(detail, ensure_ascii=False), now(),
             user.get("user_id") or "", "", ""),
        )
    kpis = _persist_and_publish_kpis(rt)
    bus_publish(EV_ACTION,
                {"round_id": int(round_id), "elapsed_s": elapsed, **detail, "kpis": kpis},
                class_id=rt.class_id)
    return {"round_id": int(round_id), "elapsed_s": elapsed,
            "action_type": at, "kpis": kpis}


@router.get("/nodes")
def nodes_state(user: dict = Depends(get_current_user)):
    """本班沙盘故障态（节点离线标记 / 共识暂停标记；监控与云桌面可读取）。"""
    return get_sandbox_state(_class_of(user))
