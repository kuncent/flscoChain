"""合约调用监听器 API。"""
from __future__ import annotations

import json
from collections import Counter

from fastapi import APIRouter, HTTPException

from ..db import get_conn

router = APIRouter(prefix="/api/monitor", tags=["monitor"])


@router.get("/{address}")
def monitor(address: str):
    """返回某合约调用统计：总次数、各方法次数、最近调用。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM contract_calls WHERE contract_address=? ORDER BY id DESC LIMIT 500",
            (address,),
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
def methods_stat(address: str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT method, COUNT(*) AS count FROM contract_calls WHERE contract_address=? GROUP BY method",
            (address,),
        ).fetchall()
    return {"address": address, "methods": [dict(r) for r in rows]}


@router.get("/{address}/recent")
def recent(address: str, limit: int = 50):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM contract_calls WHERE contract_address=? ORDER BY id DESC LIMIT ?",
            (address, limit),
        ).fetchall()
    return {"items": [dict(r) for r in rows]}
