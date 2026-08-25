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
        rows = conn.execute("SELECT * FROM deployed_contracts").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["abi"] = json.loads(d["abi"])
        # 内置系统合约（seed 自动部署的 3 份生态合约）优先展示并打标
        d["builtin"] = (d.get("name") or "") in ("GreenEnergy", "PlantCertificate", "EcoBadge")
        # 标注合约在当前链实例上是否仍有代码（后端重启后 in-memory EVM 状态会重置，
        # DB 记录会变成 stale；live 字段让前端与 /eco/contracts/status 保持一致）
        try:
            d["live"] = bool(c.has_code(d["address"]))
        except Exception:
            d["live"] = False
        out.append(d)
    # 内置合约排最前，其余按部署时间先后排列（学生后部署的自定义合约显示在后面）
    out.sort(key=lambda d: (0 if d["builtin"] else 1, d.get("created_at") or ""))
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
    if not abi:
        raise HTTPException(404, "未找到该合约：请确认合约已部署，或从「合约接口」页面重新选择")

    # 无参数调用明确提示：根据 ABI 校验方法所需参数，缺失时给出可读错误
    fn_abi = next(
        (x for x in abi if x.get("type") == "function" and x.get("name") == req.method),
        None,
    )
    if fn_abi is None:
        raise HTTPException(
            400,
            f"合约 ABI 中不存在方法 {req.method}：请核对方法名（区分大小写），"
            "或重新部署合约后刷新接口列表",
        )
    required = [i for i in fn_abi.get("inputs", [])]
    got = req.args or []
    missing_names = [i.get("name") or i.get("type") for i in required[len(got):]]
    if len(got) > len(required):
        raise HTTPException(
            400,
            f"方法 {req.method} 仅需 {len(required)} 个参数，实际传入 {len(got)} 个，请移除多余参数",
        )
    if missing_names:
        raise HTTPException(
            400,
            f"方法 {req.method} 缺少参数：{'、'.join(missing_names)}"
            f"（共需 {len(required)} 个，已提供 {len(got)} 个）。请在表单中补全后重新调用",
        )

    c = get_chain_client()
    r = c.call_contract(req.address, req.method, req.args, req.caller, abi)

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


# ==================== 方向三：合约安全审计 ====================
class AuditReq(BaseModel):
    source: str
    name: str = "Contract"


@router.post("/audit")
def audit_contract(req: AuditReq, x_wallet: Optional[str] = Header(default=None, alias="X-Wallet")):
    """合约安全审计 - 检测常见 Solidity 漏洞。"""
    import re as _re
    source = req.source
    issues = []

    # 1. 重入攻击检测
    if ".call(" in source or ".call{" in source:
        lines = source.split('\n')
        in_func = False
        found_call = False
        call_line = 0
        for i, line in enumerate(lines):
            s = line.strip()
            if 'function' in s and '{' in s:
                in_func = True
                found_call = False
            elif in_func:
                if '.call(' in s or '.call{' in s:
                    found_call = True
                    call_line = i + 1
                elif found_call and ('=' in s or '+=' in s or '-=' in s) and not s.startswith('//'):
                    issues.append({
                        "severity": "high", "type": "reentrancy",
                        "message": "重入攻击风险：外部调用后修改状态变量",
                        "suggestion": "使用 checks-effects-interactions 模式",
                        "line": i + 1,
                    })
                    break
                if s == '}' or (s.endswith('}') and s.count('}') > s.count('{')):
                    in_func = False

    # 2. tx.origin 认证风险
    if 'tx.origin' in source:
        issues.append({
            "severity": "high", "type": "tx_origin",
            "message": "使用 tx.origin 进行认证存在钓鱼攻击风险",
            "suggestion": "使用 msg.sender 替代 tx.origin",
        })

    # 3. selfdestruct 风险
    if 'selfdestruct' in source:
        issues.append({
            "severity": "high", "type": "self_destruct",
            "message": "合约包含 selfdestruct，可能导致合约被意外销毁",
            "suggestion": "谨慎使用 selfdestruct，确保有严格的访问控制",
        })

    # 4. 未检查的外部调用返回值
    lines = source.split('\n')
    for i, line in enumerate(lines):
        s = line.strip()
        if ('.call(' in s or '.send(' in s) and not s.startswith('//'):
            if 'require' not in s and 'if' not in s and 'bool' not in s and '=' not in s.split('.')[0]:
                next_s = lines[i + 1].strip() if i + 1 < len(lines) else ''
                if 'require' not in next_s and 'if' not in next_s:
                    issues.append({
                        "severity": "medium", "type": "unchecked_call",
                        "message": f"第 {i + 1} 行：外部调用未检查返回值",
                        "suggestion": "检查 call/send 的返回值，使用 require 确保调用成功",
                        "line": i + 1,
                    })

    # 5. 整数溢出（Solidity < 0.8）
    version_match = _re.search(r'pragma solidity\s+([\^~]?[\d.]+)', source)
    if version_match:
        ver = version_match.group(1).lstrip('^~')
        if ver.startswith('0.') and not ver.startswith('0.8'):
            if any(op in source for op in [' + ', ' - ', ' * ']):
                if 'SafeMath' not in source and 'using' not in source:
                    issues.append({
                        "severity": "medium", "type": "integer_overflow",
                        "message": "Solidity 0.8 以下版本存在整数溢出风险",
                        "suggestion": "使用 SafeMath 库或升级到 Solidity 0.8+",
                    })

    # 6. 弱随机数
    if ('block.timestamp' in source or 'blockhash' in source) and 'rand' in source.lower():
        issues.append({
            "severity": "medium", "type": "weak_randomness",
            "message": "使用区块变量生成随机数存在可预测风险",
            "suggestion": "使用可信随机数预言机（如 Chainlink VRF）",
        })

    # 7. 函数可见性缺失
    for i, line in enumerate(lines):
        s = line.strip()
        if 'function' in s and '{' in s:
            if not any(v in s for v in ['public', 'private', 'internal', 'external']):
                issues.append({
                    "severity": "low", "type": "visibility",
                    "message": f"第 {i + 1} 行：函数未明确指定可见性",
                    "suggestion": "明确指定 public/private/internal/external",
                    "line": i + 1,
                })

    # 8. 缺少事件日志
    has_state_fn = any(
        'function' in l and ('public' in l or 'external' in l) and 'view' not in l and 'pure' not in l
        for l in lines
    )
    if has_state_fn and 'event ' not in source and 'emit ' not in source:
        issues.append({
            "severity": "low", "type": "missing_events",
            "message": "状态修改函数未触发事件",
            "suggestion": "为关键操作添加事件日志，便于链下追踪",
        })

    # 9. 缺少访问控制
    has_acl = any(kw in source for kw in ['onlyOwner', 'require(msg.sender', 'modifier', 'AccessControl'])
    has_sensitive = any(kw in source for kw in ['mint', 'burn', 'transfer', 'withdraw', 'selfdestruct'])
    if has_sensitive and not has_acl:
        issues.append({
            "severity": "medium", "type": "missing_access_control",
            "message": "敏感函数缺少访问控制",
            "suggestion": "使用 Ownable 或 AccessControl 限制敏感操作",
        })

    # 10. Gas 优化建议
    if source.lower().count('sstore') > 3 or source.lower().count('storage') > 5:
        issues.append({
            "severity": "low", "type": "gas_optimization",
            "message": "频繁的 storage 操作会消耗大量 Gas",
            "suggestion": "使用 memory 变量缓存中间结果",
        })

    high = sum(1 for i in issues if i['severity'] == 'high')
    medium = sum(1 for i in issues if i['severity'] == 'medium')
    low = sum(1 for i in issues if i['severity'] == 'low')

    _track("contract_audit", target=req.name, wallet=x_wallet or "",
           extra={"issues": len(issues), "high": high, "medium": medium, "low": low})

    return {
        "ok": True, "name": req.name,
        "issues_count": len(issues),
        "high": high, "medium": medium, "low": low,
        "issues": issues,
        "score": max(0, 100 - high * 20 - medium * 10 - low * 5),
    }


# ==================== 方向三：统一错误码体系 ====================
@router.get("/error-codes")
def list_error_codes():
    """返回平台统一错误码体系。"""
    return {
        "error_codes": [
            {"code": "E1001", "message": "合约编译失败", "solution": "检查 Solidity 语法和版本兼容性"},
            {"code": "E1002", "message": "合约部署失败", "solution": "确认部署者余额充足，检查构造函数参数"},
            {"code": "E1003", "message": "合约调用失败", "solution": "检查方法名和参数类型，确认合约已部署"},
            {"code": "E1004", "message": "ABI 解码失败", "solution": "确认 ABI 与合约版本匹配"},
            {"code": "E2001", "message": "钱包余额不足", "solution": "向钱包注入测试代币"},
            {"code": "E2002", "message": "Gas 不足", "solution": "增加 Gas Limit 或优化合约代码"},
            {"code": "E2003", "message": "交易确认超时", "solution": "检查网络连接，增加等待时间"},
            {"code": "E3001", "message": "权限不足", "solution": "确认当前账户有执行该操作的权限"},
            {"code": "E3002", "message": "角色未选择", "solution": "先选择联盟角色再进行操作"},
            {"code": "E3003", "message": "业务凭证不满足阈值", "solution": "检查业务数据是否达到发放条件"},
            {"code": "E4001", "message": "合约不存在", "solution": "确认合约地址正确且已部署"},
            {"code": "E4002", "message": "方法不存在", "solution": "检查方法名拼写，区分大小写"},
            {"code": "E4003", "message": "参数类型不匹配", "solution": "核对参数类型和数量"},
            {"code": "E5001", "message": "数据库连接失败", "solution": "检查数据库服务状态"},
            {"code": "E5002", "message": "链节点连接失败", "solution": "检查 FISCO 节点或 EVM 引擎状态"},
        ]
    }
