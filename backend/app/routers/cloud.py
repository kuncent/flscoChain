"""云桌面 WebSocket 终端后端。

提供伪终端执行能力：mock 模式下解析预设命令返回教学输出，
evm/fisco 模式下尝试真实 docker 命令或本地 subprocess 执行。
"""
from __future__ import annotations

import asyncio
import subprocess
import time
import random
import re
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..config import settings

router = APIRouter(prefix="/api/cloud", tags=["cloud"])

# deploy 目录（用于 docker-compose 命令）
DEPLOY_DIR = Path(settings.base_dir).parent.parent / "deploy"


# ==================== 虚拟文件系统 ====================
class VirtualFileSystem:
    """模拟 FISCO-BCOS 开发环境的虚拟文件系统"""

    def __init__(self):
        self.cwd = "/root/fisco"
        self.files: Dict[str, Dict[str, Any]] = {}
        self._init_fisco_structure()

    def _init_fisco_structure(self):
        """初始化 FISCO-BCOS 目录结构"""
        # 根目录
        self.files["/root/fisco"] = {"type": "dir", "name": "fisco"}

        # contracts 目录
        self.files["/root/fisco/contracts"] = {"type": "dir", "name": "contracts"}
        self.files["/root/fisco/contracts/GreenEnergy.sol"] = {
            "type": "file", "name": "GreenEnergy.sol",
            "content": "// GreenEnergy ERC20 Token Contract\npragma solidity ^0.6.10;\n\ncontract GreenEnergy {\n    string public name = \"GreenEnergy\";\n    string public symbol = \"GE\";\n    uint8 public decimals = 0;\n    uint256 public totalSupply;\n    \n    mapping(address => uint256) public balanceOf;\n    mapping(address => bool) public mintRole;\n    address public owner;\n    \n    event Transfer(address indexed from, address indexed to, uint256 value);\n    event Mint(address indexed to, uint256 amount, string reason);\n    \n    constructor(uint256 initialSupply) public {\n        owner = msg.sender;\n        totalSupply = initialSupply;\n        balanceOf[msg.sender] = initialSupply;\n    }\n    \n    modifier onlyOwner() {\n        require(msg.sender == owner, \"Only owner\");\n        _;\n    }\n    \n    modifier onlyMintRole() {\n        require(mintRole[msg.sender] || msg.sender == owner, \"Not authorized\");\n        _;\n    }\n    \n    function mint(address to, uint256 amount, string memory reason) public onlyMintRole {\n        balanceOf[to] += amount;\n        emit Mint(to, amount, reason);\n        emit Transfer(address(0), to, amount);\n    }\n}"
        }

        # console 目录
        self.files["/root/fisco/console"] = {"type": "dir", "name": "console"}
        self.files["/root/fisco/console/conf"] = {"type": "dir", "name": "conf"}
        self.files["/root/fisco/console/start.sh"] = {
            "type": "file", "name": "start.sh",
            "content": "#!/bin/bash\n# FISCO BCOS Console Startup Script\njava -jar console.jar"
        }

        # nodes 目录（4 节点结构）
        self.files["/root/fisco/nodes"] = {"type": "dir", "name": "nodes"}
        self.files["/root/fisco/nodes/127.0.0.1"] = {"type": "dir", "name": "127.0.0.1"}

        # 节点配置
        for i in range(4):
            node_path = f"/root/fisco/nodes/127.0.0.1/node{i}"
            self.files[node_path] = {"type": "dir", "name": f"node{i}"}
            self.files[f"{node_path}/conf"] = {"type": "dir", "name": "conf"}
            self.files[f"{node_path}/log"] = {"type": "dir", "name": "log"}

            # 配置文件
            self.files[f"{node_path}/conf/config.ini"] = {
                "type": "file", "name": "config.ini",
                "content": f"[network]\nlisten_ip=0.0.0.0\nchannel_listen_port={20200 + i}\njsonrpc_listen_port={8545 + i}\n\n[consensus]\ntx_max_limit=1000000\n\n[state]\ntype=mpt"
            }
            self.files[f"{node_path}/conf/group.1.genesis"] = {
                "type": "file", "name": "group.1.genesis",
                "content": "[consensus]\nconsensus_type=pbft\nmax_trans_num=1000\n\n[state]\nstate_type=mpt"
            }

            # 证书文件
            self.files[f"{node_path}/conf/ca.crt"] = {"type": "file", "name": "ca.crt", "content": "-----BEGIN CERTIFICATE-----\nCA Certificate Content\n-----END CERTIFICATE-----"}
            self.files[f"{node_path}/conf/node.crt"] = {"type": "file", "name": "node.crt", "content": f"-----BEGIN CERTIFICATE-----\nNode{i} Certificate\n-----END CERTIFICATE-----"}
            self.files[f"{node_path}/conf/node.key"] = {"type": "file", "name": "node.key", "content": "-----BEGIN PRIVATE KEY-----\nNode Private Key\n-----END PRIVATE KEY-----"}
            self.files[f"{node_path}/conf/node.nodeid"] = {"type": "file", "name": "node.nodeid", "content": f"node{i}_id_{random.randint(1000, 9999)}"}

            # 日志文件
            self.files[f"{node_path}/log/log_2026-08-25.log"] = {"type": "file", "name": "log_2026-08-25.log", "content": ""}

        # SDK 证书
        self.files["/root/fisco/nodes/127.0.0.1/sdk"] = {"type": "dir", "name": "sdk"}
        self.files["/root/fisco/nodes/127.0.0.1/sdk/ca.crt"] = {"type": "file", "name": "ca.crt", "content": "SDK CA Certificate"}
        self.files["/root/fisco/nodes/127.0.0.1/sdk/sdk.crt"] = {"type": "file", "name": "sdk.crt", "content": "SDK Certificate"}
        self.files["/root/fisco/nodes/127.0.0.1/sdk/sdk.key"] = {"type": "file", "name": "sdk.key", "content": "SDK Private Key"}

        # 启动脚本
        self.files["/root/fisco/nodes/127.0.0.1/start_all.sh"] = {
            "type": "file", "name": "start_all.sh",
            "content": "#!/bin/bash\nfor node in node0 node1 node2 node3; do\n  echo \"Starting $node...\"\ndone"
        }
        self.files["/root/fisco/nodes/127.0.0.1/stop_all.sh"] = {
            "type": "file", "name": "stop_all.sh",
            "content": "#!/bin/bash\nfor node in node0 node1 node2 node3; do\n  echo \"Stopping $node...\"\ndone"
        }
        self.files["/root/fisco/nodes/127.0.0.1/check_node_status.sh"] = {
            "type": "file", "name": "check_node_status.sh",
            "content": "#!/bin/bash\necho \"Checking node status...\""
        }

        # README
        self.files["/root/fisco/README.md"] = {
            "type": "file", "name": "README.md",
            "content": "# FISCO-BCOS 联盟链开发环境\n\n## 目录结构\n- contracts/: 智能合约源码\n- console/: 控制台工具\n- nodes/: 节点配置和日志\n\n## 快速开始\n1. 启动节点: bash nodes/127.0.0.1/start_all.sh\n2. 进入控制台: cd console && bash start.sh\n3. 查看区块高度: getBlockNumber"
        }

    def resolve_path(self, path: str) -> str:
        """解析路径（支持相对路径和绝对路径）"""
        if path.startswith("/"):
            return path
        return f"{self.cwd}/{path}" if self.cwd != "/" else f"/{path}"

    def exists(self, path: str) -> bool:
        """检查路径是否存在"""
        return self.resolve_path(path) in self.files

    def is_dir(self, path: str) -> bool:
        """检查是否为目录"""
        resolved = self.resolve_path(path)
        return resolved in self.files and self.files[resolved]["type"] == "dir"

    def is_file(self, path: str) -> bool:
        """检查是否为文件"""
        resolved = self.resolve_path(path)
        return resolved in self.files and self.files[resolved]["type"] == "file"

    def list_dir(self, path: str) -> List[str]:
        """列出目录内容"""
        resolved = self.resolve_path(path)
        if not self.is_dir(resolved):
            return []

        items = []
        for file_path in self.files.keys():
            if file_path.startswith(resolved) and file_path != resolved:
                # 获取直接子项
                relative = file_path[len(resolved):].lstrip("/")
                if "/" not in relative:
                    items.append(self.files[file_path]["name"])

        return sorted(set(items))

    def read_file(self, path: str) -> Optional[str]:
        """读取文件内容"""
        resolved = self.resolve_path(path)
        if self.is_file(resolved):
            return self.files[resolved].get("content", "")
        return None

    def write_file(self, path: str, content: str) -> bool:
        """写入文件内容（如果文件不存在则创建）"""
        resolved = self.resolve_path(path)
        # 确保父目录存在
        parent = "/".join(resolved.rsplit("/", 1)[:-1]) if "/" in resolved else ""
        if parent and not self.exists(parent):
            self._ensure_dir(parent)
        
        name = resolved.rsplit("/", 1)[-1] if "/" in resolved else resolved
        self.files[resolved] = {"type": "file", "name": name, "content": content}
        return True

    def _ensure_dir(self, path: str):
        """递归确保目录存在"""
        if self.exists(path):
            return
        parts = path.split("/")
        for i in range(1, len(parts) + 1):
            partial = "/".join(parts[:i])
            if not self.exists(partial):
                name = parts[i-1]
                self.files[partial] = {"type": "dir", "name": name}

    def mkdir(self, path: str) -> bool:
        """创建目录"""
        resolved = self.resolve_path(path)
        if self.exists(resolved):
            return False
        self._ensure_dir(resolved)
        return True

    def touch(self, path: str) -> bool:
        """创建空文件"""
        resolved = self.resolve_path(path)
        if self.exists(resolved):
            return True
        # 确保父目录存在
        parent = "/".join(resolved.rsplit("/", 1)[:-1]) if "/" in resolved else ""
        if parent and not self.exists(parent):
            self._ensure_dir(parent)
        name = resolved.rsplit("/", 1)[-1] if "/" in resolved else resolved
        self.files[resolved] = {"type": "file", "name": name, "content": ""}
        return True

    def get_tree(self, path: str = "", prefix: str = "", is_last: bool = True, depth: int = 0, max_depth: int = 3) -> str:
        """生成目录树结构"""
        if depth == 0:
            resolved = self.resolve_path(path) if path else self.cwd
            if not self.is_dir(resolved):
                return f"{path}: Not a directory"
            result = [self.files[resolved]["name"]]
            items = self.list_dir(resolved)
            for i, item in enumerate(items):
                is_last_item = (i == len(items) - 1)
                connector = "└── " if is_last_item else "├── "
                item_path = f"{resolved}/{item}"
                result.append(f"{connector}{item}")
                if self.is_dir(item_path) and depth < max_depth:
                    extension = "    " if is_last_item else "│   "
                    subtree = self.get_tree(item_path, extension, is_last_item, depth + 1, max_depth)
                    if subtree:
                        result.append(subtree)
            return "\n".join(result)
        else:
            resolved = self.resolve_path(path) if path.startswith("/") else f"{self.cwd}/{path}"
            items = self.list_dir(resolved)
            lines = []
            for i, item in enumerate(items):
                is_last_item = (i == len(items) - 1)
                connector = "└── " if is_last_item else "├── "
                item_path = f"{resolved}/{item}"
                lines.append(f"{prefix}{connector}{item}")
                if self.is_dir(item_path) and depth < max_depth:
                    extension = "    " if is_last_item else "│   "
                    subtree = self.get_tree(item_path, extension, is_last_item, depth + 1, max_depth)
                    if subtree:
                        lines.append(subtree)
            return "\n".join(lines)

    def cd(self, path: str) -> bool:
        """切换目录"""
        resolved = self.resolve_path(path)
        if self.is_dir(resolved):
            self.cwd = resolved
            return True
        return False

    def get_prompt(self) -> str:
        """获取命令提示符"""
        return f"root@fisco-dev:{self.cwd}#"


# 全局文件系统实例（每个 WebSocket 连接独立）
_fs_instances: Dict[str, VirtualFileSystem] = {}


def _get_fs(session_id: str) -> VirtualFileSystem:
    """获取或创建文件系统实例"""
    if session_id not in _fs_instances:
        _fs_instances[session_id] = VirtualFileSystem()
    return _fs_instances[session_id]


# ==================== 节点状态模拟 ====================
class NodeSimulator:
    """模拟 FISCO-BCOS 节点运行状态"""

    def __init__(self):
        self.block_number = 100
        self.nodes = [
            {"id": "node0", "status": "running", "role": "sealer", "owner": "管理员+地铁"},
            {"id": "node1", "status": "running", "role": "sealer", "owner": "公交+单车"},
            {"id": "node2", "status": "running", "role": "sealer", "owner": "外卖+回收"},
            {"id": "node3", "status": "running", "role": "observer", "owner": "热备/监管"},
        ]
        self.last_update = time.time()

    def update(self):
        """更新节点状态（模拟区块增长）"""
        elapsed = time.time() - self.last_update
        if elapsed > 3:  # 每 3 秒出一个块
            self.block_number += 1
            self.last_update = time.time()

    def get_logs(self, node_id: str, lines: int = 10) -> str:
        """获取节点日志"""
        self.update()
        logs = []
        ts = time.strftime("%Y-%m-%d %H:%M:%S")

        for i in range(lines):
            blk = self.block_number - i
            if blk < 0:
                continue

            if i % 2 == 0:
                logs.append(f"[{ts}] +++Generating seal on: #blk={blk} tx={random.randint(0, 3)}   sealer={node_id}")
            else:
                logs.append(f"[{ts}] Report: sealer={random.randint(0, 3)} blk={blk} tx={random.randint(0, 2)}  4 节点 PBFT 通过")

        return "\n".join(logs)


# 全局节点模拟器
_node_sim = NodeSimulator()


# ==================== 命令执行器 ====================
def _execute_shell_command(cmd: str, fs: VirtualFileSystem, session_id: str) -> str:
    """执行 shell 命令并返回输出"""
    cmd = cmd.strip()
    if not cmd:
        return ""

    parts = cmd.split()
    command = parts[0]

    # pwd
    if command == "pwd":
        return fs.cwd

    # cd
    elif command == "cd":
        path = parts[1] if len(parts) > 1 else "/root/fisco"
        if fs.cd(path):
            return ""
        return f"bash: cd: {path}: No such file or directory"

    # ls
    elif command == "ls":
        path = parts[-1] if len(parts) > 1 and not parts[-1].startswith("-") else "."
        if not fs.exists(path):
            return f"ls: cannot access '{path}': No such file or directory"

        if fs.is_file(path):
            return fs.files[fs.resolve_path(path)]["name"]

        items = fs.list_dir(path)
        if not items:
            return ""

        # 格式化输出（带颜色）
        output = []
        for item in items:
            full_path = f"{fs.resolve_path(path)}/{item}"
            if fs.is_dir(full_path):
                output.append(f"\033[1;34m{item}\033[0m")  # 蓝色目录
            else:
                output.append(item)

        return "  ".join(output)

    # cat
    elif command == "cat":
        if len(parts) < 2:
            return "cat: missing operand"
        path = parts[1]
        content = fs.read_file(path)
        if content is None:
            return f"cat: {path}: No such file or directory"
        return content

    # mkdir
    elif command == "mkdir":
        if len(parts) < 2:
            return "mkdir: missing operand"
        path = parts[-1]
        if fs.mkdir(path):
            return f"Created directory: {path}"
        return f"mkdir: cannot create directory '{path}': File exists"

    # touch
    elif command == "touch":
        if len(parts) < 2:
            return "touch: missing operand"
        path = parts[-1]
        fs.touch(path)
        return ""

    # vim/vi/nano
    elif command in ["vim", "vi", "nano"]:
        if len(parts) < 2:
            return f"{command}: missing file argument"
        filename = parts[1]
        return f"提示: 请使用前端编辑器编辑文件 '{filename}'\n可通过 API 读写文件: GET/POST /api/cloud/files?path={filename}"

    # chmod
    elif command == "chmod":
        return ""  # 静默成功

    # curl
    elif command == "curl":
        if "build_chain.sh" in cmd:
            return "  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current\n                                 Dload  Upload   Total   Spent    Left  Speed\n100  1234  100  1234    0     0   5678      0 --:--:-- --:--:-- --:--:--  5678\n\n已下载 build_chain.sh (模拟)"
        return "curl: try 'curl --help' for more information"

    # tree
    elif command == "tree":
        path = parts[1] if len(parts) > 1 else ""
        return fs.get_tree(path)

    # grep
    elif command == "grep":
        if len(parts) < 3:
            return "Usage: grep [pattern] [file]"
        pattern = parts[1]
        filepath = parts[2]
        content = fs.read_file(filepath)
        if content is None:
            return f"grep: {filepath}: No such file or directory"
        lines = content.split("\n")
        matches = [line for line in lines if pattern in line]
        return "\n".join(matches) if matches else ""

    # head
    elif command == "head":
        if len(parts) < 2:
            return "head: missing operand"
        filepath = parts[-1]
        content = fs.read_file(filepath)
        if content is None:
            return f"head: {filepath}: No such file or directory"
        lines = content.split("\n")
        return "\n".join(lines[:10])

    # wc
    elif command == "wc":
        if len(parts) < 2:
            return "wc: missing operand"
        filepath = parts[-1]
        content = fs.read_file(filepath)
        if content is None:
            return f"wc: {filepath}: No such file or directory"
        lines = content.split("\n")
        words = content.split()
        chars = len(content)
        return f" {len(lines)} {len(words)} {chars} {filepath}"

    # find
    elif command == "find":
        if len(parts) < 2:
            return "find: missing path"
        search_path = parts[1]
        resolved = fs.resolve_path(search_path)
        if not fs.exists(resolved):
            return f"find: '{search_path}': No such file or directory"
        results = []
        for path in fs.files.keys():
            if path.startswith(resolved):
                results.append(path)
        return "\n".join(sorted(results))

    # netstat
    elif command == "netstat":
        if "-tlnp" in cmd or "-an" in cmd:
            return "Active Internet connections (only servers)\nProto Recv-Q Send-Q Local Address           Foreign Address         State       PID/Program name\ntcp        0      0 0.0.0.0:20200           0.0.0.0:*               LISTEN      1001/fisco-bcos\ntcp        0      0 0.0.0.0:20201           0.0.0.0:*               LISTEN      1002/fisco-bcos\ntcp        0      0 0.0.0.0:20202           0.0.0.0:*               LISTEN      1003/fisco-bcos\ntcp        0      0 0.0.0.0:20203           0.0.0.0:*               LISTEN      1004/fisco-bcos\ntcp        0      0 0.0.0.0:8545            0.0.0.0:*               LISTEN      1001/fisco-bcos\ntcp        0      0 0.0.0.0:8546            0.0.0.0:*               LISTEN      1002/fisco-bcos\ntcp        0      0 0.0.0.0:8547            0.0.0.0:*               LISTEN      1003/fisco-bcos\ntcp        0      0 0.0.0.0:8548            0.0.0.0:*               LISTEN      1004/fisco-bcos"
        return "Active Internet connections (servers and established)\n(使用 netstat -tlnp 查看详细端口)"

    # df
    elif command == "df":
        return "Filesystem     1K-blocks    Used Available Use% Mounted on\n/dev/sda1      104857600  1234567 103623033   2% /\ntmpfs           16384000       0  16384000   0% /dev/shm"

    # du
    elif command == "du":
        if len(parts) < 2:
            path = "."
        else:
            path = parts[-1]
        resolved = fs.resolve_path(path)
        if not fs.exists(resolved):
            return f"du: cannot access '{path}': No such file or directory"
        # 计算目录大小（模拟）
        size = 0
        for p in fs.files.keys():
            if p.startswith(resolved):
                if fs.files[p]["type"] == "file":
                    size += len(fs.files[p].get("content", ""))
        return f"{size // 1024 + 1}\t{path}"

    # openssl
    elif command == "openssl":
        if "x509" in cmd and "-in" in cmd:
            # 提取证书路径
            match = re.search(r"-in\s+(\S+)", cmd)
            if match:
                cert_path = match.group(1)
                content = fs.read_file(cert_path)
                if content is None:
                    return f"openssl: {cert_path}: No such file or directory"
                return f"Certificate:\n    Data:\n        Version: 3 (0x2)\n        Serial Number: 1234567890\n        Signature Algorithm: sha256WithRSAEncryption\n        Issuer: C=CN, ST=Beijing, O=FISCO-BCOS, CN=CA\n        Validity\n            Not Before: Jan  1 00:00:00 2024 GMT\n            Not After : Dec 31 23:59:59 2025 GMT\n        Subject: C=CN, ST=Beijing, O=FISCO-BCOS, CN=Node\n        Subject Public Key Info:\n            Public Key Algorithm: rsaEncryption\n                RSA Public-Key: (2048 bit)"
        return "openssl: Error: missing arguments\nusage: openssl x509 -in <cert> -text -noout"

    # ps
    elif command == "ps":
        if "grep" in cmd and "fisco-bcos" in cmd:
            _node_sim.update()
            output = []
            for i, node in enumerate(_node_sim.nodes):
                if node["status"] == "running":
                    output.append(
                        f"root      {1001 + i}      1  0 {time.strftime('%H:%M')} ?        00:00:{10 + i} fisco-bcos  {node['id']}  <- {node['owner']}"
                    )
            return "\n".join(output) if output else "No fisco-bcos processes running"
        return "PID TTY          TIME CMD"

    # tail
    elif command == "tail":
        if "node" in cmd and "log" in cmd:
            # 提取节点 ID
            match = re.search(r"node(\d)", cmd)
            if match:
                node_id = f"node{match.group(1)}"
                lines = 10
                if "-n" in parts:
                    try:
                        idx = parts.index("-n")
                        lines = int(parts[idx + 1])
                    except:
                        pass
                return _node_sim.get_logs(node_id, lines)
        return "tail: invalid input"

    # bash
    elif command == "bash":
        script = parts[1] if len(parts) > 1 else ""

        if "start_all.sh" in script:
            output = []
            for node in _node_sim.nodes:
                node["status"] = "running"
                output.append(f"try to start {node['id']} is_running: false  start successful   <- {node['owner']}")
            _node_sim.update()
            return "\n".join(output) + f"\n\n4 个 FISCO-BCOS 节点已启动，当前块高: {_node_sim.block_number}"

        elif "stop_all.sh" in script:
            output = []
            for node in _node_sim.nodes:
                node["status"] = "stopped"
                output.append(f"try to stop {node['id']} is_running: true  stop successful")
            return "\n".join(output)

        elif "check_node_status.sh" in script:
            output = ["======= FISCO-BCOS 节点健康检查 ======="]
            for node in _node_sim.nodes:
                status = "SUCCESS" if node["status"] == "running" else "FAILED"
                output.append(f"{node['id']} (...)  : {status}  <- {node['owner']}")
            output.append("-" * 40)
            running = sum(1 for n in _node_sim.nodes if n["status"] == "running")
            output.append(f"节点在线: {running}/4 ✅")
            return "\n".join(output)

        elif "start.sh" in script:
            return "==================================================================================\nFISCO BCOS Console (version 2.9.1)\n=================================================================================="

        return f"bash: {script}: No such file or directory"

    # cp
    elif command == "cp":
        if "-r" in parts:
            return "'nodes/127.0.0.1/sdk/ca.crt'        -> 'console/conf/ca.crt'\n'nodes/127.0.0.1/sdk/sdk.crt'       -> 'console/conf/sdk.crt'\n'nodes/127.0.0.1/sdk/sdk.key'       -> 'console/conf/sdk.key'\n\nSDK 证书已复制到控制台配置目录"
        return "cp: missing operand"

    # echo
    elif command == "echo":
        return " ".join(parts[1:]).strip("'\"")

    # help
    elif command == "help":
        return (
            "支持的命令:\n"
            "  ls [path]              列出目录内容\n"
            "  cd [path]              切换目录\n"
            "  pwd                    显示当前目录\n"
            "  cat <file>             查看文件内容\n"
            "  mkdir <dir>            创建目录\n"
            "  touch <file>           创建空文件\n"
            "  vim/vi/nano <file>     编辑文件（提示使用前端编辑器）\n"
            "  chmod <mode> <file>    修改文件权限\n"
            "  curl <url>             下载文件（支持 build_chain.sh）\n"
            "  tree [path]            显示目录树结构\n"
            "  grep <pattern> <file>  搜索文件内容\n"
            "  head <file>            查看文件前 10 行\n"
            "  wc <file>              统计文件行数/词数/字符数\n"
            "  find <path>            查找文件\n"
            "  netstat -tlnp          查看网络端口\n"
            "  df                     查看磁盘空间\n"
            "  du [path]              查看目录大小\n"
            "  openssl x509 -in <cert> 查看证书信息\n"
            "  ps -ef | grep fisco    查看节点进程\n"
            "  tail -f <log>          查看日志\n"
            "  bash <script>          执行脚本\n"
            "  cp -r <src> <dst>      复制文件\n"
            "\n控制台命令（进入 console 后）:\n"
            "  getBlockNumber         查询区块高度\n"
            "  getPeers               查看对等节点\n"
            "  getSealerList          查看共识节点\n"
            "  getGroupPeers          查看群组节点\n"
            "\n文件操作 API:\n"
            "  GET /api/cloud/files?path=<path>     读取虚拟文件\n"
            "  POST /api/cloud/files                保存虚拟文件\n"
            "  GET /api/cloud/tree?path=<path>      获取目录树\n"
            "  GET /api/cloud/autocomplete?prefix=x 命令自动补全"
        )

    # 未知命令
    return f"bash: {command}: command not found"


def _sandbox_exec(cmd: str, session_id: str = "default") -> str:
    """沙盒模式命令执行"""
    fs = _get_fs(session_id)
    return _execute_shell_command(cmd, fs, session_id)


def _real_exec(cmd: str) -> str:
    """在非沙盒模式下真实执行命令。

    优先尝试 docker 相关命令（如 docker ps / docker logs），
    其他命令在 deploy 目录执行（如 docker-compose）。
    """
    try:
        cwd = str(DEPLOY_DIR) if DEPLOY_DIR.exists() else None
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=15,
            cwd=cwd,
        )
        out = (r.stdout or "") + (r.stderr or "")
        if not out.strip():
            out = f"(命令已执行，无输出. exit code={r.returncode})"
        return out + "\n"
    except Exception as e:
        return f"exec error: {e}\n"


# ==================== 文件操作 API ====================
class FileContent(BaseModel):
    path: str
    content: str


@router.get("/files")
async def read_file(path: str = Query(..., description="文件路径")):
    """读取虚拟文件内容"""
    # 使用默认会话的文件系统
    fs = _get_fs("api_default")
    content = fs.read_file(path)
    if content is None:
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    return {"path": path, "content": content}


@router.post("/files")
async def write_file(file_data: FileContent):
    """保存虚拟文件内容"""
    fs = _get_fs("api_default")
    success = fs.write_file(file_data.path, file_data.content)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to write file")
    return {"path": file_data.path, "message": "File saved successfully"}


@router.get("/tree")
async def get_tree(path: str = Query("", description="目录路径")):
    """获取目录树结构"""
    fs = _get_fs("api_default")
    tree = fs.get_tree(path)
    return {"path": path or fs.cwd, "tree": tree}


# ==================== 命令自动补全 API ====================
@router.get("/autocomplete")
async def autocomplete(prefix: str = Query(..., description="命令前缀")):
    """返回匹配的命令建议"""
    all_commands = [
        "ls", "cd", "pwd", "cat", "mkdir", "touch", "vim", "vi", "nano",
        "chmod", "curl", "tree", "grep", "head", "wc", "find", "netstat",
        "df", "du", "openssl", "ps", "tail", "bash", "cp", "echo", "help",
        "getBlockNumber", "getPeers", "getSealerList", "getGroupPeers"
    ]
    
    matches = [cmd for cmd in all_commands if cmd.startswith(prefix)]
    return {"prefix": prefix, "suggestions": matches}


@router.websocket("/ws/terminal")
async def terminal(ws: WebSocket):
    mode_label = "FISCO-BCOS 联盟链节点" if settings.is_fisco else ("EVM 虚拟机链路" if not settings.is_mock else "本地沙盒链路")
    await ws.accept()

    # 生成会话 ID
    session_id = f"session_{int(time.time())}_{random.randint(1000, 9999)}"
    fs = _get_fs(session_id)

    await ws.send_text(f"FISCO 联盟链云桌面 ({mode_label} · 输入 help 查看命令)\n{fs.get_prompt()} ")
    try:
        while True:
            cmd = await ws.receive_text()
            if settings.is_mock:
                out = _sandbox_exec(cmd, session_id)
            else:
                out = await asyncio.to_thread(_real_exec, cmd)
            await ws.send_text(out + "\n" + fs.get_prompt() + " ")
    except WebSocketDisconnect:
        # 清理会话
        if session_id in _fs_instances:
            del _fs_instances[session_id]
        return
