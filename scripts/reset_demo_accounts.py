"""演示账户重置脚本。

用途：
    删除钱包密钥库文件（backend/app/storage/keystore.json）并重新生成
    8 个固定演示账户（0xadmin / 0xmetro / 0xbus / 0xbike / 0xtakeout /
    0xrecycle / 0xlearner / 0xnft），供实训数据重置使用。
    注：学习者（0xlearner）已合并原 Alice（0xalice）身份；0xalice / 0xbob /
    0xminter（铸造专员）均无业务用途，已下线不再重置生成。

用法：
    # 在项目根目录执行（使用 backend/.venv 虚拟环境）
    backend/.venv/Scripts/python scripts/reset_demo_accounts.py

    # 可选：通过环境变量指定密钥库加密口令（与后端 .env 中保持一致）
    $env:KEYSTORE_PASSWORD="xxx"; python scripts/reset_demo_accounts.py

注意：
    - 重置会删除所有账户（含学生钱包别名账户）的加密私钥；
    - 重置后所有账户地址都会重新生成，旧链上地址的余额 / 合约部署者 /
      mint 白名单等与新地址不再匹配，需要重新初始化链上数据；
    - 执行前请停止后端服务，避免进程内缓存与文件不一致。
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# 允许从项目根直接导入 backend.app 包
ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

from app import keystore as ks  # noqa: E402


def main() -> int:
    print(f"[reset] 密钥库文件: {ks.KEYSTORE_FILE}")
    before = ks.list_aliases()
    print(f"[reset] 当前密钥库包含 {len(before)} 个别名账户: {before}")

    ks.reset_keystore()
    print("[reset] 密钥库已删除，开始重新生成演示账户 ...")

    accounts = ks.ensure_demo_accounts()
    print("\n[reset] 演示账户已重新生成（私钥已加密落盘，仅显示地址）：")
    for alias, addr in accounts:
        print(f"  {alias:<10} -> {addr}")
    print("\n[reset] 完成。请重启后端服务以使新账户生效；"
          "若运行真实 FISCO-BCOS 节点，请重新初始化链上数据。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
