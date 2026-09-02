"""五级任务验证流水线（任务 #21）。

    L1 compile  →  L2 semantic  →  L3 business  →  L4 onchain  →  L5 scoring

职责与设计原则：
- 每级统一返回 {stage, ok, detail, latency_ms}（不适用级标 skipped: true）；
- run_pipeline    完整执行模式：L1-L4 由调用方注入的函数顺序执行，门控语义
                  （前级失败则后续级 skipped），用于 contracts /compile /deploy；
- finalize_run    记录模式：调用方已持有「现有校验 / 执行结果」（不重复校验
                  两次），仅组装 stages + 补 L5 + 落库，用于 eco /energy/issue
                  与 tutorial_engine.exec_command_impl（L3/L4 复用既有结果）；
- record_failure  失败兜底：业务主体早期失败（HTTPException 等）也落一行
                  task_runs（status='failed'），满足「失败也写」；
- 每次运行写 task_runs 一行（成功 / 失败均写，落库失败只记日志不阻塞业务）；
- L5 scoring：只产出「成绩影响摘要」——按钱包只读聚合 grades 既有数据源
  （learning.events.aggregate）中与本任务相关的计数；不重复算分、不调用
  learning/events.track（行为埋点保持在各接入点原位置，避免重复埋点）；
- 向后兼容：本模块只产出 pipeline 结构 {run_id, stages, ok, latency_ms}，
  由调用方以纯新增字段追加到既有响应，既有字段一律不变。

阶段函数协议（run_pipeline 注入的 fn）：
- fn(ctx) -> (ok: bool, detail: str) 或 (ok, detail, data)；
  ctx = {"task_type", "payload", "user_ctx", "artifacts"}，artifacts 为
  前序阶段的 data 产物（如 L1 编译结果供 L2 语义校验读取）；
- fn 直接返回 dict 视为产物直通（该级通过，产物入 artifacts）；
  返回 None / 其它非约定类型视为协议违规：记该级失败并告警；
- fn 抛异常视为该级失败（ok=False，detail=异常摘要），不向调用方抛出。
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# 五级固定顺序（stage_results JSON 与响应 pipeline.stages 均按此排列）
STAGES = ("compile", "semantic", "business", "onchain", "scoring")

# L5 成绩影响摘要：各任务类型关注的 aggregate 计数键
# （与 grades._compute_training_score 消费的 learning.events.aggregate 同源）
_SUMMARY_KEYS = {
    "compile": ("contract_compile_ok",),
    "deploy": ("deployed_contracts", "contract_compile_ok"),
    "energy_issue": ("energy_issue",),
    "tutorial_command": ("tutorial_done", "transactions"),
}


# ===========================================================================
# 基础结构
# ===========================================================================
def user_ctx_from(user: Optional[dict]) -> dict:
    """从 get_current_user 的身份 dict 提取流水线上下文（缺省安全）。"""
    u = user or {}
    return {
        "user_id": str(u.get("user_id") or ""),
        "wallet": str(u.get("wallet") or ""),
        "class_id": str(u.get("class_id") or "").strip(),
        "tenant_id": str(u.get("tenant_id") or ""),
        "role_id": int(u.get("role_id") or 0),
    }


def stage_result(stage: str, ok: bool, detail: str,
                 latency_ms: float = 0.0, skipped: bool = False) -> dict:
    """构造单级结果（统一字段口径）。"""
    return {
        "stage": stage,
        "ok": bool(ok),
        "skipped": bool(skipped),
        "detail": str(detail),
        "latency_ms": round(float(latency_ms or 0.0), 2),
    }


def stage_skipped(stage: str, detail: str) -> dict:
    """构造 skipped 级（ok=True：跳过不算失败，仅表示不适用）。"""
    return stage_result(stage, True, detail, 0.0, skipped=True)


@dataclass
class PipelineResult:
    """run_pipeline 返回值：既有响应构造所需的完整上下文。"""

    run_id: str
    task_type: str
    stages: list
    ok: bool
    status: str                      # success | failed
    latency_ms: float
    artifacts: dict = field(default_factory=dict)   # 各阶段 data 产物
    onchain_error: Optional[str] = None             # L4 异常摘要（供调用方还原错误响应）
    pipeline: dict = field(default_factory=dict)    # 直接挂到响应的结构


# ===========================================================================
# 阶段执行器
# ===========================================================================
def _run_stage(fn: Callable, ctx: dict) -> tuple:
    """执行单级函数，返回 (ok, detail, latency_ms, data, error)。

    fn 返回 (ok, detail) / (ok, detail, data)；抛异常 → 该级失败。
    任务 #25 收紧：返回 None（或非约定类型）视为协议违规 → 记该级失败并告警，
    仅 dict 视为产物直通（该级通过）。
    """
    t = time.perf_counter()
    try:
        ret = fn(ctx)
    except Exception as e:
        ms = (time.perf_counter() - t) * 1000
        msg = f"{type(e).__name__}: {e}"
        return False, msg, ms, None, msg
    ms = (time.perf_counter() - t) * 1000
    if isinstance(ret, tuple) and len(ret) >= 2 and isinstance(ret[0], bool):
        data = ret[2] if len(ret) > 2 else None
        return ret[0], str(ret[1]), ms, data, None
    if isinstance(ret, dict):
        # fn 直接返回产物对象：视为通过（产物直通）
        return True, "ok", ms, ret, None
    # 返回 None / 其它非约定类型：协议违规，记该级失败并告警（不再静默当成功）
    logger.warning(
        "[verifier] 阶段函数协议违规（返回 %s）: fn=%s task_type=%s",
        type(ret).__name__, getattr(fn, "__name__", repr(fn)),
        (ctx or {}).get("task_type") or "",
    )
    msg = f"阶段函数协议违规：返回 {type(ret).__name__}（应为 (ok, detail) 元组或产物 dict）"
    return False, msg, ms, None, msg


def _score_summary(task_type: str, wallet: str) -> dict:
    """L5 成绩影响摘要：只读聚合既有数据源，不重算分、不写埋点。"""
    keys = _SUMMARY_KEYS.get(task_type)
    if not keys or not wallet:
        return {}
    try:
        from .learning.events import aggregate
        m = aggregate(wallet)
        return {k: int(m.get(k, 0)) for k in keys}
    except Exception:
        logger.warning("[verifier] L5 成绩摘要聚合失败 task_type=%s", task_type, exc_info=True)
        return {}


def _persist_run(task_type: str, payload: dict, user_ctx: dict,
                 stages: list, status: str, latency_ms: float, task_ref: str) -> None:
    """写 task_runs 一行（失败容错：落库不阻塞业务，与埋点同风格）。"""
    try:
        from .db import _lock as _DB_LOCK, get_conn, now
        with _DB_LOCK, get_conn() as conn:
            conn.execute(
                "INSERT INTO task_runs(wallet,user_id,tenant_id,class_id,task_type,task_ref,"
                "stage_results,status,latency_ms,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    user_ctx.get("wallet") or "", user_ctx.get("user_id") or "",
                    user_ctx.get("tenant_id") or "", user_ctx.get("class_id") or "",
                    task_type, task_ref or "",
                    json.dumps(stages, ensure_ascii=False),
                    status, round(float(latency_ms or 0.0), 2), now(),
                ),
            )
    except Exception:
        logger.warning("[verifier] task_runs 落库失败 task_type=%s", task_type, exc_info=True)


def _build_pipeline(run_id: str, stages: list, latency_ms: float) -> tuple:
    """由 stages 计算整体结果并构造响应用 pipeline 结构。"""
    ok = all(s.get("ok") for s in stages if not s.get("skipped"))
    status = "success" if ok else "failed"
    return ok, status, {
        "run_id": run_id,
        "stages": stages,
        "ok": ok,
        "latency_ms": round(float(latency_ms or 0.0), 1),
    }


# ===========================================================================
# 完整执行模式（contracts /compile /deploy）
# ===========================================================================
def run_pipeline(task_type: str, payload: dict, user_ctx: dict, *,
                 compile_fn: Optional[Callable] = None,
                 semantic_fn: Optional[Callable] = None,
                 business_fns: Optional[list] = None,
                 onchain_fn: Optional[Callable] = None,
                 task_ref: str = "") -> PipelineResult:
    """五级顺序执行（L1-L4 由注入函数驱动，L5 自动附加）。

    - compile_fn / semantic_fn / onchain_fn：阶段函数（协议见模块注释）；
      传 None 表示该任务不适用该级（标 skipped）；
    - business_fns：[(name, fn), ...] 依次执行，全部通过该级才通过；
    - 门控：任一级失败 → 后续级 skipped（L5 摘要始终附加）；
    - L4 异常不向外抛：记入 onchain_error 供调用方还原既有错误响应；
    - 无论成败写 task_runs 一行。
    """
    t0 = time.perf_counter()
    ctx = {"task_type": task_type, "payload": payload or {},
           "user_ctx": user_ctx or {}, "artifacts": {}}
    stages: list = []
    gate = True
    onchain_error: Optional[str] = None

    # L1 compile
    if compile_fn is None:
        stages.append(stage_skipped("compile", f"{task_type} 任务不涉及编译"))
    else:
        ok, detail, ms, data, _err = _run_stage(compile_fn, ctx)
        stages.append(stage_result("compile", ok, detail, ms))
        if data is not None:
            ctx["artifacts"]["compile"] = data
        gate = gate and ok

    # L2 semantic
    if not gate:
        stages.append(stage_skipped("semantic", "前序阶段未通过，门控跳过"))
    elif semantic_fn is None:
        stages.append(stage_skipped("semantic", f"{task_type} 任务不涉及 ABI/参数语义校验"))
    else:
        ok, detail, ms, data, _err = _run_stage(semantic_fn, ctx)
        stages.append(stage_result("semantic", ok, detail, ms))
        if data is not None:
            ctx["artifacts"]["semantic"] = data
        gate = gate and ok

    # L3 business（按 task_type 注入适用规则：防重放 / 角色权限 / 钱包白名单等）
    if not gate:
        stages.append(stage_skipped("business", "前序阶段未通过，门控跳过"))
    elif not business_fns:
        stages.append(stage_skipped("business", f"{task_type} 任务无适用业务规则"))
    else:
        t = time.perf_counter()
        oks: list = []
        details: list = []
        for name, fn in business_fns:
            ok, detail, _ms, data, _err = _run_stage(fn, ctx)
            oks.append(ok)
            details.append(f"{name}: {detail}")
            if data is not None:
                ctx["artifacts"][f"business.{name}"] = data
        ms = (time.perf_counter() - t) * 1000
        ok = all(oks)
        stages.append(stage_result("business", ok, "；".join(details), ms))
        gate = gate and ok

    # L4 onchain
    if not gate:
        stages.append(stage_skipped("onchain", "前序阶段未通过，门控跳过"))
    elif onchain_fn is None:
        stages.append(stage_skipped("onchain", f"{task_type} 任务不涉及链上动作"))
    else:
        ok, detail, ms, data, err = _run_stage(onchain_fn, ctx)
        stages.append(stage_result("onchain", ok, detail, ms))
        if data is not None:
            ctx["artifacts"]["onchain"] = data
        if err:
            onchain_error = err
        gate = gate and ok

    # L5 scoring（始终附加：只读摘要，不影响门控）
    summary = _score_summary(task_type, (user_ctx or {}).get("wallet") or "")
    l5 = stage_result(
        "scoring", True,
        f"成绩影响摘要（grades 消费既有数据源，不重复算分）: "
        f"{json.dumps(summary, ensure_ascii=False)}",
        0.0,
    )
    l5["summary"] = summary
    stages.append(l5)

    latency_ms = (time.perf_counter() - t0) * 1000
    run_id = uuid.uuid4().hex[:16]
    ok, status, pipeline = _build_pipeline(run_id, stages, latency_ms)
    _persist_run(task_type, payload, user_ctx, stages, status, latency_ms,
                 task_ref or run_id)
    return PipelineResult(
        run_id=run_id, task_type=task_type, stages=stages, ok=ok,
        status=status, latency_ms=latency_ms,
        artifacts=ctx["artifacts"], onchain_error=onchain_error, pipeline=pipeline,
    )


# ===========================================================================
# 记录模式（eco /energy/issue、tutorial_engine.exec_command_impl）
# ===========================================================================
def finalize_run(task_type: str, payload: dict, user_ctx: dict,
                 stages: list, *, started_at: Optional[float] = None,
                 task_ref: str = "") -> dict:
    """记录模式：stages 由调用方用既有校验/执行结果组装（不重复校验两次）。

    自动补 L5（若未提供）→ 生成 run_id → 落 task_runs → 返回响应用
    pipeline 结构 {run_id, stages, ok, latency_ms}。
    """
    stages = [dict(s) for s in (stages or [])]
    if not any(s.get("stage") == "scoring" for s in stages):
        summary = _score_summary(task_type, (user_ctx or {}).get("wallet") or "")
        l5 = stage_result(
            "scoring", True,
            f"成绩影响摘要（grades 消费既有数据源，不重复算分）: "
            f"{json.dumps(summary, ensure_ascii=False)}",
        )
        l5["summary"] = summary
        stages.append(l5)
    latency_ms = (time.perf_counter() - started_at) * 1000 if started_at else 0.0
    run_id = uuid.uuid4().hex[:16]
    ok, status, pipeline = _build_pipeline(run_id, stages, latency_ms)
    _persist_run(task_type, payload, user_ctx, stages, status, latency_ms,
                 task_ref or run_id)
    return pipeline


def record_failure(task_type: str, payload: dict, user_ctx: dict,
                   started_at: float, detail: str, task_ref: str = "") -> dict:
    """业务主体早期失败（未走完整流水线）也落一行 task_runs（status=failed）。"""
    latency_ms = (time.perf_counter() - started_at) * 1000 if started_at else 0.0
    stages = [{
        "stage": "aborted", "ok": False, "skipped": False,
        "detail": str(detail)[:1000], "latency_ms": round(latency_ms, 2),
    }]
    run_id = uuid.uuid4().hex[:16]
    _persist_run(task_type, payload, user_ctx, stages, "failed", latency_ms,
                 task_ref or run_id)
    return {"run_id": run_id, "stages": stages, "ok": False,
            "latency_ms": round(latency_ms, 1)}


# ===========================================================================
# 内置阶段实现（接入点复用，避免各路由重复写校验）
# ===========================================================================
def compile_stage(source: str) -> tuple:
    """L1 compile（编译类任务）：真实调 tx_decoder.compile_source（带缓存）。

    返回 (ok, detail, result)：result 为完整编译产物（含失败时的 errors）。
    """
    from .tx_decoder import compile_source
    r = compile_source(source or "")
    ok = bool(r.get("ok"))
    errs = r.get("errors") or []
    detail = "编译成功" if ok else f"编译失败（{len(errs)} 条）: {'; '.join(str(e) for e in errs[:2])[:300]}"
    return ok, detail, r


def check_compile_semantic(ctx: dict) -> tuple:
    """L2 semantic（编译类任务）：编译产物的合约名 / 函数存在性粗校验。"""
    r = (ctx.get("artifacts") or {}).get("compile") or {}
    if not r.get("ok"):
        return False, "编译未通过，无产物可做语义校验"
    abi = r.get("abi") or []
    if not isinstance(abi, list):
        return False, "ABI 不是 JSON 数组"
    fns = [x for x in abi if isinstance(x, dict) and x.get("type") == "function"]
    name = r.get("name") or ""
    return True, f"合约 {name or '(未命名)'}：ABI 含 {len(fns)} 个函数，结构合法"


def check_deploy_artifacts(ctx: dict) -> tuple:
    """L1 compile（部署任务）：前端已提交 abi/bytecode，校验产物齐备；
    有源码时做 solc 复核（编译缓存命中时开销可忽略），复核失败仅提示不拦截
    （避免环境差异误伤既有部署链路）。
    """
    p = ctx.get("payload") or {}
    abi = p.get("abi")
    bytecode = p.get("bytecode") or ""
    if not isinstance(abi, list) or not abi:
        return False, "ABI 为空或格式不正确，请先编译合约"
    if not str(bytecode).strip():
        return False, "bytecode 为空，请先编译合约"
    recheck = "跳过（无源码）"
    source = p.get("source") or ""
    if source:
        try:
            from .tx_decoder import compile_source
            r = compile_source(source)
            recheck = "通过" if r.get("ok") else f"未通过（{len(r.get('errors') or [])} 条，不拦截部署）"
        except Exception as e:
            recheck = f"复核异常 {type(e).__name__}（不拦截部署）"
    return True, f"部署产物齐备（bytecode {len(str(bytecode))} 字符）；solc 复核: {recheck}"


def check_deploy_semantic(ctx: dict) -> tuple:
    """L2 semantic（部署任务）：ABI 结构 + 构造函数参数个数粗校验。"""
    p = ctx.get("payload") or {}
    abi = p.get("abi")
    if not isinstance(abi, list):
        return False, "ABI 应为 JSON 数组"
    fns = [x for x in abi if isinstance(x, dict) and x.get("type") == "function"]
    ctor = next((x for x in abi if isinstance(x, dict) and x.get("type") == "constructor"), None)
    need = len((ctor or {}).get("inputs", [])) if ctor else 0
    got = len(p.get("ctor_args") or [])
    if need and got != need:
        return False, f"构造函数需要 {need} 个参数，实际提供 {got} 个"
    return True, f"ABI 含 {len(fns)} 个函数；构造函数参数匹配（{got}/{need}）"


def check_wallet_whitelist(ctx: dict) -> tuple:
    """L3 business（部署/调用类任务）：钱包白名单。

    通过条件（任一）：
    1. keystore.has_account 已注册（链上已有账户）；
    2. 与当前登录身份钱包一致（新学生钱包首次使用时惰性注册，不能误拦）；
    3. 内置演示别名（DEMO_ALIASES）。
    """
    p = ctx.get("payload") or {}
    uc = ctx.get("user_ctx") or {}
    w = str(p.get("wallet") or p.get("deployer") or p.get("caller") or "").strip()
    if not w:
        return False, "钱包为空"
    try:
        from .keystore import DEMO_ALIASES, has_account
    except Exception:
        return True, "keystore 模块不可用，白名单校验降级放行"
    if w == (uc.get("wallet") or ""):
        return True, f"钱包 {w} 为当前登录身份钱包（白名单通过）"
    if w in DEMO_ALIASES or has_account(w):
        return True, f"钱包 {w} 在白名单（演示别名 / keystore 已注册）"
    return False, f"钱包 {w} 不在白名单（keystore 未注册且非当前身份）"


def onchain_deploy(client, req) -> tuple:
    """L4 onchain（部署任务）：复用 chain_client.deploy_contract，确认回执 status。

    回执成功语义按链后端归一化（任务 #25 评审修复）：
    - EVM / mock：回执 status=1 为成功；
    - FISCO-BCOS v2：回执 status=0 为成功。
    方案选型（改动最小）：读 settings.chain_mode 判断，不改
    chain_client 三个 deploy_contract 的返回结构（避免影响浏览器/
    交易列表等消费 status 原值的其它路径）。
    """
    r = client.deploy_contract(
        req.name, req.abi, req.bytecode, req.source,
        req.deployer, getattr(req, "standard", None), getattr(req, "ctor_args", None),
    )
    status = r.get("status")
    try:
        s = int(status)
        from .config import settings
        if str(getattr(settings, "chain_mode", "") or "").lower() == "fisco":
            ok = s == 0   # FISCO 回执 0 = 成功
        else:
            ok = s == 1   # EVM / mock 回执 1 = 成功
    except (TypeError, ValueError):
        ok = True
    return ok, f"部署回执 status={status}，address={r.get('address')}，块高={r.get('block_number')}", r
