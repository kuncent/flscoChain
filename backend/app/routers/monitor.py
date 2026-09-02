"""合约调用监听器 API。

任务 #18 鉴权口径：contract_calls 是 per-学生 学习数据（含 args / result /
caller，带 _TENANT_COLS 归属列），三个端点均为 optional 鉴权 + 租户 scope
过滤 —— 登录时仅返回本人归属行 + 未登记旧行；未登录时退化为只读公共数据
（仅未登记旧行，tenant.scope_filter 统一构造），明确归属他人的调用记录
不可见。前端统一经 http.ts 注入 Bearer JWT，登录态页面行为不变。
"""
from __future__ import annotations

import json
from collections import Counter

from fastapi import APIRouter, HTTPException, Request

from ..db import get_conn
from ..tenant import request_uid, scope_filter

router = APIRouter(prefix="/api/monitor", tags=["monitor"])


@router.get("/{address}")
def monitor(address: str, request: Request):
    """返回某合约调用统计：总次数、各方法次数、最近调用（scope 过滤）。"""
    cond, sp = scope_filter("contract_calls", request_uid(request))
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM contract_calls WHERE contract_address=?"
            + (" AND " + cond if cond else "")
            + " ORDER BY id DESC LIMIT 500",
            (address, *sp),
        ).fetchall()
    if not rows:
        return {"address": address, "total": 0, "methods": {}, "recent": []}
    methods = Counter(r["method"] for r in rows)
    return {
        "address": address,
        "total": len(rows),
        "methods": dict(methods),
        "recent": [dict(r) for r in rows[:50]],
    }


@router.get("/{address}/methods")
def methods_stat(address: str, request: Request):
    """各方法调用次数统计（scope 过滤，口径同 monitor）。"""
    cond, sp = scope_filter("contract_calls", request_uid(request))
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT method, COUNT(*) AS count FROM contract_calls WHERE contract_address=?"
            + (" AND " + cond if cond else "")
            + " GROUP BY method",
            (address, *sp),
        ).fetchall()
    return {"address": address, "methods": [dict(r) for r in rows]}


@router.get("/{address}/recent")
def recent(address: str, request: Request, limit: int = 50):
    """最近调用明细（scope 过滤，口径同 monitor）。"""
    cond, sp = scope_filter("contract_calls", request_uid(request))
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM contract_calls WHERE contract_address=?"
            + (" AND " + cond if cond else "")
            + " ORDER BY id DESC LIMIT ?",
            (address, *sp, limit),
        ).fetchall()
    return {"items": [dict(r) for r in rows]}
