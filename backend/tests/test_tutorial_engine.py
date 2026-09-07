"""tutorial_engine 测试：_match_command 正反用例 / 进度 upsert 幂等 /
TUTORIAL 10 步结构完整性 / 跨步骤与步骤内命令顺序校验。

顺序校验走 exec_command_impl 真实链路（mock 链、管理员代操作身份），
前置状态用 _upsert_step_state 构造（顺带覆盖懒建表逻辑）。
"""
import re

import pytest
from app.db import get_conn
from app.learning.tutorial_engine import (
    _match_command, _upsert_step_state, exec_command_impl,
)
from app.learning.tutorial_steps import ROLE_ENERGY_RULES, TUTORIAL
from app.wallet_id import address_variants, to_address

STEP1_CMD1 = ("curl -#LO https://github.com/FISCO-BCOS/FISCO-BCOS/releases/"
              "download/v2.9.1/build_chain.sh && chmod +x build_chain.sh")
STEP1_CMD_LAST = "bash nodes/127.0.0.1/start_all.sh"
STEP2_CMD1 = "ps -ef | grep fisco-bcos | grep -v grep"
STEP2_CMD2 = "ls nodes/127.0.0.1/"
ADMIN_USER = {"user_id": "", "user_name": "", "role_id": 1,
              "wallet": "", "class_id": ""}


def _exec(step, command, wallet="0xlearner"):
    return exec_command_impl(
        {"step": step, "command": command, "wallet": wallet}, dict(ADMIN_USER))


def _progress_row(wallet, step):
    """双口径读进度行：写侧统一落真实链上地址，测试仍按别名调用。"""
    marks = ",".join("?" * len(address_variants(wallet)))
    addr = to_address(wallet).lower()
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM chain_tutorial_progress "
            f"WHERE lower(wallet) IN ({marks}) AND step=?",
            (*address_variants(wallet), step)).fetchall()
    if not rows:
        return None
    hit = next((r for r in rows if str(r["wallet"] or "").lower() == addr), rows[0])
    return dict(hit)


def _mark_done(wallet, step, cmd_idx):
    _upsert_step_state(wallet, step, 1, output="ok", finished=True, cmd_idx=cmd_idx)

@pytest.fixture(autouse=True)
def _progress_table(temp_db):
    # order checks SELECT chain_tutorial_progress directly (no write yet),
    # so the lazy CREATE TABLE is never reached; pre-create it here.
    from app.learning.tutorial_engine import _ensure_progress_table
    _ensure_progress_table()

class TestMatchCommand:
    def test_empty_input_rejected(self):
        r = _match_command("   ", 1)
        assert r["ok"] is False and "不能为空" in r["hint"]

    def test_comment_line_passes_without_cmd_index(self):
        r = _match_command("# 只是注释", 1)
        assert r["ok"] is True and r["type"] == "comment" and r["cmd_index"] == -1

    def test_step1_syntax_ok(self):
        r = _match_command(STEP1_CMD1, 1)
        assert r["ok"] is True and r["cmd_index"] == 0
        # start_all.sh 是展示清单的第 5 条：cmd_index 必须等于展示下标 4
        # （历史上注册表只登 3 条并把它的下标写成 2，导致步骤进度封顶 3/5）
        r2 = _match_command(STEP1_CMD_LAST, 1)
        assert r2["ok"] is True and r2["cmd_index"] == 4

    def test_step1_syntax_fail_with_hint(self):
        r = _match_command("rm -rf /", 1)
        assert r["ok"] is False and r["matched_pattern"] is None
        assert "语法格式" in r["hint"]

    def test_step2_syntax(self):
        r = _match_command(STEP2_CMD1, 2)
        assert r["ok"] is True and r["cmd_index"] == 0
        assert _match_command("ps aux", 2)["ok"] is False

    def test_step10_console_command(self):
        r = _match_command("[console] call GreenEnergy <address> balanceOf 0xlearner", 10)
        assert r["ok"] is True and r["cmd_index"] == 1

    def test_unknown_step_has_no_registry(self):
        r = _match_command("ls", 99)
        assert r["ok"] is False and "无可用命令定义" in r["hint"]
REQUIRED_FIELDS = {"step", "title", "desc", "principle", "commands",
                   "expected", "tip", "role_focus", "biz_note"}


class TestTutorialStructure:
    def test_ten_steps_in_order(self):
        assert len(TUTORIAL) == 10
        assert [s["step"] for s in TUTORIAL] == list(range(1, 11))

    def test_every_step_has_all_required_fields(self):
        for s in TUTORIAL:
            missing = REQUIRED_FIELDS - set(s)
            assert not missing, f"step {s['step']} 缺字段: {missing}"

    def test_commands_nonempty_and_textual(self):
        for s in TUTORIAL:
            cmds = s["commands"]
            assert isinstance(cmds, list) and cmds
            assert all(isinstance(c, str) and c.strip() for c in cmds)

    def test_text_fields_meaningful(self):
        for s in TUTORIAL:
            for k in ("principle", "expected", "tip", "role_focus", "biz_note"):
                assert len(s[k].strip()) >= 4, f"step {s['step']}.{k} 过短"

    def test_role_energy_rules_derived_from_roles(self):
        from app.learning.alliance_roles import ROLES
        assert len(ROLE_ENERGY_RULES) == len(ROLES) == 6
        by_wallet = {r["wallet"]: r for r in ROLE_ENERGY_RULES}
        for role in ROLES:
            rule = by_wallet[role["wallet"]]
            assert rule["role"] == f"{role['icon']} {role['name']}({role['wallet'][2:]})"
            er = role.get("energy_rule")
            assert rule["amount"] == (f"+{er['points']} 能量" if er else "0 / 次")
            assert rule["scene"].strip()

class TestStepStateUpsert:
    def test_repeated_upsert_is_idempotent(self, temp_db):
        _upsert_step_state("0xlearner", 1, 1, output="v1", finished=True, cmd_idx=2)
        _upsert_step_state("0xlearner", 1, 1, output="v2", finished=True, cmd_idx=2)
        marks = ",".join("?" * len(address_variants("0xlearner")))
        with get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM chain_tutorial_progress "
                f"WHERE lower(wallet) IN ({marks}) AND step=?",
                (*address_variants("0xlearner"), 1)).fetchall()
        assert len(rows) == 1, "UNIQUE(wallet, step) 下重复 upsert 不得产生多行"
        row = rows[0]
        # 写入口径：进度行的 wallet 必须是真实链上地址（不带别名 / 分隔符）
        assert row["wallet"] == to_address("0xlearner")
        assert row["done"] == 1 and row["cmd_idx"] == 2
        assert row["finished_at"] and row["started_at"]

    def test_in_progress_state_tracks_cmd_idx(self, temp_db):
        _upsert_step_state("0xlearner", 2, 0, output="p1", finished=False, cmd_idx=0)
        _upsert_step_state("0xlearner", 2, 0, output="p2", finished=False, cmd_idx=1)
        row = _progress_row("0xlearner", 2)
        assert row["done"] == 0 and row["cmd_idx"] == 1
        assert row["started_at"] and not row["finished_at"]
        assert row["output"] == "p2"

    def test_per_wallet_isolation(self, temp_db):
        _mark_done("0xa", 1, 0)
        _mark_done("0xb", 1, 0)
        assert _progress_row("0xa", 1)["done"] == 1
        assert _progress_row("0xb", 1)["wallet"] == "0xb"

    def test_user_class_coalesce_keeps_old(self, temp_db):
        _upsert_step_state("0xc", 1, 0, finished=False, cmd_idx=0,
                           user_id="u1", class_id="cls1")
        _upsert_step_state("0xc", 1, 1, output="done", finished=True, cmd_idx=0,
                           user_id="", class_id="")
        row = _progress_row("0xc", 1)
        assert row["user_id"] == "u1" and row["class_id"] == "cls1"

class TestCommandOrderValidation:
    def test_cross_step_blocked_without_prev_done(self, temp_db):
        r = _exec(2, STEP2_CMD1)
        assert r["ok"] is False and r["error_type"] == "order"
        assert "步骤顺序错误" in r["output"]
        assert "步骤 1" in r["output"]
    def test_cross_step_allowed_after_prev_done(self, temp_db):
        _mark_done("0xlearner", 1, 4)
        r = _exec(2, STEP2_CMD1)
        assert r["ok"] is True and r["error_type"] is None
        assert r["cmd_index"] == 0 and r["step_completed"] is False
        row = _progress_row("0xlearner", 2)
        assert row["cmd_idx"] == 0 and row["done"] == 0
    def test_in_step_order_blocked(self, temp_db):
        r = _exec(1, STEP1_CMD_LAST)
        assert r["ok"] is False and r["error_type"] == "order"
        assert "命令顺序错误" in r["output"]
    def test_in_step_sequential_first_ok(self, temp_db):
        r = _exec(1, STEP1_CMD1)
        assert r["ok"] is True and r["cmd_index"] == 0
        assert r["step_completed"] is False and r["progress"] == 1
        assert _progress_row("0xlearner", 1)["cmd_idx"] == 0
    def test_step_completes_after_last_command(self, temp_db):
        # Registry is now aligned with the displayed command list (see
        # test_every_displayed_command_is_matchable_in_list_order), so any
        # step can be finished by typing exactly what the UI shows.
        for s in (1, 2, 3, 4):
            _mark_done("0xlearner", s, 0)
        for cmd in TUTORIAL[4]["commands"]:
            r = _exec(5, cmd)
            assert r["ok"] is True and r["error_type"] is None
        assert r["step_completed"] is True
        row = _progress_row("0xlearner", 5)
        assert row["done"] == 1 and row["finished_at"]
    def test_syntax_error_checked_before_order(self, temp_db):
        r = _exec(1, "rm -rf /")
        assert r["error_type"] == "syntax"
        assert _progress_row("0xlearner", 1) is None
    def test_invalid_step(self, temp_db):
        r = _exec(99, "ls")
        assert r["ok"] is False and r["error_type"] == "invalid_step"


class TestDisplayedCommandCoverage:
    """UI 展示清单与命令注册表必须一一对应（P0 回归）。

    历史缺陷：注册表只覆盖展示清单的一部分且 cmd_index 错位（Step 1 展示 5 条
    只注册 3 条，start_all.sh 注册为 idx=2 而展示下标是 4），而步骤完成判定是
    「new_idx >= len(commands) - 1」→ 学生照屏幕逐条敲也会被卡死，10 步教程
    （D 项 10 分）一步都做不完。
    """

    def test_every_displayed_command_is_matchable_in_list_order(self):
        for item in TUTORIAL:
            shown = item.get("commands") or []
            for i, cmd in enumerate(shown):
                m = _match_command(cmd, item["step"])
                assert m["ok"], f"Step {item['step']} 第 {i + 1} 条展示命令判为语法错误: {cmd}"
                hit = m["cmd_index"]
                # 文本重复的命令（Step 10 首尾各一次 balanceOf）正则按首次出现返回
                # 下标，执行时由 exec_command_impl 的重复命令兼容推进；其余必须同序
                assert hit == i or shown[hit].strip() == cmd.strip(), (
                    f"Step {item['step']} 第 {i + 1} 条命令的 cmd_index={hit}，"
                    f"与展示下标不一致（顺序校验会与屏幕清单不同序）"
                )

    def test_step1_finishes_by_typing_displayed_commands_only(self, temp_db):
        for cmd in TUTORIAL[0]["commands"]:
            r = _exec(1, cmd)
            assert r["ok"] is True, r["output"][:80]
        assert r["step_completed"] is True and r["progress"] == 5
        assert _progress_row("0xlearner", 1)["done"] == 1

    def test_typed_command_with_single_space_instead_of_double_still_ok(self):
        # 展示清单里的 tail 命令含连续空格（日志名与管道之间），手敲只打一个空格也要过
        shown = next(c for c in TUTORIAL[2]["commands"] if c.startswith("tail -n"))
        loose = re.sub(r"\s+", " ", shown).strip()
        assert "  " not in loose
        assert _match_command(loose, 3)["ok"] is True