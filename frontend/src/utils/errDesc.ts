/**
 * 错误摘要助手（P1-27：上报给后端的错误详情不得携带凭据）。
 *
 * 背景：实战页原先用 `JSON.stringify(e ?? {})` 把整个 axios error 塞进
 * `/api/eco/errors/record` 的 detail 字段，而 axios 的 `error.config.headers`
 * 里就有 `Authorization: Bearer <JWT>`（还有自报身份的 X-* 头）。这些内容会
 * 原样落库 eco_operation_logs，再被日志查询接口回显 —— 等于把自己的登录凭据
 * 存进了别人的可读表里。
 *
 * 因此上报一律走本函数：只挑「定位问题真正需要的字段」，绝不透传 headers。
 * 后端另有 security.redact_secrets 做入库/回显双道兜底，但前端不该依赖它。
 */

/** 从任意异常对象提取可安全上报的摘要（JSON 字符串，无凭据、长度可控）。 */
export function safeErrDetail(err: unknown): string {
  const e = err as any
  const out: Record<string, unknown> = {}
  const status = e?.response?.status
  if (status !== undefined) out.status = status
  const code = e?.response?.data?.code ?? e?.code
  if (code !== undefined && code !== null) out.code = String(code).slice(0, 60)
  // detail 是后端 HTTPException 的业务文案，本身不含凭据，是排障最有用的一句
  const detail = e?.response?.data?.detail ?? e?.message
  if (detail) out.detail = String(detail).slice(0, 300)
  const method = e?.config?.method
  if (method) out.method = String(method).slice(0, 8)
  const url = e?.config?.url
  if (url) out.url = String(url).slice(0, 160)
  const txHash = e?.response?.data?.tx_hash ?? e?.txHash
  if (txHash) out.tx_hash = String(txHash).slice(0, 80)
  return JSON.stringify(out)
}

/** 面向用户的一句话错误文案（后端 detail 优先，退化到 Error.message）。 */
export function safeErrMsg(err: unknown, fallback = '操作失败'): string {
  const e = err as any
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (detail && typeof detail === 'object') return JSON.stringify(detail).slice(0, 200)
  if (e?.message) return String(e.message)
  return fallback
}
