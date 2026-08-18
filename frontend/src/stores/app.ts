import { defineStore } from 'pinia'
import { ref } from 'vue'
import { chainApi, chainApiExtra } from '@/api'
import { safeGet, safeSet } from '@/utils/storage'

export const useAppStore = defineStore('app', () => {
  const chainMode = ref<'fisco' | 'evm' | 'mock'>(safeGet<'fisco' | 'evm' | 'mock'>('chain_mode_override', 'evm'))
  const chainHeight = ref(0)
  const currentWallet = ref(localStorage.getItem('wallet') || '0xlearner')
  const shortcutsOpen = ref<{ open?: () => void; close?: () => void } | null>(null)

  function setWallet(w: string) {
    currentWallet.value = w
    localStorage.setItem('wallet', w)
  }

  async function refreshStatus() {
    try {
      const r: any = await chainApi.status()
      // 优先用户覆盖（切模式后刷新也不会被后端覆盖回默认值）
      const override = safeGet<'fisco' | 'evm' | 'mock' | null>('chain_mode_override', null)
      chainMode.value = override || (r.mode as any) || 'evm'
      chainHeight.value = r.height || 0
    } catch (e) {
      /* silent */
    }
  }

  /** 切换链模式（dev / 教师用；浏览器端本地提示，后端模式需重启） */
  async function setChainMode(mode: 'fisco' | 'evm' | 'mock') {
    safeSet('chain_mode_override', mode)
    chainMode.value = mode
    try {
      // 尝试通知后端（后端若未重启则保持原模式）
      await chainApiExtra.setMode(mode)
    } catch {
      /* 后端版本不一致时忽略 */
    }
    await refreshStatus()
  }

  /** 彩带粒子：canvas-confetti，失败静默（依赖未安装时不报错） */
  function confetti(opts?: any) {
    try {
      // @ts-ignore
      import('canvas-confetti').then((m: any) => {
        const fn = (m.default || m) as any
        fn({
          particleCount: 90,
          spread: 70,
          startVelocity: 45,
          origin: { y: 0.6 },
          colors: ['#00e6c3', '#4d8dff', '#f5379b', '#ffcf4d', '#2dd4bf'],
          ticks: 180,
          ...(opts || {}),
        })
      })
    } catch { /* noop */ }
  }

  return {
    chainMode, chainHeight, currentWallet, shortcutsOpen,
    setWallet, refreshStatus, setChainMode, confetti,
  }
})
