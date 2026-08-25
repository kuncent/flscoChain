"""实训报告 API：聚合学习数据、高级实战、自动评分、操作错误分析、Markdown/JSON 导出。

评分规则 V2（学习性更强 + 商业逻辑更严谨，服务端计算，杜绝前端篡改）：
满分 100 = 基础模块 55 分（A~D） + 高级实战 40 分（E~G） + 综合拓展 5 分（I）。

【基础模块 55 分】
  A. 合约部署              20 分：≥1份合约 +10；ERC20/ERC721/ERC1155 各 +3/3/4；上限20
  B. 链上交易              15 分：≥10笔 15；≥5笔 10；≥2笔 5；≥1笔 2
  C. NFT 铸造与交易        10 分：铸造≥1件 +5；交易≥1笔 +5；合计上限10
  D. 搭链教程（必修）      10 分：完成 10/10 步 10分；≥5/10 6分；≥1/10 2分
        （额外：尝试并产生失败 step 的"探索型学生"额外 +1~3 分，计入D项"质量加分"）

【高级实战 40 分】（绿色低碳联盟链）
  E. 角色与节点体验        10 分：体验 6/6 角色 10 分；≥4 角色 8 分；≥2 角色 5 分；≥1 角色 2 分
  F. 能量发放多样性        10 分：3 种不同角色发放 10 分；2 种 6 分；1 种且≥3 次 3 分
  G. 资产兑换多样性        15 分：
          · 植树证书兑换 8 分（2+ 树种 8/1 树种 4/0）
          · 勋章/骑行券兑换 4 分（两类都有 4/一类 2/0）
          · 能量发放多样性（metro/bus/bike/takeout/recycle 实际≥4 种真实体验）+3 加分
  H. 合约激活 / 完整度      5 分：3/3 合约 5 分；2/3 2 分；1/3 1 分
        （这里把 H 从"勋章/骑行券"改成"合约激活"，勋章/骑行券合并进 G 里，保持 A~I 9 维度约定）

【扣分项 · 最低 0 分】
  - error × 1 分（上限 10）
  - warn × 0.3 分（上限 5）

【综合拓展题 5 分】（行为埋点，鼓励学生"真的学"而非"刷点"）
  I-1 合约源码阅读/编译/保存  ≥3 次内置模板源码查看  +2；至少 1 次 solc 真实编译成功 +1（合计上限 3）
  I-2 接口调试使用 ≥1 次    +2

【等级】
  未完成 (<60) / 合格 (60~69) / 良好 (70~79) / 优秀 (80~89) / 卓越 (≥90)
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Response, Header
from fastapi.responses import PlainTextResponse
from typing import Optional

from ..chain_client import get_chain_client, get_chain_mode_label
from ..db import get_conn, now

router = APIRouter(prefix="/api/report", tags=["report"])


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


def _parse_ts_any(val: Any) -> int:
    """兼容 TEXT (ISO 字符串) 和 数字/字符串数字 的时间戳，返回 unix 秒."""
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).strip()
    if not s:
        return 0
    if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
        try:
            return int(float(s))
        except Exception:
            return 0
    try:
        s2 = s.replace("T", " ")
        if "." in s2:
            s2 = s2.split(".", 1)[0]
        dt = datetime.strptime(s2, "%Y-%m-%d %H:%M:%S")
        return int(dt.timestamp())
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(s)
        return int(dt.timestamp())
    except Exception:
        return 0


def _load_eco_brief(wallet: str = "") -> dict[str, Any]:
    """加载 eco 高级实战汇总数据（无异常不中断，失败返回空结构）。

    V2：扩展学习质量维度（搭链进度/耗时分布、角色多样性、能量发放多样性、树种多样性、行为埋点）。
    V3：支持 per-wallet 过滤（wallet 非空时仅统计该钱包数据）。
    """
    try:
        with get_conn() as conn:
            # 构建 wallet 过滤条件
            wallet_filter = ""
            wallet_params = ()
            if wallet:
                wallet_filter = " WHERE wallet = ?"
                wallet_params = (wallet,)

            # ===== 角色：曾选择过多少不同的 UNIQUE 角色（E项基础）======
            row = conn.execute(
                "SELECT COUNT(DISTINCT role_key) AS distinct_roles, "
                "COUNT(*) AS total_switches, "
                "COUNT(DISTINCT wallet) AS unique_wallets "
                "FROM eco_role_selections" + wallet_filter,
                wallet_params
            ).fetchone()
            distinct_roles = row["distinct_roles"] if row else 0
            role_switches = row["total_switches"] if row else 0
            role_wallets = row["unique_wallets"] if row else 0

            # ===== 能量发放：次数、总点数、不同 role_key 发放的角色数（F项核心）======
            row = conn.execute(
                "SELECT COUNT(*) AS n, "
                "COALESCE(SUM(points),0) AS s, "
                "COUNT(DISTINCT role_key) AS distinct_roles "
                "FROM eco_energy_records" + wallet_filter,
                wallet_params
            ).fetchone()
            energy_issues = row["n"] if row else 0
            energy_total = row["s"] if row else 0
            energy_distinct_roles = row["distinct_roles"] if row else 0

            # 每种角色具体发了多少次（排序）
            if wallet:
                breakdown_rows = conn.execute(
                    "SELECT role_key, COUNT(*) AS n, COALESCE(SUM(points),0) AS s "
                    "FROM eco_energy_records " + wallet_filter + " "
                    "GROUP BY role_key ORDER BY n DESC",
                    wallet_params
                ).fetchall()
            else:
                breakdown_rows = conn.execute(
                    "SELECT role_key, COUNT(*) AS n, COALESCE(SUM(points),0) AS s "
                    "FROM eco_energy_records "
                    "GROUP BY role_key ORDER BY n DESC"
                ).fetchall()
            energy_breakdown = [dict(r) for r in breakdown_rows]

            # ===== 树种数量 =====
            row = conn.execute("SELECT COUNT(*) AS n FROM eco_tree_species").fetchone()
            tree_species = row["n"] if row else 0

            # ===== 植树证书（数量、消耗能量、不同树种兑换数 = 树种多样性）======
            # 注意：eco_certificates 表用 owner 列存钱包，不是 wallet
            cert_filter = (" WHERE owner = ?" if wallet else "")
            cert_params = (wallet,) if wallet else ()
            row = conn.execute(
                "SELECT COUNT(*) AS n, "
                "COALESCE(SUM(cost_energy),0) AS s, "
                "COUNT(DISTINCT species_id) AS distinct_trees "
                "FROM eco_certificates" + cert_filter,
                cert_params
            ).fetchone()
            certificates = row["n"] if row else 0
            cert_cost_total = row["s"] if row else 0
            cert_distinct_species = row["distinct_trees"] if row else 0

            # ===== 勋章 & 骑行券 =====
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM eco_badges WHERE badge_type='badge'" +
                (" AND owner = ?" if wallet else ""),
                wallet_params if wallet else ()
            ).fetchone()
            badges = row["n"] if row else 0
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM eco_badges WHERE badge_type='voucher'" +
                (" AND owner = ?" if wallet else ""),
                wallet_params if wallet else ()
            ).fetchone()
            vouchers = row["n"] if row else 0

            # ===== 三个合约是否部署过 =====
            eco_contracts = {}
            for cname in ("GreenEnergy", "PlantCertificate", "EcoBadge"):
                row = conn.execute(
                    "SELECT address FROM deployed_contracts WHERE name=? ORDER BY created_at DESC LIMIT 1",
                    (cname,),
                ).fetchone()
                eco_contracts[cname] = {"deployed": bool(row), "address": row["address"] if row else ""}

            # ===== 操作日志统计 =====
            if wallet:
                log = conn.execute(
                    "SELECT COUNT(*) AS total, "
                    "COALESCE(SUM(CASE WHEN level='error' THEN 1 ELSE 0 END),0) AS ec, "
                    "COALESCE(SUM(CASE WHEN level='warn' THEN 1 ELSE 0 END),0) AS wc, "
                    "COALESCE(SUM(CASE WHEN level='success' THEN 1 ELSE 0 END),0) AS sc "
                    "FROM eco_operation_logs WHERE wallet = ?",
                    (wallet,)
                ).fetchone()
            else:
                log = conn.execute(
                    "SELECT COUNT(*) AS total, "
                    "COALESCE(SUM(CASE WHEN level='error' THEN 1 ELSE 0 END),0) AS ec, "
                    "COALESCE(SUM(CASE WHEN level='warn' THEN 1 ELSE 0 END),0) AS wc, "
                    "COALESCE(SUM(CASE WHEN level='success' THEN 1 ELSE 0 END),0) AS sc "
                    "FROM eco_operation_logs"
                ).fetchone()
            log_total = log["total"] if log else 0
            log_errors = log["ec"] if log else 0
            log_warns = log["wc"] if log else 0
            log_success = log["sc"] if log else 0
            log_error_rate = round((log_errors / log_total) * 100, 2) if log_total else 0.0

            # ===== 学习质量维度 H：搭链教程进度 & 耗时分布（探索型学生奖励）======
            try:
                if wallet:
                    t_rows = conn.execute(
                        "SELECT step, done, output, started_at, finished_at "
                        "FROM chain_tutorial_progress WHERE wallet = ? ORDER BY step",
                        (wallet,)
                    ).fetchall()
                else:
                    t_rows = conn.execute(
                        "SELECT step, done, output, started_at, finished_at "
                        "FROM chain_tutorial_progress ORDER BY step"
                    ).fetchall()
            except Exception:
                t_rows = []
            total_steps = 10
            done_steps = [r["step"] for r in t_rows if r["done"]]
            failed_steps = [r["step"] for r in t_rows if r["done"] == 0 and (r["output"] or "").strip()]
            # 耗时统计（unix 秒）
            durations: list[int] = []
            for r in t_rows:
                if r["started_at"] and r["finished_at"]:
                    s = _parse_ts_any(r["started_at"])
                    e = _parse_ts_any(r["finished_at"])
                    if s and e and e > s:
                        durations.append(int(e - s))
            total_duration_sec = int(sum(durations))
            # 耗时分布：<5min 速成党 / 5~15min 正常 / 15~30min 深入探索 / >30min 困难党
            if total_duration_sec <= 0 and (done_steps or failed_steps):
                dur_tag = "unknown"
            elif total_duration_sec < 5 * 60:
                dur_tag = "cram"     # 速成
            elif total_duration_sec <= 15 * 60:
                dur_tag = "normal"   # 正常
            elif total_duration_sec <= 30 * 60:
                dur_tag = "explore"  # 探索
            else:
                dur_tag = "struggle" # 困难
            progress = {
                "total_steps": total_steps,
                "done_count": len(done_steps),
                "failed_count": len(failed_steps),
                "done_steps": done_steps,
                "failed_steps": failed_steps,
                "percent": round((len(done_steps) / total_steps) * 100, 1) if total_steps else 0.0,
                "durations_sec": durations,
                "total_duration_sec": total_duration_sec,
                "duration_tag": dur_tag,
            }

            # ===== 综合拓展题 I：学习行为埋点（真学 vs 刷点）======
            beh = {
                "ide_open_builtin": 0,   # ≥3 次 +2
                "ide_save_project_sol": 0,
                "contract_compile_ok": 0, # ≥1 次 +1
                "contract_compile_fail": 0,
                "interface_invoke": 0,    # ≥1 次 +2
            }
            try:
                if wallet:
                    b_rows = conn.execute(
                        "SELECT event_type, COUNT(*) AS n FROM learning_events "
                        "WHERE wallet = ? AND event_type IN "
                        "('ide_open_builtin','ide_save_project','contract_compile_ok','contract_compile_fail','interface_invoke') "
                        "GROUP BY event_type",
                        (wallet,)
                    ).fetchall()
                else:
                    b_rows = conn.execute(
                        "SELECT event_type, COUNT(*) AS n FROM learning_events "
                        "WHERE event_type IN "
                        "('ide_open_builtin','ide_save_project','contract_compile_ok','contract_compile_fail','interface_invoke') "
                        "GROUP BY event_type"
                    ).fetchall()
                for r in b_rows:
                    if r["event_type"] == "ide_save_project":
                        beh["ide_save_project_sol"] = int(r["n"])
                    else:
                        beh[r["event_type"]] = int(r["n"])
            except Exception:
                # learning_events 表可能在旧 DB 中不存在（埋点新表），不影响主流程
                pass

            # 最近的错误/警告（最多 20 条）
            if wallet:
                log_rows = conn.execute(
                    "SELECT * FROM eco_operation_logs WHERE level IN ('warn','error') AND wallet = ? "
                    "ORDER BY id DESC LIMIT 20",
                    (wallet,)
                ).fetchall()
            else:
                log_rows = conn.execute(
                    "SELECT * FROM eco_operation_logs WHERE level IN ('warn','error') "
                    "ORDER BY id DESC LIMIT 20"
                ).fetchall()

        return {
            # 角色 & 切换
            "role_wallets": role_wallets,
            "role_switches": role_switches,
            "distinct_roles": distinct_roles,                       # V2：E项 = 体验过多少 UNIQUE 角色
            # 能量
            "energy_issues": energy_issues,
            "energy_total": energy_total,
            "energy_distinct_roles": energy_distinct_roles,         # V2：F项核心 = 发放过的角色多样性
            "energy_breakdown": energy_breakdown,                   # V2：每种角色发放了多少次
            # 树种 & 证书
            "tree_species": tree_species,
            "certificates": certificates,
            "cert_cost_total": cert_cost_total,
            "cert_distinct_species": cert_distinct_species,         # V2：G项 = 兑换了多少不同树种
            # 勋章/券
            "badges": badges,
            "vouchers": vouchers,
            # 合约激活
            "contracts": eco_contracts,
            # 操作日志 + 错误率（V2：用于 H 项"探索型学生"和"学习质量扣分阈值"）
            "logs": {
                "total": log_total,
                "error_count": log_errors,
                "warn_count": log_warns,
                "success_count": log_success,
                "error_rate": log_error_rate,
                "recent_issues": [dict(r) for r in log_rows],
            },
            # 学习质量 V2：搭链进度 + 耗时分布
            "tutorial_progress": progress,
            # 综合拓展 V2：行为埋点（学生"真学"的证据）
            "behavior": beh,
        }
    except Exception as e:
        return {
            "role_wallets": 0, "role_switches": 0, "distinct_roles": 0,
            "energy_issues": 0, "energy_total": 0,
            "energy_distinct_roles": 0, "energy_breakdown": [],
            "tree_species": 0, "certificates": 0, "cert_cost_total": 0,
            "cert_distinct_species": 0,
            "badges": 0, "vouchers": 0,
            "contracts": {
                "GreenEnergy": {"deployed": False, "address": ""},
                "PlantCertificate": {"deployed": False, "address": ""},
                "EcoBadge": {"deployed": False, "address": ""},
            },
            "logs": {"total": 0, "error_count": 0, "warn_count": 0,
                     "success_count": 0, "error_rate": 0.0, "recent_issues": []},
            "tutorial_progress": {
                "total_steps": 10, "done_count": 0, "failed_count": 0,
                "done_steps": [], "failed_steps": [], "percent": 0.0,
                "durations_sec": [], "total_duration_sec": 0, "duration_tag": "unknown",
            },
            "behavior": {
                "ide_open_builtin": 0, "ide_save_project_sol": 0,
                "contract_compile_ok": 0, "contract_compile_fail": 0, "interface_invoke": 0,
            },
            "_eco_error": f"{type(e).__name__}: {e}",
        }


def _suggestions(
    contract_count: int,
    std_breakdown: dict,
    tx_count: int,
    nft_count: int,
    nft_trade_count: int,
    success_rate: float,
    eco: dict,
) -> list[dict]:
    """智能纠错 & 下一步学习建议（V2：对齐新 9 维度评分模型）。"""
    sgs: list[dict] = []
    contracts = eco.get("contracts") or {}
    beh = eco.get("behavior") or {}
    prog = eco.get("tutorial_progress") or {}
    logs = eco.get("logs") or {}

    # ================= A. 合约部署（20分）建议 =================
    if contract_count == 0:
        sgs.append({"priority": 1, "level": "error", "category": "A 合约部署",
                    "title": "尚未部署任何合约（A 项 20 分 0/20）",
                    "action": "进入『合约 IDE』，选择模板 ERC20，点击『编译 & 部署』即可获得 A 项 +10 分。",
                    "gain": "+10",
                    "knowledge": "ERC20 代币标准 / constructor / mint 函数"})
    else:
        missing_std = [std for std in ("ERC20", "ERC721", "ERC1155") if (std_breakdown.get(std) or 0) == 0]
        if missing_std:
            gain_remain = min(10, 3 if "ERC20" in missing_std else 0
                              + 3 if "ERC721" in missing_std else 0
                              + 4 if "ERC1155" in missing_std else 0)
            sgs.append({
                "priority": 2, "level": "warn", "category": "A 合约部署",
                "title": f"缺少 {missing_std} 协议的合约体验（A 项协议分布加分未拿满）",
                "action": f"依次部署 {', '.join(missing_std)}，ERC20 +3、ERC721 +3、ERC1155 +4，A 项合计 20 封顶。",
                "gain": f"+A ≤+{gain_remain}",
                "knowledge": "/".join(missing_std) + " 标准核心接口与差异"
            })

    # ================= B. 链上交易（15分）建议 =================
    if tx_count < 10:
        tier_target = 10 if tx_count >= 5 else 5 if tx_count >= 2 else 2 if tx_count >= 1 else 1
        tier_gain = {10: 15, 5: 10, 2: 5, 1: 2, 0: 0}[10] - ({10: 15, 5: 10, 2: 5, 1: 2, 0: 0}.get(tx_count, 0) if tx_count >= 10 else (10 if tx_count >= 5 else (5 if tx_count >= 2 else (2 if tx_count >= 1 else 0))))
        sgs.append({
            "priority": 2, "level": "warn", "category": "B 链上交易",
            "title": f"链上交易笔数不足（{tx_count}/10），B 项 15 分拿不满",
            "action": "在『ERC20 钱包』里多做几笔代币转账，或在合约管理中多次调用 state-change 函数，满 10 笔 15 分。",
            "gain": f"+B +{tier_gain}",
            "knowledge": "交易结构：nonce / gasPrice / gasLimit / to / value / data / vrs"
        })

    # ================= C. NFT 铸造与交易（10分）建议 =================
    if nft_count < 1:
        sgs.append({"priority": 3, "level": "warn", "category": "C NFT 铸造",
                    "title": "尚未铸造任何 NFT（C 项铸造 +5 未拿）",
                    "action": "进入『NFT 交易市场』，上传一张图片并铸造 1 件 ERC721。",
                    "gain": "+C +5",
                    "knowledge": "ERC721 ownerOf / safeTransferFrom / tokenURI 元数据模式"})
    elif nft_trade_count < 1:
        sgs.append({"priority": 4, "level": "info", "category": "C NFT 交易",
                    "title": "铸造了 NFT 但尚未发生市场交易（C 项交易 +5 未拿）",
                    "action": "把刚铸造的 NFT 上架定价，再用另一个钱包购买完成一次交易流转。",
                    "gain": "+C +5",
                    "knowledge": "NFT 一级/二级市场、撮合交易、授权 approve / setApprovalForAll"})

    # ================= D. 搭链教程（10分 + 探索加分）建议 =================
    dc_done = prog.get("done_count") or 0
    dc_total = prog.get("total_steps") or 10
    dc_fail = prog.get("failed_count") or 0
    if dc_done < dc_total:
        step_gain = 0 if dc_done >= 10 else (6 if dc_done >= 5 else 2 if dc_done >= 1 else 0)
        next_gain = 10 - step_gain
        sgs.append({
            "priority": 1, "level": "error", "category": "D 搭链教程",
            "title": f"搭链教程进度 {dc_done}/{dc_total}（必修 10 分当前约 {step_gain}/10）",
            "action": f"进入『云桌面·搭链教程』，按顺序执行剩余 {dc_total - dc_done} 步；遇到错误不用怕，保留失败记录会获得 D 项额外的「探索型学生」+1~3 加分。",
            "gain": f"+D +{next_gain}（再加探索 ≤+3）",
            "knowledge": "PBFT 共识 / 4 节点落盘 / 证书签发 / 节点启动 / SDK 接入"
        })
    if dc_fail == 0 and dc_done >= 3:
        sgs.append({"priority": 5, "level": "info", "category": "D 搭链探索",
                    "title": "尚未触发任何搭链失败场景（未拿到探索加分 ≤+3）",
                    "action": "可以故意在第 4 步改个端口/错误路径触发一次失败，体验 PBFT 节点异常诊断；失败 1 次 +1、失败 2 次 +2、≥3 次 +3（D 项合计 ≤10+3=13 不超 D 项 full 值 10，额外分纳入 I 项建议说明）。",
                    "gain": "探索 ≤+3（计入 D 项质量分）",
                    "knowledge": "共识失败 / 证书过期 / 端口冲突 / 节点宕机等生产事故 80% 的根因"})

    # ================= E. 角色与节点体验（10分，多样性）建议 =================
    dr = eco.get("distinct_roles") or 0
    if dr < 6:
        sgs.append({
            "priority": 2, "level": "warn", "category": "E 角色体验",
            "title": f"仅体验了 {dr}/6 种联盟链节点角色（E 项多样性 10 分需体验至少 4 种拿 8 分，6 种 10 分）",
            "action": "依次切换：管理员 / 地铁 / 公交 / 共享单车 / 外卖平台 / 回收公司。至少 4 种即可拿 8 分；体验满 6 种 +10 分。",
            "gain": f"+E +{max(0, 10 - (10 if dr >= 6 else 8 if dr >= 4 else 5 if dr >= 2 else 2 if dr >= 1 else 0))}",
            "knowledge": "联盟链 PBFT 共识：2f+1 个节点共同签名才能最终确认（f=容错节点数）"
        })

    # ================= F. 能量发放多样性（10分）建议 =================
    edr = eco.get("energy_distinct_roles") or 0
    ei = eco.get("energy_issues") or 0
    if edr < 3:
        next_gain = 10 - (10 if edr >= 3 else 6 if edr >= 2 else 3 if ei >= 3 and edr >= 1 else 0)
        sgs.append({
            "priority": 2, "level": "warn", "category": "F 能量发放",
            "title": f"能量发放多样性不足（{edr}/3 种角色发放过，当前 F {10-next_gain}/10）",
            "action": "至少用 3 种不同角色各自发放一次能量，例如 地铁→公交→单车 组合发放，F 项直接 +10 满分。",
            "gain": f"+F +{next_gain}",
            "knowledge": "ERC20 mint 权限控制：onlyMintController modifier / RBAC 多角色签名"
        })
    elif ei < 3:
        sgs.append({"priority": 4, "level": "info", "category": "F 能量发放",
                    "title": f"发放能量总次数仅 {ei} 次（建议 ≥3 次更能体现真实业务量）",
                    "action": "继续用外卖平台 / 回收公司等角色多发放几次，确保生态里有足够的能量供后续兑换。",
                    "gain": "为 G 项前置准备",
                    "knowledge": "代币发行的商业节奏：冷启动 → 分发 → 激励 → 价值承载 → 回收"})

    # ================= G. 资产兑换多样性（15分）建议 =================
    # 7.1 树种
    if eco.get("tree_species", 0) == 0:
        sgs.append({"priority": 3, "level": "warn", "category": "G 资产兑换",
                    "title": "管理员尚未上架树种（G-1 8 分无法开始）",
                    "action": "切到『管理员』角色 → 植树证书管理 → 新增至少 2 个树种（例：银杏 1000 能量 / 水杉 1500 能量）。",
                    "gain": "G 项前置条件",
                    "knowledge": '数字资产发行的"商品主数据"：SKU / 定价 / 库存 / 生命周期'})
    # 7.2 证书多样性
    elif eco.get("certificates", 0) == 0:
        sgs.append({"priority": 2, "level": "error", "category": "G 资产兑换",
                    "title": "尚未兑换植树证书（G-1 8 分；2+ 树种可拿满 8 分）",
                    "action": f"管理员已上架 {eco.get('tree_species',0)} 个树种。切换到能量较高的角色（如回收公司 1 次 +100）攒能量 ≥1000，兑换至少 2 种不同树种拿满 8 分。",
                    "gain": "+G 8",
                    "knowledge": 'ERC721 数字藏品的"发行-持有-流转-核销"生命周期'})
    else:
        cds = eco.get("cert_distinct_species") or 0
        if cds < 2:
            sgs.append({"priority": 3, "level": "info", "category": "G 资产兑换",
                        "title": f"仅兑换了 {cds} 种树种的证书（多样性 G-1 满需 2 种 +8）",
                        "action": f"用另一种树种再兑换一张证书（当前有 {eco.get('tree_species',0)} 个树种可挑），多体验不同定价档位。",
                        "gain": "+G 剩余 +{4 if cds<2 else 0}",
                        "knowledge": "NFT SKU 定价差异 / 批量发行 / 稀有度策略"})
    # 7.3 勋章/骑行券
    bd = eco.get("badges", 0)
    vc = eco.get("vouchers", 0)
    if bd == 0 or vc == 0:
        gaction = ""
        if bd == 0 and vc == 0:
            gaction = "勋章和骑行券都没有。建议 1000 能量先换 1 枚碳减排先锋勋章（EcoBadge token_id=1），再 20 能量换 1 张骑行券（token_id=2）。"
        elif bd == 0:
            gaction = "骑行券已持有，还缺勋章。攒 1000 能量换勋章。"
        else:
            gaction = "勋章已持有，还缺骑行券。20 能量即可兑换一张骑行券。"
        sgs.append({"priority": 3, "level": "warn", "category": "G 资产兑换",
                    "title": f"勋章/骑行券兑换不齐（G-2 4 分：两类都有才满）",
                    "action": gaction,
                    "gain": "+G +{4 if (bd>=1 and vc>=1) else 2 if (bd>=1 or vc>=1) else 4}",
                    "knowledge": "ERC1155 多批次同质化/半同质化：同合约存多 token_id，省 Gas"})
    # 7.4 能量发放多样性加分（G-3 = 发放角色 ≥4 种 +3）
    if (eco.get("certificates", 0) >= 1) and edr < 4:
        sgs.append({"priority": 5, "level": "info", "category": "G 商业闭环",
                    "title": f"能量发放角色 {edr}/4，G-3 额外 +3 分未拿（发放过 ≥4 种角色即满分）",
                    "action": "除 地铁/公交/单车 之外，再用 外卖平台 和 回收公司 各发一次能量，凑齐 4 种真实角色体验。",
                    "gain": "+G +3",
                    "knowledge": "多角色联合治理 — 真实 FISCO/长安链 等生产联盟链的治理结构"})

    # ================= H. 合约激活完整度（5分）建议 =================
    deploy_n = sum(1 for cname in ("GreenEnergy", "PlantCertificate", "EcoBadge")
                   if (contracts.get(cname) or {}).get("deployed"))
    if deploy_n < 3:
        missing_c = [c for c in ("GreenEnergy", "PlantCertificate", "EcoBadge")
                     if not (contracts.get(c) or {}).get("deployed")]
        hgain = {3: 5, 2: 2, 1: 1, 0: 0}[3] - {3: 5, 2: 2, 1: 1, 0: 0}[deploy_n]
        sgs.append({
            "priority": 1, "level": "error", "category": "H 合约激活",
            "title": f"生态合约未完全激活（{deploy_n}/3），缺少 {missing_c}（H 项 {5-hgain}/5）",
            "action": "进入『合约管理』→ 选择系统内置模板，依次部署 GreenEnergy、PlantCertificate、EcoBadge，满 3 份 +5。",
            "gain": f"+H +{hgain}",
            "knowledge": "ERC20 / ERC721 / ERC1155 三代币协同的多资产架构"
        })

    # ================= I. 综合拓展题（行为埋点 = 真学 5 分） =================
    i_open = beh.get("ide_open_builtin", 0) or 0
    i_compile = beh.get("contract_compile_ok", 0) or 0
    i_call = beh.get("interface_invoke", 0) or 0
    i1_got = (2 if i_open >= 3 else 0) + (1 if i_compile >= 1 else 0)
    i2_got = 2 if i_call >= 1 else 0
    if i1_got < 3:
        sgs.append({
            "priority": 5, "level": "info", "category": "I 拓展·真学",
            "title": f"I-1 合约源码学习加分 {i1_got}/3 分（看源码 {i_open}/3，真实编译 {i_compile}/1）",
            "action": "去『合约管理 → 内置合约』点开 ERC20/ERC721/GreenEnergy 至少看 3 份源码，再在『合约 IDE』里点一次真实 solc 编译，I-1 拿满 3 分。",
            "gain": f"+I {3 - i1_got}",
            "knowledge": "Solidity 编译原理：AST 解析 → solc → bytecode / ABI / devdoc"
        })
    if i2_got < 2:
        sgs.append({
            "priority": 5, "level": "info", "category": "I 拓展·真学",
            "title": f"I-2 接口调试加分 {i2_got}/2 分（尚未调用 ABI 接口）",
            "action": "『接口调试』选一份已部署合约，点一个 mint/transfer/balanceOf 函数执行一次即可拿 I-2 +2。",
            "gain": "+I +2",
            "knowledge": "ABI JSON-RPC 调用：eth_call / eth_sendRawTransaction 与 ABI encode/decode"
        })

    # ================= 错误/警告扣分建议 =================
    if logs.get("error_count", 0) >= 3:
        ep = min(10, logs.get("error_count", 0))
        sgs.append({"priority": 1, "level": "error", "category": "扣分",
                    "title": f"错误操作较多（{logs.get('error_count',0)} 次，已扣 -{ep} 分）",
                    "action": "向下滚动查看『操作错误与异常分析』，逐条点开错误详情；错误大多来自'权限未选 / 参数不全 / 能量不足'，先完成前置条件再操作。",
                    "gain": f"+{ep}（避免下一次重复扣分）",
                    "knowledge": "合约 Debug 三板斧：事件日志 / require 错误字符串 / 单步 Remix Debugger"})
    if logs.get("warn_count", 0) >= 5:
        wp = min(5, int(logs.get("warn_count", 0) * 3 // 10))
        sgs.append({"priority": 4, "level": "warn", "category": "扣分",
                    "title": f"警告次数偏高（{logs.get('warn_count',0)} 次，已扣 -{wp} 分）",
                    "action": "警告通常是前置条件不满足（例如：还没选角色就点发放能量）。先切换角色 → 再执行动作，可显著降低警告。",
                    "gain": f"+{wp}（避免下一次重复扣分）",
                    "knowledge": "前端 UI 前置校验：按钮 disabled / 引导提示 / 步骤锁"})

    # ================= 优秀：全拿满分恭喜 =================
    if not sgs:
        sgs.append({
            "priority": 9, "level": "success", "category": "总体",
            "title": "卓越！A~I 九项全部达标，学习质量维度也拿到了探索加分",
            "action": "下一步挑战：① 多钱包跨角色转账；② 自己写一个新的高级实战场景（供应链金融/司法存证）；③ 进入合约安全 CTF 挑战 Reentrancy 漏洞。",
            "gain": "进阶 L5 合约安全审计 / 架构师路径",
            "knowledge": "跨角色协作、复杂 DApp 架构、智能合约安全审计"
        })

    sgs.sort(key=lambda x: (x["priority"], x.get("level", "")))
    return sgs


def _calc_score(
    contract_count: int,
    std_breakdown: dict,
    tx_count: int,
    nft_count: int,
    nft_trade_count: int,
    success_rate: float,
    eco: dict,
) -> dict[str, Any]:
    """
    服务端评分 V2：返回分项得分 + 总分 + 等级 + 智能建议。
    满分 100 = 基础模块 55 (A~D) + 高级实战 40 (E~H) + 综合拓展 5 (I)。

    【A~D 基础模块 55 分】
      A 合约部署 20 分：≥1份+10；ERC20+3；ERC721+3；ERC1155+4；上限20
      B 链上交易 15 分：≥10笔15；≥5笔10；≥2笔5；≥1笔2
      C NFT 铸造与交易 10 分：铸造≥1件+5；交易≥1笔+5
      D 搭链教程(必修) 10 分：10/10→10；≥5/10→6；≥1/10→2； 失败尝试 +1~3(仍≤10)

    【E~H 高级实战 40 分】(绿色低碳联盟链)
      E 角色与节点体验 10 分：6/6→10；≥4→8；≥2→5；≥1→2
      F 能量发放多样性 10 分：3 种角色→10；2 种→6；1 种且≥3次→3
      G 资产兑换多样性 15 分：证书 8 + 勋章/券 4 + 发放角色≥4 +3
      H 生态合约激活完整度 5 分：3/3→5；2/3→2；1/3→1

    【I 综合拓展 5 分】(行为埋点 = 学生真学的证据)
      I-1 IDE 阅读源码≥3次 +2；真实编译≥1次 +1（合计≤3）
      I-2 接口调试≥1次 +2

    【扣分】error -1/次（≤10），warn -0.3/次（≤5），合计≤15
    """
    breakdown: list[dict[str, Any]] = []
    contracts = eco.get("contracts") or {}
    beh = eco.get("behavior") or {}
    prog = eco.get("tutorial_progress") or {}
    logs = eco.get("logs") or {}

    # ====== A 合约部署 20 ======
    a = 0
    if contract_count >= 1:
        a += 10
    if (std_breakdown.get("ERC20") or 0) >= 1:
        a += 3
    if (std_breakdown.get("ERC721") or 0) >= 1:
        a += 3
    if (std_breakdown.get("ERC1155") or 0) >= 1:
        a += 4
    a = min(20, a)
    breakdown.append({
        "id": "A", "section": "基础模块", "name": "合约部署",
        "full": 20, "score": a,
        "rule": "≥1份合约+10；ERC20/ERC721/ERC1155分布+3/3/4",
    })

    # ====== B 链上交易 15 ======
    if tx_count >= 10:
        b = 15
    elif tx_count >= 5:
        b = 10
    elif tx_count >= 2:
        b = 5
    elif tx_count >= 1:
        b = 2
    else:
        b = 0
    breakdown.append({
        "id": "B", "section": "基础模块", "name": "链上交易",
        "full": 15, "score": b,
        "rule": "≥10笔15；≥5笔10；≥2笔5；≥1笔2",
    })

    # ====== C NFT 铸造与交易 10 ======
    c = 0
    if nft_count >= 1:
        c += 5
    if nft_trade_count >= 1:
        c += 5
    breakdown.append({
        "id": "C", "section": "基础模块", "name": "NFT铸造与交易",
        "full": 10, "score": c,
        "rule": "铸造≥1件+5；交易≥1笔+5",
    })

    # ====== D 搭链教程(必修+学习质量) 10 ======
    dc_done = int(prog.get("done_count") or 0)
    dc_fail = int(prog.get("failed_count") or 0)
    dur_tag = prog.get("duration_tag") or "unknown"
    err_rate = float(logs.get("error_rate") or 0.0)
    if dc_done >= 10:
        d = 10
    elif dc_done >= 5:
        d = 6
    elif dc_done >= 1:
        d = 2
    else:
        d = 0
    # 探索型学生加分（失败尝试 1~3 次 = +1~3，但 D 项仍封顶 10）
    explore = min(3, dc_fail)
    d_with_bonus = min(10, d + explore)
    breakdown.append({
        "id": "D", "section": "基础模块·学习质量", "name": "搭链教程(必修)",
        "full": 10, "score": d_with_bonus,
        "rule": "10/10→10；≥5/10→6；≥1/10→2；失败尝试 +1~3(学习质量探索加分)",
        "quality": {
            "steps_done": dc_done,
            "steps_total": prog.get("total_steps", 10),
            "failed_attempts": dc_fail,
            "explore_bonus": explore,
            "duration_tag": dur_tag,
            "operation_error_rate": err_rate,
        },
    })

    # ====== E 角色与节点体验 10 ======
    dr = int(eco.get("distinct_roles") or 0)
    if dr >= 6:
        e = 10
    elif dr >= 4:
        e = 8
    elif dr >= 2:
        e = 5
    elif dr >= 1:
        e = 2
    else:
        e = 0
    breakdown.append({
        "id": "E", "section": "高级实战", "name": "角色与节点体验",
        "full": 10, "score": e,
        "rule": f"6/6 角色→10；≥4→8；≥2→5；≥1→2（实际体验 {dr}/6）",
    })

    # ====== F 能量发放多样性 10 ======
    edr = int(eco.get("energy_distinct_roles") or 0)
    ei = int(eco.get("energy_issues") or 0)
    if edr >= 3:
        f = 10
    elif edr >= 2:
        f = 6
    elif edr >= 1 and ei >= 3:
        f = 3
    else:
        f = 0
    breakdown.append({
        "id": "F", "section": "高级实战", "name": "能量发放多样性",
        "full": 10, "score": f,
        "rule": f"3 种角色→10；2 种→6；1 种且≥3 次→3（实际 {edr} 种 / 累计发放 {ei} 次）",
    })

    # ====== G 资产兑换多样性 15 ======
    certs = int(eco.get("certificates") or 0)
    cds = int(eco.get("cert_distinct_species") or 0)
    bd = int(eco.get("badges") or 0)
    vc = int(eco.get("vouchers") or 0)
    g1 = 0
    if certs >= 1:
        g1 = 8 if cds >= 2 else 4
    g2 = 0
    if bd >= 1 and vc >= 1:
        g2 = 4
    elif bd >= 1 or vc >= 1:
        g2 = 2
    g3 = 3 if edr >= 4 else 0
    g = min(15, g1 + g2 + g3)
    breakdown.append({
        "id": "G", "section": "高级实战", "name": "资产兑换多样性",
        "full": 15, "score": g,
        "rule": f"植树证书 +{g1}(2+树种/1树种)；勋章+骑行券 +{g2}；发放角色≥4 种 +{g3}",
        "detail": {"cert_score": g1, "badges_voucher_score": g2, "diversity_bonus": g3},
    })

    # ====== H 生态合约激活完整度 5 ======
    deployed_count = sum(1 for cname in ("GreenEnergy", "PlantCertificate", "EcoBadge")
                         if (contracts.get(cname) or {}).get("deployed"))
    h = {3: 5, 2: 2, 1: 1, 0: 0}.get(deployed_count, 0)
    breakdown.append({
        "id": "H", "section": "高级实战", "name": "生态合约激活完整度",
        "full": 5, "score": h,
        "rule": f"3/3→5；2/3→2；1/3→1（已部署 {deployed_count}/3）",
    })

    # ====== I 综合拓展·真学指标 5（行为埋点） ======
    i_open = int(beh.get("ide_open_builtin") or 0)
    i_save_sol = int(beh.get("ide_save_project_sol") or 0)
    i_compile_ok = int(beh.get("contract_compile_ok") or 0)
    i_compile_fail = int(beh.get("contract_compile_fail") or 0)
    i_call = int(beh.get("interface_invoke") or 0)
    i1 = min(3, (2 if (i_open + i_save_sol) >= 3 else 0) + (1 if i_compile_ok >= 1 else 0))
    i2 = 2 if i_call >= 1 else 0
    i = i1 + i2
    breakdown.append({
        "id": "I", "section": "综合拓展·真学", "name": "源码阅读 / 编译 / 接口调试",
        "full": 5, "score": i,
        "rule": f"读源码≥3 +2；真实编译≥1 +1；接口调试≥1 +2",
        "behavior": {
            "ide_read": i_open + i_save_sol,
            "compile_ok": i_compile_ok,
            "compile_fail": i_compile_fail,
            "interface_invoke": i_call,
        },
    })

    # ====== 扣分项 ======
    total_before = sum(int(x.get("score") or 0) for x in breakdown)
    err_n = int(logs.get("error_count") or 0)
    warn_n = int(logs.get("warn_count") or 0)
    err_penalty = min(10, err_n)
    warn_penalty = min(5, warn_n * 3 // 10)
    penalty_total = min(15, err_penalty + warn_penalty)
    if penalty_total > 0:
        breakdown.append({
            "id": "P", "section": "扣分", "name": "操作错误扣分",
            "full": 0, "score": -penalty_total,
            "rule": f"error -{err_penalty}(最多10)；warn -{warn_penalty}(最多5)；合计最多-15",
        })
    final = max(0, total_before - penalty_total)

    # 等级
    if final >= 90:
        level = "优秀 🏆"
    elif final >= 75:
        level = "良好 🥈"
    elif final >= 60:
        level = "合格 ✅"
    elif final >= 40:
        level = "待完善 🚧"
    else:
        level = "未完成 ❌"

    base_score = a + b + c + d_with_bonus  # A~D
    eco_score = e + f + g + h              # E~H
    expand_score = i                        # I

    return {
        "total": final,
        "total_before_penalty": total_before,
        "penalty": penalty_total,
        "error_penalty": err_penalty,
        "warn_penalty": warn_penalty,
        "level": level,
        "breakdown": breakdown,
        "base_score": base_score,    # A~D 满分 55
        "base_full": 55,
        "eco_score": eco_score,      # E~H 满分 40
        "eco_full": 40,
        "expand_score": expand_score,  # I 满分 5
        "expand_full": 5,
        "quality_dimension": {
            "tutorial_duration_tag": dur_tag,
            "operation_error_rate": float(err_rate),
            "tutorial_explore_bonus": explore,
            "tutorial_fail_attempts": dc_fail,
            "tutorial_progress": f"{dc_done}/{prog.get('total_steps',6)}",
            "behavior_read_compile_invoke": f"读源码 {i_open+i_save_sol} · 编译 {i_compile_ok}/{i_compile_ok+i_compile_fail} · 接口 {i_call}",
        },
    }


def _aggregate_data(wallet: str = "") -> dict[str, Any]:
    """聚合实训报告所有数据（搭链进度、合约、交易、NFT、高级实战、评分）。
    
    V3：支持 per-wallet 过滤（wallet 非空时仅统计该钱包数据）。
    """
    c = get_chain_client()
    height = c.block_number()
    
    # 构建钱包过滤条件
    wallet_filter = ""
    wallet_params = ()
    if wallet:
        wallet_filter = " WHERE from_addr = ? OR to_addr = ?"
        wallet_params = (wallet, wallet)
    
    # 获取交易列表（按钱包过滤）
    if wallet:
        txs = c.list_txs(5000, from_addr=wallet)
    else:
        txs = c.list_txs(5000)

    # 已部署合约
    with get_conn() as conn:
        if wallet:
            contracts = conn.execute(
                "SELECT address, name, standard, deployer, created_at, tx_hash "
                "FROM deployed_contracts WHERE deployer = ? ORDER BY created_at DESC",
                (wallet,)
            ).fetchall()
            std_rows = conn.execute(
                "SELECT COUNT(*) AS n, standard FROM deployed_contracts WHERE deployer = ? GROUP BY standard",
                (wallet,)
            ).fetchall()
        else:
            contracts = conn.execute(
                "SELECT address, name, standard, deployer, created_at, tx_hash "
                "FROM deployed_contracts ORDER BY created_at DESC"
            ).fetchall()
            std_rows = conn.execute(
                "SELECT COUNT(*) AS n, standard FROM deployed_contracts GROUP BY standard"
            ).fetchall()

    contract_list = [dict(r) for r in contracts]
    for item in contract_list:
        if "created_at" in item:
            item["deployed_at"] = _parse_ts_any(item.get("created_at"))
    std_breakdown = {r["standard"] or "自定义": r["n"] for r in std_rows}
    contract_count = sum(std_breakdown.values())

    # 交易统计
    tx_count = len(txs)
    total_gas = sum(getattr(t, "gas_used", 0) or 0 for t in txs)
    gas_avg = int(total_gas / tx_count) if tx_count > 0 else 0
    status_ok = sum(1 for t in txs if getattr(t, "status", 1) == 1)
    success_rate = round((status_ok / tx_count) * 100, 1) if tx_count else 0

    # 最近10笔交易
    recent_txs = []
    for t in txs[-10:]:
        d = t.__dict__
        recent_txs.append({
            "hash": str(d.get("hash", ""))[:16] + "...",
            "from": (str(d.get("from_addr") or ""))[:12],
            "to": (str(d.get("to_addr") or "合约创建"))[:12],
            "value": d.get("value", 0),
            "gas": d.get("gas_used", 0),
            "time": datetime.fromtimestamp(int(d.get("timestamp", 0) or 0)).strftime("%H:%M:%S") if d.get("timestamp") else "-",
        })
    recent_txs.reverse()

    # NFT 统计
    try:
        with get_conn() as conn:
            if wallet:
                nft_count = (conn.execute(
                    "SELECT COUNT(*) AS n FROM nfts WHERE author = ?", (wallet,)
                ).fetchone())["n"]
                nft_trade_count = (conn.execute(
                    "SELECT COUNT(*) AS n FROM nft_trades WHERE from_addr = ? OR to_addr = ?",
                    (wallet, wallet)
                ).fetchone())["n"]
            else:
                nft_count = (conn.execute("SELECT COUNT(*) AS n FROM nfts").fetchone())["n"]
                nft_trade_count = (conn.execute("SELECT COUNT(*) AS n FROM nft_trades").fetchone())["n"]
    except Exception:
        nft_count = 0
        nft_trade_count = 0

    # ERC20 余额 TOP 5（按钱包过滤）
    try:
        with get_conn() as conn:
            if wallet:
                bal_rows = conn.execute(
                    "SELECT wallet, token_address, balance FROM wallet_balances "
                    "WHERE wallet = ? ORDER BY CAST(balance AS REAL) DESC LIMIT 5",
                    (wallet,)
                ).fetchall()
            else:
                bal_rows = conn.execute(
                    "SELECT wallet, token_address, balance FROM wallet_balances "
                    "ORDER BY CAST(balance AS REAL) DESC LIMIT 5"
                ).fetchall()
        top_balances = [dict(r) for r in bal_rows]
    except Exception:
        top_balances = []

    # 高级实战数据（传入钱包参数）
    eco = _load_eco_brief(wallet)

    # 服务端自动评分
    score = _calc_score(
        contract_count=contract_count,
        std_breakdown=std_breakdown,
        tx_count=tx_count,
        nft_count=nft_count,
        nft_trade_count=nft_trade_count,
        success_rate=success_rate,
        eco=eco,
    )
    # 智能纠错建议
    suggestions = _suggestions(
        contract_count=contract_count,
        std_breakdown=std_breakdown,
        tx_count=tx_count,
        nft_count=nft_count,
        nft_trade_count=nft_trade_count,
        success_rate=success_rate,
        eco=eco,
    )
    score["suggestions"] = suggestions

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "chain_mode": get_chain_mode_label(),
        "chain_height": height,
        "contract_count": contract_count,
        "contract_list": contract_list,
        "standard_breakdown": std_breakdown,
        "tx_count": tx_count,
        "total_gas": total_gas,
        "gas_avg": gas_avg,
        "success_rate": success_rate,
        "recent_txs": recent_txs,
        "nft_count": nft_count,
        "nft_trade_count": nft_trade_count,
        "top_balances": top_balances,
        "eco": eco,
        "score": score,
    }


@router.get("/aggregate")
def report_aggregate(x_wallet: Optional[str] = Header(default=None, alias="X-Wallet")):
    """前端展示用的报告聚合数据。任何异常都被包装成 JSON，不抛 500/404。"""
    # 行为埋点：学生查看实训报告（对应 alliance_gov 维度的 report_view 指标）
    wallet = x_wallet or ""
    _track("report_view", target="aggregate", wallet=wallet)
    try:
        data = _aggregate_data(wallet)
        # 闭环：报告生成时自动为学生创建/更新成绩草稿
        if wallet:
            _auto_draft_grade(wallet)
        return data
    except Exception as e:  # pragma: no cover - 兜底
        import traceback as _tb
        err = f"{type(e).__name__}: {e}"
        return {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "chain_mode": get_chain_mode_label(),
            "chain_height": 0,
            "contract_count": 0,
            "contract_list": [],
            "standard_breakdown": {},
            "tx_count": 0,
            "total_gas": 0,
            "gas_avg": 0,
            "success_rate": 0,
            "recent_txs": [],
            "nft_count": 0,
            "nft_trade_count": 0,
            "top_balances": [],
            "eco": _load_eco_brief(wallet),
            "score": {"total": 0, "level": "数据异常", "breakdown": []},
            "error_msg": err,
            "error_trace": _tb.format_exc(limit=6),
        }


def _auto_draft_grade(wallet: str):
    """报告生成时自动为学生创建/更新成绩草稿（打通 report→grades）。"""
    try:
        from .grades import _compute_training_score, _compute_final
        w = wallet.strip()
        if not w:
            return
        sid = f"W{w[:10]}"
        sname = f"学生_{w[:6]}"
        ts = now()
        training_score, detail = _compute_training_score(w)
        detail_json = json.dumps(detail, ensure_ascii=False)
        final_score = _compute_final(training_score, 0)
        with get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM student_grades WHERE student_id=? AND course=?",
                (sid, "区块链实训"),
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE student_grades
                       SET wallet=?, training_score=?, final_score=?,
                           training_detail=?, updated_at=?
                       WHERE id=?""",
                    (w, training_score, final_score, detail_json, ts, existing["id"]),
                )
            else:
                conn.execute(
                    """INSERT INTO student_grades
                       (student_id, student_name, course, score, wallet,
                        training_score, final_score, training_detail,
                        teacher_id, teacher_name, class_id, school_id, remark,
                        created_at, updated_at)
                       VALUES (?, ?, ?, 0, ?, ?, ?, ?, 'system', '系统自动', '', '', '实训报告自动生成草稿', ?, ?)""",
                    (sid, sname, "区块链实训", w, training_score, final_score, detail_json, ts, ts),
                )
    except Exception:
        # 不影响报告生成主流程
        pass


@router.get("/wallet/{wallet}")
def report_by_wallet(wallet: str, x_wallet: Optional[str] = Header(default=None, alias="X-Wallet")):
    """按钱包地址生成个人实训报告（per-wallet 聚合）。
    
    用于学生端查看自己的实训成绩和报告，数据仅包含该钱包的活动。
    """
    wallet_clean = wallet.strip()
    if not wallet_clean:
        return {"error": "钱包地址不能为空"}
    
    # 行为埋点：学生查看个人报告
    _track("report_view", target=f"wallet:{wallet_clean[:10]}...", wallet=wallet_clean)
    
    try:
        data = _aggregate_data(wallet_clean)
        data["wallet"] = wallet_clean
        data["is_personal_report"] = True
        return data
    except Exception as e:
        import traceback as _tb
        err = f"{type(e).__name__}: {e}"
        return {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "wallet": wallet_clean,
            "is_personal_report": True,
            "chain_mode": get_chain_mode_label(),
            "chain_height": 0,
            "contract_count": 0,
            "contract_list": [],
            "standard_breakdown": {},
            "tx_count": 0,
            "total_gas": 0,
            "gas_avg": 0,
            "success_rate": 0,
            "recent_txs": [],
            "nft_count": 0,
            "nft_trade_count": 0,
            "top_balances": [],
            "eco": _load_eco_brief(wallet_clean),
            "score": {"total": 0, "level": "暂无数据", "breakdown": []},
            "error_msg": err,
            "error_trace": _tb.format_exc(limit=6),
        }


def _render_markdown(d: dict[str, Any]) -> str:
    """把聚合数据渲染成一份完整的 Markdown 实训报告（含评分与错误分析）。"""
    lines: list[str] = []
    score = d.get("score") or {}
    eco = d.get("eco") or {}
    sb = score.get("breakdown") or []

    lines.append("# 区块链实训报告")
    lines.append("")
    lines.append(f"> 生成时间：{d['generated_at']}  ")
    lines.append(f"> 实训环境：{d['chain_mode']}  ")
    lines.append(f"> 当前块高：{d['chain_height']}  ")
    lines.append(f"> 综合评分：**{score.get('total', 0)} / 100**  ")
    lines.append(f"> 成绩等级：{score.get('level', '-')}")
    lines.append("")

    # 一、实训概览
    lines.append("## 一、实训概览")
    lines.append("")
    lines.append("### 1.1 核心指标")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("| --- | --- |")
    lines.append(f"| 已部署合约 | **{d['contract_count']}** 份 |")
    lines.append(f"| 链上交易总数 | **{d['tx_count']}** 笔 |")
    lines.append(f"| 累计 Gas 消耗 | **{d['total_gas']:,}** |")
    lines.append(f"| 平均 Gas / 笔 | **{d['gas_avg']:,}** |")
    lines.append(f"| 交易成功率 | **{d['success_rate']}%** |")
    lines.append(f"| 铸造 NFT 数量 | **{d['nft_count']}** 件 |")
    lines.append(f"| NFT 交易次数 | **{d['nft_trade_count']}** 次 |")
    lines.append("")

    lines.append("### 1.2 学习路径 9 阶段（按推荐顺序推进）")
    lines.append("")
    prog = eco.get("tutorial_progress") or {}
    beh = eco.get("behavior") or {}
    contracts = eco.get("contracts") or {}
    bd_d = int(prog.get("done_count") or 0)
    bd_t = int(prog.get("total_steps") or 10)
    miss_std = sum(1 for s in ("ERC20", "ERC721", "ERC1155") if (d.get("standard_breakdown") or {}).get(s, 0) <= 0)
    cc = d.get("contract_count", 0)
    i_open = int(beh.get("ide_open_builtin") or 0) + int(beh.get("ide_save_project_sol") or 0)
    i_cmp = int(beh.get("contract_compile_ok") or 0)
    i_call = int(beh.get("interface_invoke") or 0)
    txc = d.get("tx_count", 0)
    nftc = d.get("nft_count", 0)
    nfttc = d.get("nft_trade_count", 0)
    dc = sum(1 for cname in ("GreenEnergy", "PlantCertificate", "EcoBadge")
             if (contracts.get(cname) or {}).get("deployed"))
    dr = int(eco.get("distinct_roles") or 0)
    edr = int(eco.get("energy_distinct_roles") or 0)
    certs = int(eco.get("certificates") or 0)
    cds = int(eco.get("cert_distinct_species") or 0)
    bdgs = int(eco.get("badges") or 0)
    vchs = int(eco.get("vouchers") or 0)
    def _chk(v: bool): return "✅" if v else "⬜"
    steps = [
        ("L1 搭链教程 (D)", f"{bd_d}/{bd_t} 步", bd_d >= bd_t),
        ("L2 合约部署 (A)", f"{cc} 份 · 缺标准 {miss_std}/3", cc >= 1 and miss_std == 0),
        ("L3 接口调试·真学 (I)", f"读源码 {i_open} · 编译 {i_cmp} · 调接口 {i_call}", i_open >= 3 and i_cmp >= 1 and i_call >= 1),
        ("L4 ERC20 交易 (B)", f"{txc} 笔交易（≥10 满 15 分）", txc >= 10),
        ("L5 NFT 铸造与交易 (C)", f"铸 {nftc} · 成交 {nfttc}", nftc >= 1 and nfttc >= 1),
        ("L6 激活 3 份生态合约 (H)", f"{dc}/3 已部署（GreenEnergy/PlantCertificate/EcoBadge）", dc >= 3),
        ("L7 6 角色体验 (E)", f"{dr}/6 角色", dr >= 6),
        ("L8 能量发放多样性 (F)", f"{edr} 种角色发放（≥3 满 10 分）", edr >= 3),
        ("L9 资产兑换多样性 (G)", f"证 {certs}({cds}种) · 勋 {bdgs} · 券 {vchs}", certs >= 1 and cds >= 2 and bdgs >= 1 and vchs >= 1),
    ]
    lines.append("| # | 阶段 | 当前状态 | 完成 |")
    lines.append("| --- | --- | --- | --- |")
    for i, (n, s, ok) in enumerate(steps, 1):
        lines.append(f"| {i} | {n} | {s} | {_chk(ok)} |")
    lines.append("")
    done_n = sum(1 for _, _, ok in steps if ok)
    lines.append(f"> 当前学习进度：**{done_n}/9 阶段** 完成。建议按上表 L1→L9 顺序依次推进，基础→进阶→综合拓展。")
    lines.append("")

    # 二、综合评分明细
    lines.append("## 二、综合评分明细（V2 满分 100）")
    lines.append("")
    lines.append("### 2.1 学习质量维度")
    lines.append("")
    q = score.get("quality_dimension") or {}
    if q:
        lines.append("| 质量指标 | 数值 |")
        lines.append("| --- | --- |")
        lines.append(f"| 搭链教程进度 | {q.get('tutorial_progress','-')} |")
        lines.append(f"| 搭链耗时分布（学习节奏） | {q.get('tutorial_duration_tag','unknown')} |")
        lines.append(f"| 搭链失败尝试次数（探索加分） | +{q.get('tutorial_explore_bonus',0)} 分（失败 {q.get('tutorial_fail_attempts',0)} 次） |")
        lines.append(f"| 操作错误率 | {float(q.get('operation_error_rate') or 0.0):.1f} % |")
        lines.append(f"| 真学行为（源码·编译·接口） | {q.get('behavior_read_compile_invoke','-')} |")
        lines.append("")
    lines.append("### 2.2 分项得分表")
    lines.append("")
    lines.append("| 编号 | 模块 | 项目 | 满分 | 得分 | 规则 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for item in sb:
        lines.append(
            f"| {item['id']} | {item['section']} | {item['name']} | {item['full']} | "
            f"**{item['score']}** | {item['rule']} |"
        )
    lines.append("")
    lines.append(
        f"- 基础模块得分（A~D）：**{score.get('base_score', 0)} / {score.get('base_full', 55)}**"
    )
    lines.append(
        f"- 高级实战得分（E~H）：**{score.get('eco_score', 0)} / {score.get('eco_full', 40)}**"
    )
    lines.append(
        f"- 综合拓展·真学得分（I）：**{score.get('expand_score', 0)} / {score.get('expand_full', 5)}**"
    )
    lines.append(
        f"- 扣分合计：**-{score.get('penalty', 0)}**（error -{score.get('error_penalty',0)}，warn -{score.get('warn_penalty',0)}，扣分上限 -15）"
    )
    lines.append(
        f"- **最终得分：{score.get('total', 0)} / 100 · {score.get('level', '-')}**"
    )
    lines.append("")

    # ==================== 按学习流程 L1→L9 分阶段叙述 ====================

    # 三、搭链教程进度（L1 · D 项 · 必修基础）
    lines.append("## 三、搭链教程进度（L1 · D 项 · 必修 10 分）")
    lines.append("")
    prog = eco.get("tutorial_progress") or {}
    bd_d = int(prog.get("done_count") or 0)
    bd_t = int(prog.get("total_steps") or 10)
    bd_fail = int(prog.get("failed_count") or 0)
    bd_pct = float(prog.get("percent") or 0)
    dur_tag = prog.get("duration_tag") or "unknown"
    dur_total = int(prog.get("total_duration_sec") or 0)
    done_steps = prog.get("done_steps") or []
    lines.append("| 指标 | 数值 |")
    lines.append("| --- | --- |")
    lines.append(f"| 搭链进度 | **{bd_d}/{bd_t} 步**（{bd_pct:.0f}%） |")
    lines.append(f"| 已完成步骤 | {' → '.join(str(x) for x in done_steps) if done_steps else '—'} |")
    lines.append(f"| 失败尝试次数 | {bd_fail} 次（失败 1~3 次可获探索型学生 +1~3 分，仍计入 D 项） |")
    lines.append(f"| 累计耗时 | {dur_total//60} 分 {dur_total%60} 秒 · 节奏标签：{dur_tag} |")
    lines.append("")
    if bd_d < bd_t:
        lines.append("- 🚧 建议：进入『云桌面·搭链教程』补齐剩余 %d 步；遇到报错不用怕，保留失败场景拿「探索加分」。" % (bd_t - bd_d))
    else:
        lines.append("✅ 搭链教程 10/10 全部完成，基础扎实！")
    if bd_fail == 0 and bd_d >= 3:
        lines.append("- 💡 探索加分提示：故意触发 1~3 次节点异常（端口冲突/证书过期），体验 PBFT 故障排查场景，可额外 +1~3 分计入 D 项。")
    lines.append("")

    # 四、合约部署情况（L2 · A 项 · 20 分）
    lines.append("## 四、合约部署情况（L2 · A 项 · 20 分）")
    lines.append("")
    if d["standard_breakdown"]:
        lines.append("### 4.1 协议分布")
        lines.append("")
        for std, n in d["standard_breakdown"].items():
            lines.append(f"- **{std}**：{n} 份")
        lines.append("")
    if d["contract_list"]:
        lines.append("### 4.2 合约清单")
        lines.append("")
        lines.append("| # | 合约名 | 标准 | 地址 | 部署时间 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for i, c in enumerate(d["contract_list"], 1):
            addr = c.get("address", "")
            short_addr = addr[:10] + "…" + addr[-6:] if len(addr) > 16 else addr
            ts = c.get("deployed_at", 0)
            t_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "-"
            lines.append(
                f"| {i} | {c.get('name','-')} | {c.get('standard') or '自定义'} | `{short_addr}` | {t_str} |"
            )
        lines.append("")
    miss_std = [s for s in ("ERC20", "ERC721", "ERC1155") if (d.get("standard_breakdown") or {}).get(s, 0) <= 0]
    if miss_std:
        lines.append(f"- ⚠️ 还缺少 {miss_std} 协议的合约体验（A 项协议分布加分未拿满），进入『合约 IDE』依次部署。")
    lines.append("")

    # 五、接口调试 / 真学行为埋点（L3 · I 项 · 综合拓展 5 分）
    lines.append("## 五、接口调试 / 真学行为埋点（L3 · I 项 · 综合拓展 5 分）")
    lines.append("")
    beh = eco.get("behavior") or {}
    i_open = int(beh.get("ide_open_builtin") or 0)
    i_save = int(beh.get("ide_save_project_sol") or 0)
    i_cmp = int(beh.get("contract_compile_ok") or 0)
    i_cmpf = int(beh.get("contract_compile_fail") or 0)
    i_call = int(beh.get("interface_invoke") or 0)
    lines.append("| 埋点指标 | 数值 | 说明 |")
    lines.append("| --- | --- | --- |")
    lines.append(f"| 打开内置合约源码 | {i_open} 次 | I-1 要求 ≥3 次（+2 分） |")
    lines.append(f"| 在 IDE 另存为项目 | {i_save} 次 | 与『打开源码』合计，≥3 次拿 I-1 +2 |")
    lines.append(f"| 真实 solc 编译成功 | {i_cmp} 次 | ≥1 次 I-1 再 +1 分（合计 I-1 满 3） |")
    lines.append(f"| 真实 solc 编译失败 | {i_cmpf} 次 | （可查看错误辅助学习） |")
    lines.append(f"| ABI 接口函数调用 | {i_call} 次 | ≥1 次 I-2 +2 分（满 2） |")
    lines.append("")
    need = []
    if i_open + i_save < 3:
        need.append("打开 ≥3 份内置合约源码（I-1 +2）")
    if i_cmp < 1:
        need.append("在 IDE 真实编译一次（I-1 +1）")
    if i_call < 1:
        need.append("在『接口调试』调用一次 mint/transfer/balanceOf 任意函数（I-2 +2）")
    if need:
        lines.append("- 🎯 下一步：" + "；".join(need))
    else:
        lines.append("✅ I 项综合拓展全部达标，真学证据完整！")
    lines.append("")

    # 六、ERC20 交易流水（L4 · B 项 · 15 分）
    lines.append("## 六、ERC20 交易流水（L4 · B 项 · 15 分）")
    lines.append("")
    lines.append(f"> 已完成 **{d['tx_count']} 笔** 交易：≥10 笔 = 15 分；≥5 笔 = 10；≥2 笔 = 5；≥1 笔 = 2")
    lines.append("")
    if d["recent_txs"]:
        lines.append("### 6.1 最近 10 笔交易")
        lines.append("")
        lines.append("| 时间 | From | To | 金额 | Gas |")
        lines.append("| --- | --- | --- | --- | --- |")
        for t in d["recent_txs"]:
            lines.append(f"| {t['time']} | `{t['from']}` | `{t['to']}` | {t['value']} | {t['gas']:,} |")
        lines.append("")
    if d["tx_count"] < 10:
        lines.append("- ⚠️ 交易笔数不足 10 笔：进入『ERC20 钱包』多做几笔转账/授权，B 项很快就能拿满 15 分。")
    lines.append("")

    # 七、NFT 铸造与交易（L5 · C 项 · 10 分）
    lines.append("## 七、NFT 铸造与交易（L5 · C 项 · 10 分）")
    lines.append("")
    lines.append("| 指标 | 数值 | 得分 |")
    lines.append("| --- | --- | --- |")
    lines.append(f"| 铸造 NFT | **{d['nft_count']}** 件 | ≥1 件 +5 分 |")
    lines.append(f"| NFT 交易（购买/成交） | **{d['nft_trade_count']}** 次 | ≥1 笔 +5 分 |")
    lines.append("")
    if d["nft_count"] == 0:
        lines.append("- 🚧 尚未铸造 NFT：进入『NFT 交易市场』上传一张图片，点『铸造』即可 +5。")
    elif d["nft_trade_count"] == 0:
        lines.append("- 💡 已铸造但缺交易：把 NFT 上架定价，用另一个钱包『购买』完成一次流转，C 项 +5 拿满。")
    else:
        lines.append("✅ C 项 10/10 分完成，ERC721 一级发行 & 二级流通都体验啦！")
    lines.append("")

    # 八、高级实战 · 绿色低碳联盟链（L6~L9 · H→E→F→G 顺序）
    lines.append("## 八、高级实战 · 绿色低碳联盟链（L6~L9 · H→E→F→G）")
    lines.append("")
    lines.append("### 8.1 (L6 / H) 激活 3 份生态合约（满分 5）")
    lines.append("")
    contracts = eco.get("contracts") or {}
    for cname in ("GreenEnergy", "PlantCertificate", "EcoBadge"):
        info = contracts.get(cname) or {}
        addr = info.get("address", "")
        if info.get("deployed") and addr:
            short = addr[:10] + "…" + addr[-6:] if len(addr) > 16 else addr
            lines.append(f"- ✅ **{cname}**：已部署 · 地址 `{short}`")
        else:
            lines.append(f"- 🔒 **{cname}**：未部署")
    dc = sum(1 for cname in ("GreenEnergy", "PlantCertificate", "EcoBadge")
             if (contracts.get(cname) or {}).get("deployed"))
    if dc < 3:
        lines.append(f"- ⚠️ 生态合约未完全激活（{dc}/3）：进入『合约管理』→ 内置模板 → 依次部署 GreenEnergy / PlantCertificate / EcoBadge，满 3 = +5 分。")
    else:
        lines.append("- ✅ H 项 5/5 · 3 份生态合约全部激活！")
    lines.append("")

    lines.append("### 8.2 (L7 / E) 6 角色节点体验（满分 10）")
    lines.append("")
    dr = int(eco.get("distinct_roles") or 0)
    role_wallets = int(eco.get("role_wallets") or 0)
    role_switches = int(eco.get("role_switches") or 0)
    lines.append(f"- 已体验角色数：**{dr} / 6**（6 角色满 = +10；≥4 = +8；≥2 = +5；≥1 = +2）")
    lines.append(f"- 角色钱包绑定：{role_wallets} 个 · 切换角色次数：{role_switches} 次")
    lines.append("- 6 角色推荐顺序：`管理员 → 地铁 → 公交 → 共享单车 → 外卖平台 → 回收公司`")
    if dr < 6:
        lines.append("- ⚠️ 还有 %d 个角色未体验，依次切换每个角色至少发一次能量，E 项快速加分。" % (6 - dr))
    else:
        lines.append("✅ E 项 10/10 · 完整 PBFT 多角色联合治理体验！")
    lines.append("")

    lines.append("### 8.3 (L8 / F) 能量发放多样性（满分 10）")
    lines.append("")
    edr = int(eco.get("energy_distinct_roles") or 0)
    ei = int(eco.get("energy_issues") or 0)
    et = int(eco.get("energy_total") or 0)
    lines.append(f"- 发放角色多样性：**{edr} 种** · 发放次数：{ei} 次 · 累计能量：{et:,} 点")
    lines.append("- 评分规则：≥3 种 = +10；≥2 种 = +6；1 种且 ≥3 次 = +3")
    eb = eco.get("energy_breakdown") or []
    if eb:
        lines.append("")
        lines.append("| 发放角色 | 次数 | 累计能量 |")
        lines.append("| --- | --- | --- |")
        for it in eb:
            lines.append(f"| {it.get('role','-')} | {it.get('count',0)} 次 | {int(it.get('total',0)):,} 点 |")
    lines.append("")
    if edr < 3:
        lines.append("- ⚠️ 能量发放角色不足 3 种：至少用『地铁 / 公交 / 共享单车』各发 1 次，F 项直接 +10。")
    lines.append("")

    lines.append("### 8.4 (L9 / G) 资产兑换多样性（满分 15）")
    lines.append("")
    tree_s = int(eco.get("tree_species") or 0)
    certs = int(eco.get("certificates") or 0)
    cds = int(eco.get("cert_distinct_species") or 0)
    bdgs = int(eco.get("badges") or 0)
    vchs = int(eco.get("vouchers") or 0)
    g1 = 8 if (certs >= 1 and cds >= 2) else (4 if certs >= 1 else 0)
    g2 = 4 if (bdgs >= 1 and vchs >= 1) else (2 if (bdgs >= 1 or vchs >= 1) else 0)
    g3 = 3 if edr >= 4 else 0
    lines.append("| 子项 | 数值 | 得分 | 满分 |")
    lines.append("| --- | --- | --- | --- |")
    lines.append(f"| G-1 植树证书 | {certs} 张（{cds} 树种）· 树种上架 {tree_s} 种 | **{g1}** | 8 |")
    lines.append(f"| G-2 勋章+骑行券 | 勋章 {bdgs} 枚 · 骑行券 {vchs} 张 | **{g2}** | 4 |")
    lines.append(f"| G-3 发放角色≥4 | 发放角色 {edr} 种（≥4 才 +3） | **{g3}** | 3 |")
    lines.append(f"| **G 合计** |  | **{g1+g2+g3}** | **15** |")
    lines.append("")
    tips = []
    if tree_s < 2:
        tips.append("切到『管理员』新增 ≥2 个树种（G 前置条件）")
    if certs == 0:
        tips.append("攒能量 ≥1000，兑换植树证书（G-1 起算前提）")
    elif cds < 2:
        tips.append("再兑换 1 种不同树种拿 G-1 满 8 分")
    if bdgs == 0 or vchs == 0:
        tips.append("勋章 & 骑行券两类都要有（G-2 满 4 分）")
    if edr < 4 and certs >= 1:
        tips.append("发放角色扩到 ≥4 种（外卖平台 & 回收公司），G-3 +3")
    if tips:
        for t in tips:
            lines.append(f"- 🎯 {t}")
    else:
        lines.append("✅ G 项 15/15 满！完美完成资产兑换全链路闭环。")
    lines.append("")

    # 八-B. 绿色实战阶段综合评估
    lines.append("### 8.5 阶段总评")
    lines.append("")
    if dr >= 6 and edr >= 4 and certs >= 1 and cds >= 2 and bdgs >= 1 and vchs >= 1 and dc == 3:
        lines.append("- ✅ **卓越！完整体验了全部高级实战场景（多角色 / 多发放 / 多资产 / 多合约）。**")
    else:
        lines.append("- 🔗 绿色实战链路：H(合约) → E(角色) → F(发放) → G(兑换)，建议按本节 L6→L7→L8→L9 顺序补齐缺失环节。")
    lines.append("")

    # 九、操作错误与异常分析
    logs = eco.get("logs") or {}
    lines.append("## 九、操作错误与异常分析")
    lines.append("")
    lines.append("| 类型 | 数量 |")
    lines.append("| --- | --- |")
    lines.append(f"| 成功记录 (success) | {logs.get('success_count',0)} |")
    lines.append(f"| 警告记录 (warn) | {logs.get('warn_count',0)} |")
    lines.append(f"| 错误记录 (error) | {logs.get('error_count',0)} |")
    lines.append(f"| 日志总数 | {logs.get('total',0)} |")
    lines.append("")
    issues = logs.get("recent_issues") or []
    if issues:
        lines.append("### 9.1 最近 20 条异常记录")
        lines.append("")
        lines.append("| # | 模块 | 动作 | 级别 | 消息 | 时间 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for i, it in enumerate(issues, 1):
            ts = _parse_ts_any(it.get("created_at"))
            t_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "-"
            msg = (it.get("message") or "").replace("|", "｜")
            lines.append(f"| {i} | {it.get('module','-')} | {it.get('action','-')} | "
                         f"{it.get('level','-')} | {msg} | {t_str} |")
        lines.append("")

    # 十、Token 余额 TOP 5
    lines.append("## 十、Token 余额 TOP 5")
    lines.append("")
    if d["top_balances"]:
        lines.append("| 钱包 | 合约地址 | 余额 |")
        lines.append("| --- | --- | --- |")
        for b in d["top_balances"]:
            addr = b.get("token_address", "")
            short = addr[:10] + "…" + addr[-6:] if len(addr) > 16 else addr
            lines.append(f"| `{b.get('wallet','')[:12]}` | `{short}` | {b.get('balance',0)} |")
        lines.append("")

    # 十一、学习建议与提升路径（智能纠错建议）
    sgs = score.get("suggestions") or []
    lines.append("## 十一、学习建议与提升路径（智能推荐）")
    lines.append("")
    lines.append("> 建议按学习路径 L1→L9 顺序执行：搭链教程 → 合约部署 → 接口调试 → ERC20交易 → NFT → 激活生态合约 → 角色 → 发放 → 兑换")
    lines.append("")
    if sgs:
        lines.append("| 优先级 | 类别 | 级别 | 问题诊断 | 下一步怎么做 | 预计提升 | 对应知识点 |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        level_map = {"error": "🔴 必改", "warn": "🟡 建议", "success": "🟢 优秀", "info": "ℹ️ 提示"}
        for s in sgs:
            lvl = s.get("level", "info")
            lines.append(
                f"| P{s.get('priority', '?')} | {s.get('category', '-')} | {level_map.get(lvl, lvl)} | "
                f"{s.get('title', '-')} | {s.get('action', '-')} | {s.get('gain', '-')} | {s.get('knowledge', '-')} |"
            )
    else:
        lines.append("_所有知识点掌握扎实，无待优化项。_")
    lines.append("")

    # 十二、实训结论
    lines.append("## 十二、实训结论")
    lines.append("")
    if score.get("total", 0) >= 90:
        lines.append("- 🏆 实训完成度极高，扎实掌握了合约开发、ERC 标准、链上交易与高级联合治理场景。")
    elif score.get("total", 0) >= 75:
        lines.append("- 🥈 实训完成度良好，基础模块掌握扎实，建议进一步完善高级实战场景体验。")
    elif score.get("total", 0) >= 60:
        lines.append("- ✅ 实训合格，建议补做高级实战的能量发放与资产兑换环节。")
    else:
        lines.append("- 🚧 实训尚未完成，请按学习路径 L1→L9 依次推进：『云桌面·搭链教程』10 步 → 合约 IDE 部署 → 接口调试 → ERC20 钱包交易 → NFT 市场铸造交易 → 激活 3 份生态合约 → 6 角色 → 能量发放 → 资产兑换。")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("_本报告由区块链实训平台自动生成（服务端评分 + 智能纠错，杜绝前端篡改）_")
    return "\n".join(lines)


@router.get("/download")
def report_download(format: str = "md", x_wallet: Optional[str] = Header(default=None, alias="X-Wallet")):
    """下载实训报告，支持 md / json。"""
    # 行为埋点：学生下载实训报告
    _track("report_view", target=f"download:{format}", wallet=x_wallet or "")
    data = _aggregate_data()
    if format.lower() == "json":
        body = json.dumps(data, ensure_ascii=False, indent=2)
        return Response(
            content=body,
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=report.json"},
        )
    # 默认 md
    md = _render_markdown(data)
    return PlainTextResponse(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=report.md"},
    )
