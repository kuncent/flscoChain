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
          钱包地址：<b>{{ wallet || '未连接' }}</b>
          · 系统自动采集你的链上活动，按 4 维加权计算实训成绩
        </div>
      </div>
      <div class="hero-right">
        <el-button type="primary" @click="loadData" :loading="loading">
          <el-icon><Refresh /></el-icon>&nbsp;刷新成绩
        </el-button>
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
            <div class="detail-label">{{ dimensionLabels[key as keyof typeof dimensionLabels] || key }}</div>
            <div class="detail-bar">
              <div class="bar-fill" :style="{ width: `${item.score}%` }"></div>
            </div>
            <div class="detail-score">{{ item.score.toFixed(1) }}</div>
            <div class="detail-weight">× {{ (item.weight * 100).toFixed(0) }}%</div>
          </div>
        </div>
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
      <el-table :data="grades" stripe v-loading="loading" empty-text="暂无成绩记录，完成实训后将自动生成">
        <el-table-column prop="course" label="课程" width="150" />
        <el-table-column prop="student_name" label="学生" width="120" />
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
import { ref, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Document } from '@element-plus/icons-vue'
import { gradesApi } from '@/api'
import * as echarts from 'echarts'

const wallet = ref('')
const loading = ref(false)
const grades = ref<any[]>([])
const trainingNow = ref<number | null>(null)
const detailNow = ref<any>(null)
const radarChart = ref<HTMLElement>()

const dimensionLabels = {
  chain_setup: '链搭建',
  contract_dev: '合约开发',
  chain_verify: '链上验证',
  alliance_gov: '联盟治理',
}

const formatTime = (ts: string) => {
  if (!ts) return '-'
  const d = new Date(ts)
  return d.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

const loadData = async () => {
  // 从 localStorage 获取钱包地址
  const walletData = localStorage.getItem('wallet')
  if (walletData) {
    try {
      const parsed = JSON.parse(walletData)
      wallet.value = parsed.address || ''
    } catch {
      wallet.value = walletData
    }
  }

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

    // 渲染雷达图
    await nextTick()
    renderRadarChart()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载成绩失败')
  } finally {
    loading.value = false
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
