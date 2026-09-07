import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { ecoApi } from '@/api'
import { isChainAddress, normAddr, shortAddr } from '@/utils/address'
import { useAuthStore } from './auth'

/**
 * 钱包口径登记处（前端唯一事实源）。
 *
 * 修三件事：
 *  1. 资产钱包一律用**真实链上地址**（0x + 40 hex）：下拉选项、角色卡片、身份标签
 *     全部取后端 `/api/eco/roles` 返回的 `address`，不再前端硬编码 `0xmetro` 这类
 *     密钥库别名（别名只作展示括号注记，不参与匹配 / 提交）；
 *  2. 钱包 ↔ 角色 ↔ 身份双向联动的映射源：`roleKeyByAddress` 由后端角色表派生，
 *     顶部切钱包与页面选角色共用同一张表，避免前端各写一套名单导致口径漂移；
 *  3. 旧会话残留的内部别名（`stu:xxx` / `0xlearner` / user_id）不再被当成钱包：
 *     `normalize()` 统一收敛回本人地址。
 */
export { isChainAddress, shortAddr }

export type AllianceWallet = {
  roleKey: string
  address: string      // 真实链上地址（资产标识 / 提交后端的唯一口径）
  alias: string        // 密钥库友好别名（0xmetro），仅展示
  name: string
  icon: string
  color: string
  desc: string
  profile: string
  assets: string[]     // 可发行的绿色资产形态（certificate / badge / voucher）
  canIssueEnergy: boolean
  energyQuota: number
  /** 该节点累计已发行能量（后端 SQL 聚合）：授信余量 = energyQuota - energyIssued */
  energyIssued: number
}

export const useWalletStore = defineStore('wallets', () => {
  const auth = useAuthStore()
  /** 后端 /api/eco/roles 原始返回（含 address / issues_assets / energy_quota） */
  const roles = ref<any[]>([])
  const loaded = ref(false)
  const loading = ref(false)

  /** 本人钱包 = 登录时下发的真实链上地址；旧会话缓存里还是 stu:xxx / user_id
   *  时返回空串（宁可选项缺失引导重新登录，也不把内部别名当资产地址提交） */
  const myAddress = computed(() => {
    const w = normAddr(auth.user?.wallet)
    return isChainAddress(w) ? w : ''
  })
  /** 本人钱包尚未落地为地址时（旧会话缓存）应显示的原值：用于提示重新登录 */
  const myRaw = computed(() => String(auth.user?.wallet || '').trim())

  const alliance = computed<AllianceWallet[]>(() =>
    (roles.value || [])
      .filter((r: any) => isChainAddress(r.address))
      .map((r: any) => ({
        roleKey: String(r.key || ''),
        address: String(r.address).toLowerCase(),
        alias: String(r.wallet_alias || ''),
        name: String(r.name || ''),
        icon: String(r.icon || ''),
        color: String(r.color || ''),
        desc: String(r.desc || ''),
        profile: String(r.key === 'admin' ? 'admin' : 'node'),
        assets: Array.isArray(r.issues_assets) ? r.issues_assets.map(String) : [],
        canIssueEnergy: !!r.energy_rule,
        energyQuota: Number(r.energy_quota || 0),
        energyIssued: Number(r.energy_issued || 0),
      })),
  )

  /** 真实地址 → 联盟角色 key（顶部切钱包自动联动角色的唯一映射源） */
  const roleKeyByAddress = computed<Record<string, string>>(() => {
    const m: Record<string, string> = {}
    for (const a of alliance.value) if (a.roleKey) m[a.address] = a.roleKey
    return m
  })
  /** 角色 key → 真实地址 */
  const addressByRole = computed<Record<string, string>>(() => {
    const m: Record<string, string> = {}
    for (const a of alliance.value) if (a.roleKey) m[a.roleKey] = a.address
    return m
  })
  /** 别名 → 真实地址（历史链接 / 手工输入的旧口径兜底） */
  const addressByAlias = computed<Record<string, string>>(() => {
    const m: Record<string, string> = {}
    for (const a of alliance.value) if (a.alias) m[a.alias.toLowerCase()] = a.address
    return m
  })

  const allianceOf = (addr: string) =>
    alliance.value.find((a) => a.address === normAddr(addr)) || null

  /** 地址 → 角色 key / 角色 key → 地址：组件侧统一走函数。 */
  const roleKeyOf = (addr: string): string => roleKeyByAddress.value[normAddr(addr)] || ''
  const addressOf = (roleKey: string): string => addressByRole.value[String(roleKey || '')] || ''

  /**
   * 任意口径 → 可选钱包的真实地址。
   * 用于严格联动：命中联盟地址 / 联盟别名 → 该机构地址；等于本人 → 本人地址；
   * 其余（stu:xxx、user_id、0xlearner 等内部别名）→ 空串，由调用方回落本人钱包。
   */
  function normalize(value: string): string {
    const v = normAddr(value)
    if (!v) return ''
    if (isChainAddress(v)) return v
    const byAlias = addressByAlias.value[v]
    if (byAlias) return byAlias
    if (myAddress.value && isChainAddress(myAddress.value) && v === myAddress.value) return myAddress.value
    return ''
  }

  /** 联盟角色钱包（地址不在选项里时用于「未命名钱包」兜底展示） */
  async function ensureRoles(force = false): Promise<any[]> {
    if (loaded.value && !force) return roles.value
    if (loading.value) return roles.value
    loading.value = true
    try {
      const r: any = await ecoApi.roles()
      const list = r?.items || r || []
      roles.value = Array.isArray(list) ? list : []
      loaded.value = roles.value.length > 0
    } catch {
      /* 后端未就绪：保留上一次结果，选择器退回「我的钱包」单项 */
    } finally {
      loading.value = false
    }
    return roles.value
  }

  function setRoles(list: any[]) {
    roles.value = Array.isArray(list) ? list : []
    loaded.value = roles.value.length > 0
  }

  return {
    roles, loaded, loading,
    myAddress, myRaw, alliance, roleKeyByAddress, addressByRole, addressByAlias,
    allianceOf, roleKeyOf, addressOf, normalize, ensureRoles, setRoles,
  }
})
