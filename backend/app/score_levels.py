"""分数等级阈值 · 单一事实源（修 P3-16「文档与代码档位不一致」+ P2-22「成绩页与报告页两套阈值」）。

背景（为什么必须有这个模块）：
  1. 旧实现把档位写在 report.py 的 if/elif 里（90/75/60/40），而 report.py 顶部文档、
     师生手册、报告页「卓越！」提示都写着「卓越 ≥90 / 优秀 80~89 / …」。结果是学生
     做完九维拿到 100 分，页面等级仍是「优秀 🏆」——最高档在代码里根本不可达；
  2. 成绩页 Grades.vue 另写一套 90/80/60 三档色阶，同一个 65 分在两个页面读数不同，
     学生按颜色理解等级必然误判。

口径（本模块是唯一来源，改档位必须同步 frontend/src/utils/score.ts）：
  卓越 ≥90 / 优秀 80~89 / 良好 70~79 / 合格 60~69 / 待完善 40~59 / 未完成 <40
  综合成绩、实训成绩、教师评分、报告总分**共用这一套**：都是 0~100 的同尺度分数，
  没有理由各用一套阈值。

色值取自产品设计系统 frontend/src/styles/global.scss 的颜色令牌（手册配色同源）：
  --dq-primary #00e6c3 / --dq-success #2dd4bf / --dq-info #4d8dff / --dq-warn #ffcf4d /
  待完善用橙 #ff9500（介于 warn 与 error 之间的过渡档）/ --dq-error #ff5470
"""
from __future__ import annotations

from typing import Any

# 从高到低排列，最后一档 min=0 兜底。key 是稳定标识（前端 CSS 类名 / 埋点用它，
# 不得随文案改动）；badge 是给人看的带图标文案，直接给前端与 Markdown 渲染。
SCORE_LEVELS: tuple[dict[str, Any], ...] = (
    {"min": 90, "key": "supreme",    "name": "卓越",   "badge": "卓越 🏆",    "color": "#00e6c3"},
    {"min": 80, "key": "excellent",  "name": "优秀",   "badge": "优秀 🥇",    "color": "#2dd4bf"},
    {"min": 70, "key": "good",       "name": "良好",   "badge": "良好 🥈",    "color": "#4d8dff"},
    {"min": 60, "key": "pass",       "name": "合格",   "badge": "合格 ✅",    "color": "#ffcf4d"},
    {"min": 40, "key": "improving",  "name": "待完善", "badge": "待完善 🚧",  "color": "#ff9500"},
    {"min": 0,  "key": "unfinished", "name": "未完成", "badge": "未完成 ❌",  "color": "#ff5470"},
)


def level_of(total: Any) -> dict[str, Any]:
    """分数 → 档位字典（非数字 / None 一律按 0 处理，落到「未完成」而非抛错）。"""
    try:
        v = float(total if total is not None else 0)
    except (TypeError, ValueError):
        v = 0.0
    for lv in SCORE_LEVELS:
        if v >= lv["min"]:
            return lv
    return SCORE_LEVELS[-1]


def badge_of(total: Any) -> str:
    """给人看的等级文案（含图标），报告页 / Markdown 报告同用。"""
    return str(level_of(total)["badge"])


def with_level(payload: dict[str, Any], key: str = "total") -> dict[str, Any]:
    """给响应体补一组等级字段：level（文案）/ level_key / level_color。

    前端只认这三个键即可，不再自己写阈值；老客户端继续读 level 字符串，向后兼容。
    """
    lv = level_of(payload.get(key))
    payload["level"] = lv["badge"]
    payload["level_key"] = lv["key"]
    payload["level_color"] = lv["color"]
    return payload
