<template>
  <div class="explorer dq-enter-up">
    <!-- 搜索栏 -->
    <div class="dq-card search">
      <div class="dq-card-title" style="margin-bottom:10px">
        <span class="title-icon"><el-icon><Search /></el-icon></span>
        区块链浏览器
        <span class="dq-tag info" style="margin-left:auto">
          <el-icon><Link /></el-icon>&nbsp;
          {{ modeLabel }} · 块高 #{{ overview?.height || app.chainHeight }}
        </span>
      </div>
      <el-input v-model="keyword" placeholder="搜索 区块高度 / 交易哈希 / 合约地址 / 钱包地址" @keyup.enter="search" size="large">
        <template #prefix><el-icon><Search /></el-icon></template>
        <template #append>
          <el-button @click="search">
            <el-icon><Search /></el-icon> 搜索
          </el-button>
        </template>
      </el-input>
    </div>

    <!-- Gas 柱图 + 统计卡片（顶部行） -->
    <div class="exp-top" v-if="overview">
      <!-- 左：4张玻璃拟态KPI卡 -->
      <div class="kpi-row">
        <div class="dq-glass kpi">
          <div class="kpi-top">
            <div class="kpi-ico k-h"><el-icon><Cpu /></el-icon></div>
            <span class="dq-tag">最新块高</span>
          </div>
          <CountUp :target="overview.height" class="kpi-num" />
          <div class="kpi-sub">链顶端区块</div>
        </div>
        <div class="dq-glass kpi">
          <div class="kpi-top">
            <div class="kpi-ico k-t"><el-icon><Document /></el-icon></div>
            <span class="dq-tag">交易总数</span>
          </div>
          <CountUp :target="overview.tx_count" class="kpi-num" />
          <div class="kpi-sub">链上累计交易</div>
        </div>
        <div class="dq-glass kpi">
          <div class="kpi-top">
            <div class="kpi-ico k-c"><el-icon><Files /></el-icon></div>
            <span class="dq-tag">已部署合约</span>
          </div>
          <CountUp :target="overview.contract_count" class="kpi-num" />
          <div class="kpi-sub">含 ERC20/721/1155</div>
        </div>
        <div class="dq-glass kpi">
          <div class="kpi-top">
            <div class="kpi-ico k-g"><el-icon><Lightning /></el-icon></div>
            <span class="dq-tag warn">平均 Gas</span>
          </div>
          <CountUp :target="avgGas" class="kpi-num warn" />
          <div class="kpi-sub">近 {{ blocks.length }} 块均值</div>
        </div>
      </div>

      <!-- 右：Gas 消耗柱状图（原生 SVG 不依赖 echarts） -->
      <div class="dq-glass gas-card">
        <div class="gas-head">
          <div>
            <div class="gas-title">Gas 消耗趋势</div>
            <div class="gas-sub">近 <b class="dq-mono">{{ blocks.length }}</b> 个区块的累计 Gas Used</div>
          </div>
          <div class="gas-tags">
            <span class="dq-tag info dq-mono">峰值 {{ maxGas.toLocaleString() }}</span>
            <span class="dq-tag dq-mono">均值 {{ avgGas.toLocaleString() }}</span>
          </div>
        </div>
        <div class="gas-chart">
          <svg viewBox="0 0 600 140" preserveAspectRatio="none" class="gas-svg">
            <!-- 背景网格 -->
            <g stroke="rgba(255,255,255,0.035)" stroke-width="1">
              <line x1="0" y1="35" x2="600" y2="35"/>
              <line x1="0" y1="70" x2="600" y2="70"/>
              <line x1="0" y1="105" x2="600" y2="105"/>
            </g>
            <!-- 柱体 -->
            <g v-for="(b, i) in blocksForChart" :key="i">
              <rect
                :x="b.x" :y="b.y"
                :width="b.w" :height="b.h"
                :fill="b.fill"
                rx="2"
              >
                <title>区块 #{{ b.n }} · Gas {{ b.gas.toLocaleString() }}</title>
              </rect>
            </g>
            <!-- 均线（虚线） -->
            <path :d="avgLinePath" fill="none" stroke="#ffcf4d" stroke-width="1.2" stroke-dasharray="4,4" opacity="0.75">
              <title>Gas 均值基准线</title>
            </path>
          </svg>
          <div class="gas-x">
            <span class="gx dq-mono" v-for="(l, i) in xLabels" :key="i">{{ l }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="grid-2" style="margin-top:14px">
      <!-- 区块列表：增加出块耗时 badge -->
      <div class="dq-card">
        <div class="dq-card-title">最近区块 <span class="dq-tag info" style="margin-left:auto">{{ blocks.length }} / {{ total }}</span></div>
        <el-table :data="blocks" border size="small" max-height="420" class="exp-table" stripe>
          <el-table-column label="高度" width="90">
            <template #default="{ row }">
              <div class="blk-cell">
                <span class="dq-mono link" @click="goBlock(row.number)">#{{ row.number }}</span>
                <span class="blk-badge dq-tag info" v-if="row._delta">
                  <el-icon><Timer /></el-icon>{{ row._delta }}
                </span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="hash" label="哈希" min-width="180">
            <template #default="{ row }"><span class="dq-mono dim">{{ short(row.hash) }}</span></template>
          </el-table-column>
          <el-table-column label="交易 / Gas" width="150">
            <template #default="{ row }">
              <div class="txgas-cell">
                <span class="dq-tag">{{ row.tx_count }} Tx</span>
                <span class="dq-mono dim gas-used">{{ (row.gas_used || 0).toLocaleString() }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="timestamp" label="时间" width="160">
            <template #default="{ row }">{{ fmtTime(row.timestamp) }}</template>
          </el-table-column>
        </el-table>
        <el-pagination small layout="prev, pager, next" :total="total" :page-size="size" v-model:current-page="page" @current-change="loadBlocks" style="margin-top:10px" />
      </div>

      <!-- 交易列表 -->
      <div class="dq-card">
        <div class="dq-card-title">
          最近交易
          <span class="dq-tag info" v-if="curAddr" style="margin-left:auto">过滤: {{ short(curAddr) }}</span>
          <el-button size="small" @click="clearFilter" v-if="curAddr" style="margin-left:8px">清除</el-button>
        </div>
        <el-table :data="txs" border size="small" max-height="420" class="exp-table" stripe>
          <el-table-column prop="hash" label="交易哈希" min-width="150">
            <template #default="{ row }"><span class="dq-mono link" @click="goTx(row.hash)">{{ short(row.hash) }}</span></template>
          </el-table-column>
          <el-table-column label="方法" width="120">
            <template #default="{ row }">
              <span class="dq-tag" v-if="row.method">{{ row.method }}</span>
              <span class="dq-tag accent" v-else-if="row.to_addr === '' || row.to_addr === null">deploy</span>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column label="流向" min-width="180">
            <template #default="{ row }">
              <div class="flow-cell">
                <span class="dq-mono link" @click="goAddr(row.from_addr)">{{ short(row.from_addr) }}</span>
                <el-icon class="flow-arrow"><Right /></el-icon>
                <span class="dq-mono link" v-if="row.to_addr" @click="goAddr(row.to_addr)">{{ short(row.to_addr) }}</span>
                <span class="dq-tag accent" v-else>部署</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="Gas" width="90">
            <template #default="{ row }"><span class="dq-mono dim">{{ (row.gas_used || 0).toLocaleString() }}</span></template>
          </el-table-column>
        </el-table>
        <el-button size="small" @click="loadTxs" style="margin-top:10px">刷新</el-button>
      </div>
    </div>

    <!-- 已识别合约 -->
    <div class="dq-card" style="margin-top:14px" v-if="contracts.length">
      <div class="dq-card-title">已识别合约 <span class="dq-tag info" style="margin-left:auto">自动识别 ERC20/721/1155</span></div>
      <el-table :data="contracts" border size="small" class="exp-table" stripe>
        <el-table-column prop="name" label="合约名" min-width="140" />
        <el-table-column label="协议" width="120">
          <template #default="{ row }">
            <span class="std-tag" :class="stdClass(row.standard)" v-if="row.standard">{{ row.standard }}</span>
            <span class="std-tag s-custom" v-else>自定义</span>
          </template>
        </el-table-column>
        <el-table-column prop="address" label="地址" min-width="240">
          <template #default="{ row }"><span class="dq-mono link" @click="goAddr(row.address)">{{ row.address }}</span></template>
        </el-table-column>
        <el-table-column prop="deployer" label="部署者" min-width="160">
          <template #default="{ row }"><span class="dq-mono dim">{{ short(row.deployer) }}</span></template>
        </el-table-column>
        <el-table-column prop="created_at" label="部署时间" width="170" />
      </el-table>
    </div>

    <EmptyIllustration v-else type="contract" style="margin-top:14px" />

    <!-- 详情抽屉（结构化展示） -->
    <el-drawer v-model="drawer" size="660px" :title="drawerTitle">
      <div class="detail-wrap" v-if="detail">
        <!-- 区块详情 -->
        <template v-if="detailType === 'block'">
          <div class="dq-flow-card"><div class="dq-flow-card__inner">
            <div class="detail-head">
              <div class="dh-ico b-ico"><el-icon><Coin /></el-icon></div>
              <div class="dh-info">
                <div class="dh-name">区块 #{{ detail.number }}</div>
                <div class="dh-sub dq-mono">{{ short(detail.hash) }}</div>
              </div>
              <div class="dh-badges">
                <span class="dq-tag">{{ detail.tx_count }} Tx</span>
                <span class="dq-tag info">{{ fmtTime(detail.timestamp) }}</span>
              </div>
            </div>
          </div></div>
          <div class="detail-body" style="margin-top:14px">
            <div class="dq-kv"><span class="k">区块高度</span><span class="v">#{{ detail.number }}</span></div>
            <div class="dq-kv"><span class="k">哈希</span><span class="v break">{{ detail.hash }}</span></div>
            <div class="dq-kv"><span class="k">父哈希</span><span class="v break dq-mono dim">{{ detail.parent_hash }}</span></div>
            <div class="dq-kv"><span class="k">交易数</span><span class="v"><span class="dq-tag">{{ detail.tx_count }}</span></span></div>
            <div class="dq-kv"><span class="k">时间</span><span class="v">{{ fmtTime(detail.timestamp) }}</span></div>
          </div>
          <div class="dq-card-title" style="margin-top:16px">区块内交易 <span class="dq-tag info" style="margin-left:auto">{{ (detail.transactions || []).length }} 笔</span></div>
          <div class="tx-mini" v-for="t in (detail.transactions || [])" :key="t.hash" @click="showTx(t)">
            <span class="dq-mono link">{{ short(t.hash) }}</span>
            <span class="dq-tag" v-if="t.method">{{ t.method }}</span>
            <span class="dq-mono dim">{{ short(t.from_addr) }} → {{ t.to_addr ? short(t.to_addr) : '(deploy)' }}</span>
            <span class="dq-mono dim" style="margin-left:auto">{{ (t.gas_used || 0).toLocaleString() }} Gas</span>
          </div>
          <EmptyIllustration v-if="!(detail.transactions || []).length" type="explorer" :hide-text="true" />
        </template>

        <!-- 交易详情（参数解码可视化 + ABI/Event 解码表） -->
        <template v-else-if="detailType === 'tx'">
          <div class="dq-flow-card"><div class="dq-flow-card__inner">
            <div class="detail-head">
              <div class="dh-ico t-ico"><el-icon><Document /></el-icon></div>
              <div class="dh-info">
                <div class="dh-name">交易详情</div>
                <div class="dh-sub dq-mono">{{ short(detail.hash) }}</div>
              </div>
              <div class="dh-badges">
                <span class="dq-tag" :class="detail.status === 'success' ? '' : 'error'">{{ detail.status || 'pending' }}</span>
                <span class="dq-tag info" v-if="detail.method">{{ detail.method }}</span>
              </div>
            </div>
          </div></div>
          <div class="detail-body" style="margin-top:14px">
            <div class="dq-kv"><span class="k">交易哈希</span><span class="v break">{{ detail.hash }}</span></div>
            <div class="dq-kv"><span class="k">区块号</span><span class="v link" @click="goBlock(detail.block_number)">#{{ detail.block_number }}</span></div>
            <div class="dq-kv"><span class="k">From</span><span class="v break link" @click="goAddr(detail.from_addr)">{{ detail.from_addr }}</span></div>
            <div class="dq-kv">
              <span class="k">To</span>
              <span class="v break link" v-if="detail.to_addr" @click="goAddr(detail.to_addr)">{{ detail.to_addr }}</span>
              <span class="v"><span class="dq-tag accent">合约部署</span></span>
            </div>
            <div class="dq-kv"><span class="k">Gas 消耗</span><span class="v dq-mono">{{ (detail.gas_used || 0).toLocaleString() }}</span></div>
            <div class="dq-kv">
              <span class="k">状态</span>
              <span class="v">
                <span class="dq-tag" :class="detail.status === 'success' ? '' : 'error'">
                  {{ detail.status === 'success' ? '✅ 成功' : '❌ 失败' }}
                </span>
              </span>
            </div>
          </div>

          <!-- ABI 输入参数解码表 -->
          <div class="dq-card-title" style="margin-top:20px">
            <span class="title-icon"><el-icon><Connection /></el-icon></span>
            接口调用解码 · 输入参数
            <span class="dq-tag accent" v-if="detail.method" style="margin-left:auto">{{ detail.method }}</span>
          </div>
          <div v-if="parsedArgsArr.length" class="args-table-wrap">
            <table class="args-table">
              <thead>
                <tr>
                  <th style="width:40px">#</th>
                  <th>参数名</th>
                  <th>类型</th>
                  <th>解码值</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in parsedArgsArr" :key="row.key">
                  <td class="idx dq-mono">{{ row.idx }}</td>
                  <td class="pname dq-mono">{{ row.key }}</td>
                  <td class="ptype"><span class="dq-tag info">{{ guessType(row.val) }}</span></td>
                  <td class="pval dq-mono break">{{ formatVal(row.val) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="dq-tip" v-else-if="detail.input && detail.input !== '0x'">
            <span class="dt-label">原始输入:</span>
            <span class="dq-mono">{{ short(detail.input) }}</span>
            （未识别合约 ABI，无法解码）
          </div>
          <EmptyIllustration v-else type="default" title="无输入数据" />

          <!-- 事件日志解码表 -->
          <template v-if="detail.logs && detail.logs.length">
            <div class="dq-card-title" style="margin-top:20px">
              <span class="title-icon"><el-icon><BellFilled /></el-icon></span>
              事件日志 ({{ detail.logs.length }})
              <span class="dq-tag accent" v-if="detail.event_standard" style="margin-left:auto">协议识别: {{ detail.event_standard }}</span>
            </div>
            <div class="log-list">
              <div class="log-card" v-for="(log, i) in detail.logs" :key="i">
                <div class="log-card-head">
                  <span class="log-idx">Log #{{ i + 1 }}</span>
                  <span class="dq-mono dim log-addr" :title="log.address">合约: {{ short(log.address) }}</span>
                </div>
                <table class="logs-table">
                  <thead>
                    <tr><th style="width:100px">字段</th><th>值</th></tr>
                  </thead>
                  <tbody>
                    <tr v-for="(t, j) in log.topics" :key="'t'+j">
                      <td class="fname"><span class="topic-tag">topic{{ j }}</span></td>
                      <td class="fval dq-mono break">
                        <span v-if="j === 0 && knownEventSig(t)" class="dq-tag accent ev-sig">{{ knownEventSig(t) }}</span>
                        <span class="t-hex">{{ t }}</span>
                      </td>
                    </tr>
                    <tr v-if="log.data && log.data !== '0x'">
                      <td class="fname"><span class="topic-tag data">data</span></td>
                      <td class="fval dq-mono break">{{ log.data }}</td>
                    </tr>
                  </tbody>
                </table>
                <div class="log-decoded" v-if="log.decoded && Object.keys(log.decoded).length">
                  <div class="ld-label"><el-icon><MagicStick /></el-icon> 已 ABI 解码</div>
                  <div class="ld-row" v-for="(dv, dk) in log.decoded" :key="dk">
                    <span class="ld-k dq-mono">{{ dk }}</span>
                    <span class="ld-v dq-mono">{{ formatVal(dv) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </template>

        <!-- 地址画像 -->
        <template v-else-if="detailType === 'address'">
          <div class="dq-flow-card"><div class="dq-flow-card__inner">
            <div class="detail-head">
              <div class="dh-ico" :class="detail.is_contract ? 'c-ico' : 'a-ico'">
                <el-icon><component :is="detail.is_contract ? 'Files' : 'User'" /></el-icon>
              </div>
              <div class="dh-info">
                <div class="dh-name">{{ detail.is_contract ? '合约地址' : '普通账户' }}</div>
                <div class="dh-sub dq-mono addr-val">{{ short(detail.address) }}</div>
              </div>
              <div class="dh-badges">
                <span class="std-tag" :class="stdClass(detail.contract?.standard)" v-if="detail.contract?.standard">{{ detail.contract.standard }}</span>
                <span class="dq-tag info">{{ detail.tx_count }} Tx</span>
              </div>
            </div>
          </div></div>
          <div class="detail-body" style="margin-top:14px">
            <div class="dq-kv"><span class="k">地址</span><span class="v break">{{ detail.address }}</span></div>
            <div class="dq-kv" v-if="detail.contract"><span class="k">合约名</span><span class="v">{{ detail.contract.name }}</span></div>
            <div class="dq-kv" v-if="detail.contract?.standard"><span class="k">协议</span><span class="v"><span class="std-tag" :class="stdClass(detail.contract.standard)">{{ detail.contract.standard }}</span></span></div>
            <div class="dq-kv"><span class="k">交易数</span><span class="v">{{ detail.tx_count }}</span></div>
          </div>
          <div class="dq-card-title" style="margin-top:16px">相关交易 <span class="dq-tag info" style="margin-left:auto">最近 {{ (detail.txs || []).length }} 笔</span></div>
          <div class="tx-mini" v-for="t in (detail.txs || []).slice(0, 20)" :key="t.hash" @click="showTx(t)">
            <span class="dq-mono link">{{ short(t.hash) }}</span>
            <span class="dq-tag" v-if="t.method">{{ t.method }}</span>
            <span class="dq-mono dim">{{ short(t.from_addr) }} → {{ t.to_addr ? short(t.to_addr) : '(deploy)' }}</span>
            <span class="dq-mono dim" style="margin-left:auto">{{ (t.gas_used || 0).toLocaleString() }} Gas</span>
          </div>
          <EmptyIllustration v-if="!(detail.txs || []).length" type="explorer" :hide-text="true" />
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onActivated, onMounted } from 'vue'
import { explorerApi } from '@/api'
import { ElMessage } from 'element-plus'
import { Search, Link, Cpu, Document, Files, Lightning, Timer, Right, Coin, Connection, BellFilled, MagicStick, User } from '@element-plus/icons-vue'
import CountUp from '@/components/CountUp.vue'
import EmptyIllustration from '@/components/EmptyIllustration.vue'
import { useAppStore } from '@/stores/app'
import { fmtTime as _fmtTime } from '@/utils/storage'

const app = useAppStore()
const keyword = ref('')
const overview = ref<any>(null)
const blocks = ref<any[]>([])
const txs = ref<any[]>([])
const contracts = ref<any[]>([])
const page = ref(1)
const size = ref(20)
const total = ref(0)
const curAddr = ref('')

const drawer = ref(false)
const drawerTitle = ref('')
const detail = ref<any>(null)
const detailType = ref<'block' | 'tx' | 'address'>('block')

/* 把 parsed_args 从 {key:val} 转成 [{key, val, idx}] 数组，避免 Vue v-for 三元索引 TS 报错 */
const parsedArgsArr = computed(() => {
  const obj = detail.value?.parsed_args
  if (!obj) return []
  return Object.entries(obj).map(([k, v], i) => ({ key: k, val: v, idx: i + 1 }))
})

const modeLabel = computed(() => {
  const m = app.chainMode
  if (m === 'fisco') return 'FISCO-BCOS'
  if (m === 'evm') return 'py-evm Engine'
  return 'Local Sandbox'
})

const short = (h: string) => (h && h.length > 16) ? h.slice(0, 10) + '...' + h.slice(-4) : (h || '-')
const fmtTime = (t: number) => _fmtTime(t)

/* ---------- 出块耗时（delta）计算 ---------- */
function computeDeltas(list: any[]) {
  for (let i = 0; i < list.length; i++) {
    if (i + 1 < list.length && list[i].timestamp && list[i + 1].timestamp) {
      const d = Number(list[i].timestamp) - Number(list[i + 1].timestamp)
      if (d >= 0 && d < 3600) {
        list[i]._delta = d < 60 ? `${d}s` : `${Math.floor(d / 60)}m${d % 60}s`
      }
    }
  }
}

/* ---------- Gas 柱图 ---------- */
const maxGas = computed(() => Math.max(1, ...blocks.value.map((b) => Number(b.gas_used) || 0)))
const avgGas = computed(() => {
  if (!blocks.value.length) return 0
  const total = blocks.value.reduce((a, b) => a + (Number(b.gas_used) || 0), 0)
  return Math.round(total / blocks.value.length)
})
const blocksForChart = computed(() => {
  const list = blocks.value.slice().reverse() // 按时间升序，从旧→新
  if (!list.length) return []
  const n = list.length
  const W = 600, gap = 4, barW = (W - gap * (n + 1)) / n
  const max = maxGas.value
  return list.map((b, i) => {
    const gas = Number(b.gas_used) || 0
    const h = Math.max(2, (gas / max) * 110)
    const isAvg = Math.abs(gas - avgGas.value) / Math.max(1, avgGas.value) < 0.08
    const fill = isAvg
      ? 'url(#grad-avg)'
      : gas > avgGas.value * 1.25
        ? 'url(#grad-high)'
        : 'url(#grad-normal)'
    return {
      x: gap + i * (barW + gap),
      y: 130 - h,
      w: barW,
      h,
      n: b.number,
      gas,
      fill: `rgba(0,230,195,${0.25 + (gas / max) * 0.6})`,
    }
  })
})
const xLabels = computed(() => {
  const list = blocks.value.slice().reverse()
  if (!list.length) return []
  const n = 5
  const step = Math.max(1, Math.floor(list.length / (n - 1)))
  const out: string[] = []
  for (let i = 0; i < n; i++) {
    const idx = Math.min(list.length - 1, i * step)
    out.push('#' + (list[idx]?.number || 0))
  }
  return out
})
const avgLinePath = computed(() => {
  const n = blocksForChart.value.length
  if (!n) return ''
  const avgY = 130 - (avgGas.value / Math.max(1, maxGas.value)) * 110
  const firstX = blocksForChart.value[0].x + blocksForChart.value[0].w / 2
  const lastX = blocksForChart.value[n - 1].x + blocksForChart.value[n - 1].w / 2
  return `M ${firstX} ${avgY} L ${lastX} ${avgY}`
})

/* ---------- 协议类型样式 ---------- */
function stdClass(name: string) {
  if (!name) return 's-custom'
  const s = name.toLowerCase()
  if (s.includes('erc20')) return 's-erc20'
  if (s.includes('erc721')) return 's-erc721'
  if (s.includes('erc1155')) return 's-erc1155'
  return 's-custom'
}

/* ---------- ABI / Event 辅助 ---------- */
function guessType(v: any): string {
  if (v == null) return 'null'
  if (typeof v === 'bigint') return 'uint256'
  if (typeof v === 'number') return 'uint'
  if (typeof v === 'boolean') return 'bool'
  if (Array.isArray(v)) return `${guessType(v[0] || '0')}[]`
  if (/^0x[a-f0-9]{40}$/i.test(String(v))) return 'address'
  if (/^0x[a-f0-9]{64}$/i.test(String(v))) return 'bytes32'
  if (/^0x/i.test(String(v))) return 'bytes'
  return 'string'
}
function formatVal(v: any): string {
  if (v == null) return '∅'
  if (typeof v === 'bigint') return v.toString()
  if (Array.isArray(v)) return '[' + v.map(formatVal).join(', ') + ']'
  return String(v)
}
const EVENT_SIGS: Record<string, string> = {
  '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef': 'Transfer(address,address,uint256)',
  '0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925': 'Approval(address,address,uint256)',
  '0x17307eab39ab30500eb72f9129f5019a32a159851e17e2b32b70439ef7222c7b': 'ApprovalForAll(address,address,bool)',
  '0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62': 'TransferSingle(address,address,address,uint256,uint256)',
  '0x4a39dc06d4c0dbc64b70af90fd698a233a518aa5d07e595d983b8c0526c8f7fb': 'TransferBatch(address,address,address,uint256[],uint256[])',
}
function knownEventSig(t: string): string | null {
  return EVENT_SIGS[t?.toLowerCase?.()] || null
}

/* ---------- 加载逻辑 ---------- */
const loadOverview = async () => { overview.value = await explorerApi.overview() }
const loadBlocks = async () => {
  const r: any = await explorerApi.blocks(page.value, size.value)
  blocks.value = r.items; total.value = r.total
  computeDeltas(blocks.value)
}
const loadTxs = async () => {
  if (curAddr.value) {
    const r: any = await explorerApi.txs(100, curAddr.value)
    txs.value = r.items
  } else {
    const r: any = await explorerApi.txs(50)
    txs.value = r.items
  }
}
const loadContracts = async () => { contracts.value = ((await explorerApi.contracts()) as any).items || [] }

function clearFilter() {
  curAddr.value = ''
  loadTxs()
}

const search = async () => {
  const k = keyword.value.trim()
  if (!k) return
  if (/^\d+$/.test(k)) {
    await goBlock(Number(k))
  } else if (k.startsWith('0x') && k.length >= 32) {
    try { await goTx(k) } catch { await goAddr(k) }
  } else {
    await goAddr(k)
  }
}

const goBlock = async (n: number) => {
  const b: any = await explorerApi.block(n)
  detail.value = b; detailType.value = 'block'; drawerTitle.value = `区块 #${n}`; drawer.value = true
}
const goTx = async (h: string) => {
  const t: any = await explorerApi.tx(h)
  detail.value = t; detailType.value = 'tx'; drawerTitle.value = '交易详情'; drawer.value = true
}
function showTx(t: any) {
  detail.value = t; detailType.value = 'tx'; drawerTitle.value = '交易详情'; drawer.value = true
}
const goAddr = async (a: string) => {
  if (!a) return
  curAddr.value = a; await loadTxs()
  const r: any = await explorerApi.address(a)
  detail.value = r; detailType.value = 'address'; drawerTitle.value = '地址画像'; drawer.value = true
}

const loadAll = () => { loadOverview(); loadBlocks(); loadTxs(); loadContracts() }
/* 首次进入触发 onMounted，KeepAlive 缓存后再次进入触发 onActivated，两者都执行加载 */
onMounted(loadAll)
onActivated(loadAll)
</script>

<style scoped lang="scss">
/* ---------- 顶部布局 ---------- */
.exp-top { display: grid; grid-template-columns: 1fr 1.4fr; gap: 14px; margin-top: 14px; }
.kpi-row { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; align-content: start; }
.kpi { padding: 12px;
  .kpi-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
  .kpi-ico {
    width: 28px; height: 28px; border-radius: 7px;
    display: inline-flex; align-items: center; justify-content: center;
    color: var(--dq-primary); font-size: 14px;
    &.k-c { background: rgba(0,230,195,0.15); }
    &.k-t { background: rgba(77,141,255,0.15); color: var(--dq-info); }
    &.k-h { background: rgba(45,212,191,0.15); color: var(--dq-success); }
    &.k-g { background: rgba(255,207,77,0.15); color: var(--dq-warn); }
  }
  .kpi-num {
    font-family: var(--dq-mono); font-size: 24px; font-weight: 800;
    background: var(--dq-grad-primary);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent;
    &.warn { background: linear-gradient(135deg, #ffcf4d, #e6a23c); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
  }
  .kpi-sub { font-size: 11px; color: var(--dq-text-dim); margin-top: 2px; }
}

/* ---------- Gas 柱图 ---------- */
.gas-card { padding: 14px; }
.gas-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; gap: 10px;
  .gas-title { font-size: 14px; font-weight: 600; color: var(--dq-text); }
  .gas-sub { font-size: 11px; color: var(--dq-text-dim); margin-top: 2px; b { color: var(--dq-primary); } }
  .gas-tags { display: flex; gap: 6px; flex-shrink: 0; }
}
.gas-chart { position: relative; }
.gas-svg { width: 100%; height: 140px; display: block; }
.gas-x {
  display: flex; justify-content: space-between;
  margin-top: 4px;
  .gx { font-size: 10px; color: var(--dq-text-dimmer); }
}

/* ---------- 区块 / 交易表 ---------- */
.exp-table { margin-bottom: 10px; }
.blk-cell { display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  .blk-badge { padding: 1px 5px; font-size: 10px; gap: 2px; }
}
.txgas-cell { display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  .gas-used { font-size: 11px; }
}
.flow-cell { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; min-width: 0;
  .flow-arrow { color: var(--dq-primary); font-size: 12px; flex-shrink: 0; }
}
.link { color: var(--dq-primary); cursor: pointer; &:hover { text-decoration: underline; } }
.dim { color: var(--dq-text-dim); }

/* ---------- 协议色 ---------- */
.std-tag {
  display: inline-flex; align-items: center; gap: 3px;
  padding: 2px 8px; border-radius: 4px;
  font-family: var(--dq-mono); font-size: 11px; font-weight: 600;
  border: 1px solid transparent;
  &.s-erc20   { color: #4d8dff; background: rgba(77,141,255,0.1);  border-color: rgba(77,141,255,0.3); }
  &.s-erc721  { color: #f5379b; background: rgba(245,55,155,0.1);  border-color: rgba(245,55,155,0.3); }
  &.s-erc1155 { color: #ffcf4d; background: rgba(255,207,77,0.1);  border-color: rgba(255,207,77,0.3); }
  &.s-custom  { color: #7b8aab; background: rgba(123,138,171,0.1); border-color: rgba(123,138,171,0.3); }
}

/* ---------- 详情：header 卡片（流动描边） ---------- */
.detail-wrap { font-size: 13px; padding-right: 4px; }
.detail-head { display: flex; gap: 12px; align-items: center; }
.dh-ico {
  width: 46px; height: 46px; border-radius: 12px;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 22px; flex-shrink: 0;
  &.b-ico { background: rgba(0,230,195,0.15); color: var(--dq-primary); }
  &.t-ico { background: rgba(77,141,255,0.15); color: var(--dq-info); }
  &.c-ico { background: rgba(245,55,155,0.15); color: var(--dq-accent); }
  &.a-ico { background: rgba(123,138,171,0.18); color: #97a5c6; }
}
.dh-info { flex: 1; min-width: 0;
  .dh-name { font-size: 17px; font-weight: 700; color: var(--dq-text); }
  .dh-sub { font-size: 12px; color: var(--dq-text-dim); margin-top: 2px; }
  .addr-val { font-size: 11px; letter-spacing: 0; }
}
.dh-badges { display: flex; gap: 6px; flex-shrink: 0; flex-wrap: wrap; }
.detail-body { padding: 2px 2px; }
.break { word-break: break-all; }

/* ---------- ABI 参数表 ---------- */
.args-table-wrap { margin: 8px 0 4px; }
.args-table {
  width: 100%; border-collapse: collapse;
  background: rgba(0,230,195,0.03);
  border: 1px solid rgba(0,230,195,0.2);
  border-radius: 8px; overflow: hidden;
  font-size: 12.5px;
  th, td { padding: 8px 10px; text-align: left; border-bottom: 1px dashed var(--dq-border); vertical-align: top; }
  thead th { background: rgba(0,230,195,0.06); color: var(--dq-primary); font-size: 11px; text-transform: uppercase; letter-spacing: 0.6px; }
  tbody tr:last-child td { border-bottom: none; }
  .idx { color: var(--dq-text-dimmer); }
  .pname { color: var(--dq-info); font-weight: 600; }
  .pval { color: var(--dq-text); font-size: 12px; }
}

/* ---------- 事件日志 ---------- */
.log-list { display: flex; flex-direction: column; gap: 10px; }
.log-card {
  background: var(--dq-bg-2);
  border-left: 3px solid var(--dq-accent);
  border-radius: 8px; padding: 10px 12px;
}
.log-card-head {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px; padding-bottom: 6px; border-bottom: 1px dashed var(--dq-border);
  .log-idx { font-family: var(--dq-mono); font-weight: 700; color: var(--dq-accent); font-size: 12px; }
  .log-addr { font-size: 11px; }
}
.logs-table {
  width: 100%; border-collapse: collapse; font-size: 12px;
  th, td { padding: 5px 8px; text-align: left; border-bottom: 1px dashed rgba(255,255,255,0.04); vertical-align: top; }
  th { color: var(--dq-text-dim); font-size: 11px; font-weight: 600; background: rgba(255,255,255,0.015); }
  tbody tr:last-child td { border-bottom: none; }
  .fname { width: 110px; }
  .topic-tag {
    display: inline-block; font-family: var(--dq-mono); font-size: 10px;
    padding: 1px 6px; border-radius: 3px;
    color: var(--dq-accent); background: rgba(245,55,155,0.1);
    border: 1px solid rgba(245,55,155,0.25);
    &.data { color: var(--dq-info); background: rgba(77,141,255,0.1); border-color: rgba(77,141,255,0.25); }
  }
  .ev-sig { margin-right: 6px; margin-bottom: 2px; }
  .t-hex { color: var(--dq-text-dim); }
}
.log-decoded {
  margin-top: 8px;
  background: linear-gradient(135deg, rgba(245,55,155,0.05), rgba(0,230,195,0.04));
  border: 1px solid rgba(123,138,171,0.2);
  border-radius: 6px; padding: 8px 10px;
  .ld-label { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; color: var(--dq-text-dim); margin-bottom: 6px; }
  .ld-row { display: flex; gap: 10px; padding: 3px 0; font-size: 12px;
    .ld-k { min-width: 110px; color: var(--dq-info); flex-shrink: 0; }
    .ld-v { color: var(--dq-text); flex: 1; word-break: break-all; }
  }
}

/* ---------- 小交易列表 ---------- */
.tx-mini {
  display: flex; align-items: center; gap: 8px; padding: 7px 10px;
  background: var(--dq-bg-2); border-radius: 6px; margin-bottom: 5px;
  cursor: pointer; transition: background .15s;
  font-size: 12px;
  &:hover { background: rgba(0,230,195,0.06); }
  .dim { font-size: 11px; }
}

@media (max-width: 1180px) {
  .exp-top { grid-template-columns: 1fr; }
  .kpi-row { grid-template-columns: repeat(4, 1fr); }
  .grid-2 { grid-template-columns: 1fr !important; }
}
@media (max-width: 760px) {
  .kpi-row { grid-template-columns: repeat(2, 1fr); }
}
</style>
