"""区块链浏览器 API（真实链数据 + ABI 参数解析 + ERC 识别）。"""
from __future__ import annotations

import json
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from ..chain_client import get_chain_client
from ..db import get_conn
from ..tx_decoder import decode_input_data, identify_standard_by_logs
from ..tenant import request_uid, scope_filter

router = APIRouter(prefix="/api/explorer", tags=["explorer"])


# 任务 #18 逐端点鉴权口径（optional 语义，详见各端点 docstring）：
#   - 查 DB 业务表（deployed_contracts / contract_calls，带 _TENANT_COLS）的端点：
#     登录 → 本人归属行 + 未登记旧行；未登录 → 仅未登记旧行（公共演示数据），
#     明确归属他人的私有行不可见（tenant.scope_filter 统一构造）；
#   - 纯链客户端数据（区块 / 交易 / 地址 / Gas / 性能）：保持公开 —— 联盟链
#     浏览器语义即全链公共视图，无 per-学生 归属。


def _load_contract_abi_map():
    """加载所有已部署合约的 {address: (name, abi, standard)} 映射。"""
    out = {}
    with get_conn() as conn:
        rows = conn.execute("SELECT address,name,abi,standard FROM deployed_contracts").fetchall()
    for r in rows:
        out[r["address"].lower()] = (r["name"], json.loads(r["abi"]), r["standard"])
    return out


def _enrich_tx(tx) -> dict:
    """把 Transaction 对象转为 dict 并用 ABI 解码 input data、识别事件。"""
    d = tx.__dict__
    # 若已有 method（来自链客户端记录），保留；否则尝试用 ABI 解码
    if not d.get("method") and d.get("input") and d["input"] != "0x":
        abi_map = _load_contract_abi_map()
        target = (d.get("to_addr") or "").lower()
        if target in abi_map:
            _, abi, _ = abi_map[target]
            decoded = decode_input_data(abi, d["input"])
            if decoded:
                d["method"] = decoded["method"]
                d["parsed_args"] = decoded["args"]
    # 事件识别
    if d.get("logs"):
        std = identify_standard_by_logs(d["logs"])
        if std:
            d["event_standard"] = std
    return d


@router.get("/overview")
def overview(request: Request):
    """总览：链上块高 / 交易公共；合约统计部分按租户 scope 过滤（optional）。"""
    c = get_chain_client()
    height = c.block_number()
    txs = c.list_txs(1000)
    cond, sp = scope_filter("deployed_contracts", request_uid(request))
    with get_conn() as conn:
        contracts = conn.execute(
            "SELECT COUNT(*) AS n, standard FROM deployed_contracts"
            + (" WHERE " + cond if cond else "")
            + " GROUP BY standard",
            sp,
        ).fetchall()
    contract_count = sum(r["n"] for r in contracts)
    std_breakdown = {r["standard"] or "自定义": r["n"] for r in contracts}
    # 近 7 日趋势
    from collections import Counter
    days = Counter()
    for t in txs:
        d = time.strftime("%Y-%m-%d", time.gmtime(t.timestamp))
        days[d] += 1
    trend = [{"date": d, "count": n} for d, n in sorted(days.items())]
    return {
        "height": height,
        "tx_count": len(txs),
        "contract_count": contract_count,
        "standard_breakdown": std_breakdown,
        "trend": trend,
    }


@router.get("/blocks")
def list_blocks(page: int = 1, size: int = 20):
    c = get_chain_client()
    height = c.block_number()
    start = max(0, height - page * size + 1)
    end = max(0, height - (page - 1) * size)
    blocks = c.list_blocks(start, end)
    return {"total": height + 1, "page": page, "size": size, "items": [b.__dict__ for b in blocks]}


@router.get("/blocks/{number}")
def get_block(number: int):
    c = get_chain_client()
    b = c.get_block(number)
    if not b:
        raise HTTPException(404, "block not found")
    txs = [_enrich_tx(t) for t in c.list_txs(1000) if t.block_number == number]
    d = b.__dict__
    d["transactions"] = txs
    return d


@router.get("/txs")
def list_txs(limit: int = 50, address: Optional[str] = None):
    c = get_chain_client()
    if address:
        txs = c.list_txs_by_address(address)
    else:
        txs = c.list_txs(limit)
    return {"items": [_enrich_tx(t) for t in txs]}


@router.get("/txs/{tx_hash}")
def get_tx(tx_hash: str):
    c = get_chain_client()
    t = c.get_tx(tx_hash)
    if not t:
        raise HTTPException(404, "tx not found")
    return _enrich_tx(t)


@router.get("/contracts")
def list_contracts(request: Request):
    """已部署合约列表：optional 鉴权 + 租户 scope 过滤（见文件头口径）。"""
    cond, sp = scope_filter("deployed_contracts", request_uid(request))
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT address,name,standard,deployer,tx_hash,created_at FROM deployed_contracts"
            + (" WHERE " + cond if cond else "")
            + " ORDER BY created_at DESC",
            sp,
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.get("/contracts/{address}")
def get_contract(address: str, request: Request):
    """合约详情（含调用记录）：optional 鉴权，主行与 calls 同租户 scope 过滤。"""
    cond, sp = scope_filter("deployed_contracts", request_uid(request))
    cond_c, sp_c = scope_filter("contract_calls", request_uid(request))
    with get_conn() as conn:
        r = conn.execute(
            "SELECT * FROM deployed_contracts WHERE address=?"
            + (" AND " + cond if cond else ""),
            (address, *sp),
        ).fetchone()
        calls = conn.execute(
            "SELECT * FROM contract_calls WHERE contract_address=?"
            + (" AND " + cond_c if cond_c else "")
            + " ORDER BY id DESC LIMIT 50",
            (address, *sp_c),
        ).fetchall()
    if not r:
        raise HTTPException(404, "contract not found")
    d = dict(r)
    d["abi"] = json.loads(d["abi"])
    d["calls"] = [dict(c) for c in calls]
    return d


@router.get("/address/{addr}")
def query_address(addr: str):
    c = get_chain_client()
    txs = c.list_txs_by_address(addr)
    with get_conn() as conn:
        contract = conn.execute(
            "SELECT address,name,standard FROM deployed_contracts WHERE address=?", (addr,)
        ).fetchone()
    return {
        "address": addr,
        "is_contract": contract is not None,
        "contract": dict(contract) if contract else None,
        "txs": [_enrich_tx(t) for t in txs],
        "tx_count": len(txs),
    }


# ==================== 方向一：Gas 分析 ====================
@router.get("/gas/analysis")
def gas_analysis(limit: int = 100):
    """Gas 消耗分析 - 近 N 笔交易的 Gas 统计。"""
    c = get_chain_client()
    txs = c.list_txs(limit)

    if not txs:
        return {
            "avg_gas_used": 0,
            "max_gas_used": 0,
            "min_gas_used": 0,
            "total_gas_cost_wei": 0,
            "total_gas_cost_gwei": 0,
            "avg_gas_price_gwei": 0,
            "tx_count": 0,
        }

    gas_used_list = [t.gas_used for t in txs]
    gas_cost_wei_list = [t.gas_cost_wei for t in txs]

    return {
        "avg_gas_used": sum(gas_used_list) // len(gas_used_list),
        "max_gas_used": max(gas_used_list),
        "min_gas_used": min(gas_used_list),
        "total_gas_cost_wei": sum(gas_cost_wei_list),
        "total_gas_cost_gwei": sum(gas_cost_wei_list) / 1e9,
        "avg_gas_price_gwei": 8.75,  # GAS_PRICE = 8750000000 wei = 8.75 gwei
        "tx_count": len(txs),
    }


@router.get("/gas/trend")
def gas_trend(hours: int = 24):
    """Gas 价格趋势（近 N 小时）。"""
    c = get_chain_client()
    txs = c.list_txs(500)
    now = int(time.time())
    cutoff = now - hours * 3600

    trend = []
    for t in txs:
        if t.timestamp >= cutoff:
            trend.append({
                "timestamp": t.timestamp,
                "gas_used": t.gas_used,
                "gas_price_gwei": 8.75,
                "gas_cost_gwei": t.gas_cost_gwei,
            })

    return {"trend": trend, "hours": hours}


# ==================== 方向二：代币经济分析 ====================
@router.get("/token/economics")
def token_economics(request: Request):
    """代币经济模型分析 - 流通量、持有者分布、交易趋势。

    ERC20 合约清单按租户 scope 过滤（optional）；链上事件统计公共。
    """
    c = get_chain_client()

    # 获取所有已部署的 ERC20 合约（scope 过滤：登录=本人+旧行，未登录=仅旧行）
    cond, sp = scope_filter("deployed_contracts", request_uid(request))
    with get_conn() as conn:
        erc20s = conn.execute(
            "SELECT address, name, standard FROM deployed_contracts WHERE standard='ERC20'"
            + (" AND " + cond if cond else ""),
            sp,
        ).fetchall()

    economics = []
    for erc20 in erc20s:
        addr = erc20["address"]
        name = erc20["name"]

        # 获取该代币的所有交易
        txs = [t for t in c.list_txs(1000) if t.to_addr and t.to_addr.lower() == addr.lower()]

        # 统计持有者分布（从 Transfer 事件解析）
        holders = {}
        transfer_count = 0
        for tx in txs:
            for log in tx.logs:
                # ERC20 Transfer 事件签名: 0xddf252ad...
                if len(log.get("topics", [])) >= 3 and log["topics"][0].startswith("0xddf252ad"):
                    transfer_count += 1
                    from_addr = "0x" + log["topics"][1][-40:] if len(log["topics"][1]) >= 40 else ""
                    to_addr = "0x" + log["topics"][2][-40:] if len(log["topics"][2]) >= 40 else ""

                    # 解码 amount
                    try:
                        from eth_abi import decode
                        amount = int(decode(["uint256"], bytes.fromhex(log["data"].replace("0x", "")))[0])
                    except:
                        amount = 0

                    # 更新余额
                    if from_addr:
                        holders[from_addr] = holders.get(from_addr, 0) - amount
                    if to_addr:
                        holders[to_addr] = holders.get(to_addr, 0) + amount

        # 过滤掉余额为 0 或负数的地址
        holders = {k: v for k, v in holders.items() if v > 0}
        total_supply = sum(holders.values())
        holder_count = len(holders)

        # 按余额排序
        sorted_holders = sorted(holders.items(), key=lambda x: x[1], reverse=True)[:10]

        economics.append({
            "contract_address": addr,
            "token_name": name,
            "total_supply": str(total_supply),
            "holder_count": holder_count,
            "transfer_count": transfer_count,
            "top_holders": [{"address": h[0], "balance": str(h[1])} for h in sorted_holders],
        })

    return {"tokens": economics}


# ==================== 方向二：数据一致性校验 ====================
@router.get("/data/consistency")
def data_consistency(request: Request):
    """数据一致性校验 - 链上数据与链下数据对比。

    校验对象（deployed_contracts 清单）按租户 scope 过滤（optional），
    学生仅校验自己可见的合约；块高连续性等链级校验公共。
    """
    c = get_chain_client()

    issues = []

    # 1. 检查已部署合约的代码是否存在（scope 过滤）
    cond, sp = scope_filter("deployed_contracts", request_uid(request))
    with get_conn() as conn:
        contracts = conn.execute(
            "SELECT address, name FROM deployed_contracts"
            + (" WHERE " + cond if cond else ""),
            sp,
        ).fetchall()

    for contract in contracts:
        addr = contract["address"]
        if not c.has_code(addr):
            issues.append({
                "type": "contract_code_missing",
                "severity": "high",
                "message": f"合约 {contract['name']} ({addr}) 在链上无代码",
            })

    # 2. 检查交易确认数
    current_block = c.block_number()
    recent_txs = c.list_txs(50)
    unconfirmed_txs = [t for t in recent_txs if t.confirmations < 6]
    if unconfirmed_txs:
        issues.append({
            "type": "low_confirmation_count",
            "severity": "medium",
            "message": f"有 {len(unconfirmed_txs)} 笔交易确认数不足 6 个区块",
            "details": [{"hash": t.hash, "confirmations": t.confirmations} for t in unconfirmed_txs[:5]],
        })

    # 3. 检查区块高度连续性
    blocks = c.list_blocks(max(0, current_block - 10), current_block)
    for i in range(len(blocks) - 1):
        if blocks[i].number - blocks[i + 1].number != 1:
            issues.append({
                "type": "block_gap",
                "severity": "high",
                "message": f"区块 {blocks[i+1].number} 和 {blocks[i].number} 之间存在间隙",
            })

    return {
        "status": "healthy" if not issues else "issues_found",
        "issue_count": len(issues),
        "issues": issues,
        "current_block": current_block,
        "contract_count": len(contracts),
        "tx_count": len(recent_txs),
    }


# ==================== 方向三：性能监控 ====================
@router.get("/performance/metrics")
def performance_metrics():
    """性能监控 - TPS、延迟、资源使用。"""
    c = get_chain_client()

    # 计算 TPS（近 100 笔交易）
    txs = c.list_txs(100)
    if len(txs) >= 2:
        time_span = txs[0].timestamp - txs[-1].timestamp
        tps = len(txs) / time_span if time_span > 0 else 0
    else:
        tps = 0

    # 计算平均出块时间
    blocks = c.list_blocks(max(0, c.block_number() - 20), c.block_number())
    if len(blocks) >= 2:
        block_times = [blocks[i].timestamp - blocks[i + 1].timestamp for i in range(len(blocks) - 1)]
        avg_block_time = sum(block_times) / len(block_times) if block_times else 0
    else:
        avg_block_time = 0

    # 计算平均交易延迟（Gas 使用率）
    avg_gas_used = sum(t.gas_used for t in txs) // len(txs) if txs else 0
    gas_limit = 8_000_000
    gas_utilization = (avg_gas_used / gas_limit * 100) if gas_limit > 0 else 0

    return {
        "tps": round(tps, 2),
        "avg_block_time": round(avg_block_time, 2),
        "avg_gas_used": avg_gas_used,
        "gas_utilization_percent": round(gas_utilization, 2),
        "current_block": c.block_number(),
        "pending_txs": 0,  # 联盟链通常无 pending
        "network_health": "healthy" if tps > 0 else "idle",
    }
