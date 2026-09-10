"""绿色能量「账本 vs 链上」双口径回归（真机实测症状锁定）。

现场：用户提交低碳凭证成功 → 钱包页能量不涨、联盟链页能量在涨、勋章 / 骑行券
兑换全部报错。根因是能量余额同时存在两个事实源：

- 联盟页与兑换前的余额校验读**能量账本**（eco_energy_flows，SQLite 持久）；
- 钱包页与兑换时的实际扣款读**链上** GreenEnergy（本地沙盒链是进程内内存链，
  后端每重启一次余额全清零）。

链重置后账本 > 链上，于是「钱包页 0 点」+「链上 transfer revert」，而回填实现
是 best-effort 且失败静默 return，前端只能拿到 `GE: insufficient balance`。

本文件用一份带真实余额语义的假链（余额字典 + onlyIssuer + 余额不足 revert）把
三件事钉住：
① 余额只有一个事实源：钱包页与联盟页读到同一个账本净额，并暴露待同步差额；
② 扣款前必须把差额回填到链上，回填失败抛**可诊断中文**，不冒 revert 原文；
③ 启动对账 align_chain_balances() 能把全量账本余额补回链上。
"""
from __future__ import annotations

import json

import pytest

from app import alliance_contracts
from app.alliance_contracts import ENERGY_TOKEN_NAME, sync_energy_token
from app.db import get_conn, now
from app.routers import eco
from app.routers import wallet as wallet_router
from app.security import create_token
from app.wallet_id import to_address

P = "/api/eco"
GE_ADDR = "0x" + "a1" * 20
PC_ADDR = "0x" + "b2" * 20
EB_ADDR = "0x" + "c3" * 20
RESIDENT = "0xlearner9"
TREASURY = to_address(eco.TREASURY_WALLET)

_FN = {"type": "function", "stateMutability": "nonpayable", "inputs": [], "outputs": []}
_VIEW = {"type": "function", "stateMutability": "view", "inputs": [],
         "outputs": [{"name": "", "type": "uint256"}]}
ABI = [dict(_FN, name=n) for n in
       ("mint", "transfer", "burn", "addIssuer")] + \
      [dict(_VIEW, name=n) for n in ("balanceOf", "totalSupply", "issuers", "owner")]


class FakeChain:
    """GreenEnergy / EcoBadge 语义的极简假链：真实余额 + onlyIssuer + revert 原文。

    只为暴露「链上余额与账本脱节」这一类缺陷而存在：余额按地址记账、mint 需要
    发行权、transfer 需要余额充足，revert 文案与 contracts/*.sol 逐字一致。
    """

    def __init__(self, *, ge_owner: str, ge_issuers: set, eb_owner: str, eb_issuers: set):
        self.owners = {GE_ADDR: ge_owner, PC_ADDR: ge_owner, EB_ADDR: eb_owner}
        self.issuers = {GE_ADDR: set(ge_issuers), PC_ADDR: set(), EB_ADDR: set(eb_issuers)}
        self.balances: dict = {}
        self.calls: list = []

    # -- 链客户端最小接口 ---------------------------------------------------
    def resolve_account(self, addr):
        return to_address(addr) or (addr or "").lower()

    def has_code(self, address):
        return str(address or "").lower() in (GE_ADDR, PC_ADDR, EB_ADDR)

    def block_number(self):
        return 1

    # 只读 / 写交易分类（启动对账必须区分「重入查询」与「真发了交易」）
    VIEWS = ("balanceOf", "owner", "issuers", "totalSupply", "symbol", "decimals")

    def write_calls(self) -> list:
        return [c for c in self.calls if c[1] not in self.VIEWS]

    # -- 记账辅助 -----------------------------------------------------------
    def _get(self, addr):
        return int(self.balances.get(self.resolve_account(addr), 0))

    def _add(self, addr, delta):
        a = self.resolve_account(addr)
        self.balances[a] = max(0, int(self.balances.get(a, 0)) + int(delta))

    def set_balance(self, addr, value):
        self.balances[self.resolve_account(addr)] = int(value)

    # -- 合约调用 -----------------------------------------------------------
    def call_contract(self, address, method, args, caller, abi):
        args = list(args or [])
        addr = str(address or "").lower()
        who = self.resolve_account(caller)
        self.calls.append((addr, method, tuple(args), who))
        ok = lambda r="True": {"ok": True, "readonly": False, "tx_hash": "0x" + "ee" * 32,
                               "block_number": 1, "result": r, "status": "success",
                               "method": method, "args": args}
        bad = lambda e: {"ok": False, "readonly": False, "tx_hash": "", "result": "",
                         "error": e, "status": "reverted", "method": method, "args": args}
        if addr not in self.owners:
            # 链重置 / 地址错位时真实链就是无代码回 revert，不能假装读出 0
            return bad("execution reverted: no contract code at address")
        # 发行白名单三件套（三份内置合约同一口径）
        if method == "owner":
            return ok(self.owners[addr])
        if method == "issuers":
            return ok(bool(who and self.resolve_account(args[0]) in self.issuers[addr]))
        if method == "addIssuer":
            if who != self.owners[addr]:
                return bad({GE_ADDR: "GE: not owner", EB_ADDR: "EB: not owner"}.get(addr, "not owner"))
            self.issuers[addr].add(self.resolve_account(args[0]))
            return ok("True")
        if method == "mint":
            if who != self.owners[addr] and who not in self.issuers[addr]:
                return bad({GE_ADDR: "GE: not issuer", EB_ADDR: "EB: not issuer"}.get(addr, "not issuer"))
            if addr == GE_ADDR:
                self._add(args[0], int(args[1]))
            return ok("True")
        if addr == GE_ADDR:
            if method == "balanceOf":
                return ok(self._get(args[0]))
            if method == "transfer":
                v = int(args[1])
                if self._get(who) < v:
                    return bad("GE: insufficient balance")
                self._add(who, -v)
                self._add(args[0], v)
                return ok("True")
            if method == "burn":
                v = int(args[0])
                if self._get(who) < v:
                    return bad("GE: insufficient balance")
                self._add(who, -v)
                return ok("True")
        if addr == EB_ADDR and method == "balanceOf":
            return ok(1)
        return ok("True")


@pytest.fixture
def chain(temp_db, monkeypatch):
    """三份内置合约落库 + 假链接管 eco / wallet / 取址三处链入口（链上余额全 0）。

    必须显式依赖 temp_db：本文件的 _credit() 直接写 eco_energy_flows，
    少了这个依赖就会落到 settings.db_path 指向的真实库上。
    """
    with get_conn() as conn:
        for name, addr, std in ((ENERGY_TOKEN_NAME, GE_ADDR, "ERC20"),
                                ("PlantCertificate", PC_ADDR, "ERC721"),
                                ("EcoBadge", EB_ADDR, "ERC1155")):
            conn.execute("DELETE FROM deployed_contracts WHERE address=?", (addr,))
            conn.execute(
                "INSERT INTO deployed_contracts(address,name,abi,bytecode,source,deployer,"
                "tx_hash,standard,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (addr, name, json.dumps(ABI), "0x00", "", "0xadmin", "0xseed", std, now()))
    sync_energy_token(GE_ADDR, owner=TREASURY)
    fake = FakeChain(ge_owner=TREASURY, ge_issuers={TREASURY},
                     eb_owner=TREASURY, eb_issuers={TREASURY})
    monkeypatch.setattr(eco, "get_chain_client", lambda *a, **kw: fake)
    monkeypatch.setattr(wallet_router, "get_chain_client", lambda *a, **kw: fake)
    monkeypatch.setattr(alliance_contracts, "get_chain_client", lambda *a, **kw: fake)
    return fake


def _credit(wallet: str, points: int, ref: str) -> None:
    """只写账本流水、不碰链上：精确复现「链重启后账本仍留着历史余额」。"""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO eco_energy_flows(wallet,kind,amount,ref,note,role_key,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (to_address(wallet), "issue", int(points), ref, "历史发放", "recycling", now()))


def _tok(wallet: str, role_id: int = 4) -> dict:
    return {"Authorization": "Bearer " + create_token({
        "user_id": wallet, "role_id": role_id, "wallet": wallet,
        "class_id": "c1", "user_name": wallet})}


def _ge_item(client, wallet: str) -> dict:
    body = client.get(f"/api/wallet/balances/{wallet}").json()
    return next(i for i in body["items"] if i["symbol"] == "GE")


class TestSingleSourceOfTruth:
    """① 链上为 0、账本有余额时，钱包页与联盟页必须报同一个数（账本口径）。"""

    def test_wallet_page_shows_ledger_not_zero(self, client, chain):
        _credit(RESIDENT, 300, "energy:hist-1")
        item = _ge_item(client, RESIDENT)
        assert item["balance"] == "300", item          # 旧行为：链上 balanceOf → "0"
        assert item["ledger_balance"] == 300 and item["chain_balance"] == 0
        assert item["needs_sync"] is True and item["sync_gap"] == 300
        eco_body = client.get(f"{P}/energy/balance", params={"wallet": RESIDENT},
                              headers=_tok(RESIDENT)).json()
        assert int(eco_body["balance"]) == int(item["balance"]) == 300   # 两页同一口径

    def test_query_failure_is_not_masked_as_zero(self, client, chain):
        """普通代币查不动时不得伪装成余额 0（旧实现 except → "0"）。"""
        with get_conn() as conn:
            conn.execute("INSERT INTO tokens(address,name,symbol,decimals,total_supply,owner,"
                         "created_at) VALUES(?,?,?,?,?,?,?)",
                         ("0x" + "f9" * 20, "Broken", "BRK", 18, "0", TREASURY, now()))
        body = client.get(f"/api/wallet/balances/{RESIDENT}").json()
        brk = next(i for i in body["items"] if i["symbol"] == "BRK")
        assert brk["query_ok"] is False and brk["query_note"]


class TestBackfillBeforeDeduct:
    """② 扣款前把差额补到链上；补不动时给可诊断中文，不冒 revert 原文。"""

    def test_sync_mints_the_gap(self, chain):
        _credit(RESIDENT, 300, "energy:hist-2")
        res = eco._sync_chain_balance(RESIDENT)
        assert res["ok"] is True and res["diff"] == 300, res
        assert res["chain_balance_after"] == 300
        assert eco._energy_balance_view(RESIDENT)["needs_sync"] is False

    def test_sync_reports_failure_instead_of_swallowing_it(self, chain, monkeypatch):
        """链上合约的管理员既不是 owner 也无发行权（重部署后最常见的形态）。"""
        chain.owners[GE_ADDR] = "0x" + "d3" * 20
        chain.issuers[GE_ADDR] = set()
        _credit(RESIDENT, 300, "energy:hist-3")
        res = eco._sync_chain_balance(RESIDENT)
        assert res["ok"] is False, res
        assert "链上能量补发失败" in res["detail"] and "insufficient" not in res["detail"]

    def test_backfill_failure_surfaces_as_http_400_not_revert(self, client, chain):
        chain.owners[GE_ADDR] = "0x" + "d3" * 20
        chain.issuers[GE_ADDR] = set()
        _credit(RESIDENT, 300, "energy:hist-4")
        r = client.post(f"{P}/badges/exchange",
                        json={"wallet": RESIDENT, "badge_type": "badge", "quantity": 1},
                        headers=_tok(RESIDENT))
        assert r.status_code == 400, r.text
        detail = r.json()["detail"]
        assert "链上能量补发失败" in detail, detail
        assert "GE: insufficient balance" not in detail        # 不再冒合约原文
        # 失败不能留下半截账：额度回滚、账本不动
        assert eco._get_energy_ledger_balance(RESIDENT) == 300

    def test_badge_exchange_succeeds_after_chain_reset_drift(self, client, chain):
        """真机主症状：链上 0 点、账本 300 点，兑换勋章 / 骑行券必须成功。"""
        _credit(RESIDENT, 300, "energy:hist-5")
        for badge, cost in (("badge", 10), ("voucher", 20)):
            r = client.post(f"{P}/badges/exchange",
                            json={"wallet": RESIDENT, "badge_type": badge, "quantity": 1},
                            headers=_tok(RESIDENT))
            assert r.status_code == 200, r.text
        assert eco._get_energy_ledger_balance(RESIDENT) == 270
        view = eco._energy_balance_view(RESIDENT)
        assert view["chain_balance"] == 270 and view["needs_sync"] is False

    def test_insufficient_ledger_balance_is_still_friendly(self, client, chain):
        _credit(RESIDENT, 5, "energy:hist-6")
        r = client.post(f"{P}/badges/exchange",
                        json={"wallet": RESIDENT, "badge_type": "voucher", "quantity": 1},
                        headers=_tok(RESIDENT))
        assert r.status_code == 400, r.text
        assert "绿色能量不足" in r.json()["detail"] and "voucher" not in r.json()["detail"]


class TestStartupAlignment:
    """③ 启动对账：把所有「账本 > 链上」的钱包一次性补回链上。"""

    def test_align_repairs_every_drifted_wallet(self, chain):
        _credit(RESIDENT, 300, "energy:hist-7")
        _credit("0xlearner7", 120, "energy:hist-8")
        _credit(eco.TREASURY_WALLET, 60, "energy:hist-9")
        report = eco.align_chain_balances()
        assert report["failed"] == 0, report
        assert report["aligned"] == 3 and report["minted_total"] == 480, report
        assert eco._energy_balance_view(RESIDENT)["needs_sync"] is False
        assert eco._energy_balance_view("0xlearner7")["chain_balance"] == 120

    def test_align_is_noop_when_already_consistent(self, chain):
        _credit(RESIDENT, 300, "energy:hist-10")
        first = eco.align_chain_balances()
        txs_before = len(chain.write_calls())
        second = eco.align_chain_balances()
        assert first["aligned"] == 1 and second["aligned"] == 0
        assert second["skipped"] == first["total"]
        assert len(chain.write_calls()) == txs_before     # 已一致的钱包不再发交易
