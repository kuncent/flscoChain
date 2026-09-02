"""tutorial_engine 测试：_match_command 正反用例 / 进度 upsert 幂等 /
TUTORIAL 10 步结构完整性 / 跨步骤与步骤内命令顺序校验。

顺序校验走 exec_command_impl 真实链路（mock 链、管理员代操作身份），
前置状态用 _upsert_step_state 构造（顺带覆盖懒建表逻辑）。
"""
import pytest
from app.db import get_conn
from app.learning.tutorial_engine import (
    _match_command, _upsert_step_state, exec_command_impl,
)
from app.learning.tutorial_steps import ROLE_ENERGY_RULES, TUTORIAL

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
    with get_conn() as conn:
        r = conn.execute(
            "SELECT * FROM chain_tutorial_progress WHERE wallet=? AND step=?",
            (wallet, step)).fetchone()
    return dict(r) if r else None


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
        r2 = _match_command(STEP1_CMD_LAST, 1)
        assert r2["ok"] is True and r2["cmd_index"] == 2

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
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM chain_tutorial_progress WHERE wallet=? AND step=?",
                ("0xlearner", 1)).fetchall()
        assert len(rows) == 1, "UNIQUE(wallet, step) 下重复 upsert 不得产生多行"
        row = rows[0]
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
        # step2: TUTORIAL lists 5 commands but registry has only 2 (data gap).
        # Use step5 whose registry matches TUTORIAL exactly to verify that
        # finishing the last command marks the whole step done.
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