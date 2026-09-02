"""真实 Solidity 编译器封装（基于 py-solc-x）。

- 自动从源码解析 pragma 版本，安装对应 solc
- 真实编译输出 ABI + 字节码
- 真实编译错误/警告解析
- 自动识别 ERC20/721/1155 标准

任务 #20 性能底座：
- 编译迁入 ThreadPoolExecutor（验证结论：solcx.compile_source 内部通过
  subprocess 调用外部 solc 二进制，不依赖调用进程的 GIL/CPU，输入输出均为
  可直接传递的 str/dict，ThreadPoolExecutor 即可安全并发，无需进程池 pickle）；
- 产物缓存：键 = sha256(source) + solc 版本，落盘 storage/compile_cache/{key}.json，
  命中直接返回（不再调 solcx），仅缓存编译成功（ok=True）的产物；
- 启动预装常用 solc 版本（默认 ["0.4.25", "0.8.20"]，可用 SOLC_PREINSTALL
  环境变量覆盖，逗号分隔），在后台线程执行不阻塞导入；下载失败显式记录并
  在后续编译需要该版本时 raise（修复旧实现"安装失败也标记为已安装"的静默吞错）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from .config import settings

# solc 版本缓存：已安装版本（内存缓存，避免重复查询磁盘）
_installed_versions: set = set()
# 编译结果内存缓存（热结果免磁盘 IO；磁盘缓存为主，内存缓存为辅）
_result_cache: Dict[str, Dict[str, Any]] = {}
_result_cache_lock = threading.Lock()

# 预装失败记录（不静默：编译需要对应版本时会显式 raise，并附本次记录）
_preinstall_errors: Dict[str, str] = {}

# 常用 solc 预装版本：0.4.25（FISCO-BCOS 兼容默认）+ 0.8.20（现代教学常用）
DEFAULT_SOLC_VERSIONS = ["0.4.25", "0.8.20"]


def _preinstall_versions() -> List[str]:
    """读取预装版本列表（SOLC_PREINSTALL 环境变量可覆盖默认值）。"""
    raw = os.getenv("SOLC_PREINSTALL", "").strip()
    if raw:
        return [v.strip() for v in raw.split(",") if v.strip()]
    return list(DEFAULT_SOLC_VERSIONS)


def _preinstall_worker() -> None:
    """后台预装常用 solc 版本；失败显式记录（不静默），不抛出线程。"""
    for version in _preinstall_versions():
        try:
            _ensure_solc(version)
            print(f"[tx_decoder] solc {version} 预装就绪")
        except Exception as e:
            _preinstall_errors[version] = str(e)
            print(f"[tx_decoder] solc {version} 预装失败（编译需要该版本时将显式报错）: {e}")


# 模块导入即创建预装线程（启动延后到模块末尾，确保 _ensure_solc 已定义）
_preinstall_thread = threading.Thread(
    target=_preinstall_worker, name="solc-preinstall", daemon=True
)

# 编译执行池：solc 本体是外部子进程，线程池即可并发驱动多份编译
_compile_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="solc-compile")


def _detect_solc_version(source: str) -> str:
    """从 pragma solidity 声明解析目标 solc 版本。"""
    m = re.search(r"pragma\s+solidity\s+\^?(\d+\.\d+\.\d+)", source)
    if m:
        return m.group(1)
    return "0.4.25"  # FISCO-BCOS 默认兼容版本


def _ensure_solc(version: str) -> None:
    """确保指定版本 solc 已安装；安装失败显式 raise（不静默吞错）。"""
    if version in _installed_versions:
        return
    import solcx
    # 已在磁盘上（此前安装过）：直接标记，避免重复下载
    try:
        installed = {str(v) for v in solcx.get_installed_solc_versions()}
        if version in installed:
            _installed_versions.add(version)
            return
    except Exception:
        pass  # 版本探测失败不阻塞，继续走安装路径
    try:
        solcx.install_solc(version)
        _installed_versions.add(version)
    except Exception as e:
        # 修复旧实现 bug：旧版在异常分支也把版本加入 _installed_versions，
        # 导致后续报出"找不到 solc 二进制"之类隐晦错误。现在显式抛出、
        # 由 compile_source 转为明确错误信息返回给调用方。
        raise RuntimeError(f"solc {version} 安装失败: {e}") from e


def _cache_key(source: str, version: str) -> str:
    """编译产物缓存键：sha256(source) + solc 版本。"""
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return f"{digest}-{version}"


def _cache_path(key: str):
    return settings.compile_cache_dir / f"{key}.json"


def _load_disk_cache(key: str) -> Optional[Dict[str, Any]]:
    """从磁盘读取编译产物缓存；损坏/缺失返回 None。"""
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("ok"):
            return data
    except Exception:
        pass  # 缓存损坏按未命中处理，重新编译并覆写
    return None


def _save_disk_cache(key: str, result: Dict[str, Any]) -> None:
    """原子写入编译产物缓存（tmp + rename，避免半写状态）。"""
    try:
        path = _cache_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as e:
        # 缓存写失败不影响编译结果返回（日志降级）
        print(f"[tx_decoder] 编译缓存写入失败（降级）: {e}")


def _compile_uncached(source: str, version: str) -> Dict[str, Any]:
    """执行真实编译（无缓存路径），返回结构与旧版 compile_source 完全一致。"""
    errors: List[str] = []
    try:
        import solcx
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


def compile_source(source: str) -> Dict[str, Any]:
    """编译 Solidity 源码，返回 {abi, bytecode, errors, standard, name}。

    errors 为列表，每个元素为字符串，以 'error:' 或 'warning:' 开头。

    任务 #20：编译在 ThreadPoolExecutor 中执行（不阻塞调用线程），
    产物按 sha256(source)+solc 版本缓存（内存 + 磁盘），命中直接返回。
    返回结构与旧版完全一致，调用方无感知。
    """
    version = _detect_solc_version(source)
    key = _cache_key(source, version)

    # 1) 内存缓存命中
    with _result_cache_lock:
        cached = _result_cache.get(key)
    if cached is not None:
        return dict(cached)

    # 2) 磁盘缓存命中（回填内存缓存）
    cached = _load_disk_cache(key)
    if cached is not None:
        with _result_cache_lock:
            _result_cache[key] = cached
        return dict(cached)

    # 3) 未命中：线程池执行真实编译（solc 为外部子进程，线程池即可并发）
    result = _compile_pool.submit(_compile_uncached, source, version).result()

    # 4) 成功结果写缓存（失败结果不缓存：便于环境修复后重试）
    if result.get("ok"):
        with _result_cache_lock:
            _result_cache[key] = result
        _save_disk_cache(key, result)
    return result


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


# 在模块末尾启动预装线程（后台 daemon，不阻塞导入与请求处理）：
# 必须等 _ensure_solc 定义完成后再启动，否则线程抢跑会 NameError。
_preinstall_thread.start()
