"""区块链浏览器 API（真实链数据 + ABI 参数解析 + ERC 识别）。"""
from __future__ import annotations

import json
import time
from typing import Optional

from fastapi import APIRouter, HTTPException

from ..chain_client import get_chain_client
from ..db import get_conn
from ..tx_decoder import decode_input_data, identify_standard_by_logs

router = APIRouter(prefix="/api/explorer", tags=["explorer"])


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
def overview():
    c = get_chain_client()
    height = c.block_number()
    txs = c.list_txs(1000)
    with get_conn() as conn:
        contracts = conn.execute("SELECT COUNT(*) AS n, standard FROM deployed_contracts GROUP BY standard").fetchall()
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
def list_contracts():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT address,name,standard,deployer,tx_hash,created_at FROM deployed_contracts ORDER BY created_at DESC"
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.get("/contracts/{address}")
def get_contract(address: str):
    with get_conn() as conn:
        r = conn.execute("SELECT * FROM deployed_contracts WHERE address=?", (address,)).fetchone()
        calls = conn.execute(
            "SELECT * FROM contract_calls WHERE contract_address=? ORDER BY id DESC LIMIT 50", (address,)
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
