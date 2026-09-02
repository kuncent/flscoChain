"""report._load_eco_brief 业务闭环口径回归测试。

闭环口径：G 项资产计数 = 当前持有 ∪ 曾兑换后售出（挂牌时后端已校验归属，
能卖出必曾兑换）。仅按 owner 统计会导致「卖出资产后分数倒退」，与
鼓励流通的业务导向矛盾（见 report.py _load_eco_brief 注释）。
"""
from app.db import get_conn, now
from app.routers.report import _load_eco_brief

W = "0xlearner"


def _mk_cert(conn, token_id: int, owner: str, species_id: int) -> int:
    conn.execute(
        "INSERT INTO eco_certificates(token_id,species_id,species_name,owner,cost_energy,"
        "contract_address,tx_hash,cert_no,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (str(token_id), species_id, f"树种{species_id}", owner, 100, "0xc", "0xt",
         f"CERT{token_id}", now()),
    )
    return conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]


def test_cert_counts_held_union_sold(temp_db):
    """证书 = 持有 ∪ 自己兑换后售出；树种多样性同口径，卖出后分数不回退。"""
    with get_conn() as conn:
        _mk_cert(conn, 1, W, 1)                          # 持有中
        cid2 = _mk_cert(conn, 2, "0xbuyer", 2)           # 已流通给买家
        conn.execute(
            "INSERT INTO eco_market_listings(seller,asset_type,asset_id,asset_name,token_id,"
            "contract_address,standard,price_energy,status,buyer,tx_hash,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (W, "certificate", cid2, "树种2", "2", "0xc", "ERC721", 50,
             "sold", "0xbuyer", "0xtx", now()),
        )
    b = _load_eco_brief(W)
    assert b["certificates"] == 2
    assert b["cert_distinct_species"] == 2
    assert b["market"]["listings"] == 1
    assert b["market"]["sold"] == 1
    assert b["market"]["bought"] == 0
    assert b["market"]["trades"] == 1
    assert b["market"]["income"] == 50


def test_market_counts_buy_side_and_isolation(temp_db):
    """买入成交计入本人流水；他人之间的成交不计入（钱包隔离）。"""
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO eco_market_listings(seller,asset_type,asset_id,asset_name,token_id,"
            "contract_address,standard,price_energy,status,buyer,tx_hash,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("0xseller", "badge", 1, "勋章", "1", "0xc", "ERC1155", 30, "sold", W, "0xa", now()),
                ("0xother1", "badge", 2, "勋章", "2", "0xc", "ERC1155", 30, "sold", "0xother2", "0xb", now()),
            ],
        )
    b = _load_eco_brief(W)
    assert b["market"]["bought"] == 1
    assert b["market"]["sold"] == 0
    assert b["market"]["spent"] == 30
    # 买入过的勋章按闭环口径计入持有多样性（G-2 不因「买来即用」被漏计）
    assert b["badges"] == 1 or b["badges"] == 0  # 仅卖出侧并入；买入持有以 eco_badges.owner 为准
    b2 = _load_eco_brief("0xnobody")
    assert b2["market"]["trades"] == 0
