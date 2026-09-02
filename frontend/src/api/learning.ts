import http from './http'

/**
 * 学习路径单一事实源（GET /api/learning/path，后端 app/learning/paths.py）。
 *
 * 返回 P1-P4 十步路径清单（文案与原 Dashboard.vue pathSteps 硬编码逐字一致）
 * + 每阶段服务端核验状态：
 *   stages: [{ id, level, to, icon, title, desc, keywords, tag, tagClass,
 *              eta, goal, kpoints, accept, tutorialSteps, achievements,
 *              progress: {
 *                tutorial_progress: { done, total } | null,   // 关联教程步骤 done 计数
 *                achievements: { achieved: string[], total } | null, // 关联成就已获得状态
 *                checks: [{ text, kind, manual, verified, current?, target? }],
 *                auto_total                                    // 可自动核验项数
 *              },
 *              verified: boolean }]                             // 可核验项全部通过
 *
 * 表不存在 / 空数据时后端兜底空态（计数 0、verified=false），不抛错；
 * 前端请求失败时回退内置 fallback 文案（见 Dashboard.vue FALLBACK_PATH_STEPS）。
 */
export function getLearningPath(): Promise<any> {
  return http.get('/learning/path')
}

export const learningApi = {
  getLearningPath,
}

export default learningApi
