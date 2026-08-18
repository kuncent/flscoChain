<template>
  <div class="report">
    <!-- 顶部：综合评分 -->
    <section class="hero">
      <div class="hero-bg"></div>
      <div class="hero-inner">
        <div class="hero-left">
          <h1 class="hero-title">实训综合报告</h1>
          <p class="hero-sub">
            <span>实训环境：<b>{{ data.chain_mode }}</b></span>
            <span>块高：<b>{{ data.chain_height }}</b></span>
            <span>生成于：<b>{{ data.generated_at }}</b></span>
          </p>
          <div class="hero-metrics">
            <div class="m-card"><span class="m-label">已部署合约</span><span class="m-val">{{ data.contract_count }}<em>份</em></span></div>
            <div class="m-card"><span class="m-label">链上交易</span><span class="m-val">{{ data.tx_count }}<em>笔</em></span></div>
            <div class="m-card"><span class="m-label">累计 Gas</span><span class="m-val">{{ formatInt(data.total_gas) }}</span></div>
            <div class="m-card"><span class="m-label">铸造 NFT</span><span class="m-val">{{ data.nft_count }}<em>件</em></span></div>
            <div class="m-card"><span class="m-label">NFT 交易</span><span class="m-val">{{ data.nft_trade_count }}<em>次</em></span></div>
            <div class="m-card"><span class="m-label">交易成功率</span><span class="m-val">{{ data.success_rate }}<em>%</em></span></div>
          </div>
          <div class="hero-actions">
            <el-button type="primary" round @click="refresh">
              <el-icon><Refresh /></el-icon>&nbsp;刷新数据
            </el-button>
            <el-button type="success" round :loading="downloading" @click="download('md')">
              <el-icon><Download /></el-icon>&nbsp;下载 Markdown 报告
            </el-button>
            <el-button round :loading="downloading" @click="download('json')">
              <el-icon><Document /></el-icon>&nbsp;下载 JSON 数据
            </el-button>
          </div>
        </div>

        <div class="hero-score">
          <div class="score-ring">
            <svg viewBox="0 0 120 120" class="score-svg">
              <circle cx="60" cy="60" r="54" fill="none" stroke="rgba(255,255,255,0.12)" stroke-width="10" />
              <circle cx="60" cy="60" r="54" fill="none" :stroke="scoreColor" stroke-width="10"
                      stroke-linecap="round"
                      :stroke-dasharray="(score.total/100)*339.29 + ' 339.29'"
                      transform="rotate(-90 60 60)"
                      style="transition: stroke-dasharray .8s ease" />
            </svg>
            <div class="score-num">
              <div class="score-v">{{ score.total }}</div>
              <div class="score-max">/ 100</div>
            </div>
          </div>
          <div class="score-level" :style="{ color: scoreColor }">{{ score.level }}</div>
          <div class="score-tip">
            <div>基础模块 <b>{{ score.base_score ?? 0 }}</b> / {{ score.base_full ?? 55 }}</div>
            <div>高级实战 <b>{{ score.eco_score ?? 0 }}</b> / {{ score.eco_full ?? 40 }}</div>
            <div>综合拓展·真学 <b>{{ score.expand_score ?? 0 }}</b> / {{ score.expand_full ?? 5 }}</div>
            <div style="color: #ff6666" v-if="score.penalty">扣分 <b>-{{ score.penalty }}</b> (err-{{ score.error_penalty ?? 0 }} · warn-{{ score.warn_penalty ?? 0 }})</div>
          </div>
        </div>
      </div>
    </section>

    <!-- 学习路径进度路线图（按真实学习流程排序） -->
    <section class="card roadmap-card">
      <div class="sec-head">
        <h2><span class="tag-t eco">🛤️</span>学习路径进度 · 按推荐顺序推进</h2>
        <p class="sec-desc">
          推荐学习顺序：搭链教程 → 合约部署 → 接口调试 → ERC20 交易 → NFT 铸造交易 → 激活 3 份生态合约 → 角色体验 → 能量发放 → 资产兑换 · 完成前一阶段会自动解锁后一阶段
        </p>
      </div>
      <div class="roadmap">
        <div v-for="(st, i) in roadmapSteps" :key="st.key"
             :class="['rp-step', st.status, { 'has-arrow': i < roadmapSteps.length - 1 }]">
          <div class="rp-icon">{{ st.icon }}</div>
          <div class="rp-body">
            <div class="rp-top">
              <span class="rp-idx">L{{ i + 1 }}</span>
              <span class="rp-name">{{ st.name }}</span>
              <span class="rp-tag" :class="st.status">{{ rpStatusLabel(st.status) }}</span>
            </div>
            <div class="rp-sub">{{ st.subtitle }}</div>
            <div class="rp-bar">
              <div class="rp-bar-fill" :style="{ width: st.percent + '%' }"></div>
            </div>
            <div class="rp-foot">
              <span class="rp-score">{{ st.scoreLabel }}</span>
              <el-button
                v-if="st.route"
                link type="primary" size="small"
                @click="$router.push(st.route)"
              >
                {{ st.actionLabel }} →
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 学习质量维度（新增 V2） -->
    <section class="card quality-card" v-if="quality">
      <div class="sec-head">
        <h2><span class="tag-t eco">🧭</span>学习质量维度（行为埋点 + 搭链节奏）</h2>
        <p class="sec-desc">
          鼓励"真学"而非"刷点"：搭链耗时分布、失败探索加分、源码阅读/编译/接口调试次数 — 直接影响 D 项和 I 项评分
        </p>
      </div>
      <div class="q-grid">
        <div class="q-item q-a">
          <div class="q-label">搭链教程进度</div>
          <div class="q-val">{{ quality.tutorial_progress ?? '0/10' }}</div>
          <div class="q-rule">完成 10/10 → 10 分；≥5/10 → 6；≥2/10 → 2</div>
        </div>
        <div class="q-item q-b">
          <div class="q-label">搭链耗时分布（学习节奏）</div>
          <div class="q-val">{{ durationLabel(quality.tutorial_duration_tag) }}</div>
          <div class="q-rule">fast=30 分钟内完成；normal=1 小时；slow=1.5 小时+</div>
        </div>
        <div class="q-item q-c">
          <div class="q-label">搭链失败尝试（探索型学生）</div>
          <div class="q-val">失败 {{ quality.tutorial_fail_attempts ?? 0 }} 次 · 质量 +{{ quality.tutorial_explore_bonus ?? 0 }}</div>
          <div class="q-rule">1 次失败 +1；2 次 +2；≥3 次 +3（D 项 10 分封顶）</div>
        </div>
        <div class="q-item q-d">
          <div class="q-label">操作错误率</div>
          <div class="q-val" :class="{ bad: Number(quality.operation_error_rate || 0) > 15 }">
            {{ Number(quality.operation_error_rate || 0).toFixed(1) }} %
          </div>
          <div class="q-rule">error -1 分/次 (≤-10)；warn -0.3 分/次 (≤-5)；合计≤-15</div>
        </div>
        <div class="q-item q-e" style="grid-column: span 2;">
          <div class="q-label">真学行为埋点（IDE 阅读 / Solc 编译 / ABI 接口）</div>
          <div class="q-val">{{ quality.behavior_read_compile_invoke ?? '-' }}</div>
          <div class="q-rule">读源码≥3 +2；真实编译≥1 +1；接口调试≥1 +2（I 项 5 分满分）</div>
        </div>
      </div>
    </section>

    <!-- 二、详细打分明细 -->
    <section class="card score-card">
      <div class="sec-head">
        <h2><span class="tag-t">S</span>综合评分明细（V2 满分 100）</h2>
        <p class="sec-desc">
          服务端计算，杜绝前端篡改 · 基础 55 分(A~D) + 高级实战 40 分(E~H) + 综合拓展 5 分(I) = 100 分
          · 扣分上限 -15（error≤-10 / warn≤-5）
        </p>
      </div>
      <el-table :data="score.breakdown" :row-class-name="scoreRowClass" border stripe>
        <el-table-column prop="id" label="#" width="50" align="center" />
        <el-table-column prop="section" label="模块" width="100" align="center" />
        <el-table-column prop="name" label="项目" min-width="150">
          <template #default="{ row }">
            <span v-if="row.id === 'P'" style="color:#ff6666;font-weight:600">
              <el-icon><Warning /></el-icon> {{ row.name }}
            </span>
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="full" label="满分" width="70" align="center" />
        <el-table-column label="得分" width="140" align="center">
          <template #default="{ row }">
            <el-progress
              :percentage="row.full ? Math.max(0, Math.min(100, Math.round(row.score * 100 / row.full))) : 0"
              :color="row.score >= 0 ? '#00e6c3' : '#ff6666'"
              :format="() => (row.score < 0 ? '' : row.score + '/' + row.full)"
            />
            <span v-if="row.score < 0" style="color:#ff6666;font-weight:700;margin-left:6px">{{ row.score }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rule" label="规则说明" min-width="320" show-overflow-tooltip />
      </el-table>
    </section>

    <!-- 二点五、智能纠错建议（关键模块） -->
    <section class="card suggest-card">
      <div class="sec-head">
        <h2><span class="tag-t eco">🧭</span>学习建议与提升路径（智能推荐）</h2>
        <p class="sec-desc">
          根据您当前完成情况自动生成：优先级 P1 > P2 > P3 &nbsp;|&nbsp;
          每条建议含「预计加分值」和「对应知识点」，按顺序执行即可快速提升成绩
        </p>
      </div>
      <div class="sg-grid">
        <div
          v-for="(s, idx) in suggestions"
          :key="idx"
          class="sg-card"
          :class="['sg-lvl-' + (s.level || 'info'), 'sg-pri-' + (s.priority || 9)]"
        >
          <div class="sg-head">
            <div class="sg-left">
              <span class="sg-pri">P{{ s.priority ?? '?' }}</span>
              <el-tag :type="sgLevelTag(s.level).type" :effect="'dark'" size="small">
                {{ sgLevelTag(s.level).label }}
              </el-tag>
              <el-tag type="info" effect="plain" size="small" style="margin-left:6px">{{ s.category }}</el-tag>
            </div>
            <div class="sg-gain">
              <span>预计加分</span>
              <b>{{ s.gain || '-' }}</b>
            </div>
          </div>
          <div class="sg-title">{{ s.title }}</div>
          <div class="sg-act">
            <span class="sg-k">下一步怎么做：</span>
            <span>{{ s.action }}</span>
          </div>
          <div class="sg-know">
            <el-icon><Reading /></el-icon>
            <span>知识点：{{ s.knowledge }}</span>
          </div>
          <div class="sg-jump" v-if="sgRouteOf(s.category)">
            <el-button size="small" type="primary" plain round
                       @click="$router.push(sgRouteOf(s.category))">
              🚀 一键前往 · {{ sgJumpLabel(sgRouteOf(s.category)) }}
            </el-button>
          </div>
        </div>
        <div v-if="!suggestions.length" class="empty">
          🎉 所有知识点掌握扎实，暂无优化建议。可以挑战 L5 合约安全 CTF，或切换不同角色做跨角色联合治理演练。
        </div>
      </div>
    </section>

    <!-- 三、合约 / 交易 -->
    <section class="card">
      <div class="sec-head">
        <h2><span class="tag-t">A</span>合约部署 / 链上交易</h2>
        <p class="sec-desc">合约标准分布、部署清单与最近交易流水</p>
      </div>
      <div class="row2">
        <div class="col">
          <h3 class="sub-title">协议分布</h3>
          <div class="std-grid">
            <div v-for="(n, s) in data.standard_breakdown" :key="s" class="std-item">
              <div class="std-name">{{ s }}</div>
              <div class="std-n">{{ n }} 份</div>
            </div>
            <div v-if="!Object.keys(data.standard_breakdown).length" class="empty">尚未部署合约，可到 <b>合约 IDE</b> 部署 HelloCoin、GreenEnergy 等合约</div>
          </div>
        </div>
        <div class="col">
          <h3 class="sub-title">最近 10 笔交易</h3>
          <el-table :data="data.recent_txs" size="small" stripe>
            <el-table-column prop="time" label="时间" width="86" />
            <el-table-column label="From" width="110">
              <template #default="{ row }"><span class="mono">{{ row.from }}</span></template>
            </el-table-column>
            <el-table-column label="To" width="110">
              <template #default="{ row }"><span class="mono">{{ row.to }}</span></template>
            </el-table-column>
            <el-table-column prop="value" label="金额" width="80" align="right" />
            <el-table-column label="Gas" width="100" align="right">
              <template #default="{ row }">{{ formatInt(row.gas) }}</template>
            </el-table-column>
          </el-table>
          <div v-if="!data.recent_txs.length" class="empty mt8">暂无交易记录</div>
        </div>
      </div>
    </section>

    <!-- 四、高级实战（绿色低碳联盟链）核心统计 -->
    <section class="card eco-card">
      <div class="sec-head">
        <h2><span class="tag-t eco">🌿</span>高级实战 · 绿色低碳联盟链</h2>
        <p class="sec-desc">
          联盟节点：管理员 / 地铁 / 公交 / 共享单车 / 外卖平台 / 回收公司 &nbsp;|&nbsp;
          代币标准：ERC20 绿色能量 · ERC721 植树证书 · ERC1155 生态勋章/骑行券
        </p>
      </div>
      <div class="eco-contracts">
        <div class="ec-row">
          <div v-for="cname in ['GreenEnergy','PlantCertificate','EcoBadge']" :key="cname" class="ec-item">
            <div class="ec-name">
              <span :class="['ec-dot', (eco.contracts||{})[cname]?.deployed ? 'ok' : 'lock']"></span>
              {{ cname }}
            </div>
            <div class="ec-status">{{ (eco.contracts||{})[cname]?.deployed ? '已部署' : '未部署' }}</div>
            <div class="ec-addr mono" v-if="(eco.contracts||{})[cname]?.address">
              {{ shortAddr((eco.contracts||{})[cname].address) }}
            </div>
          </div>
        </div>
      </div>

      <div class="eco-kpis">
        <div class="kpi kpi-a">
          <div class="kpi-label">角色体验</div>
          <div class="kpi-val">{{ eco.distinct_roles ?? 0 }}<em>/6 种</em></div>
          <div class="kpi-rule">6/6→10；≥4→8；≥2→5；≥1→2（E项）</div>
        </div>
        <div class="kpi kpi-b">
          <div class="kpi-label">能量发放多样性</div>
          <div class="kpi-val">{{ eco.energy_distinct_roles ?? 0 }}<em>种角色</em></div>
          <div class="kpi-rule">{{ eco.energy_issues ?? 0 }} 次发放 / {{ eco.energy_total ?? 0 }} 点 · 3 种→10分（F项）</div>
        </div>
        <div class="kpi kpi-c">
          <div class="kpi-label">植树证书（品种）</div>
          <div class="kpi-val">{{ eco.certificates ?? 0 }}<em>张 / {{ eco.cert_distinct_species ?? 0 }} 种</em></div>
          <div class="kpi-rule">2+ 树种 → +8；1 树种 → +4（G-1）</div>
        </div>
        <div class="kpi kpi-d">
          <div class="kpi-label">生态勋章</div>
          <div class="kpi-val">{{ eco.badges ?? 0 }}<em>枚</em></div>
          <div class="kpi-rule">勋章 & 券 齐全 → G-2 +4</div>
        </div>
        <div class="kpi kpi-e">
          <div class="kpi-label">骑行券</div>
          <div class="kpi-val">{{ eco.vouchers ?? 0 }}<em>张</em></div>
          <div class="kpi-rule">勋章 1 + 骑行券 1 → +4 分（G-2）</div>
        </div>
        <div class="kpi kpi-f">
          <div class="kpi-label">树种上架</div>
          <div class="kpi-val">{{ eco.tree_species ?? 0 }}<em>种</em></div>
          <div class="kpi-rule">管理员上架 ≥2 种才可拿 G-1 满 8 分</div>
        </div>
      </div>

      <div class="eco-tips mt16">
        <el-alert v-if="(eco.distinct_roles ?? 0) < 6" type="warning" :closable="false" show-icon class="mt8">
          仅体验了 {{ eco.distinct_roles ?? 0 }}/6 种节点角色（E 项 10 分需体验满 6 种），建议依次切换：管理员 / 地铁 / 公交 / 共享单车 / 外卖平台 / 回收公司。
        </el-alert>
        <el-alert v-if="(eco.energy_distinct_roles ?? 0) < 3" type="warning" :closable="false" show-icon class="mt8">
          能量发放多样性不足（F 项 10 分需 ≥3 种角色），至少用地铁、公交、共享单车 3 种角色各发放 1 次即可拿满 F 项 10 分。
        </el-alert>
        <el-alert v-if="(eco.energy_distinct_roles ?? 0) >= 1 && (eco.energy_distinct_roles ?? 0) < 3 && (eco.energy_issues ?? 0) < 3" type="warning" :closable="false" show-icon class="mt8">
          若当前只体验了 1 种角色：发放 ≥3 次可拿 F 项 3 分。
        </el-alert>
        <el-alert v-if="(eco.tree_species ?? 0) < 2" type="warning" :closable="false" show-icon class="mt8">
          管理员上架树种不足 2 种，需切到 <b>管理员</b> 角色新增 ≥2 个树种（如：银杏 1000 能量 / 水杉 1500 能量），G-1 才能拿满 8 分。
        </el-alert>
        <el-alert v-if="(eco.tree_species ?? 0) > 0 && (eco.certificates ?? 0) === 0" type="warning" :closable="false" show-icon class="mt8">
          管理员已上架 {{ eco.tree_species ?? 0 }} 个树种，尚未兑换植树证书：切换到能量较高的角色（如回收公司 1 次 +100）攒能量 ≥1000，兑换 2 种不同树种拿 G-1 满 8 分。
        </el-alert>
        <el-alert v-if="(eco.certificates ?? 0) > 0 && (eco.cert_distinct_species ?? 0) < 2" type="warning" :closable="false" show-icon class="mt8">
          只兑换了 1 种树种的证书，再兑换另一种（当前有 {{ eco.tree_species ?? 0 }} 种可挑）可拿 G-1 满 8 分。
        </el-alert>
        <el-alert v-if="(eco.badges ?? 0) === 0 || (eco.vouchers ?? 0) === 0" type="warning" :closable="false" show-icon class="mt8">
          勋章 / 骑行券未兑换齐（G-2 4 分需要两类都有）：1000 能量换 1 枚碳减排先锋勋章（EcoBadge token_id=1），20 能量换 1 张骑行券（token_id=2）。
        </el-alert>
        <el-alert v-if="(eco.certificates ?? 0) > 0 && (eco.energy_distinct_roles ?? 0) < 4" type="info" :closable="false" show-icon class="mt8">
          💡 额外加分项（G-3 = +3 分）：能量发放角色 ≥4 种即可获得（当前 {{ eco.energy_distinct_roles ?? 0 }}/4），建议再用 外卖平台 和 回收公司 各发一次。
        </el-alert>
        <el-alert
          v-if="deployedCount < 3"
          type="warning" :closable="false" show-icon class="mt8">
          生态合约尚未完全激活（{{ deployedCount }}/3，H 项 5 分需 3/3），请回到「合约管理」依次部署 GreenEnergy、PlantCertificate、EcoBadge。
        </el-alert>
        <el-alert
          v-if="(eco.distinct_roles ?? 0) >= 6 && (eco.energy_distinct_roles ?? 0) >= 4 && (eco.certificates ?? 0) >= 1 && (eco.cert_distinct_species ?? 0) >= 2 && (eco.badges ?? 0) >= 1 && (eco.vouchers ?? 0) >= 1 && deployedCount === 3"
          type="success" :closable="false" show-icon class="mt8">
          卓越！你已完整体验了 V2 评分模型的所有高级实战核心环节：6 大角色满体验 + ≥4 种能量发放 + ≥2 种树种证书 + 勋章/骑行券全部兑换 + 3 份生态合约全激活。
        </el-alert>
      </div>
    </section>

    <!-- 五、操作错误与异常分析 -->
    <section class="card">
      <div class="sec-head">
        <h2><span class="tag-t warn">!</span>操作错误与异常分析</h2>
        <p class="sec-desc">
          每次 error 扣 <b>1 分</b>（上限 -10），每次 warn 扣 <b>0.3 分</b>（上限 -5）· 实训过程中尽量减少错误操作
        </p>
      </div>
      <div class="err-row">
        <div class="err-stat">
          <div class="err-num s">
            <span class="err-v">{{ (eco.logs||{}).success_count ?? 0 }}</span>
            <span class="err-l">成功 success</span>
          </div>
        </div>
        <div class="err-stat">
          <div class="err-num w">
            <span class="err-v">{{ (eco.logs||{}).warn_count ?? 0 }}</span>
            <span class="err-l">警告 warn</span>
          </div>
        </div>
        <div class="err-stat">
          <div class="err-num e">
            <span class="err-v">{{ (eco.logs||{}).error_count ?? 0 }}</span>
            <span class="err-l">错误 error</span>
          </div>
        </div>
        <div class="err-stat">
          <div class="err-num t">
            <span class="err-v">{{ (eco.logs||{}).total ?? 0 }}</span>
            <span class="err-l">日志总数</span>
          </div>
        </div>
      </div>
      <div class="mt16">
        <h3 class="sub-title">最近 20 条异常记录（warn / error）</h3>
        <el-table :data="(eco.logs||{}).recent_issues || []" size="small" border stripe>
          <el-table-column label="#" type="index" width="50" align="center" />
          <el-table-column prop="created_at" label="时间" width="160" />
          <el-table-column prop="module" label="模块" width="90" align="center" />
          <el-table-column prop="action" label="动作" width="120" />
          <el-table-column label="级别" width="80" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.level === 'error' ? 'danger' : 'warning'" effect="dark">
                {{ row.level === 'error' ? '❌ error' : '⚠️ warn' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="message" label="错误/警告信息" min-width="320" show-overflow-tooltip />
          <el-table-column prop="wallet" label="钱包" width="90">
            <template #default="{ row }"><span class="mono">{{ shortAddr(row.wallet, 8) }}</span></template>
          </el-table-column>
        </el-table>
        <div v-if="!((eco.logs||{}).recent_issues||[]).length" class="empty mt8">
          🎉 暂无异常记录！继续保持，争取拿满分。
        </div>
      </div>
    </section>

    <!-- 六、合约清单 + Token TOP5 -->
    <section class="card">
      <div class="sec-head">
        <h2><span class="tag-t">B</span>合约清单 / Token 余额 TOP 5</h2>
      </div>
      <div class="row2">
        <div class="col">
          <h3 class="sub-title">已部署合约</h3>
          <el-table :data="data.contract_list" size="small" border stripe>
            <el-table-column prop="name" label="合约名" min-width="130" />
            <el-table-column prop="standard" label="标准" width="90" align="center" />
            <el-table-column label="地址" width="140">
              <template #default="{ row }"><span class="mono">{{ shortAddr(row.address) }}</span></template>
            </el-table-column>
            <el-table-column label="部署者" width="90">
              <template #default="{ row }"><span class="mono">{{ shortAddr(row.deployer, 8) }}</span></template>
            </el-table-column>
          </el-table>
          <div v-if="!data.contract_list.length" class="empty mt8">暂无部署记录</div>
        </div>
        <div class="col">
          <h3 class="sub-title">Token 余额 TOP 5</h3>
          <el-table :data="data.top_balances" size="small" border stripe>
            <el-table-column label="钱包" width="120">
              <template #default="{ row }"><span class="mono">{{ shortAddr(row.wallet, 8) }}</span></template>
            </el-table-column>
            <el-table-column label="合约" width="140">
              <template #default="{ row }"><span class="mono">{{ shortAddr(row.token_address) }}</span></template>
            </el-table-column>
            <el-table-column prop="balance" label="余额" align="right" />
          </el-table>
          <div v-if="!data.top_balances.length" class="empty mt8">暂无 Token 数据</div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onActivated, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Refresh, Download, Document, Warning, Reading,
} from '@element-plus/icons-vue'
import { reportApi } from '@/api'

const router = useRouter()

/* ========== 类型 ========== */
type Suggestion = {
  priority: number; level: 'error' | 'warn' | 'success' | 'info'; category: string;
  title: string; action: string; gain: string; knowledge: string;
}
type ScoreBreakdown = {
  id: string; section: string; name: string; full: number; score: number; rule: string;
  quality?: any; detail?: any; behavior?: any;
}
type Score = {
  total: number; level: string;
  base_score?: number; base_full?: number;
  eco_score?: number; eco_full?: number;
  expand_score?: number; expand_full?: number;
  penalty?: number; error_penalty?: number; warn_penalty?: number;
  breakdown: ScoreBreakdown[];
  suggestions?: Suggestion[];
  quality_dimension?: {
    tutorial_duration_tag: string;
    operation_error_rate: number;
    tutorial_explore_bonus: number;
    tutorial_fail_attempts: number;
    tutorial_progress: string;
    behavior_read_compile_invoke: string;
  }
}
type Aggregate = {
  generated_at: string; chain_mode: string; chain_height: number;
  contract_count: number; contract_list: any[]; standard_breakdown: Record<string, number>;
  tx_count: number; total_gas: number; gas_avg: number; success_rate: number;
  recent_txs: any[]; nft_count: number; nft_trade_count: number; top_balances: any[];
  eco: any; score: Score;
}
const DEFAULT_ECO = {
  role_wallets: 0, role_switches: 0, distinct_roles: 0,
  energy_issues: 0, energy_total: 0, energy_distinct_roles: 0, energy_breakdown: [],
  tree_species: 0, certificates: 0, cert_cost_total: 0, cert_distinct_species: 0,
  badges: 0, vouchers: 0,
  contracts: {
    GreenEnergy: { deployed: false, address: '' },
    PlantCertificate: { deployed: false, address: '' },
    EcoBadge: { deployed: false, address: '' },
  },
  logs: { total: 0, error_count: 0, warn_count: 0, success_count: 0, error_rate: 0, recent_issues: [] },
  tutorial_progress: {
    total_steps: 6, done_count: 0, failed_count: 0, done_steps: [], failed_steps: [],
    percent: 0, durations_sec: [], total_duration_sec: 0, duration_tag: 'unknown',
  },
  behavior: {
    ide_open_builtin: 0, ide_save_project_sol: 0,
    contract_compile_ok: 0, contract_compile_fail: 0, interface_invoke: 0,
  },
}
const DEFAULT_DATA: Aggregate = {
  generated_at: '-', chain_mode: '-', chain_height: 0,
  contract_count: 0, contract_list: [], standard_breakdown: {},
  tx_count: 0, total_gas: 0, gas_avg: 0, success_rate: 0,
  recent_txs: [], nft_count: 0, nft_trade_count: 0, top_balances: [],
  eco: { ...DEFAULT_ECO },
  score: { total: 0, level: '-', breakdown: [] },
}

/* ========== 状态 ========== */
const data = ref<Aggregate>({ ...DEFAULT_DATA })
const downloading = ref(false)
const score = computed<Score>(() => data.value.score || { total: 0, level: '-', breakdown: [] })
const eco = computed<any>(() => ({ ...DEFAULT_ECO, ...(data.value.eco || {}) }))
const quality = computed(() => score.value.quality_dimension || null)
const deployedCount = computed(() => {
  const cs = (eco.value.contracts || {}) as any
  return Object.values(cs).filter((x: any) => x?.deployed).length
})
const suggestions = computed<Suggestion[]>(() => {
  const list = (score.value.suggestions as any) || []
  return Array.isArray(list) ? (list as Suggestion[]) : []
})

/* ========== 学习路径路线图：按推荐学习顺序 9 阶段 ========== */
const roadmapSteps = computed(() => {
  const e = eco.value
  const sc = score.value
  const bd = (sc.breakdown || []) as ScoreBreakdown[]
  const findBD = (id: string) => bd.find(x => x.id === id)

  // D 搭链教程
  const dProg = (e.tutorial_progress?.done_count as number) || 0
  const dTotal = (e.tutorial_progress?.total_steps as number) || 6
  const dScore = findBD('D')?.score ?? 0
  const dFull = findBD('D')?.full ?? 10

  // A 合约部署
  const cc = data.value.contract_count || 0
  const missStdA = ['ERC20', 'ERC721', 'ERC1155'].filter(s => !(data.value.standard_breakdown?.[s] || 0)).length
  const aScore = findBD('A')?.score ?? 0
  const aFull = findBD('A')?.full ?? 20

  // I 接口调试（真学行为埋点）
  const beh = e.behavior || {}
  const iOpen = (beh.ide_open_builtin || 0) + (beh.ide_save_project_sol || 0)
  const iComp = beh.contract_compile_ok || 0
  const iCall = beh.interface_invoke || 0
  const iScore = findBD('I')?.score ?? 0
  const iFull = findBD('I')?.full ?? 5

  // B 链上交易
  const txN = data.value.tx_count || 0
  const bScore = findBD('B')?.score ?? 0
  const bFull = findBD('B')?.full ?? 15

  // C NFT 铸造交易
  const cScore = findBD('C')?.score ?? 0
  const cFull = findBD('C')?.full ?? 10

  // H 生态合约激活
  const dc = deployedCount.value  // 0~3
  const hScore = findBD('H')?.score ?? 0
  const hFull = findBD('H')?.full ?? 5

  // E 角色体验
  const dr = e.distinct_roles || 0
  const eScore = findBD('E')?.score ?? 0
  const eFull = findBD('E')?.full ?? 10

  // F 能量发放多样性
  const edr = e.energy_distinct_roles || 0
  const fScore = findBD('F')?.score ?? 0
  const fFull = findBD('F')?.full ?? 10

  // G 资产兑换多样性
  const gScore = findBD('G')?.score ?? 0
  const gFull = findBD('G')?.full ?? 15

  const pct = (s: number, f: number) => f <= 0 ? 0 : Math.max(0, Math.min(100, Math.round(s * 100 / f)))
  const statusOf = (p: number) => p >= 95 ? 'done' : (p >= 40 ? 'doing' : 'todo')

  const steps = [
    { key: 'D',  name: '搭链教程',         subtitle: '云桌面 10 步完成 PBFT 联盟链 + 6 组织接入', icon: '🖥️',
      route: '/cloud',     actionLabel: '进入搭链教程',
      percent: pct(dProg/dTotal*100, 100), scoreLabel: `${dScore}/${dFull} 分 · ${dProg}/${dTotal} 步`,
      status: statusOf(dProg/dTotal*100) },
    { key: 'A',  name: '合约部署',         subtitle: 'ERC20 / ERC721 / ERC1155 三份', icon: '📝',
      route: '/ide',       actionLabel: '打开合约 IDE',
      percent: cc <= 0 ? 0 : pct(aScore, aFull), scoreLabel: `${aScore}/${aFull} 分 · ${cc} 份合约 · 缺${missStdA}个标准`,
      status: statusOf(pct(aScore, aFull)) },
    { key: 'I',  name: '接口调试 / 真学', subtitle: '阅读源码 ≥3 · 真实编译 ≥1 · 接口调用 ≥1', icon: '🔬',
      route: '/interfaces', actionLabel: '进入接口调试',
      percent: pct(iScore, iFull), scoreLabel: `${iScore}/${iFull} 分 · 读${iOpen}·编译${iComp}·调${iCall}`,
      status: statusOf(pct(iScore, iFull)) },
    { key: 'B',  name: 'ERC20 交易',      subtitle: '转账 / mint / 授权 满 10 笔 15 分', icon: '💸',
      route: '/wallet',    actionLabel: '打开 ERC20 钱包',
      percent: pct(bScore, bFull), scoreLabel: `${bScore}/${bFull} 分 · ${txN} 笔交易`,
      status: statusOf(pct(bScore, bFull)) },
    { key: 'C',  name: 'NFT 铸造与交易',  subtitle: '铸造 ≥1 件 + 成交 ≥1 笔', icon: '🖼️',
      route: '/nft',       actionLabel: '前往 NFT 市场',
      percent: pct(cScore, cFull), scoreLabel: `${cScore}/${cFull} 分 · 铸${data.value.nft_count||0}·交易${data.value.nft_trade_count||0}`,
      status: statusOf(pct(cScore, cFull)) },
    { key: 'H',  name: '生态合约激活',    subtitle: 'GreenEnergy / PlantCertificate / EcoBadge', icon: '🔌',
      route: '/contracts', actionLabel: '进入合约管理',
      percent: pct(hScore, hFull), scoreLabel: `${hScore}/${hFull} 分 · ${dc}/3 已部署`,
      status: statusOf(pct(hScore, hFull)) },
    { key: 'E',  name: '6 角色体验',      subtitle: '管理员 / 地铁 / 公交 / 单车 / 外卖 / 回收', icon: '🎭',
      route: '/eco',       actionLabel: '进入绿色实战',
      percent: pct(eScore, eFull), scoreLabel: `${eScore}/${eFull} 分 · ${dr}/6 角色`,
      status: statusOf(pct(eScore, eFull)) },
    { key: 'F',  name: '能量发放多样性',  subtitle: '≥3 种角色发能量 F 项满 10 分', icon: '⚡',
      route: '/eco',       actionLabel: '去发放能量',
      percent: pct(fScore, fFull), scoreLabel: `${fScore}/${fFull} 分 · ${edr} 种角色发放`,
      status: statusOf(pct(fScore, fFull)) },
    { key: 'G',  name: '资产兑换多样性',  subtitle: '2+ 树种证书 + 勋章 + 骑行券 + ≥4 发放', icon: '🎁',
      route: '/eco',       actionLabel: '去兑换资产',
      percent: pct(gScore, gFull), scoreLabel: `${gScore}/${gFull} 分 · 券${e.badges||0}·证${e.certificates||0}·树${e.tree_species||0}`,
      status: statusOf(pct(gScore, gFull)) },
  ]
  return steps
})
const rpStatusLabel = (s: string) => ({ done: '✅ 已完成', doing: '🔄 进行中', todo: '⏳ 待开始' } as Record<string,string>)[s] || s

/* ========== 建议卡片 → 跳转路由映射 ========== */
const sgRouteOf = (cat: string) => {
  const c = (cat || '').trim()
  if (/D\s*搭链|搭链教程|云桌面/i.test(c))       return '/cloud'
  if (/A\s*合约|合约部署|协议|ERC\d+ 体验/i.test(c)) return '/ide'
  if (/H\s*合约|合约激活|GreenEnergy|PlantCertificate|EcoBadge/i.test(c)) return '/contracts'
  if (/I\s*拓展|真学|接口调试|源码|编译/i.test(c)) return '/interfaces'
  if (/B\s*链上交易|B 链上|转账|交易笔数/i.test(c)) return '/wallet'
  if (/C\s*NFT|铸造|NFT 交易/i.test(c))            return '/nft'
  if (/[EFG]\s*|角色|发放|能量|兑换|勋章|骑行券|树种|资产|商业|绿色/i.test(c)) return '/eco'
  return ''
}
const sgJumpLabel = (r: string) => ({
  '/cloud': '云桌面·搭链', '/ide': '合约IDE', '/contracts': '合约管理',
  '/interfaces': '接口调试', '/wallet': 'ERC20钱包', '/nft': 'NFT市场', '/eco': '绿色实战',
} as Record<string,string>)[r] || '对应页面'

const scoreColor = computed(() => {
  const s = score.value.total
  if (s >= 90) return '#00e6c3'
  if (s >= 75) return '#409eff'
  if (s >= 60) return '#ff9500'
  if (s >= 40) return '#ffa940'
  return '#ff4d4f'
})

/* ========== 工具 ========== */
const formatInt = (n: any) => (Number(n || 0)).toLocaleString('en-US')
const shortAddr = (addr: string, n = 10) => {
  if (!addr) return '-'
  if (addr.length <= n * 2) return addr
  return addr.slice(0, n) + '…' + addr.slice(-6)
}
const durationLabel = (tag: string) => {
  switch (tag) {
    case 'fast':   return '⚡ 快速 (≤30 分钟)'
    case 'normal': return '✅ 正常 (30~60 分钟)'
    case 'slow':   return '🐢 慢节奏 (60+ 分钟)'
    default:       return '— 暂无数据 —'
  }
}
const scoreRowClass = ({ row }: any) => row.id === 'P' ? 'row-penalty' : (row.score <= 0 && row.id !== 'P' ? 'row-zero' : '')
const sgLevelTag = (level: string) => {
  switch (level) {
    case 'error': return { type: 'danger' as const, label: '🔴 必改' }
    case 'warn':  return { type: 'warning' as const, label: '🟡 建议' }
    case 'success': return { type: 'success' as const, label: '🟢 优秀' }
    default:      return { type: 'info' as const, label: 'ℹ️ 提示' }
  }
}

/* ========== 动作 ========== */
const refresh = async () => {
  try {
    const r: any = await reportApi.aggregate()
    data.value = { ...DEFAULT_DATA, ...(r || {}) }
    if ((r as any)?.error_msg) {
      ElMessage.error('报告数据异常：' + (r as any).error_msg)
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '加载报告失败')
  }
}

const download = async (fmt: 'md' | 'json') => {
  downloading.value = true
  try {
    const blob: any = await reportApi.download(fmt)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = fmt === 'md' ? '实训报告.md' : '实训报告.json'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (e: any) {
    ElMessage.error(e?.message || '下载失败')
  } finally {
    downloading.value = false
  }
}

/* KeepAlive：首次 onMounted，再次进入 onActivated */
onMounted(refresh)
onActivated(refresh)
</script>

<style lang="scss" scoped>
$dq-bg: #0a1024;
$dq-bg-2: #0f172e;
$dq-card: rgba(22, 30, 58, 0.68);
$dq-bord: rgba(255, 255, 255, 0.08);
$dq-text: #e7ecff;
$dq-text-2: #a5adc6;
$eco-c: #00c97e;
$warn-c: #ff9500;
$err-c: #ff4d4f;

.report {
  padding: 18px 20px 50px;
  color: $dq-text;

  .tag-t {
    display: inline-flex; align-items: center; justify-content: center;
    width: 24px; height: 24px; border-radius: 6px;
    background: linear-gradient(135deg, rgba(0, 230, 195, 0.2), rgba(64, 158, 255, 0.2));
    color: #00e6c3; font-weight: 800; font-size: 13px; margin-right: 8px;
    &.eco { background: rgba(0, 201, 126, 0.2); color: $eco-c; font-size: 14px; }
    &.warn { background: rgba(255, 77, 79, 0.18); color: $err-c; }
  }
  .sec-head { margin-bottom: 14px;
    h2 { font-size: 16px; font-weight: 700; margin: 0; display: inline-flex; align-items: center; }
    .sec-desc { margin: 4px 0 0 32px; font-size: 12.5px; color: $dq-text-2; }
  }
  .sub-title {
    font-size: 14px; font-weight: 600; margin: 4px 0 10px;
    padding-left: 10px; border-left: 3px solid #00e6c3;
  }
  .mono { font-family: "JetBrains Mono", Consolas, monospace; font-size: 12.5px; }
  .empty { font-size: 12.5px; color: $dq-text-2; padding: 14px 12px; border-radius: 6px;
    background: rgba(255, 255, 255, 0.03); border: 1px dashed $dq-bord; }
  .mt8 { margin-top: 8px; } .mt16 { margin-top: 16px; }
}

/* ========== Hero / Score ========== */
.hero {
  position: relative; overflow: hidden; border-radius: 14px;
  padding: 20px 24px 24px; margin-bottom: 16px;
  background:
    radial-gradient(1200px 300px at -10% -50%, rgba(0, 230, 195, 0.25), transparent 60%),
    radial-gradient(900px 280px at 110% 10%, rgba(64, 158, 255, 0.25), transparent 60%),
    linear-gradient(180deg, $dq-bg-2, $dq-card);
  border: 1px solid $dq-bord;
  &-bg {
    position: absolute; inset: 0; pointer-events: none; opacity: 0.15;
    background-image:
      linear-gradient(rgba(0, 230, 195, 0.35) 1px, transparent 1px),
      linear-gradient(90deg, rgba(64, 158, 255, 0.35) 1px, transparent 1px);
    background-size: 36px 36px; mask-image: radial-gradient(ellipse at center, #000 30%, transparent 80%);
  }
  &-inner { position: relative; display: grid; grid-template-columns: 1fr 280px; gap: 18px; }
  &-title { font-size: 22px; font-weight: 800; margin: 0; letter-spacing: 0.5px; }
  &-sub { color: $dq-text-2; font-size: 13px; margin: 6px 0 18px;
    span { margin-right: 18px; b { color: $dq-text; font-weight: 600; } }
  }
  &-metrics { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; margin-bottom: 18px;
    .m-card {
      background: rgba(255, 255, 255, 0.04); border: 1px solid $dq-bord; border-radius: 10px;
      padding: 10px 12px;
      .m-label { display: block; font-size: 11.5px; color: $dq-text-2; }
      .m-val { font-size: 19px; font-weight: 800; margin-top: 3px; letter-spacing: 0.5px;
        em { font-size: 11.5px; color: $dq-text-2; font-style: normal; margin-left: 2px; font-weight: 500; }
      }
    }
  }
  &-actions button { margin-right: 8px; }
  &-score {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    background: rgba(10, 16, 36, 0.55); border: 1px solid $dq-bord; border-radius: 14px;
    padding: 16px 10px; position: relative;
  }
}
.score-ring { position: relative; width: 180px; height: 180px; }
.score-svg { width: 180px; height: 180px; }
.score-num {
  position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center;
  .score-v { font-size: 46px; font-weight: 900; line-height: 1; background: linear-gradient(135deg, #00e6c3, #409eff);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
  .score-max { font-size: 13px; color: $dq-text-2; margin-top: 2px; }
}
.score-level { margin-top: 6px; font-weight: 800; font-size: 17px; letter-spacing: 1px; }
.score-tip { margin-top: 8px; font-size: 12.5px; color: $dq-text-2; line-height: 1.9; b { color: $dq-text; } }

/* ========== 学习质量维度 V2 ========== */
.quality-card {
  background:
    radial-gradient(500px 200px at 0% -10%, rgba(0, 201, 126, 0.18), transparent 60%),
    $dq-card;
  border-color: rgba(0, 201, 126, 0.2);
}
.q-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  .q-item {
    border: 1px solid $dq-bord; border-radius: 10px;
    padding: 12px 14px; background: rgba(255,255,255,0.03);
    position: relative; overflow: hidden;
    &::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; }
    &.q-a::before { background: #00e6c3; }
    &.q-b::before { background: #409eff; }
    &.q-c::before { background: #ffb300; }
    &.q-d::before { background: #ff4d4f; }
    &.q-e::before { background: #a461ff; }
    .q-label { font-size: 12px; color: $dq-text-2; }
    .q-val {
      font-size: 20px; font-weight: 800; margin-top: 4px; line-height: 1.3;
      &.bad { color: $err-c; }
    }
    .q-rule { font-size: 11.5px; color: $dq-text-2; margin-top: 4px; }
  }
}

/* ========== Card ========== */
.card {
  background: $dq-card; border: 1px solid $dq-bord; border-radius: 12px;
  padding: 18px 20px; margin-bottom: 16px;
  backdrop-filter: blur(6px);
  :deep(.el-table) { --el-table-bg-color: transparent; --el-table-tr-bg-color: transparent;
    --el-table-header-bg-color: rgba(0, 230, 195, 0.06); --el-table-border-color: rgba(255,255,255,0.08);
    --el-table-header-text-color: #a5adc6; --el-table-text-color: $dq-text;
    font-size: 13px;
  }
  :deep(.el-alert) {
    --el-alert-padding: 10px 14px; border-radius: 8px; border: 1px solid $dq-bord;
  }
  &.score-card :deep(.el-table .row-penalty) { background: rgba(255, 77, 79, 0.08) !important; }
  &.score-card :deep(.el-table .row-zero)   { background: rgba(255, 149, 0, 0.05) !important; }
}
.row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
.col { min-width: 0; }

/* ========== 高级实战 ========== */
.eco-card {
  background:
    radial-gradient(600px 200px at 95% 0%, rgba(0, 201, 126, 0.18), transparent 60%),
    $dq-card;
  border-color: rgba(0, 201, 126, 0.25);
}
.eco-contracts { margin-bottom: 14px;
  .ec-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
  .ec-item {
    background: rgba(255, 255, 255, 0.035); border: 1px solid $dq-bord; border-radius: 10px;
    padding: 12px 14px; display: flex; flex-direction: column; gap: 4px;
  }
  .ec-name { font-weight: 700; display: flex; align-items: center; gap: 8px; }
  .ec-dot {
    display: inline-block; width: 10px; height: 10px; border-radius: 50%;
    background: #ff9500;
    &.ok   { background: #00c97e; box-shadow: 0 0 8px #00c97e; }
    &.lock { background: #ff4d4f; }
  }
  .ec-status { font-size: 12.5px; color: $dq-text-2; }
  .ec-addr { font-size: 12px; color: rgba(0, 230, 195, 0.8); }
}
.eco-kpis { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px;
  .kpi {
    border: 1px solid $dq-bord; border-radius: 10px; padding: 12px 12px; position: relative;
    overflow: hidden; background: rgba(255, 255, 255, 0.03);
    &::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; }
    &.kpi-a::before { background: #00e6c3; }
    &.kpi-b::before { background: #409eff; }
    &.kpi-c::before { background: #00c97e; }
    &.kpi-d::before { background: #ffb300; }
    &.kpi-e::before { background: #e14dff; }
    &.kpi-f::before { background: #ff7a45; }
    .kpi-label { font-size: 11.5px; color: $dq-text-2; }
    .kpi-val { font-size: 20px; font-weight: 800; margin-top: 4px;
      em { font-size: 11.5px; color: $dq-text-2; font-style: normal; margin-left: 2px; font-weight: 500; }
    }
    .kpi-rule { font-size: 11.5px; color: $dq-text-2; margin-top: 3px; }
  }
}

/* ========== 错误分析 ========== */
.err-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px;
  .err-stat {
    border: 1px solid $dq-bord; border-radius: 10px; padding: 14px;
    background: rgba(255, 255, 255, 0.03);
  }
  .err-num {
    display: flex; align-items: baseline; gap: 10px;
    .err-v { font-size: 24px; font-weight: 900; }
    .err-l { font-size: 12px; color: $dq-text-2; }
    &.s .err-v { color: #00c97e; }
    &.w .err-v { color: $warn-c; }
    &.e .err-v { color: $err-c; }
    &.t .err-v { color: #409eff; }
  }
}

/* ========== 智能建议卡片 ========== */
.suggest-card {
  background:
    radial-gradient(500px 200px at 100% -20%, rgba(64, 158, 255, 0.18), transparent 60%),
    $dq-card;
  border-color: rgba(64, 158, 255, 0.25);
}
.sg-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: 12px;
  > .empty { grid-column: 1 / -1; }
}
.sg-card {
  position: relative;
  border: 1px solid $dq-bord;
  border-left: 3px solid #409eff;
  border-radius: 10px;
  background: rgba(255,255,255,0.03);
  padding: 12px 14px;
  transition: transform .15s ease, box-shadow .15s ease, border-color .15s ease;
  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 20px rgba(0,0,0,0.25);
  }
  &.sg-pri-1 { border-left-color: #ff4d4f; box-shadow: 0 0 0 1px rgba(255,77,79,0.18) inset; }
  &.sg-pri-2 { border-left-color: #ff9500; }
  &.sg-pri-3 { border-left-color: #ffa940; }
  &.sg-pri-4 { border-left-color: #409eff; }

  &.sg-lvl-error   { background: linear-gradient(180deg, rgba(255,77,79,0.09), transparent 70%); }
  &.sg-lvl-warn    { background: linear-gradient(180deg, rgba(255,149,0,0.08), transparent 70%); }
  &.sg-lvl-success { background: linear-gradient(180deg, rgba(0,201,126,0.09), transparent 70%); }

  .sg-head {
    display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;
    .sg-left { display: flex; align-items: center; gap: 8px; }
  }
  .sg-pri {
    display: inline-flex; width: 28px; height: 22px; border-radius: 5px;
    background: rgba(64,158,255,0.18); color: #a0cfff;
    font-weight: 800; font-size: 11.5px; align-items: center; justify-content: center;
  }
  .sg-pri-1 .sg-pri { background: rgba(255,77,79,0.22); color: #ffa39e; }
  .sg-pri-2 .sg-pri { background: rgba(255,149,0,0.22); color: #ffd591; }
  .sg-pri-3 .sg-pri { background: rgba(255,169,64,0.22); color: #ffd591; }

  .sg-gain { display: flex; flex-direction: column; align-items: flex-end;
    font-size: 11.5px; color: $dq-text-2;
    b { font-size: 15px; color: #00e6c3; font-weight: 800; line-height: 1.2; }
  }
  .sg-title { font-weight: 700; font-size: 14px; margin-bottom: 6px; line-height: 1.4; }
  .sg-act {
    font-size: 12.5px; color: #d4d8e8; line-height: 1.7; margin-bottom: 8px;
    .sg-k { color: $dq-text-2; display: inline-block; }
  }
  .sg-know {
    display: flex; align-items: center; gap: 5px;
    padding-top: 8px; border-top: 1px dashed $dq-bord;
    font-size: 12px; color: $dq-text-2;
    svg { color: #00e6c3; }
  }
  .sg-jump { margin-top: 10px; display: flex; justify-content: flex-end; }
}

/* ========== 学习路径路线图 V2 ========== */
.roadmap-card {
  background:
    radial-gradient(600px 220px at 100% 0%, rgba(164, 97, 255, 0.16), transparent 60%),
    radial-gradient(600px 220px at 0% 100%, rgba(0, 230, 195, 0.14), transparent 60%),
    $dq-card;
  border-color: rgba(164, 97, 255, 0.22);
}
.roadmap {
  position: relative;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px 18px;
}
.rp-step {
  position: relative;
  display: grid;
  grid-template-columns: 46px 1fr;
  gap: 12px;
  align-items: start;
  padding: 14px 14px 12px;
  border-radius: 12px;
  background: rgba(255,255,255,0.03);
  border: 1px solid $dq-bord;
  transition: transform .15s ease, border-color .15s ease;
  &:hover { transform: translateY(-1px); border-color: rgba(0, 230, 195, 0.35); }
  &.done {
    border-color: rgba(0, 201, 126, 0.35);
    background: linear-gradient(180deg, rgba(0, 201, 126, 0.08), transparent 70%);
  }
  &.doing {
    border-color: rgba(64, 158, 255, 0.4);
    background: linear-gradient(180deg, rgba(64, 158, 255, 0.09), transparent 70%);
    &::after {
      content: "";
      position: absolute; top: 12px; right: 12px;
      width: 8px; height: 8px; border-radius: 50%;
      background: #409eff;
      box-shadow: 0 0 0 0 rgba(64, 158, 255, 0.7);
      animation: rp-pulse 1.6s infinite;
    }
  }
  &.todo { opacity: .75; }
}
@keyframes rp-pulse {
  0%   { box-shadow: 0 0 0 0 rgba(64,158,255,.65); }
  70%  { box-shadow: 0 0 0 10px rgba(64,158,255,0); }
  100% { box-shadow: 0 0 0 0 rgba(64,158,255,0); }
}
.rp-step .rp-icon {
  width: 46px; height: 46px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  font-size: 22px;
  background: rgba(255,255,255,0.05);
  border: 1px solid $dq-bord;
}
.rp-step.done  .rp-icon { background: rgba(0,201,126,0.18); border-color: rgba(0,201,126,0.35); }
.rp-step.doing .rp-icon { background: rgba(64,158,255,0.18); border-color: rgba(64,158,255,0.4); }

.rp-top {
  display: flex; align-items: center; gap: 8px;
  .rp-idx {
    display: inline-flex; align-items: center; justify-content: center;
    width: 28px; height: 18px; border-radius: 4px;
    font-size: 11px; font-weight: 800; letter-spacing: 0.5px;
    background: linear-gradient(135deg, rgba(0,230,195,0.25), rgba(64,158,255,0.25));
    color: #a5f1df;
  }
  .rp-name { font-weight: 700; font-size: 14px; }
  .rp-tag {
    margin-left: auto;
    font-size: 11px; padding: 2px 8px; border-radius: 999px;
    background: rgba(255,255,255,0.04);
    &.done  { background: rgba(0,201,126,0.18); color: #79e2b4; }
    &.doing { background: rgba(64,158,255,0.2);  color: #a0cfff; }
    &.todo  { background: rgba(255,255,255,0.06); color: #959db9; }
  }
}
.rp-sub { font-size: 12px; color: $dq-text-2; margin: 4px 0 8px; line-height: 1.5; }
.rp-bar {
  height: 6px; border-radius: 999px;
  background: rgba(255,255,255,0.06);
  overflow: hidden; margin-bottom: 8px;
}
.rp-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #00e6c3, #409eff, #a461ff);
  transition: width .6s ease;
}
.rp-foot {
  display: flex; align-items: center; justify-content: space-between;
  .rp-score { font-size: 12px; color: $dq-text-2; b { color: #00e6c3; } }
  button { font-size: 12px !important; padding: 0 !important; }
}

/* 响应式 */
@media (max-width: 1200px) {
  .hero-metrics { grid-template-columns: repeat(3, 1fr); }
  .eco-kpis { grid-template-columns: repeat(3, 1fr); }
  .q-grid   { grid-template-columns: repeat(2, 1fr); }
  .q-grid .q-e { grid-column: span 2; }
  .roadmap  { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 960px) {
  .hero-inner { grid-template-columns: 1fr; }
  .row2 { grid-template-columns: 1fr; }
  .eco-contracts .ec-row { grid-template-columns: 1fr; }
  .eco-kpis { grid-template-columns: repeat(2, 1fr); }
  .err-row { grid-template-columns: repeat(2, 1fr); }
  .hero-metrics { grid-template-columns: repeat(2, 1fr); }
  .sg-grid { grid-template-columns: 1fr; }
  .q-grid   { grid-template-columns: 1fr; }
  .q-grid .q-e { grid-column: auto; }
  .roadmap  { grid-template-columns: 1fr; }
}
</style>
