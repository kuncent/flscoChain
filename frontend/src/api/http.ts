import axios from 'axios'
import { ElMessage } from 'element-plus'
import { safeGet } from '@/utils/storage'

const http = axios.create({
  baseURL: '/api',
  timeout: 20000,
})

/** 请求拦截：自动附加登录身份头（成绩等模块做角色校验） */
http.interceptors.request.use((config) => {
  // 当前学生链上钱包（用于后端 learning_events 归属 + 成绩闭环）
  config.headers['X-Wallet'] = localStorage.getItem('wallet') || '0xlearner'
  const user = safeGet<any>('auth_user', null)
  if (user) {
    config.headers['X-User-Id'] = user.userId || ''
    config.headers['X-User-Name'] = encodeURIComponent(user.name || user.username || '')
    config.headers['X-Role-Id'] = String(user.roleId ?? '')
    // 班级 ID：学生=所属班级，教师=管理班级；后端用于按班级过滤成绩 / 班级整体进度
    config.headers['X-Class-Id'] = String(user.classId ?? '')
    config.headers['Authorization'] = user.accessToken ? `Bearer ${user.accessToken}` : ''
  }
  return config
})

http.interceptors.response.use(
  (r) => r.data,
  (err) => {
    const msg = err.response?.data?.detail || err.message || '请求失败'
    ElMessage.error(msg)
    return Promise.reject(err)
  }
)

export default http
