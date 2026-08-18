"""合约编译 / 部署 / 调用 API（真实 solc 编译 + 真实 EVM 部署执行）。"""
from __future__ import annotations

import json
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

from ..config import settings
from ..chain_client import get_chain_client
from ..db import get_conn, now
from ..tx_decoder import compile_source, decode_input_data
import json as _json

router = APIRouter(prefix="/api/contracts", tags=["contracts"])


def _track(event_type: str, target: str = "", ref_id: str = "", wallet: str = "", extra: dict | None = None):
    """轻量学习行为埋点，失败不抛错（兼容旧 DB 无 learning_events 表）。"""
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO learning_events(wallet,event_type,target,ref_id,extra,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (wallet, event_type, target, ref_id,
                 _json.dumps(extra or {}, ensure_ascii=False), now()),
            )
    except Exception:
        pass

BUILTIN = {
    "ERC20": "ERC20.sol",
    "ERC721": "ERC721.sol",
    "ERC1155": "ERC1155.sol",
    "GreenEnergy": "GreenEnergy.sol",
    "PlantCertificate": "PlantCertificate.sol",
    "EcoBadge": "EcoBadge.sol",
}


@router.get("/builtin")
def list_builtin():
    out = []
    for name, fn in BUILTIN.items():
        p = settings.contracts_dir / fn
        out.append({
            "name": name, "standard": name, "file": fn,
            "source": p.read_text(encoding="utf-8") if p.exists() else "",
        })
    return out


@router.get("/builtin/{name}")
def get_builtin(name: str, x_wallet: Optional[str] = Header(default=None, alias="X-Wallet")):
    fn = BUILTIN.get(name)
    if not fn:
        raise HTTPException(404, "contract not found")
    p = settings.contracts_dir / fn
    source = p.read_text(encoding="utf-8") if p.exists() else ""
    # 行为埋点：学生打开内置模板源码（说明在阅读/学习合约，对应 I-1 拓展分）
    _track("ide_open_builtin", target=name, wallet=x_wallet or "", extra={"file": fn})
    return {"name": name, "source": source}


# ---------- 真实编译 ----------
class CompileReq(BaseModel):
    name: str
    source: str


@router.post("/compile")
def compile_contract(req: CompileReq, x_wallet: Optional[str] = Header(default=None, alias="X-Wallet")):
    """真实 solc 编译，返回真实 ABI/字节码/错误。"""
    result = compile_source(req.source)
    ok = bool(result["ok"])
    # 行为埋点：真实编译成功/失败（I-1 加分项："至少编译过 1 次合约"）
    _track(
        "contract_compile_ok" if ok else "contract_compile_fail",
        target=req.name or "compile",
        wallet=x_wallet or "",
        extra={"errors_count": len(result.get("errors") or []), "standard": result.get("standard") or ""},
    )
    return {
        "ok": ok,
        "errors": result["errors"],
        "abi": result["abi"],
        "bytecode": result["bytecode"],
        "standard": result["standard"],
        "name": result.get("name") or req.name,
        "solc_version": result.get("solc_version"),
    }


# ---------- 真实部署 ----------
class DeployReq(BaseModel):
    name: str
    source: str
    abi: List[Any]
    bytecode: str
    deployer: str = "0xlearner"
    standard: Optional[str] = None
    ctor_args: Optional[List[Any]] = None  # 构造函数参数


@router.post("/deploy")
def deploy(req: DeployReq):
    c = get_chain_client()
    try:
        r = c.deploy_contract(
            req.name, req.abi, req.bytecode, req.source,
            req.deployer, req.standard, req.ctor_args,
        )
    except Exception as e:
        msg = str(e)
        # 构造函数参数缺失时给出学习性提示
        ctor = next((x for x in req.abi if x.get("type") == "constructor"), None)
        hint = ""
        if ctor and not req.ctor_args:
            params = ", ".join(f"{i['type']} {i['name']}" for i in ctor.get("inputs", []))
            hint = f" 该合约构造函数需要参数 ({params})，请在部署表单中填写。"
        raise HTTPException(400, msg + hint)
    with get_conn() as conn:
        # EVM 重启后地址可能复用，先清除旧记录避免 UNIQUE 冲突
        conn.execute("DELETE FROM deployed_contracts WHERE address=?", (r["address"],))
        conn.execute(
            "INSERT INTO deployed_contracts(address,name,abi,bytecode,source,deployer,tx_hash,standard,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (r["address"], req.name, json.dumps(req.abi), req.bytecode, req.source,
             req.deployer, r["tx_hash"], req.standard, now()),
        )
    return r


@router.get("/deployed")
def list_deployed():
    c = get_chain_client()
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM deployed_contracts ORDER BY created_at DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["abi"] = json.loads(d["abi"])
        # 标注合约在当前链实例上是否仍有代码（后端重启后 in-memory EVM 状态会重置，
        # DB 记录会变成 stale；live 字段让前端与 /eco/contracts/status 保持一致）
        try:
            d["live"] = bool(c.has_code(d["address"]))
        except Exception:
            d["live"] = False
        out.append(d)
    return out


@router.get("/deployed/{address}")
def get_deployed(address: str):
    with get_conn() as conn:
        r = conn.execute("SELECT * FROM deployed_contracts WHERE address=?", (address,)).fetchone()
    if not r:
        raise HTTPException(404, "not found")
    d = dict(r)
    d["abi"] = json.loads(d["abi"])
    return d


# ---------- 真实调用 ----------
class CallReq(BaseModel):
    address: str
    method: str
    args: List[Any] = []
    caller: str = "0xlearner"
    abi: Optional[List[Any]] = None


@router.post("/call")
def call(req: CallReq):
    abi = req.abi
    if not abi:
        with get_conn() as conn:
            r = conn.execute("SELECT abi FROM deployed_contracts WHERE address=?", (req.address,)).fetchone()
        if r:
            abi = json.loads(r["abi"])
    c = get_chain_client()
    r = c.call_contract(req.address, req.method, req.args, req.caller, abi or [])

    # 行为埋点：接口调试真实调用（对应 I-2 "是否使用过接口调试"）
    _track(
        "interface_invoke",
        target=req.method or "call",
        ref_id=r.get("tx_hash", ""),
        wallet=req.caller or "",
        extra={"address": req.address, "status": r.get("status", "unknown")},
    )

    # 写监听记录
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO contract_calls(contract_address,method,args,result,caller,tx_hash,block_number,status,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (req.address, req.method, json.dumps(req.args),
             json.dumps(r.get("result"), ensure_ascii=False) if r.get("result") else r.get("error", ""),
             req.caller, r.get("tx_hash", ""), r.get("block_number", 0),
             r.get("status", "success"), now()),
        )
    return r


# ---------- 合约接口自动生成 ----------
@router.get("/deployed/{address}/interfaces")
def get_interfaces(address: str):
    """根据已部署合约 ABI 自动生成可调试接口列表。"""
    with get_conn() as conn:
        r = conn.execute("SELECT abi FROM deployed_contracts WHERE address=?", (address,)).fetchone()
    if not r:
        raise HTTPException(404, "not found")
    abi = json.loads(r["abi"])
    out = []
    for item in abi:
        if item.get("type") == "function":
            out.append({
                "name": item["name"],
                "inputs": item.get("inputs", []),
                "outputs": item.get("outputs", []),
                "stateMutability": item.get("stateMutability", "nonpayable"),
                "readonly": item.get("stateMutability") in ("view", "pure"),
            })
    return {"address": address, "interfaces": out}
