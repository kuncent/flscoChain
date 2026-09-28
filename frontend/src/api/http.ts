import axios from 'axios'
import { ElMessage } from 'element-plus'
import { safeGet } from '@/utils/storage'

/** 平台签发 JWT 的存储键（登录成功写入，登出清除；与后端 app/security.py 约定一致） */
export const AUTH_TOKEN_KEY = 'auth_token'

const http = axios.create({
  baseURL: '/api',
  timeout: 20000,
})

/**
 * SSO 兑换闸门（由 router/index.ts 的守卫在等外部 SSO 往返时置位）。
 *
 * 为什么需要它：URL 带 token 进入时，守卫要在页面组件挂载前把 token 换成 JWT，
 * 这段真空期里已经发出的鉴权请求必然不带凭据 → 必定 401；若把它们当成
 * 「当前凭据过期」，就会抹掉守卫刚下发的 JWT 并把用户踢回登录页（并且踢回时
 * 还会把 URL 上的 token 一并丢光）。这就是“退出登录后再带 token 进来必跳登录页”
 * 的最后一公里：只把兑换上提到守卫仍不够，旧的残留 401 还是能误杀新会话。
 */
let ssoRedeeming = false
export function setSsoRedeeming(value: boolean): void {
  ssoRedeeming = value
}

/**
 * 401 统一处理（防弹窗轰炸 + 防跨标签页误杀）：
 * - SSO 兑换进行中 → 一律当成真空期噪声，静默忽略（新会话即将落地）；
 * - 请求未带凭据但现在已有凭据 → 该 401 发生在登录之前，不是当前凭据过期；
 * - 请求注入的 token 与当前 localStorage 中的 token 不一致 → 该 401 来自旧凭据请求，
 *   说明本标签页或其他标签页已重新登录，静默忽略、绝不动新凭据；
 * - 否则当前凭据确已失效：清除 token + 登录态，只提示一次并跳转登录页；
 * - 并发轮询（成就/状态等）多次 401 只处理一次，避免 ElMessage 刷屏。
 * 登录/加密接口自身失败也是 401（密码错误），由调用方展示后端 msg，不在此劫持。
 */
let authExpiredHandled = false
function handleAuthExpired(config: any) {
  const url = String(config?.url || '')
  if (url.startsWith('/auth/login') || url.startsWith('/auth/encrypt')) return
  let currentToken = ''
  try {
    currentToken = localStorage.getItem(AUTH_TOKEN_KEY) || ''
  } catch {
    /* ignore */
  }
  const sentToken = String(config?.headers?.Authorization || '').replace(/^Bearer\s+/i, '')
  // SSO 正在把 URL 上的 token 换成会话：此时所有 401 都是登录前的残留请求
  if (ssoRedeeming) return
  // 发出时根本没带凭据、而现在已有凭据：新会话已落地，不能当成“过期”误杀
  if (!sentToken && currentToken) return
  // 旧请求（其他标签页/登录前的残留请求）触发的 401：不碰当前新凭据、不提示、不跳转
  if (sentToken && currentToken && sentToken !== currentToken) return
  if (authExpiredHandled) return
  authExpiredHandled = true
  try {
    localStorage.removeItem(AUTH_TOKEN_KEY)
  } catch {
    /* ignore */
  }
  ElMessage.error('登录已过期，请重新登录')
  // 清除登录态并跳转登录页（动态 import 避免 http ↔ stores/router 循环依赖）；
  // 跳转后页面组件卸载，后台轮询随之停止，不会继续产生 401
  Promise.all([import('@/stores/auth'), import('@/router')])
    .then(([authMod, routerMod]) => {
      authMod.useAuthStore().logout()
      routerMod.default.push({ path: '/login' })
    })
    .catch(() => {
      try {
        localStorage.removeItem('auth_user')
      } catch {
        /* ignore */
      }
      window.location.hash = '#/login'
    })
    .finally(() => {
      // 短暂节流后复位，允许后续新会话再次过期时正常引导（不影响跳转本身）
      setTimeout(() => {
        authExpiredHandled = false
      }, 3000)
    })
}

/**
 * 请求拦截：自动注入 Authorization: Bearer <JWT>。
 * 后端统一对该 JWT 验签解析身份（见 backend/app/security.py），
 * X-* 自报头已被后端废弃，不再作为身份凭据。
 */
http.interceptors.request.use((config) => {
  let token = ''
  try {
    token = localStorage.getItem(AUTH_TOKEN_KEY) || ''
  } catch {
    token = ''
  }
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`
  }
  // 仅本地开发调试时附带旧 X-* 头（需后端 AUTH_DEV_HEADER_FALLBACK=true 才会被读取）；
  // 生产构建不注入，身份一律以 JWT 验签为准
  if (import.meta.env.DEV) {
    const user = safeGet<any>('auth_user', null)
    if (user) {
      config.headers['X-User-Id'] = user.userId || ''
      config.headers['X-User-Name'] = encodeURIComponent(user.name || user.username || '')
      config.headers['X-Role-Id'] = String(user.roleId ?? '')
      config.headers['X-Class-Id'] = String(user.classId ?? '')
      // 钱包头只带**真实链上地址**（顶栏当前操作钱包 → 登录下发的本人地址），
      // userId 仅作最后兜底；不再写死 0xlearner（公共演示别名，会串账号）
      config.headers['X-Wallet'] =
        localStorage.getItem('wallet') || user.wallet || user.userId || ''
    }
  }
  return config
})

http.interceptors.response.use(
  (r) => r.data,
  (err) => {
    const status = err.response?.status
    const msg = err.response?.data?.detail || err.message || '请求失败'
    if (status === 401) {
      // 401 = 未登录 / JWT 失效：统一走 handleAuthExpired（去重 + 跨标签页保护 + 引导重登），
      // 不再逐请求弹 ElMessage（轮询接口 401 会刷屏）
      handleAuthExpired(err.config)
      return Promise.reject(err)
    }
    ElMessage.error(msg)
    return Promise.reject(err)
  }
)

export default http
