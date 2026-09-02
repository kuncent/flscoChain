#!/usr/bin/env python3
"""多班级并发压测脚本（任务 #23）。

模拟多个班级的学生并发登录并执行 10 类平台操作，输出每类操作的
p50/p95/p99、错误率与总吞吐，用于沙盘 / 多班级演示形态的容量验证。

======================== 账号预置（必读） ========================
本平台登录是对外部 SSO（EXTERNAL_API_BASE）的代理，后端【没有注册端点】
（已核对 backend/app/routers/auth.py：仅 encrypt / login / session）。
因此压测账号必须事先在 SSO 侧存在，命名约定：
    账号 = {--seed}{全局序号:03d}      如 --seed 2024 → 2024001, 2024002, ...
    密码 = --password（默认 123456，与 docs/登录API文档.md 演示账号一致）
若登录批量失败（401），请先向平台管理员在 SSO 中批量开通对应学号。
===================================================================

登录请求结构（对照 backend/app/routers/auth.py）：
  1) POST /api/auth/encrypt   {"pwd": "<明文>"}            → data = 密文
  2) POST /api/auth/login     {"username", "passwordEncode"} → data.token = 平台 JWT
  备选：--sso-token-login 走智云 SSO Token 通道（先向 SSO 的
       generateZhiYunToken 换取 TOKEN，再 POST /api/auth/login {"TOKEN": ...}），
       适用于 SSO 侧未开通账号密码登录、仅有学号档案的演示环境。

10 类操作（只读为主、写操作幂等优先，不清空任何数据）：
  tutorial_progress  GET  /api/chain/tutorial/progress          只读
  tutorial_command   POST /api/chain/tutorial/command           用「注释行」命令：
                         引擎对 # 开头命令直接放行（见 tutorial_engine._match_command），
                         无终端执行、无顺序推进、无落库，天然幂等零副作用
  contracts_list     GET  /api/contracts/deployed               只读
  compile            POST /api/contracts/compile                内置 GreenEnergy 源码
  deploy             POST /api/contracts/deploy                 【默认跳过】：
                         部署非幂等，每轮都会在链上新增合约实例、累积链状态；
                         默认不启用以保护演示环境。需要压真实链上写入时加 --with-deploy
                         （复用预热阶段编译产物，避免重复编译放大负载）
  energy_balance     GET  /api/eco/energy/balance?wallet=...    只读
  role_switch        POST /api/eco/role/select                  INSERT OR REPLACE，幂等
  explorer_overview  GET  /api/explorer/overview                只读
  achievements_my    GET  /api/achievements/my                  只读（惰性成就检查）
  monitor            GET  /api/monitor/{address}                只读（地址取已部署合约）

依赖：仅 Python 3.10+ 标准库；如安装了 httpx（已在 backend/requirements.txt 中）
则自动启用连接池提升压测精度，否则回退 urllib。

用法示例：
  python scripts/loadtest.py --base http://127.0.0.1:8000 \
      --students 40 --classes 2 --ops 10 --seed 2024 --password 123456
  # 冒烟：
  python scripts/loadtest.py --students 2 --classes 1 --ops 2

退出码：0=通过；1=错误率 > --max-error-rate 或 p95 > --max-p95s；2=无账号登录成功。
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

try:  # httpx 可选（已含于 backend/requirements.txt），缺失时回退标准库
    import httpx  # type: ignore
except ImportError:  # pragma: no cover
    httpx = None

# ---------------- 操作权重（总和无需为 1，按相对比例抽样） ----------------
OP_WEIGHTS: dict[str, int] = {
    "tutorial_progress": 20,
    "tutorial_command": 15,
    "contracts_list": 12,
    "compile": 12,
    "energy_balance": 10,
    "explorer_overview": 10,
    "role_switch": 8,
    "achievements_my": 8,
    "monitor": 5,
    # deploy 默认 0（非幂等写操作），--with-deploy 时置 5
    "deploy": 0,
}

# 教程命令操作用「注释行」：引擎直接放行，零副作用（见文件头说明）
TUTORIAL_COMMENT_CMD = "# loadtest probe: idempotent comment line"

COMPILE_CONTRACT = "GreenEnergy"
DEPLOY_CTOR_ARGS = [1000000]  # 与教程 `[console] deploy GreenEnergy 1000000` 一致
# 智云 SSO Token 通道（仅 --sso-token-login 使用）
SSO_TOKEN_URL = "https://ecosim.sztzjy.com:166/server/api/user/generateZhiYunToken"


# ---------------- 结果记录 ----------------
@dataclass
class Sample:
    op: str
    status: int = 0          # HTTP 状态；0 表示未收到响应
    elapsed: float = 0.0     # 秒
    err_kind: str = ""       # ""=正常 / timeout / network
    biz_ok: bool = True      # 业务层 ok 字段（仅部分接口有）


@dataclass
class Session:
    username: str
    token: str = ""
    user_id: str = ""
    class_idx: int = 0


@dataclass
class Ctx:
    """压测共享上下文（只读数据，线程安全）。"""
    green_source: str = ""
    compile_cache: dict = field(default_factory=dict)   # deploy 复用的编译产物
    monitor_addresses: list = field(default_factory=list)
    role_keys: list = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


# ---------------- HTTP 封装（httpx 可选，回退 urllib） ----------------
class Http:
    """线程局部持有连接池客户端；返回 (status, text, elapsed, err_kind)。"""

    _local = threading.local()

    def __init__(self, base: str, timeout: float):
        self.base = base.rstrip("/")
        self.timeout = timeout

    def _client(self):
        if httpx is None:
            return None
        c = getattr(Http._local, "client", None)
        if c is None:
            c = httpx.Client(timeout=self.timeout)
            Http._local.client = c
        return c

    def request(self, method: str, path: str, token: str = "",
                json_body: dict | None = None, params: dict | None = None):
        url = self.base + path
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        t0 = time.perf_counter()
        client = self._client()
        try:
            if client is not None:
                r = client.request(method, url, json=json_body,
                                   params=params, headers=headers)
                return r.status_code, r.text, time.perf_counter() - t0, ""
            # ---- stdlib 回退 ----
            if params:
                url += "?" + urllib.parse.urlencode(params)
            data = None
            if json_body is not None:
                data = json.dumps(json_body).encode("utf-8")
                headers["Content-Type"] = "application/json"
            req = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read().decode("utf-8", "replace")
                    return resp.status, body, time.perf_counter() - t0, ""
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace") if e.fp else ""
                return e.code, body, time.perf_counter() - t0, ""
        except (TimeoutError,):
            return 0, "", time.perf_counter() - t0, "timeout"
        except Exception as e:  # noqa: BLE001 —— 压测需把一切网络异常归类统计
            kind = "timeout" if "timed out" in str(e).lower() or "timeout" in type(e).__name__.lower() else "network"
            return 0, str(e), time.perf_counter() - t0, kind


# ---------------- 登录 ----------------
def login_one(http: Http, username: str, pwd_encode: str) -> Session | None:
    status, text, _, _ = http.request(
        "POST", "/api/auth/login",
        json_body={"username": username, "passwordEncode": pwd_encode},
    )
    return _session_from_login(status, text, username)


def login_one_token(http: Http, username: str, password: str) -> Session | None:
    """智云 SSO Token 登录：先向 SSO 换 TOKEN，再用 TOKEN 换平台 JWT。

    直连外部 SSO（绕过本地后端），失败时返回 None，由主流程统计。
    """
    url = SSO_TOKEN_URL + "?" + urllib.parse.urlencode(
        {"username": username, "password": password})
    try:
        if httpx is not None:
            r = httpx.get(url, timeout=http.timeout, verify=False)
            status, text = r.status_code, r.text
        else:
            import ssl
            with urllib.request.urlopen(  # noqa: S310 —— 内网/演示环境固定 SSO 地址
                url, timeout=http.timeout,
                context=ssl._create_unverified_context()) as resp:
                status, text = resp.status, resp.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return None
    if status != 200:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    token = (payload or {}).get("data") or ""
    if payload.get("code") != 200 or not token:
        return None
    status, text, _, _ = http.request("POST", "/api/auth/login",
                                      json_body={"TOKEN": token})
    return _session_from_login(status, text, username)


def _session_from_login(status: int, text: str, username: str) -> Session | None:
    if status != 200:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    token = data.get("token") or ""
    if not token:
        return None
    return Session(username=username, token=token,
                   user_id=str(data.get("userId") or ""))


def encrypt_password(http: Http, password: str) -> str | None:
    status, text, _, _ = http.request(
        "POST", "/api/auth/encrypt", json_body={"pwd": password})
    if status != 200:
        return None
    try:
        return (json.loads(text) or {}).get("data")
    except json.JSONDecodeError:
        return None


# ---------------- 预热：取内置源码 / 已部署合约 / 角色列表 ----------------
def warmup(http: Http, ctx: Ctx, admin_token: str) -> None:
    status, text, _, _ = http.request("GET", f"/api/contracts/builtin/{COMPILE_CONTRACT}")
    if status == 200:
        try:
            ctx.green_source = (json.loads(text) or {}).get("source") or ""
        except json.JSONDecodeError:
            pass
    status, text, _, _ = http.request("GET", "/api/contracts/deployed")
    if status == 200:
        try:
            for d in json.loads(text) or []:
                if d.get("address"):
                    ctx.monitor_addresses.append(d["address"])
        except json.JSONDecodeError:
            pass
    status, text, _, _ = http.request("GET", "/api/eco/roles")
    if status == 200:
        try:
            ctx.role_keys = [r.get("key") for r in (json.loads(text) or []) if r.get("key")]
        except json.JSONDecodeError:
            pass
    # deploy 复用的一次性编译产物（避免 --with-deploy 时每轮重复编译）
    if ctx.green_source:
        status, text, _, _ = http.request(
            "POST", "/api/contracts/compile", token=admin_token,
            json_body={"name": COMPILE_CONTRACT, "source": ctx.green_source})
        if status == 200:
            try:
                r = json.loads(text)
                if r.get("ok"):
                    ctx.compile_cache = {"abi": r.get("abi") or [],
                                         "bytecode": r.get("bytecode") or "",
                                         "standard": r.get("standard") or ""}
            except json.JSONDecodeError:
                pass


# ---------------- 10 类操作实现（返回 Sample） ----------------
def _sample(op: str, resp: tuple, biz_ok: bool = True) -> Sample:
    status, _text, elapsed, err_kind = resp
    return Sample(op=op, status=status, elapsed=elapsed,
                  err_kind=err_kind, biz_ok=biz_ok)


def op_tutorial_progress(http, sess, ctx, turn):
    return _sample("tutorial_progress",
                   http.request("GET", "/api/chain/tutorial/progress", token=sess.token))


def op_tutorial_command(http, sess, ctx, turn):
    resp = http.request("POST", "/api/chain/tutorial/command", token=sess.token,
                        json_body={"step": 1, "command": TUTORIAL_COMMENT_CMD})
    biz = _biz_ok(resp)
    return _sample("tutorial_command", resp, biz)


def op_contracts_list(http, sess, ctx, turn):
    return _sample("contracts_list",
                   http.request("GET", "/api/contracts/deployed", token=sess.token))


def op_compile(http, sess, ctx, turn):
    resp = http.request("POST", "/api/contracts/compile", token=sess.token,
                        json_body={"name": COMPILE_CONTRACT, "source": ctx.green_source})
    return _sample("compile", resp, _biz_ok(resp))


def op_deploy(http, sess, ctx, turn):
    cc = ctx.compile_cache
    if not cc.get("bytecode"):
        return Sample(op="deploy", status=0, biz_ok=False)  # 无编译产物：记为失败
    resp = http.request("POST", "/api/contracts/deploy", token=sess.token,
                        json_body={"name": COMPILE_CONTRACT, "source": ctx.green_source,
                                   "abi": cc["abi"], "bytecode": cc["bytecode"],
                                   "standard": cc["standard"],
                                   "deployer": sess.user_id,  # JWT 本人身份，避免 403
                                   "ctor_args": DEPLOY_CTOR_ARGS})
    return _sample("deploy", resp, _biz_ok(resp))


def op_energy_balance(http, sess, ctx, turn):
    return _sample("energy_balance",
                   http.request("GET", "/api/eco/energy/balance",
                                token=sess.token, params={"wallet": sess.user_id}))


def op_role_switch(http, sess, ctx, turn):
    if not ctx.role_keys:
        return Sample(op="role_switch", status=0, biz_ok=False)
    role_key = ctx.role_keys[turn % len(ctx.role_keys)]
    resp = http.request("POST", "/api/eco/role/select", token=sess.token,
                        json_body={"wallet": sess.user_id, "role_key": role_key})
    return _sample("role_switch", resp, _biz_ok(resp))


def op_explorer_overview(http, sess, ctx, turn):
    return _sample("explorer_overview",
                   http.request("GET", "/api/explorer/overview", token=sess.token))


def op_achievements_my(http, sess, ctx, turn):
    return _sample("achievements_my",
                   http.request("GET", "/api/achievements/my", token=sess.token))


def op_monitor(http, sess, ctx, turn):
    if not ctx.monitor_addresses:
        return Sample(op="monitor", status=0, biz_ok=False)  # 无已部署合约：跳过计失败
    addr = ctx.monitor_addresses[turn % len(ctx.monitor_addresses)]
    return _sample("monitor",
                   http.request("GET", f"/api/monitor/{addr}", token=sess.token))


OPS = {
    "tutorial_progress": op_tutorial_progress,
    "tutorial_command": op_tutorial_command,
    "contracts_list": op_contracts_list,
    "compile": op_compile,
    "deploy": op_deploy,
    "energy_balance": op_energy_balance,
    "role_switch": op_role_switch,
    "explorer_overview": op_explorer_overview,
    "achievements_my": op_achievements_my,
    "monitor": op_monitor,
}


def _biz_ok(resp: tuple) -> bool:
    """业务层 ok 判定：HTTP 200 且响应体 ok/地址字段不显式为假。"""
    status, text, _, err = resp
    if err or status != 200:
        return False
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return True
    if isinstance(data, dict) and "ok" in data:
        return bool(data["ok"])
    return True


# ---------------- 统计 ----------------
def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = max(0, min(len(sorted_vals) - 1, int(round(p / 100 * (len(sorted_vals) - 1)))))
    return sorted_vals[k]


def summarize(samples: list[Sample], duration: float,
              max_error_rate: float, max_p95: float) -> int:
    by_op: dict[str, list[Sample]] = {}
    err_class: dict[str, int] = {}
    total_err = 0
    for s in samples:
        by_op.setdefault(s.op, []).append(s)
        is_err = bool(s.err_kind) or s.status >= 400 or (s.status == 0 and not s.err_kind)
        if s.err_kind:
            err_class[s.err_kind] = err_class.get(s.err_kind, 0) + 1
        elif s.status == 401:
            err_class["401"] = err_class.get("401", 0) + 1
        elif s.status == 403:
            err_class["403"] = err_class.get("403", 0) + 1
        elif s.status >= 500:
            err_class["5xx"] = err_class.get("5xx", 0) + 1
        elif s.status >= 400:
            err_class[f"4xx({s.status})"] = err_class.get(f"4xx({s.status})", 0) + 1
        if is_err:
            total_err += 1

    all_lat = sorted(s.elapsed for s in samples)
    total_err_rate = total_err / len(samples) if samples else 0.0
    overall_p95 = percentile(all_lat, 95)

    print("\n=== 压测结果（延迟单位：ms）===")
    header = f"{'操作':<20}{'次数':>6}{'错误':>6}{'错误率':>8}{'p50':>9}{'p95':>9}{'p99':>9}{'业务失败':>8}"
    print(header)
    print("-" * 76)
    fail = False
    for op in OP_WEIGHTS:
        group = by_op.get(op)
        if not group:
            continue
        lats = sorted(g.elapsed for g in group if not g.err_kind and 0 < g.status < 400)
        errs = sum(1 for g in group if g.err_kind or g.status >= 400 or g.status == 0)
        biz_bad = sum(1 for g in group if not g.biz_ok)
        print(f"{op:<20}{len(group):>6}{errs:>6}{errs/len(group)*100:>7.1f}%"
              f"{percentile(lats,50)*1000:>9.0f}{percentile(lats,95)*1000:>9.0f}"
              f"{percentile(lats,99)*1000:>9.0f}{biz_bad:>8}")
    print("-" * 76)
    print(f"总请求: {len(samples)}  耗时: {duration:.1f}s  "
          f"吞吐: {len(samples)/duration:.1f} req/s  总错误率: {total_err_rate*100:.2f}%")
    print(f"整体 p50/p95/p99: {percentile(all_lat,50)*1000:.0f} / "
          f"{overall_p95*1000:.0f} / {percentile(all_lat,99)*1000:.0f} ms")
    if err_class:
        print("错误分类: " + ", ".join(f"{k}={v}" for k, v in sorted(err_class.items())))
    else:
        print("错误分类: 无")

    if total_err_rate > max_error_rate:
        print(f"[FAIL] 总错误率 {total_err_rate*100:.2f}% > 阈值 {max_error_rate*100:.1f}%")
        fail = True
    if overall_p95 > max_p95:
        print(f"[FAIL] 整体 p95 {overall_p95*1000:.0f}ms > 阈值 {max_p95*1000:.0f}ms")
        fail = True
    if not fail:
        print("[PASS] 各项指标均在阈值内")
    return 1 if fail else 0


# ---------------- 主流程 ----------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="联盟链实训平台多班级并发压测（只读为主、写幂等优先）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="账号需预先存在于外部 SSO（后端无注册端点），命名 = {--seed}{序号:03d}。")
    ap.add_argument("--base", default="http://127.0.0.1:8000", help="后端地址（默认 %(default)s）")
    ap.add_argument("--students", type=int, default=40, help="每班学生数（默认 %(default)s）")
    ap.add_argument("--classes", type=int, default=2, help="班级数（默认 %(default)s）")
    ap.add_argument("--ops", type=int, default=10, help="每学生操作轮数（默认 %(default)s）")
    ap.add_argument("--seed", default="2024", help="账号前缀（默认 %(default)s，如 2024→2024001）")
    ap.add_argument("--password", default="123456", help="统一密码（默认 %(default)s，与文档演示账号一致）")
    ap.add_argument("--concurrency", type=int, default=0, help="并发线程数（默认=学生总数，上限 64）")
    ap.add_argument("--timeout", type=float, default=10.0, help="单请求超时秒（默认 %(default)s）")
    ap.add_argument("--max-error-rate", type=float, default=0.01, help="错误率阈值（默认 1%%）")
    ap.add_argument("--max-p95", type=float, default=3.0, help="p95 阈值秒（默认 %(default)s）")
    ap.add_argument("--with-deploy", action="store_true",
                    help="启用合约部署操作（非幂等写，默认关闭以减少链状态累积）")
    ap.add_argument("--sso-token-login", action="store_true",
                    help="改用智云 SSO Token 登录（适用于 SSO 未开通账号密码登录的环境）")
    args = ap.parse_args()

    if args.with_deploy:
        OP_WEIGHTS["deploy"] = 5

    total_students = args.students * args.classes
    if total_students <= 0 or args.ops <= 0:
        print("students/classes/ops 必须为正整数", file=sys.stderr)
        return 2

    http = Http(args.base, args.timeout)
    print(f"[loadtest] base={args.base}  学生={args.students}x{args.classes}班 "
          f"轮数={args.ops}  httpx={'是' if httpx else '否(stdlib 回退)'}")

    # 0) 健康检查
    status, text, _, err = http.request("GET", "/health")
    if err or status != 200:
        print(f"[loadtest] 后端不可达（{args.base}/health: {err or status}），请确认服务已启动",
              file=sys.stderr)
        return 2

    # 1) 密码加密（一次，全体复用；仅账号密码登录需要）
    pwd_encode = ""
    if not args.sso_token_login:
        pwd_encode = encrypt_password(http, args.password) or ""
        if not pwd_encode:
            print("[loadtest] /api/auth/encrypt 失败：检查 EXTERNAL_API_BASE / SSO 连通性；"
                  "若 SSO 未开通账号密码登录可改用 --sso-token-login", file=sys.stderr)
            return 2

    # 2) 批量登录
    usernames = [f"{args.seed}{i:03d}" for i in range(1, total_students + 1)]
    sessions: list[Session] = []
    login_fail = 0
    t0 = time.perf_counter()
    workers = args.concurrency or min(total_students, 64)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        if args.sso_token_login:
            futs = {pool.submit(login_one_token, http, u, args.password): u
                    for u in usernames}
        else:
            futs = {pool.submit(login_one, http, u, pwd_encode): u for u in usernames}
        for i, fut in enumerate(as_completed(futs)):
            sess = fut.result()
            if sess:
                sess.class_idx = i // args.students
                sessions.append(sess)
            else:
                login_fail += 1
    print(f"[loadtest] 登录完成：成功 {len(sessions)} / 失败 {login_fail}"
          f"（{time.perf_counter()-t0:.1f}s）")
    if not sessions:
        print("[loadtest] 无任何账号登录成功：请确认账号已在外部 SSO 预置"
              "（后端无注册端点；命名约定见 --help）", file=sys.stderr)
        return 2

    # 3) 预热共享数据
    ctx = Ctx()
    warmup(http, ctx, sessions[0].token)
    if not ctx.monitor_addresses:
        print("[loadtest] 提示：无已部署合约，monitor 操作将计为失败")
    print(f"[loadtest] 预热完成：内置源码 {'有' if ctx.green_source else '无'}，"
          f"合约地址 {len(ctx.monitor_addresses)} 个，角色 {len(ctx.role_keys)} 个")

    # 4) 生成操作任务：每学生每轮按权重抽 1 个操作
    op_names = list(OP_WEIGHTS)
    weights = [OP_WEIGHTS[n] for n in op_names]
    rng = random.Random(23)  # 固定种子，结果可复现
    tasks = [(s, rng.choices(op_names, weights=weights, k=1)[0], turn)
             for s in sessions for turn in range(args.ops)]

    # 5) 并发执行
    samples: list[Sample] = []
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(lambda s=s, op=op, turn=t: OPS[op](http, s, ctx, turn))
                for s, op, t in tasks]
        for fut in as_completed(futs):
            try:
                samples.append(fut.result())
            except Exception as e:  # noqa: BLE001
                samples.append(Sample(op="unknown", err_kind="network", biz_ok=False,
                                      status=0))
    duration = time.perf_counter() - t0

    # 6) 汇总输出 + 阈值判定
    return summarize(samples, duration, args.max_error_rate, args.max_p95)


if __name__ == "__main__":
    sys.exit(main())
