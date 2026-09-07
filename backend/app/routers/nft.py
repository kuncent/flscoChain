"""NFT 仿真交易市场 API（真实 ERC721/1155 编译部署 + 真实 mint 调用）。"""
from __future__ import annotations

import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from ..alliance_contracts import ENERGY_TOKEN_NAME, latest_deployed
from ..config import settings
from ..chain_client import get_chain_client
from ..db import get_conn, now
from .files import validate_upload, _ensure_uploads_meta
# 能量余额口径与绿色资产市场 / 联盟页兑换完全一致（同一事实源：业务账本优先，
# 链上余额只读回退；写路径前先把账本回填到链上）
from .eco import _get_energy_ledger_balance, _sync_chain_balance
from ..security import assert_actor_wallet, get_current_user
from ..tx_decoder import compile_source
from ..wallet_id import address_variants, to_address

router = APIRouter(prefix="/api/nft", tags=["nft"])


def _same_wallet(a: str, b: str) -> bool:
    """两个钱包口径是否同一账户（地址化后的唯一可靠比较）。

    历史行可能还是别名 / stu: 前缀，直接字符串比较会把「自己买自己的 NFT」
    漏判成两个不同的人（能量从自己账户扣、又流回自己账户）。
    """
    if not a or not b:
        return False
    return to_address(a) == to_address(b)

STANDARD_FILE = {"ERC721": "ERC721.sol", "ERC1155": "ERC1155.sol"}


class MintReq(BaseModel):
    standard: str = "ERC721"
    title: str
    description: str = ""
    image_url: Optional[str] = None
    author: str = ""   # 留空 = 按 JWT 本人钱包（真实地址）；不再默认 0xlearner 别名
    price: str = "0"
    # 发行数量：ERC1155 半同质化特性——同一 tokenId 可一次铸造多份；ERC721 唯一性——恒为 1（后端强制）
    amount: int = 1
    contract_address: Optional[str] = None  # 复用已部署合约；为空则新部署


@router.post("/mint")
def mint(req: MintReq, user: dict = Depends(get_current_user)):
    if req.standard not in ("ERC721", "ERC1155"):
        raise HTTPException(400, "standard must be ERC721 or ERC1155")
    if not (req.title or "").strip():
        raise HTTPException(400, "作品名称不能为空")
    # 协议特性约束：ERC721 每个 token 独一无二，数量恒为 1；ERC1155 支持同一 ID 多份发行（1~10000）
    if req.standard == "ERC721":
        req.amount = 1
    else:
        if req.amount < 1:
            req.amount = 1
        if req.amount > 10000:
            raise HTTPException(400, "ERC1155 发行数量不能超过 10000")
    req.author = assert_actor_wallet(user, req.author, "author")  # 铸造者身份从 JWT 解析
    # 铸造权限分级：居民须先获得联盟链生态身份（选择联盟角色）才能铸造数字资产
    # （兼容未迁移的历史别名行：地址 + 原值两套口径一起比）
    with get_conn() as conn:
        variants = [v.lower() for v in address_variants(req.author)] or [req.author.lower()]
        sel = conn.execute(
            f"SELECT role_key FROM eco_role_selections "
            f"WHERE lower(wallet) IN ({','.join('?' * len(variants))})",
            variants,
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

    # 真实调用 mint：ERC721 mint(to, tokenId, uri) 唯一铸造；
    # ERC1155 mint(to, tokenId, amount, uri) 按数量多份铸造（半同质化核心差异）
    uri = req.image_url or f"nft://{token_id}"
    if req.standard == "ERC721":
        args = [c.resolve_account(req.author), token_id_int, uri]
    else:
        args = [c.resolve_account(req.author), token_id_int, req.amount, uri]
    r_mint = c.call_contract(addr, "mint", args, req.author, abi)
    if not r_mint.get("ok"):
        raise HTTPException(400, "mint 失败: " + str(r_mint.get("error", "")))

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO nfts(token_id,standard,contract_address,author,title,description,image_url,meta_url,price,amount,owner,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (token_id, req.standard, addr, req.author, req.title, req.description,
             req.image_url, uri, req.price, req.amount, req.author, now()),
        )
    return {"token_id": token_id, "standard": req.standard, "amount": req.amount,
            "contract_address": addr,
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


@router.get("/trades")
def all_trades(limit: int = 200):
    """全量数字 NFT 成交记录（跨 token，权威数据源）：市场页交易时间线据此展示，
    不依赖浏览器本地缓存。注意路由须注册在 /{token_id} 之前。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM nft_trades ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
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
def buy(req: BuyReq, user: dict = Depends(get_current_user)):
    req.buyer = assert_actor_wallet(user, req.buyer, "buyer")  # 买家身份从 JWT 解析
    with get_conn() as conn:
        nft = conn.execute("SELECT * FROM nfts WHERE token_id=?", (req.token_id,)).fetchone()
        if not nft:
            raise HTTPException(404, "nft not found")
    # 当前持有人（转售后 owner 会变更，不能再用固定 author 当卖家）
    seller_wallet = nft["owner"] or nft["author"]
    if _same_wallet(seller_wallet, req.buyer):
        raise HTTPException(400, "不能购买自己持有的 NFT")
    # 价格以链上登记记录为唯一事实源（不信任客户端传入，防篡改）；
    # 支付货币统一为绿色能量（GreenEnergy）：平台唯一流通货币，与绿色资产市场结算口径自洽 ——
    # 学生能量来自业务角色凭证发放，其他 ERC20 仅限管理员发行且不向学生流通，
    # 若允许任意代币支付，买家无币可付、卖家也无法选择收款币种。
    price = int(nft["price"] or 0)
    # 取址必须与联盟页发行 / 兑换同一口径（deployed_contracts 最新一份）：
    # tokens 表只是「钱包展示的流通代币登记」，历史上只在启动 seed 时写一次，
    # GreenEnergy 一旦被重新部署就会指向作废地址（实测：居民钱包有 270 点能量，
    # 市场付款却被告知「当前 0」，报告 C 项「成交 +5」结构性拿不到）。
    # 故：先取最新部署且链上有代码的那一份，tokens 仅作兜底。
    ge_addr, _ = latest_deployed(ENERGY_TOKEN_NAME)
    if not ge_addr:
        with get_conn() as conn:
            ge = conn.execute(
                "SELECT address FROM tokens WHERE lower(name)=? OR upper(symbol)=? "
                "ORDER BY created_at DESC LIMIT 1",
                (ENERGY_TOKEN_NAME.lower(), "GE"),
            ).fetchone()
        ge_addr = (ge["address"] if ge else "")
    if not ge_addr:
        raise HTTPException(400, "GreenEnergy 合约未部署，无法完成支付")
    req.token_contract = ge_addr
    req.price = str(price)
    c = get_chain_client()
    tx_hash = ""
    # 1. 绿色能量支付（买方 → 卖方）：先查余额友好提示，再真实 transfer
    ge_abi = _load_abi(req.token_contract)
    if price > 0:
        # 先「账本 → 链上」回填，再以链上 balanceOf 为购买力事实源：
        # 本地沙盒链重启后 GreenEnergy 是一份新合约（人人余额 0），
        # 不回填就会把「账上有 270 点能量的居民」判成「余额不足」，
        # 导致 NFT 市场永远成交不了（报告 C 项「交易 +5」结构性拿不到）。
        _sync_chain_balance(req.buyer)
        bal_r = c.call_contract(req.token_contract, "balanceOf",
                                [c.resolve_account(req.buyer)], req.buyer, ge_abi)
        try:
            bal = int(str(bal_r.get("result", "0")))
        except (TypeError, ValueError):
            # 链上返回非数值（mock 链 / 异常节点）→ 回落账本净额（与市场 / 兑换同一口径）
            bal = _get_energy_ledger_balance(req.buyer)
        if bal < price:
            raise HTTPException(400, f"绿色能量不足：需要 {price}，当前 {bal}")
        r = c.call_contract(req.token_contract, "transfer",
                            [c.resolve_account(seller_wallet), price],
                            req.buyer, ge_abi)
        if not r.get("ok"):
            raise HTTPException(400, "能量支付失败: " + str(r.get("error", "")))
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
async def upload_image(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """NFT 素材上传：与 /api/files/upload 同源校验（白名单 + 5MB + 魔数），并记录上传者归属。"""
    content = await file.read()
    ext = validate_upload(file.filename or "", content)
    name = f"{uuid.uuid4().hex}{ext}"
    p = settings.uploads_dir / name
    p.write_bytes(content)
    # 上传归属写入 uploads_meta（files 模块自建表），保证下载/元数据归属校验一致
    try:
        with get_conn() as conn:
            _ensure_uploads_meta(conn)
            conn.execute(
                "INSERT INTO uploads_meta(name,original_filename,content_type,size,"
                "uploaded_by,uploader_wallet,uploader_name,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (name, file.filename or "", file.content_type or "", len(content),
                 user.get("user_id") or "", user.get("wallet") or "",
                 user.get("user_name") or "", now()),
            )
    except Exception:
        pass  # 元数据写入失败不阻断上传主流程（文件已落盘）
    return {"url": f"/static/{name}", "filename": name, "size": len(content)}


def _load_abi(address: str):
    with get_conn() as conn:
        r = conn.execute("SELECT abi FROM deployed_contracts WHERE address=?", (address,)).fetchone()
    return json.loads(r["abi"]) if r else []
