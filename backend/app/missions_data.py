"""联盟运营微任务清单常量（L5 高级实战 · 10 微任务）。

文案平移自前端 frontend/src/views/Dashboard.vue 的 L5_MICRO_TASKS，
服务端由此成为任务清单的权威数据源（前端仅保留本地打卡降级逻辑）。

字段说明：
    key         任务唯一标识（与前端 localStorage 打卡键一致，勿改动）
    phase       阶段分组（L5-1 系统激活 / L5-2 能量发放 / L5-3 资产兑换）
    title/desc/label/hint/to    任务展示文案（与前端原文案保持一致）
    verify_desc 关联验收数据源描述（说明服务端自动验收依据哪张表 / 哪种口径）
"""
from __future__ import annotations

MISSIONS: list[dict] = [
    # ---------------- Phase 1：系统激活（2 步） ----------------
    {
        "key": "eco_t1",
        "phase": "L5-1",
        "title": "T1 · 管理员激活系统合约",
        "desc": "切换到管理员 → 一键激活 3 份系统合约（能量代币 / 证书 / 勋章）",
        "label": "4 分钟",
        "hint": "目标：3/3 合约激活（报告 H 项 5 分）",
        "to": "/eco",
        "verify_desc": "deployed_contracts 表中 GreenEnergy / PlantCertificate / EcoBadge 三份系统合约均已部署",
    },
    {
        "key": "eco_t2",
        "phase": "L5-1",
        "title": "T2 · 体验 6 大角色全览",
        "desc": "依次切换管理员 / 地铁 / 公交 / 单车 / 外卖 / 回收 6 个角色",
        "label": "5 分钟",
        "hint": "目标：6/6 角色体验（报告 E 项 10 分满分）",
        "to": "/eco",
        "verify_desc": "learning_events 表（event_type='eco_role_switch'）中切换过全部 6 个联盟角色",
    },
    # ---------------- Phase 2：能量发放（5 种真实场景） ----------------
    {
        "key": "eco_t3",
        "phase": "L5-2",
        "title": "T3 · 地铁集团发放 · 通勤 10 公里",
        "desc": "切到「地铁」角色 → 向学习者钱包发放绿色能量（metro 场景）",
        "label": "3 分钟",
        "hint": "场景体验：≥1 种发放（F 项起步 3 分）",
        "to": "/eco",
        "verify_desc": "eco_energy_records 表（role_key='metro'）中地铁角色向本钱包发放能量 ≥1 次",
    },
    {
        "key": "eco_t4",
        "phase": "L5-2",
        "title": "T4 · 公交公司发放 · 换乘 2 次",
        "desc": "切到「公交」角色 → 向学习者钱包发放绿色能量（bus 场景）",
        "label": "3 分钟",
        "hint": "目标：≥2 种不同角色（F 项 6 分）",
        "to": "/eco",
        "verify_desc": "eco_energy_records 表中 bus 角色发放过能量，且累计 ≥2 种联盟角色向本钱包发放过能量",
    },
    {
        "key": "eco_t5",
        "phase": "L5-2",
        "title": "T5 · 共享单车发放 · 骑行 5 公里",
        "desc": "切到「共享单车」角色 → 发放绿色能量（bike 场景）",
        "label": "3 分钟",
        "hint": "目标：≥3 种不同角色（F 项 10 分满分）",
        "to": "/eco",
        "verify_desc": "eco_energy_records 表中 bike 角色发放过能量，且累计 ≥3 种联盟角色向本钱包发放过能量",
    },
    {
        "key": "eco_t6",
        "phase": "L5-2",
        "title": "T6 · 外卖平台发放 · 无需餐具",
        "desc": "切到「外卖平台」角色 → 发放绿色能量（takeout 场景）",
        "label": "3 分钟",
        "hint": "能量多样性：≥4 种 → G 项 +3 加分",
        "to": "/eco",
        "verify_desc": "eco_energy_records 表中 takeout 角色发放过能量，且累计 ≥4 种联盟角色向本钱包发放过能量",
    },
    {
        "key": "eco_t7",
        "phase": "L5-2",
        "title": "T7 · 回收公司发放 · 快递纸箱回收",
        "desc": "切到「回收公司」角色 → 发放绿色能量（recycling 场景）",
        "label": "3 分钟",
        "hint": "能量发放 diversity 满分达成",
        "to": "/eco",
        "verify_desc": "eco_energy_records 表中 recycling 角色发放过能量，且 metro/bus/bike/takeout/recycling 5 种角色全部发放过",
    },
    # ---------------- Phase 3：资产兑换（3 种 NFT） ----------------
    {
        "key": "eco_t8",
        "phase": "L5-3",
        "title": "T8 · 兑换植树证书（2+ 树种）",
        "desc": "切换回学习者 → 用积攒的能量兑换「植树证书」NFT",
        "label": "5 分钟",
        "hint": "G 项 8 分：≥2 种树种 8 分 / 1 种 4 分",
        "to": "/eco",
        "verify_desc": "eco_certificates 表中本钱包兑换过 ≥2 种不同树种的植树证书",
    },
    {
        "key": "eco_t9",
        "phase": "L5-3",
        "title": "T9 · 兑换勋章 & 骑行券（两类 NFT）",
        "desc": "兑换「绿色勋章」NFT + 「免费骑行券」NFT，凑齐资产多样性",
        "label": "5 分钟",
        "hint": "G 项 4 分：两类都有 4 分 / 一类 2 分",
        "to": "/eco",
        "verify_desc": "eco_badges 表中本钱包兑换过 badge（勋章）与 voucher（骑行券）两类资产",
    },
    {
        "key": "eco_t10",
        "phase": "L5-3",
        "title": "T10 · 生成实训报告 · 查看 L5 评分",
        "desc": "生成报告并查看 E~H 四项得分与智能纠错建议",
        "label": "3 分钟",
        "hint": "交付：40 分高级实战 + 5 分综合拓展 ≥ 40/45",
        "to": "/report",
        "verify_desc": "learning_events 表（event_type='report_view'）中生成 / 查看过实训报告 ≥1 次",
    },
]
