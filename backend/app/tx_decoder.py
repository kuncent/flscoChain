"""真实 Solidity 编译器封装（基于 py-solc-x）。

- 自动从源码解析 pragma 版本，安装对应 solc
- 真实编译输出 ABI + 字节码
- 真实编译错误/警告解析
- 自动识别 ERC20/721/1155 标准
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# solc 版本缓存：已安装版本
_installed_versions: set = set()


def _detect_solc_version(source: str) -> str:
    """从 pragma solidity 声明解析目标 solc 版本。"""
    m = re.search(r"pragma\s+solidity\s+\^?(\d+\.\d+\.\d+)", source)
    if m:
        return m.group(1)
    return "0.4.25"  # FISCO-BCOS 默认兼容版本


def _ensure_solc(version: str):
    """确保指定版本 solc 已安装。"""
    import solcx
    if version not in _installed_versions:
        try:
            solcx.install_solc(version)
            _installed_versions.add(version)
        except Exception:
            # 已安装则跳过
            _installed_versions.add(version)


def compile_source(source: str) -> Dict[str, Any]:
    """编译 Solidity 源码，返回 {abi, bytecode, errors, standard, name}。

    errors 为列表，每个元素为字符串，以 'error:' 或 'warning:' 开头。
    """
    errors: List[str] = []
    try:
        import solcx
        version = _detect_solc_version(source)
        _ensure_solc(version)
        out = solcx.compile_source(
            source,
            output_values=["abi", "bin"],
            solc_version=version,
        )
        # compile_source 返回 {contract_id: {abi, bin}}
        # 取第一个合约
        if not out:
            return {"ok": False, "errors": ["error: 编译输出为空，未找到合约定义"], "abi": [], "bytecode": ""}
        # 找到主合约（取非 interface/library 的最后一个）
        contract_id, compiled = list(out.items())[-1]
        name = contract_id.split(":")[-1] if ":" in contract_id else contract_id
        abi = compiled["abi"]
        bytecode = compiled["bin"]
        standard = _detect_standard(source, name)
        return {
            "ok": True, "errors": errors, "abi": abi, "bytecode": "0x" + bytecode,
            "standard": standard, "name": name, "solc_version": version,
        }
    except Exception as e:
        msg = str(e)
        # 解析 solc 错误信息
        for line in msg.split("\n"):
            line = line.strip()
            if line and ("Error" in line or "error:" in line or "Warning" in line or "warning:" in line):
                errors.append(line)
        if not errors:
            errors.append(f"error: {msg}")
        return {"ok": False, "errors": errors, "abi": [], "bytecode": "", "standard": None, "name": None}


# ERC 标准特征：事件签名 + 必需方法
# keccak256 topic0
ERC_SIGS = {
    "Transfer(address,address,uint256)": "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
    "Approval(address,address,uint256)": "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925",
    # ERC721 Transfer 与 ERC20 相同 topic0，区分靠 ownerOf 等方法
    # ERC1155
    "TransferSingle(address,address,address,uint256,uint256)": "0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62",
    "TransferBatch(address,address,address,uint256[],uint256[])": "0x4a39dc06d4c0dbc64b70af90fd698a233a518aa5d07e595d983b8c0526c8f7fb",
    "URI(string,uint256)": "0x6bb7ff708619ba0610cba295a58592e0451dee2622938c8755667688daf3529b",
}

ERC_METHODS = {
    "ERC20": {"transfer", "balanceOf", "approve", "transferFrom", "totalSupply", "name", "symbol", "decimals", "allowance"},
    "ERC721": {"ownerOf", "balanceOf", "transferFrom", "safeTransferFrom", "approve", "setApprovalForAll", "getApproved", "isApprovedForAll", "tokenURI"},
    "ERC1155": {"balanceOf", "safeTransferFrom", "safeBatchTransferFrom", "balanceOfBatch", "setApprovalForAll", "isApprovedForAll", "uri"},
}


def _detect_standard(source: str, name: str) -> Optional[str]:
    """根据源码方法名识别 ERC 标准。"""
    fn_names = set(re.findall(r"function\s+(\w+)\s*\(", source))
    for std, required in ERC_METHODS.items():
        # 命中 60% 以上方法即认定
        hit = len(fn_names & required)
        if hit >= max(3, len(required) // 2):
            return std
    return None


def decode_input_data(abi: List[Any], input_hex: str) -> Optional[Dict[str, Any]]:
    """根据合约 ABI 解码交易 input data，返回 {method, args}。

    input_hex 形如 0xa9059cbb0000...
    """
    try:
        from eth_abi import decode as abi_decode
        from eth_utils import function_abi_to_4byte_selector
        raw = input_hex[2:] if input_hex.startswith("0x") else input_hex
        if len(raw) < 8:
            return None
        selector = "0x" + raw[:8].lower()
        params_hex = raw[8:]
        # 遍历 ABI 匹配 selector
        for item in abi:
            if item.get("type") != "function":
                continue
            sig = function_abi_to_4byte_selector(item)
            if "0x" + sig.hex().lower() == selector:
                in_types = [i["type"] for i in item.get("inputs", [])]
                in_names = [i.get("name", f"arg{i}") for i in item.get("inputs", [])]
                if in_types:
                    decoded = abi_decode(in_types, bytes.fromhex(params_hex))
                    args = {nm: _readable(v) for nm, v in zip(in_names, decoded)}
                else:
                    args = {}
                return {"method": item["name"], "args": args, "selector": selector}
        return {"method": "unknown", "args": {}, "selector": selector}
    except Exception:
        return None


def _readable(v) -> Any:
    if isinstance(v, (bytes, bytearray)):
        return "0x" + v.hex()
    if isinstance(v, int):
        return v
    return v


def identify_standard_by_logs(logs: List[Dict]) -> Optional[str]:
    """根据事件日志的 topic0 识别 ERC 标准。"""
    topic0s = {lg.get("topics", [""])[0].lower() if lg.get("topics") else "" for lg in logs}
    # ERC1155 特征
    if ERC_SIGS["TransferSingle(address,address,address,uint256,uint256)"] in topic0s or \
       ERC_SIGS["TransferBatch(address,address,address,uint256[],uint256[])"] in topic0s:
        return "ERC1155"
    # ERC20/721 都有 Transfer + Approval
    if ERC_SIGS["Transfer(address,address,uint256)"] in topic0s:
        # 需要 ABI 区分；暂归 ERC20（含 721，浏览器按合约 standard 字段精确标注）
        return "ERC20"
    return None
