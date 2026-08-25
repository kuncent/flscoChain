<template>
  <div class="wallet dq-enter-up">
    <!-- 学习引导 -->
    <div class="dq-flow-card guide-card"><div class="dq-flow-card__inner">
      <div class="guide-head">
        <div class="guide-title">
          <span class="g-icon">💳</span>
          ERC20 钱包实训
          <span class="dq-tag info dq-tag-lg">第 8 步 · 综合实战</span>
          <span class="dq-live" style="margin-left:6px"><span class="dot"></span>真实链上执行</span>
        </div>
      </div>
      <div class="flow">
        <div class="flow-step">
          <div class="fs-no">01</div>
          <div class="fs-info">
            <div class="fs-title">发行 Token</div>
            <div class="fs-desc">在真实链上部署 ERC20 合约，构造函数将总量铸造到你的 owner 地址</div>
            <div class="fs-tags"><span class="fs-kw">deploy</span><span class="fs-kw">constructor</span><span class="fs-kw">SSTORE</span></div>
          </div>
        </div>
        <div class="flow-arrow">→</div>
        <div class="flow-step">
          <div class="fs-no">02</div>
          <div class="fs-info">
            <div class="fs-title">查询余额</div>
            <div class="fs-desc">调用 balanceOf 这个 view 函数，<b>本地 EVM 执行</b>、不发交易、不消耗 Gas</div>
            <div class="fs-tags"><span class="fs-kw muted">eth_call</span><span class="fs-kw muted">view / pure</span></div>
          </div>
        </div>
        <div class="flow-arrow">→</div>
        <div class="flow-step">
          <div class="fs-no">03</div>
          <div class="fs-info">
            <div class="fs-title">Token 转账</div>
            <div class="fs-desc">调用 transfer 发送交易，EVM 修改存储、触发 Transfer 事件，写入区块</div>
            <div class="fs-tags"><span class="fs-kw">sendTx</span><span class="fs-kw">Transfer 事件</span><span class="fs-kw">topic0=ddf252ad</span></div>
          </div>
        </div>
      </div>
    </div></div>

    <!-- 顶部三卡：玻璃拟态 KPI -->
    <div class="kpi-row" v-if="true">
      <div class="dq-glass kpi">
        <div class="kpi-top">
          <div class="kpi-ico k-t"><el-icon><Coin /></el-icon></div>
          <span class="dq-tag info">已发行 Token</span>
        </div>
        <CountUp :target="tokens.length" class="kpi-num info" />
        <div class="kpi-sub">ERC20 合约部署数</div>
      </div>
      <div class="dq-glass kpi">
        <div class="kpi-top">
          <div class="kpi-ico k-b"><el-icon><Wallet /></el-icon></div>
          <span class="dq-tag">钱包余额种类</span>
        </div>
        <CountUp :target="balances.length" class="kpi-num" />
        <div class="kpi-sub">可在下方余额列表查看</div>
      </div>
      <div class="dq-glass kpi">
        <div class="kpi-top">
          <div class="kpi-ico k-tx"><el-icon><Document /></el-icon></div>
          <span class="dq-tag warn">累计转账</span>
        </div>
        <CountUp :target="transfers.length" class="kpi-num warn" />
        <div class="kpi-sub">真实链 ERC20 Transfer 事件</div>
      </div>
    </div>

    <div class="grid" style="margin-top:14px">
      <!-- 钱包信息 -->
      <div class="dq-card">
        <div class="dq-card-title">我的钱包 <span class="dq-live" style="margin-left:auto"><span class="dot"></span>真实链</span></div>
        <el-form label-width="80px" size="small">
          <el-form-item label="地址">
            <el-input v-model="wallet" @change="setWallet" />
          </el-form-item>
        </el-form>
        <div class="bal-list">
          <div class="bal-item" v-for="b in balances" :key="b.token_address">
            <div class="b-left">
              <div class="b-name">
                <span v-if="isGreenEnergy(b)" style="margin-right:4px">⚡</span>{{ b.name }}
                <span class="dq-mono dim">({{ b.symbol }})</span>
                <span v-if="isGreenEnergy(b)" class="dq-tag accent" style="margin-left:6px">绿色能量</span>
              </div>
              <div class="dq-mono dim addr">{{ short(b.token_address) }}</div>
            </div>
            <div class="b-right">
              <div class="b-val dq-mono">{{ b.balance }}</div>
            </div>
          </div>
        </div>
        <EmptyIllustration v-if="!balances.length" type="wallet" :hide-text="true" />
        <el-button size="small" @click="loadBalances" style="margin-top:6px">
          <el-icon><Refresh /></el-icon> 刷新余额
        </el-button>
      </div>

      <!-- 发行 Token -->
      <div class="dq-card">
        <div class="dq-card-title">发行 ERC20 Token</div>
        <el-alert
          v-if="!isAdminWallet"
          type="warning"
          :closable="false"
          show-icon
          style="margin-bottom: 10px"
          title="发行权限仅限联盟管理员钱包（0xadmin）"
          description="当前钱包不是管理员，请先点击右上角「当前操作钱包」切换为 0xadmin 后再发行"
        />
        <el-form label-width="90px" size="small">
          <el-form-item label="名称"><el-input v-model="issue.name" placeholder="如 LearnToken" /></el-form-item>
          <el-form-item label="符号"><el-input v-model="issue.symbol" placeholder="如 LTK" /></el-form-item>
          <el-form-item label="精度"><el-input-number v-model="issue.decimals" :min="0" :max="18" /></el-form-item>
          <el-form-item label="发行量"><el-input v-model="issue.total_supply" placeholder="如 1000000" /></el-form-item>
          <el-form-item>
            <el-button type="primary" :disabled="!isAdminWallet" @click="doIssue">
              <el-icon><UploadFilled /></el-icon> 真实发行
            </el-button>
          </el-form-item>
        </el-form>
        <div class="dq-tip">
          <span class="dt-label">说明:</span>点击发行会在真实链部署 ERC20 合约，构造函数将发行量铸造到你的地址。
          所有学生共享同一条联盟链<i>公共账本</i>：任何学生发行的代币对全员可见、可查询、可转账，
          发行的合约源码会自动登记到「智能合约 IDE」工程，与监听器数据保持一致。
        </div>
      </div>

      <!-- 转账 -->
      <div class="dq-card">
        <div class="dq-card-title">Token 转账</div>
        <el-form label-width="90px" size="small">
          <el-form-item label="Token">
            <el-select v-model="transfer.token_address" style="width:100%" placeholder="选择要转账的 Token">
              <el-option v-for="t in tokens" :key="t.address" :label="`${t.name} (${t.symbol})`" :value="t.address" />
            </el-select>
          </el-form-item>
          <el-form-item label="From"><el-input v-model="transfer.from_addr" /></el-form-item>
          <el-form-item label="To"><el-input v-model="transfer.to_addr" placeholder="0x..." /></el-form-item>
          <el-form-item label="金额"><el-input v-model="transfer.amount" /></el-form-item>
          <el-form-item>
            <el-button type="primary" @click="doTransfer">
              <el-icon><Promotion /></el-icon> 真实转账
            </el-button>
          </el-form-item>
        </el-form>
        <div class="dq-tip"><span class="dt-label">说明:</span>转账调用 transfer 函数，消耗 Gas，触发 Transfer 事件，可在浏览器查看。</div>
      </div>
    </div>

    <!-- 绿色能量钱包 + 绿色资产（业务闭环） -->
    <div class="eco-row" style="margin-top:14px">
      <!-- 绿色能量钱包 -->
      <div class="dq-card">
        <div class="dq-card-title">
          ⚡ 绿色能量钱包
          <span class="dq-live" style="margin-left:auto"><span class="dot"></span>GreenEnergy ERC20</span>
        </div>
        <div class="ge-balance dq-glass">
          <div class="ge-num">{{ greenEnergyBalance }}</div>
          <div class="ge-sub">绿色能量余额（链上真实查询）</div>
        </div>
        <div class="ge-hint dq-tip">
          <span class="dt-label">获取能量:</span>
          选择联盟业务角色并提交真实业务凭证（地铁 ≥10km / 公交 ≥5min / 骑行 ≥2km / 无需餐具 / 回收 ≥1kg），
          校验通过后绿色能量直接发放到当前钱包，余额实时更新。
        </div>
        <div class="ge-ops">
          <el-button type="primary" @click="openEnergyDlg">
            ⚡ 提交凭证获取能量
          </el-button>
          <el-button @click="$router.push('/eco')">🌿 前往绿色低碳联盟链</el-button>
        </div>
      </div>

      <!-- 我的绿色资产 -->
      <div class="dq-card">
        <div class="dq-card-title">
          🌱 我的绿色资产
          <span class="dq-tag accent" style="margin-left:auto">{{ ecoAssets.length }} 项</span>
        </div>
        <div class="eco-assets" v-if="ecoAssets.length">
          <div class="eco-asset" v-for="a in ecoAssets" :key="a.key">
            <div class="ea-left">
              <span class="ea-icon">{{ a.icon }}</span>
              <div>
                <div class="ea-name">{{ a.name }}</div>
                <div class="dq-mono dim ea-id">{{ a.idText }}</div>
              </div>
            </div>
            <div class="ea-right">
              <span v-if="a.listed" class="dq-tag info">📍 在售中</span>
              <template v-else>
                <span class="dq-tag" :class="a.standard === 'ERC721' ? 'accent' : 'warn'">{{ a.standard }}</span>
                <el-button size="small" type="primary" plain :loading="listingKey === a.key" @click="openListDlg(a)">
                  挂牌
                </el-button>
              </template>
            </div>
          </div>
        </div>
        <div v-else class="empty-tip">
          暂无绿色资产。在「绿色低碳联盟链」消耗能量兑换植树证书 / 勋章 / 骑行券后将在此展示，
          并可挂牌到绿色资产市场流通。
        </div>
      </div>
    </div>

    <!-- 绿色资产挂牌对话框 -->
    <el-dialog v-model="ecoListDlg" title="挂牌出售绿色资产" width="440px">
      <div class="li-row" v-if="ecoCurAsset">
        <span>资产名称</span><b>{{ ecoCurAsset.name }}</b>
      </div>
      <el-form label-width="90px" style="margin-top: 10px">
        <el-form-item label="挂牌价格">
          <el-input-number v-model="ecoListPrice" :min="1" :step="10" style="width: 100%" />
          <div class="dq-tip" style="margin-top: 4px">
            <span class="dt-label">说明:</span>以绿色能量计价，其他居民购买时自动执行 ERC20 转账 + NFT 转移。
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="ecoListDlg = false">取消</el-button>
        <el-button type="primary" :loading="ecoListing" @click="doEcoList">确认挂牌</el-button>
      </template>
    </el-dialog>

    <!-- 绿色能量获取对话框（角色 + 业务凭证） -->
    <el-dialog v-model="energyDlg" title="提交业务凭证 · 获取绿色能量" width="560px">
      <el-form label-width="118px" size="small">
        <el-form-item label="发放角色">
          <el-select v-model="energyRoleKey" style="width: 100%" @change="onEnergyRoleChange">
            <el-option
              v-for="r in energyRoles"
              :key="r.key"
              :label="`${r.icon} ${r.name} · ${r.energy_rule.action} +${r.energy_rule.points} 能量`"
              :value="r.key"
            />
          </el-select>
          <div class="dq-tip" style="margin-top: 4px">
            <span class="dt-label">说明:</span>该能量由所选联盟业务方（地铁 / 公交 / 单车 / 外卖 / 回收）代表发放，当前钱包作为居民接收。
          </div>
        </el-form-item>
        <template v-if="curEnergyRole">
          <el-form-item label="接收钱包">
            <el-input :model-value="wallet" disabled />
          </el-form-item>
          <el-form-item v-for="f in energyProofFields" :key="f.key" :label="f.label">
            <el-switch
              v-if="f.type === 'switch'"
              v-model="energyProof[f.key]"
              active-text="已选择无需餐具"
            />
            <el-input-number
              v-else-if="f.type === 'number'"
              v-model="energyProof[f.key]"
              :min="0"
              :placeholder="f.placeholder"
              style="width: 100%"
              controls-position="right"
            />
            <el-input v-else v-model="energyProof[f.key]" :placeholder="f.placeholder" />
          </el-form-item>
          <el-form-item>
            <div class="energy-threshold dq-tip">
              ⚠️ 发放条件：{{ energyThresholdHint }}；凭证校验通过后发放
              <b>{{ curEnergyRule?.points }} 点</b>绿色能量。
            </div>
          </el-form-item>
        </template>
        <template v-else>
          <el-empty description="请先选择发放角色" :image-size="60" />
        </template>
      </el-form>
      <template #footer>
        <el-button @click="energyDlg = false">取消</el-button>
        <el-button type="primary" :loading="issuingEnergy" @click="doGetEnergy">
          校验并获取能量
        </el-button>
      </template>
    </el-dialog>

    <!-- 已发行 Token -->
    <div class="dq-card" style="margin-top:14px" v-if="tokens.length">
      <div class="dq-card-title">已发行 Token <span class="dq-tag info" style="margin-left:auto">{{ tokens.length }} 份合约</span></div>
      <el-table :data="tokens" border size="small" class="exp-table" stripe>
        <el-table-column prop="name" label="名称" width="140" />
        <el-table-column prop="symbol" label="符号" width="100">
          <template #default="{ row }"><span class="std-tag s-erc20">{{ row.symbol }}</span></template>
        </el-table-column>
        <el-table-column prop="decimals" label="精度" width="80" />
        <el-table-column prop="total_supply" label="发行量" min-width="140">
          <template #default="{ row }"><span class="dq-mono">{{ (row.total_supply || '').toLocaleString ? (row.total_supply || '').toLocaleString() : row.total_supply }}</span></template>
        </el-table-column>
        <el-table-column prop="address" label="合约地址" min-width="260">
          <template #default="{ row }"><span class="dq-mono link" @click="$router.push('/explorer')">{{ row.address }}</span></template>
        </el-table-column>
        <el-table-column prop="owner" label="发行者" min-width="160">
          <template #default="{ row }"><span class="dq-mono dim">{{ short(row.owner) }}</span></template>
        </el-table-column>
      </el-table>
    </div>
    <EmptyIllustration v-else type="contract" style="margin-top:14px" subtitle="发行第一份 ERC20 合约后，此处将展示已部署 Token 列表" />

    <!-- 交易流水时间线（TxTimeline） -->
    <div class="dq-card" style="margin-top:14px" v-if="transferTimeline.length || tokens.length">
      <TxTimeline
        :list="transferTimeline"
        :title="`钱包交易记录 · ERC20 转账/发行 共 ${transferTimeline.length} 笔`"
      />
    </div>
    <div v-else style="margin-top:14px">
      <EmptyIllustration type="wallet" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onActivated, onMounted } from 'vue'
import { walletApi, ecoApi } from '@/api'
import { useAppStore } from '@/stores/app'
import { ElMessage } from 'element-plus'
import { Coin, Wallet as WalletIcon, Document, Refresh, UploadFilled, Promotion } from '@element-plus/icons-vue'
import CountUp from '@/components/CountUp.vue'
import EmptyIllustration from '@/components/EmptyIllustration.vue'
import TxTimeline from '@/components/TxTimeline.vue'

const app = useAppStore()
const wallet = computed(() => app.currentWallet)
const setWallet = (v: string) => { app.setWallet(v); loadAll() }

const balances = ref<any[]>([])
const tokens = ref<any[]>([])
const transfers = ref<any[]>([])

const issue = reactive({ name: '', symbol: '', decimals: 18, total_supply: '1000000' })
const transfer = reactive({ token_address: '', from_addr: app.currentWallet, to_addr: '', amount: '' })

// watch store 钱包变化（header 全局切换时联动刷新）
watch(() => app.currentWallet, (newWallet) => {
  transfer.from_addr = newWallet  // 转账表单 From 地址同步
  loadAll()
})

const short = (h: string) => h ? h.slice(0, 10) + '...' + h.slice(-4) : '-'

/* 将后端 transfer + token 数据映射成 TxTimeline 格式 */
const transferTimeline = computed(() => {
  const out: any[] = []
  // 发行记录（从 tokens 推断）
  for (const t of tokens.value) {
    out.push({
      kind: '部署 ERC20',
      from: '0x0000000000000000000000000000000000000000',
      to: t.address,
      to_is_contract: true,
      amount: String(t.total_supply || ''),
      token: `${t.name} (${t.symbol})`,
      gas: (21000 + 200 * 2000).toLocaleString(),
      tx_hash: t.tx_hash || `deploy_${t.address}`,
      time: t.created_at || '-',
      status: 'ok',
    })
  }
  // 转账记录
  for (const x of transfers.value) {
    out.push({
      kind: 'ERC20 转账',
      from: x.from_addr,
      to: x.to_addr,
      to_is_contract: false,
      amount: String(x.amount || ''),
      token: short(x.token_address),
      gas: x.gas_used ? String(x.gas_used) : undefined,
      tx_hash: x.tx_hash,
      time: x.created_at || '-',
      status: x.status === 'fail' || x.status === 'error' ? 'fail' : 'ok',
    })
  }
  // 按时间倒序
  out.sort((a, b) => {
    const ta = a.time === '-' ? 0 : new Date(String(a.time)).getTime()
    const tb = b.time === '-' ? 0 : new Date(String(b.time)).getTime()
    return tb - ta
  })
  return out
})

const loadBalances = async () => { balances.value = ((await walletApi.balances(wallet.value)) as any).items || [] }
const loadTokens = async () => { tokens.value = ((await walletApi.tokens()) as any).items || [] }
const loadTransfers = async () => { transfers.value = ((await walletApi.transfers(wallet.value)) as any).items || [] }

/* ==================== 绿色能量钱包 + 绿色资产（业务闭环） ==================== */
/** 是否 GreenEnergy（绿色能量代币，seed 注册 name=GreenEnergy / symbol=GE） */
const isGreenEnergy = (b: any) =>
  String(b.name || '').toLowerCase().includes('greenenergy') ||
  String(b.symbol || '').toUpperCase() === 'GE' ||
  String(b.name || '').includes('绿色能量')

const greenEnergyBalance = computed(() => {
  const b = balances.value.find(isGreenEnergy)
  return b ? Number(b.balance ?? 0) : 0
})

const myCertificates = ref<any[]>([])
const myBadges = ref<any[]>([])
const marketList = ref<any[]>([])

interface EcoAssetItem {
  key: string
  icon: string
  name: string
  idText: string
  standard: string
  asset_type: string
  asset_id: number
  listed: boolean
}

const ecoAssets = computed<EcoAssetItem[]>(() => {
  const out: EcoAssetItem[] = []
  for (const c of myCertificates.value) {
    out.push({
      key: `cert_${c.id}`,
      icon: '🌱',
      name: c.species_name || '植树证书',
      idText: `Token ID: ${c.token_id}`,
      standard: 'ERC721',
      asset_type: 'certificate',
      asset_id: Number(c.id),
      listed: isEcoListed('certificate', Number(c.id)),
    })
  }
  for (const b of myBadges.value) {
    out.push({
      key: `${b.badge_type}_${b.id}`,
      icon: b.badge_type === 'voucher' ? '🎫' : '🏅',
      name: b.name || (b.badge_type === 'voucher' ? '骑行券' : '生态勋章'),
      idText: `Token ID: ${b.token_id}`,
      standard: 'ERC1155',
      asset_type: b.badge_type === 'voucher' ? 'voucher' : 'badge',
      asset_id: Number(b.id),
      listed: isEcoListed(b.badge_type === 'voucher' ? 'voucher' : 'badge', Number(b.id)),
    })
  }
  return out
})

const isEcoListed = (asset_type: string, asset_id: number) =>
  marketList.value.some(
    (m) => m.asset_type === asset_type && Number(m.asset_id) === Number(asset_id) && m.status === 'active',
  )

const ecoListDlg = ref(false)
const ecoListing = ref(false)
const ecoListPrice = ref(50)
const listingKey = ref('')
const ecoCurAsset = ref<EcoAssetItem | null>(null)

const openListDlg = (a: EcoAssetItem) => {
  ecoCurAsset.value = a
  ecoListPrice.value = a.asset_type === 'certificate' ? 500 : a.asset_type === 'voucher' ? 100 : 50
  ecoListDlg.value = true
}

const doEcoList = async () => {
  if (!ecoCurAsset.value) return
  if (ecoListPrice.value <= 0) {
    ElMessage.warning('价格必须大于 0')
    return
  }
  ecoListing.value = true
  listingKey.value = ecoCurAsset.value.key
  try {
    await ecoApi.marketList({
      seller: wallet.value,
      asset_type: ecoCurAsset.value.asset_type,
      asset_id: ecoCurAsset.value.asset_id,
      price_energy: ecoListPrice.value,
    })
    ElMessage.success(`已挂牌：${ecoCurAsset.value.name} · ${ecoListPrice.value} 能量`)
    ecoListDlg.value = false
    await loadEcoAssets()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '挂牌失败')
  } finally {
    ecoListing.value = false
    listingKey.value = ''
  }
}

const loadEcoAssets = async () => {
  try {
    const r: any = await ecoApi.marketItems()
    marketList.value = r?.items || []
  } catch {
    marketList.value = []
  }
  // 仅加载当前钱包持有的绿色资产
  try {
    const r: any = await ecoApi.certificates(wallet.value)
    myCertificates.value = r?.items || r || []
  } catch {
    myCertificates.value = []
  }
  try {
    const r: any = await ecoApi.badges(wallet.value)
    myBadges.value = r?.items || r || []
  } catch {
    myBadges.value = []
  }
}

/* ==================== 钱包内获取绿色能量（角色 + 业务凭证） ==================== */
/** 联盟管理员钱包：发行新代币唯一身份（与后端 ADMIN_WALLET 一致） */
const ADMIN_WALLET = '0xadmin'
const isAdminWallet = computed(() => String(wallet.value || '').toLowerCase() === ADMIN_WALLET)

const energyRoles = ref<any[]>([])
const energyDlg = ref(false)
const energyRoleKey = ref('')
const energyProof = reactive<Record<string, any>>({})
const issuingEnergy = ref(false)

/** 当前选中的发放角色定义 */
const curEnergyRole = computed(() =>
  energyRoles.value.find((r) => r.key === energyRoleKey.value) || null,
)
const curEnergyRule = computed(() => curEnergyRole.value?.energy_rule || null)
const energyProofFields = computed(() => curEnergyRule.value?.proof_fields || [])
const energyThresholdHint = computed(() => {
  const r = curEnergyRule.value
  if (!r) return ''
  if (r.proof_field === 'no_cutlery') return 'no_cutlery = true（必须选择「无需餐具」）'
  return `${r.proof_field} ≥ ${r.min} ${r.unit}`
})

/** 打开获取能量对话框：加载联盟角色（仅保留可发能量的业务角色） */
const openEnergyDlg = async () => {
  if (!energyRoles.value.length) {
    try {
      const r: any = await ecoApi.roles()
      energyRoles.value = (r?.items || r || []).filter((x: any) => x && x.energy_rule)
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || e?.message || '联盟角色加载失败')
      return
    }
  }
  if (!energyRoleKey.value && energyRoles.value.length) {
    energyRoleKey.value = energyRoles.value[0].key
    resetEnergyProof()
  }
  energyDlg.value = true
}

/** 切换角色时重置凭证字段 */
const onEnergyRoleChange = () => resetEnergyProof()

const resetEnergyProof = () => {
  for (const k of Object.keys(energyProof)) delete energyProof[k]
  for (const f of energyProofFields.value) {
    if (f.type === 'switch') energyProof[f.key] = false
    else if (f.type === 'number') energyProof[f.key] = undefined
    else energyProof[f.key] = ''
  }
}

/** 提交业务凭证 → 角色绑定 → 后端校验 → 能量发放到当前钱包 */
const doGetEnergy = async () => {
  const role = curEnergyRole.value
  if (!role) {
    ElMessage.warning('请选择发放角色')
    return
  }
  // 必填业务字段前端预校验
  const missing: string[] = []
  for (const f of energyProofFields.value) {
    if (!f.required) continue
    const v = energyProof[f.key]
    if (v === undefined || v === null || v === '' || (typeof v === 'string' && !v.trim())) {
      missing.push(f.label || f.key)
    }
  }
  if (missing.length) {
    ElMessage.warning(`缺少必填业务数据：${missing.join('、')}，请补全业务凭证`)
    return
  }
  issuingEnergy.value = true
  try {
    // 业务闭环：先绑定当前钱包为所选联盟角色（后台校验发放身份），再发起能量发放
    await ecoApi.selectRole(wallet.value, role.key)
    const r: any = await ecoApi.issueEnergy(wallet.value, role.key, energyProof)
    ElMessage.success(
      `${role.icon} ${role.name} 发放成功：+${r?.points ?? role.energy_rule.points} 绿色能量（已到账当前钱包）`,
    )
    energyDlg.value = false
    await loadBalances()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '能量发放失败')
  } finally {
    issuingEnergy.value = false
  }
}

const doIssue = async () => {
  if (!isAdminWallet.value) {
    ElMessage.warning(`发行新代币仅限联盟管理员钱包（${ADMIN_WALLET}），请先切换「当前操作钱包」`)
    return
  }
  if (!issue.name || !issue.symbol) return ElMessage.warning('请填写名称与符号')
  try {
    const r: any = await walletApi.issue({ ...issue, owner: wallet.value })
    ElMessage.success(`发行成功: ${r.address}`)
    /* 部署完成彩粒 */
    try { app.confetti({ particleCount: 80, spread: 70, origin: { y: 0.45 }, ticks: 160 }) } catch {}
    issue.name = ''; issue.symbol = ''; issue.total_supply = '1000000'
    loadTokens(); loadBalances()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '发行失败')
  }
}

const doTransfer = async () => {
  if (!transfer.token_address || !transfer.to_addr || !transfer.amount) return ElMessage.warning('请完整填写')
  const r: any = await walletApi.transfer({ ...transfer })
  ElMessage.success(`转账成功: ${r.tx_hash ? short(r.tx_hash) : ''}`)
  transfer.to_addr = ''; transfer.amount = ''
  loadBalances(); loadTransfers()
}

const loadAll = () => { loadBalances(); loadTokens(); loadTransfers(); loadEcoAssets() }
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
    &.k-t  { background: rgba(77,141,255,0.15); color: var(--dq-info); }
    &.k-b  { background: rgba(0,230,195,0.15); }
    &.k-tx { background: rgba(255,207,77,0.15); color: var(--dq-warn); }
  }
  .kpi-num {
    font-family: var(--dq-mono); font-size: 24px; font-weight: 800;
    background: var(--dq-grad-primary);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent;
    &.warn { background: linear-gradient(135deg, #ffcf4d, #e6a23c); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
    &.info { background: linear-gradient(135deg, #4d8dff, #2e6bd9); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
  }
  .kpi-sub { font-size: 11px; color: var(--dq-text-dim); margin-top: 2px; }
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
    background: linear-gradient(135deg, rgba(77,141,255,0.05), rgba(77,141,255,0.01));
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
  .fs-desc { font-size: 12px; color: var(--dq-text-dim); line-height: 1.6; margin-bottom: 6px; b { color: var(--dq-primary); font-weight: 500; } }
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
  .kpi-row { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 760px) {
  .kpi-row { grid-template-columns: 1fr; }
  .grid { grid-template-columns: 1fr !important; }
}

.grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; }

/* ---- 绿色能量钱包 + 绿色资产 ---- */
.eco-row {
  display: grid; grid-template-columns: 1fr 1.4fr; gap: 14px;
  align-items: stretch;
}
.ge-balance {
  padding: 16px 18px; margin-bottom: 12px;
  text-align: center;
  .ge-num {
    font-family: var(--dq-mono); font-size: 44px; font-weight: 800;
    background: var(--dq-grad-primary);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent;
    text-shadow: 0 0 24px var(--dq-primary-glow);
    line-height: 1.15;
  }
  .ge-sub { font-size: 11px; color: var(--dq-text-dim); margin-top: 6px; }
}
.ge-hint { margin-bottom: 12px; }
.ge-ops { display: flex; gap: 8px; flex-wrap: wrap; }
.eco-assets { display: flex; flex-direction: column; gap: 8px; max-height: 300px; overflow-y: auto; }
.eco-asset {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 12px;
  background: var(--dq-bg-2);
  border: 1px solid var(--dq-border);
  border-radius: 8px;
  .ea-left { display: flex; align-items: center; gap: 10px; }
  .ea-icon { font-size: 22px; }
  .ea-name { color: var(--dq-text); font-size: 13px; font-weight: 600; }
  .ea-id { font-size: 11px; margin-top: 2px; }
  .ea-right { display: flex; align-items: center; gap: 8px; }
}
.li-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 12px;
  background: var(--dq-bg-2);
  border: 1px solid var(--dq-border);
  border-radius: 8px;
  span { color: var(--dq-text-dim); font-size: 13px; }
  b { color: var(--dq-text); font-size: 13px; }
}
.empty-tip {
  color: var(--dq-text-dim); font-size: 13px;
  padding: 20px 14px; text-align: center; line-height: 1.7;
}
@media (max-width: 1000px) {
  .eco-row { grid-template-columns: 1fr; }
}
.bal-list { margin-bottom: 10px; display: flex; flex-direction: column; gap: 6px; }
.bal-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 9px 12px; background: var(--dq-bg-2); border-radius: 6px;
  border: 1px solid var(--dq-border); transition: all .15s;
  &:hover { border-color: var(--dq-border-2); }
  .b-name { color: var(--dq-text); font-weight: 600; font-size: 13px; }
  .b-val { color: var(--dq-primary); font-size: 17px; font-weight: 800; }
  .addr { font-size: 11px; margin-top: 2px; }
}
.link { color: var(--dq-primary); cursor: pointer; }
.dim { color: var(--dq-text-dim); }
.tip { color: var(--dq-text-dim); font-size: 12px; margin-top: 10px; }

/* 协议色 */
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
.exp-table { margin-bottom: 10px; }
</style>
