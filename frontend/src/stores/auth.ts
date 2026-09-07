import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { authApi } from '@/api'
import { AUTH_TOKEN_KEY } from '@/api/http'
// 任务 #21/#25：登录成功后建立 SSE 推送连接，登出时断开（单例幂等）
import { eventStream } from '@/api/events'
import { safeGet, safeSet, safeDel } from '@/utils/storage'
import { isChainAddress } from '@/utils/address'
import { useAppStore } from '@/stores/app'

export type UserRole = 1 | 3 | 4 // 1=管理员 3=教师 4=学生

export interface AuthUser {
  userId: string
  /** 姓名（SSO 的 name；实测 username 也回传姓名，两者不区分来源） */
  name: string
  /** ⚠ 实测 SSO 把**姓名**装进了 username，不是登录账号，不得用来定位人 */
  username: string
  /** ⚠ 实测 SSO 把**登录账号**（手机号 / 工号）装进了 studentId，不是学号 */
  studentId?: string
  accessToken: string
  roleId: UserRole
  roleName: string
  classId?: string          // 班级 ID（学生=所属班级，教师=管理班级；与后端 TEXT 一致）
  schoolId?: string         // ★ 成绩归档边界字段（后端 school_of_expr / teacher_scope 同源）
  schoolName?: string       // 仅展示，比较一律用 schoolId
  collegeId?: string
  majorId?: string
  wallet?: string           // 一人一钱包：登录账号本人的**真实链上地址**（0x + 40 hex），对应「我的钱包」
  studentWallet?: string     // 学生专属钱包别名（stu:xxx，仅展示 / 密钥库反查）
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
   * 会话恢复：后端 /auth/session 对 Bearer JWT 真实验签，并**从 user_info 回查权威身份**
   *   （name / username / studentId / classId / schoolId / schoolName / collegeId / wallet）。
   *   - 拦截器从 localStorage 'auth_token' 自动注入 Authorization 头；
   *   - 验签成功（active=true）：用本地缓存 user 打底、后端回查值覆盖（后端为准）；
   *   - 无有效 token / 验签失败（active=false）：抛错，由调用方引导账号密码登录。
   *
   * 为什么要覆盖本地缓存（P1-33）：学校 / 班级是成绩归档边界的依据，可能在后台被改绑，
   * 而 JWT 载荷里根本没有 school_id。旧版只验签不回查，前端永远拿着登录当时的缓存值
   * （或是缓存丢失后的空值），表现为“教师端明明有学校却显示未定范围”。
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
    const pick = (v: any) => (v === undefined || v === null ? '' : String(v))
    const res: any = await authApi.session()
    if (!res?.active) {
      _persistToken(null)  // JWT 失效：清除本地凭据，引导重新登录
      throw new Error(res?.message || '登录会话已失效，请使用账号密码登录')
    }
    // store 初始化时已从 localStorage 载入 user；若仍为空则用会话回查值重建一份
    // （清了缓存但留着 token 的场景：旧版直接报“会话失效”，现在能就地恢复）
    const cached = user.value || safeGet<AuthUser | null>(STORAGE_KEY, null)
    const uid = pick(res.userId) || cached?.userId || ''
    if (!uid) throw new Error('登录会话已失效，请使用账号密码登录')
    /** 后端回查值为权威：非空就覆盖（空值不覆盖，避免把已知字段抹成空） */
    const keep = (next: string, prev?: string) => next || prev || ''
    const merged: AuthUser = {
      userId: uid,
      roleId: (Number(res.roleId) || cached?.roleId || 0) as UserRole,
      roleName: keep(pick(res.roleName), cached?.roleName),
      name: keep(pick(res.name), cached?.name),
      username: keep(pick(res.username), cached?.username),
      studentId: keep(pick(res.studentId), cached?.studentId),
      classId: keep(pick(res.classId), cached?.classId),
      schoolId: keep(pick(res.schoolId), cached?.schoolId),
      schoolName: keep(pick(res.schoolName), cached?.schoolName),
      collegeId: keep(pick(res.collegeId), cached?.collegeId),
      majorId: keep(pick(res.majorId), cached?.majorId),
      accessToken: cached?.accessToken || '',
      wallet: cached?.wallet || '',
      studentWallet: cached?.studentWallet || '',
    }
    // 会话恢复：后端已重新校验 / 补发学生钱包，本人地址与本地缓存不一致时以本人地址
    // 为准（旧版只验签不同步钱包 → 升级后缓存里仍是 stu: 别名，资产页读写两套口径）
    const addr = String(res?.student_wallet_address || res?.wallet || '').trim()
    if (isChainAddress(addr)) {
      merged.wallet = addr
      merged.studentWallet = String(res?.student_wallet || '') || merged.studentWallet
    }
    _persist(merged)
    if (isChainAddress(merged.wallet)) {
      try { useAppStore().setWallet(merged.wallet!) } catch { /* pinia 未就绪时忽略 */ }
    }
    // 任务 #25：登录成功 → 以新 token 重启 SSE 推送连接（reconnect 清零失败计数并解除停机；
    // 未登录/环境不支持时 connect 内部自行短路，单例语义不变）
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
    // 一人一钱包：登录后切到本人钱包（一律用后端下发的**真实链上地址**，
    // 不再用 stu: 别名 / userId：带冒号连字符的内部标识不是钱包，写进资产表就是 P0-2 根因）。
    // 不能沿用 localStorage 残留值——同一浏览器换账号登录时，残留的公共演示钱包
    // （0xlearner）会导致不同账号看到相同的资产与实训进度。
    try {
      const own = [
        String(data.student_wallet_address || ''),
        String(data.wallet || ''),
      ].find(isChainAddress) || ''
      if (own) {
        useAppStore().setWallet(own)
        u.wallet = own  // 持久化到用户信息，供「我的钱包」选项与角色联动读取
        u.studentWallet = String(data.student_wallet || '') || u.studentWallet
        _persist(u)
      } else if (data.roster_ok === false) {
        // 后端未能落库 / 未发钱包：不猜测钱包，避免把 userId 当资产地址写进台账
        console.warn('[auth] 登录未返回本人链上地址，请重新登录发放钱包')
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
