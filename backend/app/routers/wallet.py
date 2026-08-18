"""ERC20 钱包实践 API（真实 ERC20 部署 + 真实 transfer 调用）。"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..chain_client import get_chain_client
from ..db import get_conn, now
from ..tx_decoder import compile_source

router = APIRouter(prefix="/api/wallet", tags=["wallet"])


class IssueReq(BaseModel):
    name: str
    symbol: str
    decimals: int = 18
    total_supply: str
    owner: str = "0xlearner"


@router.post("/issue")
def issue(req: IssueReq):
    """真实发行 ERC20：编译 ERC20.sol → EVM 部署（构造函数初始化总量）→ 记录。"""
    c = get_chain_client()
    src = (settings.contracts_dir / "ERC20.sol").read_text(encoding="utf-8")
    comp = compile_source(src)
    if not comp["ok"]:
        raise HTTPException(400, "编译失败: " + "; ".join(comp["errors"]))
    # 构造函数参数 (string name, string symbol, uint256 initialSupply)
    r = c.deploy_contract(
        req.name, comp["abi"], comp["bytecode"], src,
        req.owner, "ERC20",
        ctor_args=[req.name, req.symbol, int(req.total_supply)],
    )
    addr = r["address"]
    with get_conn() as conn:
        conn.execute("DELETE FROM deployed_contracts WHERE address=?", (addr,))
        conn.execute(
            "INSERT INTO deployed_contracts(address,name,abi,bytecode,source,deployer,tx_hash,standard,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (addr, req.name, json.dumps(comp["abi"]), comp["bytecode"], src,
             req.owner, r["tx_hash"], "ERC20", now()),
        )
        conn.execute(
            "INSERT INTO tokens(address,name,symbol,decimals,total_supply,owner,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (addr, req.name, req.symbol, req.decimals, req.total_supply, req.owner, now()),
        )
    return {"address": addr, "name": req.name, "symbol": req.symbol,
            "tx_hash": r["tx_hash"], "block_number": r["block_number"], "gas_used": r.get("gas_used", 0)}


@router.get("/tokens")
def list_tokens():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM tokens ORDER BY created_at DESC").fetchall()
    return {"items": [dict(r) for r in rows]}


@router.get("/balance")
def balance(wallet: str, token_address: str):
    """真实查询 ERC20 balanceOf。"""
    c = get_chain_client()
    abi = _load_abi(token_address)
    try:
        r = c.call_contract(token_address, "balanceOf", [c.resolve_account(wallet)], wallet, abi)
        bal = r.get("result", "0") if r.get("ok") else "0"
    except Exception as e:
        bal = "0"
    return {"wallet": wallet, "token_address": token_address, "balance": str(bal)}


@router.get("/balances/{wallet}")
def balances(wallet: str):
    """查询钱包下所有 Token 真实余额（单个 token 失败不影响整体）。"""
    c = get_chain_client()
    with get_conn() as conn:
        rows = conn.execute("SELECT address,name,symbol,decimals FROM tokens").fetchall()
    items = []
    for row in rows:
        try:
            abi = _load_abi(row["address"])
            r = c.call_contract(row["address"], "balanceOf", [c.resolve_account(wallet)], wallet, abi)
            bal = r.get("result", "0") if r.get("ok") else "0"
        except Exception:
            bal = "0"
        items.append({
            "token_address": row["address"], "balance": str(bal),
            "name": row["name"], "symbol": row["symbol"], "decimals": row["decimals"],
        })
    return {"wallet": wallet, "items": items}


class TransferReq(BaseModel):
    token_address: str
    from_addr: str
    to_addr: str
    amount: str


@router.post("/transfer")
def transfer(req: TransferReq):
    """真实 ERC20 transfer 调用。"""
    c = get_chain_client()
    abi = _load_abi(req.token_address)
    r = c.call_contract(req.token_address, "transfer",
                        [c.resolve_account(req.to_addr), int(req.amount)],
                        req.from_addr, abi)
    if not r.get("ok"):
        raise HTTPException(400, r.get("error", "transfer failed"))
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO wallet_transfers(token_address,from_addr,to_addr,amount,tx_hash,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (req.token_address, req.from_addr, req.to_addr, req.amount, r.get("tx_hash", ""), now()),
        )
    return {"ok": True, "tx_hash": r.get("tx_hash", ""), "gas_used": r.get("gas_used", 0),
            "block_number": r.get("block_number", 0)}


@router.get("/transfers/{wallet}")
def transfers(wallet: str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM wallet_transfers WHERE from_addr=? OR to_addr=? ORDER BY id DESC",
            (wallet, wallet),
        ).fetchall()
    return {"wallet": wallet, "items": [dict(r) for r in rows]}


def _load_abi(address: str):
    with get_conn() as conn:
        r = conn.execute("SELECT abi FROM deployed_contracts WHERE address=?", (address,)).fetchone()
    return json.loads(r["abi"]) if r else []
