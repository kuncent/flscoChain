"""钱包口径归一（资产侧唯一事实源：真实链上地址 0x + 40 位十六进制）。

为什么需要这一层（修「资产钱包里出现 stu:0ae7783d-d59d-40e1-… 这种带冒号/
连字符的内部别名」）：
  - 证书归属、勋章持有、能量流水、市场挂牌/成交、角色绑定这些**资产台账**，
    在真实商业与真实链上只认一个东西：账户地址。内部别名（`stu:{userId}`、
    裸 user_id、uuid）是登录体系的产物，写进资产表会让同一人出现四套归属口径
    （P0-2 的根因），前端也无法复制 / 上链核对；
  - 链上交易记录（transactions.from_addr / to_addr）本来就是真实地址，资产表
    存别名导致「链上账」和「库内账」永远对不上（P0-3）。

因此本模块提供全站唯一的归一函数，边界口径：
  - **写入与查询资产相关表**（eco_* 全部钱包列、令牌归属、能量流水）一律先经
    `to_address()` 变成真实地址；
  - **展示层**仍可看友好别名（`label_of()`），但跳转 / 复制 / 上链核对必须用地址；
  - 解析失败（密钥库不可用 / 口令错误）**降级返回原值小写**，读路径绝不抛异常，
    宁可暂时保留旧口径也不能让页面 500。

依赖约束：只依赖 keystore，禁止 import db / routers / eco（避免循环导入）。
"""
from __future__ import annotations

import re
import threading
from typing import Dict, Optional, Tuple

# 真实 EVM 地址形态：0x + 40 位十六进制（全站唯一的「真实地址」判定）
_ADDR_RE = re.compile(r"^0x[0-9a-f]{40}$")

# 别名 → 地址的进程内记忆表：`_norm_wallet` 处在查询热路径上，
# 每次都读 keystore.json 会把每次列表查询变成文件 IO。
_memo: Dict[str, str] = {}
# 地址 → 别名（用于展示友好名与按地址反查私钥）
_reverse: Optional[Dict[str, str]] = None
_lock = threading.RLock()


def is_address(value: str) -> bool:
    """是否为真实链上地址（0x + 40 位十六进制，大小写不敏感）。"""
    return bool(_ADDR_RE.match((value or "").strip().lower()))


def normalize_raw(value: str) -> str:
    """仅做空白与大小写规范化（不涉及密钥库，供纯字符串比较使用）。"""
    return (value or "").strip().lower()


def _lookup_alias(alias: str) -> str:
    """查密钥库中该别名的真实地址；不创建账户、不解密私钥。失败返回空串。"""
    try:
        from . import keystore as ks
        return ks.get_account_address(alias) or ""
    except Exception:
        return ""


def _student_wallet_addr(value: str) -> str:
    """按「一人一钱包」规范查 user_id 的学生钱包地址；不适用 / 未发放返回空串。

    历史数据里同一学生可能同时存在 `stu:{uid}`（登录后发放的正式钱包）与
    裸 `{uid}`（早期链上写入时按需建号的残留）两套密钥，资产归属必须以
    **学生钱包**为准，否则迁移会把人拆成两个地址。
    演示别名（0x 开头，如 0xlearner）不参与该规则：密钥库里存在
    `stu:0xlearner` 这类脏条目，绝不能盖掉 0xlearner 自己的地址。
    """
    if value.startswith("stu:") or value.startswith("0x"):
        return ""
    try:
        from . import keystore as ks
        return ks.get_account_address(ks.student_alias(value)) or ""
    except Exception:
        return ""


def to_address(value: str, *, create: bool = False) -> str:
    """把任意钱包口径（真实地址 / 演示别名 / stu: 别名 / user_id）归一为真实地址。

    - 已是真实地址 → 原样小写返回；
    - 密钥库已有该别名 → 返回其地址（只读，无副作用）；
    - user_id（含 uuid）→ 优先取「一人一钱包」的 `stu:{uid}` 地址，其次取同名
      别名地址；`stu:{uid}` 未发放 → 再按去掉前缀的 uid 查一次；
    - 查不到且 `create=True` → 在密钥库为其生成专属账户（写路径用，与链上
      `resolve_account` 的按需建号行为一致，保证别名与地址一一对应）；
    - 查不到且 `create=False` → 降级返回规范化原值（读路径不建号、不抛异常）。
    """
    raw = normalize_raw(value)
    if not raw:
        return ""
    with _lock:
        hit = _memo.get(raw)
    if hit:
        return hit
    if is_address(raw):
        resolved = raw
    else:
        # 学生钱包优先（同一人多口径必须收敛到同一个地址），再退回同名别名
        resolved = _student_wallet_addr(raw) or _lookup_alias(raw)
        if not resolved and raw.startswith("stu:"):
            resolved = _lookup_alias(raw[4:])
        if not resolved and create:
            try:
                from . import keystore as ks
                resolved = ks.get_or_create_account(raw)[0]
            except Exception:
                resolved = ""
    out = resolved or raw
    with _lock:
        _memo[raw] = out
    return out


def to_addresses(values) -> list:
    """批量归一（去重保序，过滤空值）：候选集 / IN 查询用。"""
    out: list = []
    for v in (values or []):
        a = to_address(v if isinstance(v, str) else str(v or ""))
        if a and a not in out:
            out.append(a)
    return out


def address_variants(value: str) -> Tuple[str, ...]:
    """某钱包口径的**全部合法标识**（原值 + 真实地址），兼容迁移前的历史行。

    读侧用 `lower(col) IN (?)` 命中两种口径；写侧只写 `to_address()` 的结果。
    """
    raw = normalize_raw(value)
    if not raw:
        return ()
    addr = to_address(raw)
    return tuple(dict.fromkeys([raw, addr]))


def alias_of(address: str) -> str:
    """真实地址 → 友好别名（`0xmetro` / `stu:tzs001`）；未登记返回空串。

    用于展示「机构钱包 0xmetro（0x44bf…a4c6dda）」与链上交易按地址反查身份。
    """
    a = normalize_raw(address)
    if not a:
        return ""
    global _reverse
    with _lock:
        if _reverse is None:
            _reverse = _build_reverse_index()
        hit = _reverse.get(a)
    if hit:
        return hit
    # 记忆表已有但反查索引未覆盖（本次运行内新建的账户）：补一次单点查
    for alias, addr in list(_memo.items()):
        if addr == a:
            with _lock:
                if _reverse is not None:
                    _reverse[a] = alias
            return alias
    return ""


def _build_reverse_index() -> Dict[str, str]:
    """全量扫描密钥库建 地址→别名 索引（首次调用时一次 IO，之后常驻内存）。"""
    idx: Dict[str, str] = {}
    try:
        from . import keystore as ks
        with ks._lock:  # noqa: SLF001 - 仅为读文件时的加锁一致性
            data = ks._load_file()  # noqa: SLF001
        accounts = data.get("accounts") or {}
        for alias, entry in accounts.items():
            addr = normalize_raw(str((entry or {}).get("address") or ""))
            if not addr:
                continue
            # 演示短别名优先于 stu: 长别名（同一地址展示时取更好看的那个）
            cur = idx.get(addr)
            if not cur or (cur.startswith("stu:") and not str(alias).startswith("stu:")):
                idx[addr] = normalize_raw(str(alias))
    except Exception:
        return {}
    return idx


def reset_reverse_index() -> None:
    """密钥库被重建 / 重置后清缓存（演示数据重置脚本调用）。"""
    global _reverse
    with _lock:
        _memo.clear()
        _reverse = None


def short(value: str, head: int = 6, tail: int = 4) -> str:
    """地址短显（0x1234…abcd）；非地址原样返回。"""
    v = (value or "").strip()
    if not is_address(v):
        return v
    return f"{v[:head + 2]}…{v[-tail:]}"


def label_of(value: str) -> str:
    """展示口径：真实地址（短显），别名放括号里，便于人工核对。"""
    v = normalize_raw(value)
    if not v:
        return ""
    if is_address(v):
        al = alias_of(v)
        return f"{short(v)}（{al}）" if al and al != v else short(v)
    addr = to_address(v)
    return f"{v}（{short(addr)}）" if is_address(addr) else v
