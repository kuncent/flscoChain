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

from . import keystore as ks
from .chain_client import get_chain_client, RealEvmChainClient, MockChainClient
from .config import settings
from .db import get_conn, now
from .energy_ledger import FLOW_BACKFILL, FLOW_ISSUE, ensure_flow, record_exchange_cost
from .learning.alliance_roles import find_role
from .tx_decoder import compile_source
from .wallet_id import to_address


# 内置合约清单与构造参数统一取自 app/alliance_contracts.py（与 eco 路由同一来源，
# 不存在“改一处漏一处”）：GreenEnergy 创世初始供应 = 0，能量只能按行为逐步发行
from .alliance_contracts import (
    BUILTIN_CONTRACTS,
    DEFAULT_CTOR_ARGS,
    ENERGY_TOKEN_NAME,
    grant_issuers,
    sync_energy_token,
)

# 学习者钱包别名
LEARNER_WALLET = "0xlearner"
ADMIN_WALLET = "0xadmin"


def _deploy_builtin(name: str, standard: str, file: str, deployer: str = ADMIN_WALLET) -> dict | None:
    """编译 + 部署一份内置合约，写入 deployed_contracts 表。

    部署方默认 = 联盟创世账户 0xadmin（与 eco 路由的一键部署口径一致）：
    三个内置合约是联盟公共结算层，不应记在某个学生钱包名下（否则 ERC20 的
    创世初始供应会落到学生地址，链上余额与能量账本对不上）。
    """
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
    if not r.get("address") or int(r.get("status") or 0) != 1:
        # 构造函数 revert 时链上不会返回合约地址，此时必须跳过，
        # 否则会把一条无代码的部署记录写进库，后续所有调用都失败
        print(f"[seed] 部署 {name} 未成功（构造函数 revert 或未返回地址）: {r}")
        return None

    with get_conn() as conn:
        # 落库的 deployer 用**真实链上地址**（别名只用于链上签名 / 文案）：
        # 合约列表与资产页按地址匹配本人钱包，存别名会永远对不上
        deployer_addr = to_address(deployer) or deployer
        conn.execute("DELETE FROM deployed_contracts WHERE address=?", (r["address"],))
        conn.execute(
            "INSERT INTO deployed_contracts(address,name,abi,bytecode,source,deployer,tx_hash,standard,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (r["address"], name, json.dumps(comp["abi"]), comp["bytecode"], source,
             deployer_addr, r["tx_hash"], standard, now()),
        )
    print(f"[seed] 已部署 {name} ({standard}) → {r['address']}")
    # 链上发行权白名单初始化：owner（0xadmin）把 5 个业务节点组织钱包加入 issuers，
    # 否则新版合约下节点 mint / 勋章 mint 会被链上 revert（旧合约自动降级为 legacy）
    grant = grant_issuers(c, r["address"], comp["abi"], name, operator=ADMIN_WALLET)
    if grant.get("enforcement") == "onchain":
        print(f"[seed] {name} 链上发行白名单已授予: "
              f"{','.join(grant.get('granted') or []) or '无'}"
              + (f"（失败 {len(grant.get('failed') or [])} 个）" if grant.get("failed") else ""))
    else:
        print(f"[seed] {name} 为旧版本合约（无 addIssuer），发行权仅由应用层校验")
    r["issuer_grant"] = grant
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


def _grant_treasury(conn, *, wallet: str, cost: int, kind_prefix: str, obj_id: int,
                    note: str = "") -> None:
    """兑换成本的账本双写（与 API 同一入口 record_exchange_cost，ref 口径不分叉）。"""
    record_exchange_cost(conn, wallet=wallet, cost=cost, kind_prefix=kind_prefix,
                         obj_id=obj_id, note=note)


def _issue_energy(wallet: str, role_key: str, role_name: str, action: str, points: int,
                  kind: str = FLOW_ISSUE):
    """向钱包投放绿色能量，并记录到 eco_energy_records + 能量流水。

    链上交易 FROM 与业务口径一致：能量由**发行方节点的组织钱包**签发
    （0xmetro / 0xbus / …），而不是接收者自铸；kind="backfill" 用于
    管理员国库的创世启动资金投放（不属于节点发行量，不计入配额与通胀审计）。
    """
    ge_addr, ge_abi = _find_contract("GreenEnergy")
    if not ge_addr:
        return
    role = find_role(role_key) or {}
    issuer = role.get("wallet") or ADMIN_WALLET
    c = get_chain_client()
    r = c.call_contract(
        ge_addr, "mint",
        [c.resolve_account(wallet), points, action],
        issuer, ge_abi,
    )
    if not r.get("ok"):
        print(f"[seed] 能量发放失败 ({role_name}): {r.get('error')}")
        return
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO eco_energy_records(wallet,role_key,role_name,action,points,tx_hash,created_at,"
            "issuer_wallet,proof_no,proof_validated,points_base) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (wallet, role_key, role_name, action, points, r.get("tx_hash", ""), now(),
             issuer, f"seed-{role_key}-{uuid.uuid4().hex[:6]}",
             1 if kind == FLOW_ISSUE else 0, points),
        )
        ensure_flow(conn, wallet=wallet, kind=kind, amount=points,
                    ref=f"energy:{cur.lastrowid}", note=action, role_key=role_key)


def _add_tree(name: str, required_energy: int, description: str, supply: int = 100):
    """新增树种（管理员操作）并备案 ERC721 项目发行额度（一证一树，额满即售罄）。"""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO eco_tree_species(name,required_energy,image_url,description,created_by,created_at,"
            "supply,issued,status) VALUES(?,?,?,?,?,?,?,0,'active')",
            (name, required_energy, "", description, ADMIN_WALLET, now(), supply),
        )
        return cur.lastrowid


def _exchange_certificate(wallet: str, species_id: int, species_name: str, cost: int):
    """兑换植树证书（ERC721）。失败时打印原因，便于发现能量不足等矛盾。"""
    ge_addr, ge_abi = _find_contract("GreenEnergy")
    pc_addr, pc_abi = _find_contract("PlantCertificate")
    if not ge_addr or not pc_addr:
        print("[seed] 证书兑换跳过：GreenEnergy/PlantCertificate 合约未就绪")
        return
    c = get_chain_client()
    admin_addr = c.resolve_account(ADMIN_WALLET)

    # 1. 扣能量（wallet → admin）
    r_t = c.call_contract(ge_addr, "transfer", [admin_addr, cost], wallet, ge_abi)
    if not r_t.get("ok"):
        print(f"[seed] 证书兑换失败（能量扣除）: {r_t.get('error')}")
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
        cur = conn.execute(
            "INSERT INTO eco_certificates(token_id,species_id,species_name,owner,exchanged_by,"
            "cost_energy,contract_address,tx_hash,cert_no,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (str(token_id), species_id, species_name, wallet, wallet, cost,
             pc_addr, r_m.get("tx_hash", ""), cert_no, now()),
        )
        _grant_treasury(conn, wallet=wallet, cost=cost, kind_prefix="cert",
                        obj_id=cur.lastrowid, note=f"植树证书 · {species_name}")
        conn.execute("UPDATE eco_tree_species SET issued = issued + 1 WHERE id=?", (species_id,))
    print(f"[seed] 植树证书铸造成功: {cert_no}（{species_name}，消耗 {cost} 能量）")


def _exchange_badge(wallet: str, badge_type: str, token_id: int, name: str, cost: int,
                    issuer_role: str = "", quantity: int = 1):
    """兑换生态勋章 / 骑行券（ERC1155）。失败时打印原因。

    与 API 同口径：链上 mint 的 FROM 是**该类型的发行方节点组织钱包**（骑行券 = 0xbike），
    旧内置类型无发行方时回退国库代签；数量 = ERC1155 份数。
    """
    ge_addr, ge_abi = _find_contract("GreenEnergy")
    eb_addr, eb_abi = _find_contract("EcoBadge")
    if not ge_addr or not eb_addr:
        print("[seed] 勋章兑换跳过：GreenEnergy/EcoBadge 合约未就绪")
        return
    c = get_chain_client()
    admin_addr = c.resolve_account(ADMIN_WALLET)
    issuer = ((find_role(issuer_role) or {}).get("wallet") if issuer_role else "") or ADMIN_WALLET

    # 1. 扣能量（余额不足会导致失败，播种前必须先足额发放）
    r_t = c.call_contract(ge_addr, "transfer", [admin_addr, cost], wallet, ge_abi)
    if not r_t.get("ok"):
        print(f"[seed] 勋章兑换失败（能量扣除）: {r_t.get('error')}")
        return

    # 2. 铸造勋章（与 API 同口径：由发行方账户铸造，居民不能自铸）
    r_m = c.call_contract(
        eb_addr, "mint",
        [c.resolve_account(wallet), token_id, int(quantity), ""],
        issuer, eb_abi,
    )
    if not r_m.get("ok"):
        return

    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO eco_badges(token_id,badge_type,name,owner,exchanged_by,cost_energy,issued_by,"
            "issuer_role,contract_address,tx_hash,created_at,quantity) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (token_id, badge_type, name, wallet, wallet, cost,
             issuer, issuer_role or "", eb_addr, r_m.get("tx_hash", ""), now(), int(quantity)),
        )
        _grant_treasury(conn, wallet=wallet, cost=cost, kind_prefix="badge",
                        obj_id=cur.lastrowid, note=f"{name} ×{int(quantity)}")


def seed_student_wallets() -> None:
    """为 user_info 中已有学生逐一发放专属钱包别名 stu:{user_id}（任务 #19，幂等）。

    保留 / 调整说明：
      - 仅在密钥库层面 provision（随机私钥加密落盘），不写 user_info、
        不动链上数据；user_info.wallet 的回填由登录自动写入与
        scripts/migrate_wallets.py 负责，职责单一；
      - 不改变现有演示数据对 0xlearner 的注入：种子能量 / 证书 / 勋章仍
        发给 0xlearner（教师演示流兼容）；新学生的行为数据走各自钱包；
      - 与链模式无关（不触碰链节点），放在 seed_init_data 开头执行，
        避免被"已有合约 / 已有业务数据"的提前 return 跳过；
      - 幂等：已发放的学生钱包直接跳过，可重复执行。
    """
    try:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT user_id FROM user_info "
                "WHERE role_id=4 AND TRIM(COALESCE(user_id,''))<>''"
            ).fetchall()
    except Exception as e:
        print(f"[seed] 学生钱包播种跳过（user_info 不可用）: {e}")
        return
    if not rows:
        return
    created = 0
    for r in rows:
        uid = (r["user_id"] or "").strip()
        if not uid:
            continue
        try:
            if ks.get_student_wallet(uid):
                continue  # 已发放，幂等跳过（轻量检查，不解密私钥）
            ks.provision_student_wallet(uid)
            created += 1
        except Exception as e:
            print(f"[seed] 学生钱包发放失败（{uid}）: {e}")
    print(f"[seed] 学生钱包播种: 共 {len(rows)} 名学生，本次新建 {created} 个专属钱包")


def _ensure_energy_token(force: bool = False) -> None:
    """把 tokens（能量钱包余额展示 + 市场结算币种）对齐到当前生效的 GreenEnergy。

    为什么必须放在「链非空即跳过播种」之前（P0 自愈）：GreenEnergy 会被教程第 9 步 /
    联盟页一键部署反复重新部署，而 tokens 过去只在首次播种时写一次，老环境重启后
    登记会一直停在作废地址上，表现为「联盟页有能量、能量钱包显示 0、市场付款说余额不足」。
    只在确实不一致时改写，避免每次启动都刷 created_at。
    """
    ge_addr, _ = _find_contract(ENERGY_TOKEN_NAME)
    if not ge_addr:
        return
    with get_conn() as conn:
        row = conn.execute("SELECT address FROM tokens WHERE name=?",
                           (ENERGY_TOKEN_NAME,)).fetchone()
    if not force and row and str(row["address"] or "").lower() == ge_addr.lower():
        return
    if sync_energy_token(ge_addr, owner=to_address(ADMIN_WALLET) or ADMIN_WALLET):
        print(f"[seed] 绿色能量钱包登记已对齐: GreenEnergy (GE) -> {ge_addr}")


def seed_init_data() -> None:
    """启动时自动播种实训基础数据。仅在链为空（无合约）时执行。"""
    # 学生钱包（一人一钱包）播种：仅本地密钥库操作，与链模式无关，幂等；
    # 不影响下方 0xlearner 演示数据注入逻辑
    seed_student_wallets()

    c = get_chain_client()
    # 仅对进程内链（evm / 沙盒）自动播种，避免误操作真实 FISCO 节点
    if not isinstance(c, (RealEvmChainClient, MockChainClient)):
        print("[seed] 非 EVM 虚拟机 / 本地沙盒模式，跳过自动播种")
        return

    # 检查是否已有可用合约（避免重复播种）
    ge_addr, _ = _find_contract("GreenEnergy")
    if ge_addr:
        # 已有链：不重复播种，但能量代币登记必须自愈一次（教程重跑后地址会变）
        _ensure_energy_token()
        print("[seed] 检测到已部署合约，跳过自动播种")
        return

    print("[seed] 开始自动播种实训基础数据 ...")

    # 1. 部署 3 份系统合约（链重启后必须重新部署，保证前端 has_code 校验通过）
    # 部署方统一为联盟创世账户（与 /eco/contracts/deploy 同一口径）
    for contract in BUILTIN_CONTRACTS:
        _deploy_builtin(contract["name"], contract["standard"], contract["file"],
                        deployer=ADMIN_WALLET)

    # 1.1 将 GreenEnergy 登记为默认「绿色能量钱包」代币（ERC20 钱包余额列表可见）
    #     登记实现与教程第 9 步 / 联盟页一键部署共用 sync_energy_token：
    #     “哪一份 GE 是当前流通代币”只允许有一个写法，否则重启后重跑教程就又会错位。
    _ensure_energy_token(force=True)

    # 1.2 内置「系统内置合约」IDE 工程（默认第一个工程，学生新增工程排在其后）
    _seed_builtin_project()

    # 2. 业务种子数据仅在数据库为空时播种一次（后端重启链重置但数据库持久，避免重复）
    with get_conn() as conn:
        tree_count = conn.execute("SELECT COUNT(*) FROM eco_tree_species").fetchone()[0]
    if tree_count:
        print("[seed] 检测到已有业务播种数据，跳过重复播种")
        return

    # 2.1 新增 2 个树种（管理员操作，同时备案 ERC721 项目发行额度：一证一树、额满售罄）
    tree1 = _add_tree("银杏树", 1500, "国家一级保护植物，被誉为“活化石”，固碳能力强", supply=50)
    tree2 = _add_tree("樟子松", 1000, "耐寒耐旱，适合北方沙地绿化造林，防风固沙先锋树种", supply=100)

    # 2.2 向学习者钱包发放绿色能量（覆盖 5 个联盟角色的能量发放规则，共 195 点）
    _issue_energy(LEARNER_WALLET, "metro", "地铁集团", "地铁通勤", 50)
    _issue_energy(LEARNER_WALLET, "bus", "公交集团", "公交出行", 20)
    _issue_energy(LEARNER_WALLET, "bike", "共享单车", "共享单车骑行", 15)
    _issue_energy(LEARNER_WALLET, "takeout", "外卖平台", "绿色外卖(无需餐具)", 10)
    _issue_energy(LEARNER_WALLET, "recycling", "回收公司", "可回收物回收", 100)

    # 2.2.1 余额一致性修复：先足额投放再兑换。旧逻辑仅发 195 点却要兑换 1500 能量证书
    # + 10 能量勋章，链上转账必然失败；此处由能量国库（管理员 0xadmin）投放启动资金
    # 1405 点。该笔不属节点发行量（kind=backfill），不计入节点授信配额与通胀审计的
    # “联盟发行”科目，而是作为国库投放单独可识——真实商业里它就是储备能量释放。
    _issue_energy(LEARNER_WALLET, "admin", "能量国库", "国库启动资金投放", 1405,
                  kind=FLOW_BACKFILL)
    # 累计 1600 点 ≥ 证书 1500 + 勋章 10 = 1510，兑换后剩余 90 点

    # 2.3 兑换 1 份植树证书 + 1 个生态勋章（内置资产，绿色资产市场初始非空）
    # 先兑证书（大额 1500）再兑勋章（10），余额已足额（1600），链上转账真实执行
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