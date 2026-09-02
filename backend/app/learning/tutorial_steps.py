"""搭链教程数据（TUTORIAL 10 步 + ROLE_ENERGY_RULES）。

TUTORIAL 数据与注释自 app/routers/chain.py 原样迁入（逐字段不变，含
role_focus / biz_note）。chain.py 改为 `from ..learning.tutorial_steps import
TUTORIAL, ROLE_ENERGY_RULES`，achievements.py 同步切换，对外行为不变。

ROLE_ENERGY_RULES 从 alliance_roles.ROLES 派生（单一代码来源，替代原先与
eco.py 阈值靠人工同步的双份维护），派生规则保证最终值与原 chain.py 手写版本
逐字段完全一致（快照对比脚本验证）：
  role   = f"{icon} {name}({wallet 去掉 0x 前缀})"
  scene  = 教学演示文案（与 energy_rule.action 非同一文案体系，按钱包映射维护于此）
  amount = energy_rule 存在 → f"+{points} 能量"，否则 "0 / 次"
  wallet = ROLES.wallet
"""
from __future__ import annotations

from typing import Any, Dict, List

from .alliance_roles import ROLES


# ---------------------------------------------------------------------------
# 绿色低碳联盟链搭建 10 步教程（明确覆盖 6 大联盟节点：管理员/地铁/公交/单车/外卖/回收）
# 阶段 A · 链底层（Step 1-4）：启动 4 节点 → 检查进程/日志/控制台
# 阶段 B · 6 联盟节点组织配置（Step 5-8）：4 逻辑节点 ↔ 6 业务组织的映射、角色职责、钱包注册、权限
# 阶段 C · 核心代币合约（Step 9-10）：部署 GreenEnergy → 调用验证
# 每步包含：真实命令、原理讲解、预期输出、执行动作（连接真实 EVM）
# ---------------------------------------------------------------------------
TUTORIAL: List[Dict[str, Any]] = [
    {
        "step": 1,
        "title": "下载官方脚本并生成 4 节点联盟链（证书体系建立）",
        "desc": "严格按 FISCO-BCOS 官方建链流程：下载 build_chain.sh → 赋予执行权限 → 一键生成 4 节点 PBFT 联盟链。\n"
                "build_chain.sh 会同时生成完整的链上证书体系：CA 证书、机构证书（Agency）、节点证书（Node）、SDK 证书，\n"
                "证书 = 联盟准入凭证：只有持有联盟 CA 签发的有效证书，机构/节点/控制台才能接入本链。\n"
                "本项目 6 大联盟成员映射：\n"
                "node0=🛡️管理员+🚇地铁 · node1=🚌公交+🚲单车 · node2=📦外卖+♻️回收 · node3=🔥热备共识。",
        "principle": "FISCO-BCOS 采用 PBFT 共识，4 节点可容忍 1 个拜占庭节点（3f+1=4）。\n"
                     "证书分三级：根 CA → 机构证书 → 节点/SDK 证书，构成联盟准入的信任链；\n"
                     "每个逻辑节点可代表多个业务组织（共享共识权重），业务上通过「钱包地址 + 合约白名单」做权限隔离。",
        "commands": [
            "curl -#LO https://github.com/FISCO-BCOS/FISCO-BCOS/releases/download/v2.9.1/build_chain.sh && chmod +x build_chain.sh",
            "bash build_chain.sh -l 127.0.0.1:4 -p 30300,20200,8545 -o nodes",
            "cat nodes/127.0.0.1/node0/config.ini | grep -E '^\[|node_listen|channel_listen|peer_listen' | head -20",
            "cat nodes/127.0.0.1/node0/conf/group.1.genesis | head -30",
            "bash nodes/127.0.0.1/start_all.sh",
        ],
        "expected": "build_chain.sh 输出 CA/机构/节点/SDK 四类证书生成信息；config.ini 显示网络配置（listen_ip、listen_port）；genesis 显示共识配置（consensus_type=pbft、sealer_list 4 个节点）；start_all.sh 输出 4 个 start successful。",
        "tip": "故障排查：① 若 start 失败检查端口占用 netstat -tlnp | grep -E '30300|20200|8545'；② 查看节点日志 tail -f nodes/127.0.0.1/node0/log/log_*.log | grep ERROR",
        "role_focus": "链管理员",
        "biz_note": "生产环境节点采购与部署对应商业项目的基建立项：先确定联盟成员与节点拓扑，再申请预算搭建底层网络。",
    },
    {
        "step": 2,
        "title": "检查节点进程与证书目录（联盟准入凭证核验）",
        "desc": "① 确认 4 个 fisco-bcos 进程在运行；\n"
                "② 查看 nodes 目录结构，核验链上证书体系的四大组成部分（CA / Agency / Node / SDK）；\n"
                "③ 用 openssl 验证证书链完整性——节点证书必须由联盟 CA 签发；\n"
                "④ 用 nc 测试节点端口连通性，确保网络层可达。\n"
                "对照映射表确认每个节点承载的业务组织：\n"
                "  node0 → 管理员 + 地铁集团 · node1 → 公交集团 + 共享单车\n"
                "  node2 → 外卖平台 + 回收公司 · node3 → 热备共识。",
        "principle": "联盟链每个节点都是独立进程，进程存活 ≠ 联盟可用；\n"
                     "还需核验「节点证书是否由联盟 CA 签发」以及各组织钱包位置。\n"
                     "证书链验证：openssl verify -CAfile ca.crt node.crt 验证签名链完整性。\n"
                     "生产环境用 systemd/supervisor 守护进程。",
        "commands": [
            "ps -ef | grep fisco-bcos | grep -v grep | wc -l",
            "ls nodes/127.0.0.1/",
            "openssl x509 -in nodes/127.0.0.1/ca/ca.crt -noout -subject -issuer -dates",
            "openssl verify -CAfile nodes/127.0.0.1/ca/ca.crt nodes/127.0.0.1/node0/conf/node.crt",
            "nc -zv 127.0.0.1 30300 20200 8545 2>&1",
        ],
        "expected": "① 输出 4（4 个 fisco-bcos 进程）；② 目录含 agency/ ca/ node0~3/ sdk/；\n"
                    "③ CA 证书 subject=FISCO-BCOS-CA，issuer 自签名，有效期正常；\n"
                    "④ node.crt: OK（证书链验证通过）；⑤ 3 个端口全部 Connection succeeded。",
        "tip": "故障排查：① 进程数 < 4 → tail 对应 node 日志查 ERROR；② 证书验证失败 → 检查 ca.crt 是否被覆盖；\n"
               "③ 端口不通 → 检查防火墙 iptables -L -n；④ 6 组织清单：管理员🛡️ 地铁🚇 公交🚌 单车🚲 外卖📦 回收♻️",
        "role_focus": "链管理员",
        "biz_note": "对应商业项目上线前的准入核验：联盟成员资质与证书年审，确保只有持证机构可接入生产网络。",
    },
    {
        "step": 3,
        "title": "检查日志出块（PBFT 共识确认 + 日志分析）",
        "desc": "查看 node0 日志，确认 PBFT 共识正常出块。\n"
                "用 grep 精确提取关键字段：出块标记、共识报告、错误信息。\n"
                "后续 6 角色发起的「能量发放 mint」「资产兑换 transferFrom」都会在这些区块里打包。",
        "principle": "PBFT 通过 `+++Generating seal` 标记某个 sealer 开始打包；`Report` 表示三阶段（Pre-prepare/Prepare/Commit）完成、区块落盘。\n"
                     "4 个 sealer 轮流出块，6 业务组织只要在任一共识节点上「有签名权」就可参与。\n"
                     "日志关键字段：Generating seal（出块）、Report（共识完成）、ERROR（异常）、peer 相关（节点连接）。",
        "commands": [
            "tail -n 50 nodes/127.0.0.1/node0/log/log_* | grep -E '\\+\\+\\+Generating|Report'",
            "tail -n 200 nodes/127.0.0.1/node0/log/log_* | grep -iE 'ERROR|WARN' | tail -5",
            "tail -n 100 nodes/127.0.0.1/node0/log/log_* | grep -oE 'blk_num=[0-9]+' | tail -3",
            "tail -n 100 nodes/127.0.0.1/node0/log/log_* | grep -oE 'hash=[a-f0-9]{64}' | tail -3",
        ],
        "expected": "① 持续输出 `+++Generating seal` 与 `Report`，说明共识正常；\n"
                    "② 无 ERROR 或仅有少量 WARN（如连接重试）属正常；\n"
                    "③ 显示最近区块号 blk_num=递增序列；④ 显示最近区块哈希。",
        "tip": "故障排查：① 无 Generating seal → 检查 sealer_list 是否配置正确；② ERROR 含 'view not match' → 节点视图不一致，检查 genesis 文件；\n"
               "③ ERROR 含 'timeout' → 网络延迟或节点掉线，检查 nc 端口连通性；④ 日志路径：nodes/127.0.0.1/node{0,1,2,3}/log/log_YYYYMMDDHHMM.log",
        "role_focus": "链管理员",
        "biz_note": "对应联盟链运营方的日常巡检与 SLA 监控：出块停滞会触发商业服务降级，是运维考核的硬指标。",
    },
    {
        "step": 4,
        "title": "接入控制台（SDK 证书配置 + 链状态查询）",
        "desc": "真实控制台接入流程：\n"
                "  ① 把 build_chain 生成的 SDK 证书拷入 console 配置目录（控制台持证才能连链）\n"
                "  ② 校验 SDK 证书有效期（openssl 验证 sdk.crt 未过期）\n"
                "  ③ 启动控制台 start.sh，进入交互式命令行\n"
                "  ④ 依次查询区块高度 / 共识节点 / 群组成员：\n"
                "     getBlockNumber 确认链存活 · getPeers 查看对等节点 · getSealerList / getGroupPeers 确认 4 共识节点同组",
        "principle": "控制台通过 Channel 协议（双向长连接 + SDK 证书）连接节点，比裸 JSON-RPC 更安全，\n"
                     "是联盟链运营方日常运维的入口。证书不匹配时控制台会拒绝连接——这就是联盟准入在工具层的体现。\n"
                     "SDK 证书三件套：sdk.crt（证书）+ sdk.key（私钥）+ ca.crt（CA 根证书），缺一不可。",
        "commands": [
            "cp -r nodes/127.0.0.1/sdk/* ~/fisco/console/conf/",
            "openssl x509 -in nodes/127.0.0.1/sdk/sdk.crt -noout -subject -dates",
            "openssl verify -CAfile nodes/127.0.0.1/sdk/ca.crt nodes/127.0.0.1/sdk/sdk.crt",
            "cd ~/fisco/console && bash start.sh",
            "[console] getBlockNumber",
            "[console] getPeers",
            "[console] getSealerList",
            "[console] getGroupPeers",
        ],
        "expected": "① SDK 证书拷贝成功；② sdk.crt subject=FISCO-BCOS-SDK，dates 在有效期内；\n"
                    "③ sdk.crt: OK（证书链验证通过）；④ 控制台启动 Banner（版本 2.9.1）；\n"
                    "⑤ 返回当前块高（如 5）；⑥ 对等节点 3 个；⑦ 共识节点 4 个；⑧ groupId=1 内 4 节点。",
        "tip": "故障排查：① 控制台连不上 → 检查 sdk.crt/sdk.key/ca.crt 三件套是否齐全；\n"
               "② 证书过期 → 重新用 build_chain.sh 生成或手动 openssl 续签；\n"
               "③ 对等节点数 < 3 → 检查其他节点进程是否存活；④ 控制台命令等价 JSON-RPC：getBlockByNumber / getConsensusStatus",
        "role_focus": "链管理员",
        "biz_note": "对应商业项目的运维工作台开通：控制台是运营方日常审批与链上排障的入口，SDK 证书按机构最小权限分发。",
    },
    # ======================== Step 5-8 · 6 大联盟组织接入 ========================
    {
        "step": 5,
        "title": "Step 5 · 联盟组织证书与节点归属核查",
        "desc": "联盟组织接入前，先在节点侧核验接入凭据：\n"
                "  ① 查看 node0 配置目录，核对节点证书与群组配置（group.1.genesis 创世块 / 节点私钥 / 证书）\n"
                "  ② 查看 config.ini 确认网络配置（listen_ip、listen_port、channel_listen_port）\n"
                "  ③ 用 openssl 检查节点证书有效期（确保未过期）\n"
                "  ④ getNodeVersion 确认链版本一致（联盟内各机构需运行版本一致的节点软件）",
        "principle": "FISCO-BCOS 每个节点的 conf 目录包含：节点证书 node.crt / 私钥 node.key、\n"
                     "创世块 group.1.genesis（记录联盟初始成员与共识配置）、config.ini（网络/日志）。\n"
                     "联盟成员间「版本一致 + 证书同源 + 证书有效」是共识的前提。\n"
                     "证书有效期检查：openssl x509 -dates 查看 notBefore/notAfter。",
        "commands": [
            "ls -la nodes/127.0.0.1/node0/conf/",
            "cat nodes/127.0.0.1/node0/conf/config.ini | grep -E 'listen|peer|channel' | head -10",
            "openssl x509 -in nodes/127.0.0.1/node0/conf/node.crt -noout -subject -dates",
            "openssl verify -CAfile nodes/127.0.0.1/ca/ca.crt nodes/127.0.0.1/node0/conf/node.crt",
            "[console] getNodeVersion",
        ],
        "expected": "① conf 目录含 node.crt / node.key / group.1.genesis / config.ini / genesis 等文件；\n"
                    "② config.ini 显示 listen_ip=0.0.0.0、node_listen=8545、channel_listen=20200；\n"
                    "③ 节点证书 subject=FISCO-BCOS-Node，dates 在有效期内；\n"
                    "④ node.crt: OK（证书链验证通过）；⑤ 返回 Version=2.9.1。",
        "tip": "故障排查：① 证书过期 → 用 openssl 重新签发或重新运行 build_chain.sh；\n"
               "② 版本不一致 → 所有节点必须升级到相同版本；③ 联盟接入三件套：证书（身份）→ 创世块（共识资格）→ 端口（网络连通）",
        "role_focus": "各组织管理员",
        "biz_note": "对应商业项目的联盟成员准入尽调：核实各成员机构证书、节点归属与版本一致性，是签约进驻联盟链的前置条件。",
    },
    {
        "step": 6,
        "title": "Step 6 · 6 组织治理规则公示（能量发放规则表）",
        "desc": "6 大联盟成员在链上开展业务前，先在联盟内公示治理规则（能量发放标准），\n"
                "并以组织钱包真实余额验证各成员已具备链上身份。规则与生态合约（/eco）的阈值校验完全一致：\n"
                "钱包注册流程说明：每个组织钱包地址由节点预置在 genesis 账户列表中，首次查询即激活上链。",
        "principle": "能量值按「减碳贡献」梯度设计：回收 1kg 旧物 > 地铁通勤 ≥10km > 公交 ≥5min > 骑行 ≥2km > 1 单无需餐具外卖。\n"
                     "管理员作为治理角色不直接发能量，避免利益冲突；业务角色发能量必须在白名单内（mintRole）且凭证达标。\n"
                     "钱包激活机制：FISCO-BCOS 账户首次出现在交易或查询中时自动创建账户状态，无需显式注册。",
        "commands": [
            "cat <<'RULES'\n角色         业务场景                     单次能量   钱包\n============================================================\n管理员       部署合约/树种管理               0        0xadmin\n地铁集团     乘坐地铁 1 次（里程 ≥ 10 km）   +50      0xmetro\n公交集团     乘坐公交 1 次（时长 ≥ 5 分钟）  +20      0xbus\n共享单车     骑行 ≥ 2 km                    +15      0xbike\n外卖平台     绿色外卖(无需餐具)             +10      0xtakeout\n回收公司     纸箱/塑料瓶回收 ≥ 1kg          +100     0xrecycle\nRULES",
            "[console] getAccountBalance 0xmetro",
            "[console] getAccountBalance 0xbus",
            "[console] getAccountBalance 0xbike",
            "[console] getAccountBalance 0xtakeout",
            "[console] getAccountBalance 0xrecycle",
        ],
        "expected": "能复述 6 角色的发放阈值（回收100 > 地铁50 > 公交20 > 单车15 > 外卖10 > 管理员0）；\n"
                    "5 个业务角色钱包均返回余额 0（账户已激活），管理员钱包 0xadmin 余额为初始发行量。",
        "tip": "故障排查：① 钱包余额查询失败 → 检查钱包地址格式（0x 前缀 + 40 位十六进制）；\n"
               "② 前端绿色低碳联盟链（/eco）与 ERC20 钱包的凭证校验按此规则表逐项执行",
        "role_focus": "各组织管理员 · 联盟治理委员会",
        "biz_note": "对应商业联盟的治理章程公示：能量发放阈值写进联盟公约，是后续业务结算与争议仲裁的链上依据。",
    },
    {
        "step": 7,
        "title": "Step 7 · 注册 6 组织钱包（链上身份登记 + 钱包激活验证）",
        "desc": "为 6 大业务组织在链上登记独立身份钱包：\n"
                "  0xadmin（管理员·部署/治理） 0xmetro（地铁） 0xbus（公交）\n"
                "  0xbike（单车） 0xtakeout（外卖） 0xrecycle（回收）\n"
                "逐个查询链上余额，确认全部钱包已生效（余额 ≥ 0 即账户已上链）。\n"
                "钱包注册流程：FISCO-BCOS 账户首次查询时自动创建，无需显式注册交易。",
        "principle": "ERC20 两种发能量模式：① mint（合约白名单角色造币，适合业务角色批量发放）\n"
                     "② transfer（有余额的钱包转账）。本实训用 mint 模式：GreenEnergy 合约内嵌 mintRole 白名单，\n"
                     "只有登记过的联盟角色才有铸造权，防止任意账户凭空造币。\n"
                     "钱包激活验证：getAccountBalance 返回 0 表示账户已创建但未持有代币。",
        "commands": [
            "[console] getAccountBalance 0xadmin",
            "[console] getAccountBalance 0xbike",
            "[console] getAccountBalance 0xtakeout",
            "[console] getAccountBalance 0xrecycle",
            "[console] getAccountBalance 0xmetro",
            "[console] getAccountBalance 0xbus",
        ],
        "expected": "6 个组织钱包均返回余额（0 或初始值），确认全部钱包已激活上链。\n"
                    "管理员 0xadmin 余额为初始发行量，5 个业务角色钱包余额为 0（待发放）。",
        "tip": "故障排查：① 钱包地址格式错误 → 检查 0x 前缀 + 40 位十六进制；\n"
               "② 前端 /eco 的角色切换卡片严格对应这 6 个角色 + 钱包，角色决定你能调用哪些接口",
        "role_focus": "各组织管理员",
        "biz_note": "对应商业项目的账户体系开户：为 6 家成员机构开设链上钱包并登记白名单，相当于财务系统的开户与授权。",
    },
    {
        "step": 8,
        "title": "Step 8 · 联盟上线健康检查（节点 + 证书 + 三合约探针）",
        "desc": "上线前综合健康检查：\n"
                "  ① check_node_status.sh 确认 4 共识节点在线\n"
                "  ② 批量检查 4 个节点证书有效期（openssl 逐一验证 node.crt）\n"
                "  ③ 用 nc 批量测试 4 节点端口连通性（确保节点间网络互通）\n"
                "  ④ 调用核心合约视图函数验证链上可调用（Step 9 会正式部署 GreenEnergy）：\n"
                "     GreenEnergy / PlantCertificate 调用 name()，\n"
                "     EcoBadge（ERC1155 多资产合约）调用 tokenURI(1) 探针，\n"
                "     确认「能量代币 + 植树证书 + 环保勋章」三件套就绪",
        "principle": "联盟链「上线」≠ 节点启动，需「共识节点在线 + 证书有效 + 网络互通 + 核心合约可调用 + 角色白名单」同时就绪。\n"
                     "name() / tokenURI() 是 view 函数，本地执行验证合约字节码已在链上（has_code 检查），不消耗 Gas。\n"
                     "ERC1155 标准不强制命名视图，对多资产合约用 tokenURI(id) 探针是通用做法。\n"
                     "健康检查脚本 check_node_status.sh 会逐一检测进程存活、端口监听、日志出块状态。",
        "commands": [
            "bash nodes/127.0.0.1/check_node_status.sh all",
            "for i in 0 1 2 3; do echo \"=== node$i ===\"; openssl x509 -in nodes/127.0.0.1/node$i/conf/node.crt -noout -enddate; done",
            "for i in 0 1 2 3; do echo \"=== node$i ===\"; nc -zv 127.0.0.1 $((30300+i)) $((20200+i)) $((8545+i)) 2>&1; done",
            "[console] call GreenEnergy <address> name",
            "[console] call PlantCertificate <address> name",
            "[console] call EcoBadge <address> tokenURI 1",
        ],
        "expected": "① 4/4 节点 SUCCESS（进程存活 + 端口监听 + 日志出块）；\n"
                    "② 4 个节点证书 notAfter 均在有效期内（如 notAfter=Dec 31 23:59:59 2035 GMT）；\n"
                    "③ 12 个端口全部 Connection succeeded；\n"
                    "④ 探针通过：GreenEnergy name()='Green Energy'、PlantCertificate name()='Plant Certificate'、EcoBadge tokenURI(1) 返回 URI。",
        "tip": "故障排查：① 某节点 check 失败 → ps -ef | grep node$i 查进程 + tail 日志查 ERROR；\n"
               "② 证书过期 → openssl 重新签发并替换 conf/node.crt；③ 端口不通 → 检查防火墙与 config.ini 监听配置；\n"
               "④ 合约探针失败 → 确认合约已部署且地址正确；⑤ 健康检查通过 = 联盟运营模块（/eco）可放开使用",
        "role_focus": "各组织管理员 · 链管理员联检",
        "biz_note": "对应商业项目的上线验收（UAT）：节点、证书、网络、合约四类探针全部通过后才正式对盟外提供服务。",
    },
    # Step 9/10 · 核心代币部署 + 商业化链路验证
    {
        "step": 9,
        "title": "Step 9 · 部署 GreenEnergy 绿色能量代币（管理员授权 + Gas 消耗说明）",
        "desc": "由联盟管理员（0xadmin）部署 GreenEnergy ERC20 合约，初始发行 1,000,000 能量。\n"
                "部署成功后：管理员持有初始能量，地铁/公交/单车/外卖/回收 5 个业务角色进入 mintRole 白名单，\n"
                "可向低碳行为用户发放能量。\n"
                "Gas 消耗说明：合约部署交易消耗 Gas，FISCO-BCOS 联盟链中 Gas 由共识节点内部结算，\n"
                "用户无需额外支付；部署一笔 ERC20 合约约消耗 1.5~2.5M Gas。",
        "principle": "GreenEnergy 继承 ERC20，构造函数接收 initialSupply 初始发行量。\n"
                     "部署交易 to 字段为空，data = 字节码 + 构造函数参数 ABI 编码；\n"
                     "EVM 执行构造函数初始化状态，合约地址 = keccak256(rlp([sender, nonce])) 后 20 字节。\n"
                     "商业化前提：只有管理员部署（治理闭环），5 业务角色只授「铸造权」不授「所有权」。\n"
                     "交易确认数：PBFT 共识下交易在 1 个区块内即确认（约 3 秒），无需像公链等待多区块确认。",
        "commands": [
            "[console] deploy GreenEnergy 1000000",
            "[console] getTransactionReceipt <tx_hash>",
        ],
        "expected": "① 返回 0x... 合约地址 + 交易哈希 + 区块号 + gasUsed（约 1.5~2.5M）；\n"
                    "② Receipt 显示 status=0x1（成功）、blockNumber、gasUsed、contractAddress；\n"
                    "合约登记进「智能合约 IDE」工程，监听器可查。",
        "tip": "故障排查：① 部署失败 status=0x0 → 检查构造函数参数类型是否匹配；\n"
               "② Gas 超限 → 检查合约字节码大小，FISCO-BCOS 默认 blockGasLimit=300M；\n"
               "③ GreenEnergy decimals=0（整数），1 能量 = 1 次低碳行为积分；地址已写入 deployed_contracts 表",
        "role_focus": "合约开发方 + 链管理员授权",
        "biz_note": "对应商业项目的核心资产上线：由治理方部署代币合约并授权发放权限，是整个绿色能量商业模式的发起点。",
    },
    {
        "step": 10,
        "title": "Step 10 · 商业化全链路验证（5 业务角色发放 → 居民持有 + 交易确认）",
        "desc": "验证绿色能量商业化发放链路（与 /eco 生态页同一套合约与白名单）：\n"
                "  ① 查代币名与 0xlearner 初始余额\n"
                "  ② 5 个业务角色各按规则发放一次：地铁+50 / 公交+20 / 单车+15 / 外卖+10 / 回收+100，共 +195\n"
                "  ③ 复核 0xlearner 余额，确认能量入账\n"
                "  ④ 抽查最近一笔 mint 交易的 Receipt，确认 status=0x1 + 交易确认数\n"
                "Gas 消耗说明：每笔 mint 交易约消耗 50~80K Gas，view 函数（name/balanceOf）不消耗 Gas。",
        "principle": "view 函数（name/balanceOf）通过 eth_call 本地执行，不消耗 Gas 不上链；\n"
                     "状态变更函数（mint）通过 sendTransaction 广播、消耗 Gas、产生 Transfer 事件日志。\n"
                     "每次 mint 由对应角色钱包签名（0xmetro/0xbus/...），非白名单角色调用会被合约拒绝。\n"
                     "交易确认数检查：PBFT 共识下交易在 1 个区块内确认，getTransactionReceipt 的 status=0x1 即最终确认。",
        "commands": [
            "[console] call GreenEnergy <address> name",
            "[console] call GreenEnergy <address> balanceOf 0xlearner",
            "[console] call GreenEnergy <address> mint 0xmetro 0xlearner 50 地铁通勤≥10km",
            "[console] call GreenEnergy <address> mint 0xbus 0xlearner 20 公交出行≥5min",
            "[console] call GreenEnergy <address> mint 0xbike 0xlearner 15 骑行≥2km",
            "[console] call GreenEnergy <address> mint 0xtakeout 0xlearner 10 绿色外卖",
            "[console] call GreenEnergy <address> mint 0xrecycle 0xlearner 100 回收≥1kg",
            "[console] getTransactionReceipt <last_mint_tx_hash>",
            "[console] call GreenEnergy <address> balanceOf 0xlearner",
        ],
        "expected": "5 笔 mint 全部上链（各角色签名），每笔 gasUsed 约 50~80K；\n"
                    "Receipt 抽查 status=0x1（交易成功确认）；\n"
                    "0xlearner 余额从 0 → 195（+50+20+15+10+100）；\n"
                    "能量 → 兑换 NFT → 挂单 → 购买形成完整商业闭环。",
        "tip": "故障排查：① mint 失败 status=0x0 → 检查调用方是否在 mintRole 白名单；\n"
               "② 余额未增加 → 检查 to 地址是否正确（0xlearner）；\n"
               "③ 至此 10 步完成 → 进入绿色低碳联盟链（/eco）与 ERC20 钱包（/wallet）体验完整商业运营",
        "role_focus": "合约开发方 + 审计方",
        "biz_note": "对应商业项目的运营验收与对账：5 类业务角色发放能量入账形成完整商业闭环，审计方抽查交易回执留档。",
    },
]


# 6 角色能量发放规则的教学演示文案（scene）。
# 注意：该文案与 alliance_roles.ROLES[].energy_rule.action 不是同一套文本
# （如「乘坐地铁 1 次（里程 ≥ 10 km）」vs「地铁通勤」），故按钱包映射维护于此；
# 发放值（amount）与钱包（wallet）则从 ROLES.energy_rule / ROLES.wallet 派生，
# 保证与生态模块（/eco）的阈值永远同源一致。
_ROLE_SCENE: Dict[str, str] = {
    "0xadmin":   "系统管理方，部署合约 / 管理树种 / 不发放能量",
    "0xmetro":   "乘坐地铁 1 次（里程 ≥ 10 km）",
    "0xbus":     "乘坐公交 1 次（时长 ≥ 5 分钟）",
    "0xbike":    "骑行 ≥ 2 km",
    "0xtakeout": "选择「无需餐具」绿色外卖 1 单",
    "0xrecycle": "旧纸箱 / 塑料瓶回收 ≥ 1kg",
}


def _derive_role_energy_rules() -> List[Dict[str, str]]:
    """从 alliance_roles.ROLES 派生 6 角色能量发放规则表。

    派生规则（保证最终值与迁移前 chain.py 手写版本逐字段一致）：
    - role   = "{icon} {name}({wallet 去掉 0x 前缀})"
    - scene  = _ROLE_SCENE[wallet]（教学演示文案）
    - amount = energy_rule 存在 → "+{points} 能量"，否则 "0 / 次"
    - wallet = ROLES.wallet
    """
    rules: List[Dict[str, str]] = []
    for r in ROLES:
        rule = r.get("energy_rule") or None
        rules.append({
            "role": f"{r['icon']} {r['name']}({r['wallet'][2:]})",
            "scene": _ROLE_SCENE[r["wallet"]],
            "amount": f"+{rule['points']} 能量" if rule else "0 / 次",
            "wallet": r["wallet"],
        })
    return rules


# 6 角色能量发放规则（阈值与生态合约 eco.py ROLES 严格一致 —— 现由 alliance_roles 单一来源派生）
ROLE_ENERGY_RULES: List[Dict[str, str]] = _derive_role_energy_rules()
