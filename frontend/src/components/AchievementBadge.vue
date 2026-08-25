<template>
  <div class="achievement-badge">
    <!-- 统计概览 -->
    <div class="stats-overview">
      <div class="stat-item">
        <div class="stat-label">已获得成就</div>
        <div class="stat-value">
          <CountUp :target="achievedCount" /> / {{ achievements.length }}
        </div>
      </div>
      <div class="stat-item">
        <div class="stat-label">总积分</div>
        <div class="stat-value highlight">
          <CountUp :target="totalPoints" />
        </div>
      </div>
    </div>

    <!-- 成就分类展示 -->
    <div class="achievement-section" v-for="(group, category) in groupedAchievements" :key="category">
      <div class="section-title">{{ categoryLabels[category] || category }}</div>
      <div class="achievement-grid">
        <div
          v-for="item in group"
          :key="item.id"
          class="achievement-card"
          :class="{ obtained: item.obtained, locked: !item.obtained }"
          @click="showDetail(item)"
        >
          <div class="achievement-icon">
            <span class="icon-text">{{ item.icon || '🏆' }}</span>
          </div>
          <div class="achievement-info">
            <div class="achievement-name">{{ item.name }}</div>
            <div class="achievement-desc">{{ item.description }}</div>
            <div class="progress-bar">
              <div
                class="progress-fill"
                :style="{ width: `${getProgressPercent(item)}%` }"
              ></div>
            </div>
            <div class="progress-text">
              {{ item.current_progress || 0 }} / {{ item.target_value || 1 }}
            </div>
          </div>
          <div class="achievement-status">
            <el-tag v-if="item.obtained" type="success" size="small">已获得</el-tag>
            <el-tag v-else type="info" size="small">未获得</el-tag>
          </div>
        </div>
      </div>
    </div>

    <!-- 挑战任务展示 -->
    <div v-if="showChallenges && challenges.length > 0" class="challenges-section">
      <div class="section-title">挑战任务</div>
      <div v-for="(group, difficulty) in groupedChallenges" :key="difficulty" class="difficulty-group">
        <div class="difficulty-label">{{ difficultyLabels[difficulty] || difficulty }}</div>
        <div class="challenge-list">
          <div v-for="challenge in group" :key="challenge.id" class="challenge-card">
            <div class="challenge-header">
              <div class="challenge-name">{{ challenge.name }}</div>
              <el-tag :type="difficultyTagType(difficulty)" size="small">
                {{ difficultyLabels[difficulty] }}
              </el-tag>
            </div>
            <div class="challenge-desc">{{ challenge.description }}</div>
            <div class="challenge-meta">
              <div class="challenge-progress">
                <div class="progress-bar">
                  <div
                    class="progress-fill"
                    :style="{ width: `${getChallengeProgress(challenge)}%` }"
                  ></div>
                </div>
                <div class="progress-text">
                  {{ challenge.current_progress || 0 }} / {{ challenge.target_value || 1 }}
                </div>
              </div>
              <div class="challenge-reward">
                <span class="reward-label">奖励积分：</span>
                <span class="reward-value">{{ challenge.reward_points || 0 }}</span>
              </div>
            </div>
            <div class="challenge-action">
              <el-button
                v-if="!challenge.started"
                type="primary"
                size="small"
                @click="startChallenge(challenge.id)"
              >
                开始挑战
              </el-button>
              <el-tag v-else type="warning" size="small">进行中</el-tag>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 成就详情对话框 -->
    <el-dialog
      v-model="detailVisible"
      title="成就详情"
      width="500px"
      class="achievement-detail-dialog"
    >
      <div v-if="selectedAchievement" class="detail-content">
        <div class="detail-icon">
          <span class="icon-text">{{ selectedAchievement.icon || '🏆' }}</span>
        </div>
        <div class="detail-header">
          <div class="detail-name">{{ selectedAchievement.name }}</div>
          <el-tag
            :type="selectedAchievement.obtained ? 'success' : 'info'"
            size="small"
          >
            {{ selectedAchievement.obtained ? '已获得' : '未获得' }}
          </el-tag>
        </div>
        <div class="detail-section">
          <div class="detail-label">描述</div>
          <div class="detail-value">{{ selectedAchievement.description }}</div>
        </div>
        <div class="detail-section">
          <div class="detail-label">获得条件</div>
          <div class="detail-value">{{ selectedAchievement.condition || '完成指定任务' }}</div>
        </div>
        <div class="detail-section">
          <div class="detail-label">当前进度</div>
          <div class="detail-value">
            <div class="progress-bar large">
              <div
                class="progress-fill"
                :style="{ width: `${getProgressPercent(selectedAchievement)}%` }"
              ></div>
            </div>
            <div class="progress-text">
              {{ selectedAchievement.current_progress || 0 }} / {{ selectedAchievement.target_value || 1 }}
            </div>
          </div>
        </div>
        <div class="detail-section" v-if="selectedAchievement.obtained_at">
          <div class="detail-label">获得时间</div>
          <div class="detail-value">{{ formatTime(selectedAchievement.obtained_at) }}</div>
        </div>
        <div class="detail-section">
          <div class="detail-label">奖励积分</div>
          <div class="detail-value highlight">{{ selectedAchievement.points || 0 }}</div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { achievementApi } from '@/api'
import CountUp from './CountUp.vue'

const props = withDefaults(defineProps<{
  wallet: string
  showChallenges?: boolean
}>(), {
  showChallenges: false,
})

// 数据状态
const achievements = ref<any[]>([])
const challenges = ref<any[]>([])
const detailVisible = ref(false)
const selectedAchievement = ref<any>(null)
let refreshTimer: number | null = null

// 分类标签映射
const categoryLabels: Record<string, string> = {
  development: '开发技能',
  contract: '合约开发',
  chain: '链操作',
  eco: '绿色生态',
  nft: 'NFT 交易',
  training: '实训任务',
  advanced: '高级实战',
}

// 难度标签映射
const difficultyLabels: Record<string, string> = {
  easy: '简单',
  medium: '中等',
  hard: '困难',
}

// 计算属性
const achievedCount = computed(() => achievements.value.filter(a => a.obtained).length)
const totalPoints = computed(() => {
  return achievements.value
    .filter(a => a.obtained)
    .reduce((sum, a) => sum + (a.points || 0), 0)
})

const groupedAchievements = computed(() => {
  const groups: Record<string, any[]> = {}
  achievements.value.forEach(item => {
    const cat = item.category || 'other'
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(item)
  })
  return groups
})

const groupedChallenges = computed(() => {
  const groups: Record<string, any[]> = {}
  challenges.value.forEach(item => {
    const diff = item.difficulty || 'easy'
    if (!groups[diff]) groups[diff] = []
    groups[diff].push(item)
  })
  return groups
})

// 方法
function getProgressPercent(item: any): number {
  const current = item.current_progress || 0
  const target = item.target_value || 1
  return Math.min(100, Math.round((current / target) * 100))
}

function getChallengeProgress(challenge: any): number {
  const current = challenge.current_progress || 0
  const target = challenge.target_value || 1
  return Math.min(100, Math.round((current / target) * 100))
}

function difficultyTagType(difficulty: string): 'success' | 'warning' | 'danger' {
  const map: Record<string, 'success' | 'warning' | 'danger'> = {
    easy: 'success',
    medium: 'warning',
    hard: 'danger',
  }
  return map[difficulty] || 'info' as any
}

function formatTime(timestamp: string | number): string {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function showDetail(item: any) {
  selectedAchievement.value = item
  detailVisible.value = true
}

async function loadAchievements() {
  try {
    const res = await achievementApi.myAchievements()
    achievements.value = res.data || res || []
  } catch (error) {
    console.error('加载成就失败:', error)
  }
}

async function checkAchievements() {
  try {
    await achievementApi.check(props.wallet)
    await loadAchievements()
  } catch (error) {
    console.error('检查成就失败:', error)
  }
}

async function loadChallenges() {
  if (!props.showChallenges) return
  try {
    const res = await achievementApi.myChallenges()
    challenges.value = res.data || res || []
  } catch (error) {
    console.error('加载挑战任务失败:', error)
  }
}

async function startChallenge(challengeId: string) {
  try {
    await achievementApi.startChallenge(challengeId)
    ElMessage.success('挑战已开始')
    await loadChallenges()
  } catch (error) {
    console.error('开始挑战失败:', error)
  }
}

// 生命周期
onMounted(async () => {
  await Promise.all([
    loadAchievements(),
    checkAchievements(),
    loadChallenges(),
  ])

  // 每 30 秒自动刷新
  refreshTimer = window.setInterval(() => {
    loadAchievements()
    if (props.showChallenges) {
      loadChallenges()
    }
  }, 30000)
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
  }
})
</script>

<style scoped lang="scss">
.achievement-badge {
  padding: 20px;
  background: var(--dq-bg-2);
  border-radius: 12px;
  border: 1px solid var(--dq-border);
}

.stats-overview {
  display: flex;
  gap: 24px;
  margin-bottom: 24px;
  padding: 16px;
  background: var(--dq-bg);
  border-radius: 8px;
  border: 1px solid var(--dq-border);

  .stat-item {
    flex: 1;
    text-align: center;

    .stat-label {
      font-size: 12px;
      color: var(--dq-text-dim);
      margin-bottom: 8px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .stat-value {
      font-size: 24px;
      font-weight: 700;
      color: var(--dq-text);
      font-family: var(--dq-mono);

      &.highlight {
        color: var(--dq-primary);
        text-shadow: 0 0 10px var(--dq-primary-glow);
      }
    }
  }
}

.achievement-section {
  margin-bottom: 32px;

  .section-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--dq-text);
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--dq-border);
  }
}

.achievement-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;

  @media (min-width: 1200px) {
    grid-template-columns: repeat(4, 1fr);
  }

  @media (min-width: 768px) and (max-width: 1199px) {
    grid-template-columns: repeat(3, 1fr);
  }

  @media (max-width: 767px) {
    grid-template-columns: repeat(2, 1fr);
  }
}

.achievement-card {
  position: relative;
  padding: 16px;
  background: var(--dq-bg);
  border-radius: 8px;
  border: 2px solid var(--dq-border);
  cursor: pointer;
  transition: all 0.3s ease;
  display: flex;
  flex-direction: column;
  gap: 12px;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  }

  &.obtained {
    border-color: #ffd700;
    box-shadow: 0 0 20px rgba(255, 215, 0, 0.3);

    .achievement-icon {
      background: linear-gradient(135deg, #ffd700, #ffed4e);
    }
  }

  &.locked {
    filter: grayscale(0.6);
    opacity: 0.7;

    .achievement-icon {
      background: var(--dq-bg-2);
    }
  }
}

.achievement-icon {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--dq-primary), var(--dq-primary-2));
  flex-shrink: 0;

  .icon-text {
    font-size: 24px;
  }
}

.achievement-info {
  flex: 1;
  min-width: 0;

  .achievement-name {
    font-size: 14px;
    font-weight: 600;
    color: var(--dq-text);
    margin-bottom: 4px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .achievement-desc {
    font-size: 12px;
    color: var(--dq-text-dim);
    margin-bottom: 8px;
    line-height: 1.4;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
}

.progress-bar {
  height: 6px;
  background: var(--dq-bg-2);
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 4px;

  &.large {
    height: 10px;
  }

  .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--dq-primary), var(--dq-primary-2));
    border-radius: 3px;
    transition: width 0.3s ease;
    box-shadow: 0 0 8px var(--dq-primary-glow);
  }
}

.progress-text {
  font-size: 11px;
  color: var(--dq-text-dim);
  font-family: var(--dq-mono);
}

.achievement-status {
  position: absolute;
  top: 12px;
  right: 12px;
}

.challenges-section {
  margin-top: 32px;

  .section-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--dq-text);
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--dq-border);
  }
}

.difficulty-group {
  margin-bottom: 24px;

  .difficulty-label {
    font-size: 12px;
    font-weight: 600;
    color: var(--dq-text-dim);
    margin-bottom: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
}

.challenge-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.challenge-card {
  padding: 16px;
  background: var(--dq-bg);
  border-radius: 8px;
  border: 1px solid var(--dq-border);
  display: flex;
  flex-direction: column;
  gap: 12px;

  .challenge-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;

    .challenge-name {
      font-size: 14px;
      font-weight: 600;
      color: var(--dq-text);
      flex: 1;
    }
  }

  .challenge-desc {
    font-size: 12px;
    color: var(--dq-text-dim);
    line-height: 1.4;
  }

  .challenge-meta {
    display: flex;
    flex-direction: column;
    gap: 8px;

    .challenge-progress {
      flex: 1;
    }

    .challenge-reward {
      display: flex;
      align-items: center;
      gap: 4px;

      .reward-label {
        font-size: 12px;
        color: var(--dq-text-dim);
      }

      .reward-value {
        font-size: 14px;
        font-weight: 700;
        color: var(--dq-primary);
        font-family: var(--dq-mono);
      }
    }
  }

  .challenge-action {
    margin-top: 4px;
  }
}

.achievement-detail-dialog {
  .detail-content {
    display: flex;
    flex-direction: column;
    gap: 16px;

    .detail-icon {
      width: 64px;
      height: 64px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      background: linear-gradient(135deg, var(--dq-primary), var(--dq-primary-2));
      margin: 0 auto;

      .icon-text {
        font-size: 32px;
      }
    }

    .detail-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;

      .detail-name {
        font-size: 18px;
        font-weight: 700;
        color: var(--dq-text);
        flex: 1;
      }
    }

    .detail-section {
      display: flex;
      flex-direction: column;
      gap: 8px;

      .detail-label {
        font-size: 12px;
        font-weight: 600;
        color: var(--dq-text-dim);
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }

      .detail-value {
        font-size: 14px;
        color: var(--dq-text);
        line-height: 1.6;

        &.highlight {
          color: var(--dq-primary);
          font-weight: 700;
          font-size: 18px;
          font-family: var(--dq-mono);
        }
      }
    }
  }
}
</style>
