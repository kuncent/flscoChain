"""分数等级六档 + 报告/微任务口径一致性回归测试。

覆盖编写师生使用手册时逐条真机核对发现的 4 个阻塞性问题：
  P3-16  满分 100 仍显示「优秀 🏆」——最高档「卓越」在旧 if/elif（90/75/60/40）里不可达，
         与 report.py 顶部文档、报告页「卓越！」提示、两本手册全部对不上；
  P2-22  成绩页 Grades.vue 写 90/80/60、报告页写 90/75/60/40，同一个 65 分两个页面读数不同；
  P2-23  D 项已封顶 10 分时仍建议学生「故意制造失败拿探索加分」（恒为 0 分，误导）；
  P2-24  A 项协议分布剩余分因三元与 `+` 的优先级算错（三种标准全缺时只报 +3，实际可拿 +10）；
  P2-25  微任务 eco_t2 与报告 E 项角色多样性口径分裂：真机同一学生「E 项 6/6 满分、T2 却 5/6 未达标」。
"""
from __future__ import annotations

from app import score_levels
from app.db import get_conn
from app.learning.events import EventType, track
from app.learning.role_diversity import experienced_roles
from app.routers import report as report_mod
from app.routers.missions import _verify_task

STU = "0x017f9f6f706d99b8e0697b8dccca2dd3e95cd366"
UID = "19898800030"


def _eco(**over):
    """一份「九维全满」的 eco 简报（各维取满分的最低数据 + 零扣分）。"""
    eco = {
        "contracts": {k: {"deployed": True, "address": "0x" + "1" * 40}
                      for k in ("GreenEnergy", "PlantCertificate", "EcoBadge")},
        "behavior": {"ide_open_builtin": 5, "ide_save_project_sol": 1,
                     "contract_compile_ok": 3, "contract_compile_fail": 0,
                     "interface_invoke": 4},
        "tutorial_progress": {"done_count": 10, "total_steps": 10, "failed_count": 0,
                              "duration_tag": "normal"},
        "logs": {"error_count": 0, "warn_count": 0, "success_count": 50, "total": 50,
                 "error_rate": 0.0},
        "distinct_roles": 6, "role_switches": 12, "role_wallets": 6,
        "energy_distinct_roles": 5, "energy_issues": 8,
        "certificates": 3, "cert_distinct_species": 2,
        "badges": 2, "vouchers": 1, "tree_species": 3,
    }
    eco.update(over)
    return eco


def _perfect_score():
    return report_mod._calc_score(
        contract_count=5,
        std_breakdown={"ERC20": 2, "ERC721": 1, "ERC1155": 1},
        tx_count=19, nft_count=2, nft_trade_count=1, success_rate=100.0,
        eco=_eco(),
    )


# ---------------------------------------------------------------- 六档本身
def test_level_thresholds_six_tiers():
    """档位边界逐点锁死：卓越 ≥90 / 优秀 80~89 / 良好 70~79 / 合格 60~69 / 待完善 40~59 / 未完成 <40。"""
    cases = {
        100: "卓越 🏆", 90: "卓越 🏆", 89.5: "优秀 🥇", 80: "优秀 🥇",
        79: "良好 🥈", 70: "良好 🥈", 69: "合格 ✅", 60: "合格 ✅",
        59: "待完善 🚧", 40: "待完善 🚧", 39: "未完成 ❌", 0: "未完成 ❌",
    }
    for score, badge in cases.items():
        assert score_levels.badge_of(score) == badge, f"{score} 分档位错"
    # 非数字 / None 不得抛错，按 0 → 未完成
    assert score_levels.badge_of(None) == "未完成 ❌"
    assert score_levels.badge_of("-") == "未完成 ❌"
    assert score_levels.badge_of("85") == "优秀 🥇"


def test_level_scale_is_ordered_and_gapless():
    mins = [lv["min"] for lv in score_levels.SCORE_LEVELS]
    assert mins == sorted(mins, reverse=True)
    assert mins[-1] == 0
    keys = [lv["key"] for lv in score_levels.SCORE_LEVELS]
    assert len(set(keys)) == len(keys)


# ---------------------------------------------------------------- P3-16
def test_full_marks_report_is_supreme():
    """满分报告必须是「卓越 🏆」，且 level_key / level_color / level_scale 一并下发。"""
    score = _perfect_score()
    assert score["total"] == 100, score["breakdown"]
    assert score["level"] == "卓越 🏆"
    assert score["level_key"] == "supreme"
    assert score["level_color"] == "#00e6c3"
    assert [x["min"] for x in score["level_scale"]] == [90, 80, 70, 60, 40, 0]


def test_report_level_matches_score_levels_module():
    """报告等级只能来自 score_levels（不得再在 report.py 里写一套阈值）。"""
    for total, expect in ((95, "卓越 🏆"), (78, "良好 🥈"), (55, "待完善 🚧")):
        assert score_levels.badge_of(total) == expect


# ---------------------------------------------------------------- P2-23 / P2-24
def test_explore_suggestion_hidden_when_d_capped():
    """D 已封顶 10 分（教程 10/10）时，不得再建议「故意制造失败」。"""
    sgs = report_mod._suggestions(1, {"ERC20": 1, "ERC721": 1, "ERC1155": 1},
                                  19, 2, 1, 100.0, _eco())
    assert not [s for s in sgs if s["category"] == "D 搭链探索"]


def test_explore_suggestion_reports_real_capped_gain():
    """教程 6/10（步骤分 6）时探索加分最多只值 3 分，建议里必须写真实上限。"""
    eco = _eco(tutorial_progress={"done_count": 6, "total_steps": 10, "failed_count": 0,
                                  "duration_tag": "normal"})
    sgs = report_mod._suggestions(1, {"ERC20": 1, "ERC721": 1, "ERC1155": 1},
                                  19, 2, 1, 100.0, eco)
    explore = [s for s in sgs if s["category"] == "D 搭链探索"]
    assert len(explore) == 1
    assert explore[0]["gain"] == "+D ≤+3（计入 D 项质量分，封顶 10）"
    # 教程未做完时，D 主建议的提升值 = 封顶后的真实差值（10 - 6），不是理论值
    main = [s for s in sgs if s["category"] == "D 搭链教程"][0]
    assert main["gain"].startswith("+D 最多 +4")


def test_a_standard_remaining_gain_uses_explicit_sum():
    """三种 ERC 标准全缺时剩余 +10（旧写法因优先级只报 +3）。"""
    sgs = report_mod._suggestions(1, {}, 19, 2, 1, 100.0, _eco())
    a = [s for s in sgs if s["category"] == "A 合约部署"][0]
    assert a["gain"] == "+A ≤+10"
    # 只缺 ERC721 + ERC1155 时 = 3 + 4，且受 A 项 20 封顶
    sgs2 = report_mod._suggestions(1, {"ERC20": 1}, 19, 2, 1, 100.0, _eco())
    assert [s for s in sgs2 if s["category"] == "A 合约部署"][0]["gain"] == "+A ≤+7"


# ---------------------------------------------------------------- P2-25
def _seed_role_switches():
    """6 个角色的切换埋点：wallet 一律写**机构钱包**（学生点角色卡即切过去），只有 user_id 认人。

    另塞 1 条未知角色 resident（切回普通用户）——它不得计入多样性。
    """
    for role_key, org_wallet in (
        ("admin", "0xadmin"), ("metro", "0xmetro"), ("bus", "0xbus"),
        ("bike", "0xbike"), ("delivery", "0xdelivery"), ("recycle", "0xrecycle"),
    ):
        track(EventType.ECO_ROLE_SWITCH, target=role_key, wallet=org_wallet, user_id=UID)
    track(EventType.ECO_ROLE_SWITCH, target="resident", wallet=STU, user_id=UID)


def test_t2_and_report_e_agree_on_role_diversity(temp_db):
    """同一批行为，微任务 eco_t2 与报告 E 项必须给出一致的「体验过几种角色」。"""
    _seed_role_switches()

    eco = report_mod._load_eco_brief(STU, UID, candidates=[STU])
    assert eco["distinct_roles"] == 6, eco          # delivery/recycle 归一后计入

    with get_conn() as conn:
        v = _verify_task(conn, "eco_t2", STU, "?", [STU.lower()], cands=[STU], uid=UID)
    assert v["verified"] is True
    assert v["progress"] == "已切换体验 6/6 个联盟角色"


def test_role_diversity_ignores_unknown_and_counts_selection_table(temp_db):
    """eco_role_selections 的当前选择并入并集；未知角色不得虚增。"""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO eco_role_selections(wallet, role_key, selected_at) VALUES(?,?,?)",
            (STU.lower(), "recycling", "2026-09-07T00:00:00"),
        )
        rd = experienced_roles(conn, [STU], user_id=UID)
    assert rd["count"] == 1                        # 只有存量表里的 recycling
    assert rd["keys"] == {"recycling"}

    _seed_role_switches()
    with get_conn() as conn:
        rd2 = experienced_roles(conn, [STU], user_id=UID)
    assert rd2["count"] == 6
    assert "resident" not in rd2["keys"]
    assert rd2["switches"] == 7                    # 切换动作次数含切回普通用户


def test_role_diversity_single_wallet_scope_excludes_others(temp_db):
    """候选集只含本人钱包时（教师 per-wallet 单口径），不得把别人的角色切换算进来。"""
    track(EventType.ECO_ROLE_SWITCH, target="metro", wallet="0xmetro", user_id="22222")
    with get_conn() as conn:
        rd = experienced_roles(conn, [STU], user_id=UID)
    assert rd["count"] == 0
