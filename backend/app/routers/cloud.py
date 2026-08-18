"""云桌面 WebSocket 终端后端。

提供伪终端执行能力：mock 模式下解析预设命令返回教学输出，
evm/fisco 模式下尝试真实 docker 命令或本地 subprocess 执行。
"""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import settings

router = APIRouter(prefix="/api/cloud", tags=["cloud"])

# deploy 目录（用于 docker-compose 命令）
DEPLOY_DIR = Path(settings.base_dir).parent.parent / "deploy"


# 预置链路输出（沙盒模式教学用）
SANDBOX_CMDS = {
    "ls": "contracts  console  nodes  README.md",
    "pwd": "/root/fisco",
    "ps -ef | grep fisco-bcos | grep -v grep": "\n".join(
        f"fisco-bcos  {i}  running  node{i}" for i in range(4)
    ),
    "bash nodes/127.0.0.1/start_all.sh": "node0 start successful\nnode1 start successful\nnode2 start successful\nnode3 start successful",
    "bash nodes/127.0.0.1/stop_all.sh": "node0 stop successful\nnode1 stop successful\nnode2 stop successful\nnode3 stop successful",
    "tail -n 20 nodes/127.0.0.1/node0/log/log_*.log": "+++Generating seal\nReport: sealer=0 blk=1 tx=0\n+++Generating seal",
    "getBlockNumber": "BlockNumber = 12",
    "getPeers": "node1\nnode2\nnode3",
    "getNodeIDList": "node0\nnode1\nnode2\nnode3",
    "deploy ERC20 TestToken TST 1000000": "contract address: 0x1234abcd7e8f9a3b2c1d4e5f6a7b8c9d0e1f2a3b",
    "call ERC20 0x1234 name": "TestToken",
    "help": "支持命令: ls, pwd, ps, start_all, stop_all, tail, getBlockNumber, getPeers, deploy, call",
}


def _sandbox_exec(cmd: str) -> str:
    cmd = cmd.strip()
    if not cmd:
        return ""
    # 部分匹配
    for k, v in SANDBOX_CMDS.items():
        if k in cmd or cmd in k:
            return v + "\n"
    return f"bash: {cmd}: command not found（沙盒模式下支持的命令见 help）\n"


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


@router.websocket("/ws/terminal")
async def terminal(ws: WebSocket):
    mode_label = "FISCO-BCOS 联盟链节点" if settings.is_fisco else ("EVM 虚拟机链路" if not settings.is_mock else "本地沙盒链路")
    await ws.accept()
    await ws.send_text(f"FISCO 联盟链云桌面 ({mode_label} · 输入 help 查看命令)\n$ ")
    try:
        while True:
            cmd = await ws.receive_text()
            if settings.is_mock:
                out = _sandbox_exec(cmd)
            else:
                out = await asyncio.to_thread(_real_exec, cmd)
            await ws.send_text(out + "\n$ ")
    except WebSocketDisconnect:
        return
