"""NFT 仿真交易市场 API（真实 ERC721/1155 编译部署 + 真实 mint 调用）。"""
from __future__ import annotations

import json
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from ..config import settings
from ..chain_client import get_chain_client
from ..db import get_conn, now
from ..tx_decoder import compile_source

router = APIRouter(prefix="/api/nft", tags=["nft"])

STANDARD_FILE = {"ERC721": "ERC721.sol", "ERC1155": "ERC1155.sol"}


class MintReq(BaseModel):
    standard: str = "ERC721"
    title: str
    description: str = ""
    image_url: Optional[str] = None
    author: str = "0xlearner"
    price: str = "0"
    contract_address: Optional[str] = None  # 复用已部署合约；为空则新部署


@router.post("/mint")
def mint(req: MintReq):
    if req.standard not in ("ERC721", "ERC1155"):
        raise HTTPException(400, "standard must be ERC721 or ERC1155")
    if not (req.title or "").strip():
        raise HTTPException(400, "作品名称不能为空")
    # 铸造权限分级：居民须先获得联盟链生态身份（选择联盟角色）才能铸造数字资产
    with get_conn() as conn:
        sel = conn.execute(
            "SELECT role_key FROM eco_role_selections WHERE wallet=?", (req.author,)
        ).fetchone()
    if not sel:
        raise HTTPException(403, "请先在「绿色低碳联盟链」页面选择联盟角色身份，再铸造数字资产")
    c = get_chain_client()
    token_id_int = uuid.uuid4().int & 0xFFFFFFFF  # 32 位 tokenId
    token_id = str(token_id_int)

    addr = req.contract_address
    abi = None
    # 若未指定合约地址，则真实编译部署一个
    if not addr:
        src = (settings.contracts_dir / STANDARD_FILE[req.standard]).read_text(encoding="utf-8")
        comp = compile_source(src)
        if not comp["ok"]:
            raise HTTPException(400, "编译失败: " + "; ".join(comp["errors"]))
        r = c.deploy_contract(
            f"{req.standard}-{token_id[:6]}", comp["abi"], comp["bytecode"], src,
            req.author, req.standard,
        )
        addr = r["address"]
        abi = comp["abi"]
        with get_conn() as conn:
            conn.execute("DELETE FROM deployed_contracts WHERE address=?", (addr,))
            conn.execute(
                "INSERT INTO deployed_contracts(address,name,abi,bytecode,source,deployer,tx_hash,standard,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (addr, f"{req.standard}-{token_id[:6]}", json.dumps(abi), comp["bytecode"], src,
                 req.author, r["tx_hash"], req.standard, now()),
            )

    if abi is None:
        with get_conn() as conn:
            row = conn.execute("SELECT abi FROM deployed_contracts WHERE address=?", (addr,)).fetchone()
        abi = json.loads(row["abi"]) if row else []

    # 真实调用 mint
    uri = req.image_url or f"nft://{token_id}"
    if req.standard == "ERC721":
        args = [c.resolve_account(req.author), token_id_int, uri]
    else:
        args = [c.resolve_account(req.author), token_id_int, 1, uri]
    r_mint = c.call_contract(addr, "mint", args, req.author, abi)
    if not r_mint.get("ok"):
        raise HTTPException(400, "mint 失败: " + str(r_mint.get("error", "")))

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO nfts(token_id,standard,contract_address,author,title,description,image_url,meta_url,price,owner,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (token_id, req.standard, addr, req.author, req.title, req.description,
             req.image_url, uri, req.price, req.author, now()),
        )
    return {"token_id": token_id, "standard": req.standard, "contract_address": addr,
            "mint_tx": r_mint.get("tx_hash", ""), "gas_used": r_mint.get("gas_used", 0)}


@router.get("/list")
def list_nfts(standard: Optional[str] = None):
    sql = "SELECT * FROM nfts"
    params = ()
    if standard:
        sql += " WHERE standard=?"
        params = (standard,)
    sql += " ORDER BY created_at DESC"
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.get("/{token_id}")
def get_nft(token_id: str):
    with get_conn() as conn:
        r = conn.execute("SELECT * FROM nfts WHERE token_id=?", (token_id,)).fetchone()
        trades = conn.execute("SELECT * FROM nft_trades WHERE token_id=? ORDER BY id DESC", (token_id,)).fetchall()
    if not r:
        raise HTTPException(404, "nft not found")
    d = dict(r)
    d["trades"] = [dict(t) for t in trades]
    return d


class BuyReq(BaseModel):
    token_id: str
    buyer: str
    token_contract: str = ""   # ERC20 合约地址
    price: str = "0"


@router.post("/buy")
def buy(req: BuyReq):
    with get_conn() as conn:
        nft = conn.execute("SELECT * FROM nfts WHERE token_id=?", (req.token_id,)).fetchone()
        if not nft:
            raise HTTPException(404, "nft not found")
    # 当前持有人（转售后 owner 会变更，不能再用固定 author 当卖家）
    seller_wallet = nft["owner"] or nft["author"]
    if seller_wallet == req.buyer:
        raise HTTPException(400, "不能购买自己持有的 NFT")
    c = get_chain_client()
    tx_hash = ""
    # 真实 ERC20 转账（买方 → 卖方）
    if req.token_contract and req.price != "0":
        abi = _load_abi(req.token_contract)
        r = c.call_contract(req.token_contract, "transfer",
                            [c.resolve_account(seller_wallet), int(req.price)],
                            req.buyer, abi)
        if not r.get("ok"):
            raise HTTPException(400, "付款失败: " + str(r.get("error", "")))
        tx_hash = r.get("tx_hash", "")
    # 真实 NFT 转移（ERC721 transferFrom / ERC1155 safeTransferFrom，FROM = 当前持有人）
    nft_abi = _load_abi(nft["contract_address"])
    if nft_abi:
        seller = c.resolve_account(seller_wallet)
        buyer = c.resolve_account(req.buyer)
        tid = int(nft["token_id"])
        if nft["standard"] == "ERC721":
            r2 = c.call_contract(nft["contract_address"], "transferFrom",
                                 [seller, buyer, tid], seller_wallet, nft_abi)
        else:
            r2 = c.call_contract(nft["contract_address"], "safeTransferFrom",
                                 [seller, buyer, tid, 1], seller_wallet, nft_abi)
        if not r2.get("ok"):
            raise HTTPException(400, "NFT 转移失败: " + str(r2.get("error", "")))
        tx_hash = r2.get("tx_hash", tx_hash)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO nft_trades(token_id,from_addr,to_addr,price,token_contract,tx_hash,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (req.token_id, seller_wallet, req.buyer, req.price, req.token_contract, tx_hash, now()),
        )
        conn.execute("UPDATE nfts SET owner=?, price=? WHERE token_id=?", (req.buyer, req.price, req.token_id))
    return {"ok": True, "tx_hash": tx_hash}


@router.get("/{token_id}/trades")
def trades(token_id: str):
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM nft_trades WHERE token_id=? ORDER BY id DESC", (token_id,)).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    ext = file.filename.split(".")[-1] if file.filename else "png"
    name = f"{uuid.uuid4().hex}.{ext}"
    p = settings.uploads_dir / name
    content = await file.read()
    p.write_bytes(content)
    return {"url": f"/static/{name}", "filename": name, "size": len(content)}


def _load_abi(address: str):
    with get_conn() as conn:
        r = conn.execute("SELECT abi FROM deployed_contracts WHERE address=?", (address,)).fetchone()
    return json.loads(r["abi"]) if r else []
