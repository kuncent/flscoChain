import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'
import { defineAsyncComponent, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { setSsoRedeeming } from '@/api/http'

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

/**
 * SSO token 兑换：URL 带 token（智云 SSO 回调）时，**在放行任何页面组件之前**换好平台 JWT。
 *
 * 为什么必须放在守卫里而不是页面组件里（修复「退出登录后再带 token 进来必跳登录页」）：
 * 旧实现由 Dashboard 的 onMounted 兑换 token，而 Dashboard 是异步 chunk，换 JWT 又要等一次
 * 外部 SSO 往返；这段窗口里 MainLayout / Dashboard 已经发出**不带 Authorization** 的鉴权请求
 * （platform-progress / tutorial/progress / achievements…）并拿到 401，http 拦截器据此判定
 * 「当前凭据过期」→ 清掉刚下发的 JWT 并 push('/login')；push('/login') 又把 hash 上的 token
 * 一起丢光，于是再没人兑换它 —— 表现为静默回到登录页。守卫 await 到 JWT 落地才放行，
 * 这个窗口就不存在了（未登录时不存在带凭据的页面请求）。
 */

/** 已成功兑换过且会话仍在的 SSO token：同一次回调只换一次，守卫重入不重复打 SSO */
let ssoRedeemedToken = ''
/** 进行中的兑换请求（以 token 为键）：同一个 token 的并发导航共享一次请求，不同 token 之间不互相覆盖 */
let ssoPending: { token: string; p: Promise<SsoResult> } | null = null

interface SsoResult { ok: boolean; msg: string }

/**
 * 守卫正在用 URL 上的 token 换 JWT（外部 SSO 往返实测 ~1.5s）。
 * 期间页面组件还未挂载：1) 由 App.vue 摆一条状态提示，避免全屏空白；
 * 2) 同时给 http 拦截器置闸门（setSsoRedeeming），不让真空期里那些无凭据的 401
 *    把刚下发的 JWT 当“过期凭据”抹掉（否则守卫上提了也没用，仍会被踢回登录页）。
 */
export const ssoRedeeming = ref(false)

/** 抹掉 URL 上的 token（search 与 hash query 两处）：JWT 不该进浏览器历史 / Referer / 代理日志 */
function stripUrlToken() {
  try {
    const clean = window.location.origin + window.location.pathname + window.location.hash.split('?')[0]
    window.history.replaceState(null, '', clean)
  } catch {
    /* 某些沙箱环境禁止改历史，忽略即可，不影响登录 */
  }
}

async function redeemSsoToken(token: string): Promise<SsoResult> {
  const auth = useAuthStore()
  // 同一个 token 已兑换过、且会话还在：直接复用，不重复请求
  // （会话已被登出清掉时 ssoRedeemedToken 命中也要重新兑换，否则会把用户送进未登录的 dashboard）
  if (ssoRedeemedToken === token && auth.isLoggedIn) return { ok: true, msg: '' }
  if (ssoPending?.token === token) return ssoPending.p

  const p = auth
    .loginByToken(token)
    .then((u) => {
      ssoRedeemedToken = token
      ElMessage.success(`欢迎回来，${u.name || u.username}`)
      return { ok: true, msg: '' } satisfies SsoResult
    })
    .catch((e: any) => {
      const status = Number(e?.response?.status) || 0
      // 401 / 403：http 拦截器对登录接口刻意不弹全局提示（见 handleAuthExpired 的早退），
      // 这里必须把后端转发的外部 msg（如「token 无效！」）说清楚，不能静默跳登录页；
      // 其余状态码（400 / 502 / 500）拦截器已经弹过 detail，再弹就是重复提示
      const own = status === 401 || status === 403
      return {
        ok: false,
        msg: own
          ? String(e?.response?.data?.detail || '智云 Token 无效或已过期，请重新从平台入口进入')
          : '',
      } satisfies SsoResult
    })

  ssoPending = { token, p }
  try {
    return await p
  } finally {
    // 只清自己这一次（期间可能有新 token 接管）
    if (ssoPending?.p === p) ssoPending = null
  }
}

/* 全局路由守卫：URL 带 token 先换会话；其余按登录态鉴权，非教师访问 /grades 跳 /dashboard */
router.beforeEach(async (to, _from, next) => {
  const auth = useAuthStore()

  // SSO 回调：URL 携带 token 时，无论是否已登录，都重新登录（覆盖旧会话 / 切换账号）
  const urlToken =
    new URLSearchParams(window.location.search).get('token') ||
    (to.query.token as string) ||
    ''
  if (urlToken) {
    // 先抹 URL 再发请求：兑换失败也不能把 JWT 留在地址栏 / 历史记录里
    stripUrlToken()
    ssoRedeeming.value = true
    setSsoRedeeming(true)
    let res: SsoResult
    try {
      res = await redeemSsoToken(urlToken)
    } finally {
      ssoRedeeming.value = false
      setSsoRedeeming(false)
    }
    if (res.ok) return next({ path: '/dashboard', replace: true })
    if (res.msg) ElMessage.error(res.msg)
    // token 已从 URL 抹掉，这里不会再命中上面的分支，不会自循环
    return next({ path: '/login', query: { redirect: '/dashboard' }, replace: true })
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
