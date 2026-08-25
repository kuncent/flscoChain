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

# 联盟管理员钱包：新代币发行仅限该身份操作（治理闭环）
ADMIN_WALLET = "0xadmin"


class IssueReq(BaseModel):
    name: str
    symbol: str
    decimals: int = 18
    total_supply: str
    owner: str = "0xlearner"


@router.post("/issue")
def issue(req: IssueReq):
    """真实发行 ERC20：编译 ERC20.sol → EVM 部署（构造函数初始化总量）→ 记录。"""
    name = (req.name or "").strip()
    symbol = (req.symbol or "").strip()
    # 发币权限闭环：新代币发行是联盟治理行为，仅管理员钱包（0xadmin）可操作，
    # 避免学生随意发币造成账本混乱；学生可使用管理员发行的绿色能量参与生态流转
    owner = (req.owner or "").strip()
    if owner.lower() != ADMIN_WALLET:
        raise HTTPException(
            403,
            f"发行新代币仅限联盟管理员钱包（{ADMIN_WALLET}）操作，当前发行者 {owner or '未填写'}。"
            "请在页面右上角「当前操作钱包」切换为管理员身份后再发行",
        )
    # 发币限制：名称 / 符号 / 总量合法性校验
    if not name:
        raise HTTPException(400, "代币名称不能为空")
    if len(name) > 30:
        raise HTTPException(400, "代币名称过长：请控制在 30 个字符以内")
    if not symbol:
        raise HTTPException(400, "代币符号不能为空")
    if not (1 <= len(symbol) <= 8):
        raise HTTPException(400, "代币符号长度应为 1-8 个字符（如 GE / CARBON）")
    if not symbol.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(400, "代币符号仅支持字母 / 数字 / 中划线 / 下划线")
    if not (0 <= req.decimals <= 18):
        raise HTTPException(400, "代币精度 decimals 取值范围为 0-18")
    try:
        supply = int(req.total_supply)
    except (TypeError, ValueError):
        raise HTTPException(400, "发行总量必须为整数")
    if supply <= 0:
        raise HTTPException(400, "发行总量必须大于 0")
    if supply > 10 ** 12:
        raise HTTPException(400, "发行总量过大：上限 10^12（教学环境防溢出）")
    c = get_chain_client()
    src = (settings.contracts_dir / "ERC20.sol").read_text(encoding="utf-8")
    comp = compile_source(src)
    if not comp["ok"]:
        raise HTTPException(400, "编译失败: " + "; ".join(comp["errors"]))
    # 构造函数参数 (string name, string symbol, uint256 initialSupply)
    r = c.deploy_contract(
        name, comp["abi"], comp["bytecode"], src,
        req.owner, "ERC20",
        ctor_args=[name, symbol, supply],
    )
    addr = r["address"]
    with get_conn() as conn:
        conn.execute("DELETE FROM deployed_contracts WHERE address=?", (addr,))
        conn.execute(
            "INSERT INTO deployed_contracts(address,name,abi,bytecode,source,deployer,tx_hash,standard,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (addr, name, json.dumps(comp["abi"]), comp["bytecode"], src,
             req.owner, r["tx_hash"], "ERC20", now()),
        )
        conn.execute(
            "INSERT INTO tokens(address,name,symbol,decimals,total_supply,owner,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (addr, name, symbol, req.decimals, str(supply), req.owner, now()),
        )
        # 业务闭环：把钱包发行的合约源码登记进「合约 IDE」工程，
        # 保证 钱包发币 / 合约 IDE / 监听器 三处数据一致（测试反馈：监听器能看到但 IDE 看不到）
        pid = "wallet-issued"
        conn.execute(
            "INSERT INTO projects(id,name,created_at,updated_at,is_builtin) VALUES(?,?,?,?,0) "
            "ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at",
            (pid, "钱包发行代币", now(), now()),
        )
        conn.execute(
            "INSERT INTO project_files(id,project_id,path,content,updated_at) "
            "VALUES(?,?,?,?,?) ON CONFLICT(project_id,path) "
            "DO UPDATE SET content=excluded.content, updated_at=excluded.updated_at",
            (f"{pid}-{symbol}", pid, f"{name}_{symbol}.sol", src, now()),
        )
    return {"address": addr, "name": name, "symbol": symbol,
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
