/**
 * 绿色能量核算（前端预估口径）
 *
 * 与后端 `app/learning/alliance_roles.calc_energy_points` 逐条对齐，任何一侧改公式
 * 都必须同步另一侧，否则会出现「弹窗说 +50、实际到账 90」的口径漂移：
 *   points = 基础分 rule.points + 超门槛加成 (计量值 - rule.min) × rule.bonus_per_unit，
 *   超过 rule.bonus_cap 时按封顶截断；
 *   bonus_per_unit 缺省 / 0，或「无需餐具」这类开关型规则 → 固定基础分，不乘量、不截断。
 *
 * 仅用于业务凭证弹窗按用户已填数据实时预估，**实际发行量以后端返回的 points 为准**。
 */

export interface EnergyRule {
  action?: string
  points?: number | string
  proof_field?: string
  min?: number | string
  unit?: string
  bonus_per_unit?: number | string
  bonus_cap?: number | string
  [k: string]: any
}

export interface EnergyEstimate {
  /** 预计发行量（含封顶截断） */
  points: number
  base: number
  per: number
  cap: number
  min: number
  unit: string
  field: string
  /** 用户当前填写的计量值 */
  val: number
  /** 超出门槛的部分 */
  excess: number
  /** 加成部分（截断后） */
  bonus: number
  /** 是否触发单次封顶截断 */
  capped: boolean
  /** 固定分规则（不按量加成） */
  fixed: boolean
  /** 未达发放门槛 / 未勾选必需开关：提交会被后端驳回 */
  belowMin: boolean
  /** 计量字段还没有有效输入（不做门槛判定，交给必填校验） */
  pending: boolean
}

const num = (v: any): number => {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 展示用数字：整数不带小数点，小数最多 2 位（里程 3.5km 不要显示 3.500） */
const fmt = (v: number): string =>
  Number.isInteger(v) ? String(v) : String(Number(v.toFixed(2)))

export function estimateEnergy(
  rule?: EnergyRule | null,
  proof?: Record<string, any> | null,
): EnergyEstimate {
  const r = (rule || {}) as EnergyRule
  const base = Math.trunc(num(r.points))
  const per = Math.trunc(num(r.bonus_per_unit))
  const cap = Math.trunc(num(r.bonus_cap)) || base
  const min = num(r.min)
  const unit = String(r.unit || '')
  const field = String(r.proof_field || '')
  const raw = field && proof ? (proof as any)[field] : undefined
  const val = typeof raw === 'boolean' ? (raw ? 1 : 0) : num(raw)
  const est: EnergyEstimate = {
    points: base, base, per, cap, min, unit, field, val,
    excess: 0, bonus: 0, capped: false,
    fixed: per <= 0 || field === 'no_cutlery',
    belowMin: false, pending: false,
  }
  // 开关型（外卖「无需餐具」）：未勾选即不满足发放条件，分值固定
  if (field === 'no_cutlery') {
    if (raw === undefined || raw === null || raw === '') est.pending = true
    else est.belowMin = raw !== true
    return est
  }
  if (!field) return est
  // 计量值未填写：不做门槛判定，预估按基础分展示，必填校验会拦住提交
  if (raw === undefined || raw === null || raw === '') {
    est.pending = true
    return est
  }
  if (val < min) {
    est.belowMin = true
    return est
  }
  if (est.fixed) return est
  const excess = Math.max(0, val - min)
  let pts = base + Math.trunc(excess * per)
  const capped = pts > cap
  if (capped) pts = cap
  est.excess = Number(excess.toFixed(3))
  est.bonus = Math.max(0, pts - base)
  est.capped = capped
  est.points = Math.max(base, pts)
  return est
}

/** 核算过程文案，如「基础 50 + 超门槛 20km × 2 = 90（单次封顶 150）」 */
export function energyCalcText(e: EnergyEstimate): string {
  if (e.pending) return `达门槛后按规则核算（基础 ${e.base} 点${e.per > 0 ? ` + 超量加成，单次封顶 ${e.cap} 点` : ''}）`
  if (e.field === 'no_cutlery') {
    return e.belowMin ? `需勾选「已选择无需餐具」，勾选后固定 +${e.points} 点` : `无需餐具 · 固定 +${e.points} 点`
  }
  if (!e.field) return `固定 +${e.points} 点`
  if (e.belowMin) return `未达发放门槛：${fmt(e.val)}${e.unit} < ${fmt(e.min)}${e.unit}，提交会被驳回`
  if (e.fixed) return `达门槛（≥ ${fmt(e.min)}${e.unit}）固定 +${e.points} 点`
  const calc = e.excess > 0
    ? `基础 ${e.base} + 超门槛 ${fmt(e.excess)}${e.unit} × ${e.per}`
    : `基础 ${e.base}（刚好达门槛，无超量加成）`
  return `${calc} = ${e.points} 点 · 单次封顶 ${e.cap}${e.capped ? '（已按封顶截断）' : ''}`
}

/** 一句话规则提示（列表 / 卡片用，不含用户填写值） */
export function energyRuleHint(rule?: EnergyRule | null): string {
  if (!rule) return ''
  const base = Math.trunc(num(rule.points))
  const per = Math.trunc(num(rule.bonus_per_unit))
  const cap = Math.trunc(num(rule.bonus_cap)) || base
  return per > 0
    ? `${base} 起 · 每超 1 ${rule.unit || ''} +${per}（单次封顶 ${cap}）`
    : `固定 ${base} 点`
}
