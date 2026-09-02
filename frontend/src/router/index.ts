import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'
import { defineAsyncComponent } from 'vue'
import { useAuthStore } from '@/stores/auth'

/* 异步加载重页面：切 tab 时才开始加载（首屏不加载 Monaco/ECharts），配合 keep-alive 二次命中秒开 */
const asyncPage = (loader: () => Promise<any>) => defineAsyncComponent({
  loader,
  delay: 0,
  timeout: 20000,
  loadingComponent: {
    template: `<div style="display:flex;align-items:center;justify-content:center;min-height:60vh;color:#8fa0c4;font-size:12px;">
      <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#00e6c3;margin-right:8px;animation:dq-pulse 1s ease-in-out infinite;"></span>
      页面加载中…
      <style>@keyframes dq-pulse{0%,100%{opacity:.4}50%{opacity:1}}</style>
    </div>`,
  },
})

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    children: [
      { path: '', redirect: '/dashboard' },
      { path: 'dashboard',  name: 'dashboard',  component: asyncPage(() => import('@/views/Dashboard.vue')),  meta: { title: '总览',          icon: 'DataBoard' } },
      { path: 'cloud',      name: 'cloud',      component: asyncPage(() => import('@/views/CloudDesktop.vue')), meta: { title: '搭链云桌面',       icon: 'Monitor'   } },
      { path: 'ide',        name: 'ide',        component: asyncPage(() => import('@/views/ContractIDE.vue')),  meta: { title: '合约 IDE',       icon: 'EditPen'   } },
      { path: 'contracts',  name: 'contracts',  component: asyncPage(() => import('@/views/Contracts.vue')),    meta: { title: '合约管理',       icon: 'Files'     } },
      { path: 'interfaces', name: 'interfaces', component: asyncPage(() => import('@/views/Interfaces.vue')),   meta: { title: '接口调试',       icon: 'Connection'} },
      { path: 'monitor',    name: 'monitor',    component: asyncPage(() => import('@/views/Monitor.vue')),      meta: { title: '调用监听器',     icon: 'BellFilled'} },
      { path: 'explorer',   name: 'explorer',   component: asyncPage(() => import('@/views/Explorer.vue')),     meta: { title: '区块链浏览器',   icon: 'Search'    } },
      { path: 'explorer/address/:addr', name: 'explorer-addr', component: asyncPage(() => import('@/views/Explorer.vue')) },
      { path: 'nft',        name: 'nft',        component: asyncPage(() => import('@/views/NftMarket.vue')),    meta: { title: 'NFT 交易市场',   icon: 'Picture'   } },
      { path: 'wallet',     name: 'wallet',     component: asyncPage(() => import('@/views/Wallet.vue')),       meta: { title: 'ERC20 钱包',     icon: 'Wallet'    } },
      { path: 'eco',        name: 'eco',        component: asyncPage(() => import('@/views/EcoPractice.vue')),  meta: { title: '绿色低碳联盟链',  icon: 'Promotion' } },
      { path: 'report',     name: 'report',     component: asyncPage(() => import('@/views/Report.vue')),       meta: { title: '实训报告',       icon: 'Document'  } },
      { path: 'my-grades',  name: 'my-grades',  component: asyncPage(() => import('@/views/MyGrades.vue')),     meta: { title: '我的成绩',       icon: 'Trophy'    } },
      { path: 'achievements', name: 'achievements', component: asyncPage(() => import('@/views/Achievements.vue')), meta: { title: '成就中心',       icon: 'Medal'     } },
      // 教师专属：学生成绩管理
      {
        path: 'grades',
        name: 'grades',
        component: asyncPage(() => import('@/views/Grades.vue')),
        meta: { title: '学生成绩', icon: 'Histogram', requiresTeacher: true },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

/* 全局路由守卫：未登录跳 /login；非教师访问 /grades 跳 /dashboard */
router.beforeEach((to, _from, next) => {
  const auth = useAuthStore()

  // SSO 回调：URL 携带 token 时，无论是否已登录，都统一到 /dashboard 处理重新登录
  // （已登录也重新登录，避免旧会话残留 / 切换账号场景）
  const urlToken =
    new URLSearchParams(window.location.search).get('token') ||
    (to.query.token as string) ||
    ''
  if (urlToken) {
    // 已在 /dashboard 则放行，让 Dashboard 组件处理 token 登录
    if (to.path === '/dashboard') return next()
    // 其他路径重定向到 /dashboard（保留 token）
    return next({ path: '/dashboard', query: { token: urlToken } })
  }

  // 以下为无 token 的常规鉴权
  if (to.meta?.public) {
    // 单点登录自动检测：已保持登录会话则直接跳过登录页
    if (to.path === '/login' && auth.isLoggedIn) return next('/dashboard')
    return next()
  }
  if (!auth.isLoggedIn) {
    return next({ path: '/login', query: { redirect: to.fullPath } })
  }
  if (to.meta?.requiresTeacher && !auth.canManageGrades) {
    return next('/dashboard')
  }
  next()
})

export default router
