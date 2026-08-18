<template>
  <!-- 快捷键帮助面板：按 ? 呼出；Esc 关闭 -->
  <el-dialog v-model="show" title="⌨️ 全局快捷键" width="520px" top="18vh" class="dq-shortcuts" destroy-on-close>
    <div class="cols">
      <div class="col">
        <div class="col-title">页面导航</div>
        <div class="row" v-for="r in navRows" :key="r.key">
          <span class="k"><kbd>{{ r.key }}</kbd></span>
          <span class="v">{{ r.label }}</span>
        </div>
      </div>
      <div class="col">
        <div class="col-title">通用操作</div>
        <div class="row" v-for="r in commonRows" :key="r.key">
          <span class="k"><kbd>{{ r.key }}</kbd></span>
          <span class="v">{{ r.label }}</span>
        </div>
      </div>
    </div>
    <div class="foot dq-tip" style="margin-top:14px">
      <span class="dt-label">提示</span>本面板可随时按 <kbd style="padding:0 4px">?</kbd> 打开。链模式切换见顶栏链状态卡的下拉。
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

const show = ref(false)
const router = useRouter()
const navRows = [
  { key: '1', label: '总览 / 学习路径', to: '/dashboard' },
  { key: '2', label: '云桌面 · 搭链教程', to: '/cloud' },
  { key: '3', label: '合约 IDE',          to: '/ide' },
  { key: '4', label: '合约管理',          to: '/contracts' },
  { key: '5', label: '接口调试',          to: '/interfaces' },
  { key: '6', label: '区块链浏览器',      to: '/explorer' },
  { key: '7', label: 'ERC20 钱包实训',    to: '/wallet' },
  { key: '8', label: 'NFT 交易市场',      to: '/nft' },
  { key: '9', label: '生成实训报告',      to: '/report' },
]
const commonRows = [
  { key: '?',    label: '打开/关闭 快捷键面板' },
  { key: 'Esc',  label: '关闭对话框 / 返回' },
  { key: 'R',    label: '刷新当前页数据' },
  { key: '/',    label: '聚焦全局搜索（如浏览器）' },
]

function onKey(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement)?.tagName
  const inp = tag === 'INPUT' || tag === 'TEXTAREA' || (e.target as HTMLElement)?.isContentEditable
  if (e.key === '?' && !inp) { e.preventDefault(); show.value = !show.value; return }
  if (e.key === 'Escape') { show.value = false; return }
  if (inp) return
  if (/^[1-9]$/.test(e.key)) {
    const t = navRows[Number(e.key) - 1]
    if (t) router.push(t.to)
  }
  if (e.key.toLowerCase() === 'r') window.location.reload()
}

onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

defineExpose({ open: () => (show.value = true), close: () => (show.value = false) })
</script>

<style scoped lang="scss">
.cols { display:grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.col-title { font-size: 12px; font-weight: 700; color: var(--dq-text-dim); text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 10px; }
.row { display:flex; align-items:center; justify-content:space-between; padding: 7px 0; border-bottom: 1px dashed var(--dq-border);
  &:last-child { border-bottom: none; }
  .k { display:inline-flex; align-items:center; justify-content:center; min-width: 36px;
    kbd {
      padding: 2px 8px; border-radius: 4px;
      background: var(--dq-bg-2); border: 1px solid var(--dq-border-2);
      color: var(--dq-primary); font-family: var(--dq-mono); font-size: 12px;
      box-shadow: inset 0 -2px 0 rgba(0,0,0,0.25);
    }
  }
  .v { font-size: 13px; color: var(--dq-text); }
}
.foot { margin-top: 10px; }
.foot kbd { padding: 0 6px; border-radius: 4px; background: var(--dq-bg-2); border: 1px solid var(--dq-border-2); color: var(--dq-primary); font-family: var(--dq-mono); font-size: 11px; }
@media (max-width: 600px) { .cols { grid-template-columns: 1fr; } }
</style>
