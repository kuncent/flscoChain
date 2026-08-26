<template>
  <div class="dashboard dq-enter-up">

    <!-- 顶部：校园风 Hero 横幅（移除 ChainNetworkBG，直接用渐变背景兜底） -->
    <div class="hero">
      <div class="hero-overlay"></div>
      <div class="hero-content">
        <div class="hero-left">
          <div class="hero-badge">
            <span class="hb-dot"></span>
            区块链实训平台 · 联盟链方向
          </div>
          <h1 class="hero-title">
            你好，<span class="grad">同学</span> 👋
            <span class="hero-title-sub dq-mono">实训进度 {{ learnPercent }}%</span>
          </h1>
          <p class="hero-desc">从零搭建一条绿色低碳联盟链：启动节点 → 部署合约 → 6 角色运营 → 资产兑换 → 链上验证</p>
          <!-- 进度条直接内嵌到 Hero -->
          <div class="hero-progress">
            <div class="hp-bar">
              <div class="hp-fill" :style="{ width: learnPercent + '%' }"></div>
            </div>
            <div class="hp-labels">
              <span class="hp-l dq-mono">步骤 {{ learnedCount }} / 10</span>
              <span class="hp-r dq-mono">{{ remainingSteps }} 个模块待完成</span>
            </div>
          </div>
          <!-- 3 个核心数据卡：玻璃拟态 + CountUp -->
          <div class="hero-stats">
            <div class="dq-glass hs-item" @click="$router.push('/cloud')">
              <div class="hs-ico hs-c"><el-icon><Monitor /></el-icon></div>
              <div class="hs-info">
                <div class="hs-num dq-mono"><CountUp :target="cloudDoneSteps.length" /> / <CountUp :target="10" /></div>
                <div class="hs-label">搭链步骤完成</div>
              </div>
            </div>
            <div class="dq-glass hs-item" @click="$router.push('/contracts')">
              <div class="hs-ico hs-t"><el-icon><Files /></el-icon></div>
              <div class="hs-info">
                <div class="hs-num dq-mono"><CountUp :target="overview.contract_count ?? 0" /></div>
                <div class="hs-label">已部署智能合约</div>
              </div>
            </div>
            <div class="dq-glass hs-item" @click="$router.push('/wallet')">
              <div class="hs-ico hs-w"><el-icon><Wallet /></el-icon></div>
              <div class="hs-info">
                <div class="hs-num dq-mono"><CountUp :target="overview.tx_count ?? 0" /></div>
                <div class="hs-label">链上交易笔数</div>
              </div>
            </div>
          </div>
        </div>
        <div class="hero-right">
          <!-- 协议分布小饼条 + 链状态 -->
          <div class="dq-glass chain-card">
            <div class="chain-head">
              <span class="chain-title">实训链状态</span>
              <span class="dq-live"><span class="dot"></span>{{ chainRunning }}</span>
            </div>
            <div class="chain-body">
              <div class="chain-stat">
                <div class="dq-stat">
                  <div class="dq-stat__num"><CountUp :target="overview.height ?? app.chainHeight" /></div>
                  <div class="dq-stat__label">当前块高</div>
                </div>
              </div>
              <div class="chain-stat">
                <div class="dq-stat">
                  <div class="dq-stat__num accent"><CountUp :target="overview.tx_count ?? 0" /></div>
                  <div class="dq-stat__label">交易总数</div>
                </div>
              </div>
              <div class="chain-stat">
                <div class="dq-stat">
                  <div class="dq-stat__num info"><CountUp :target="overview.contract_count ?? 0" /></div>
                  <div class="dq-stat__label">部署合约</div>
                </div>
              </div>
            </div>
            <!-- 协议分布小饼条 -->
            <div class="chain-std" v-if="stdBreakdownKeys.length">
              <div class="cs-label dq-mono">协议分布</div>
              <div class="cs-bar">
                <div
                  class="cs-seg"
                  v-for="s in stdBreakdownKeys"
                  :key="s.name"
                  :class="s.cls"
                  :style="{ width: s.pct + '%' }"
                  :title="`${s.name}: ${s.n} 份`"
                ></div>
              </div>
              <div class="cs-legend">
                <span class="cs-lg" v-for="s in stdBreakdownKeys" :key="s.name">
                  <i class="cs-dot" :class="s.cls"></i>{{ s.name }}
                </span>
              </div>
            </div>
            <div class="chain-foot">
              <span class="cf-k">实训引擎</span>
              <span class="cf-v real" :class="app.chainMode">{{ modeLabel }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 平台实训进度看板（教师=班级整体 / 学生=个人+排名 / 管理员=全校概览） -->
    <section class="dq-card platform-card" v-if="platformData">
      <div class="pc-head">
        <div class="pc-title">
          <span class="pc-ico">📈</span>
          {{ platformData.scope === 'class' ? '班级实训进度看板' :
             platformData.scope === 'global' ? '全校实训进度概览' : '我的实训进度' }}
          <span class="dq-tag" v-if="platformData.scope === 'class'">教师视角 · 班级 {{ platformData.class_id }}</span>
          <span class="dq-tag accent" v-else-if="platformData.scope === 'global'">管理员视角</span>
        </div>
        <el-button size="small" plain @click="loadPlatformProgress" :loading="platformLoading">
          <el-icon><Refresh /></el-icon>&nbsp;刷新
        </el-button>
      </div>

      <!-- 教师：班级整体进度 -->
      <template v-if="platformData.scope === 'class'">
        <div class="pc-stats" v-if="platformData.total_students">
          <div class="pcs-item">
            <div class="pcs-num dq-mono">{{ platformData.total_students }}</div>
            <div class="pcs-label">班级人数</div>
          </div>
          <div class="pcs-item">
            <div class="pcs-num accent dq-mono">{{ platformData.avg_done_steps }} / 10</div>
            <div class="pcs-label">平均完成步数</div>
          </div>
          <div class="pcs-item">
            <div class="pcs-num dq-mono">{{ platformData.avg_progress_pct }}%</div>
            <div class="pcs-label">平均进度</div>
          </div>
          <div class="pcs-item">
            <div class="pcs-num success dq-mono">{{ platformData.avg_training_score }}</div>
            <div class="pcs-label">平均实训成绩</div>
          </div>
        </div>
        <!-- 各步完成率柱状条 -->
        <div class="pc-steps" v-if="platformData.step_completion?.length">
          <div class="pc-step-row" v-for="(cnt, i) in platformData.step_completion" :key="i">
            <span class="psr-label dq-mono">步骤 {{ i + 1 }}</span>
            <div class="psr-bar">
              <div class="psr-fill" :style="{ width: (platformData.total_students ? (cnt / platformData.total_students * 100) : 0) + '%' }"></div>
            </div>
            <span class="psr-count dq-mono">{{ cnt }}/{{ platformData.total_students }}</span>
          </div>
        </div>
        <!-- 学生明细列表 -->
        <div class="pc-students" v-if="platformData.items?.length">
          <div class="pcs-table">
            <div class="pcs-th">
              <span class="pcs-td-name">姓名（学号）</span>
              <span class="pcs-td-prog">完成进度</span>
              <span class="pcs-td-score">实训成绩</span>
              <span class="pcs-td-final">综合成绩</span>
            </div>
            <div class="pcs-tr" v-for="s in platformData.items" :key="s.user_id">
              <span class="pcs-td-name">{{ s.name }}（{{ s.student_id }}）</span>
              <span class="pcs-td-prog">
                <div class="mini-bar"><div class="mini-fill" :style="{ width: s.progress_pct + '%' }"></div></div>
                <span class="dq-mono">{{ s.done_steps }}/10</span>
              </span>
              <span class="pcs-td-score dq-mono accent">{{ s.training_score }}</span>
              <span class="pcs-td-final dq-mono success">{{ s.final_score }}</span>
            </div>
          </div>
        </div>
        <el-empty v-else description="暂无同班学生数据（学生登录后自动同步）" :image-size="80" />
      </template>

      <!-- 管理员：全校概览 -->
      <template v-else-if="platformData.scope === 'global'">
        <div class="pc-stats">
          <div class="pcs-item">
            <div class="pcs-num dq-mono">{{ platformData.total_students }}</div>
            <div class="pcs-label">学生总数</div>
          </div>
          <div class="pcs-item">
            <div class="pcs-num accent dq-mono">{{ platformData.total_classes }}</div>
            <div class="pcs-label">班级数</div>
          </div>
          <div class="pcs-item">
            <div class="pcs-num dq-mono">{{ platformData.avg_done_steps }} / 10</div>
            <div class="pcs-label">平均完成步数</div>
          </div>
          <div class="pcs-item">
            <div class="pcs-num success dq-mono">{{ platformData.avg_progress_pct }}%</div>
            <div class="pcs-label">全校平均进度</div>
          </div>
        </div>
        <div class="pc-steps" v-if="platformData.step_completion?.length">
          <div class="pc-step-row" v-for="(cnt, i) in platformData.step_completion" :key="i">
            <span class="psr-label dq-mono">步骤 {{ i + 1 }}</span>
            <div class="psr-bar">
              <div class="psr-fill" :style="{ width: (platformData.total_students ? (cnt / platformData.total_students * 100) : 0) + '%' }"></div>
            </div>
            <span class="psr-count dq-mono">{{ cnt }}/{{ platformData.total_students }}</span>
          </div>
        </div>
      </template>

      <!-- 学生：个人进度 + 班级排名 -->
      <template v-else>
        <div class="pc-stats">
          <div class="pcs-item">
            <div class="pcs-num accent dq-mono">{{ platformData.done_steps }} / 10</div>
            <div class="pcs-label">已完成步骤</div>
          </div>
          <div class="pcs-item">
            <div class="pcs-num dq-mono">{{ platformData.progress_pct }}%</div>
            <div class="pcs-label">总进度</div>
          </div>
          <div class="pcs-item">
            <div class="pcs-num dq-mono">{{ platformData.event_count }}</div>
            <div class="pcs-label">学习行为数</div>
          </div>
          <div class="pcs-item" v-if="platformData.class_total">
            <div class="pcs-num success dq-mono">{{ platformData.class_rank }} / {{ platformData.class_total }}</div>
            <div class="pcs-label">班级排名</div>
          </div>
        </div>
      </template>
    </section>

    <!-- 下半部分：双栏（左：学习路径 右：今日任务 + 快速入口） -->
    <div class="main-grid">

      <!-- 左：9 步学习路径 — 垂直时间轴 -->
      <div class="dq-card path-card">
        <div class="path-head">
          <div class="path-title">
            <span class="title-ico"><el-icon><Guide /></el-icon></span>
            <div>
              <div class="path-t">学习路径 · 4 阶段 · 10 步搭建绿色低碳联盟链</div>
              <div class="path-s">完成 ✓ · 当前脉冲 · 每步含 目标/锚点/验收</div>
            </div>
          </div>
          <div class="path-progress-tag">
            <span class="dq-mono">{{ learnedCount }}</span> / <span class="dq-mono">10</span>
          </div>
        </div>
        <!-- 垂直时间轴 -->
        <div class="path-timeline">
          <div
            class="tl-step"
            v-for="(p, i) in pathSteps"
            :key="p.to"
            :class="{
              done: isStepDone(p),
              cur: i === currentStepIndex,
              locked: !isStepDone(p) && i !== currentStepIndex,
            }"
            @click="goStep(p.to)"
          >
            <!-- 左侧时间轴节点 -->
            <div class="tl-side">
              <div class="tl-node">
                <el-icon v-if="isStepDone(p)" class="tln-check"><Check /></el-icon>
                <span v-else class="tln-idx">{{ i + 1 }}</span>
              </div>
              <div class="tl-line" v-if="i < pathSteps.length - 1"></div>
            </div>
            <!-- 右侧主体卡片 -->
            <div class="tl-body">
              <div class="tlb-head">
                <div class="tlb-title-row">
                  <el-icon class="tlb-ico"><component :is="p.icon" /></el-icon>
                  <span class="tlb-title">{{ p.title }}</span>
                  <span class="dq-tag lvl {{ LEVEL_TAG[p.level].cls }}">{{ LEVEL_TAG[p.level].label }}</span>
                  <span class="dq-tag eta-tag">⏱ {{ p.eta }}</span>
                  <span class="dq-tag" :class="p.tagClass" v-if="p.tag">{{ p.tag }}</span>
                </div>
                <span class="tlb-badge" v-if="i === currentStepIndex && !isStepDone(p)">
                  <el-icon><VideoPlay /></el-icon> 进行中
                </span>
                <span class="tlb-badge ok" v-else-if="isStepDone(p)">
                  <el-icon><CircleCheckFilled /></el-icon> 已完成
                </span>
                <span class="tlb-badge lock" v-else>
                  <el-icon><Lock /></el-icon> 待解锁
                </span>
              </div>
              <p class="tlb-desc">{{ p.desc }}</p>
              <div class="tlb-tags">
                <span class="ps-sub-tag" v-for="k in p.keywords" :key="k">#{{ k }}</span>
              </div>
              <!-- 学习目标 + 知识点 + 验收条件（三步法） -->
              <div class="tlb-learn-block">
                <div class="lb-row">
                  <span class="lb-k">🎯 目标</span>
                  <span class="lb-v">{{ p.goal }}</span>
                </div>
                <div class="lb-row">
                  <span class="lb-k">📚 锚点</span>
                  <div class="lb-kps">
                    <span class="kp-chip" v-for="(kp, idx) in p.kpoints" :key="idx">{{ kp }}</span>
                  </div>
                </div>
                <div class="lb-row">
                  <span class="lb-k">✅ 验收</span>
                  <ul class="lb-ul">
                    <li v-for="(a, idx) in p.accept" :key="idx">{{ a }}</li>
                  </ul>
                </div>
              </div>
              <div class="tlb-action">
                <el-button
                  v-if="i === currentStepIndex"
                  type="primary"
                  size="small"
                  @click.stop="goStep(p.to)"
                >
                  开始学习 <el-icon><Right /></el-icon>
                </el-button>
                <el-button v-else-if="isStepDone(p)" size="small" @click.stop="goStep(p.to)">
                  复习回顾
                </el-button>
                <el-button v-else size="small" :disabled="false" @click.stop="goStep(p.to)">
                  提前预览
                </el-button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右：今日任务 + 快速入口 -->
      <div class="side-col">

        <!-- 今日任务（自适应阶段：基础搭建 → 联盟运营 10 微任务） -->
        <div class="dq-card todo-card">
          <div class="card-head">
            <span class="title-icon">{{ l4Done ? '🌿' : '⛓️' }}</span>
            <div>
              <div class="ct-title">{{ l4Done ? '联盟运营 · 10 微任务' : '今日任务 · 基础搭建' }}</div>
              <div class="ct-sub">
                {{ todoDoneCount }}/{{ todos.length }} 已完成
                <span v-if="l4Done" class="ct-phase-hint">
                  · 阶段 1 激活 · 阶段 2 发能量 · 阶段 3 兑换 NFT
                </span>
              </div>
            </div>
            <div class="ct-progress dq-mono" :class="{ 'l5-mode': l4Done }">{{ todoPercent }}%</div>
          </div>
          <div class="todo-list" :class="{ 'l5-list': l4Done }">
            <div
              class="todo-item"
              v-for="(t, i) in todos"
              :key="i"
              :class="{ done: t.done, 'l5-item': l4Done }"
              @click="l4Done ? toggleTodo(t) : (t.done || $router.push(t.to))"
            >
              <div class="ti-check" :class="{ 'l5-check': l4Done }">
                <i class="tic-box"></i>
                <el-icon class="tic-check-icon" v-if="t.done"><Check /></el-icon>
              </div>
              <div class="ti-info">
                <div class="ti-title">{{ t.title }}</div>
                <div class="ti-desc">{{ t.desc }}</div>
                <div class="ti-hint dq-mono">{{ t.hint }}</div>
              </div>
              <div class="ti-badge">
                <span class="dq-tag" :class="t.klass">{{ t.label }}</span>
              </div>
            </div>
          </div>
          <div class="todo-foot" v-if="l4Done">
            <span class="tf-k dq-mono">运营路线</span>
            <div class="tf-phases">
              <span class="tf-p p1">Phase1 系统激活 · T1~T2</span>
              <span class="tf-p p2">Phase2 能量发放 · T3~T7</span>
              <span class="tf-p p3">Phase3 资产兑换 · T8~T10</span>
            </div>
          </div>
        </div>

        <!-- 快速入口 -->
        <div class="dq-card quick-card">
          <div class="card-head">
            <span class="title-icon">⚡</span>
            <div>
              <div class="ct-title">快速开始</div>
              <div class="ct-sub">常用实训工具，直接进入</div>
            </div>
          </div>
          <div class="quick-grid">
            <div class="qi" @click="$router.push('/cloud')">
              <div class="qi-ico"><el-icon><Monitor /></el-icon></div>
              <span>搭链</span>
            </div>
            <div class="qi" @click="$router.push('/ide')">
              <div class="qi-ico"><el-icon><EditPen /></el-icon></div>
              <span>写合约</span>
            </div>
            <div class="qi" @click="$router.push('/interfaces')">
              <div class="qi-ico"><el-icon><Connection /></el-icon></div>
              <span>调接口</span>
            </div>
            <div class="qi" @click="$router.push('/explorer')">
              <div class="qi-ico"><el-icon><Search /></el-icon></div>
              <span>浏览器</span>
            </div>
            <div class="qi" @click="$router.push('/wallet')">
              <div class="qi-ico"><el-icon><Wallet /></el-icon></div>
              <span>发币</span>
            </div>
            <div class="qi" @click="$router.push('/nft')">
              <div class="qi-ico"><el-icon><Picture /></el-icon></div>
              <span>NFT</span>
            </div>
          </div>
        </div>

      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onActivated, watch, reactive, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Check, Right, Monitor, Files, Wallet, Guide, VideoPlay, CircleCheckFilled, Lock, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { chainApi, explorerApi, authApi } from '@/api'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import CountUp from '@/components/CountUp.vue'

const app = useAppStore()
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const overview = ref<any>({})

/* 平台实训进度看板（教师=班级 / 学生=个人+排名 / 管理员=全校） */
const platformData = ref<any>(null)
const platformLoading = ref(false)
async function loadPlatformProgress() {
  platformLoading.value = true
  try {
    platformData.value = await authApi.platformProgress()
  } catch {
    platformData.value = null
  } finally {
    platformLoading.value = false
  }
}

/* 链模式文案与状态 */
const modeLabel = computed(() => {
  const m = app.chainMode
  if (m === 'fisco') return 'FISCO-BCOS · 联盟链节点'
  if (m === 'evm')   return 'EVM · 进程内虚拟机链路'
  return '本地沙盒 · 预置教学链路'
})
const chainRunning = computed(() => {
  const h = (overview.value.height ?? app.chainHeight) || 0
  return h > 0 ? '链运行中' : '链就绪'
})

/* 协议分布小饼条 */
const stdBreakdownKeys = computed(() => {
  const bd: any = overview.value.standard_breakdown || {}
  const entries = Object.entries(bd) as [string, number][]
  const total = entries.reduce((a, [, n]) => a + (Number(n) || 0), 0)
  if (!total || !entries.length) return []
  function cls(name: string) {
    const s = name.toLowerCase()
    if (s.includes('erc20'))   return 's-erc20'
    if (s.includes('erc721'))  return 's-erc721'
    if (s.includes('erc1155')) return 's-erc1155'
    return 's-custom'
  }
  return entries.map(([name, n]) => ({
    name,
    n: Number(n) || 0,
    pct: Math.round(((Number(n) || 0) / total) * 100),
    cls: cls(name),
  }))
})

function goStep(to: string) {
  router.push(to)
}

/* ---------- 联盟链搭建实训：10 步学习路径 ----------
   整个实训围绕一个真实项目：搭建联盟链
   阶段 1 · 链底层搭建（步骤 1-2）：启动节点 + 部署 GreenEnergy
   阶段 2 · 业务合约开发（步骤 3-5）：IDE + 合约管理 + 接口调试
   阶段 3 · 联盟治理与运营（步骤 6-8）：6 角色 + 能量发放 + 资产兑换
   阶段 4 · 链上验证（步骤 9-10）：监听器 + 浏览器 + 报告
*/
const LEVEL_TAG: Record<string, { label: string; cls: string; desc: string }> = {
  P1: { label: '阶段1·链底层', cls: 'lvl-l1', desc: '搭建联盟链节点 + 部署核心代币合约' },
  P2: { label: '阶段2·合约开发', cls: 'lvl-l2', desc: '开发/部署/调试 3 份业务合约' },
  P3: { label: '阶段3·联盟运营', cls: 'lvl-l4', desc: '6 角色权限 + 能量发放 + 资产兑换闭环' },
  P4: { label: '阶段4·链上验证', cls: 'lvl-l3', desc: '监听业务调用 + 浏览器查链上数据' },
}
type PathStep = {
  to: string; icon: string; title: string; desc: string;
  keywords: string[]; tag?: string; tagClass?: string;
  level: 'P1' | 'P2' | 'P3' | 'P4';
  goal: string;
  kpoints: string[];
  accept: string[];
  eta: string;
  extraDone?: () => boolean;
}
const pathSteps: PathStep[] = [
  { to: '/dashboard', icon: 'DataBoard', level: 'P1',
    title: '总览 · 绿色低碳联盟链项目', desc: '了解项目全貌：6 个联盟成员、3 份智能合约、能量发放→兑换闭环',
    keywords: ['项目全貌', '6 角色联盟', '3 合约体系'], tag: '起点', tagClass: '',
    eta: '5 分钟',
    goal: '能复述绿色低碳联盟链的业务架构：谁发能量、谁兑换、能量如何流转',
    kpoints: ['联盟成员：管理员/地铁/公交/单车/外卖/回收 6 组织', 'GreenEnergy(ERC20) → 能量代币；PlantCertificate(ERC721) → 植树证书；EcoBadge(ERC1155) → 勋章/骑行券', '商业闭环：低碳行为→发能量→累积→兑换 NFT 资产→能量回收'],
    accept: ['阅读本页所有步骤描述', '明确下一步是"搭建链底层"'],
  },
  { to: '/cloud', icon: 'Monitor', level: 'P1',
    title: '搭建链底层 · 10 步搭链', desc: '启动 4 节点联盟链 → 6 联盟组织接入 → 部署 GreenEnergy → 6 角色发能量链路验证',
    keywords: ['FISCO-BCOS', 'PBFT', 'GreenEnergy', '节点启动'], tag: '必修', tagClass: '',
    eta: '30 分钟',
    goal: '亲手搭建一条联盟链并部署绿色能量代币合约',
    kpoints:['4 节点 PBFT 共识：3f+1 容错', 'build_chain.sh 一键生成节点配置', 'GreenEnergy 构造函数：initialSupply=1000000', 'deploy → name/balanceOf/transfer 验证'],
    accept: ['完成 10/10 步骤', '成功部署 GreenEnergy 合约', '调用 name() 返回 GreenEnergy', '完成 6 角色发能量链路验证'],
    extraDone: () => isCloudAllDone.value,
  },
  { to: '/ide', icon: 'EditPen', level: 'P2',
    title: '开发业务合约 · PlantCertificate + EcoBadge', desc: '从内置模板起步：查看 GreenEnergy/PlantCertificate/EcoBadge 源码 → Solc 编译 → 部署',
    keywords: ['Solidity', 'ERC721', 'ERC1155', '编译部署'],
    eta: '15 分钟',
    goal: '理解 3 份业务合约的 Solidity 实现并独立编译部署',
    kpoints: ['PlantCertificate(ERC721)：每份证书唯一，含树种 ID + URI', 'EcoBadge(ERC1155)：半同质化，badge ID=1 勋章 / ID=2 骑行券', 'GreenEnergy(ERC20)：mint(to,value,reason) 向用户发放能量'],
    accept: ['至少查看 3 份内置合约源码', '独立编译成功 ≥1 次', '成功部署 PlantCertificate 或 EcoBadge'],
  },
  { to: '/contracts', icon: 'Files', level: 'P2',
    title: '管理已部署合约 · 3 合约体系', desc: '查看 GreenEnergy / PlantCertificate / EcoBadge 部署状态，确认 3 合约全部就绪',
    keywords: ['合约地址', 'ERC20/721/1155', '部署状态'],
    eta: '5 分钟',
    goal: '确认 3 份系统合约全部部署成功，记录合约地址',
    kpoints: ['GreenEnergy：绿色能量代币（ERC20）', 'PlantCertificate：植树证书（ERC721）', 'EcoBadge：生态勋章+骑行券（ERC1155）'],
    accept: ['3/3 合约全部部署', '能区分 3 种代币标准的用途'],
  },
  { to: '/interfaces', icon: 'Connection', level: 'P2',
    title: '接口调试 · 验证合约方法', desc: '通过 ABI 调试 GreenEnergy.mint() / PlantCertificate.mint() / EcoBadge.mint() 等核心方法',
    keywords: ['ABI', 'mint', 'balanceOf', 'view vs send'],
    eta: '10 分钟',
    goal: '能用在线接口独立完成"读 + 写"两类合约调用',
    kpoints: ['GreenEnergy.mint(to,value,reason) → 发放能量', 'PlantCertificate.mint(to,tokenId,speciesId,uri) → 铸造证书', 'call（只读不花 Gas）vs send（写上链花 Gas）'],
    accept: ['成功调用 ≥1 个 view 方法（如 balanceOf）', '成功调用 ≥1 个写方法并上链'],
  },
  { to: '/eco', icon: 'Promotion', level: 'P3',
    title: '联盟治理与运营 · 6 角色 + 能量 + 兑换', desc: '配置 6 大联盟角色权限 → 5 种低碳场景发放绿色能量 → 兑换植树证书/勋章/骑行券',
    keywords: ['角色权限', '能量发放', '资产兑换', '商业闭环'], tag: '核心', tagClass: 'accent',
    eta: '40 分钟',
    goal: '完成绿色低碳联盟链的完整商业闭环：角色→发能量→兑换→回收',
    kpoints: ['6 角色：管理员(管理树种) / 地铁(50) / 公交(20) / 单车(15) / 外卖(10) / 回收(100)', '能量发放：各角色按业务规则向用户钱包 mint 绿色能量', '兑换闭环：能量→transfer(admin)→mint NFT 证书/勋章，能量回收至管理员'],
    accept: ['完成 6/6 角色切换体验', '能量发放 ≥3 种不同角色', '兑换 ≥2 类不同资产（证书/勋章/骑行券）'],
  },
  { to: '/wallet', icon: 'Wallet', level: 'P3',
    title: '能量钱包 · 查询绿色能量余额', desc: '查询钱包中的 GreenEnergy 余额、能量转账记录、辅助理解能量流转',
    keywords: ['余额查询', '能量流转', 'ERC20'], tag: '工具', tagClass: 'info',
    eta: '5 分钟',
    goal: '能独立查询任意地址的绿色能量余额并理解能量流向',
    kpoints: ['balanceOf(address) 查询能量余额', 'transfer(to,amount) 发起链上能量转账', '能量从联盟成员→用户→管理员（兑换回收）的流转路径'],
    accept: ['成功查询 ≥1 个地址的能量余额', '理解能量"发放→累积→消耗"的流转模型'],
  },
  { to: '/nft', icon: 'Picture', level: 'P3',
    title: '绿色资产市场 · NFT 铸造与交易', desc: '铸造 ERC721/1155 绿色资产 NFT、上架交易，辅助理解植树证书/勋章的 NFT 本质',
    keywords: ['NFT 铸造', 'ERC721', 'ERC1155', '资产交易'], tag: '工具', tagClass: 'info',
    eta: '10 分钟',
    goal: '理解植树证书和生态勋章本质上就是 ERC721/ERC1155 NFT',
    kpoints: ['ERC721：每件 NFT 唯一（如植树证书）', 'ERC1155：同类批量（如勋章/骑行券）', 'mint + safeTransferFrom 的资产流转机制'],
    accept: ['成功铸造 ≥1 件 NFT', '理解证书/勋章与 NFT 的对应关系'],
  },
  { to: '/monitor', icon: 'BellFilled', level: 'P4',
    title: '调用监听器 · 监控业务调用', desc: '观察能量发放、资产兑换的合约调用次数、方法分布、失败率，复盘业务运行',
    keywords: ['调用统计', '方法分布', 'Gas 消耗', '失败率'],
    eta: '5 分钟',
    goal: '会用监听器定位"哪个角色发了多少能量、兑换是否成功"',
    kpoints: ['最近调用列表：按时间倒序', '失败调用标红（status=0）', '方法分布可辅助发现异常调用模式'],
    accept: ['能在列表中找到自己刚才的 mint/transfer 调用', '理解 status=1 成功 / 0 失败的含义'],
  },
  { to: '/explorer', icon: 'Search', level: 'P4',
    title: '区块链浏览器 · 链上验证', desc: '按高度查块、按 hash 查交易，验证能量发放和资产兑换真的上链了',
    keywords: ['区块查询', '交易解码', '事件日志', '链上验证'],
    eta: '5 分钟',
    goal: '能独立用浏览器验证"一笔能量发放交易真的上链了"',
    kpoints: ['区块：height / timestamp / txRoot', '交易：from / to / input data 解码', 'Receipt：logs 事件（Transfer / Mint）'],
    accept: ['输入一笔 tx_hash 查到对应交易', '能解码出 Transfer 事件参数'],
  },
]

/* ---------- 持久化存储键（注意：必须与 CloudDesktop / NftMarket 保持完全一致） ---------- */
const VISIT_KEY = 'learn_visited_v1'
const CLOUD_STEP_KEY = 'cloud_done_v1'        // 与 CloudDesktop.vue 第 124 行 DONE_KEY 保持一致
const COMPLETED_KEY = 'learn_completed_steps_v1'
const NFT_COUNT_KEY = 'learn_nft_count_v1'    // 与 NftMarket.vue 第 197 行保持一致

/* ---------- 响应式状态：访问 / 达标 ---------- */
function loadVisited(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(VISIT_KEY)
    const arr = raw ? JSON.parse(raw) : []
    const list: string[] = Array.isArray(arr) ? arr.filter((x: unknown) => typeof x === 'string') : []
    const obj: Record<string, boolean> = { '/dashboard': true }
    list.forEach((p) => (obj[p] = true))
    try { if (route.path) obj[route.path] = true } catch { /* noop */ }
    return obj
  } catch {
    return { '/dashboard': true }
  }
}
const visited = reactive<Record<string, boolean>>(loadVisited())
const persistVisited = () => {
  try {
    const arr = Object.keys(visited).filter((k) => visited[k])
    localStorage.setItem(VISIT_KEY, JSON.stringify(arr))
  } catch { /* noop */ }
}
watch(
  () => route.path,
  (p) => {
    if (p && !visited[p]) {
      visited[p] = true
      persistVisited()
    }
    // 每次进入 /dashboard（从云桌面/其他页面跳回）都立刻刷新本地存储快照，
    // 避免同 tab 下 storage event 不触发导致状态不同步
    if (p === '/dashboard') {
      refreshCompleted()
    }
  },
  { immediate: true },
)

const cloudDoneSteps = ref<number[]>([])
const CLOUD_TOTAL = 10
const isCloudAllDone = computed(() => cloudDoneSteps.value.length >= CLOUD_TOTAL)
async function loadCloudSteps() {
  // 本地 localStorage 已完成步骤（旧数据、自证完成等）
  const localSet = new Set<number>()
  try {
    const raw = localStorage.getItem(CLOUD_STEP_KEY)
    const arr = raw ? JSON.parse(raw) : []
    if (Array.isArray(arr)) arr.forEach((x: unknown) => { if (typeof x === 'number') localSet.add(x) })
  } catch {
    /* ignore */
  }
  // 服务端持久化完成步骤（chain_tutorial_progress 表）—— 换设备可续学
  try {
    const wallet = app.currentWallet || '0xlearner'
    const p = await chainApi.progress(wallet)
    if (p && Array.isArray(p.steps)) {
      p.steps.forEach((s: { step: number; done?: boolean }) => { if (s.done) localSet.add(s.step) })
    }
  } catch {
    /* 后端未就绪时，只展示本地进度 */
  }
  cloudDoneSteps.value = Array.from(localSet).sort((a, b) => a - b)
  // 同步回 localStorage，保证其它页面读值一致（并集写回）
  try {
    localStorage.setItem(CLOUD_STEP_KEY, JSON.stringify(cloudDoneSteps.value))
  } catch { /* quota ignore */ }
}

function loadCompleted(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(COMPLETED_KEY)
    const arr = raw ? JSON.parse(raw) : []
    const list: string[] = Array.isArray(arr) ? arr.filter((x: unknown) => typeof x === 'string') : []
    const obj: Record<string, boolean> = {}
    list.forEach((p) => (obj[p] = true))
    return obj
  } catch {
    return {}
  }
}
const completed = reactive<Record<string, boolean>>(loadCompleted())
const persistCompleted = () => {
  try {
    const arr = Object.keys(completed).filter((k) => completed[k])
    localStorage.setItem(COMPLETED_KEY, JSON.stringify(arr))
  } catch { /* noop */ }
}

const nftCount = ref<number>(0)
function loadNftCount() {
  try {
    const raw = localStorage.getItem(NFT_COUNT_KEY)
    nftCount.value = raw ? Number(raw) || 0 : 0
  } catch {
    nftCount.value = 0
  }
}

async function refreshCompleted() {
  try {
    await loadCloudSteps()
    loadNftCount()
    loadPlatformProgress()  // 登录后展示平台整体实训进度（教师=班级 / 学生=个人+排名）
    let changed = false
    for (const s of pathSteps) {
      let ok = !!visited[s.to]
      if (s.extraDone) ok = ok && s.extraDone()
      if (ok && !completed[s.to]) {
        completed[s.to] = true
        changed = true
      }
    }
    if (changed) persistCompleted()
  } catch {
    /* ignore storage / serialization failures during refresh */
  }
}
onMounted(refreshCompleted)
onActivated(refreshCompleted)

/* ---------- SSO Token 自动登录 ----------
 * 适用于智云 SSO 回调，URL 形如：
 *   - http://domain/?token=xxx（URL 级参数，位于 hash 之前）
 *   - http://domain/#/dashboard?token=xxx（hash 级参数）
 * 无论是否已登录，URL 带 token 就重新登录（覆盖旧会话 / 刷新会话）。
 *
 * 设计：不阻塞 Dashboard 渲染 — 页面首访时 Vite 异步编译组件 + SSO 网络往返
 * 叠加会导致长时间空白。改为后台静默登录，登录完成后刷新数据，用户无感。
 */
onMounted(async () => {
  const ssoToken =
    new URLSearchParams(window.location.search).get('token') ||
    (route.query.token as string) ||
    ''
  if (!ssoToken) return
  try {
    const u = await auth.loginByToken(ssoToken)
    // 清理 URL 上的 token（hash 与 search 都清）
    const cleanUrl = window.location.origin + window.location.pathname + window.location.hash.split('?')[0]
    window.history.replaceState(null, '', cleanUrl)
    ElMessage.success(`欢迎回来，${u.name || u.username}`)
    // 登录成功后静默刷新数据（用新身份重新拉取 overview / platformProgress）
    await loadOverview()
    refreshCompleted()
  } catch {
    // SSO 失败，回退到登录页（http 拦截器已提示错误原因）
    router.replace('/login')
  }
})

/* 单步是否完成（独立判断，不要求前缀连续） */
function isStepDone(s: typeof pathSteps[0]): boolean {
  let ok = !!visited[s.to]
  if (s.extraDone) ok = ok && s.extraDone()
  return ok
}
/* 已完成总数（独立计数，不受其他步骤影响） */
const learnedCount = computed(() => pathSteps.filter((s) => isStepDone(s)).length)
/* 当前推荐步骤 = 第一个未完成的 */
const currentStepIndex = computed(() => {
  const idx = pathSteps.findIndex((s) => !isStepDone(s))
  return idx === -1 ? pathSteps.length : idx
})
const learnPercent = computed(() => Math.round((learnedCount.value / pathSteps.length) * 100))
const remainingSteps = computed(() => Math.max(0, pathSteps.length - learnedCount.value))

/* ---------- 今日任务（自适应：根据当前阶段推荐 或 展示 L5 高级实战 10 微任务） ---------- */
/* 高级实战 10 微任务：把 45 分钟的大场景拆成 10 个可交付的小步骤（每步 3~5 分钟） */
type MicroTask = { phase: 'L5-1'|'L5-2'|'L5-3'; title: string; desc: string; label: string; klass: string; hint: string; to: string; key: string }
const L5_MICRO_TASKS: MicroTask[] = [
  // Phase 1：系统激活（2 步）
  { phase: 'L5-1', to: '/eco', key: 'eco_t1',
    title: 'T1 · 管理员激活系统合约',
    desc: '切换到管理员 → 一键激活 3 份系统合约（能量代币 / 证书 / 勋章）',
    label: '4 分钟', klass: 'lvl-l5-1',
    hint: '目标：3/3 合约激活（报告 H 项 5 分）' },
  { phase: 'L5-1', to: '/eco', key: 'eco_t2',
    title: 'T2 · 体验 6 大角色全览',
    desc: '依次切换管理员 / 地铁 / 公交 / 单车 / 外卖 / 回收 6 个角色',
    label: '5 分钟', klass: 'lvl-l5-1',
    hint: '目标：6/6 角色体验（报告 E 项 10 分满分）' },
  // Phase 2：能量发放（5 种真实场景）
  { phase: 'L5-2', to: '/eco', key: 'eco_t3',
    title: 'T3 · 地铁集团发放 · 通勤 10 公里',
    desc: '切到「地铁」角色 → 向学习者钱包发放绿色能量（metro 场景）',
    label: '3 分钟', klass: 'lvl-l5-2',
    hint: '场景体验：≥1 种发放（F 项起步 3 分）' },
  { phase: 'L5-2', to: '/eco', key: 'eco_t4',
    title: 'T4 · 公交公司发放 · 换乘 2 次',
    desc: '切到「公交」角色 → 向学习者钱包发放绿色能量（bus 场景）',
    label: '3 分钟', klass: 'lvl-l5-2',
    hint: '目标：≥2 种不同角色（F 项 6 分）' },
  { phase: 'L5-2', to: '/eco', key: 'eco_t5',
    title: 'T5 · 共享单车发放 · 骑行 5 公里',
    desc: '切到「共享单车」角色 → 发放绿色能量（bike 场景）',
    label: '3 分钟', klass: 'lvl-l5-2',
    hint: '目标：≥3 种不同角色（F 项 10 分满分）' },
  { phase: 'L5-2', to: '/eco', key: 'eco_t6',
    title: 'T6 · 外卖平台发放 · 无需餐具',
    desc: '切到「外卖平台」角色 → 发放绿色能量（takeout 场景）',
    label: '3 分钟', klass: 'lvl-l5-2',
    hint: '能量多样性：≥4 种 → G 项 +3 加分' },
  { phase: 'L5-2', to: '/eco', key: 'eco_t7',
    title: 'T7 · 回收公司发放 · 快递纸箱回收',
    desc: '切到「回收公司」角色 → 发放绿色能量（recycle 场景）',
    label: '3 分钟', klass: 'lvl-l5-2',
    hint: '能量发放 diversity 满分达成' },
  // Phase 3：资产兑换（3 种 NFT）
  { phase: 'L5-3', to: '/eco', key: 'eco_t8',
    title: 'T8 · 兑换植树证书（2+ 树种）',
    desc: '切换回学习者 → 用积攒的能量兑换「植树证书」NFT',
    label: '5 分钟', klass: 'lvl-l5-3',
    hint: 'G 项 8 分：≥2 种树种 8 分 / 1 种 4 分' },
  { phase: 'L5-3', to: '/eco', key: 'eco_t9',
    title: 'T9 · 兑换勋章 & 骑行券（两类 NFT）',
    desc: '兑换「绿色勋章」NFT + 「免费骑行券」NFT，凑齐资产多样性',
    label: '5 分钟', klass: 'lvl-l5-3',
    hint: 'G 项 4 分：两类都有 4 分 / 一类 2 分' },
  { phase: 'L5-3', to: '/report', key: 'eco_t10',
    title: 'T10 · 生成实训报告 · 查看 L5 评分',
    desc: '生成报告并查看 E~H 四项得分与智能纠错建议',
    label: '3 分钟', klass: 'lvl-l5-3',
    hint: '交付：40 分高级实战 + 5 分综合拓展 ≥ 40/45' },
]
const STORAGE_L5_KEY = 'l5_micro_done_v1'
function loadL5Done(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(STORAGE_L5_KEY)
    const arr = raw ? JSON.parse(raw) : []
    const obj: Record<string, boolean> = {}
    if (Array.isArray(arr)) arr.forEach((k) => (obj[k] = true))
    return obj
  } catch { return {} }
}
const l5Done = reactive<Record<string, boolean>>(loadL5Done())

/* 根据当前阶段选择展示：
   - 搭链完成（cloud 10/10）→ 展示 10 个联盟运营微任务
   - 否则 → 展示基础搭建任务
*/
const l4Done = computed(() => {
  return !!visited['/cloud'] && isCloudAllDone.value
})

const basicTodos = computed(() => {
  const cloudDone = !!visited['/cloud'] && isCloudAllDone.value
  const hasContract = (overview.value.contract_count ?? 0) >= 1
  const has2Txs = (overview.value.tx_count ?? 0) >= 2
  const hasNft = nftCount.value >= 1
  return [
    {
      title: '阶段 1 · 完成 10 步搭链教程',
      desc: '启动 4 节点联盟链 → 6 联盟组织接入 → 部署 GreenEnergy → 6 角色发能量链路验证',
      label: '30 分钟', klass: 'info', done: cloudDone,
      to: '/cloud',
      hint: isCloudAllDone.value
        ? cloudDoneSteps.value.length + '/' + CLOUD_TOTAL + ' 步骤已完成'
        : (cloudDoneSteps.value.length ? '进度 ' + cloudDoneSteps.value.length + '/' + CLOUD_TOTAL : '点击前往云桌面'),
    },
    {
      title: '阶段 2 · 部署 3 份业务合约',
      desc: '在合约 IDE 中编译并部署 GreenEnergy / PlantCertificate / EcoBadge',
      label: '关键', klass: '', done: hasContract,
      to: '/ide',
      hint: hasContract ? '已部署 ' + (overview.value.contract_count ?? 0) + ' 份合约' : '点击打开合约 IDE',
    },
    {
      title: '阶段 3 · 体验联盟角色与能量发放',
      desc: '切换到地铁/公交/单车等角色，向用户钱包发放绿色能量',
      label: '核心', klass: 'warn', done: has2Txs,
      to: '/eco',
      hint: has2Txs ? '已累计 ' + (overview.value.tx_count ?? 0) + ' 笔交易' : '点击前往绿色低碳联盟链',
    },
    {
      title: '阶段 3 · 兑换绿色资产 NFT',
      desc: '用积攒的绿色能量兑换植树证书 / 生态勋章 / 骑行券',
      label: '挑战', klass: 'accent', done: hasNft,
      to: '/eco',
      hint: hasNft ? '已累计铸造 ' + nftCount.value + ' 件绿色资产' : '点击前往资产兑换',
    },
  ]
})

/* 最终 todos 列表（自适应阶段） */
const todos = computed(() => {
  if (l4Done.value) {
    return L5_MICRO_TASKS.map((t) => ({
      title: t.title, desc: t.desc, label: t.label, klass: t.klass,
      done: !!l5Done[t.key], to: t.to, hint: t.hint,
      key: t.key,
    }))
  }
  return basicTodos.value
})
/* 点击 L5 任务可以打勾（由老师抽查或学生自证完成，localStorage 持久化） */
function toggleTodo(t: any) {
  if (t.done) {
    delete l5Done[t.key]
  } else if (l4Done.value && t.key) {
    l5Done[t.key] = true
  }
  try {
    localStorage.setItem(STORAGE_L5_KEY, JSON.stringify(Object.keys(l5Done)))
  } catch { /* noop */ }
}
const todoDoneCount = computed(() => todos.value.filter((t) => t.done).length)
const todoPercent = computed(() => Math.round((todoDoneCount.value / todos.value.length) * 100))

/* ---------- 跨页同步 ---------- */
function onStorage(e: StorageEvent) {
  if (e.key === CLOUD_STEP_KEY || e.key === VISIT_KEY || e.key === COMPLETED_KEY || e.key === NFT_COUNT_KEY) {
    refreshCompleted()
  }
}
onMounted(() => {
  window.addEventListener('storage', onStorage)
})
onUnmounted(() => {
  window.removeEventListener('storage', onStorage)
})
/* 加载链上概览数据（块高 / 交易数 / 合约数等）。SSO 登录前调用会拿不到数据，需跳过 */
async function loadOverview() {
  try {
    const raw = (await explorerApi.overview()) as any
    overview.value = raw?.data ?? raw ?? {}
  } catch (e) { /* noop */ }
}

onActivated(async () => {
  await loadOverview()
  refreshCompleted()
})

// 钱包切换时刷新实训进度（角色/钱包联动）
watch(() => app.currentWallet, () => {
  refreshCompleted()
})
</script>

<style scoped lang="scss">
.dashboard { display: flex; flex-direction: column; gap: 14px; }

/* ================== 平台实训进度看板 ================== */
.platform-card {
  padding: 16px 20px;
  .pc-head {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 14px;
  }
  .pc-title { display: flex; align-items: center; gap: 8px; font-size: 15px; font-weight: 600; color: var(--text-1); }
  .pc-ico { font-size: 20px; }
  .pc-stats { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
  .pcs-item {
    flex: 1; min-width: 120px;
    background: var(--bg-2, rgba(0,0,0,0.03));
    border-radius: 10px; padding: 12px 16px; text-align: center;
  }
  .pcs-num { font-size: 22px; font-weight: 700; line-height: 1.2; color: var(--text-1); }
  .pcs-num.accent { color: var(--primary, #409eff); }
  .pcs-num.success { color: var(--success, #67c23a); }
  .pcs-label { font-size: 12px; color: var(--text-3, #909399); margin-top: 4px; }
  .pc-steps { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
  .pc-step-row { display: flex; align-items: center; gap: 10px; }
  .psr-label { width: 56px; font-size: 12px; color: var(--text-3, #909399); flex-shrink: 0; }
  .psr-bar { flex: 1; height: 8px; background: var(--bg-2, rgba(0,0,0,0.06)); border-radius: 4px; overflow: hidden; }
  .psr-fill { height: 100%; background: linear-gradient(90deg, #409eff, #67c23a); border-radius: 4px; transition: width 0.5s ease; }
  .psr-count { width: 70px; font-size: 11px; color: var(--text-3, #909399); text-align: right; flex-shrink: 0; }
  .pc-students { overflow-x: auto; }
  .pcs-table { min-width: 480px; }
  .pcs-th, .pcs-tr { display: flex; align-items: center; padding: 8px 12px; }
  .pcs-th { font-size: 12px; color: var(--text-3, #909399); border-bottom: 1px solid var(--border-2, rgba(0,0,0,0.06)); }
  .pcs-tr { font-size: 13px; border-bottom: 1px solid var(--border-2, rgba(0,0,0,0.04)); &:hover { background: var(--bg-2, rgba(0,0,0,0.03)); } }
  .pcs-td-name { width: 35%; }
  .pcs-td-prog { width: 30%; display: flex; align-items: center; gap: 8px; }
  .pcs-td-score { width: 17.5%; text-align: center; }
  .pcs-td-final { width: 17.5%; text-align: center; }
  .mini-bar { flex: 1; height: 6px; background: var(--bg-2, rgba(0,0,0,0.06)); border-radius: 3px; overflow: hidden; }
  .mini-fill { height: 100%; background: #409eff; border-radius: 3px; transition: width 0.4s ease; }
  .pcs-td-score.accent { color: var(--primary, #409eff); }
  .pcs-td-final.success { color: var(--success, #67c23a); }
}

/* ================== 顶部 Hero（移除 ChainNetworkBG，渐变背景兜底） ================== */
.hero {
  position: relative;
  overflow: hidden;
  isolation: isolate;
  padding: 22px 26px;
  min-height: 300px;              /* 防止内容过少时被压扁 */
  border: 1px solid var(--dq-border-2);
  border-radius: 14px;
  box-shadow: var(--dq-shadow);
  background:
    radial-gradient(700px 260px at 100% 0%, rgba(59,130,246,0.12), transparent 60%),
    radial-gradient(500px 220px at 0% 100%, rgba(0,230,195,0.09), transparent 60%),
    linear-gradient(135deg, rgba(11,16,30,0.92), rgba(8,12,22,0.96));
  /* z-index 分层兜底：背景 z0 / overlay z1 / 内容 z2 */
  z-index: 0;
}
/* 响应式：窄屏 hero 最小高度减小 */
@media (max-width: 760px) {
  .hero { min-height: 250px; padding: 16px 16px; }
}
.hero-overlay {
  position: absolute; inset: 0;
  background: linear-gradient(135deg, rgba(7,11,22,0.55) 0%, rgba(7,11,22,0.25) 60%, rgba(7,11,22,0.65) 100%);
  z-index: 1;
}
.hero-content {
  position: relative; z-index: 2;
  display: grid; grid-template-columns: 1.55fr 1fr; gap: 18px;
}
.hero-left { display: flex; flex-direction: column; justify-content: center; min-width: 0; gap: 12px; }

.hero-badge {
  display: inline-flex; align-items: center; gap: 8px;
  align-self: flex-start;
  padding: 5px 12px;
  border-radius: 999px;
  background: rgba(77,141,255,0.12);
  border: 1px solid rgba(77,141,255,0.3);
  color: var(--dq-info);
  font-size: 11.5px; font-weight: 500;
  backdrop-filter: blur(4px);
  .hb-dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--dq-info);
    box-shadow: 0 0 6px rgba(77,141,255,0.8);
  }
}
.hero-title {
  font-size: 28px; font-weight: 800; margin: 0;
  color: var(--dq-text); letter-spacing: 0.3px;
  display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap;
  .grad {
    background: var(--dq-grad-primary); -webkit-background-clip: text; background-clip: text; color: transparent;
    filter: drop-shadow(0 0 12px rgba(0,230,195,0.25));
  }
}
.hero-title-sub {
  margin-left: auto;
  font-size: 13px; font-weight: 600;
  color: var(--dq-primary);
  opacity: 0.98;
  padding: 3px 10px;
  border-radius: 6px;
  background: rgba(0,230,195,0.1);
  border: 1px solid rgba(0,230,195,0.28);
  backdrop-filter: blur(4px);
}
.hero-desc { color: #a9b6d6; margin: 0; font-size: 13px; }

/* Hero 内嵌进度条 */
.hero-progress {
  margin-top: 2px;
  display: flex; flex-direction: column; gap: 6px;
  .hp-bar {
    height: 6px; background: rgba(123,138,171,0.16);
    border-radius: 999px; overflow: hidden;
    position: relative;
    &::before {
      content: ''; position: absolute; inset: 0;
      background-image: repeating-linear-gradient(90deg, transparent 0, transparent 12px, rgba(255,255,255,0.04) 12px, rgba(255,255,255,0.04) 14px);
      pointer-events: none;
    }
  }
  .hp-fill {
    height: 100%;
    background: var(--dq-grad-primary);
    border-radius: 999px;
    box-shadow: 0 0 10px var(--dq-primary-glow);
    transition: width .45s cubic-bezier(0.16,1,0.3,1);
    position: relative;
  }
  .hp-labels {
    display: flex; justify-content: space-between;
    font-size: 11px; color: #8fa0c4;
  }
}

/* 3 个核心数据卡：玻璃拟态 */
.hero-stats {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;
  margin-top: 4px;
}
.hs-item {
  padding: 13px 14px;
  display: flex; align-items: center; gap: 12px;
  cursor: pointer;
  min-height: 72px;
  backdrop-filter: blur(12px);
  .hs-ico {
    width: 38px; height: 38px; border-radius: 10px;
    display: inline-flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    .el-icon { font-size: 19px; color: #fff; }
  }
  .hs-c { background: linear-gradient(135deg, #4d8dff, #2e6bd9); box-shadow: 0 4px 14px rgba(77,141,255,0.3); }
  .hs-t { background: linear-gradient(135deg, #00e6c3, #0a9d88); box-shadow: 0 4px 14px rgba(0,230,195,0.3); }
  .hs-w { background: linear-gradient(135deg, #f5379b, #b8298a); box-shadow: 0 4px 14px rgba(245,55,155,0.28); }
  .hs-info { display: flex; flex-direction: column; min-width: 0; }
  .hs-num { font-size: 20px; font-weight: 800; color: var(--dq-text); line-height: 1.15; letter-spacing: -0.3px;
    :deep(.dq-countup) { background: var(--dq-grad-primary); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
  }
  .hs-label { font-size: 11px; color: #8fa0c4; margin-top: 3px; }
}

/* 右侧实训链卡：玻璃拟态 + 协议分布饼条 */
.hero-right { display: flex; }
.chain-card {
  flex: 1;
  padding: 14px 16px;
  display: flex; flex-direction: column;
  min-height: 200px;
  backdrop-filter: blur(14px);
}
.chain-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.chain-title { font-weight: 700; font-size: 14px; color: var(--dq-text); }
.chain-body { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 12px; }
.chain-stat {
  padding: 10px 6px;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.05);
  border-radius: 8px;
  text-align: center;
  .dq-stat__num { font-size: 20px !important; }
  .dq-stat__label { font-size: 10.5px !important; }
}
/* 协议分布小饼条 */
.chain-std {
  margin-bottom: 12px;
  padding: 10px 12px;
  background: rgba(255,255,255,0.025);
  border: 1px solid rgba(255,255,255,0.05);
  border-radius: 8px;
  .cs-label { font-size: 10.5px; color: #8fa0c4; margin-bottom: 6px; }
  .cs-bar {
    display: flex; height: 8px; border-radius: 999px; overflow: hidden;
    background: rgba(123,138,171,0.15);
    .cs-seg { transition: width .5s cubic-bezier(0.16,1,0.3,1); }
    .cs-seg.s-erc20   { background: linear-gradient(90deg, #4d8dff, #6ba6ff); }
    .cs-seg.s-erc721  { background: linear-gradient(90deg, #f5379b, #ff69b4); }
    .cs-seg.s-erc1155 { background: linear-gradient(90deg, #ffcf4d, #ffe38a); }
    .cs-seg.s-custom  { background: linear-gradient(90deg, #7b8aab, #98a8c9); }
  }
  .cs-legend { margin-top: 7px; display: flex; gap: 10px; flex-wrap: wrap; }
  .cs-lg { display: inline-flex; align-items: center; gap: 4px; font-size: 10.5px; color: #a9b6d6; }
  .cs-dot {
    width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
    &.s-erc20   { background: #4d8dff; box-shadow: 0 0 4px rgba(77,141,255,0.6); }
    &.s-erc721  { background: #f5379b; box-shadow: 0 0 4px rgba(245,55,155,0.6); }
    &.s-erc1155 { background: #ffcf4d; box-shadow: 0 0 4px rgba(255,207,77,0.6); }
    &.s-custom  { background: #7b8aab; }
  }
}
.chain-foot {
  display: flex; justify-content: space-between; align-items: center;
  margin-top: auto;
  padding-top: 10px;
  border-top: 1px dashed rgba(123,138,171,0.3);
  font-size: 11px;
  .cf-k { color: #8fa0c4; }
  .cf-v { font-family: var(--dq-mono); font-weight: 600;
    &.fisco { color: var(--dq-success); }
    &.evm   { color: var(--dq-primary); }
    &.mock  { color: var(--dq-warn); }
  }
}

/* ================== 主区双栏 ================== */
.main-grid { display: grid; grid-template-columns: 1.5fr 1fr; gap: 14px; }

/* 路径卡头部 */
.path-head {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1px dashed var(--dq-border);
}
.path-title { display: flex; align-items: center; gap: 12px; }
.title-ico {
  width: 36px; height: 36px; border-radius: 9px;
  background: linear-gradient(135deg, rgba(0,230,195,0.12), rgba(0,230,195,0.03));
  border: 1px solid rgba(0,230,195,0.2);
  display: inline-flex; align-items: center; justify-content: center;
  .el-icon { color: var(--dq-primary); font-size: 18px; }
}
.path-t { font-size: 15px; font-weight: 700; color: var(--dq-text); }
.path-s { font-size: 11.5px; color: var(--dq-text-dimmer); margin-top: 2px; }

.path-progress-tag {
  padding: 6px 14px;
  border-radius: 999px;
  background: rgba(0,230,195,0.08);
  border: 1px solid rgba(0,230,195,0.2);
  font-weight: 700; color: var(--dq-primary);
  font-size: 13px;
  display: inline-flex; align-items: center; gap: 3px;
}

/* ============== 垂直时间轴：学习路径 ============== */
.path-timeline { display: flex; flex-direction: column; }
.tl-step {
  display: flex; gap: 14px;
  padding-bottom: 14px;
  cursor: pointer;
  position: relative;
  &:last-child { padding-bottom: 0; }
}
.tl-side {
  width: 32px; flex-shrink: 0;
  display: flex; flex-direction: column; align-items: center;
  position: relative;
  z-index: 1;
}
.tl-node {
  position: relative;
  width: 32px; height: 32px; border-radius: 50%;
  flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--dq-panel-2);
  border: 2px solid var(--dq-border-2);
  color: var(--dq-text-dim);
  font-family: var(--dq-mono); font-weight: 700; font-size: 13px;
  transition: all .25s ease;
  .tln-check { color: inherit; font-size: 15px; }
}
.tl-line {
  flex: 1;
  width: 2px;
  margin-top: 6px;
  background: linear-gradient(180deg, var(--dq-border-2), rgba(42,58,94,0.3));
  transition: background .25s ease;
}
/* 状态：已完成 */
.tl-step.done {
  .tl-node {
    background: linear-gradient(135deg, var(--dq-primary), var(--dq-primary-3));
    border-color: var(--dq-primary);
    color: #062b25;
    box-shadow: 0 0 0 3px rgba(0,230,195,0.12), 0 0 10px var(--dq-primary-glow);
  }
  .tl-line {
    background: linear-gradient(180deg, var(--dq-primary), rgba(0,230,195,0.2));
  }
}
/* 状态：当前步骤（脉冲） */
.tl-step.cur {
  .tl-node {
    background: var(--dq-panel);
    border-color: var(--dq-primary);
    color: var(--dq-primary);
    animation: dq-node-pulse 1.8s ease-in-out infinite;
    overflow: visible;
    &::after {
      content: '';
      position: absolute;
      left: 50%; top: 50%;
      width: 32px; height: 32px;
      margin-left: -16px; margin-top: -16px;
      border-radius: 50%;
      border: 2px solid var(--dq-primary);
      opacity: 0.6;
      z-index: 2;
      pointer-events: none;
      box-shadow: 0 0 8px rgba(0,230,195,0.3);
      animation: dq-ripple 1.8s ease-out infinite;
    }
  }
  .tl-line {
    background: linear-gradient(180deg, var(--dq-primary), var(--dq-border-2));
  }
}
/* 状态：锁定 */
.tl-step.locked {
  .tl-node { opacity: 0.7; border-style: dashed; }
  .tl-body { opacity: 0.75; }
  &:hover {
    .tl-body { opacity: 0.95; }
    .tl-node { opacity: 0.9; }
  }
}
@keyframes dq-node-pulse {
  0%, 100% { box-shadow: 0 0 0 3px rgba(0,230,195,0.08), 0 0 10px rgba(0,230,195,0.2); }
  50%      { box-shadow: 0 0 0 5px rgba(0,230,195,0.16), 0 0 14px rgba(0,230,195,0.4); }
}
@keyframes dq-ripple {
  0%   { transform: scale(1);    opacity: 0.45; }
  100% { transform: scale(2.0);  opacity: 0; }
}

/* 时间轴右侧内容卡片 */
.tl-body {
  flex: 1; min-width: 0;
  padding: 12px 14px;
  background: var(--dq-bg-2);
  border: 1px solid var(--dq-border);
  border-radius: 10px;
  transition: all .22s ease;
  &:hover {
    border-color: var(--dq-border-2);
    transform: translateX(3px);
    background: #12192d;
  }
}
.tl-step.done .tl-body {
  background: linear-gradient(90deg, rgba(0,230,195,0.04), transparent 80%);
  border-color: rgba(0,230,195,0.22);
}
.tl-step.cur .tl-body {
  background: linear-gradient(90deg, rgba(0,230,195,0.08), rgba(0,230,195,0.025));
  border-color: var(--dq-primary);
  box-shadow: 0 0 0 1px rgba(0,230,195,0.12), 0 6px 20px rgba(0,230,195,0.08);
}
.tl-step.locked .tl-body {
  border-style: dashed;
  border-color: rgba(123,138,171,0.22);
}
.tlb-head {
  display: flex; justify-content: space-between; align-items: flex-start;
  gap: 10px; margin-bottom: 6px; flex-wrap: wrap;
}
.tlb-title-row {
  display: inline-flex; align-items: center; gap: 8px; min-width: 0;
}
.tlb-ico {
  color: var(--dq-primary);
  font-size: 17px;
  opacity: 0.9;
  flex-shrink: 0;
}
.tlb-title {
  font-weight: 600; color: var(--dq-text); font-size: 13.5px;
}
.tlb-badge {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 10.5px; font-family: var(--dq-mono);
  padding: 2px 8px; border-radius: 999px;
  background: rgba(0,230,195,0.1); color: var(--dq-primary);
  border: 1px solid rgba(0,230,195,0.25);
  &.ok { background: rgba(45,212,191,0.1); color: var(--dq-success); border-color: rgba(45,212,191,0.25); }
  &.lock { background: rgba(123,138,171,0.1); color: var(--dq-text-dim); border-color: rgba(123,138,171,0.25); }
}
.tlb-desc { color: var(--dq-text-dim); font-size: 11.5px; line-height: 1.6; margin: 0 0 6px 0; }
.tlb-tags { display: flex; gap: 5px; flex-wrap: wrap; margin-bottom: 10px; }
.ps-sub-tag {
  font-family: var(--dq-mono);
  font-size: 10px; color: var(--dq-text-dimmer);
  background: rgba(255,255,255,0.025);
  padding: 1px 5px; border-radius: 3px;
  border: 1px solid var(--dq-border);
}
.tlb-action { display: flex; justify-content: flex-end; }

/* 右侧栏 */
.side-col { display: flex; flex-direction: column; gap: 14px; }

/* 通用卡片头 */
.card-head {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px dashed var(--dq-border);
  .title-icon {
    width: 32px; height: 32px; border-radius: 8px;
    background: linear-gradient(135deg, rgba(77,141,255,0.12), rgba(77,141,255,0.03));
    border: 1px solid rgba(77,141,255,0.2);
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 15px;
    flex-shrink: 0;
  }
  .ct-title { font-size: 14px; font-weight: 700; color: var(--dq-text); }
  .ct-sub { font-size: 11px; color: var(--dq-text-dimmer); margin-top: 1px; }
  .ct-progress {
    margin-left: auto;
    font-weight: 700; color: var(--dq-info);
    padding: 4px 10px;
    border-radius: 999px;
    background: rgba(77,141,255,0.08);
    border: 1px solid rgba(77,141,255,0.2);
    font-size: 12px;
  }
}

/* 今日任务 */
.todo-list { display: flex; flex-direction: column; gap: 6px; }
.todo-item {
  display: flex; align-items: flex-start; gap: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid var(--dq-border);
  cursor: pointer;
  transition: all .15s;
  &:hover { background: rgba(0,230,195,0.03); border-color: var(--dq-border-2); }
  &.done {
    background: rgba(45,212,191,0.035);
    border-color: rgba(45,212,191,0.18);
    .ti-title { color: var(--dq-text-dim); text-decoration: line-through; }
  }
}
.ti-check {
  width: 18px; height: 18px; flex-shrink: 0; margin-top: 1px;
  position: relative;
  .tic-box {
    position: absolute; inset: 0;
    border: 1.5px solid var(--dq-border-2); border-radius: 5px;
  }
  .tic-check-icon {
    position: relative; z-index: 1;
    color: var(--dq-success); font-size: 14px;
    display: flex; align-items: center; justify-content: center;
    width: 100%; height: 100%;
  }
}
.ti-info { flex: 1; min-width: 0; }
.ti-title { font-size: 13px; font-weight: 600; color: var(--dq-text); margin-bottom: 2px; }
.ti-desc { font-size: 11px; color: var(--dq-text-dim); line-height: 1.5; }
.ti-hint {
  margin-top: 4px;
  font-size: 10.5px;
  color: var(--dq-primary);
  opacity: 0.9;
}

/* 快速入口 */
.quick-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px;
}
.qi {
  padding: 14px 6px;
  border: 1px solid var(--dq-border);
  border-radius: 10px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 8px;
  cursor: pointer;
  background: var(--dq-bg-2);
  transition: all .15s;
  color: var(--dq-text-dim);
  .qi-ico {
    width: 34px; height: 34px; border-radius: 9px;
    background: linear-gradient(135deg, rgba(0,230,195,0.12), rgba(0,230,195,0.02));
    border: 1px solid rgba(0,230,195,0.2);
    display: inline-flex; align-items: center; justify-content: center;
    .el-icon { font-size: 17px; color: var(--dq-primary); }
  }
  span { font-size: 12px; font-weight: 600; }
  &:hover { border-color: var(--dq-primary); background: rgba(0,230,195,0.05); color: var(--dq-text); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,230,195,0.05); }
}

/* ================== L1~L5 等级标签 + 学习块样式 ================== */
/* 等级颜色：从柔和绿 → 蓝 → 紫 → 橙 → 粉（暗示难度爬坡） */
.dq-tag.lvl {
  font-weight: 600;
  padding: 2px 8px;
}
.dq-tag.lvl.lvl-l1 { background: rgba(132,204,22,0.12);  color: #a3e635; border-color: rgba(132,204,22,0.30); }
.dq-tag.lvl.lvl-l2 { background: rgba(59,130,246,0.12);  color: #60a5fa; border-color: rgba(59,130,246,0.30); }
.dq-tag.lvl.lvl-l3 { background: rgba(139,92,246,0.12);  color: #a78bfa; border-color: rgba(139,92,246,0.30); }
.dq-tag.lvl.lvl-l4 { background: rgba(245,158,11,0.12);  color: #fbbf24; border-color: rgba(245,158,11,0.30); }
.dq-tag.lvl.lvl-l5 { background: rgba(236,72,153,0.14);  color: #f472b6; border-color: rgba(236,72,153,0.35); }
.dq-tag.eta-tag {
  background: rgba(255,255,255,0.04);
  color: var(--dq-text-dim);
  border-color: rgba(123,138,171,0.25);
  font-weight: 500;
}
/* 学习三步法：目标 / 锚点 / 验收 */
.tlb-learn-block {
  margin: 10px 0 10px;
  padding: 10px 12px;
  border-radius: 9px;
  background: rgba(255,255,255,0.018);
  border: 1px dashed rgba(123,138,171,0.22);
}
.lb-row {
  display: flex;
  gap: 10px;
  margin: 5px 0;
  align-items: flex-start;
  &:first-child { margin-top: 0; }
  &:last-child  { margin-bottom: 0; }
}
.lb-k {
  flex-shrink: 0;
  width: 54px;
  font-size: 11px;
  font-weight: 700;
  color: var(--dq-primary);
  padding-top: 1px;
  font-family: var(--dq-mono);
}
.lb-v {
  flex: 1;
  font-size: 11.5px;
  color: var(--dq-text);
  line-height: 1.55;
}
.lb-kps {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.kp-chip {
  font-size: 10.5px;
  color: var(--dq-text-dim);
  padding: 3px 8px;
  border-radius: 6px;
  background: rgba(0,230,195,0.06);
  border: 1px solid rgba(0,230,195,0.16);
  line-height: 1.4;
}
.lb-ul {
  flex: 1;
  margin: 0;
  padding: 0 0 0 16px;
  color: var(--dq-text-dim);
  li {
    font-size: 11px;
    line-height: 1.55;
    list-style-type: '✓ ';
    padding-left: 4px;
    color: #a9b6d6;
  }
}
/* 未完成时，验收列表样式变灰，暗示学生需要达成 */
.tl-step:not(.done) .lb-ul li { list-style-type: '○ '; color: #8a98b8; }
.tl-step.cur .lb-ul li { list-style-type: '→ '; color: var(--dq-text); }

/* ================== L5 三阶段任务颜色 ================== */
.dq-tag.lvl-l5-1 {
  background: rgba(251,191,36,0.10);  color: #fbbf24;
  border-color: rgba(251,191,36,0.28);
}
.dq-tag.lvl-l5-2 {
  background: rgba(34,197,94,0.10);   color: #4ade80;
  border-color: rgba(34,197,94,0.28);
}
.dq-tag.lvl-l5-3 {
  background: rgba(236,72,153,0.12);  color: #f472b6;
  border-color: rgba(236,72,153,0.32);
}
/* L5 列表：更紧凑 + 支持打勾视觉 */
.todo-list.l5-list { gap: 4px; }
.todo-item.l5-item {
  padding: 8px 10px !important;
  &:hover { background: rgba(236,72,153,0.04); border-color: rgba(236,72,153,0.20); }
  &.done .ti-title { color: var(--dq-text-dim); }
}
.ti-check.l5-check {
  cursor: pointer;
  .tic-box {
    border-color: rgba(236,72,153,0.35) !important;
    transition: all .15s;
  }
  &:hover .tic-box {
    border-color: rgba(236,72,153,0.70) !important;
    background: rgba(236,72,153,0.06);
  }
}
.ct-progress.l5-mode {
  color: var(--dq-accent);
  background: rgba(236,72,153,0.10);
  border-color: rgba(236,72,153,0.28);
}
.ct-phase-hint {
  margin-left: 6px;
  font-family: var(--dq-mono);
  color: #94a3c7;
  opacity: 0.9;
}
.todo-foot {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed rgba(123,138,171,0.25);
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 10.5px;
}
.tf-k {
  padding: 2px 7px;
  border-radius: 4px;
  background: rgba(236,72,153,0.08);
  color: var(--dq-accent);
  border: 1px solid rgba(236,72,153,0.25);
}
.tf-phases {
  flex: 1;
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
}
.tf-p {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 10px;
  font-family: var(--dq-mono);
  border: 1px solid rgba(123,138,171,0.25);
  color: var(--dq-text-dim);
  background: rgba(255,255,255,0.02);
}
.tf-p.p1 { background: rgba(251,191,36,0.08); color: #fbbf24; border-color: rgba(251,191,36,0.25); }
.tf-p.p2 { background: rgba(34,197,94,0.08);  color: #4ade80; border-color: rgba(34,197,94,0.25); }
.tf-p.p3 { background: rgba(236,72,153,0.08); color: #f472b6; border-color: rgba(236,72,153,0.28); }

/* 响应式小屏降级 */
@media (max-width: 1280px) {
  .hero-content { grid-template-columns: 1fr; }
  .main-grid { grid-template-columns: 1fr; }
  .hero-title { font-size: 24px; }
  .chain-body { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 720px) {
  .hero { padding: 18px; }
  .hero-stats { grid-template-columns: 1fr; }
  .chain-body { grid-template-columns: repeat(3, 1fr); }
  .tlb-head { flex-direction: column; align-items: flex-start; }
  .tlb-title-row { flex-wrap: wrap; }
  .lb-k { width: 46px; font-size: 10.5px; }
}
</style>