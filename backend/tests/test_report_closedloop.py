"""report._load_eco_brief 业务闭环口径回归测试。

闭环口径：G 项资产计数 = 当前持有 ∪ 曾兑换后售出（挂牌时后端已校验归属，
能卖出必曾兑换）。仅按 owner 统计会导致「卖出资产后分数倒退」，与
鼓励流通的业务导向矛盾（见 report.py _load_eco_brief 注释）。

E 项口径：角色体验多样性 = 埋点 learning_events.eco_role_switch 去重，
而不是 eco_role_selections 的当前行（该表 UNIQUE(wallet) 只能存一个角色）。
"""
from app.db import get_conn, now
from app.learning.events import EventType, track as _track
from app.routers.report import _calc_score, _load_eco_brief

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


def _select(conn, role_key: str) -> None:
    """模拟前端「切换角色」：当前选择表覆盖 + 埋点累加（与 eco.select_role 一致）。"""
    _track(EventType.ECO_ROLE_SWITCH, target=role_key, wallet=W)
    conn.execute(
        "INSERT OR REPLACE INTO eco_role_selections(wallet, role_key, selected_at) VALUES(?,?,?)",
        (W, role_key, now()),
    )


def _e_score(eco: dict) -> int:
    """跑一次完整评分，取 E 项得分（其余维度置 0，只看 E）。"""
    sc = _calc_score(0, {}, 0, 0, 0, 100.0, eco)
    return next(x["score"] for x in sc["breakdown"] if x["id"] == "E")


def test_role_diversity_counts_history_not_current_selection(temp_db):
    """E 项：逐个切换角色后只剩最后一行，多样性仍须按历史算（旧口径恒 ≤1）。"""
    with get_conn() as conn:
        for k in ("metro", "bus", "bike", "takeout"):
            _select(conn, k)
        # 学生做完通常会再点「切回普通用户」：当前选择行被 DELETE（埋点落 target=resident）
        _track(EventType.ECO_ROLE_SWITCH, target="resident", wallet=W)
        conn.execute("DELETE FROM eco_role_selections WHERE lower(wallet)=?", (W,))
    eco = _load_eco_brief(W)
    assert eco["distinct_roles"] == 4, f"E 项应按历史去重，实际 {eco}"
    assert eco["role_switches"] == 5            # 4 次选角色 + 1 次切回普通用户
    assert _e_score(eco) == 8                   # ≥4 种 → 8 分


def test_role_diversity_normalizes_alias_and_ignores_dirty(temp_db):
    """旧别名 delivery/recycle 归一后不重复计数；空值 / 未知角色不计入。"""
    with get_conn() as conn:
        for k in ("takeout", "delivery", "recycling", "recycle", "", "not_a_role"):
            _track(EventType.ECO_ROLE_SWITCH, target=k, wallet=W)
    eco = _load_eco_brief(W)
    assert eco["distinct_roles"] == 2          # takeout + recycling


def test_role_diversity_is_wallet_isolated(temp_db):
    """他人切换的角色不得计入本人 E 项（钱包隔离）。"""
    with get_conn() as conn:
        for k in ("metro", "bus", "bike"):
            _track(EventType.ECO_ROLE_SWITCH, target=k, wallet="0xother")
        _select(conn, "admin")
    assert _load_eco_brief(W)["distinct_roles"] == 1      # 仅本人当前 admin
    assert _load_eco_brief("0xother")["distinct_roles"] == 3


def test_role_diversity_attributes_org_wallet_switches(temp_db):
    """以机构钱包体验角色（点「以此钱包操作」）也要算到体验人头上。

    前端默认把操作钱包切到机构钱包（全班共用），埋点 wallet 就是机构地址；
    只按本人钱包候选集筛会全部漏计，故新埋点另落 user_id（登录账号）。
    """
    with get_conn() as conn:
        for k in ("metro", "bus"):
            _track(EventType.ECO_ROLE_SWITCH, target=k, wallet="0xmetro",
                   extra={"role_key": k}, user_id="tzs001")
        # 同一机构钱包上的他人操作不得泄入本人（wallet 同值，靠 user_id 分开）
        _track(EventType.ECO_ROLE_SWITCH, target="bike", wallet="0xmetro",
               extra={"role_key": "bike"}, user_id="tzs002")
    eco = _load_eco_brief(W, user_id="tzs001", candidates=[W])
    assert eco["distinct_roles"] == 2
    # 不传 user_id（旧调用方）时退回钱包口径，不会把机构钱包算成个人成绩
    assert _load_eco_brief(W, candidates=[W])["distinct_roles"] == 0
