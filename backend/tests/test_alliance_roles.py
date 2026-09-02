"""alliance_roles 测试：ROLES 数据完整性 / 权限助手真假分支 / require_alliance_role 403。

require_alliance_role 走真实 HTTP 路径验证：在测试内构建最小 FastAPI 应用
（GET 用 query wallet / POST 用 JSON body wallet），角色选择直接写
eco_role_selections 表（模拟前端「切换角色」落库）。
"""
import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.db import get_conn, now
from app.learning.alliance_roles import (
    PERMISSION_FLAGS, ROLES, ROLE_ALIAS,
    ensure_admin_for_trees, ensure_asset_owner, ensure_bike_for_voucher,
    ensure_issuer_role, ensure_minter_role, find_role,
    get_role_permissions, has_permission, require_alliance_role,
    role_permission_matrix,
)

EXPECTED_KEYS = ["admin", "metro", "bus", "bike", "takeout", "recycling"]
BASE_FIELDS = {"key", "name", "icon", "color", "wallet", "desc", "energy_rule",
               "can_issue_badge", "can_issue_voucher", "can_manage_trees"}

class TestRolesDefinition:
    def test_six_roles_with_expected_keys(self):
        assert [r["key"] for r in ROLES] == EXPECTED_KEYS

    def test_base_fields_complete(self):
        for r in ROLES:
            assert BASE_FIELDS <= set(r), f"角色 {r['key']} 缺字段: {BASE_FIELDS - set(r)}"

    def test_admin_has_no_energy_rule(self):
        admin = find_role("admin")
        assert admin["energy_rule"] is None
        assert admin["wallet"] == "0xadmin"

    def test_business_roles_energy_rule_and_proof_fields(self):
        for r in ROLES:
            if r["key"] == "admin":
                continue
            er = r["energy_rule"]
            assert er, f"{r['key']} 缺 energy_rule"
            pfs = er["proof_fields"]
            assert isinstance(pfs, list) and pfs, f"{r['key']} proof_fields 为空"
            keys = {f["key"] for f in pfs}
            assert er["proof_field"] in keys, f"{r['key']} proof_field 未在 proof_fields 中"
            for f in pfs:
                assert {"key", "label", "type", "required"} <= set(f)
            assert er["points"] > 0 and er["min"] > 0
            assert er.get("proof_no_field"), f"{r['key']} 缺业务单号字段"
            assert "proof_example" in er

    def test_role_alias_mapping(self):
        assert ROLE_ALIAS == {"delivery": "takeout", "recycle": "recycling"}
        assert set(PERMISSION_FLAGS) == {
            "can_issue_badge", "can_issue_voucher", "can_manage_trees"}

class TestPermissionHelpers:
    def test_find_role_basic_alias_case(self):
        assert find_role("metro")["key"] == "metro"
        assert find_role("DELIVERY")["key"] == "takeout"      # 别名 + 大小写归一
        assert find_role("  recycle ")["key"] == "recycling"  # 别名 + 空白归一
        assert find_role("nope") is None
        assert find_role("") is None

    def test_get_role_permissions_true_branch(self):
        p = get_role_permissions("metro")
        assert p == {"key": "metro", "name": "地铁集团", "can_issue_badge": True,
                     "can_issue_voucher": False, "can_manage_trees": False,
                     "has_energy_rule": True}

    def test_get_role_permissions_false_branch(self):
        p = get_role_permissions("admin")
        assert p["has_energy_rule"] is False
        assert p["can_manage_trees"] is True
        assert p["can_issue_badge"] is False
        assert get_role_permissions("ghost") is None
        # 传角色 dict 与传 key 等价
        assert get_role_permissions(find_role("bike")) == get_role_permissions("bike")

    def test_role_permission_matrix_snapshot(self):
        matrix = role_permission_matrix()
        assert [m["key"] for m in matrix] == EXPECTED_KEYS
        assert all(m is not None for m in matrix)

    def test_has_permission_unknown_flag_false(self):
        metro = find_role("metro")
        assert has_permission(metro, "can_issue_badge") is True
        assert has_permission(metro, "not_a_flag") is False
        assert has_permission(None, "can_issue_badge") is False

def _select_role(wallet, role_key):
    """直接写 eco_role_selections（模拟前端「切换角色」落库）。"""
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO eco_role_selections(wallet, role_key, selected_at) "
            "VALUES(?,?,?)", (wallet, role_key, now()))


@pytest.fixture
def probe_client(temp_db):
    """最小 FastAPI 应用：GET 用 query wallet，POST 用 JSON body wallet。"""
    app = FastAPI()

    @app.get("/probe")
    def probe_get(role: dict = Depends(require_alliance_role("can_issue_badge"))):
        return {"ok": True, "role": role["key"]}

    @app.post("/probe")
    def probe_post(payload: dict,
                   role: dict = Depends(require_alliance_role("can_issue_badge"))):
        return {"ok": True, "role": role["key"]}

    return TestClient(app)


class TestRequireAllianceRole:
    def test_403_when_no_role_selected(self, probe_client):
        r = probe_client.get("/probe", params={"wallet": "0xlearner"})
        assert r.status_code == 403
        assert "未选择联盟角色" in r.json()["detail"]

    def test_403_when_role_lacks_flag(self, probe_client):
        _select_role("0xadmin", "admin")  # admin 无 can_issue_badge
        r = probe_client.get("/probe", params={"wallet": "0xadmin"})
        assert r.status_code == 403
        assert "不具备所需联盟权限位" in r.json()["detail"]
        assert "can_issue_badge" in r.json()["detail"]

    def test_200_with_query_wallet(self, probe_client):
        _select_role("0xmetro", "metro")
        r = probe_client.get("/probe", params={"wallet": "0xmetro"})
        assert r.status_code == 200
        assert r.json() == {"ok": True, "role": "metro"}

    def test_wallet_from_json_body(self, probe_client):
        _select_role("0xbus", "bus")
        r = probe_client.post("/probe", json={"wallet": "0xbus", "x": 1})
        assert r.status_code == 200
        assert r.json()["role"] == "bus"

    def test_body_wallet_missing_role_403(self, probe_client):
        r = probe_client.post("/probe", json={"wallet": "0xghost"})
        assert r.status_code == 403

    def test_alias_role_selection(self, probe_client):
        # 历史别名 delivery 落库后，0xtakeout 请求应命中 takeout
        _select_role("0xtakeout", "delivery")
        r = probe_client.get("/probe", params={"wallet": "0xtakeout"})
        assert r.status_code == 200
        assert r.json()["role"] == "takeout"


ROLE = {"key": "metro", "name": "地铁集团"}


def _expect_403(fn, *args):
    with pytest.raises(HTTPException) as ei:
        fn(*args)
    assert ei.value.status_code == 403
    return ei.value.detail


class TestBusinessContextGuards:
    """业务上下文权限助手（ensure_* 系列）真假分支。"""

    def test_ensure_issuer_role(self):
        ensure_issuer_role(ROLE, {"key": "metro", "name": "地铁集团"})            # 一致 → 通过
        assert "未选择联盟角色" in _expect_403(ensure_issuer_role, ROLE, None)
        assert "不一致" in _expect_403(ensure_issuer_role, ROLE, {"key": "bus", "name": "公交集团"})

    def test_ensure_minter_role(self):
        ensure_minter_role(ROLE, {"key": "metro"})
        assert "铸造权限不足" in _expect_403(ensure_minter_role, ROLE, None)
        assert "铸造权限不足" in _expect_403(ensure_minter_role, ROLE, {"key": "admin", "name": "管理员"})

    def test_ensure_admin_for_trees(self):
        ensure_admin_for_trees("admin")
        assert "仅管理员" in _expect_403(ensure_admin_for_trees, "bus")
        assert "仅管理员" in _expect_403(ensure_admin_for_trees, None)

    def test_ensure_bike_for_voucher(self):
        ensure_bike_for_voucher("bike", "add")
        ensure_bike_for_voucher("bike", "mint")
        assert "可新增" in _expect_403(ensure_bike_for_voucher, "bus", "add")
        assert "可发放" in _expect_403(ensure_bike_for_voucher, "admin", "mint")

    def test_ensure_asset_owner(self):
        ensure_asset_owner("0xa", "0xa")
        assert "只能挂自己的资产" in _expect_403(ensure_asset_owner, "0xa", "0xb")
