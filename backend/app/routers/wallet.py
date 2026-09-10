"""ERC20 钱包实践 API（真实 ERC20 部署 + 真实 transfer 调用）。"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..alliance_contracts import ENERGY_TOKEN_NAME, ENERGY_TOKEN_SYMBOL
from ..config import settings
from ..chain_client import get_chain_client
from ..db import get_conn, now
from ..learning.alliance_roles import TREASURY_WALLET, wallet_address
from ..security import assert_actor_wallet, get_current_user
from ..tx_decoder import compile_source
from ..wallet_id import short as short_wallet
# 绿色能量余额统一口径（账本为事实源 + 链上余额与待同步差额）：钱包页与联盟页
# 过去各自取一个口径（一个读链上 balanceOf、一个读能量流水），同一个人两个页面
# 两个余额；现在只留 `_energy_balance_view` 一个入口。
from .eco import _energy_balance_view

router = APIRouter(prefix="/api/wallet", tags=["wallet"])

# 联盟管理员钱包：新代币发行仅限该身份操作（治理闭环）。
# ADMIN_WALLET 是密钥库**别名**（仅用于文案与链上签名），资产与接口口径是它的真实地址。
ADMIN_WALLET = TREASURY_WALLET


def admin_wallet_ids() -> set:
    """管理员身份的合法标识：别名 + 真实链上地址。

    发币校验不能再只比别名串：assert_actor_wallet 现在统一返回真实地址，
    只比 ``0xadmin`` 会让管理员（哪怕已切到管理员钱包）永远 403。
    """
    return {t for t in (ADMIN_WALLET.lower(), (wallet_address("admin") or "").lower()) if t}


class IssueReq(BaseModel):
    name: str
    symbol: str
    decimals: int = 18
    total_supply: str
    owner: str = ""   # 留空 = 按 JWT 本人钱包；不再默认 0xlearner（密钥库内部别名）


@router.post("/issue")
def issue(req: IssueReq, user: dict = Depends(get_current_user)):
    """真实发行 ERC20：编译 ERC20.sol → EVM 部署（构造函数初始化总量）→ 记录。"""
    name = (req.name or "").strip()
    symbol = (req.symbol or "").strip()
    # 发币权限闭环：新代币发行是联盟治理行为，仅管理员钱包（0xadmin）可操作，
    # 避免学生随意发币造成账本混乱；学生可使用管理员发行的绿色能量参与生态流转
    owner = assert_actor_wallet(user, (req.owner or "").strip(), "owner")  # 发行者身份从 JWT 解析
    req.owner = owner
    if str(owner or "").lower() not in admin_wallet_ids():
        raise HTTPException(
            403,
            f"发行新代币仅限联盟管理员钱包（{short_wallet(wallet_address('admin') or ADMIN_WALLET)}）操作，"
            f"当前发行者 {short_wallet(owner) or '未填写'}。"
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


def _is_energy_token(name: str = "", symbol: str = "") -> bool:
    """该 tokens 行是否就是流通中的绿色能量代币（按登记名 / 符号判定）。"""
    return str(name or "") == ENERGY_TOKEN_NAME or str(symbol or "").upper() == ENERGY_TOKEN_SYMBOL


def _chain_balance(wallet: str, token_address: str) -> dict:
    """单个代币的链上 balanceOf（失败不伪造成 0，带上 query_ok / note 供前端提示）。"""
    c = get_chain_client()
    try:
        abi = _load_abi(token_address)
        r = c.call_contract(token_address, "balanceOf",
                            [c.resolve_account(wallet)], wallet, abi)
    except Exception as e:  # 链不可用 / 客户端异常
        return {"balance": "0", "query_ok": False, "query_note": f"链上查询异常: {e}"}
    if not r.get("ok"):
        return {"balance": "0", "query_ok": False,
                "query_note": str(r.get("error") or r.get("status") or "链上查询失败")}
    return {"balance": str(r.get("result", "0")), "query_ok": True, "query_note": ""}


@router.get("/balance")
def balance(wallet: str, token_address: str):
    """真实查询 ERC20 balanceOf（绿色能量走账本统一口径）。"""
    with get_conn() as conn:
        row = conn.execute("SELECT name,symbol FROM tokens WHERE address=?",
                           (token_address,)).fetchone()
    if row and _is_energy_token(row["name"], row["symbol"]):
        v = _energy_balance_view(wallet)
        return {"wallet": wallet, "token_address": token_address,
                "balance": str(v["balance"]), "source": v["source"],
                "ledger_balance": v["ledger_balance"], "chain_balance": v["chain_balance"],
                "chain_known": v["chain_known"], "needs_sync": v["needs_sync"],
                "sync_gap": v["sync_gap"], "query_ok": True,
                "query_note": v["chain_error"]}
    out = _chain_balance(wallet, token_address)
    return {"wallet": wallet, "token_address": token_address, **out,
            "source": "chain", "ledger_balance": None, "chain_balance": None,
            "needs_sync": False}


@router.get("/balances/{wallet}")
def balances(wallet: str):
    """查询钱包下所有 Token 余额（单个代币查询失败不再伪造成 0）。

    绿色能量（GreenEnergy）例外：余额取 `_energy_balance_view` 的账本口径，并附
    chain_balance / needs_sync —— 沙盒链重启后链上余额会被清零，只读链上就会把
    「刚提交凭证到账的能量」显示成 0（钱包页与联盟页余额长期不一致的根因）。
    """
    with get_conn() as conn:
        rows = conn.execute("SELECT address,name,symbol,decimals FROM tokens").fetchall()
    items = []
    for row in rows:
        item = {"token_address": row["address"], "name": row["name"],
                "symbol": row["symbol"], "decimals": row["decimals"],
                "balance": "0", "source": "chain", "query_ok": True, "query_note": ""}
        if _is_energy_token(row["name"], row["symbol"]):
            v = _energy_balance_view(wallet)
            item.update(balance=str(v["balance"]), source=v["source"],
                        ledger_balance=v["ledger_balance"], chain_balance=v["chain_balance"],
                        chain_known=v["chain_known"], needs_sync=v["needs_sync"],
                        sync_gap=v["sync_gap"],
                        query_ok=v["chain_known"] or v["source"] == "ledger",
                        query_note=v["chain_error"])
        else:
            item.update(_chain_balance(wallet, row["address"]))
        items.append(item)
    return {"wallet": wallet, "items": items}


class TransferReq(BaseModel):
    token_address: str
    from_addr: str
    to_addr: str
    amount: str


@router.post("/transfer")
def transfer(req: TransferReq, user: dict = Depends(get_current_user)):
    """真实 ERC20 transfer 调用。转出方身份从 JWT 验签解析，防伪造他人钱包转账。"""
    req.from_addr = assert_actor_wallet(user, req.from_addr, "from_addr")
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
