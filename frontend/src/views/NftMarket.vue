<template>
  <div class="nft dq-enter-up">
    <!-- 学习引导 -->
    <div class="dq-flow-card guide-card"><div class="dq-flow-card__inner">
      <div class="guide-head">
        <div class="guide-title">
          <span class="g-icon">🖼️</span>
          链上资产交易市场
          <span class="dq-tag accent dq-tag-lg">NFT + 绿色资产</span>
          <span class="dq-live" style="margin-left:6px"><span class="dot"></span>真实链铸造 + 交易</span>
        </div>
      </div>
      <div class="flow">
        <div class="flow-step">
          <div class="fs-no accent">01</div>
          <div class="fs-info">
            <div class="fs-title">联盟链铸造 / 居民兑换</div>
            <div class="fs-desc">铸造入口在「绿色低碳联盟链」：联盟角色铸造勋章 / 骑行券，居民用绿色能量兑换证书 / 勋章 / 骑行券</div>
            <div class="fs-tags"><span class="fs-kw">选择角色</span><span class="fs-kw accent">mint</span><span class="fs-kw">能量兑换</span></div>
          </div>
        </div>
        <div class="flow-arrow">→</div>
        <div class="flow-step">
          <div class="fs-no accent">02</div>
          <div class="fs-info">
            <div class="fs-title">挂单出售</div>
            <div class="fs-desc">居民在「ERC20 钱包 · 我的绿色资产」设定能量价格挂牌，绿色资产用 GreenEnergy 能量计价</div>
            <div class="fs-tags"><span class="fs-kw muted">listing</span><span class="fs-kw">挂牌</span><span class="fs-kw accent">能量计价</span></div>
          </div>
        </div>
        <div class="flow-arrow">→</div>
        <div class="flow-step">
          <div class="fs-no accent">03</div>
          <div class="fs-info">
            <div class="fs-title">购买 / 流通</div>
            <div class="fs-desc">ERC20 / GreenEnergy 转账(买家→卖家) + NFT transferFrom(卖家→买家)，<b>资产自由流通</b></div>
            <div class="fs-tags"><span class="fs-kw">两笔交易</span><span class="fs-kw accent">transferFrom</span><span class="fs-kw">safeTransferFrom</span></div>
          </div>
        </div>
      </div>
    </div></div>

    <!-- 顶部 KPI 卡 -->
    <div class="kpi-row">
      <div class="dq-glass kpi">
        <div class="kpi-top">
          <div class="kpi-ico k-mint"><el-icon><Picture /></el-icon></div>
          <span class="dq-tag accent">资产总量</span>
        </div>
        <CountUp :target="displayList.length" class="kpi-num accent" />
        <div class="kpi-sub">{{ filter === 'green' ? '在售绿色资产' : '已铸造 NFT' }}</div>
      </div>
      <div class="dq-glass kpi">
        <div class="kpi-top">
          <div class="kpi-ico k-buy"><el-icon><Promotion /></el-icon></div>
          <span class="dq-tag info">累计成交</span>
        </div>
        <CountUp :target="totalTrades" class="kpi-num info" />
        <div class="kpi-sub">购买交易笔数</div>
      </div>
      <div class="dq-glass kpi">
        <div class="kpi-top">
          <div class="kpi-ico k-own"><el-icon><User /></el-icon></div>
          <span class="dq-tag warn">当前持有</span>
        </div>
        <CountUp :target="myOwned" class="kpi-num warn" />
        <div class="kpi-sub">我持有的资产</div>
      </div>
    </div>

    <div class="toolbar dq-card" style="margin-top:14px">
      <div class="dq-card-title">
        资产列表
        <span class="dq-tip" style="margin-left:auto; font-weight:400" v-if="filter !== 'green'">
          铸造 / 兑换请前往「绿色低碳联盟链」（本页为资产交易买卖中心）
        </span>
        <el-button v-else size="small" type="success" @click="$router.push('/eco')" style="margin-left:auto">前往绿色实战兑换</el-button>
      </div>
      <el-radio-group v-model="filter" @change="load">
        <el-radio-button label="">全部 NFT</el-radio-button>
        <el-radio-button label="ERC721">ERC721</el-radio-button>
        <el-radio-button label="ERC1155">ERC1155</el-radio-button>
        <el-radio-button label="green">🌿 绿色资产</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 通用 NFT 列表 -->
    <div class="grid" v-if="filter !== 'green' && list.length" v-loading="loading">
      <div class="dq-card nft-card" v-for="n in list" :key="n.token_id">
        <div class="thumb" @click="openDetail(n.token_id)">
          <img v-if="n.image_url" :src="n.image_url" />
          <div v-else class="placeholder"><el-icon><Picture /></el-icon></div>
          <span class="dq-tag accent std">{{ n.standard }}</span>
        </div>
        <div class="info">
          <div class="title">{{ n.title || '未命名 NFT' }}</div>
          <div class="author dq-mono">作者: {{ short(n.author) }}</div>
          <div class="price">{{ n.price || '0' }} <span class="unit">Token</span></div>
          <div class="ops">
            <el-button size="small" @click="openDetail(n.token_id)">详情</el-button>
            <el-button size="small" type="primary" @click="openBuy(n)">购买</el-button>
            <a v-if="n.image_url" :href="n.image_url" download target="_blank">
              <el-button size="small">下载</el-button>
            </a>
          </div>
        </div>
      </div>
    </div>

    <!-- 绿色资产列表 -->
    <div class="grid green-grid" v-if="filter === 'green'" v-loading="loading">
      <div class="dq-card green-card" v-for="g in greenList" :key="g.id">
        <div class="g-thumb">
          <div class="g-icon-lg">{{ greenAssetIcon(g.asset_type) }}</div>
          <span class="dq-tag" :class="g.asset_type === 'certificate' ? 'accent' : 'warn'">
            {{ greenAssetTypeLabel(g.asset_type) }}
          </span>
        </div>
        <div class="info">
          <div class="title">{{ g.asset_name }}</div>
          <div class="author dq-mono">卖家: {{ short(g.seller) }}</div>
          <div class="price green-price">
            {{ g.price_energy }} <span class="unit">⚡ 能量</span>
          </div>
          <div class="g-meta">
            <span class="dq-tag muted">{{ g.standard }}</span>
            <span class="dq-mono dim">ID: {{ g.token_id }}</span>
          </div>
          <div class="ops">
            <el-button
              v-if="g.seller !== app.currentWallet"
              size="small"
              type="primary"
              :disabled="greenBalance < g.price_energy"
              :loading="buyingId === g.id"
              @click="buyGreen(g)"
            >
              {{ greenBalance >= g.price_energy ? '购买' : `需 ${g.price_energy} 能量` }}
            </el-button>
            <el-button
              v-else
              size="small"
              type="danger"
              plain
              :loading="delistingId === g.id"
              @click="delistGreen(g)"
            >
              下架
            </el-button>
          </div>
        </div>
      </div>
      <div v-if="!greenList.length && !loading" class="green-empty">
        <EmptyIllustration type="nft" title="暂无绿色资产在售" subtitle="前往「绿色低碳联盟链」兑换资产后可挂牌出售" />
      </div>
    </div>

    <div v-if="filter !== 'green' && !list.length" style="margin-top:14px">
      <EmptyIllustration
        v-if="!loading"
        type="nft"
        title="暂无 NFT 在售"
        subtitle="铸造与兑换入口在「绿色低碳联盟链」，居民在钱包挂牌后资产在此流通"
      />
    </div>

    <!-- 购买对话框 -->
    <el-dialog v-model="buyDlg" title="购买 NFT (使用 ERC20 Token)" width="460px">
      <div class="buy-info" v-if="cur">
        <div>{{ cur.title }} <span class="dq-tag accent">{{ cur.standard }}</span></div>
        <div>价格: {{ buy.price }} Token</div>
      </div>
      <el-form label-width="100px" style="margin-top:10px">
        <el-form-item label="买家地址"><el-input v-model="buy.buyer" /></el-form-item>
        <el-form-item label="Token 合约">
          <el-select v-model="buy.token_contract" style="width:100%">
            <el-option v-for="t in tokens" :key="t.address" :label="`${t.name} (${t.symbol})`" :value="t.address" />
          </el-select>
        </el-form-item>
      </el-form>
      <div class="tip">提示：前往「ERC20 钱包」发行 Token 后，此处可选择用于购买。</div>
      <template #footer>
        <el-button @click="buyDlg = false">取消</el-button>
        <el-button type="primary" @click="doBuy">确认购买</el-button>
      </template>
    </el-dialog>

    <!-- 详情抽屉 -->
    <el-drawer v-model="detailDlg" size="560px" :title="detail?.title || 'NFT 详情'">
      <div v-if="detail" class="detail">
        <div class="d-thumb">
          <img v-if="detail.image_url" :src="detail.image_url" />
          <div v-else class="placeholder"><el-icon><Picture /></el-icon></div>
        </div>
        <div class="d-row"><span>协议</span><span class="dq-tag accent">{{ detail.standard }}</span></div>
        <div class="d-row"><span>Token ID</span><span class="dq-mono">{{ detail.token_id }}</span></div>
        <div class="d-row"><span>合约地址</span><span class="dq-mono">{{ detail.contract_address }}</span></div>
        <div class="d-row"><span>作者</span><span class="dq-mono">{{ detail.author }}</span></div>
        <div class="d-row"><span>当前持有者</span><span class="dq-mono">{{ detail.owner }}</span></div>
        <div class="d-row"><span>当前价格</span><span>{{ detail.price }} Token</span></div>
        <div class="d-row"><span>描述</span><span>{{ detail.description }}</span></div>
        <a v-if="detail.image_url" :href="detail.image_url" download target="_blank">
          <el-button style="margin-top:10px">下载数据文件</el-button>
        </a>

        <div class="dq-card-title" style="margin-top:16px">历史交易记录</div>
        <el-table :data="detail.trades" border size="small">
          <el-table-column prop="from_addr" label="From" min-width="140">
            <template #default="{ row }"><span class="dq-mono dim">{{ short(row.from_addr) }}</span></template>
          </el-table-column>
          <el-table-column prop="to_addr" label="To" min-width="140">
            <template #default="{ row }"><span class="dq-mono dim">{{ short(row.to_addr) }}</span></template>
          </el-table-column>
          <el-table-column prop="price" label="价格" width="100" />
          <el-table-column prop="created_at" label="时间" width="170" />
        </el-table>
      </div>
    </el-drawer>

    <!-- TxTimeline：NFT 铸造 / 购买 交易流水 -->
    <div class="dq-card" style="margin-top:14px" v-if="timelineList.length || list.length">
      <TxTimeline
        :list="timelineList"
        :title="`NFT 交易记录 · 铸造/购买 共 ${timelineList.length} 笔`"
      />
    </div>
    <div v-else style="margin-top:14px" v-if="!loading">
      <EmptyIllustration
        type="nft"
        title="暂无 NFT 交易"
        subtitle="铸造或购买 NFT 后，交易流水会显示在这里"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onActivated, onMounted, reactive, computed } from 'vue'
import { nftApi, walletApi, ecoApi } from '@/api'
import { useAppStore } from '@/stores/app'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Picture, Promotion, User } from '@element-plus/icons-vue'
import CountUp from '@/components/CountUp.vue'
import EmptyIllustration from '@/components/EmptyIllustration.vue'
import TxTimeline from '@/components/TxTimeline.vue'

const app = useAppStore()
const route = useRoute()
const list = ref<any[]>([])
const greenList = ref<any[]>([])
const loading = ref(false)
const filter = ref('')
const tokens = ref<any[]>([])
const txRecords = ref<any[]>([])  // 本地持久化的交易流水
const buyingId = ref<number | null>(null)
const delistingId = ref<number | null>(null)
const greenBalance = ref(0)  // 当前钱包绿色能量余额（用于购买按钮可用性判断）

const NFT_TX_KEY = 'learn_nft_tx_v1'
function loadTxRecords(): any[] {
  try {
    const raw = localStorage.getItem(NFT_TX_KEY)
    const arr = raw ? JSON.parse(raw) : []
    return Array.isArray(arr) ? arr : []
  } catch { return [] }
}
function saveTxRecords() { localStorage.setItem(NFT_TX_KEY, JSON.stringify(txRecords.value)) }

const buyDlg = ref(false)
const cur = ref<any>(null)
const buy = reactive({ token_id: '', buyer: app.currentWallet, token_contract: '', price: '' })

const detailDlg = ref(false)
const detail = ref<any>(null)

const short = (h: string) => h ? h.slice(0, 10) + '...' + h.slice(-4) : '-'

const totalTrades = computed(() => txRecords.value.filter(x => /购买|Buy/i.test(x.kind)).length)
const myOwned = computed(() => {
  const nftOwned = list.value.filter(n => n.owner === app.currentWallet).length
  const greenOwned = greenList.value.filter(g => g.seller === app.currentWallet).length
  return nftOwned + greenOwned
})

/** 用于 KPI 显示总数 */
const displayList = computed(() => filter.value === 'green' ? greenList.value : list.value)

/* ==================== 绿色资产元数据 ==================== */
const greenAssetIcon = (t: string) =>
  ({ certificate: '🌱', badge: '🏅', voucher: '🎫' }[t] || '🌿')
const greenAssetTypeLabel = (t: string) =>
  ({ certificate: '植树证书', badge: '生态勋章', voucher: '骑行券' }[t] || t)

/* 将 NFT list + 交易记录 映射成 TxTimeline */
const timelineList = computed(() => {
  const out: any[] = []
  // 1) 铸造：从 NFT 本身的 created_at 推断
  for (const n of list.value) {
    out.push({
      kind: `铸造 ${n.standard}`,
      from: '0x0000000000000000000000000000000000000000',
      to: n.author,
      to_is_contract: false,
      amount: `#${n.token_id}`,
      token: n.title || '未命名',
      gas: '460000',
      tx_hash: `mint_${n.token_id}_${n.contract_address || 'def'}`,
      time: n.created_at || new Date().toISOString().slice(0, 19).replace('T', ' '),
      status: 'ok',
    })
  }
  // 2) 本地记录的购买交易
  for (const t of txRecords.value) {
    out.push({ ...t })
  }
  // 3) 详情抽屉里的 trades（购买）
  if (detail.value?.trades?.length) {
    for (const tr of detail.value.trades) {
      out.push({
        kind: 'NFT 购买',
        from: tr.from_addr,
        to: tr.to_addr,
        to_is_contract: false,
        amount: String(tr.price || ''),
        token: 'ERC20 支付',
        gas: '210000',
        tx_hash: tr.tx_hash || `trade_${tr.created_at}`,
        time: tr.created_at || '-',
        status: 'ok',
      })
    }
  }
  out.sort((a, b) => {
    const ta = a.time === '-' ? 0 : new Date(String(a.time)).getTime()
    const tb = b.time === '-' ? 0 : new Date(String(b.time)).getTime()
    return tb - ta
  })
  return out
})

const load = async (silent = false) => {
  if (!silent) loading.value = true
  try {
    if (filter.value === 'green') {
      // 加载绿色资产市场在售列表
      const r: any = await ecoApi.marketItems()
      greenList.value = r?.items || []
    } else {
      list.value = ((await nftApi.list(filter.value)) as any).items
    }
  } finally { if (!silent) loading.value = false }
}
const loadTokens = async () => { tokens.value = ((await walletApi.tokens()) as any).items }

/** 加载当前钱包绿色能量余额（购买按钮可用性判断） */
const loadGreenBalance = async () => {
  try {
    const r: any = await ecoApi.energyBalance(app.currentWallet || '0xlearner')
    greenBalance.value = Number(r?.balance ?? r ?? 0)
  } catch { greenBalance.value = 0 }
}

/** 购买绿色资产：GreenEnergy 转账 + NFT 转移 */
const buyGreen = async (g: any) => {
  if (greenBalance.value < g.price_energy) {
    ElMessage.warning(`绿色能量不足：需要 ${g.price_energy}，当前 ${greenBalance.value}`)
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认购买「${g.asset_name}」？需要支付 ${g.price_energy} 绿色能量`,
      '购买绿色资产',
      { confirmButtonText: '确认购买', cancelButtonText: '取消', type: 'warning' },
    )
  } catch { return }
  buyingId.value = g.id
  try {
    const r: any = await ecoApi.marketBuy(app.currentWallet || '0xlearner', g.id)
    const now = new Date().toISOString().slice(0, 19).replace('T', ' ')
    txRecords.value.push({
      kind: `绿色资产购买`,
      from: app.currentWallet,
      to: g.seller,
      to_is_contract: false,
      amount: String(g.price_energy),
      token: `${g.asset_name} · 能量支付`,
      gas: '210000',
      tx_hash: r?.nft_tx || `green_buy_${Date.now()}`,
      time: now,
      status: 'ok',
    })
    saveTxRecords()
    try { app.confetti({ particleCount: 100, spread: 80, origin: { y: 0.4 }, ticks: 180 }) } catch {}
    ElMessage.success(`购买成功：${g.asset_name}`)
    // 购买改变能量余额与资产归属，同步刷新
    load(true); loadGreenBalance()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '购买失败'
    ElMessage.error(msg)
  } finally {
    buyingId.value = null
  }
}

/** 下架自己挂牌的绿色资产 */
const delistGreen = async (g: any) => {
  try {
    await ElMessageBox.confirm(`确认下架「${g.asset_name}」？`, '下架资产', { type: 'warning' })
  } catch { return }
  delistingId.value = g.id
  try {
    await ecoApi.marketCancel(g.id, app.currentWallet || '0xlearner')
    ElMessage.success('已下架')
    load(true)
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '下架失败'
    ElMessage.error(msg)
  } finally {
    delistingId.value = null
  }
}

const openBuy = (n: any) => {
  cur.value = n; buy.token_id = n.token_id; buy.price = n.price; buy.buyer = app.currentWallet
  if (tokens.value.length) buy.token_contract = tokens.value[0].address
  buyDlg.value = true
}

const doBuy = async () => {
  const r: any = await nftApi.buy(buy)
  const now = new Date().toISOString().slice(0, 19).replace('T', ' ')
  txRecords.value.push({
    kind: 'NFT 购买',
    from: buy.buyer,
    to: cur.value?.author || cur.value?.owner || '0xseller',
    to_is_contract: false,
    amount: String(buy.price || ''),
    token: cur.value?.title || '未命名 NFT',
    gas: '210000',
    tx_hash: r?.tx_hash || `buy_${Date.now()}`,
    time: now,
    status: 'ok',
  })
  saveTxRecords()
  ElMessage.success('购买成功，交易已上链')
  buyDlg.value = false
  load()
}

const openDetail = async (id: string) => {
  detail.value = await nftApi.get(id)
  detailDlg.value = true
}

const loadAll = () => {
  // 支持从其他页面通过 /nft-market?tab=green 跳转
  const q = route.query.tab as string
  if (q === 'green' && filter.value !== 'green') {
    filter.value = 'green'
  }
  txRecords.value = loadTxRecords()
  load(true); loadTokens(); loadGreenBalance()
}
/* 首次进入触发 onMounted，KeepAlive 缓存后再次进入触发 onActivated，两者都执行加载 */
onMounted(loadAll)
onActivated(loadAll)
</script>

<style scoped lang="scss">
/* ---- 顶部 KPI ---- */
.kpi-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 14px; }
.kpi { padding: 12px 14px;
  .kpi-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
  .kpi-ico {
    width: 28px; height: 28px; border-radius: 7px;
    display: inline-flex; align-items: center; justify-content: center;
    color: var(--dq-primary); font-size: 14px;
    &.k-mint { background: rgba(245,55,155,0.15); color: var(--dq-accent); }
    &.k-buy  { background: rgba(77,141,255,0.15); color: var(--dq-info); }
    &.k-own  { background: rgba(255,207,77,0.15); color: var(--dq-warn); }
  }
  .kpi-num {
    font-family: var(--dq-mono); font-size: 24px; font-weight: 800;
    background: var(--dq-grad-primary);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent;
    &.accent { background: linear-gradient(135deg, #f5379b, #b8298a); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
    &.info   { background: linear-gradient(135deg, #4d8dff, #2e6bd9); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
    &.warn   { background: linear-gradient(135deg, #ffcf4d, #e6a23c); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
  }
  .kpi-sub { font-size: 11px; color: var(--dq-text-dim); margin-top: 2px; }
}
@media (max-width: 760px) {
  .kpi-row { grid-template-columns: 1fr; }
}

/* ---- 顶部学习引导（通用） ---- */
.guide-card { margin-bottom: 14px; }
.guide-head { margin-bottom: 14px; }
.guide-title { display: inline-flex; align-items: center; gap: 10px; font-size: 16px; font-weight: 700; color: var(--dq-text); }
.g-icon { font-size: 20px; }
.dq-tag-lg { font-size: 11px; padding: 3px 10px; border-radius: 4px; }

.flow {
  display: grid; grid-template-columns: 1fr 32px 1fr 32px 1fr; gap: 6px;
  align-items: stretch;
  .flow-step {
    padding: 14px 16px;
    background: linear-gradient(135deg, rgba(245,55,155,0.05), rgba(245,55,155,0.01));
    border: 1px solid var(--dq-border);
    border-radius: 8px;
    display: flex; gap: 12px; align-items: flex-start;
    transition: all .2s;
    &:hover { border-color: var(--dq-border-2); transform: translateY(-1px); }
  }
  .fs-no {
    flex-shrink: 0;
    width: 36px; height: 36px; border-radius: 8px;
    background: var(--dq-grad-info); color: #fff;
    display: inline-flex; align-items: center; justify-content: center;
    font-family: var(--dq-mono); font-weight: 700; font-size: 14px;
    box-shadow: 0 0 10px rgba(77,141,255,0.25);
    &.accent { background: var(--dq-grad-accent); box-shadow: 0 0 10px var(--dq-accent-glow); }
  }
  .fs-info { flex: 1; min-width: 0; }
  .fs-title { font-weight: 600; color: var(--dq-text); font-size: 14px; margin-bottom: 4px; }
  .fs-desc { font-size: 12px; color: var(--dq-text-dim); line-height: 1.6; margin-bottom: 6px; b { color: var(--dq-accent); font-weight: 500; } }
  .fs-tags { display: flex; gap: 4px; flex-wrap: wrap; }
  .fs-kw {
    font-family: var(--dq-mono);
    font-size: 10px; color: var(--dq-info);
    background: rgba(77,141,255,0.1);
    padding: 1px 6px; border-radius: 3px;
    border: 1px solid rgba(77,141,255,0.22);
    &.accent { color: var(--dq-accent); background: rgba(245,55,155,0.08); border-color: rgba(245,55,155,0.22); }
    &.muted  { color: var(--dq-text-dim); background: rgba(123,138,171,0.1); border-color: rgba(123,138,171,0.2); }
  }
  .flow-arrow {
    display: flex; align-items: center; justify-content: center;
    color: var(--dq-border-strong); font-size: 18px; font-weight: 700;
  }
}
@media (max-width: 1180px) {
  .flow { grid-template-columns: 1fr;
    .flow-arrow { transform: rotate(90deg); height: 20px; }
  }
}

.toolbar { margin-bottom: 14px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 14px; }
.nft-card { padding: 10px; }
.thumb { position: relative; aspect-ratio: 1; border-radius: 6px; overflow: hidden; background: var(--dq-bg-2); cursor: pointer; display:flex; align-items:center; justify-content:center;
  img { width: 100%; height: 100%; object-fit: cover; }
  .placeholder { color: var(--dq-text-dim); font-size: 40px; }
  .std { position: absolute; top: 8px; right: 8px; }
}
.info { padding-top: 10px; .title { font-weight: 600; color: var(--dq-text); } .author { font-size: 12px; color: var(--dq-text-dim); margin: 4px 0; } .price { font-family: var(--dq-mono); color: var(--dq-primary); font-weight: 700; .unit { font-size: 12px; color: var(--dq-text-dim); } } .ops { margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap; } }

/* ---- 绿色资产卡片 ---- */
.green-grid { grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); }
.green-card {
  padding: 14px;
  border: 1px solid rgba(0,230,195,0.25) !important;
  background: linear-gradient(135deg, rgba(0,230,195,0.04), rgba(0,230,195,0.01)) !important;
  transition: all .2s;
  &:hover {
    border-color: rgba(0,230,195,0.5) !important;
    transform: translateY(-2px);
    box-shadow: 0 4px 16px rgba(0,230,195,0.12);
  }
}
.g-thumb {
  position: relative;
  aspect-ratio: 16/9;
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(0,230,195,0.12), rgba(45,212,191,0.04));
  display: flex; align-items: center; justify-content: center;
  margin-bottom: 10px;
  .g-icon-lg { font-size: 48px; }
  .dq-tag { position: absolute; top: 8px; right: 8px; }
}
.green-price {
  color: var(--dq-primary) !important;
  font-size: 16px !important;
  .unit { color: var(--dq-primary); opacity: 0.7; }
}
.g-meta {
  display: flex; gap: 6px; align-items: center;
  margin: 6px 0 8px;
  font-size: 11px;
}
.green-empty { grid-column: 1 / -1; }
.preview { margin-top: 8px; img { width: 100px; height: 100px; object-fit: cover; border-radius: 4px; } }
.buy-info { padding: 10px; background: var(--dq-bg-2); border-radius: 6px; }
.tip { color: var(--dq-text-dim); font-size: 12px; margin-top: 8px; }
.detail { .d-thumb { width: 100%; aspect-ratio: 1; border-radius: 6px; overflow: hidden; margin-bottom: 14px; background: var(--dq-bg-2); display:flex; align-items:center; justify-content:center; img { width:100%; height:100%; object-fit: cover; } .placeholder { font-size: 60px; color: var(--dq-text-dim); } } .d-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px dashed var(--dq-border); font-size: 13px; span:first-child { color: var(--dq-text-dim); } } }
.dim { color: var(--dq-text-dim); }
</style>
