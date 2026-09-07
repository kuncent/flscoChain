/**
 * 统一时间格式化：全站列表 / 时间线的时间列都必须走这里，禁止各页面自写 slice。
 *
 * 后端口径（app/db.py: now() → datetime.utcnow().isoformat()）：
 *   - 带 'T' 的裸 ISO 串（如 2026-09-06T22:45:07.277620）= **UTC 且无时区后缀**，
 *     直接交给 new Date() 会被按本地时间解析，导致展示比真实钟表慢 8 小时；
 *   - 带空格且由 strftime('%Y-%m-%d %H:%M:%S') 产出的串（如报表 generated_at）= 本地时间，
 *     只做格式规整、不做时区平移。
 * 兼容 epoch 秒 / 毫秒数字（链上区块 timestamp）与显式带 Z / ±HH:MM 的 ISO 串。
 */

const ISO_RE = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?$/

const pad = (n: number) => String(n).padStart(2, '0')

/** 把任意后端时间值解析成 Date；无法识别时返回 null */
export function toDate(value?: string | number | Date | null): Date | null {
  if (value === null || value === undefined || value === '') return null
  if (value instanceof Date) return isNaN(value.getTime()) ? null : value

  const raw = String(value).trim()
  // 纯数字：epoch 秒（10 位）或毫秒（13 位）
  if (/^\d{10,13}$/.test(raw)) {
    const n = Number(raw)
    const d = new Date(n < 1e11 ? n * 1000 : n)
    return isNaN(d.getTime()) ? null : d
  }

  const m = ISO_RE.exec(raw)
  if (m) {
    const [, y, mo, da, hh, mm, ss = '00', tz] = m
    // 无时区后缀时按 'T' / 空格区分来源口径：'T' 来自 utcnow()（UTC），空格来自本地时间
    const naiveIsUtc = !tz && raw.includes('T')
    const iso = `${y}-${mo}-${da}T${hh}:${mm}:${ss}${tz || (naiveIsUtc ? 'Z' : '')}`
    const d = new Date(iso)
    return isNaN(d.getTime()) ? null : d
  }

  const d = new Date(raw)
  return isNaN(d.getTime()) ? null : d
}

/**
 * 列表时间列：YYYY-MM-DD HH:mm:ss（按浏览器本地时区展示）
 * 无法解析的值原样回显，绝不把数据吞成 NaN。
 */
export function fmtDateTime(value?: string | number | Date | null, fallback = '-'): string {
  if (value === null || value === undefined || value === '') return fallback
  const d = toDate(value)
  if (!d) return String(value)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} `
    + `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

/** 精简展示（列表空间紧张处）：MM-DD HH:mm */
export function fmtDateTimeBrief(value?: string | number | Date | null, fallback = '-'): string {
  if (value === null || value === undefined || value === '') return fallback
  const d = toDate(value)
  if (!d) return String(value)
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** 本地当前时刻（前端乐观写入时间线时用，与后端展示口径一致） */
export function nowText(): string {
  return fmtDateTime(new Date())
}
