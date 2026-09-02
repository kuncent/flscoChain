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
            <div class="fs-title">两类铸造入口</div>
            <div class="fs-desc">🌿 绿色资产：在「绿色低碳联盟链」页面能量兑换 / 联盟角色铸造发放；🖼️ 数字 NFT：本页右上「铸造数字 NFT」（真实编译部署原始 ERC721/1155 合约，铸造者须先选联盟角色）</div>
            <div class="fs-tags"><span class="fs-kw">绿色资产兑换</span><span class="fs-kw accent">数字 NFT 铸造</span><span class="fs-kw">需联盟角色</span></div>
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
            <div class="fs-desc">两个市场统一以绿色能量结算：GreenEnergy 转账(买家→卖家) + NFT transferFrom(卖家→买家)，<b>资产自由流通</b></div>
            <div class="fs-tags"><span class="fs-kw">能量支付</span><span class="fs-kw accent">transferFrom</span><span class="fs-kw">safeTransferFrom</span></div>
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
        <div class="kpi-sub">{{ filter === 'green' ? '在售绿色资产' : '在售数字 NFT' }}</div>
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
        <div style="margin-left:auto; display:flex; align-items:center; gap:10px">
          <span class="dq-tip" style="font-weight:400" v-if="filter === 'nft'">
            本页含两个独立市场：🌿 绿色资产在「绿色低碳联盟链」兑换铸造，🖼️ 数字 NFT 由学生本页铸造，均以绿色能量计价结算
          </span>
          <el-button v-if="filter === 'green'" size="small" type="success" @click="$router.push('/eco')">前往绿色实战兑换</el-button>
          <el-button size="small" type="primary" @click="openMint">✨ 铸造数字 NFT</el-button>
        </div>
      </div>
      <div class="filter-bar">
        <!-- 一级选项卡：两个独立资产池（绿色资产池 / 数字 NFT 池），默认业务主线 -->
        <el-radio-group v-model="filter" @change="load">
          <el-radio-button label="green">🌿 绿色资产</el-radio-button>
          <el-radio-button label="nft">🖼️ 数字 NFT</el-radio-button>
        </el-radio-group>
        <!-- 二级筛选：轻量下拉，数据已全量加载，纯本地过滤不发请求 -->
        <el-select v-if="filter === 'green'" v-model="greenTypeFilter" size="small" style="width: 150px">
          <el-option label="全部类型" value="" />
          <el-option label="🌱 植树证书" value="certificate" />
          <el-option label="🏅 生态勋章" value="badge" />
          <el-option label="🎫 骑行券" value="voucher" />
        </el-select>
        <el-select v-else v-model="nftStandardFilter" size="small" style="width: 180px">
          <el-option label="全部协议" value="" />
          <el-option label="ERC721 · 独一无二" value="ERC721" />
          <el-option label="ERC1155 · 多份发行" value="ERC1155" />
        </el-select>
      </div>
    </div>

    <!-- 数字 NFT 列表（协议二级筛选为本地过滤） -->
    <div class="grid" v-if="filter === 'nft' && nftFiltered.length" v-loading="loading">
      <div class="dq-card nft-card" v-for="n in nftFiltered" :key="n.token_id">
        <div class="thumb" @click="openDetail(n.token_id)">
          <img v-if="n.image_url" :src="n.image_url" />
          <div v-else class="placeholder"><el-icon><Picture /></el-icon></div>
          <span class="dq-tag accent std">{{ n.standard }}</span>
        </div>
        <div class="info">
          <div class="title">
            {{ n.title || '未命名 NFT' }}
            <span v-if="Number(n.amount || 1) > 1" class="dq-tag warn amount-tag">×{{ n.amount }} 份</span>
          </div>
          <div class="author dq-mono">持有者: {{ short(n.owner || n.author) }}</div>
          <div class="price">{{ n.price || '0' }} <span class="unit">⚡ 能量</span></div>
          <div class="ops">
            <el-button size="small" @click="openDetail(n.token_id)">详情</el-button>
            <el-button
              size="small"
              type="primary"
              :disabled="isSelfHeld(n) || Number(n.price || 0) > greenBalance"
              @click="openBuy(n)"
            >
              {{ isSelfHeld(n) ? '我持有' : Number(n.price || 0) > greenBalance ? `需 ${n.price} 能量` : '购买' }}
            </el-button>
            <a v-if="n.image_url" :href="n.image_url" download target="_blank">
              <el-button size="small">下载</el-button>
            </a>
          </div>
        </div>
      </div>
    </div>

    <!-- 绿色资产列表（随业务类型子筛选联动） -->
    <div class="grid green-grid" v-if="filter === 'green'" v-loading="loading">
      <div class="dq-card green-card" v-for="g in greenFiltered" :key="g.id">
        <div class="g-thumb">
          <img v-if="g.image_url" class="g-img" :src="g.image_url" :alt="g.asset_name" @error="g.image_url = ''" />
          <div v-else class="g-icon-lg">{{ greenAssetIcon(g.asset_type) }}</div>
          <span class="dq-tag" :class="g.asset_type === 'certificate' ? 'accent' : 'warn'">
            {{ greenAssetTypeLabel(g.asset_type) }}
          </span>
        </div>
        <div class="info">
          <div class="title">
            {{ g.asset_name }}
            <span v-if="isMine(g)" class="dq-tag info mine-tag">我挂牌</span>
          </div>
          <div class="author dq-mono">卖家: {{ short(g.seller) }}</div>
          <div class="price green-price">
            {{ g.price_energy }} <span class="unit">⚡ 能量</span>
          </div>
          <div class="g-meta">
            <span class="dq-tag muted">{{ g.standard }}</span>
            <span class="dq-mono dim">ID: {{ g.token_id }}</span>
            <span class="dq-mono dim g-time">{{ formatTime(g.created_at) }}</span>
          </div>
          <div class="ops">
            <el-button
              v-if="!isMine(g)"
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
      <div v-if="greenLoaded && !greenFiltered.length && !loading" class="green-empty">
        <EmptyIllustration
          type="nft"
          :title="greenTypeFilter ? `暂无该类型绿色资产在售` : '暂无绿色资产在售'"
          subtitle="前往「绿色低碳联盟链」兑换资产后可挂牌出售"
        />
      </div>
    </div>

    <div v-if="filter === 'nft' && !nftFiltered.length" style="margin-top:14px">
      <EmptyIllustration
        v-if="nftLoaded && !loading"
        type="nft"
        :title="nftStandardFilter ? `暂无 ${nftStandardFilter} 数字 NFT 在售` : '暂无数字 NFT 在售'"
        subtitle="点右上「铸造数字 NFT」铸造自己的作品，选 ERC1155 可一次发行多份"
      />
    </div>

    <!-- 购买对话框（绿色能量统一结算，买家 = 当前钱包，后端从 JWT 解析） -->
    <el-dialog v-model="buyDlg" title="购买数字 NFT（绿色能量支付）" width="460px">
      <div class="buy-info" v-if="cur">
        <div>{{ cur.title }} <span class="dq-tag accent">{{ cur.standard }}</span></div>
        <div>价格: {{ buy.price }} ⚡ 绿色能量</div>
        <div>持有者（卖家）: <span class="dq-mono">{{ short(cur.owner || cur.author) }}</span></div>
      </div>
      <div class="dq-tip" style="margin-top:10px">
        <span class="dt-label">说明:</span>支付货币统一为绿色能量（GreenEnergy ERC20）：执行「能量转账(买家→卖家) + NFT 转移(卖家→买家)」两笔交易。
        能量来自业务角色凭证发放（见「绿色低碳联盟链」）；当前钱包余额 {{ greenBalance }} ⚡。
      </div>
      <template #footer>
        <el-button @click="buyDlg = false">取消</el-button>
        <el-button type="primary" :disabled="Number(buy.price || 0) > greenBalance" @click="doBuy">确认购买</el-button>
      </template>
    </el-dialog>

    <!-- 铸造数字 NFT 对话框：协议特性差异是核心教学点（真实编译部署 + mint，对应后端 /api/nft/mint） -->
    <el-dialog v-model="mintDlg" title="铸造数字 NFT（原始 ERC721 / ERC1155）" width="560px">
      <div class="dq-tip" style="margin-bottom:10px">
        <span class="dt-label">说明:</span>系统会真实编译部署所选协议的原始合约并调用 mint，以绿色能量计价；
        铸造者（当前钱包）须先在「绿色低碳联盟链」选择联盟角色身份。
      </div>
      <!-- 协议特性选择卡：两种标准的核心差异一目了然 -->
      <div class="std-cards">
        <div class="std-card" :class="{ active: mintForm.standard === 'ERC721' }" @click="mintForm.standard = 'ERC721'">
          <div class="sc-head">ERC721 <span class="dq-tag accent">非同质化</span></div>
          <div class="sc-desc">每个 token 独一无二、不可拆分，数量恒为 1；以 ownerOf 确权、transferFrom 逐个转移</div>
          <div class="sc-traits">
            <span class="sc-kw accent">独一无二</span>
            <span class="sc-kw">ownerOf</span>
            <span class="sc-kw">适合孤品作品</span>
          </div>
        </div>
        <div class="std-card" :class="{ active: mintForm.standard === 'ERC1155' }" @click="mintForm.standard = 'ERC1155'">
          <div class="sc-head">ERC1155 <span class="dq-tag info">多代币标准</span></div>
          <div class="sc-desc">半同质化：同一 ID 可一次铸造多份，支持 mintBatch / 批量转移，多份流通更省 gas</div>
          <div class="sc-traits">
            <span class="sc-kw accent">多份发行</span>
            <span class="sc-kw">批量转移</span>
            <span class="sc-kw">适合限量卡 / 徽章</span>
          </div>
        </div>
      </div>
      <el-form label-width="90px" style="margin-top:12px">
        <el-form-item label="作品名称">
          <el-input v-model="mintForm.title" placeholder="如：绿色城市 · 数字海报" />
        </el-form-item>
        <el-form-item v-if="mintForm.standard === 'ERC1155'" label="发行数量">
          <el-input-number v-model="mintForm.amount" :min="1" :max="10000" :step="10" />
          <span class="dq-tip" style="margin-left:8px">同一作品一次铸造多份（半同质化特性；ERC721 恒为 1）</span>
        </el-form-item>
        <el-form-item label="作品描述">
          <el-input v-model="mintForm.description" type="textarea" :rows="2" placeholder="选填" />
        </el-form-item>
        <el-form-item label="图片地址">
          <el-input v-model="mintForm.image_url" placeholder="https://...（选填，留空使用默认占位）" />
        </el-form-item>
        <el-form-item label="初始价格">
          <el-input-number v-model="mintForm.price" :min="0" :step="10" />
          <span class="dq-tip" style="margin-left:8px">⚡ 绿色能量计价，买家以能量余额支付</span>
        </el-form-item>
        <div class="dq-tip">
          <span class="dt-label">注:</span>铸造者 = 当前钱包（{{ short(app.currentWallet) }}），铸造后可在本页定价交易。
        </div>
      </el-form>
      <template #footer>
        <el-button @click="mintDlg = false">取消</el-button>
        <el-button type="primary" :loading="minting" @click="doMint">确认铸造</el-button>
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
        <div class="d-row">
          <span>发行数量</span>
          <span>{{ detail.amount || 1 }} {{ detail.standard === 'ERC721' ? '（独一无二）' : '（半同质化，同 ID 多份）' }}</span>
        </div>
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

    <!-- TxTimeline：NFT 铸造 / 购买 交易流水（后端权威成交记录 + 铸造 + 本地降级流水） -->
    <div class="dq-card" style="margin-top:14px" v-if="timelineList.length">
      <TxTimeline
        :list="timelineList"
        :title="`NFT 交易记录 · 铸造/购买 共 ${timelineList.length} 笔`"
      />
    </div>
    <div v-else-if="nftLoaded && tradesLoaded && !loading" style="margin-top:14px">
      <EmptyIllustration
        type="nft"
        title="暂无 NFT 交易"
        subtitle="铸造或购买 NFT 后，交易流水会显示在这里"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onActivated, onMounted, reactive, computed, watch } from 'vue'
import { nftApi, ecoApi } from '@/api'
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
/** 市场一级选项卡：green = 绿色资产池（业务主线，默认） / nft = 数字 NFT 池 */
const filter = ref('green')
/** 绿色资产业务类型子筛选（'' = 全部；certificate / badge / voucher，纯本地过滤） */
const greenTypeFilter = ref('')
/** 数字 NFT 协议子筛选（'' = 全部；ERC721 / ERC1155，纯本地过滤） */
const nftStandardFilter = ref('')
const txRecords = ref<any[]>([])  // 本地持久化的交易流水
const buyingId = ref<number | null>(null)
const delistingId = ref<number | null>(null)
const greenBalance = ref(0)  // 当前钱包绿色能量余额（用于购买按钮可用性判断）
/** 两个数据源首次加载完成标记：静默加载时 loading 恒为 false，
 * 必须用它门禁空提示，否则「暂无」插画会在数据返回前闪现 */
const greenLoaded = ref(false)
const nftLoaded = ref(false)
/** 后端权威成交记录（绿色资产市场已售 + 数字 NFT trades）：跨钱包/浏览器可见，
 * 是交易时间线的主数据源（不再依赖仅记录本浏览器操作的 localStorage） */
const serverTrades = ref<any[]>([])
const tradesLoaded = ref(false)
const loadServerTrades = async () => {
  try {
    const [ecoR, nftR]: any[] = await Promise.all([
      ecoApi.marketTrades().catch(() => ({ items: [] })),
      nftApi.tradesAll().catch(() => ({ items: [] })),
    ])
    serverTrades.value = [...(ecoR?.items || []), ...(nftR?.items || [])]
  } catch { serverTrades.value = [] } finally { tradesLoaded.value = true }
}

// v2：服务端已清理测试脏数据，升级存储键使浏览器端旧本地流水缓存自动失效
const NFT_TX_KEY = 'learn_nft_tx_v2'
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
const buy = reactive({ token_id: '', buyer: app.currentWallet, price: '' })

const detailDlg = ref(false)
const detail = ref<any>(null)

const short = (h: string) => h ? h.slice(0, 10) + '...' + h.slice(-4) : '-'

/** 累计成交：以时间线中的购买类记录计数（含后端权威成交，不依赖本地缓存） */
const totalTrades = computed(() => timelineList.value.filter(x => /购买|Buy/i.test(x.kind)).length)
/** 大小写不敏感的「是否我的挂牌」判断（钱包地址大小写可能不一致，严格比较会导致购买/下架按钮错位） */
const isMine = (g: any) =>
  String(g.seller || '').toLowerCase() === String(app.currentWallet || '').toLowerCase()
/** 数字 NFT 是否当前钱包持有（持有者无需重复购买，按钮置灰） */
const isSelfHeld = (n: any) =>
  String(n.owner || n.author || '').toLowerCase() === String(app.currentWallet || '').toLowerCase()
const myOwned = computed(() => {
  const me = String(app.currentWallet || '').toLowerCase()
  const nftOwned = list.value.filter(n => String(n.owner || '').toLowerCase() === me).length
  const greenOwned = greenList.value.filter(isMine).length
  return nftOwned + greenOwned
})
/** 挂牌时间精简展示（去掉年份与秒，如 08-06 10:59） */
const formatTime = (t?: string) => (t ? t.slice(5, 16) : '')

/** 绿色资产按业务类型子筛选后的在售列表（数据源已含全部在售项，不发额外请求） */
const greenFiltered = computed(() =>
  greenTypeFilter.value
    ? greenList.value.filter((g) => g.asset_type === greenTypeFilter.value)
    : greenList.value,
)
/** 数字 NFT 按协议子筛选（全量加载一次，切换筛选与时间线共用数据，不发额外请求） */
const nftFiltered = computed(() =>
  nftStandardFilter.value
    ? list.value.filter((n) => n.standard === nftStandardFilter.value)
    : list.value,
)

/** 用于 KPI 显示总数（随一级 + 二级筛选联动） */
const displayList = computed(() => filter.value === 'green' ? greenFiltered.value : nftFiltered.value)

/* ==================== 绿色资产元数据 ==================== */
const greenAssetIcon = (t: string) =>
  ({ certificate: '🌱', badge: '🏅', voucher: '🎫' }[t] || '🌿')
const greenAssetTypeLabel = (t: string) =>
  ({ certificate: '植树证书', badge: '生态勋章', voucher: '骑行券' }[t] || t)

/* 将 NFT list + 后端成交记录 + 本地流水 映射成 TxTimeline */
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
  // 2) 后端权威成交记录：绿色资产市场已售（带 asset_type）+ 数字 NFT trades（带 from_addr）
  const seenTx = new Set<string>()
  for (const t of serverTrades.value) {
    const isGreen = t.asset_type != null
    out.push({
      kind: isGreen ? '绿色资产购买' : '数字 NFT 购买',
      from: isGreen ? t.seller : t.from_addr,
      to: isGreen ? t.buyer : t.to_addr,
      to_is_contract: false,
      amount: String(isGreen ? t.price_energy : (t.price || '')),
      token: isGreen ? `${t.asset_name} · 能量支付` : `NFT #${t.token_id} · 能量支付`,
      gas: '210000',
      tx_hash: t.tx_hash || `trade_${t.id}_${t.created_at}`,
      time: t.created_at || '-',
      status: 'ok',
    })
    if (t.tx_hash) seenTx.add(String(t.tx_hash))
  }
  // 3) 本地流水仅作即时反馈/降级：与后端重复的按 tx_hash 去重（后端已含同一笔交易）
  for (const t of txRecords.value) {
    if (t.tx_hash && seenTx.has(String(t.tx_hash))) continue
    out.push({ ...t })
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
      // 加载绿色资产市场在售列表（含失败也视为加载完成，避免空提示被永久门禁）
      try {
        const r: any = await ecoApi.marketItems()
        greenList.value = r?.items || []
      } finally {
        greenLoaded.value = true
      }
    } else {
      // 数字 NFT 池全量加载（协议筛选为本地过滤，交易时间线也以此为数据源）
      try {
        list.value = ((await nftApi.list('')) as any).items
      } finally {
        nftLoaded.value = true
      }
    }
  } finally { if (!silent) loading.value = false }
}

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
    // 购买改变能量余额与资产归属，同步刷新（含后端成交记录）
    load(true); loadGreenBalance(); loadServerTrades()
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
  buyDlg.value = true
}

/* ==================== 铸造数字 NFT（原始 ERC721/1155，补齐供给侧入口） ==================== */
const mintDlg = ref(false)
const minting = ref(false)
const mintForm = reactive({ standard: 'ERC721', title: '', description: '', image_url: '', price: 0, amount: 1 })

const openMint = () => { mintDlg.value = true }

/** 铸造：后端真实编译部署对应标准原始合约 + mint（须已选联盟角色，后端 403 提示透传）。
 * ERC1155 按 amount 多份铸造（半同质化特性）；成功后自动切到「数字 NFT」并刷新 */
const doMint = async () => {
  if (!mintForm.title.trim()) {
    ElMessage.warning('请输入作品名称')
    return
  }
  minting.value = true
  try {
    const amount = mintForm.standard === 'ERC1155' ? mintForm.amount : 1
    const r: any = await nftApi.mint({
      standard: mintForm.standard,
      title: mintForm.title.trim(),
      description: mintForm.description,
      image_url: mintForm.image_url || null,
      author: app.currentWallet || '0xlearner',
      price: String(mintForm.price || 0),
      amount,
    })
    try { app.confetti({ particleCount: 80, spread: 70, origin: { y: 0.4 }, ticks: 150 }) } catch {}
    ElMessage.success(`铸造成功：${mintForm.standard}${amount > 1 ? ` × ${amount} 份` : ''} · Token ID ${r?.token_id ?? '-'}`)
    mintDlg.value = false
    mintForm.title = ''; mintForm.description = ''; mintForm.image_url = ''; mintForm.price = 0; mintForm.amount = 1
    // 切到数字 NFT 视图展示铸造结果（nft_mint 指标由 nfts 表 author 归属自动计数）
    filter.value = 'nft'
    nftStandardFilter.value = ''
    await load()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '铸造失败'
    ElMessage.error(msg)
  } finally {
    minting.value = false
  }
}

const doBuy = async () => {
  const r: any = await nftApi.buy(buy)
  const now = new Date().toISOString().slice(0, 19).replace('T', ' ')
  txRecords.value.push({
    kind: '数字 NFT 购买',
    from: buy.buyer,
    to: cur.value?.owner || cur.value?.author || '0xseller',
    to_is_contract: false,
    amount: String(buy.price || ''),
    token: `${cur.value?.title || '未命名 NFT'} · 能量支付`,
    gas: '210000',
    tx_hash: r?.tx_hash || `buy_${Date.now()}`,
    time: now,
    status: 'ok',
  })
  saveTxRecords()
  ElMessage.success('购买成功，能量支付与 NFT 转移均已上链')
  buyDlg.value = false
  load(); loadGreenBalance(); loadServerTrades()
}

const openDetail = async (id: string) => {
  detail.value = await nftApi.get(id)
  detailDlg.value = true
}

const loadAll = () => {
  // 支持从其他页面通过 /nft?tab=nft 跳转（默认即绿色资产）
  const q = route.query.tab as string
  if (q === 'nft') {
    filter.value = 'nft'
  }
  txRecords.value = loadTxRecords()
  load(true); loadGreenBalance(); loadServerTrades()
  // 交易时间线需要数字 NFT 铸造记录作为数据源：当前选项卡为绿色资产时额外懒加载一次（静默）
  if (filter.value === 'green' && !list.value.length) {
    nftApi.list('')
      .then((r: any) => { list.value = r?.items || [] })
      .catch(() => { /* 时间线降级：仅展示购买流水 */ })
      .finally(() => { nftLoaded.value = true })
  }
}
/* 首次进入触发 onMounted，KeepAlive 缓存后再次进入触发 onActivated，两者都执行加载 */
onMounted(loadAll)
onActivated(loadAll)

// 钱包切换时刷新市场列表与持仓（角色/钱包联动）
watch(() => app.currentWallet, () => {
  buy.buyer = app.currentWallet
  loadAll()
})
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
/* ---- 筛选栏：一级选项卡 + 二级轻量下拉 ---- */
.filter-bar { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
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
  overflow: hidden;
  background: linear-gradient(135deg, rgba(0,230,195,0.12), rgba(45,212,191,0.04));
  display: flex; align-items: center; justify-content: center;
  margin-bottom: 10px;
  .g-img { width: 100%; height: 100%; object-fit: cover; }
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
  .g-time { margin-left: auto; }
}
.mine-tag { margin-left: 6px; vertical-align: 1px; }
.amount-tag { margin-left: 6px; vertical-align: 1px; }
.green-empty { grid-column: 1 / -1; }
.preview { margin-top: 8px; img { width: 100px; height: 100px; object-fit: cover; border-radius: 4px; } }
.buy-info { padding: 10px; background: var(--dq-bg-2); border-radius: 6px; }
/* ---- 铸造对话框：协议特性选择卡 ---- */
.std-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.std-card {
  padding: 12px 14px; border: 1px solid var(--dq-border); border-radius: 8px;
  background: var(--dq-bg-2); cursor: pointer; transition: all .2s;
  &:hover { border-color: var(--dq-border-2); transform: translateY(-1px); }
  &.active {
    border-color: var(--dq-accent);
    background: linear-gradient(135deg, rgba(245,55,155,0.08), rgba(245,55,155,0.02));
    box-shadow: 0 0 0 1px var(--dq-accent) inset;
  }
  .sc-head { font-family: var(--dq-mono); font-weight: 700; font-size: 14px; color: var(--dq-text); display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
  .sc-desc { font-size: 12px; color: var(--dq-text-dim); line-height: 1.6; margin-bottom: 8px; }
  .sc-traits { display: flex; gap: 4px; flex-wrap: wrap; }
  .sc-kw {
    font-family: var(--dq-mono); font-size: 10px; color: var(--dq-info);
    background: rgba(77,141,255,0.1); padding: 1px 6px; border-radius: 3px;
    border: 1px solid rgba(77,141,255,0.22);
    &.accent { color: var(--dq-accent); background: rgba(245,55,155,0.08); border-color: rgba(245,55,155,0.22); }
  }
}
@media (max-width: 560px) { .std-cards { grid-template-columns: 1fr; } }
.tip { color: var(--dq-text-dim); font-size: 12px; margin-top: 8px; }
.detail { .d-thumb { width: 100%; aspect-ratio: 1; border-radius: 6px; overflow: hidden; margin-bottom: 14px; background: var(--dq-bg-2); display:flex; align-items:center; justify-content:center; img { width:100%; height:100%; object-fit: cover; } .placeholder { font-size: 60px; color: var(--dq-text-dim); } } .d-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px dashed var(--dq-border); font-size: 13px; span:first-child { color: var(--dq-text-dim); } } }
.dim { color: var(--dq-text-dim); }
</style>
