import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { authApi } from '@/api'
import { AUTH_TOKEN_KEY } from '@/api/http'
// 任务 #21/#25：登录成功后建立 SSE 推送连接，登出时断开（单例幂等）
import { eventStream } from '@/api/events'
import { safeGet, safeSet, safeDel } from '@/utils/storage'
import { useAppStore } from '@/stores/app'

export type UserRole = 1 | 3 | 4 // 1=管理员 3=教师 4=学生

export interface AuthUser {
  userId: string
  name: string
  username: string
  studentId?: string
  accessToken: string
  roleId: UserRole
  roleName: string
  classId?: string          // 班级 ID（学生=所属班级，教师=管理班级；与后端 TEXT 一致）
  schoolId?: string
  schoolName?: string
  collegeId?: string
  majorId?: string
  wallet?: string           // 一人一钱包：登录账号本人钱包（学生 = stu: 专属别名，教师/管理员 = 账号 ID），对应「我的钱包」普通用户身份
}

const STORAGE_KEY = 'auth_user'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<AuthUser | null>(safeGet<AuthUser | null>(STORAGE_KEY, null))

  const isLoggedIn = computed(() => !!user.value)
  const roleId = computed(() => user.value?.roleId ?? 0)
  const roleName = computed(() => user.value?.roleName || '')
  const isTeacher = computed(() => user.value?.roleId === 3)
  const isAdmin = computed(() => user.value?.roleId === 1)
  const isStudent = computed(() => user.value?.roleId === 4)
  /** 教师或管理员：可访问学生成绩模块 */
  const canManageGrades = computed(() => isTeacher.value || isAdmin.value)
  const displayName = computed(() => user.value?.name || user.value?.username || '')

  function _persist(u: AuthUser | null) {
    user.value = u
    if (u) safeSet(STORAGE_KEY, u)
    else safeDel(STORAGE_KEY)
  }

  /** 保存 / 清除后端签发的 JWT（拦截器据此注入 Authorization: Bearer） */
  function _persistToken(token: string | null) {
    try {
      if (token) localStorage.setItem(AUTH_TOKEN_KEY, token)
      else localStorage.removeItem(AUTH_TOKEN_KEY)
    } catch {
      /* localStorage 不可用时忽略（会话不跨刷新保持） */
    }
  }

  /** 账号密码登录：先加密密码，再调用登录接口 */
  async function loginByPassword(username: string, password: string): Promise<AuthUser> {
    const encRes: any = await authApi.encrypt(password)
    const encPwd = encRes.data
    if (!encPwd) throw new Error('密码加密失败')
    const data: any = await authApi.login({ username, passwordEncode: encPwd })
    return _applyLogin(data)
  }

  /** SSO Token 登录：URL 携带 token 参数时优先使用 */
  async function loginByToken(token: string): Promise<AuthUser> {
    const data: any = await authApi.login({ TOKEN: token })
    return _applyLogin(data)
  }

  /**
   * 会话恢复：后端 /auth/session 对 Bearer JWT 真实验签。
   *   - 拦截器从 localStorage 'auth_token' 自动注入 Authorization 头；
   *   - 验签成功（active=true）：用本地缓存 user 恢复登录态；
   *   - 无有效 token / 验签失败（active=false）：抛错，由调用方引导账号密码登录。
   */
  async function checkSession(): Promise<AuthUser> {
    // 无本地凭据时无需请求，直接引导登录
    let hasToken = false
    try {
      hasToken = !!localStorage.getItem(AUTH_TOKEN_KEY)
    } catch {
      hasToken = false
    }
    if (!hasToken) {
      throw new Error('未检测到有效登录凭据，请使用账号密码登录')
    }
    const res: any = await authApi.session()
    if (!res?.active) {
      _persistToken(null)  // JWT 失效：清除本地凭据，引导重新登录
      throw new Error(res?.message || '登录会话已失效，请使用账号密码登录')
    }
    // store 初始化时已从 localStorage 载入 user；若仍为空则视为会话已失效
    if (!user.value) {
      // 兜底：直接从 localStorage 取一次
      const cached = safeGet<AuthUser | null>(STORAGE_KEY, null)
      if (!cached) throw new Error('登录会话已失效，请使用账号密码登录')
      _persist(cached)
    }
    // 会话恢复成功：确保 SSE 连接在场（reconnect 幂等重启：已存活连接先拆后建，
    // 若曾因失败上限停机则清零重启）
    eventStream.reconnect()
    return user.value as AuthUser
  }

  function _applyLogin(data: any): AuthUser {
    const u: AuthUser = {
      userId: data.userId,
      name: data.name || data.username,
      username: data.username,
      studentId: data.studentId,
      accessToken: data.accessToken,
      roleId: data.roleId,
      roleName: data.roleName || _roleName(data.roleId),
      classId: data.classId != null ? String(data.classId) : undefined,
      schoolId: data.schoolId != null ? String(data.schoolId) : undefined,
      schoolName: data.schoolName,
      collegeId: data.collegeId != null ? String(data.collegeId) : undefined,
      majorId: data.majorId != null ? String(data.majorId) : undefined,
    }
    _persist(u)
    // 保存后端签发的平台 JWT（24h 有效），后续请求由拦截器自动注入
    _persistToken(data.token || null)
    // 一人一钱包：登录后切到本人钱包（学生 = 后端发放的 stu: 专属别名，
    // 教师/管理员 = userId）。不能沿用 localStorage 残留值——同一浏览器换账号登录时，
    // 残留的公共演示钱包（0xlearner）会导致不同账号看到相同的资产与实训进度。
    try {
      const own = String(data.student_wallet || data.wallet || u.userId || '')
      if (own) {
        useAppStore().setWallet(own)
        u.wallet = own  // 持久化到用户信息，供「我的钱包」选项等读取本人钱包地址
        _persist(u)
      }
    } catch { /* pinia 未就绪等异常不影响登录主流程 */ }
    // 任务 #25：登录成功 → 以新 token 重启 SSE 推送连接（reconnect 清零失败计数并解除停机；
    // 未登录/环境不支持时 connect 内部自行短路，单例语义不变）
    eventStream.reconnect()
    return u
  }

  function _roleName(rid: number): string {
    return { 1: '管理员', 3: '教师', 4: '学生' }[rid] || '未知'
  }

  function logout() {
    eventStream.disconnect()  // 任务 #25：先断 SSE（阻止后续重连），再清凭据，避免拿旧 token 重连
    _persist(null)
    _persistToken(null)  // 同步清除 JWT 凭据
  }

  return {
    user, isLoggedIn, roleId, roleName, isTeacher, isAdmin, isStudent,
    canManageGrades, displayName,
    loginByPassword, loginByToken, checkSession, logout,
  }
})
