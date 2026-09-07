"""P0 回归：GreenEnergy「哪一份是当前生效合约」必须全平台只有一个口径。

背景（真机实测复现）：GreenEnergy 会被反复重新部署（教程第 9 步 deploy、联盟页
「一键激活」），而平台曾存在两套取址：

- 联盟业务读写（能量发行 / 兑换 / 余额）→ 按 created_at DESC 取 deployed_contracts 最新一份；
- 能量钱包页与 NFT 市场结算 → 读 tokens 表，而该表只在后端启动的 seed 里写一次。

于是「重启后重跑第 9 步」把业务口径切到新地址、tokens 仍指旧地址：学生在联盟页
有 270 点能量，到 NFT 市场付款却被告知「当前 0」，实训报告 C 项「成交 +5」结构性
拿不到。本文件锁死两件事：① 取址只有 latest_deployed()；② 每次换实例都要
sync_energy_token()，让 tokens 跟着走。
"""
from __future__ import annotations

import json

from app.alliance_contracts import (
    DEFAULT_CTOR_ARGS,
    ENERGY_TOKEN_NAME,
    latest_deployed,
    sync_energy_token,
)
from app.db import get_conn, now


def _deploy(name: str, address: str, abi=None) -> None:
    """往 deployed_contracts 写一条部署记录（模拟一次成功部署的落库动作）。"""
    with get_conn() as conn:
        conn.execute("DELETE FROM deployed_contracts WHERE address=?", (address,))
        conn.execute(
            "INSERT INTO deployed_contracts(address,name,abi,bytecode,source,deployer,"
            "tx_hash,standard,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (address, name, json.dumps(abi if abi is not None else []), "0x", "",
             "0xadmin", "0xtx", "ERC20", now()),
        )


class TestLatestDeployedIsSingleSource:
    def test_returns_none_when_never_deployed(self, temp_db):
        assert latest_deployed(ENERGY_TOKEN_NAME) == (None, None)

    def test_picks_the_newest_instance(self, temp_db):
        _deploy(ENERGY_TOKEN_NAME, "0x" + "a1" * 20, [{"type": "constructor"}])
        _deploy(ENERGY_TOKEN_NAME, "0x" + "b2" * 20, [{"type": "function", "name": "mint"}])
        addr, abi = latest_deployed(ENERGY_TOKEN_NAME)
        assert addr == "0x" + "b2" * 20
        assert [f["name"] for f in abi if f.get("type") == "function"] == ["mint"]

    def test_other_contract_names_do_not_leak(self, temp_db):
        _deploy("EcoBadge", "0x" + "c3" * 20)
        assert latest_deployed(ENERGY_TOKEN_NAME) == (None, None)


class TestEnergyTokenRegistryStaysInSync:
    def test_sync_registers_current_instance(self, temp_db):
        _deploy(ENERGY_TOKEN_NAME, "0x" + "d4" * 20)
        assert sync_energy_token("0x" + "d4" * 20, owner="0xowner") is True
        with get_conn() as conn:
            rows = conn.execute("SELECT * FROM tokens WHERE name=?",
                                (ENERGY_TOKEN_NAME,)).fetchall()
        assert len(rows) == 1, "tokens 只允许一份 GreenEnergy 登记，换址不能留残行"
        assert rows[0]["address"] == "0x" + "d4" * 20
        assert rows[0]["symbol"] == "GE"

    def test_redeploy_moves_the_registration(self, temp_db):
        """教程第 9 步重跑一次 = 全平台换一份能量合约：钱包/市场登记必须跟着换。"""
        _deploy(ENERGY_TOKEN_NAME, "0x" + "e5" * 20)
        sync_energy_token("0x" + "e5" * 20, owner="0xowner")
        new_addr, _ = latest_deployed(ENERGY_TOKEN_NAME)
        assert new_addr == "0x" + "e5" * 20

        _deploy(ENERGY_TOKEN_NAME, "0x" + "f6" * 20)      # 再次部署（新地址）
        sync_energy_token(latest_deployed(ENERGY_TOKEN_NAME)[0], owner="0xowner")
        with get_conn() as conn:
            rows = conn.execute("SELECT address FROM tokens WHERE name=?",
                                (ENERGY_TOKEN_NAME,)).fetchall()
        assert [r["address"] for r in rows] == ["0x" + "f6" * 20]

    def test_empty_address_is_refused(self, temp_db):
        assert sync_energy_token("") is False

    def test_energy_genesis_supply_is_zero(self, temp_db):
        """能量不得创世预挖：教程 / seed / eco 共用 DEFAULT_CTOR_ARGS 的 [0]。"""
        assert DEFAULT_CTOR_ARGS[ENERGY_TOKEN_NAME] == [0]
