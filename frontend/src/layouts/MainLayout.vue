<template>
  <div class="layout dq-enter-up">
    <!-- 快捷键面板 -->
    <Shortcuts ref="shortcutsRef" />

    <!-- 侧边栏 -->
    <aside class="sidebar">
      <div class="logo">
        <span class="logo-mark">⬡</span>
        <div class="logo-text">
          <div class="t1 dq-grad-text">FISCO<span class="t1-sub">Chain</span></div>
          <div class="t2">联盟链实训平台 · <span class="t2-sub">天择教育</span></div>
        </div>
      </div>

      <el-menu :default-active="route.path" router class="dq-menu" :default-openeds="defaultOpen">
        <!-- 阶段 1 · 链底层搭建 -->
        <el-sub-menu index="g-learn">
          <template #title>
            <span class="menu-group-icon learn">⛓️</span>
            <span class="menu-group-label">链底层搭建</span>
          </template>
          <el-menu-item v-for="r in groupLearn" :key="r.path" :index="r.path">
            <el-icon><component :is="r.icon" /></el-icon>
            <span>{{ r.title }}</span>
            <span class="menu-tag" v-if="r.tag">{{ r.tag }}</span>
          </el-menu-item>
        </el-sub-menu>

        <!-- 阶段 2 · 业务合约开发 -->
        <el-sub-menu index="g-contract">
          <template #title>
            <span class="menu-group-icon contract">🔧</span>
            <span class="menu-group-label">业务合约开发</span>
          </template>
          <el-menu-item v-for="r in groupContract" :key="r.path" :index="r.path">
            <el-icon><component :is="r.icon" /></el-icon>
            <span>{{ r.title }}</span>
            <span class="menu-tag" v-if="r.tag">{{ r.tag }}</span>
          </el-menu-item>
        </el-sub-menu>

        <!-- 阶段 3 · 联盟治理与运营 -->
        <el-sub-menu index="g-practice">
          <template #title>
            <span class="menu-group-icon practice">🌿</span>
            <span class="menu-group-label">联盟治理与运营</span>
          </template>
          <el-menu-item v-for="r in groupPractice" :key="r.path" :index="r.path">
            <el-icon><component :is="r.icon" /></el-icon>
            <span>{{ r.title }}</span>
            <span class="menu-tag accent" v-if="r.tag">{{ r.tag }}</span>
          </el-menu-item>
        </el-sub-menu>

        <!-- 阶段 4 · 链上验证 -->
        <el-sub-menu index="g-eco">
          <template #title>
            <span class="menu-group-icon eco">🔍</span>
            <span class="menu-group-label">链上验证</span>
          </template>
          <el-menu-item v-for="r in groupEco" :key="r.path" :index="r.path">
            <el-icon><component :is="r.icon" /></el-icon>
            <span>{{ r.title }}</span>
          </el-menu-item>
          <el-menu-item v-for="r in groupExplorer" :key="r.path" :index="r.path">
            <el-icon><component :is="r.icon" /></el-icon>
            <span>{{ r.title }}</span>
          </el-menu-item>
        </el-sub-menu>

        <!-- 教学管理（教师 / 管理员可见） -->
        <el-sub-menu v-if="auth.canManageGrades" index="g-teach">
          <template #title>
            <span class="menu-group-icon teach">🎓</span>
            <span class="menu-group-label">教学管理</span>
          </template>
          <el-menu-item v-for="r in groupTeach" :key="r.path" :index="r.path">
            <el-icon><component :is="r.icon" /></el-icon>
            <span>{{ r.title }}</span>
            <span class="menu-tag accent" v-if="r.tag">{{ r.tag }}</span>
          </el-menu-item>
        </el-sub-menu>
      </el-menu>

      <!-- 独立：生成实训报告（大选项，位于左侧列表最下方，不受分组折叠影响） -->
      <div class="report-entry" :class="{ active: route.path === '/report' }" @click="$router.push('/report')">
        <div class="re-icon-wrap">
          <el-icon class="re-icon"><Document /></el-icon>
          <span class="re-sparkle"></span>
        </div>
        <div class="re-info">
          <div class="re-title">
            <span>生成实训报告</span>
            <span class="re-tag">交付</span>
          </div>
          <div class="re-sub">汇总学习进度 · 链上数据 · 合约记录 · 一键导出</div>
        </div>
        <el-icon class="re-arrow"><Right /></el-icon>
      </div>

      <!-- 底部：链状态（支持模式切换） -->
      <div class="sidebar-foot">
        <div class="sf-title">
          <span>当前链状态</span>
          <el-button link size="small" class="sf-help" @click="shortcutsRef?.open()">⌨️ 快捷键</el-button>
        </div>
        <!-- 模式切换（点击引擎行弹出 Popover） -->
        <el-popover placement="top-start" trigger="click" :width="240" popper-class="mode-pop">
          <template #reference>
            <div class="sf-row mode-row" title="点击切换链模式（dev / 教师用）">
              <span class="sf-k">引擎</span>
              <span :class="['sf-v', app.chainMode]">
                <i class="mode-dot"></i>
                {{ modeLabel }}
              </span>
              <el-icon class="mode-arrow"><ArrowDown /></el-icon>
            </div>
          </template>
          <div class="mode-switch">
            <div class="ms-title">切换链执行引擎</div>
            <div class="ms-tip dq-tip" style="margin:8px 0 12px">
              <span class="dt-label">注意</span>切换会重置链状态（块高归零）。生产环境不建议频繁切换。
            </div>
            <div
              class="ms-item"
              v-for="m in modes"
              :key="m.value"
              :class="{ active: app.chainMode === m.value }"
              @click="onSwitchMode(m.value)"
            >
              <i class="ms-dot" :class="m.value"></i>
              <div class="ms-info">
                <div class="ms-name">{{ m.label }}</div>
                <div class="ms-desc">{{ m.desc }}</div>
              </div>
              <el-icon v-if="app.chainMode === m.value" class="ms-check"><Check /></el-icon>
            </div>
          </div>
        </el-popover>

        <div class="sf-row">
          <span class="sf-k">块高</span>
          <span class="sf-v real dq-mono">#{{ app.chainHeight.toLocaleString() }}</span>
        </div>
        <div class="sf-row">
          <span class="sf-k">共识</span>
          <span class="sf-v">PBFT · 4节点</span>
        </div>
        <div class="sf-progress">
          <div class="sf-p-label">
            <span>整体学习进度</span>
            <span class="sf-p-val dq-mono">{{ learnProgress }}%</span>
          </div>
          <div class="dq-progress dq-progress--sm">
            <div class="dq-progress__bar" :style="{ width: learnProgress + '%' }"></div>
          </div>
        </div>
      </div>
    </aside>

    <!-- 主体 -->
    <div class="main">
      <header class="topbar">
        <div class="topbar-left">
          <div class="crumbs">
            <span class="crumb-group">{{ currentGroup }}</span>
            <span class="crumb-sep">/</span>
            <span class="crumb-title">{{ currentTitle }}</span>
          </div>
          <span class="dq-live" v-if="app.chainMode === 'fisco' || app.chainMode === 'evm'"><span class="dot"></span>{{ app.chainMode === 'fisco' ? 'FISCO 节点已连接' : 'EVM 真实链运行中' }}</span>
          <span class="dq-tag warn" v-else>本地沙盒模式</span>
          <span class="dq-tag info dq-tag-group">{{ tagLabel }}</span>
        </div>
        <div class="topbar-right">
          <el-button size="small" @click="shortcutsRef?.open()" title="快捷键帮助 (?)" class="sc-btn">
            <el-icon><QuestionFilled /></el-icon>
            <span>? · 快捷键</span>
          </el-button>
          <el-button size="small" type="primary" plain @click="$router.push('/report')">
            <el-icon><Document /></el-icon>
            <span>实训报告</span>
          </el-button>
          <div class="wallet-card">
            <div class="wc-label">
              当前操作钱包
              <span v-if="app.currentRole?.role_key" class="dq-tag accent wc-role-badge">
                {{ app.currentRole?.role?.icon || '' }} {{ app.currentRole?.role?.name || app.currentRole?.role_key || '' }}
              </span>
            </div>
            <el-select
              v-model="walletModel"
              size="small"
              class="wc-select"
              popper-class="wc-popper"
            >
              <el-option
                v-for="w in walletList"
                :key="w.addr"
                :value="w.addr"
                :label="w.name + '  ' + w.addr"
              >
                <div class="wc-opt">
                  <span class="wc-opt-name">{{ w.name }}</span>
                  <span class="wc-opt-addr dq-mono">{{ w.addr }}</span>
                  <span class="wc-opt-role dq-tag" :class="w.klass">{{ w.role }}</span>
                </div>
              </el-option>
            </el-select>
          </div>
          <el-button size="small" @click="app.refreshStatus()">
            <el-icon><Refresh /></el-icon>
          </el-button>
          <!-- 登录用户卡片 + 登出 -->
          <el-popover v-if="auth.isLoggedIn" placement="bottom-end" trigger="click" :width="220" popper-class="user-pop">
            <template #reference>
              <div class="user-card" title="点击登出">
                <div class="uc-avatar">{{ avatarText }}</div>
                <div class="uc-info">
                  <div class="uc-name">{{ auth.displayName || '—' }}</div>
                  <div class="uc-role dq-tag" :class="roleClass">{{ auth.roleName }}</div>
                </div>
                <el-icon class="uc-arrow"><ArrowDown /></el-icon>
              </div>
            </template>
            <div class="user-pop-body">
              <div class="up-row"><span class="up-k">姓名</span><span class="up-v">{{ auth.displayName || '—' }}</span></div>
              <div class="up-row" v-if="auth.user?.username"><span class="up-k">学号</span><span class="up-v dq-mono">{{ auth.user.username }}</span></div>
              <div class="up-row" v-if="auth.user?.schoolName"><span class="up-k">学校</span><span class="up-v">{{ auth.user.schoolName }}</span></div>
              <div class="up-row"><span class="up-k">角色</span><span class="up-v" :class="roleClass">{{ auth.roleName }}</span></div>
              <el-button type="danger" size="small" class="up-logout" @click="onLogout">
                <el-icon><SwitchButton /></el-icon>&nbsp;退出登录
              </el-button>
            </div>
          </el-popover>
          <el-button v-else size="small" type="primary" @click="$router.push('/login')">
            <el-icon><User /></el-icon>&nbsp;登录
          </el-button>
        </div>
      </header>
      <main class="content">
        <router-view v-slot="{ Component }">
          <transition name="dq-fade" mode="out-in" appear>
            <keep-alive :max="20" :include="['dashboard','cloud','ide','contracts','interfaces','monitor','explorer','wallet','nft','report','grades']">
              <component :is="Component" :key="route.path" />
            </keep-alive>
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import Shortcuts from '@/components/Shortcuts.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown, Check, Document, Refresh, QuestionFilled, Right, SwitchButton, User } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const app = useAppStore()
const auth = useAuthStore()
const shortcutsRef = ref()

// 钱包选择器：通过 setter 统一写入，确保 store + localStorage + role 重置原子执行
// 直接 v-model="app.currentWallet" 会绕过 setWallet，导致 watcher 先用新钱包读到旧 role
const walletModel = computed<string>({
  get: () => app.currentWallet,
  set: (v: string) => app.setWallet(v),
})

type RouteItem = { path: string; title: string; icon: string; tag?: string }

/* ---------- 绿色低碳联盟链搭建实训：4 阶段菜单分组 ----------
   阶段 1 · 链底层搭建：启动节点 → 部署 GreenEnergy 绿色能量代币
   阶段 2 · 业务合约开发：开发/部署 PlantCertificate + EcoBadge 合约
   阶段 3 · 联盟治理与运营：6 角色配置 + 能量发放 + 资产兑换
   阶段 4 · 链上验证：监听器 + 浏览器
*/
const groupLearn: RouteItem[] = [
  { path: '/dashboard', title: '总览 · 联盟链', icon: 'DataBoard', tag: '起点' },
  { path: '/cloud', title: '云桌面 · 搭链教程', icon: 'Monitor', tag: '必修' },
]
const groupContract: RouteItem[] = [
  { path: '/ide', title: '合约 IDE', icon: 'EditPen' },
  { path: '/contracts', title: '合约管理', icon: 'Files' },
  { path: '/interfaces', title: '接口调试', icon: 'Connection' },
]
const groupExplorer: RouteItem[] = [
  { path: '/explorer', title: '区块链浏览器', icon: 'Search' },
]
const groupPractice: RouteItem[] = [
  { path: '/eco', title: '绿色低碳联盟链', icon: 'Promotion', tag: '核心' },
  { path: '/wallet', title: '能量钱包', icon: 'Wallet', tag: '工具' },
  { path: '/nft', title: '绿色资产市场', icon: 'Picture', tag: '工具' },
]
const groupEco: RouteItem[] = [
  { path: '/monitor', title: '调用监听器', icon: 'BellFilled' },
]

/* 教学管理分组：教师 / 管理员可见（在 template 中按 auth.canManageGrades 控制显示） */
const groupTeach: RouteItem[] = [
  { path: '/grades', title: '学生成绩', icon: 'Histogram', tag: '教师' },
]

const groupMap: Record<string, string> = {
  '/dashboard': '链底层搭建',
  '/cloud': '链底层搭建',
  '/ide': '业务合约开发',
  '/contracts': '业务合约开发',
  '/interfaces': '业务合约开发',
  '/explorer': '链上验证',
  '/eco': '联盟治理与运营',
  '/wallet': '联盟治理与运营',
  '/nft': '联盟治理与运营',
  '/monitor': '链上验证',
  '/report': '实训交付',
  '/grades': '教学管理',
}
const tagMap: Record<string, string> = {
  '/dashboard': '阶段 1 · 了解项目全貌',
  '/cloud': '阶段 1 · 搭建链底层',
  '/ide': '阶段 2 · 开发业务合约',
  '/contracts': '阶段 2 · 管理已部署合约',
  '/interfaces': '阶段 2 · 验证合约接口',
  '/eco': '阶段 3 · 联盟治理与运营',
  '/wallet': '阶段 3 · 能量钱包',
  '/nft': '阶段 3 · 绿色资产',
  '/monitor': '阶段 4 · 调用监听',
  '/explorer': '阶段 4 · 链上查询',
  '/report': '交付 · 生成报告',
  '/grades': '教学 · 学生成绩管理',
}
const progressMap: Record<string, number> = {
  '/dashboard': 8, '/cloud': 22,
  '/ide': 34, '/contracts': 42, '/interfaces': 52,
  '/eco': 70, '/wallet': 78, '/nft': 85,
  '/monitor': 92, '/explorer': 96, '/grades': 88, '/report': 100,
}

const defaultOpen = ['g-learn', 'g-contract', 'g-explorer', 'g-practice', 'g-eco', 'g-teach']

const reportItem: RouteItem = { path: '/report', title: '生成实训报告', icon: 'Document', tag: '交付' }
const menus = [...groupLearn, ...groupContract, ...groupExplorer, ...groupPractice, ...groupEco, ...groupTeach, reportItem]

const currentTitle = computed(() => {
  const m = menus.find((x) => route.path.startsWith(x.path))
  return m?.title || ''
})
const currentGroup = computed(() => {
  const m = menus.find((x) => route.path.startsWith(x.path))
  return m ? groupMap[m.path] || '' : ''
})
const tagLabel = computed(() => {
  const m = menus.find((x) => route.path.startsWith(x.path))
  return m ? tagMap[m.path] || '' : ''
})
const learnProgress = computed(() => {
  const m = menus.find((x) => route.path.startsWith(x.path))
  return m ? progressMap[m.path] || 0 : 0
})

const modeLabel = computed(() =>
  app.chainMode === 'fisco' ? 'FISCO-BCOS 联盟链节点'
    : app.chainMode === 'evm' ? 'EVM 虚拟机链路'
      : '本地沙盒链路'
)

const modes = [
  { value: 'fisco' as const, label: 'FISCO-BCOS 联盟链节点', desc: '对接已部署的 4 节点 PBFT 联盟链（需 Docker 搭链）' },
  { value: 'evm'   as const, label: 'EVM 虚拟机链路',          desc: '进程内 py-evm 虚拟机，完整 EVM 字节码执行（默认）' },
  { value: 'mock'  as const, label: '本地沙盒链路',        desc: '预置链路输出，用于快速体验教学流程' },
]

async function onSwitchMode(mode: 'fisco' | 'evm' | 'mock') {
  if (app.chainMode === mode) return
  try {
    await ElMessageBox.confirm(
      `确定将链引擎切换为「${mode.toUpperCase()}」模式吗？\n切换会重置链状态，当前块高、交易、合约部署记录将清空。`,
      '切换链模式',
      { type: 'warning', confirmButtonText: '确认切换', cancelButtonText: '取消' }
    )
  } catch { return }
  await app.setChainMode(mode)
  ElMessage.success(`已切换到「${mode.toUpperCase()}」模式`)
}

/* ---------- 登录用户头像 / 角色样式 / 登出 ---------- */
const avatarText = computed(() => {
  const n = auth.displayName || auth.user?.username || '?'
  // 取首字符（中文取首字 / 英文取首字母大写）
  return n.charAt(0).toUpperCase()
})
const roleClass = computed(() => {
  if (auth.isAdmin) return 'warn'
  if (auth.isTeacher) return 'primary'
  if (auth.isStudent) return 'info'
  return ''
})

async function onLogout() {
  try {
    await ElMessageBox.confirm('确认退出登录？', '退出确认', {
      type: 'warning', confirmButtonText: '退出', cancelButtonText: '取消',
    })
  } catch { return }
  auth.logout()
  ElMessage.success('已退出登录')
  router.replace('/login')
}

/* ---------- 绿色低碳联盟链内置角色钱包列表 ----------
   6 联盟节点组织钱包 + 3 普通用户钱包 + 1 学习者部署钱包，共 10 个。
   按联盟治理角色从高到低排列，便于实训中快速切换身份操作。
*/
const walletList = [
  { addr: '0xadmin',     name: '🛡️ 联盟管理员',   role: '超级管理员 / Owner',      klass: 'warn'   },
  { addr: '0xmetro',     name: '🚇 地铁集团',     role: '发能量方 +50 / 次',         klass: 'primary' },
  { addr: '0xbus',       name: '🚌 公交集团',     role: '发能量方 +20 / 次',         klass: 'primary' },
  { addr: '0xbike',      name: '🚲 共享单车',     role: '发能量方 +15 / 次',         klass: 'primary' },
  { addr: '0xtakeout',   name: '📦 外卖平台',     role: '发能量方 +10 / 次',         klass: 'primary' },
  { addr: '0xrecycle',   name: '♻️ 回收公司',     role: '发能量方 +100 / 次',        klass: 'accent'  },
  { addr: '0xlearner',   name: '👨‍🎓 学习者',      role: '合约部署者 / 实训发起方',    klass: ''        },
  { addr: '0xalice',     name: 'Alice',           role: '低碳用户 · 个人',           klass: 'info'    },
  { addr: '0xbob',       name: 'Bob',             role: '低碳用户 · 个人',           klass: 'info'    },
  { addr: '0xminter',    name: '铸造专员',        role: 'NFT 资产铸造方',            klass: 'accent'  },
]

onMounted(() => {
  app.refreshStatus()
  const t = setInterval(() => app.refreshStatus(), 15000)
  // 通知 shortcutsRef 暴露
  try { app.shortcutsOpen = shortcutsRef.value || null } catch {}
  return () => clearInterval(t)
})
</script>

<style scoped lang="scss">
.layout { display: flex; height: 100vh; overflow: hidden; }

/* ================= 侧边栏 ================= */
.sidebar {
  width: 260px;
  background: linear-gradient(180deg, var(--dq-bg-2) 0%, #0b1220 100%);
  border-right: 1px solid var(--dq-border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}
.logo {
  display: flex; align-items: center; gap: 12px;
  padding: 20px 20px 16px;
  border-bottom: 1px solid var(--dq-border);
  .logo-mark {
    width: 40px; height: 40px; border-radius: 10px;
    background: linear-gradient(135deg, rgba(0,230,195,0.15), rgba(0,230,195,0.03));
    border: 1px solid rgba(0,230,195,0.3);
    color: var(--dq-primary);
    font-size: 22px;
    display: inline-flex; align-items: center; justify-content: center;
    text-shadow: 0 0 12px var(--dq-primary-glow);
    flex-shrink: 0;
  }
  .t1 { font-weight: 800; letter-spacing: 2.5px; font-size: 18px; line-height: 1.2; }
  .t1-sub { font-weight: 500; letter-spacing: 1px; margin-left: 4px; opacity: 0.85; }
  .t2 { font-size: 11px; color: var(--dq-text-dim); margin-top: 2px; letter-spacing: 0.5px; }
  .t2-sub { font-family: var(--dq-mono); color: var(--dq-primary); opacity: 0.9; }
}

/* 分组菜单 */
.dq-menu { flex: 1; border-right: none !important; padding: 8px 6px; overflow-y: auto; background: transparent !important; }
.dq-menu :deep(.el-sub-menu__title) {
  height: 38px !important; line-height: 38px !important;
  color: var(--dq-text-dim) !important;
  font-weight: 600; font-size: 12px !important;
  text-transform: uppercase; letter-spacing: 0.5px;
  border-radius: 6px; margin: 2px 0;
  .menu-group-icon { margin-right: 6px; opacity: 0.85; font-size: 13px; }
  .menu-group-label { font-size: 12px; }
  &:hover { background: rgba(255,255,255,0.02); color: var(--dq-text) !important; }
}
.dq-menu :deep(.el-sub-menu) { border-bottom: 1px dashed rgba(31,42,68,0.6); padding-bottom: 4px; margin-bottom: 4px; }
.dq-menu :deep(.el-sub-menu:last-child) { border-bottom: none; }

.dq-menu :deep(.el-menu-item) {
  color: var(--dq-text-dim);
  height: 38px; line-height: 38px;
  margin: 2px 0;
  border-radius: 6px;
  font-size: 13px;
  display: flex; align-items: center; gap: 10px;
  .el-icon { color: var(--dq-text-dimmer); font-size: 14px; }
  &.is-active {
    color: var(--dq-primary);
    background: linear-gradient(90deg, rgba(0,230,195,0.10), rgba(0,230,195,0.02));
    border-left: none !important;
    font-weight: 600;
    .el-icon { color: var(--dq-primary); }
    &::before {
      content: ''; position: absolute; left: 0; top: 50%; transform: translateY(-50%);
      width: 3px; height: 18px; border-radius: 2px;
      background: var(--dq-grad-primary); box-shadow: 0 0 8px var(--dq-primary-glow);
    }
  }
  &:hover { background: rgba(255,255,255,0.03); color: var(--dq-text); }
}
.menu-tag {
  margin-left: auto;
  font-family: var(--dq-mono);
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  background: rgba(0,230,195,0.12);
  color: var(--dq-primary);
  border: 1px solid rgba(0,230,195,0.25);
  line-height: 1.5;
  &.accent { background: rgba(245,55,155,0.12); color: var(--dq-accent); border-color: rgba(245,55,155,0.25); }
}

/* 独立：生成实训报告（左栏最下方大选项） */
.report-entry {
  margin: 6px 10px 10px;
  padding: 12px 12px;
  border-radius: 12px;
  cursor: pointer;
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--dq-text);
  background:
    linear-gradient(135deg, rgba(0,230,195,0.10) 0%, rgba(77,141,255,0.08) 100%),
    rgba(255,255,255,0.015);
  border: 1px solid rgba(0,230,195,0.28);
  box-shadow: 0 0 0 1px rgba(0,230,195,0.06) inset, 0 4px 18px rgba(0,0,0,0.25);
  transition: all .2s ease;
  overflow: hidden;
  &::before {
    content: '';
    position: absolute;
    inset: -70%;
    background: conic-gradient(from 30deg, transparent 0%, rgba(0,230,195,0.35) 30%, transparent 55%, rgba(77,141,255,0.28) 80%, transparent 100%);
    opacity: 0;
    transition: opacity .3s;
    z-index: 0;
  }
  > * { position: relative; z-index: 1; }
  &:hover {
    transform: translateY(-1px);
    border-color: rgba(0,230,195,0.55);
    box-shadow: 0 0 0 1px rgba(0,230,195,0.18) inset, 0 8px 24px rgba(0,0,0,0.3), 0 0 16px rgba(0,230,195,0.18);
    &::before { opacity: 0.35; }
    .re-arrow { transform: translateX(2px); color: var(--dq-primary); }
  }
  &.active {
    background: linear-gradient(135deg, rgba(0,230,195,0.20) 0%, rgba(77,141,255,0.16) 100%);
    border-color: rgba(0,230,195,0.65);
    box-shadow: 0 0 0 1px rgba(0,230,195,0.25) inset, 0 0 20px rgba(0,230,195,0.28);
    &::before { opacity: 0.45; }
  }
  .re-icon-wrap {
    width: 40px; height: 40px;
    border-radius: 10px;
    flex-shrink: 0;
    background: linear-gradient(135deg, rgba(0,230,195,0.18), rgba(77,141,255,0.16));
    border: 1px solid rgba(0,230,195,0.35);
    display: inline-flex; align-items: center; justify-content: center;
    position: relative;
    .re-icon {
      color: var(--dq-primary);
      font-size: 20px;
      filter: drop-shadow(0 0 6px var(--dq-primary-glow));
    }
    .re-sparkle {
      position: absolute;
      right: -3px; top: -3px;
      width: 8px; height: 8px;
      border-radius: 50%;
      background: var(--dq-primary);
      box-shadow: 0 0 8px var(--dq-primary-glow);
      animation: dq-pulse 1.8s ease-in-out infinite;
    }
  }
  .re-info {
    flex: 1; min-width: 0;
    .re-title {
      display: flex; align-items: center; gap: 6px;
      font-size: 13px; font-weight: 700; color: var(--dq-text);
      letter-spacing: 0.2px;
    }
    .re-tag {
      font-size: 10px; font-family: var(--dq-mono);
      padding: 1px 6px;
      border-radius: 3px;
      background: linear-gradient(135deg, rgba(0,230,195,0.18), rgba(77,141,255,0.15));
      color: var(--dq-primary);
      border: 1px solid rgba(0,230,195,0.35);
      line-height: 1.5;
    }
    .re-sub {
      margin-top: 3px;
      font-size: 11px; color: var(--dq-text-dim); line-height: 1.4;
    }
  }
  .re-arrow {
    color: var(--dq-text-dimmer);
    font-size: 14px;
    transition: all .2s;
    flex-shrink: 0;
  }
}

/* 底部链状态 */
.sidebar-foot {
  padding: 14px 16px;
  border-top: 1px solid var(--dq-border);
  background: linear-gradient(180deg, rgba(14,20,36,0.4), rgba(11,18,32,0.9));
  .sf-title {
    font-size: 11px; color: var(--dq-text-dimmer);
    text-transform: uppercase; letter-spacing: 1px; font-weight: 600;
    margin-bottom: 10px;
    display: flex; align-items: center; justify-content: space-between;
    .sf-help { font-size: 10px; padding: 0 2px !important; min-height: unset !important; }
  }
  .sf-row {
    display: flex; justify-content: space-between; align-items: center;
    font-size: 12px; padding: 5px 0;
    &.mode-row { cursor: pointer; padding: 6px 8px; margin: 0 -8px 4px; border-radius: 6px;
      transition: background .15s;
      &:hover { background: rgba(255,255,255,0.03); }
      .mode-arrow { color: var(--dq-text-dimmer); font-size: 12px; transition: transform .2s; }
    }
  }
  .sf-k { color: var(--dq-text-dimmer); }
  .sf-v {
    color: var(--dq-text);
    font-family: var(--dq-mono);
    display: inline-flex; align-items: center; gap: 6px;
    &.mock { color: var(--dq-warn); }
    &.real, &.evm { color: var(--dq-success); }
    &.fisco { color: var(--dq-primary); }
    .mode-dot {
      width: 6px; height: 6px; border-radius: 50%; background: var(--dq-success);
      box-shadow: 0 0 6px var(--dq-success);
      animation: dq-pulse 1.6s ease-in-out infinite;
    }
    &.fisco .mode-dot { background: var(--dq-primary); box-shadow: 0 0 6px var(--dq-primary); }
    &.mock .mode-dot { background: var(--dq-warn); box-shadow: 0 0 6px var(--dq-warn); }
  }
  .sf-progress { margin-top: 12px; }
  .sf-p-label {
    display: flex; justify-content: space-between; align-items: center;
    font-size: 11px; color: var(--dq-text-dimmer); margin-bottom: 5px;
  }
  .sf-p-val { text-align: right; color: var(--dq-primary); font-size: 11px; margin-top: 3px; }
}

/* 模式切换弹窗 */
.mode-pop.el-popper { padding: 12px !important; }
.mode-switch {
  .ms-title { font-size: 13px; font-weight: 700; color: var(--dq-text); letter-spacing: 0.3px; }
  .ms-item {
    display: flex; align-items: center; gap: 10px;
    padding: 10px; margin-top: 6px;
    border-radius: 8px; border: 1px solid var(--dq-border);
    cursor: pointer; transition: all .15s;
    &:hover { background: var(--dq-bg-2); border-color: var(--dq-border-2); }
    &.active {
      background: linear-gradient(135deg, rgba(0,230,195,0.08), transparent);
      border-color: rgba(0,230,195,0.4);
      box-shadow: 0 0 0 1px rgba(0,230,195,0.2) inset;
    }
  }
  .ms-dot {
    width: 10px; height: 10px; border-radius: 50%;
    flex-shrink: 0;
    &.fisco { background: var(--dq-primary); box-shadow: 0 0 8px var(--dq-primary-glow); }
    &.evm   { background: var(--dq-success); box-shadow: 0 0 8px rgba(45,212,191,0.45); }
    &.mock  { background: var(--dq-warn);    box-shadow: 0 0 8px rgba(255,207,77,0.45); }
  }
  .ms-info { flex: 1; min-width: 0;
    .ms-name { font-size: 13px; font-weight: 600; color: var(--dq-text); }
    .ms-desc { font-size: 11px; color: var(--dq-text-dim); margin-top: 2px; }
  }
  .ms-check { color: var(--dq-primary); font-size: 14px; }
}

/* ================= 主体 ================= */
.main { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-width: 0; }

/* 顶栏 */
.topbar {
  height: 60px;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 22px;
  border-bottom: 1px solid var(--dq-border);
  background: var(--dq-grad-header);
  backdrop-filter: blur(12px);
  flex-shrink: 0;
  .topbar-left { display: flex; align-items: center; gap: 12px; }
  .crumbs { display: flex; align-items: center; gap: 8px; }
  .crumb-group {
    font-size: 12px; color: var(--dq-text-dim); font-weight: 500;
    text-transform: uppercase; letter-spacing: 0.8px;
    &::before {
      content: ''; display: inline-block; width: 6px; height: 6px; border-radius: 50%;
      background: var(--dq-primary); margin-right: 8px; vertical-align: middle;
      box-shadow: 0 0 6px var(--dq-primary-glow);
    }
  }
  .crumb-sep { color: var(--dq-border-strong); font-size: 12px; }
  .crumb-title { font-size: 16px; font-weight: 600; color: var(--dq-text); letter-spacing: 0.2px; }
  .dq-tag-group { font-size: 11px; padding: 2px 8px; letter-spacing: 0.3px; }
  .topbar-right { display: flex; align-items: center; gap: 10px; }
}

/* 钱包卡片 */
.wallet-card {
  display: flex; align-items: center; gap: 10px;
  padding: 4px 10px;
  border: 1px solid var(--dq-border);
  border-radius: 8px;
  background: rgba(255,255,255,0.01);
  .wc-label { font-size: 11px; color: var(--dq-text-dimmer); white-space: nowrap; display: flex; align-items: center; gap: 6px; }
  .wc-role-badge { font-size: 10px; padding: 1px 6px; }
  .wc-select { width: 280px; }
}
.wc-opt {
  display: flex; align-items: center; gap: 10px;
  .wc-opt-name { font-weight: 600; color: var(--dq-text); min-width: 64px; }
  .wc-opt-addr {
    color: var(--dq-text-dim); font-size: 12px; flex: 1;
    margin-right: auto;
  }
  .wc-opt-role { padding: 1px 6px; font-size: 10px; }
}
.wc-popper.el-select-dropdown { padding: 6px; }

/* 登录用户卡片 */
.user-card {
  display: flex; align-items: center; gap: 8px;
  padding: 3px 10px 3px 4px;
  border: 1px solid var(--dq-border);
  border-radius: 8px;
  background: rgba(255,255,255,0.01);
  cursor: pointer;
  transition: all .15s;
  &:hover {
    border-color: var(--dq-border-2);
    background: rgba(0,230,195,0.04);
    .uc-arrow { transform: translateY(1px); color: var(--dq-primary); }
  }
  .uc-avatar {
    width: 26px; height: 26px;
    border-radius: 50%;
    background: var(--dq-grad-info);
    color: #fff;
    font-size: 13px; font-weight: 700;
    display: inline-flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    box-shadow: 0 0 0 1px rgba(255,255,255,0.06) inset;
  }
  .uc-info {
    display: flex; flex-direction: column; gap: 2px;
    line-height: 1.1;
    .uc-name { font-size: 12px; font-weight: 600; color: var(--dq-text); max-width: 90px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .uc-role { padding: 0 5px; font-size: 10px; line-height: 1.4; align-self: flex-start;
      &.warn { color: var(--dq-warn); background: rgba(255,207,77,0.10); border: 1px solid rgba(255,207,77,0.25); }
      &.primary { color: var(--dq-primary); background: rgba(0,230,195,0.10); border: 1px solid rgba(0,230,195,0.25); }
      &.info { color: var(--dq-info); background: rgba(77,141,255,0.10); border: 1px solid rgba(77,141,255,0.25); }
    }
  }
  .uc-arrow { color: var(--dq-text-dimmer); font-size: 11px; transition: all .15s; }
}

/* 用户信息弹层 */
.user-pop.el-popper { padding: 12px !important; }
.user-pop-body {
  .up-row {
    display: flex; justify-content: space-between; align-items: center;
    font-size: 12px; padding: 5px 0;
    border-bottom: 1px dashed rgba(31,42,68,0.6);
    &:last-of-type { border-bottom: none; }
    .up-k { color: var(--dq-text-dimmer); }
    .up-v { color: var(--dq-text); font-weight: 500; }
    .up-v.warn { color: var(--dq-warn); }
    .up-v.primary { color: var(--dq-primary); }
    .up-v.info { color: var(--dq-info); }
  }
  .up-logout { width: 100%; margin-top: 12px; }
}

.content { flex: 1; overflow: auto; padding: 18px 22px; }

/* ============ 切 tab 瞬时 fade 过渡（<150ms，无整页白屏感） ============ */
.dq-fade-enter-active,
.dq-fade-leave-active {
  transition: opacity .14s linear, transform .16s ease-out;
}
.dq-fade-enter-from { opacity: 0; transform: translateY(6px); }
.dq-fade-leave-to   { opacity: 0; transform: translateY(-4px); }</style>
