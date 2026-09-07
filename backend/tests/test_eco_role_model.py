"""四维度角色职能模型回归测试（谁发行能量 / 谁发行资产 / 谁获取能量 / 谁兑换资产）。

断言口径与权威定义 app/learning/alliance_roles.py 逐条对齐：
1. 职能矩阵：能量发行方仅 5 个业务节点；获取 / 兑换 / 市场交易仅居民；治理仅管理员；
   **发行方与使用方互斥**；绿色资产按协议分治（ERC20 节点授信 / ERC721 项目额度 /
   ERC1155 类型上限 + 同类多份）。
2. 能力位硬拦：越权调用一律 403（居民自铸能量、节点下场兑换或挂牌、管理员建勋章类型、
   非 bike 节点建/铸骑行券…），错误文案必须说明「当前身份缺哪项职能」。
3. 能量账本：按量计价（基础 + 超门槛加成 + 单次封顶）、节点授信上限、发行方不得自铸、
   资金守恒（Σ流水 == 累计发行 − 累计销毁 == 在途流通 + 国库余额）。
4. 国库销毁：仅「管理员机构身份 + 教师/管理员登录账号」可执行，销毁后净发行量按量下降。

链模式约束（重要）：conftest 固定 CHAIN_MODE=mock，MockChainClient.call_contract 恒
ok=True 且 result 为字符串 "mock {method}"，因此**链上 revert 无法在 pytest 断言**
（合约层发行权白名单由 backend/_verify_role_model.py 在真机 py-evm 链上验证）。
本文件只断言应用层的 403 / 400 门控与账本、额度口径。合约部署记录按 test_verifier
的范式手工种入（避开 seed 里的 solc 编译依赖；mock 链 has_code 恒真，地址可为假地址）。
"""
import json

import pytest

from app.db import get_conn, now
from app.learning.alliance_roles import (
    CAP_ASSET_EXCHANGE, CAP_ASSET_ISSUE_BADGE, CAP_ASSET_ISSUE_VOUCHER,
    CAP_ENERGY_ISSUE, CAP_ENERGY_RECEIVE, CAP_MARKET_TRADE, CAP_TREASURY_MANAGE,
    TREASURY_WALLET, duty_matrix,
)
from app.security import create_token
from app.wallet_id import is_address, to_address

P = "/api/eco"
STUDENT, TEACHER = 4, 3          # user_info.role_id：1=管理员 3=教师 4=学生
NODE_WALLETS = {"metro": "0xmetro", "bus": "0xbus", "bike": "0xbike",
                "takeout": "0xtakeout", "recycling": "0xrecycle"}
ISSUERS = set(NODE_WALLETS)

# 内置合约的极简 ABI：mock 链不校验 calldata，仅需方法名可被 _abi_has 探测到
_M = {"type": "function", "stateMutability": "nonpayable", "inputs": [], "outputs": []}
_V = {"type": "function", "stateMutability": "view", "inputs": [],
      "outputs": [{"name": "", "type": "uint256"}]}
_ABI = [dict(_M, name=n) for n in ("mint", "transfer", "transferFrom",
                                   "safeTransferFrom", "burn")] + \
       [dict(_V, name=n) for n in ("balanceOf", "totalSupply")]
_SEED_CONTRACTS = (("GreenEnergy", "0x" + "a1" * 20, "ERC20"),
                   ("PlantCertificate", "0x" + "b2" * 20, "ERC721"),
                   ("EcoBadge", "0x" + "c3" * 20, "ERC1155"))


@pytest.fixture
def eco(client):
    """种入三份内置合约部署记录，使 _find_contract / _load_abi 在 mock 链上可命中。"""
    with get_conn() as conn:
        for name, addr, std in _SEED_CONTRACTS:
            conn.execute(
                "INSERT INTO deployed_contracts(address,name,abi,bytecode,source,"
                "deployer,tx_hash,standard,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (addr, name, json.dumps(_ABI), "0x00", "", "0xadmin", "0xseed", std, now()),
            )
    return client


# ---------------------------------------------------------------------------
# 请求辅助（身份一律走 JWT + 显式 wallet，与前端「切换钱包/角色」的真实路径一致）
# ---------------------------------------------------------------------------
def tok(wallet: str, role_id: int = STUDENT, user_id: str = "") -> dict:
    return {"Authorization": "Bearer " + create_token({
        "user_id": user_id or wallet, "role_id": role_id, "wallet": wallet,
        "class_id": "c1", "user_name": user_id or wallet})}


def select(client, wallet, role_key, expect=200):
    r = client.post(f"{P}/role/select", json={"wallet": wallet, "role_key": role_key},
                    headers=tok(wallet))
    assert r.status_code == expect, r.text
    return r


def clear(client, wallet):
    r = client.post(f"{P}/role/clear", json={"wallet": wallet}, headers=tok(wallet))
    assert r.status_code == 200, r.text


def issue(client, wallet, role_key, proof, expect=200):
    r = client.post(f"{P}/energy/issue",
                    json={"wallet": wallet, "role_key": role_key, "proof": proof},
                    headers=tok(wallet))
    assert r.status_code == expect, r.text
    return r.json()          # 成功体与 {"detail": ...} 统一成 dict，便于两类断言


def recycle_proof(no, kg=21):
    """回收公司凭证：≥1kg 基础 100 点，每超 1kg +20 点，单次封顶 500 点。"""
    return {"order_no": f"RC-{no}", "category": "塑料瓶", "weight_kg": kg}


def give(client, wallet, times=3, tag="a"):
    """给居民钱包凑能量：每次回收 21kg = 500 点（封顶值），times 次 = 500*times。

    业务单号必须按钱包 + 批次隔离：幂等约束是 UNIQUE(proof_no, role_key)（全平台口径），
    重用同一单号会命中回放而不产生流水。
    """
    for i in range(times):
        body = issue(client, wallet, "recycling", recycle_proof(f"{wallet}-{tag}-{i}"))
        assert body["points"] == 500 and not body.get("idempotent"), body
    return 500 * times


def balance(client, wallet) -> int:
    r = client.get(f"{P}/energy/balance", params={"wallet": wallet}, headers=tok(wallet))
    assert r.status_code == 200, r.text
    return int(r.json()["balance"])


def flows(client, wallet):
    r = client.get(f"{P}/energy/flows", params={"wallet": wallet}, headers=tok(wallet))
    assert r.status_code == 200, r.text
    return r.json()


def add_tree(client, name, cost, supply, expect=200):
    r = client.post(f"{P}/trees/add",
                    json={"wallet": TREASURY_WALLET, "name": name,
                          "required_energy": cost, "supply": supply,
                          "image_url": "", "description": ""},
                    headers=tok(TREASURY_WALLET, role_id=TEACHER))
    assert r.status_code == expect, r.text
    return r.json()


def ledger_sum() -> int:
    with get_conn() as conn:
        return int(conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM eco_energy_flows").fetchone()[0] or 0)


# ===========================================================================
# 1. 职能矩阵（四维度 × 身份）与协议形态
# ===========================================================================
class TestDutyMatrix:
    def test_matrix_dimension_owners_are_exclusive(self, eco):
        """发行方与使用方互斥：能量发行 = 5 节点，获取/兑换/交易 = 仅居民，治理 = 仅管理员。"""
        rows = eco.get(f"{P}/roles/duties", headers=tok("0xlearner")).json()["matrix"]
        dim = {r["key"]: r["dimensions"] for r in rows}
        assert {k for k, d in dim.items() if d["issue_energy"]} == ISSUERS
        assert {k for k, d in dim.items() if d["obtain_energy"]} == {"resident"}
        assert {k for k, d in dim.items() if d["exchange_asset"]} == {"resident"}
        assert {k for k, d in dim.items() if d["trade_market"]} == {"resident"}
        assert {k for k, d in dim.items() if d["govern"]} == {"admin"}
        # 互斥：任何身份都不能既发行能量又兑换资产
        assert not ({k for k, d in dim.items() if d["issue_energy"]}
                    & {k for k, d in dim.items() if d["exchange_asset"]})

    def test_asset_forms_split_by_standard(self, eco):
        """资产形态按协议分治：形态与「发行数量」语义必须写进矩阵，前端只渲染不判定。"""
        forms = {f["asset"]: f for f in
                 eco.get(f"{P}/roles/duties", headers=tok("0xlearner")).json()["asset_forms"]}
        assert forms["energy"]["standard"] == "ERC20"
        assert forms["energy"]["supply_model"] == "node_quota"
        assert forms["certificate"]["standard"] == "ERC721"
        assert forms["certificate"]["supply_model"] == "project_quota"
        assert forms["badge"]["standard"] == "ERC1155"
        assert forms["badge"]["supply_model"] == "type_quota"
        # 骑行券全平台仅一份、发行方唯一（它是兑付义务人）
        assert forms["voucher"]["issuers"] == ["bike"]
        assert forms["certificate"]["issuers"] == ["admin"]
        assert set(forms["energy"]["issuers"]) == ISSUERS

    def test_identity_view_follows_wallet(self, eco):
        """/roles/duties 传 wallet 时返回该钱包的当前身份视图（组织钱包恒为机构角色）。"""
        duties = eco.get(f"{P}/roles/duties", params={"wallet": "0xmetro"},
                         headers=tok("0xmetro")).json()["identity"]
        caps = set(duties["capabilities"])
        assert duties["profile"] == "node" and duties["role_key"] == "metro"
        assert {CAP_ENERGY_ISSUE, CAP_ASSET_ISSUE_BADGE} <= caps
        assert not ({CAP_ENERGY_RECEIVE, CAP_ASSET_EXCHANGE, CAP_MARKET_TRADE} & caps)

        gov = eco.get(f"{P}/roles/duties", params={"wallet": TREASURY_WALLET},
                      headers=tok(TREASURY_WALLET)).json()["identity"]
        assert gov["profile"] == "admin" and CAP_TREASURY_MANAGE in set(gov["capabilities"])
        # 管理员既不发行能量也不兑换（治理层与发行/使用层三方分离）
        assert CAP_ENERGY_ISSUE not in set(gov["capabilities"])
        assert CAP_ASSET_EXCHANGE not in set(gov["capabilities"])

    def test_unselected_wallet_is_resident(self, eco):
        """未选角色的个人钱包 = 居民：只有获取 / 兑换 / 交易三项能力。"""
        cur = eco.get(f"{P}/role/current", params={"wallet": "0xlearner"},
                      headers=tok("0xlearner")).json()
        assert cur["role_key"] is None and cur["profile"] == "resident"
        assert set(cur["capabilities"]) == {CAP_ENERGY_RECEIVE, CAP_ASSET_EXCHANGE,
                                            CAP_MARKET_TRADE}

    def test_matrix_matches_api_output(self, eco):
        """接口矩阵必须与本地派生函数一致（防止 /roles/duties 自己另写一套判定）。"""
        api = {r["key"]: r for r in
               eco.get(f"{P}/roles/duties", headers=tok("0xlearner")).json()["matrix"]}
        for row in duty_matrix():
            assert api[row["key"]]["capabilities"] == row["capabilities"]
            assert api[row["key"]]["dimensions"] == row["dimensions"]
            assert api[row["key"]]["asset_forms"] == row["asset_forms"]
            # 对外契约：wallet / address 只能是真实链上地址（或空 = 无机构钱包），
            # 友好别名一律放 wallet_alias，避免前端拿别名回写成资产归属
            for r in api.values():
                for f in ("wallet", "address"):
                    assert not r.get(f) or is_address(r[f]), f"{r['key']}.{f}={r.get(f)!r}"
                assert api[row["key"]]["wallet"] == row["wallet"]


# ===========================================================================
# 2. 钱包 ↔ 机构绑定（组织钱包不能扮演别家机构）
# ===========================================================================
class TestWalletRoleBinding:
    def test_org_wallet_cannot_play_other_node(self, eco):
        """0xbus 扮演外卖平台 → 400（机构业务签章只能由本机构钱包发出）。"""
        r = select(eco, "0xbus", "takeout", expect=400)
        assert "钱包与角色不匹配" in r.json()["detail"]

    def test_org_wallet_plays_own_node(self, eco):
        select(eco, "0xbus", "bus")
        cur = eco.get(f"{P}/role/current", params={"wallet": "0xbus"},
                      headers=tok("0xbus")).json()
        assert cur["role_key"] == "bus"

    def test_personal_wallet_may_play_node_and_switch_back(self, eco):
        """实训允许个人钱包扮演节点，但必须可切回居民（否则永久失去兑换职能）。"""
        select(eco, "0xlearner", "metro")
        caps = eco.get(f"{P}/role/current", params={"wallet": "0xlearner"},
                       headers=tok("0xlearner")).json()["capabilities"]
        assert CAP_ENERGY_ISSUE in caps and CAP_ASSET_EXCHANGE not in caps
        clear(eco, "0xlearner")
        caps = eco.get(f"{P}/role/current", params={"wallet": "0xlearner"},
                       headers=tok("0xlearner")).json()["capabilities"]
        assert CAP_ASSET_EXCHANGE in caps


# ===========================================================================
# 3. 维度一 + 二：发行绿色能量（仅业务节点 · 按量计价 · 授信约束）
# ===========================================================================
class TestEnergyIssueDimension:
    def test_admin_and_resident_cannot_issue(self, eco):
        """管理员无 energy.issue 职能 → 403（治理方不是发行方）。"""
        r = issue(eco, "0xlearner", "admin", {"remark": "x"}, expect=403)
        assert CAP_ENERGY_ISSUE in r["detail"]

    def test_receiver_cannot_be_org_wallet(self, eco):
        """发行方自铸拦截：接收方是组织钱包 / 国库账户 → 400。"""
        body = issue(eco, "0xmetro", "metro",
                     {"station_in": "A", "station_out": "B", "board_time": "t",
                      "distance_km": 12, "trip_no": "T-1"}, expect=400)
        assert "联盟组织钱包" in body["detail"] or "自铸" in body["detail"]
        assert balance(eco, "0xmetro") == 0      # 拦截不得先在链上/账本产生余额

    def test_price_is_base_plus_quantity_bonus_with_cap(self, eco):
        """按真实商业计价：达成门槛给基础分，超量逐量加成，单次封顶截断。"""
        base = {"station_in": "国贸", "station_out": "西二旗", "board_time": "08:05"}
        p1 = issue(eco, "0xlearner", "metro", dict(base, distance_km=10, trip_no="M-1"))
        assert (p1["points"], p1["points_detail"]["capped"]) == (50, False)   # 恰好门槛 = 基础分
        p2 = issue(eco, "0xlearner", "metro", dict(base, distance_km=30, trip_no="M-2"))
        assert (p2["points"], p2["points_detail"]["bonus"]) == (90, 40)       # 50 + 20*2
        p3 = issue(eco, "0xlearner", "metro", dict(base, distance_km=200, trip_no="M-3"))
        assert (p3["points"], p3["points_detail"]["capped"]) == (150, True)   # 单次封顶 150
        assert balance(eco, "0xlearner") == 50 + 90 + 150

    def test_switch_type_behavior_is_fixed_points(self, eco):
        """开关型行为（无需餐具）不按量放大：每单固定 10 点。"""
        for i, oid in enumerate(("O-1", "O-2")):
            body = issue(eco, "0xlearner", "takeout",
                         {"order_id": oid, "no_cutlery": True})
            assert body["points"] == 10, body
        assert balance(eco, "0xlearner") == 20

    def test_below_threshold_rejected(self, eco):
        body = issue(eco, "0xlearner", "metro",
                     {"station_in": "A", "station_out": "B", "board_time": "t",
                      "distance_km": 3, "trip_no": "M-9"}, expect=400)
        assert "业务凭证校验失败" in body["detail"]
        assert balance(eco, "0xlearner") == 0    # 未达门槛不得入账

    def test_required_business_fields_enforced(self, eco):
        """缺必填业务字段（进站口 / 出站口 / 时间）不得发能量——真实审核需要完整凭据。"""
        body = issue(eco, "0xlearner", "metro", {"distance_km": 30, "trip_no": "M-7"},
                     expect=400)
        assert "必填业务数据" in body["detail"]
        assert balance(eco, "0xlearner") == 0

    def test_node_quota_blocks_overissue(self, eco):
        """节点授信用尽 → 400（修「发行量无上限 = 无限印钞」）。"""
        with get_conn() as conn:                # 先模拟该节点已发行 4960 点
            conn.execute(
                "INSERT INTO eco_energy_flows(wallet,kind,amount,ref,note,role_key,created_at)"
                " VALUES(?,?,?,?,?,?,?)",
                ("0xseed", "issue", 4960, "seed:metro-quota", "历史发行", "metro", now()))
        body = issue(eco, "0xlearner", "metro",
                     {"station_in": "A", "station_out": "B", "board_time": "t",
                      "distance_km": 10, "trip_no": "M-Q"}, expect=400)
        assert "授信已用尽" in body["detail"]
        assert balance(eco, "0xlearner") == 0

    def test_issue_writes_single_flow_and_operator_trace(self, eco):
        """发行必须落一笔正向流水，并留痕真实操作人（个人钱包扮演机构时）。"""
        select(eco, "0xlearner", "metro")       # 角色扮演模式
        issue(eco, "0xlearner", "metro",
              {"station_in": "A", "station_out": "B", "board_time": "t",
               "distance_km": 12, "trip_no": "M-F"})
        data = flows(eco, "0xlearner")
        assert data["balance"] == 54            # 12km → 50 + 2*2
        kinds = [f["kind"] for f in data["items"]]
        assert kinds == ["issue"] and data["items"][0]["kind_label"] == "联盟节点发行"
        with get_conn() as conn:
            rec = conn.execute(
                "SELECT operator_wallet, issuer_wallet FROM eco_energy_records "
                "WHERE proof_no='M-F'").fetchone()
        # 资产台账已统一为真实链上地址（不带冒号 / 连字符的内部别名不再入库）：
        # 链上 FROM 是机构，但签单人与发行方留痕都必须是可核对的地址
        assert rec["operator_wallet"] == to_address("0xlearner")
        assert rec["issuer_wallet"] == to_address("0xmetro")


# ===========================================================================
# 4. 维度三 + 四：获取能量（居民）与兑换绿色资产（ERC721 额度 / ERC1155 份数）
# ===========================================================================
class TestExchangeDimension:
    def test_node_identity_cannot_exchange_or_list(self, eco):
        """切到节点身份后不能再下场兑换 / 挂牌（左手发右手收）。"""
        give(eco, "0xlearner", times=3)
        tid = add_tree(eco, "侧柏", 1000, 5)["id"]
        select(eco, "0xlearner", "metro")
        r = eco.post(f"{P}/certificates/exchange",
                     json={"wallet": "0xlearner", "species_id": tid}, headers=tok("0xlearner"))
        assert r.status_code == 403 and CAP_ASSET_EXCHANGE in r.json()["detail"]
        r = eco.post(f"{P}/badges/exchange",
                     json={"wallet": "0xlearner", "badge_type": "badge", "quantity": 1},
                     headers=tok("0xlearner"))
        assert r.status_code == 403
        assert balance(eco, "0xlearner") == 1500        # 拦截不得改变账本
        clear(eco, "0xlearner")

    def test_certificate_project_quota_sells_out(self, eco):
        """ERC721 一证一树：项目额度用尽即售罄，不允许超发。"""
        give(eco, "0xlearner", times=3)           # 1500 点
        tid = add_tree(eco, "银杏", 1000, 1)["id"]
        r = eco.post(f"{P}/certificates/exchange",
                     json={"wallet": "0xlearner", "species_id": tid}, headers=tok("0xlearner"))
        assert r.status_code == 200, r.text
        assert r.json()["quota"] == {"supply": 1, "issued": 1, "remaining": 0}
        assert balance(eco, "0xlearner") == 500
        item = next(t for t in eco.get(f"{P}/trees", headers=tok("0xlearner")).json()["items"]
                    if t["id"] == tid)
        assert item["sold_out"] is True and item["remaining"] == 0
        # 能量足够但额度已满 → 400（额度优先于余额）
        give(eco, "0xlearner", times=2, tag="b")
        r = eco.post(f"{P}/certificates/exchange",
                     json={"wallet": "0xlearner", "species_id": tid}, headers=tok("0xlearner"))
        assert r.status_code == 400 and "发行额度已满" in r.json()["detail"]
        with get_conn() as conn:                # 失败不白耗额度
            assert conn.execute("SELECT issued FROM eco_tree_species WHERE id=?",
                                (tid,)).fetchone()[0] == 1

    def test_tree_quota_only_raise_and_off_status_blocks_exchange(self, eco):
        """治理额度只可上调；下架只停止新兑换，已发证书不受影响。"""
        give(eco, "0xlearner", times=4)          # 2000 点 → 够兑 2 张 1000 点证书
        tid = add_tree(eco, "国槐", 1000, 2)["id"]
        for _ in range(2):
            assert eco.post(f"{P}/certificates/exchange",
                            json={"wallet": "0xlearner", "species_id": tid},
                            headers=tok("0xlearner")).status_code == 200
        r = eco.post(f"{P}/trees/update",
                     json={"wallet": TREASURY_WALLET, "species_id": tid, "supply": 1},
                     headers=tok(TREASURY_WALLET, role_id=TEACHER))
        assert r.status_code == 400 and "只可上调" in r.json()["detail"]
        up = eco.post(f"{P}/trees/update",
                      json={"wallet": TREASURY_WALLET, "species_id": tid, "supply": 5},
                      headers=tok(TREASURY_WALLET, role_id=TEACHER)).json()
        assert up["remaining"] == 3 and up["sold_out"] is False
        off = eco.post(f"{P}/trees/update",
                       json={"wallet": TREASURY_WALLET, "species_id": tid, "status": "off"},
                       headers=tok(TREASURY_WALLET, role_id=TEACHER)).json()
        assert off["status"] == "off"
        r = eco.post(f"{P}/certificates/exchange",
                     json={"wallet": "0xlearner", "species_id": tid}, headers=tok("0xlearner"))
        assert r.status_code == 400 and "已下架" in r.json()["detail"]
        assert len(eco.get(f"{P}/certificates/list", params={"owner": "0xlearner"},
                           headers=tok("0xlearner")).json()["items"]) == 2

    def test_govern_requires_privileged_account(self, eco):
        """修 B12：学生账号冒用 0xadmin 钱包也不能改目录 / 额度（治理权不随钱包走）。"""
        r = eco.post(f"{P}/trees/add",
                     json={"wallet": TREASURY_WALLET, "name": "冒名树",
                           "required_energy": 1000, "supply": 1},
                     headers=tok(TREASURY_WALLET, role_id=STUDENT))
        assert r.status_code == 403 and "治理职能" in r.json()["detail"]
        assert eco.get(f"{P}/trees", headers=tok("0xlearner")).json()["items"] == []

    def test_badge_quantity_priced_by_unit_cost(self, eco):
        """ERC1155 同类多份：成本 = 单价 × 份数，账本只出账一次合计值。"""
        give(eco, "0xlearner", times=3)
        types = eco.get(f"{P}/badges/types").json()
        bt = next(t for t in types if t["badge_type"] == "badge")
        r = eco.post(f"{P}/badges/exchange",
                     json={"wallet": "0xlearner", "badge_type": "badge",
                           "type_id": bt["id"], "quantity": 3}, headers=tok("0xlearner"))
        assert r.status_code == 200, r.text
        assert r.json()["quantity"] == 3 and r.json()["cost_energy"] == bt["cost_energy"] * 3
        assert r.json()["standard"] == "ERC1155"
        assert balance(eco, "0xlearner") == 1500 - bt["cost_energy"] * 3
        mine = eco.get(f"{P}/badges/list", params={"owner": "0xlearner"},
                       headers=tok("0xlearner")).json()["items"]
        assert mine[0]["quantity"] == 3 and mine[0]["total_held"] == 3

    def test_badge_type_supply_only_raise(self, eco):
        """骑行券上限只可上调不可下调（下调 = 链上存量事实超发）。"""
        v = next(t for t in eco.get(f"{P}/badges/types").json() if t["badge_type"] == "voucher")
        give(eco, "0xlearner", times=1)
        r = eco.post(f"{P}/badges/exchange",
                     json={"wallet": "0xlearner", "badge_type": "voucher",
                           "type_id": v["id"], "quantity": 10}, headers=tok("0xlearner"))
        assert r.status_code == 200, r.text
        assert r.json()["cost_energy"] == v["cost_energy"] * 10
        r = eco.post(f"{P}/badges/types/add",
                     json={"wallet": "0xbike", "badge_type": "voucher", "name": "骑行券",
                           "icon": "🎫", "image_url": "", "cost_energy": v["cost_energy"],
                           "supply": 5, "desc": ""}, headers=tok("0xbike"))
        assert r.status_code == 400 and "只可上调不可下调" in r.json()["detail"]

    def test_voucher_issuer_is_only_bike(self, eco):
        """骑行券的发行方唯一：管理员与其它节点建券 / 铸券都 403。"""
        payload = {"badge_type": "voucher", "name": "月卡", "icon": "🎫",
                   "image_url": "", "cost_energy": 20, "supply": 50, "desc": ""}
        for w in (TREASURY_WALLET, "0xmetro"):
            r = eco.post(f"{P}/badges/types/add", json=dict(payload, wallet=w),
                         headers=tok(w))
            assert r.status_code == 403, f"{w} 不应具备骑行券发行权：{r.text}"
        r = eco.post(f"{P}/badges/types/add", json=dict(payload, wallet="0xbike"),
                     headers=tok("0xbike"))
        assert r.status_code == 200, r.text
        assert r.json()["issuer_role"] == "bike"

    def test_admin_cannot_create_issuable_badge_type(self, eco):
        """修 B4：管理员无铸造职能 → 不允许建勋章类型（否则是永远铸不出的死数据）。"""
        r = eco.post(f"{P}/badges/types/add",
                     json={"wallet": TREASURY_WALLET, "badge_type": "badge", "name": "治理章",
                           "icon": "🏅", "image_url": "", "cost_energy": 10, "supply": 10,
                           "desc": ""}, headers=tok(TREASURY_WALLET, role_id=TEACHER))
        assert r.status_code == 403 and CAP_ASSET_ISSUE_BADGE in r.json()["detail"]

    def test_mint_requires_issuer_and_no_self_mint(self, eco):
        """铸造发放：仅该资产发行节点可为，接收方必须是居民钱包。"""
        bt = next(t for t in eco.get(f"{P}/badges/types").json() if t["badge_type"] == "badge")
        vt = next(t for t in eco.get(f"{P}/badges/types").json() if t["badge_type"] == "voucher")
        # 居民无铸造职能
        r = eco.post(f"{P}/badges/mint",
                     json={"wallet": "0xlearner", "role_key": "metro",
                           "type_id": bt["id"], "to_wallet": "0xlearner2", "quantity": 1},
                     headers=tok("0xlearner"))
        assert r.status_code == 403
        # 跨机构代铸：地铁节点铸骑行券 → 403
        r = eco.post(f"{P}/badges/mint",
                     json={"wallet": "0xmetro", "role_key": "metro",
                           "type_id": vt["id"], "to_wallet": "0xlearner", "quantity": 1},
                     headers=tok("0xmetro"))
        assert r.status_code == 403 and CAP_ASSET_ISSUE_VOUCHER in r.json()["detail"]
        # 自铸：接收方 = 操作者本人钱包 → 400
        r = eco.post(f"{P}/badges/mint",
                     json={"wallet": "0xmetro", "role_key": "metro",
                           "type_id": bt["id"], "to_wallet": "0xmetro", "quantity": 1},
                     headers=tok("0xmetro"))
        assert r.status_code == 400 and "自铸" in r.json()["detail"]
        # 接收方是组织钱包 → 400
        r = eco.post(f"{P}/badges/mint",
                     json={"wallet": "0xmetro", "role_key": "metro",
                           "type_id": bt["id"], "to_wallet": "0xbike", "quantity": 1},
                     headers=tok("0xmetro"))
        assert r.status_code == 400 and "联盟组织钱包" in r.json()["detail"]
        # 正常投放：占用类型额度、不消耗居民能量（无流水）
        minted_before = bt["minted"]
        r = eco.post(f"{P}/badges/mint",
                     json={"wallet": "0xmetro", "role_key": "metro",
                           "type_id": bt["id"], "to_wallet": "0xlearner", "quantity": 2},
                     headers=tok("0xmetro"))
        assert r.status_code == 200, r.text
        assert r.json()["quota"]["minted"] == minted_before + 2
        assert flows(eco, "0xlearner")["balance"] == 0      # 无对价投放不入能量账本


# ===========================================================================
# 5. 二级流通（仅居民之间 · 份数按协议 · 双流水守恒）
# ===========================================================================
class TestMarketDimension:
    def _badge_id(self, client, owner):
        items = client.get(f"{P}/badges/list", params={"owner": owner},
                           headers=tok(owner)).json()["items"]
        return items[0]["id"], int(items[0]["quantity"])

    def test_erc721_listing_quantity_forced_one(self, eco):
        """ERC721 不可拆：一张证书 = 一棵树，挂牌传份数 5 仍强制归 1。"""
        give(eco, "0xlearner", times=3)
        tid = add_tree(eco, "白蜡", 1000, 3)["id"]
        assert eco.post(f"{P}/certificates/exchange",
                        json={"wallet": "0xlearner", "species_id": tid},
                        headers=tok("0xlearner")).status_code == 200
        cid = eco.get(f"{P}/certificates/list", params={"owner": "0xlearner"},
                      headers=tok("0xlearner")).json()["items"][0]["id"]
        r = eco.post(f"{P}/market/list",
                     json={"seller": "0xlearner", "asset_type": "certificate",
                           "asset_id": cid, "price_energy": 100, "quantity": 5},
                     headers=tok("0xlearner"))
        assert r.status_code == 200, r.text
        assert r.json()["standard"] == "ERC721" and r.json()["quantity"] == 1

    def test_erc1155_listing_cannot_exceed_held(self, eco):
        give(eco, "0xlearner", times=3)
        bt = next(t for t in eco.get(f"{P}/badges/types").json() if t["badge_type"] == "badge")
        eco.post(f"{P}/badges/exchange",
                 json={"wallet": "0xlearner", "badge_type": "badge",
                       "type_id": bt["id"], "quantity": 3}, headers=tok("0xlearner"))
        bid, held = self._badge_id(eco, "0xlearner")
        assert held == 3
        r = eco.post(f"{P}/market/list",
                     json={"seller": "0xlearner", "asset_type": "badge", "asset_id": bid,
                           "price_energy": 20, "quantity": held + 1}, headers=tok("0xlearner"))
        assert r.status_code == 400 and "超过持有量" in r.json()["detail"]
        r = eco.post(f"{P}/market/list",
                     json={"seller": "0xlearner", "asset_type": "badge", "asset_id": bid,
                           "price_energy": 20, "quantity": 2}, headers=tok("0xlearner"))
        assert r.status_code == 200, r.text
        assert r.json()["quantity"] == 2 and r.json()["held"] == 3
        # 同一行资产不允许两个在售挂牌（防一份资产拆多单超卖）
        r = eco.post(f"{P}/market/list",
                     json={"seller": "0xlearner", "asset_type": "badge", "asset_id": bid,
                           "price_energy": 20, "quantity": 1}, headers=tok("0xlearner"))
        assert r.status_code == 400 and "请先取消原挂牌" in r.json()["detail"]

    def test_node_identity_cannot_trade(self, eco):
        give(eco, "0xlearner", times=3)
        bt = next(t for t in eco.get(f"{P}/badges/types").json() if t["badge_type"] == "badge")
        eco.post(f"{P}/badges/exchange",
                 json={"wallet": "0xlearner", "badge_type": "badge",
                       "type_id": bt["id"], "quantity": 1}, headers=tok("0xlearner"))
        bid, _ = self._badge_id(eco, "0xlearner")
        select(eco, "0xlearner", "bus")
        r = eco.post(f"{P}/market/list",
                     json={"seller": "0xlearner", "asset_type": "badge", "asset_id": bid,
                           "price_energy": 20, "quantity": 1}, headers=tok("0xlearner"))
        assert r.status_code == 403 and CAP_MARKET_TRADE in r.json()["detail"]
        r = eco.post(f"{P}/market/buy", json={"buyer": "0xlearner", "listing_id": 1},
                     headers=tok("0xlearner"))
        assert r.status_code in (400, 403, 404)
        clear(eco, "0xlearner")

    def test_trade_moves_asset_and_conserves_energy(self, eco):
        """成交守恒：买方付款、卖方收款，份数按挂牌量交割，能量不凭空回补。"""
        give(eco, "0xlearner", times=3)                     # 卖方 1500
        bt = next(t for t in eco.get(f"{P}/badges/types").json() if t["badge_type"] == "badge")
        eco.post(f"{P}/badges/exchange",
                 json={"wallet": "0xlearner", "badge_type": "badge",
                       "type_id": bt["id"], "quantity": 3}, headers=tok("0xlearner"))
        bid, _ = self._badge_id(eco, "0xlearner")           # 3 份，成本 30
        listing = eco.post(f"{P}/market/list",
                           json={"seller": "0xlearner", "asset_type": "badge",
                                 "asset_id": bid, "price_energy": 100, "quantity": 2},
                           headers=tok("0xlearner")).json()
        give(eco, "0xlearner2", times=1)                    # 买方 500
        before_seller = balance(eco, "0xlearner")
        r = eco.post(f"{P}/market/buy",
                     json={"buyer": "0xlearner2", "listing_id": listing["listing_id"]},
                     headers=tok("0xlearner2", user_id="u2"))
        assert r.status_code == 200, r.text
        assert balance(eco, "0xlearner") == before_seller + 100    # 收款
        assert balance(eco, "0xlearner2") == 500 - 100             # 付款（不重复扣成本）
        kinds = {f["kind"] for f in flows(eco, "0xlearner")["items"]}
        assert {"issue", "exchange_out", "market_in"} <= kinds
        buyer_badge = eco.get(f"{P}/badges/list", params={"owner": "0xlearner2"},
                              headers=tok("0xlearner2", user_id="u2")).json()["items"]
        assert buyer_badge[0]["quantity"] == 2                     # 按份数交割
        remain = eco.get(f"{P}/badges/list", params={"owner": "0xlearner"},
                         headers=tok("0xlearner")).json()["items"]
        assert next(b for b in remain if b["id"] == bid)["quantity"] == 1   # 卖方留 1 份
        # 守恒：Σ流水 == 累计发行 − 累计销毁（转手只改变归属，不增减总量）
        assert ledger_sum() == 1500 + 500
        st = eco.get(f"{P}/treasury/overview", params={"wallet": "0xlearner"},
                     headers=tok("0xlearner")).json()
        assert st["inflation_audit"]["conserved"] is True


# ===========================================================================
# 6. 治理维度：能量国库与销毁（通胀敞口可审计）
# ===========================================================================
class TestTreasuryDimension:
    def test_conservation_after_full_loop(self, eco):
        """发行 → 兑换回收 → 市场转手后，账本必须仍守恒（B1 回归）。"""
        give(eco, "0xlearner", times=3)
        bt = next(t for t in eco.get(f"{P}/badges/types").json() if t["badge_type"] == "badge")
        eco.post(f"{P}/badges/exchange",
                 json={"wallet": "0xlearner", "badge_type": "badge",
                       "type_id": bt["id"], "quantity": 3}, headers=tok("0xlearner"))
        cost = bt["cost_energy"] * 3
        st = eco.get(f"{P}/treasury/overview", params={"wallet": "0xlearner"},
                     headers=tok("0xlearner")).json()
        assert st["total_issued"] == 1500 and st["total_recycled"] == cost
        assert st["pending_burn"] == cost and st["total_burned"] == 0
        assert st["circulating"] == 1500 - cost
        assert st["circulating"] + st["treasury_balance"] == st["net_issuance"]
        assert st["inflation_audit"]["conserved"] is True, st["inflation_audit"]
        # 国库钱包字段也是资产口径：wallet = 真实地址，别名只进 wallet_alias
        assert st["treasury_wallet"] == to_address(TREASURY_WALLET)
        assert is_address(st["treasury_wallet"]), st["treasury_wallet"]
        assert st["treasury_wallet_alias"] == TREASURY_WALLET
        # 授信视图：回收公司已用 1500 / 授信 8000
        q = next(n for n in st["node_quotas"] if n["role_key"] == "recycling")
        assert q["used"] == 1500 and q["remaining"] == q["quota"] - 1500
        assert q["wallet"] == to_address("0xrecycle") and q["wallet_alias"] == "0xrecycle"

    def test_burn_requires_govern_identity(self, eco):
        """销毁仅治理身份：学生冒用 0xadmin 403，居民 403，教师 + 0xadmin 可执行。"""
        give(eco, "0xlearner", times=3)
        bt = next(t for t in eco.get(f"{P}/badges/types").json() if t["badge_type"] == "badge")
        eco.post(f"{P}/badges/exchange",
                 json={"wallet": "0xlearner", "badge_type": "badge",
                       "type_id": bt["id"], "quantity": 3}, headers=tok("0xlearner"))
        cost = bt["cost_energy"] * 3
        r = eco.post(f"{P}/treasury/burn",
                     json={"wallet": TREASURY_WALLET, "amount": cost, "note": "学生越权"},
                     headers=tok(TREASURY_WALLET, role_id=STUDENT))
        assert r.status_code == 403 and "治理职能" in r.json()["detail"]
        r = eco.post(f"{P}/treasury/burn",
                     json={"wallet": "0xlearner", "amount": 1, "note": "居民"},
                     headers=tok("0xlearner", role_id=TEACHER))
        assert r.status_code == 403 and CAP_TREASURY_MANAGE in r.json()["detail"]
        # 可销毁上限 = 已回收未销毁（不能销毁尚未发行的授信）
        r = eco.post(f"{P}/treasury/burn",
                     json={"wallet": TREASURY_WALLET, "amount": cost + 1, "note": "超量"},
                     headers=tok(TREASURY_WALLET, role_id=TEACHER))
        assert r.status_code == 400 and "可销毁余额不足" in r.json()["detail"]
        ok = eco.post(f"{P}/treasury/burn",
                      json={"wallet": TREASURY_WALLET, "amount": cost, "note": "季度销毁"},
                      headers=tok(TREASURY_WALLET, role_id=TEACHER))
        assert ok.status_code == 200, ok.text
        assert ok.json()["total_burned"] == cost
        assert ok.json()["net_issuance"] == 1500 - cost
        st = eco.get(f"{P}/treasury/overview", params={"wallet": TREASURY_WALLET},
                     headers=tok(TREASURY_WALLET, role_id=TEACHER)).json()
        assert st["pending_burn"] == 0 and st["burn_rate"] == 100.0
        assert st["inflation_audit"]["conserved"] is True
        assert st["can_burn"] is True and "burns" in st and st["burns"][0]["amount"] == cost
        assert balance(eco, TREASURY_WALLET) == 0            # 国库回收的能量已退出流通

    def test_resident_view_cannot_burn(self, eco):
        """/treasury/overview 对所有身份只读开放，can_burn 由后端算给前端。"""
        st = eco.get(f"{P}/treasury/overview", params={"wallet": "0xlearner"},
                     headers=tok("0xlearner")).json()
        assert st["can_burn"] is False and st["total_issued"] == 0


# ===========================================================================
# 8. 台账双视角（发行方看自己的发行列表 / 接收方看自己的获取列表）
#    eco_energy_records.wallet 是接收居民地址、issuer_wallet 才是节点组织钱包；
#    节点若用默认口径查自己，发行列表恒为空（前端「本节点发行列表」空表的根因）。
# ===========================================================================
class TestLedgerViews:
    def _records(self, client, wallet, by=None):
        params = {"wallet": wallet}
        if by:
            params["by"] = by
        r = client.get(f"{P}/energy/records", params=params, headers=tok(wallet))
        assert r.status_code == 200, r.text
        return r.json()

    def test_energy_records_split_by_receiver_and_issuer(self, eco):
        """同一批发放：居民按接收方看到获取列表，节点按发行方看到发行列表。"""
        resident = "0xlearner9"
        give(eco, resident, times=2)                      # 2 笔 × 500，发行方 = 回收公司
        recv = self._records(eco, resident)
        assert recv["by"] == "receiver"                   # 默认口径不变（旧前端无感）
        assert recv["total_count"] == 2 and recv["total_points"] == 1000
        assert len(recv["items"]) == 2
        issuer = to_address("0xrecycle")
        mine = self._records(eco, "0xrecycle", by="issuer")
        assert mine["by"] == "issuer"
        assert mine["total_count"] >= 2 and mine["total_points"] >= 1000
        # 发行方视角必须答得出「发给了谁」，两侧地址都是真实地址（不得残留别名）
        assert all(str(r["receiver_wallet"]).lower() == to_address(resident)
                   for r in mine["items"]), mine["items"]
        assert all(is_address(str(r["issuer_wallet"])) for r in mine["items"])
        # 组织钱包在接收方口径下查不到这些发放（这正是旧行为下空表的原因）
        assert self._records(eco, "0xrecycle")["total_count"] == 0

    def test_energy_records_role_filter_and_limit(self, eco):
        """role_key 可按节点业务收窄；total_points 不受 limit 截断。"""
        resident = "0xlearner8"
        give(eco, resident, times=2, tag="x")
        issue(eco, resident, "metro",
              {"station_in": "国贸", "station_out": "西二旗", "board_time": "08:05",
               "distance_km": 12, "trip_no": f"T-{resident}"})
        issuer = to_address("0xrecycle")
        only = eco.get(f"{P}/energy/records",
                       params={"wallet": issuer, "by": "issuer", "role_key": "recycling"},
                       headers=tok("0xrecycle")).json()
        assert {r["role_key"] for r in only["items"]} == {"recycling"}
        page = eco.get(f"{P}/energy/records",
                       params={"wallet": issuer, "by": "issuer", "limit": 1},
                       headers=tok("0xrecycle")).json()
        assert len(page["items"]) == 1 and page["total_count"] >= 2
        assert page["total_points"] >= 1000               # 累计是全集聚合，不是本页求和

    def test_badge_records_split_by_owner_and_issuer(self, eco):
        """铸造入口下方要能列出本节点发行 / 发放的清单（含发行链路口径）。"""
        bt = next(t for t in eco.get(f"{P}/badges/types").json() if t["badge_type"] == "badge")
        r = eco.post(f"{P}/badges/mint",
                     json={"wallet": "0xmetro", "role_key": "metro",
                           "type_id": bt["id"], "to_wallet": "0xlearner", "quantity": 2},
                     headers=tok("0xmetro"))
        assert r.status_code == 200, r.text
        org = to_address("0xmetro")
        issued = eco.get(f"{P}/badges/list", params={"owner": org, "by": "issued"},
                         headers=tok("0xmetro")).json()
        assert issued["by"] == "issued"
        row = next(x for x in issued["items"] if int(x["id"]) == int(r.json()["badge_id"]))
        assert row["source"] == "mint" and row["owner"].lower() == to_address("0xlearner")
        assert row["issued_by"].lower() == org
        # 机构钱包按持有口径看不到（资产不属于它），居民按持有口径能看到份数
        assert eco.get(f"{P}/badges/list", params={"owner": org},
                       headers=tok("0xmetro")).json()["items"] == []
        held = eco.get(f"{P}/badges/list", params={"owner": "0xlearner"},
                       headers=tok("0xlearner")).json()
        assert held["by"] == "owner"
        assert any(int(x["quantity"]) == 2 and x["source"] == "mint"
                   for x in held["items"]), held["items"]
