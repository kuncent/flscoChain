<template>
  <div class="my-grades dq-enter-up">
    <!-- 顶部标题 -->
    <section class="dq-card hero">
      <div class="hero-left">
        <div class="hero-title">
          <span class="g-icon">🎓</span>
          我的实训成绩
          <span class="dq-live"><span class="dot"></span>{{ wallet ? '已连接' : '未连接' }}</span>
        </div>
        <div class="hero-sub">
          钱包地址：<b>{{ displayWallet || '未连接' }}</b>
          · 系统自动采集你的链上活动，按 4 维加权计算实训成绩
        </div>
        <div class="hero-sub hero-flow">
          流程：<b>刷新我的实训分</b>（产生草稿）→ 教师在「学生成绩」点同步（入册）→ 综合成绩 = 实训 × 60% + 教师 × 40%
        </div>
      </div>
      <div class="hero-right">
        <el-button type="primary" @click="loadData" :loading="loading">
          <el-icon><Refresh /></el-icon>&nbsp;刷新成绩
        </el-button>
        <el-button @click="refreshDraft" :loading="draftLoading">刷新我的实训分</el-button>
        <el-button @click="$router.push('/report')">
          <el-icon><Document /></el-icon>&nbsp;查看实训报告
        </el-button>
      </div>
    </section>

    <!-- 未连接钱包提示 -->
    <section class="dq-card" v-if="!wallet">
      <el-empty description="请先连接钱包以查看你的实训成绩">
        <el-button type="primary" @click="$router.push('/wallet')">前往钱包管理</el-button>
      </el-empty>
    </section>

    <!-- 实训成绩概览 -->
    <section class="dq-card" v-if="wallet && trainingNow !== null">
      <div class="dq-card-title">实训成绩概览</div>
      <div class="score-overview">
        <div class="score-main">
          <div class="score-label">实训成绩</div>
          <div class="score-value">{{ trainingNow.toFixed(1) }}</div>
          <div class="score-unit">/ 100</div>
        </div>
        <div class="score-detail">
          <div class="detail-item" v-for="(item, key) in detailNow" :key="key">
            <div class="detail-label">{{ dimensionLabels[String(key) as keyof typeof dimensionLabels] || key }}</div>
            <div class="detail-bar">
              <div class="bar-fill" :style="{ width: `${item.score}%` }"></div>
            </div>
            <div class="detail-score">{{ item.score.toFixed(1) }}</div>
            <div class="detail-weight">× {{ (item.weight * 100).toFixed(0) }}%</div>
          </div>
        </div>
      </div>
    </section>

    <!-- 系统实训草稿（P1-25：草稿与正式成绩分家，不影响综合分） -->
    <section class="dq-card" v-if="wallet && draft">
      <div class="dq-card-title">
        系统实训草稿
        <span class="dq-tag muted">不计入综合分</span>
        <span class="dq-tag" :class="draft.applied ? '' : 'warn'">
          {{ draft.applied ? '教师已同步入册' : '待教师同步' }}
        </span>
        <span class="dq-tag warn" v-if="draft.class_missing">本条未标班级，教师需逐条同步</span>
      </div>
      <div class="draft-body">
        <div class="draft-score">{{ Number(draft.training_score || 0).toFixed(1) }}</div>
        <div class="draft-meta">
          <div>课程：{{ draft.course }} · 草稿更新于 {{ formatTime(draft.updated_at) }}</div>
          <div v-if="draft.in_grades" class="draft-tip">
            成绩册行更新于 {{ formatTime(draft.grades_updated_at) }}
          </div>
          <div class="draft-tip">{{ draft.status_text || '这是系统按你的链上活动实时算出的实训分草稿。它只在预览里存在，需教师在「成绩册 · 系统草稿」里点同步后才会成为正式成绩（正式成绩才参与综合分）。' }}</div>
        </div>
      </div>
      <div class="draft-calibers" v-if="walletCandidates.length > 1">
        已合并同一学生的多个身份口径：{{ walletCandidates.join(' / ') }}
      </div>
    </section>

    <!-- 从没刷过草稿且成绩册为空：给出明确的下一步，而不是留一张只有标题的空卡 -->
    <section class="dq-card" v-if="wallet && !draft && !grades.length">
      <div class="dq-card-title">成绩还没开始生成</div>
      <div class="draft-meta">
        <div>① 先把实训做完：搭链教程 10 步、部署并调用合约、生态角色与兑换；</div>
        <div>② 点右上<b>「刷新我的实训分」</b>，系统按你的链上活动算出实训草稿；</div>
        <div>③ 教师在「学生成绩 · 系统实训草稿」点同步后，草稿才会变成<b>正式成绩</b>并参与综合分。</div>
      </div>
    </section>

    <!-- 能力雷达图 -->
    <section class="dq-card" v-if="wallet && detailNow">
      <div class="dq-card-title">能力维度分析</div>
      <div ref="radarChart" class="radar-chart"></div>
    </section>

    <!-- 成绩记录列表 -->
    <section class="dq-card" v-if="wallet">
      <div class="dq-card-title">
        成绩记录
        <span class="dq-tag" v-if="grades.length">{{ grades.length }} 条</span>
      </div>
      <el-table :data="grades" stripe v-loading="loading"
                empty-text="成绩册暂无记录：完成实训后由系统算出草稿，教师同步后才生成正式成绩">
        <el-table-column prop="course" label="课程" width="150" />
        <el-table-column prop="student_name" label="学生" width="120" />
        <el-table-column label="行来源" width="110">
          <template #default="{ row }">
            <!-- P1-25：让学生能看出这一行是教师正式评过的分，还是系统自动行 -->
            <span class="dq-tag" :class="row.row_kind === 'teacher' ? '' : 'muted'">
              {{ row.row_kind === 'teacher' ? '教师已评' : '系统行' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="实训成绩" width="120">
          <template #default="{ row }">
            <span class="score-cell accent">{{ row.training_score?.toFixed(1) || '0.0' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="教师评分" width="120">
          <template #default="{ row }">
            <span class="score-cell">{{ row.score?.toFixed(1) || '0.0' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="综合成绩" width="120">
          <template #default="{ row }">
            <span class="score-cell success">{{ row.final_score?.toFixed(1) || '0.0' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="teacher_name" label="评分教师" width="120" />
        <el-table-column prop="remark" label="备注" show-overflow-tooltip />
        <el-table-column label="更新时间" width="160">
          <template #default="{ row }">
            {{ row.updated_at ? formatTime(row.updated_at) : '-' }}
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- 成绩说明 -->
    <section class="dq-card info-card">
      <div class="dq-card-title">成绩计算说明</div>
      <div class="info-content">
        <div class="info-item">
          <div class="info-icon">📊</div>
          <div class="info-text">
            <div class="info-title">实训成绩（60%）</div>
            <div class="info-desc">系统自动采集你的链上活动，按 4 个维度加权计算：链搭建（20%）、合约开发（30%）、链上验证（25%）、联盟治理（25%）</div>
          </div>
        </div>
        <div class="info-item">
          <div class="info-icon">✍️</div>
          <div class="info-text">
            <div class="info-title">教师评分（40%）</div>
            <div class="info-desc">教师根据你的实训报告、课堂表现等进行综合评定</div>
          </div>
        </div>
        <div class="info-item">
          <div class="info-icon">🎯</div>
          <div class="info-text">
            <div class="info-title">综合成绩</div>
            <div class="info-desc">综合成绩 = 实训成绩 × 60% + 教师评分 × 40%</div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Document } from '@element-plus/icons-vue'
import { gradesApi } from '@/api'
import { fmtDateTime } from '@/utils/time'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { useWalletStore } from '@/stores/wallets'
import * as echarts from 'echarts'

const app = useAppStore()
const auth = useAuthStore()
const wallets = useWalletStore()
// 用 userId 作为学习行为跟踪标识（不随角色钱包切换变化），确保成绩按用户隔离；
// userId 缺失时回落**本人真实链上地址**，不再回落 0xlearner 这个公共演示别名
// （否则同一浏览器换账号登录会看到彼此的成绩）
const wallet = computed(() => auth.user?.userId || wallets.myAddress || app.currentWallet || '')
/* 顶栏与本页的取数键故意用 userId（它稳定、不随切换角色钱包变化，且后端按
   钱包候选集并集取数），但把内部 UUID 顶在「钱包地址」标签下会误导学生：
   他拿这串字符去区块链浏览器 / 钱包里找不到任何东西。展示一律用真实 0x 地址。 */
const displayWallet = computed(() => auth.user?.wallet || wallets.myAddress || '')
const loading = ref(false)
const grades = ref<any[]>([])
const trainingNow = ref<number | null>(null)
const detailNow = ref<any>(null)
// P1-25：系统草稿（grade_draft）与成绩册分行展示，不混为一谈
const draft = ref<any | null>(null)
const draftLoading = ref(false)
const walletCandidates = ref<string[]>([])
const radarChart = ref<HTMLElement>()

const dimensionLabels = {
  chain_setup: '链搭建',
  contract_dev: '合约开发',
  chain_verify: '链上验证',
  alliance_gov: '联盟治理',
}

const formatTime = (ts: string) => (ts ? fmtDateTime(ts) : '-')

const loadData = async () => {
  if (!wallet.value) {
    ElMessage.warning('请先连接钱包')
    return
  }

  loading.value = true
  try {
    const res = await gradesApi.myGrades(wallet.value)
    grades.value = res.grades || []
    trainingNow.value = res.training_now ?? 0
    detailNow.value = res.detail_now || null
    draft.value = res.draft ?? null
    walletCandidates.value = res.wallet_candidates || []

    // 渲染雷达图
    await nextTick()
    renderRadarChart()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载成绩失败')
  } finally {
    loading.value = false
  }
}

/** 刷新系统草稿（只写 grade_draft，不写成绩册，P1-8 / P1-25） */
const refreshDraft = async () => {
  if (!wallet.value) {
    ElMessage.warning('请先连接钱包')
    return
  }
  draftLoading.value = true
  try {
    const res: any = await gradesApi.draftRefresh({ wallet: wallet.value })
    ElMessage.success(`实训分草稿已刷新：${Number(res?.training_score ?? 0).toFixed(1)} 分`
      + (res?.class_missing ? '（该草稿未标班级，请告诉教师在草稿列表逐条同步）' : '（等待教师在成绩册点同步后计入综合分）'))
    await loadData()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '刷新草稿失败')
  } finally {
    draftLoading.value = false
  }
}

const renderRadarChart = () => {
  if (!radarChart.value || !detailNow.value) return

  const chart = echarts.init(radarChart.value)
  const indicators = Object.keys(detailNow.value).map(key => ({
    name: dimensionLabels[key as keyof typeof dimensionLabels] || key,
    max: 100,
  }))
  const values = Object.keys(detailNow.value).map(key => detailNow.value[key].score)

  chart.setOption({
    tooltip: {},
    radar: {
      indicator: indicators,
      shape: 'circle',
      splitNumber: 5,
      axisName: {
        color: '#8fa0c4',
        fontSize: 12,
      },
      splitLine: {
        lineStyle: { color: 'rgba(143, 160, 196, 0.2)' },
      },
      splitArea: {
        areaStyle: { color: ['rgba(0, 230, 195, 0.05)', 'rgba(0, 230, 195, 0.1)'] },
      },
      axisLine: {
        lineStyle: { color: 'rgba(143, 160, 196, 0.3)' },
      },
    },
    series: [{
      type: 'radar',
      data: [{
        value: values,
        name: '能力维度',
        areaStyle: {
          color: 'rgba(0, 230, 195, 0.3)',
        },
        lineStyle: {
          color: '#00e6c3',
          width: 2,
        },
        itemStyle: {
          color: '#00e6c3',
        },
      }],
    }],
  })

  window.addEventListener('resize', () => chart.resize())
}

onMounted(() => {
  loadData()
})

// 用户身份变化时自动刷新成绩
watch(wallet, (newWallet) => {
  if (newWallet) {
    loadData()
  } else {
    // 钱包断开：清空页面数据
    grades.value = []
    trainingNow.value = null
    detailNow.value = null
    draft.value = null
    walletCandidates.value = []
  }
})
</script>

<style scoped lang="scss">
.my-grades {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
}

.hero-left {
  flex: 1;
}

.hero-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 20px;
  font-weight: 600;
  color: #e0e6f0;
  margin-bottom: 8px;
}

.hero-sub {
  font-size: 13px;
  color: #8fa0c4;
  b {
    color: #00e6c3;
  }
}

.hero-flow {
  margin-top: 4px;
  font-size: 12px;
}

.hero-right {
  display: flex;
  gap: 10px;
}

.score-overview {
  display: flex;
  gap: 40px;
  align-items: center;
}

.score-main {
  text-align: center;
  min-width: 150px;
}

.score-label {
  font-size: 14px;
  color: #8fa0c4;
  margin-bottom: 8px;
}

.score-value {
  font-size: 48px;
  font-weight: 700;
  color: #00e6c3;
  line-height: 1;
}

.score-unit {
  font-size: 14px;
  color: #8fa0c4;
  margin-top: 4px;
}

.score-detail {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.detail-label {
  width: 80px;
  font-size: 13px;
  color: #8fa0c4;
}

.detail-bar {
  flex: 1;
  height: 8px;
  background: rgba(143, 160, 196, 0.1);
  border-radius: 4px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #00e6c3, #4d8dff);
  border-radius: 4px;
  transition: width 0.3s ease;
}

.detail-score {
  width: 50px;
  font-size: 14px;
  font-weight: 600;
  color: #e0e6f0;
  text-align: right;
}

.detail-weight {
  width: 50px;
  font-size: 12px;
  color: #8fa0c4;
}

.radar-chart {
  width: 100%;
  height: 300px;
}

.draft-body {
  display: flex;
  align-items: center;
  gap: 20px;
}

.draft-score {
  font-size: 32px;
  font-weight: 700;
  color: #ffd24d;
  line-height: 1;
  min-width: 90px;
}

.draft-meta {
  flex: 1;
  font-size: 13px;
  color: #8fa0c4;
  line-height: 1.7;
}

.draft-tip {
  margin-top: 4px;
  color: #7b8aab;
}

.draft-calibers {
  margin-top: 10px;
  font-size: 12px;
  color: #7b8aab;
  font-family: 'JetBrains Mono', Consolas, monospace;
  word-break: break-all;
}

.score-cell {
  font-weight: 600;
  &.accent {
    color: #00e6c3;
  }
  &.success {
    color: #4d8dff;
  }
}

.info-card {
  margin-top: 20px;
}

.info-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.info-item {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.info-icon {
  font-size: 24px;
  flex-shrink: 0;
}

.info-text {
  flex: 1;
}

.info-title {
  font-size: 14px;
  font-weight: 600;
  color: #e0e6f0;
  margin-bottom: 4px;
}

.info-desc {
  font-size: 13px;
  color: #8fa0c4;
  line-height: 1.5;
}
</style>
