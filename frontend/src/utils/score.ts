/**
 * 分数等级六档（前端展示口径）
 *
 * 与后端 `app/score_levels.py` 逐字段对齐（阈值 / key / 文案 / 色值），任何一侧改档位
 * 都必须同步另一侧。此前报告页写 90/75/60/40、成绩页写 90/80/60，同一个 65 分在两个
 * 页面显示成不同等级，学生按颜色理解成绩必然误判。
 *
 * 口径：卓越 ≥90 / 优秀 80~89 / 良好 70~79 / 合格 60~69 / 待完善 40~59 / 未完成 <40
 * 报告总分、实训成绩、教师评分、综合成绩共用这一套（都是 0~100 的同尺度分数）。
 *
 * 实训报告页应优先直接渲染后端下发的 `level` / `level_color`（同源结果），
 * 本工具用于成绩册等只有裸分数没有等级字段的场景，以及后端未升级时的兜底。
 */

export type ScoreLevelKey =
  | 'supreme'
  | 'excellent'
  | 'good'
  | 'pass'
  | 'improving'
  | 'unfinished'

export interface ScoreLevel {
  /** 该档位的分数下限（含） */
  min: number
  key: ScoreLevelKey
  /** 纯文字名（表格 / 无障碍标签用） */
  name: string
  /** 带图标的展示文案，与后端 level 字段完全一致 */
  badge: string
  /** 色值取自产品设计系统 global.scss 的颜色令牌 */
  color: string
}

/** 从高到低排列，levelOf 顺序命中第一个 min 达标的档位 */
export const SCORE_LEVELS: readonly ScoreLevel[] = [
  { min: 90, key: 'supreme', name: '卓越', badge: '卓越 🏆', color: '#00e6c3' },
  { min: 80, key: 'excellent', name: '优秀', badge: '优秀 🥇', color: '#2dd4bf' },
  { min: 70, key: 'good', name: '良好', badge: '良好 🥈', color: '#4d8dff' },
  { min: 60, key: 'pass', name: '合格', badge: '合格 ✅', color: '#ffcf4d' },
  { min: 40, key: 'improving', name: '待完善', badge: '待完善 🚧', color: '#ff9500' },
  { min: 0, key: 'unfinished', name: '未完成', badge: '未完成 ❌', color: '#ff5470' },
]

/** 非数字 / 空值一律按 0 处理（显示「未完成」而不是崩溃或显示 undefined） */
export function levelOf(score: number | string | null | undefined): ScoreLevel {
  const n = Number(score)
  const v = Number.isFinite(n) ? n : 0
  return SCORE_LEVELS.find((l) => v >= l.min) ?? SCORE_LEVELS[SCORE_LEVELS.length - 1]
}

export const levelBadge = (score: number | string | null | undefined): string => levelOf(score).badge

export const levelName = (score: number | string | null | undefined): string => levelOf(score).name

export const levelColor = (score: number | string | null | undefined): string => levelOf(score).color

/** CSS 类名（lv-supreme / lv-excellent / …），样式表按同一套 key 命名 */
export const levelClass = (score: number | string | null | undefined): string => `lv-${levelOf(score).key}`
