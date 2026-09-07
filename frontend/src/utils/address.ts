/**
 * 链上地址口径工具（前端唯一判定源，与后端 app/wallet_id.py 同规则）。
 *
 * 为什么单列一个工具文件：钱包选择器（MainLayout）、角色卡片（EcoPractice）、
 * 登录态（stores/auth）与钱包登记处（stores/wallets）都要判断「这是不是一个真实
 * 链上地址」，写在任何一个 store 里都会造成 store 互相 import（循环依赖）。
 */

/** 真实链上地址：0x + 40 位十六进制（带冒号 / 连字符的内部别名一律不合法） */
const CHAIN_ADDR_RE = /^0x[0-9a-f]{40}$/

export const isChainAddress = (v: any): boolean => CHAIN_ADDR_RE.test(String(v || '').trim())

/** 地址短显（0x44bf…6dda）；非地址原样返回，便于一眼看出脏口径 */
export const shortAddr = (v: any, head = 6, tail = 4): string => {
  const s = String(v || '').trim()
  if (!isChainAddress(s)) return s
  return `${s.slice(0, head + 2)}…${s.slice(-tail)}`
}

/** 小写规范化（地址比较 / 映射键统一用它；不做解析，解析一律走后端） */
export const normAddr = (v: any): string => String(v || '').trim().toLowerCase()

/** 展示口径：联盟钱包显示「名称（短地址）」，其余只显示短地址 */
export const addrLabel = (v: any, alias = ''): string => {
  const s = String(v || '').trim()
  if (!s) return ''
  const a = alias && alias !== s ? `（${alias}）` : ''
  return isChainAddress(s) ? `${shortAddr(s)}${a}` : s
}
