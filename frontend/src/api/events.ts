/**
 * 事件总线前端封装（任务 #21）：/api/notify/stream 的 EventSource 客户端。
 *
 * 设计要点：
 * - EventSource 不支持自定义请求头，JWT 以 ?token= query 传递（后端 _authenticate
 *   同时接受 Authorization: Bearer 与 ?token=，均走 security.decode_token 同一验签路径）
 * - 自动重连 + 指数退避：1s → 2s → 4s → … 上限 30s，连接成功后退避归零；
 *   连续失败达上限（8 次，典型如 token 过期后服务端持续 401）即停止重连，
 *   避免无限重试；登录流程可调用 reconnect() 以新凭据重启连接
 * - 按事件类型注册回调：on(type, handler) 返回取消函数
 * - 单例幂等：未登录（无 token）不建连接；登出时 disconnect() 即可
 */
import { AUTH_TOKEN_KEY } from './http'

/** 与后端 app/events_bus.py BusEvent 常量一一对应 */
export const EVENT_TYPES = {
  TX_CONFIRMED: 'tx_confirmed',
  DEPLOYED: 'deployed',
  COMPILED: 'compiled',
  ENERGY_ISSUED: 'energy_issued',
  TUTORIAL_STEP_DONE: 'tutorial_step_done',
  SANDBOX_READY: 'sandbox_ready',
  SANDBOX_EXIT: 'sandbox_exit',
} as const

export type BusEventType = (typeof EVENT_TYPES)[keyof typeof EVENT_TYPES]

/** SSE 推送帧 payload 结构（notify.py /stream 发送的 data 字段） */
export interface NotifyEventPayload {
  id: string
  type: string
  payload: Record<string, any>
  ts: number
}

type Handler = (data: NotifyEventPayload) => void

const MIN_DELAY_MS = 1000
const MAX_DELAY_MS = 30000
/** 连续重连失败上限：达到后停止重连（防止 token 过期后无限重试），需经 reconnect() 重启 */
const MAX_RETRY_FAILURES = 8

class EventStream {
  private es: EventSource | null = null
  private handlers = new Map<string, Set<Handler>>()
  /** 每个事件类型缓存唯一的 EventListener 引用（保证 off 时 removeEventListener 命中） */
  private listeners = new Map<string, EventListener>()
  private retryDelay = MIN_DELAY_MS
  private retryTimer: ReturnType<typeof setTimeout> | null = null
  private closed = false
  /** 连续重连失败计数（连接成功后清零） */
  private failures = 0
  /** 达到失败上限后停止自动重连（区别于用户主动 disconnect 的 closed） */
  private halted = false

  /** 幂等建连：已连接 / 未登录时不做任何事 */
  connect(): void {
    if (this.closed) this.closed = false
    if (this.es || this.retryTimer) return
    const token = this.getToken()
    if (!token) return // 未登录不建连接
    if (typeof EventSource === 'undefined') return // 环境不支持（如旧浏览器 / SSR）
    const url = `/api/notify/stream?token=${encodeURIComponent(token)}`
    this.es = new EventSource(url)
    this.es.onopen = () => {
      this.retryDelay = MIN_DELAY_MS // 连接成功：退避归零 + 失败计数清零
      this.failures = 0
    }
    // 为每种已注册事件类型挂监听（EventSource 命名事件需显式 addEventListener）
    this.bindAll()
    this.es.onerror = () => {
      this.teardown()
      if (this.closed) return
      this.scheduleReconnect()
    }
  }

  /** 注册事件回调，返回取消注册函数 */
  on(type: string, handler: Handler): () => void {
    let set = this.handlers.get(type)
    if (!set) {
      set = new Set()
      this.handlers.set(type, set)
      // 若已建连，动态补挂监听（复用缓存的唯一 listener 引用）
      this.es?.addEventListener(type, this.listenerOf(type))
    }
    set.add(handler)
    return () => {
      const s = this.handlers.get(type)
      if (!s) return
      s.delete(handler)
      if (s.size === 0) {
        this.handlers.delete(type)
        const ln = this.listeners.get(type)
        if (ln) this.es?.removeEventListener(type, ln)
      }
    }
  }

  /** 断开连接（登出 / 组件卸载时调用；之后仍可再次 connect()） */
  disconnect(): void {
    this.closed = true
    this.halted = false
    this.failures = 0
    if (this.retryTimer) {
      clearTimeout(this.retryTimer)
      this.retryTimer = null
    }
    this.teardown()
  }

  /**
   * 强制重启连接（登录成功 / token 刷新后调用）：
   * 清零失败计数、解除失败上限的停机状态、取消挂起的退避定时器后立即重连。
   */
  reconnect(): void {
    this.failures = 0
    this.halted = false
    if (this.retryTimer) {
      clearTimeout(this.retryTimer)
      this.retryTimer = null
    }
    this.teardown()
    this.closed = false
    this.connect()
  }

  // ---------- 内部 ----------
  private getToken(): string {
    try {
      return localStorage.getItem(AUTH_TOKEN_KEY) || ''
    } catch {
      return ''
    }
  }

  private makeListener(type: string): EventListener {
    return (ev: Event) => {
      const set = this.handlers.get(type)
      if (!set || !set.size) return
      let data: NotifyEventPayload
      try {
        data = JSON.parse((ev as MessageEvent).data || '{}') as NotifyEventPayload
      } catch {
        return
      }
      set.forEach((h) => {
        try {
          h(data)
        } catch {
          /* 单个回调异常不影响其他订阅者 */
        }
      })
    }
  }

  /** 每类型缓存唯一 listener（同一引用才能 add / remove 配对） */
  private listenerOf(type: string): EventListener {
    let ln = this.listeners.get(type)
    if (!ln) {
      ln = this.makeListener(type)
      this.listeners.set(type, ln)
    }
    return ln
  }

  private bindAll(): void {
    if (!this.es) return
    for (const type of this.handlers.keys()) {
      this.es.addEventListener(type, this.listenerOf(type))
    }
  }

  private teardown(): void {
    if (this.es) {
      this.es.close()
      this.es = null
    }
  }

  /** 指数退避重连：1s → 2s → 4s … 上限 30s；连续失败达上限后停止重连（停机） */
  private scheduleReconnect(): void {
    if (this.retryTimer || this.closed || this.halted) return
    this.failures += 1
    if (this.failures > MAX_RETRY_FAILURES) {
      // 连续失败超限（如 token 过期被服务端持续拒绝）：停止重连，
      // 等待登录流程调用 reconnect() 以新凭据重启，避免无限重试空转。
      this.halted = true
      this.retryDelay = MIN_DELAY_MS
      return
    }
    const delay = this.retryDelay
    this.retryDelay = Math.min(this.retryDelay * 2, MAX_DELAY_MS)
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null
      if (!this.closed && !this.halted) this.connect()
    }, delay)
  }
}

/** 全局单例（应用内共享一条 SSE 连接） */
export const eventStream = new EventStream()

/** 便捷订阅：返回取消函数。首次订阅时自动建连。 */
export function onBusEvent(type: string, handler: Handler): () => void {
  const off = eventStream.on(type, handler)
  eventStream.connect()
  return off
}
