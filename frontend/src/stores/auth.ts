import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { authApi } from '@/api'
import { safeGet, safeSet, safeDel } from '@/utils/storage'

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
   * 单点登录 · 会话校验
   * 不再请求外部智云 SSO，仅校验当前是否保持登录态：
   *   - http 拦截器会从 localStorage 'auth_user' 自动注入身份头（Authorization / X-User-Id / X-Role-Id）
   *   - 后端 /auth/session 仅判断这些头是否存在，不调用任何外部服务
   * 若会话保持：直接用本地缓存 user 恢复登录态（store 已在初始化时从 localStorage 载入）
   * 若会话未保持：抛错，由调用方引导用户改用账号密码登录
   */
  async function checkSession(): Promise<AuthUser> {
    const res: any = await authApi.session()
    if (!res?.active) {
      throw new Error(res?.message || '未检测到登录会话')
    }
    // store 初始化时已从 localStorage 载入 user；若仍为空则视为会话已失效
    if (!user.value) {
      // 兜底：直接从 localStorage 取一次
      const cached = safeGet<AuthUser | null>(STORAGE_KEY, null)
      if (!cached) throw new Error('登录会话已失效，请使用账号密码登录')
      _persist(cached)
    }
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
    return u
  }

  function _roleName(rid: number): string {
    return { 1: '管理员', 3: '教师', 4: '学生' }[rid] || '未知'
  }

  function logout() {
    _persist(null)
  }

  return {
    user, isLoggedIn, roleId, roleName, isTeacher, isAdmin, isStudent,
    canManageGrades, displayName,
    loginByPassword, loginByToken, checkSession, logout,
  }
})
