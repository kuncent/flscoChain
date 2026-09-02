"""钱包密钥库（keystore）统一管理模块。

职责：
  - 所有链客户端（mock / evm / fisco）的账户私钥一律"首次使用时随机生成"，
    不再做任何硬编码/可复算推导；
  - 私钥使用 eth_account 的 keystore v3 格式（Account.encrypt）加密后
    持久化到 backend/app/storage/keystore.json；
  - 加密口令来自环境变量 KEYSTORE_PASSWORD；未配置时使用开发兜底口令并打印告警；
  - 别名 → 账户一一对应：固定演示别名与任意未知别名（学生钱包）各自拥有独立密钥，
    重启后地址保持不变。

文件结构（keystore.json）：
{
  "version": 1,
  "accounts": {
    "<alias>": {"address": "0x..", "keystore": { ...v3 加密 JSON... }},
    ...
  }
}
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from eth_account import Account

logger = logging.getLogger(__name__)

# 密钥库文件位置：与 config.settings.storage_dir 保持一致（backend/app/storage/）
KEYSTORE_FILE = Path(__file__).resolve().parent / "storage" / "keystore.json"

# 加密口令环境变量名
PASSWORD_ENV = "KEYSTORE_PASSWORD"
# 未配置口令时的开发兜底口令（仅保证功能可用，生产必须配置 KEYSTORE_PASSWORD）
_FALLBACK_PASSWORD = "digedu-local-dev-insecure"

# 固定演示别名（联盟 6 角色 + 用户 2 角色），顺序即 get_accounts() 的顺序
# 学习者（0xlearner）已合并原 Alice（0xalice）身份：合约部署者 + 低碳个人用户；
# 0xalice / 0xbob 均无业务引用已下线，不再作为演示别名存在（历史密钥库残留条目自然废弃）。
DEMO_ALIASES: List[str] = [
    # 索引 0-5：联盟角色
    "0xadmin", "0xmetro", "0xbus", "0xbike", "0xtakeout", "0xrecycle",
    # 索引 6-7：用户角色（学习者 / NFT 铸造）
    "0xlearner", "0xnft",
]

_lock = threading.RLock()
# 内存缓存：alias -> (address, private_key_hex)；解密后的私钥仅供进程内签名使用
_cache: Dict[str, Tuple[str, str]] = {}
_pw_warned = False


def _password() -> str:
    """获取加密口令；未配置时使用兜底口令并告警（仅一次）。"""
    global _pw_warned
    pw = os.getenv(PASSWORD_ENV, "").strip()
    if pw:
        return pw
    if not _pw_warned:
        _pw_warned = True
        logger.warning(
            "[keystore] 未设置环境变量 %s，密钥库使用开发兜底口令加密，"
            "安全性降低；生产/正式环境请务必在 .env 中配置 %s",
            PASSWORD_ENV, PASSWORD_ENV,
        )
    return _FALLBACK_PASSWORD


def _load_file() -> Dict:
    """读取密钥库文件；不存在时返回空结构。"""
    if not KEYSTORE_FILE.exists():
        return {"version": 1, "accounts": {}}
    try:
        with KEYSTORE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data.get("accounts"), dict):
            raise ValueError("keystore.json 结构损坏")
        return data
    except Exception as e:
        raise RuntimeError(f"密钥库文件读取失败 {KEYSTORE_FILE}: {e}") from e


def _save_file(data: Dict) -> None:
    """原子写入密钥库文件（临时文件 + rename，避免半写状态）。"""
    KEYSTORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = KEYSTORE_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, KEYSTORE_FILE)
    try:
        # 密钥库含加密私钥，收紧文件权限（POSIX 生效，Windows 忽略失败）
        os.chmod(KEYSTORE_FILE, 0o600)
    except Exception:
        pass


def _normalize_alias(alias: str) -> str:
    return (alias or "").strip().lower()


def get_or_create_account(alias: str) -> Tuple[str, str]:
    """获取别名对应的账户，不存在则随机生成并加密持久化。

    返回 (address, private_key_hex)。同一别名永远对应同一地址；
    不同别名（含任意未知钱包别名）永远对应相互独立的密钥。
    """
    alias = _normalize_alias(alias)
    if not alias:
        raise ValueError("钱包别名不能为空")
    with _lock:
        if alias in _cache:
            return _cache[alias]
        data = _load_file()
        entry = data["accounts"].get(alias)
        if entry and entry.get("keystore"):
            try:
                pk_bytes = Account.decrypt(entry["keystore"], _password())
            except Exception as e:
                raise RuntimeError(
                    f"密钥库解密失败（别名 {alias}）：口令可能不正确或文件损坏，"
                    f"请检查环境变量 {PASSWORD_ENV}。原始错误: {e}"
                ) from e
            acct = Account.from_key(pk_bytes)
            addr = acct.address.lower()
            pk_hex = "0x" + acct.key.hex().removeprefix("0x")
            _cache[alias] = (addr, pk_hex)
            return addr, pk_hex
        # 不存在：随机生成新账户并加密落盘
        acct = Account.create()
        addr = acct.address.lower()
        pk_hex = "0x" + acct.key.hex().removeprefix("0x")
        encrypted = Account.encrypt(acct.key, _password())
        data["accounts"][alias] = {"address": addr, "keystore": encrypted}
        _save_file(data)
        _cache[alias] = (addr, pk_hex)
        logger.info("[keystore] 为别名 %s 生成新账户并加密落盘: %s", alias, addr)
        return addr, pk_hex


def get_account(alias: str) -> Optional[Tuple[str, str]]:
    """仅读取已存在的别名账户；不存在返回 None（不创建）。"""
    alias = _normalize_alias(alias)
    with _lock:
        if alias in _cache:
            return _cache[alias]
        if not KEYSTORE_FILE.exists():
            return None
        data = _load_file()
        if alias not in data["accounts"]:
            return None
    return get_or_create_account(alias)


def ensure_demo_accounts() -> List[Tuple[str, str]]:
    """确保固定演示别名全部存在于密钥库，返回 [(alias, address), ...]。

    首次运行（无密钥库文件/无口令）时自动生成并给出告警日志。
    """
    if not KEYSTORE_FILE.exists():
        logger.warning(
            "[keystore] 未发现密钥库文件 %s，将自动生成演示账户并加密落盘",
            KEYSTORE_FILE,
        )
    out: List[Tuple[str, str]] = []
    for alias in DEMO_ALIASES:
        addr, _pk = get_or_create_account(alias)
        out.append((alias, addr))
    return out


def list_aliases() -> List[str]:
    """列出密钥库中已存在的全部别名。"""
    with _lock:
        data = _load_file()
        return sorted(data["accounts"].keys())


def reset_keystore() -> None:
    """删除密钥库文件并清空内存缓存（供演示数据重置脚本使用）。

    注意：重置后所有账户地址都会重新生成，旧链上地址的余额/合约权限
    与新地址不再匹配，需要重新初始化链上数据。
    """
    with _lock:
        _cache.clear()
        if KEYSTORE_FILE.exists():
            KEYSTORE_FILE.unlink()
            logger.warning("[keystore] 已删除密钥库文件: %s", KEYSTORE_FILE)


# ===========================================================================
# 学生钱包（一人一钱包）：别名规范 stu:{user_id}
# ===========================================================================
# 学生钱包别名前缀：stu:{user_id}，如 stu:stu001（统一小写，与 _normalize_alias 一致）
STUDENT_ALIAS_PREFIX = "stu:"


def student_alias(user_id: str) -> str:
    """把 user_id 规范为学生钱包别名 `stu:{user_id}`。

    统一小写（与密钥库 _normalize_alias 口径一致），保证 user_info.wallet、
    密钥库、chain_client.resolve_account 三方对同一学生解析到同一账户。
    """
    uid = (user_id or "").strip()
    if not uid:
        raise ValueError("user_id 不能为空，无法生成学生钱包别名")
    return f"{STUDENT_ALIAS_PREFIX}{uid}".lower()


def has_account(alias: str) -> bool:
    """轻量判断别名是否已存在于密钥库（仅读文件结构，不解密私钥）。

    启动播种 / 登录发放路径的高频幂等检查用：避免对大量已存在学生钱包
    逐一执行昂贵的 scrypt 解密。
    """
    a = _normalize_alias(alias)
    with _lock:
        if a in _cache:
            return True
        if not KEYSTORE_FILE.exists():
            return False
        try:
            data = _load_file()
        except Exception:
            return False
        return a in data["accounts"]


def get_account_address(alias: str) -> Optional[str]:
    """轻量读取别名对应的链上地址（不解密私钥）；不存在返回 None。"""
    a = _normalize_alias(alias)
    with _lock:
        if a in _cache:
            return _cache[a][0]
        if not KEYSTORE_FILE.exists():
            return None
        try:
            data = _load_file()
        except Exception:
            return None
        entry = data["accounts"].get(a)
        if not entry:
            return None
        return (entry.get("address") or "").strip().lower() or None


def provision_student_wallet(user_id: str) -> Tuple[str, str]:
    """为学生发放专属钱包（一人一钱包），返回 (别名, 链上地址)。

    - 别名规范：stu:{user_id}（如 stu:stu001）；
    - 链上地址随机生成，私钥按现有加密方式（keystore v3）持久化；
    - 幂等：同一 user_id 已发放过则直接返回既有账户，不重复生成；
    - 仅操作本地密钥库，不触碰链节点，任何链模式下都可安全调用。
    """
    alias = student_alias(user_id)  # 空 user_id 在此抛 ValueError
    addr, _pk = get_or_create_account(alias)
    return alias, addr


def get_student_wallet(user_id: str) -> Optional[Tuple[str, str]]:
    """查询学生专属钱包；未发放返回 None，已发放返回 (别名, 链上地址)。"""
    uid = (user_id or "").strip()
    if not uid:
        return None
    try:
        alias = student_alias(uid)
    except ValueError:
        return None
    if not has_account(alias):
        return None
    addr = get_account_address(alias)
    if not addr:
        return None
    return alias, addr
