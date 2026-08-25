"""启动时自动播种实训基础数据。

后端每次启动时，py-evm 内存链会被重置。本模块在启动后自动：
1. 部署 3 份系统合约（GreenEnergy / PlantCertificate / EcoBadge）
2. 新增 2 个树种（管理员操作）
3. 向学习者钱包发放绿色能量（多角色场景）
4. 兑换 1 份植树证书 + 1 个生态勋章

确保前端打开时能立刻看到真实的链上数据（块高 / 交易 / 合约 / 能量 / NFT）。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from .chain_client import get_chain_client, RealEvmChainClient, MockChainClient
from .config import settings
from .db import get_conn, now
from .tx_decoder import compile_source


# 内置合约清单（与 eco.py 保持一致）
BUILTIN_CONTRACTS = [
    {"name": "GreenEnergy",      "standard": "ERC20",   "file": "GreenEnergy.sol"},
    {"name": "PlantCertificate", "standard": "ERC721",  "file": "PlantCertificate.sol"},
    {"name": "EcoBadge",         "standard": "ERC1155", "file": "EcoBadge.sol"},
]

# 各合约构造函数默认参数（与 eco.py DEFAULT_CTOR_ARGS 保持一致）
DEFAULT_CTOR_ARGS = {
    "GreenEnergy":      [1_000_000_000],
    "PlantCertificate": ["PlantCertificate", "PCERT"],
    "EcoBadge":         [],
}

# 学习者钱包别名
LEARNER_WALLET = "0xlearner"
ADMIN_WALLET = "0xadmin"


def _deploy_builtin(name: str, standard: str, file: str, deployer: str = LEARNER_WALLET) -> dict | None:
    """编译 + 部署一份内置合约，写入 deployed_contracts 表。"""
    src_path = settings.contracts_dir / file
    if not src_path.exists():
        return None
    source = src_path.read_text(encoding="utf-8")

    comp = compile_source(source)
    if not comp.get("ok"):
        print(f"[seed] 编译 {name} 失败: {comp.get('errors')}")
        return None

    c = get_chain_client()
    ctor_args = DEFAULT_CTOR_ARGS.get(name, [])
    try:
        r = c.deploy_contract(name, comp["abi"], comp["bytecode"], source,
                              deployer, standard, ctor_args)
    except Exception as e:
        print(f"[seed] 部署 {name} 失败: {e}")
        return None

    with get_conn() as conn:
        conn.execute("DELETE FROM deployed_contracts WHERE address=?", (r["address"],))
        conn.execute(
            "INSERT INTO deployed_contracts(address,name,abi,bytecode,source,deployer,tx_hash,standard,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (r["address"], name, json.dumps(comp["abi"]), comp["bytecode"], source,
             deployer, r["tx_hash"], standard, now()),
        )
    print(f"[seed] 已部署 {name} ({standard}) → {r['address']}")
    return r


def _find_contract(name: str):
    """从 deployed_contracts 表查找指定名称的最新部署合约（带 has_code 校验）。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT address, abi FROM deployed_contracts WHERE name=? ORDER BY created_at DESC LIMIT 1",
            (name,),
        ).fetchone()
    if not row:
        return None, None
    c = get_chain_client()
    if not c.has_code(row["address"]):
        return None, None
    return row["address"], json.loads(row["abi"])


def _issue_energy(wallet: str, role_key: str, role_name: str, action: str, points: int):
    """通过 GreenEnergy.mint 向钱包发放绿色能量，并记录到 eco_energy_records。"""
    ge_addr, ge_abi = _find_contract("GreenEnergy")
    if not ge_addr:
        return
    c = get_chain_client()
    r = c.call_contract(
        ge_addr, "mint",
        [c.resolve_account(wallet), points, action],
        wallet, ge_abi,
    )
    if not r.get("ok"):
        print(f"[seed] 能量发放失败 ({role_name}): {r.get('error')}")
        return
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO eco_energy_records(wallet,role_key,role_name,action,points,tx_hash,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (wallet, role_key, role_name, action, points, r.get("tx_hash", ""), now()),
        )


def _add_tree(name: str, required_energy: int, description: str):
    """新增树种（管理员操作）。"""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO eco_tree_species(name,required_energy,image_url,description,created_by,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (name, required_energy, "", description, ADMIN_WALLET, now()),
        )
        return cur.lastrowid


def _exchange_certificate(wallet: str, species_id: int, species_name: str, cost: int):
    """兑换植树证书（ERC721）。"""
    ge_addr, ge_abi = _find_contract("GreenEnergy")
    pc_addr, pc_abi = _find_contract("PlantCertificate")
    if not ge_addr or not pc_addr:
        return
    c = get_chain_client()
    admin_addr = c.resolve_account(ADMIN_WALLET)

    # 1. 扣能量（wallet → admin）
    r_t = c.call_contract(ge_addr, "transfer", [admin_addr, cost], wallet, ge_abi)
    if not r_t.get("ok"):
        return

    # 2. 铸造证书
    token_id = uuid.uuid4().int & 0xFFFFFFFF
    uri = f"pc://{token_id}"
    r_m = c.call_contract(
        pc_addr, "mint",
        [c.resolve_account(wallet), token_id, species_id, uri],
        ADMIN_WALLET, pc_abi,
    )
    if not r_m.get("ok"):
        return

    cert_no = f"PC-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO eco_certificates(token_id,species_id,species_name,owner,cost_energy,contract_address,tx_hash,cert_no,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (str(token_id), species_id, species_name, wallet, cost,
             pc_addr, r_m.get("tx_hash", ""), cert_no, now()),
        )


def _exchange_badge(wallet: str, badge_type: str, token_id: int, name: str, cost: int):
    """兑换生态勋章 / 骑行券（ERC1155）。"""
    ge_addr, ge_abi = _find_contract("GreenEnergy")
    eb_addr, eb_abi = _find_contract("EcoBadge")
    if not ge_addr or not eb_addr:
        return
    c = get_chain_client()
    admin_addr = c.resolve_account(ADMIN_WALLET)

    # 1. 扣能量
    r_t = c.call_contract(ge_addr, "transfer", [admin_addr, cost], wallet, ge_abi)
    if not r_t.get("ok"):
        return

    # 2. 铸造勋章
    r_m = c.call_contract(
        eb_addr, "mint",
        [c.resolve_account(wallet), token_id, 1, ""],
        wallet, eb_abi,
    )
    if not r_m.get("ok"):
        return

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO eco_badges(token_id,badge_type,name,owner,cost_energy,issued_by,contract_address,tx_hash,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (token_id, badge_type, name, wallet, cost,
             wallet, eb_addr, r_m.get("tx_hash", ""), now()),
        )


def seed_init_data() -> None:
    """启动时自动播种实训基础数据。仅在链为空（无合约）时执行。"""
    c = get_chain_client()
    # 仅对进程内链（evm / 沙盒）自动播种，避免误操作真实 FISCO 节点
    if not isinstance(c, (RealEvmChainClient, MockChainClient)):
        print("[seed] 非 EVM 虚拟机 / 本地沙盒模式，跳过自动播种")
        return

    # 检查是否已有可用合约（避免重复播种）
    ge_addr, _ = _find_contract("GreenEnergy")
    if ge_addr:
        print("[seed] 检测到已部署合约，跳过自动播种")
        return

    print("[seed] 开始自动播种实训基础数据 ...")

    # 1. 部署 3 份系统合约（链重启后必须重新部署，保证前端 has_code 校验通过）
    for contract in BUILTIN_CONTRACTS:
        _deploy_builtin(contract["name"], contract["standard"], contract["file"])

    # 1.1 将 GreenEnergy 登记为默认「绿色能量钱包」代币（ERC20 钱包余额列表可见）
    ge_addr, _ = _find_contract("GreenEnergy")
    if ge_addr:
        with get_conn() as conn:
            conn.execute("DELETE FROM tokens WHERE name='GreenEnergy'")
            conn.execute(
                "INSERT INTO tokens(address,name,symbol,decimals,total_supply,owner,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (ge_addr, "GreenEnergy", "GE", 0, "1000000000", ADMIN_WALLET, now()),
            )
        print("[seed] 绿色能量钱包已登记: GreenEnergy (GE)")

    # 1.2 内置「系统内置合约」IDE 工程（默认第一个工程，学生新增工程排在其后）
    _seed_builtin_project()

    # 2. 业务种子数据仅在数据库为空时播种一次（后端重启链重置但数据库持久，避免重复）
    with get_conn() as conn:
        tree_count = conn.execute("SELECT COUNT(*) FROM eco_tree_species").fetchone()[0]
    if tree_count:
        print("[seed] 检测到已有业务播种数据，跳过重复播种")
        return

    # 2.1 新增 2 个树种（管理员操作）
    tree1 = _add_tree("银杏树", 1500, "国家一级保护植物，被誉为\u201c活化石\u201d，固碳能力强")
    tree2 = _add_tree("樟子松", 1000, "耐寒耐旱，适合北方沙地绿化造林，防风固沙先锋树种")

    # 2.2 向学习者钱包发放绿色能量（覆盖 5 个联盟角色的能量发放规则，共 195 点）
    _issue_energy(LEARNER_WALLET, "metro", "地铁集团", "地铁通勤", 50)
    _issue_energy(LEARNER_WALLET, "bus", "公交集团", "公交出行", 20)
    _issue_energy(LEARNER_WALLET, "bike", "共享单车", "共享单车骑行", 15)
    _issue_energy(LEARNER_WALLET, "takeout", "外卖平台", "绿色外卖(无需餐具)", 10)
    _issue_energy(LEARNER_WALLET, "recycling", "回收公司", "可回收物回收", 100)

    # 2.3 兑换 1 份植树证书 + 1 个生态勋章（内置资产，绿色资产市场初始非空）
    if tree1:
        _exchange_certificate(LEARNER_WALLET, tree1, "银杏树", 1500)
    if tree2:
        _exchange_badge(LEARNER_WALLET, "badge", 1, "生态勋章", 10)
        with get_conn() as conn:
            conn.execute("UPDATE eco_badge_types SET minted = minted + 1 WHERE token_id=1")

    print("[seed] 实训基础数据播种完成")


def _seed_builtin_project() -> None:
    """内置「系统内置合约」IDE 工程：包含 6 份标准合约模板，学生可直接打开学习。"""
    pid = "builtin"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO projects(id,name,created_at,updated_at,is_builtin) VALUES(?,?,?,?,1) "
            "ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at",
            (pid, "系统内置合约", now(), now()),
        )
    builtin_files = [
        "GreenEnergy.sol",
        "PlantCertificate.sol",
        "EcoBadge.sol",
        "ERC20.sol",
        "ERC721.sol",
        "ERC1155.sol",
    ]
    with get_conn() as conn:
        for fname in builtin_files:
            src = settings.contracts_dir / fname
            if not src.exists():
                continue
            conn.execute(
                "INSERT INTO project_files(id,project_id,path,content,updated_at) "
                "VALUES(?,?,?,?,?) ON CONFLICT(project_id,path) "
                "DO UPDATE SET content=excluded.content, updated_at=excluded.updated_at",
                (f"{pid}-{fname}", pid, fname, src.read_text(encoding="utf-8"), now()),
            )
    print("[seed] 内置 IDE 工程「系统内置合约」已就绪（6 份合约模板）")