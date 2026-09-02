"""_compute_training_score 测试：4 维公式 / min(100,...) 封顶 /
tutorial_done*8 计入 / 空库全 0 不报错 / 一人一钱包候选口径隔离。

临时数据直接 INSERT 进隔离库（learning_events / deployed_contracts /
chain_tutorial_progress / eco_energy_records 等），链路即 grades →
learning.events.aggregate → get_conn()。
"""
from app.db import get_conn, now
from app.learning.tutorial_engine import _upsert_step_state
from app.routers.grades import TRAINING_WEIGHTS, _compute_training_score

W = "0xlearner"


def _events(conn, event_type, n, wallet=W):
    for _ in range(n):
        conn.execute(
            "INSERT INTO learning_events(wallet,event_type,target,ref_id,extra,created_at) "
            "VALUES(?,?,?,?,?,?)", (wallet, event_type, "", "", "{}", now()))


def _rows(conn, sql, rows):
    conn.executemany(sql, rows)

class TestTrainingScore:
    def test_empty_wallet_returns_zero_with_detail(self, temp_db):
        score, detail = _compute_training_score("")
        assert score == 0.0
        assert set(detail) == set(TRAINING_WEIGHTS)
        for dim, d in detail.items():
            assert d["score"] == 0 and d["weight"] == TRAINING_WEIGHTS[dim]
            assert d["metrics"] == {}

    def test_empty_db_all_zero_no_error(self, temp_db):
        score, detail = _compute_training_score(W)
        assert score == 0.0
        for dim in ("chain_setup", "contract_dev", "chain_verify", "alliance_gov"):
            assert detail[dim]["score"] == 0
            assert all(v == 0 for v in detail[dim]["metrics"].values())
    def test_full_formula_4_dimensions(self, temp_db):
        with get_conn() as conn:
            for et, n in (("ide_open_builtin", 2), ("ide_save_project", 1),
                          ("contract_compile_ok", 3), ("interface_invoke", 4),
                          ("eco_role_switch", 1), ("report_view", 2)):
                _events(conn, et, n)
            _rows(conn, "INSERT INTO deployed_contracts(address,name,abi,deployer,created_at) VALUES(?,?,?,?,?)",
                  [("0xc%d" % i, "C", "[]", W, now()) for i in range(2)])
            _rows(conn, "INSERT INTO contract_calls(contract_address,method,caller,created_at) VALUES(?,?,?,?)",
                  [("0xc1", "balanceOf", W, now())] * 2)
            _rows(conn, "INSERT INTO transactions(hash,block_number,from_addr,to_addr,timestamp) VALUES(?,?,?,?,?)",
                  [("0xt1", 1, W, "0xother", 1)])
            _rows(conn, "INSERT INTO nfts(token_id,standard,contract_address,author,owner,created_at) VALUES(?,?,?,?,?,?)",
                  [("1", "ERC721", "0xc1", W, W, now())])
            _rows(conn, "INSERT INTO nft_trades(token_id,from_addr,to_addr,created_at) VALUES(?,?,?,?)",
                  [("1", W, "0xother", now())])
            _rows(conn, "INSERT INTO wallet_transfers(token_address,from_addr,to_addr,amount,created_at) VALUES(?,?,?,?,?)",
                  [("0xc1", W, "0xother", "10", now())])
            _rows(conn, "INSERT INTO eco_energy_records(wallet,role_key,role_name,action,points,created_at) VALUES(?,?,?,?,?,?)",
                  [(W, "metro", "地铁集团", "地铁通勤", 50, now()),
                 (W, "bus", "公交集团", "公交出行", 20, now())])
        for s in (1, 2, 3):
            _upsert_step_state(W, s, 1, finished=True, cmd_idx=0)

        score, detail = _compute_training_score(W)
        assert detail["chain_setup"]["score"] == 44.0
        assert detail["contract_dev"]["score"] == 65.0
        assert detail["chain_verify"]["score"] == 31.0
        assert detail["alliance_gov"]["score"] == 49.0
        assert score == 48.3
    def test_cap_at_100(self, temp_db):
        with get_conn() as conn:
            _events(conn, "ide_save_project", 15)
        score, detail = _compute_training_score(W)
        assert detail["chain_setup"]["score"] == 100.0
        assert detail["chain_setup"]["metrics"]["ide_save_project"] == 15
        assert score == 20.0
    def test_tutorial_done_counts_8_each(self, temp_db):
        for s in (1, 2, 3):
            _upsert_step_state(W, s, 1, finished=True, cmd_idx=0)
        _, detail = _compute_training_score(W)
        cs = detail["chain_setup"]
        assert cs["metrics"]["tutorial_done"] == 3
        assert cs["score"] == 24.0
    def test_incomplete_steps_not_counted(self, temp_db):
        _upsert_step_state(W, 1, 1, finished=True, cmd_idx=0)
        _upsert_step_state(W, 2, 0, finished=False, cmd_idx=0)
        _, detail = _compute_training_score(W)
        assert detail["chain_setup"]["metrics"]["tutorial_done"] == 1

    def test_foreign_wallet_not_merged_with_learner(self, temp_db):
        """一人一钱包隔离：查询他人钱包不得并入 0xlearner 演示数据
        （旧口径候选集恒含 0xlearner 导致跨账号成绩/进度相同，已修复）。"""
        with get_conn() as conn:
            _events(conn, "ide_open_builtin", 2)
        _, detail = _compute_training_score("0xghost")
        assert detail["chain_setup"]["score"] == 0.0
