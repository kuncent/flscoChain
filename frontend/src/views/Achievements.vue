<template>
  <div class="achievements-page dq-enter-up">
    <!-- 页头：成就中心 -->
    <div class="page-hero dq-glass">
      <div class="ph-left">
        <div class="ph-badge">
          <span class="phb-dot"></span>
          成就系统 · 服务端自动核验
        </div>
        <h1 class="ph-title">
          成就中心 <span class="ph-title-ico">🏆</span>
        </h1>
        <p class="ph-desc">
          编译 / 部署 / 交易 / 生态活动 / 教程进度，全部由服务端按真实行为数据自动核验发放，无需手动打卡
        </p>
      </div>
      <div class="ph-right">
        <div class="ph-wallet">
          <div class="phw-k">当前钱包</div>
          <div class="phw-v dq-mono">{{ app.currentWallet || '—' }}</div>
        </div>
        <el-button size="small" @click="refresh" :loading="loading">
          <el-icon><Refresh /></el-icon>&nbsp;刷新核验
        </el-button>
      </div>
    </div>

    <div class="achv-grid">
      <!-- 左：成就墙 + 挑战任务（复用 AchievementBadge 组件展示逻辑） -->
      <div class="dq-card wall-card">
        <div class="card-head">
          <span class="title-icon">🎖️</span>
          <div>
            <div class="ct-title">成就墙 · 挑战任务</div>
            <div class="ct-sub">点击成就卡片查看达成条件与进度明细</div>
          </div>
          <span class="dq-tag info achv-mode-tag">{{ modeLabel }}</span>
        </div>
        <AchievementBadge :key="reloadKey" :wallet="app.currentWallet" :show-challenges="true" />
      </div>

      <!-- 右：积分排行榜 -->
      <div class="side-col">
        <div class="dq-card rank-card">
          <div class="card-head">
            <span class="title-icon">📊</span>
            <div>
              <div class="ct-title">积分排行榜</div>
              <div class="ct-sub">按已达成成就积分排序 · TOP 50</div>
            </div>
          </div>
          <div class="rank-list" v-if="leaderboard.length">
            <div
              class="rank-item"
              v-for="(r, i) in leaderboard"
              :key="r.wallet"
              :class="{ me: r.wallet === app.currentWallet, top3: i < 3 }"
            >
              <div class="ri-no dq-mono" :class="'no-' + (i + 1)">{{ rankLabel(i) }}</div>
              <div class="ri-info">
                <div class="ri-wallet dq-mono">{{ shortWallet(r.wallet) }}</div>
                <div class="ri-meta">{{ r.achievement_count }} 项成就</div>
              </div>
              <div class="ri-points dq-mono">{{ r.total_points }}</div>
            </div>
          </div>
          <el-empty v-else description="还没有人达成成就，抢先拿下一血吧" :image-size="70" />
        </div>

        <!-- 规则说明 -->
        <div class="dq-card rule-card">
          <div class="card-head">
            <span class="title-icon">📜</span>
            <div>
              <div class="ct-title">核验规则</div>
              <div class="ct-sub">成就与挑战如何被判定</div>
            </div>
          </div>
          <ul class="rule-list">
            <li><b>惰性自动</b>：打开本页即自动核验并发放成就，无需手动打卡</li>
            <li><b>真实数据源</b>：教程进度查搭链记录，交易数查链上交易，生态活动查发放记录</li>
            <li><b>挑战进度</b>：由服务端按行为记录重算，客户端上报无效，防止刷进度</li>
            <li><b>每日挑战</b>：统计开始挑战当天的行为；周期挑战统计开始后累计行为</li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onActivated } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { achievementApi } from '@/api'
import { useAppStore } from '@/stores/app'
import AchievementBadge from '@/components/AchievementBadge.vue'

const app = useAppStore()

const leaderboard = ref<any[]>([])
const loading = ref(false)
/* 切钱包 / 手动刷新时强制重建 AchievementBadge（其内部自拉数据，用 key 触发重新加载） */
const reloadKey = ref(0)

const modeLabel = computed(() =>
  app.chainMode === 'fisco' ? 'FISCO 链上核验'
    : app.chainMode === 'evm' ? 'EVM 链上核验'
      : '沙盒链路核验'
)

function rankLabel(i: number): string {
  return i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : String(i + 1)
}

function shortWallet(w: string): string {
  if (!w) return '—'
  return w.length > 16 ? `${w.slice(0, 10)}…${w.slice(-6)}` : w
}

async function loadLeaderboard() {
  loading.value = true
  try {
    const res: any = await achievementApi.stats()
    leaderboard.value = res?.leaderboard || []
  } catch {
    leaderboard.value = []
  } finally {
    loading.value = false
  }
}

function refresh() {
  reloadKey.value++
  loadLeaderboard()
}

onMounted(() => {
  loadLeaderboard()
})
onActivated(() => {
  loadLeaderboard()
})
</script>

<style scoped lang="scss">
.achievements-page { display: flex; flex-direction: column; gap: 14px; }

/* ================== 页头 ================== */
.page-hero {
  position: relative;
  overflow: hidden;
  display: flex; align-items: center; justify-content: space-between;
  gap: 18px;
  padding: 20px 24px;
  border: 1px solid var(--dq-border-2);
  border-radius: 14px;
  background:
    radial-gradient(600px 220px at 100% 0%, rgba(255,207,77,0.10), transparent 60%),
    radial-gradient(480px 200px at 0% 100%, rgba(0,230,195,0.09), transparent 60%),
    linear-gradient(135deg, rgba(11,16,30,0.92), rgba(8,12,22,0.96));
}
.ph-left { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.ph-badge {
  display: inline-flex; align-items: center; gap: 8px;
  align-self: flex-start;
  padding: 5px 12px;
  border-radius: 999px;
  background: rgba(255,207,77,0.10);
  border: 1px solid rgba(255,207,77,0.3);
  color: var(--dq-warn);
  font-size: 11.5px; font-weight: 500;
  .phb-dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--dq-warn);
    box-shadow: 0 0 6px rgba(255,207,77,0.8);
    animation: dq-pulse 1.8s ease-in-out infinite;
  }
}
.ph-title {
  margin: 0;
  font-size: 26px; font-weight: 800; letter-spacing: 0.5px;
  color: var(--dq-text);
  display: flex; align-items: center; gap: 10px;
  .ph-title-ico {
    font-size: 24px;
    filter: drop-shadow(0 0 12px rgba(255,207,77,0.4));
  }
}
.ph-desc { margin: 0; color: #a9b6d6; font-size: 12.5px; line-height: 1.6; }
.ph-right {
  display: flex; flex-direction: column; align-items: flex-end; gap: 10px;
  flex-shrink: 0;
}
.ph-wallet {
  padding: 8px 14px;
  border-radius: 10px;
  background: rgba(255,255,255,0.03);
  border: 1px solid var(--dq-border);
  text-align: right;
  .phw-k { font-size: 10.5px; color: var(--dq-text-dimmer); text-transform: uppercase; letter-spacing: 0.8px; }
  .phw-v { font-size: 13px; color: var(--dq-primary); margin-top: 2px; }
}

/* ================== 主体布局 ================== */
.achv-grid { display: grid; grid-template-columns: 1fr 320px; gap: 14px; align-items: start; }
.side-col { display: flex; flex-direction: column; gap: 14px; position: sticky; top: 0; }

.wall-card, .rank-card, .rule-card { padding: 16px 18px; }
.achv-mode-tag { margin-left: auto; font-family: var(--dq-mono); }

/* 通用卡片头（与 Dashboard 卡片风格一致） */
.card-head {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px dashed var(--dq-border);
  .title-icon {
    width: 32px; height: 32px; border-radius: 8px;
    background: linear-gradient(135deg, rgba(255,207,77,0.12), rgba(255,207,77,0.03));
    border: 1px solid rgba(255,207,77,0.22);
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 15px;
    flex-shrink: 0;
  }
  .ct-title { font-size: 14px; font-weight: 700; color: var(--dq-text); }
  .ct-sub { font-size: 11px; color: var(--dq-text-dimmer); margin-top: 1px; }
}

/* ================== 排行榜 ================== */
.rank-list { display: flex; flex-direction: column; gap: 6px; max-height: 420px; overflow-y: auto; }
.rank-item {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 12px;
  border-radius: 8px;
  border: 1px solid var(--dq-border);
  background: var(--dq-bg-2);
  transition: all .15s;
  &:hover { border-color: var(--dq-border-2); }
  &.me {
    border-color: rgba(0,230,195,0.45);
    background: linear-gradient(90deg, rgba(0,230,195,0.08), transparent);
    .ri-wallet { color: var(--dq-primary); }
  }
  &.top3 { border-color: rgba(255,207,77,0.28); }
}
.ri-no {
  width: 30px; text-align: center; flex-shrink: 0;
  font-size: 13px; font-weight: 700; color: var(--dq-text-dim);
  &.no-1 { color: #ffd700; }
  &.no-2 { color: #c0c0c0; }
  &.no-3 { color: #cd7f32; }
}
.ri-info { flex: 1; min-width: 0; }
.ri-wallet { font-size: 12px; color: var(--dq-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ri-meta { font-size: 10.5px; color: var(--dq-text-dimmer); margin-top: 2px; }
.ri-points {
  font-size: 15px; font-weight: 800; color: var(--dq-warn);
  text-shadow: 0 0 8px rgba(255,207,77,0.3);
  flex-shrink: 0;
}

/* ================== 规则说明 ================== */
.rule-list {
  margin: 0; padding-left: 18px;
  color: var(--dq-text-dim);
  font-size: 12px; line-height: 1.9;
  b { color: var(--dq-primary); font-weight: 600; }
  li::marker { color: var(--dq-primary); }
}

/* 响应式 */
@media (max-width: 1200px) {
  .achv-grid { grid-template-columns: 1fr; }
  .side-col { position: static; }
}
@media (max-width: 720px) {
  .page-hero { flex-direction: column; align-items: flex-start; }
  .ph-right { align-items: flex-start; }
  .ph-title { font-size: 22px; }
}
</style>
