"""learning.events 测试：track 唯一写入 + aggregate 计数一致性。"""
import json

from app.db import get_conn, now
from app.learning.events import EventType, aggregate, track

W = "0xlearner"
ALL_KEYS = {
    "ide_open_builtin", "ide_save_project", "contract_compile_ok",
    "interface_invoke", "eco_role_switch", "report_view",
    "deployed_contracts", "contract_calls", "transactions",
    "nft_mint", "nft_trade", "erc20_transfer", "energy_issue", "tutorial_done",
    "eco_market_trade",
}


class TestTrack:
    def test_track_persists_row(self, temp_db):
        track(EventType.IDE_OPEN_BUILTIN, target="ERC20.sol", wallet=W,
              ref_id="proj-1", extra={"src": "builtin", "note": "中文"})
        with get_conn() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM learning_events WHERE wallet=?", (W,)).fetchall()]
        assert len(rows) == 1
        row = rows[0]
        assert row["event_type"] == "ide_open_builtin"
        assert row["target"] == "ERC20.sol" and row["ref_id"] == "proj-1"
        assert json.loads(row["extra"]) == {"src": "builtin", "note": "中文"}
        assert row["created_at"]

    def test_track_extra_defaults_to_empty_json(self, temp_db):
        track(EventType.REPORT_VIEW, wallet=W)
        with get_conn() as conn:
            row = conn.execute(
                "SELECT extra FROM learning_events WHERE wallet=?", (W,)).fetchone()
        assert json.loads(row["extra"]) == {}

    def test_track_failure_does_not_raise(self, temp_db):
        with get_conn() as conn:
            conn.execute("DROP TABLE learning_events")
        track(EventType.IDE_SAVE_PROJECT, wallet=W)

class TestAggregate:
    def test_track_aggregate_consistency(self, temp_db):
        for _ in range(3):
            track(EventType.IDE_OPEN_BUILTIN, wallet=W)
        for _ in range(2):
            track(EventType.ECO_ROLE_SWITCH, wallet=W)
        track(EventType.REPORT_VIEW, wallet=W)
        m = aggregate(W)
        assert set(m) == ALL_KEYS
        assert m["ide_open_builtin"] == 3
        assert m["eco_role_switch"] == 2
        assert m["report_view"] == 1
        assert m["deployed_contracts"] == 0

    def test_aggregate_accepts_candidates_sequence(self, temp_db):
        track(EventType.INTERFACE_INVOKE, wallet=W)
        assert aggregate([W])["interface_invoke"] == 1
        assert aggregate(["0XLEARNER"])["interface_invoke"] == 1

    def test_aggregate_empty_candidates_all_zero(self, temp_db):
        track(EventType.IDE_OPEN_BUILTIN, wallet=W)
        m = aggregate([])
        assert set(m) == ALL_KEYS and all(v == 0 for v in m.values())

    def test_aggregate_tutorial_done_optional_table(self, temp_db):
        m = aggregate(W)
        assert m["tutorial_done"] == 0

    def test_aggregate_eco_market_trade_counts_sold_only(self, temp_db):
        """绿色市场成交计入联盟治理闭环：仅 status='sold' 且买/卖一方为该钱包才计数。"""
        with get_conn() as conn:
            conn.executemany(
                "INSERT INTO eco_market_listings(seller,asset_type,asset_id,asset_name,token_id,"
                "contract_address,standard,price_energy,status,buyer,tx_hash,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    # 我卖出成交 → 计 1
                    (W, "certificate", 1, "银杏证书", "1", "0xc1", "ERC721", 100, "sold", "0xbuyer", "0xt1", now()),
                    # 我买入成交 → 计 1
                    ("0xseller", "badge", 2, "生态勋章", "2", "0xc2", "ERC1155", 50, "sold", W, "0xt2", now()),
                    # 在售未成交 → 不计
                    (W, "voucher", 3, "骑行券", "3", "0xc2", "ERC1155", 20, "active", None, "", now()),
                    # 他人之间成交 → 不计（隔离）
                    ("0xa", "certificate", 4, "水杉证书", "4", "0xc1", "ERC721", 80, "sold", "0xb", "0xt3", now()),
                ])
        assert aggregate(W)["eco_market_trade"] == 2

    def test_aggregate_side_tables(self, temp_db):
        with get_conn() as conn:
            conn.executemany(
                "INSERT INTO deployed_contracts(address,name,abi,deployer,created_at) VALUES(?,?,?,?,?)",
                [("0xc%d" % i, "C", "[]", W, now()) for i in range(2)])
            conn.execute(
                "INSERT INTO contract_calls(contract_address,method,caller,created_at) VALUES(?,?,?,?)",
                ("0xc1", "balanceOf", W, now()))
            conn.executemany(
                "INSERT INTO transactions(hash,block_number,from_addr,to_addr,timestamp) VALUES(?,?,?,?,?)",
                [("0xt1", 1, W, "0xother", 1), ("0xt2", 2, "0xother", W, 2)])
            conn.execute(
                "INSERT INTO nfts(token_id,standard,contract_address,author,owner,created_at) VALUES(?,?,?,?,?,?)",
                ("1", "ERC721", "0xc1", W, W, now()))
            conn.execute(
                "INSERT INTO nft_trades(token_id,from_addr,to_addr,created_at) VALUES(?,?,?,?)",
                ("1", W, "0xother", now()))
            conn.execute(
                "INSERT INTO wallet_transfers(token_address,from_addr,to_addr,amount,created_at) VALUES(?,?,?,?,?)",
                ("0xc1", W, "0xother", "5", now()))
            conn.executemany(
                "INSERT INTO eco_energy_records(wallet,role_key,role_name,action,points,created_at) VALUES(?,?,?,?,?,?)",
                [(W, "metro", "地铁集团", "地铁通勤", 50, now()),
                 (W, "bus", "公交集团", "公交出行", 20, now())])
        m = aggregate(W)
        assert m["deployed_contracts"] == 2
        assert m["contract_calls"] == 1
        assert m["transactions"] == 2
        assert m["nft_mint"] == 1
        assert m["nft_trade"] == 1
        assert m["erc20_transfer"] == 1
        assert m["energy_issue"] == 2
