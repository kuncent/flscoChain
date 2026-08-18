<template>
  <span :class="['dq-countup', klass]" ref="refWrap">{{ display }}</span>
</template>

<script setup lang="ts">
/**
 * 数字滚动动画组件
 * - mounted 后从 0 递增到 target
 * - target 改变时重启动画
 * - 纯 requestAnimationFrame，零依赖
 */
import { computed, onMounted, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  target: number | string
  duration?: number     // 动画时长 ms，默认 900
  decimals?: number     // 小数位
  prefix?: string       // 前缀
  suffix?: string       // 后缀
  separator?: boolean   // 千分位，默认true
  klass?: string        // 附加 class
}>(), {
  duration: 900,
  decimals: 0,
  prefix: '',
  suffix: '',
  separator: true,
  klass: '',
})

const refWrap = ref<HTMLSpanElement>()
const current = ref(0)
let raf = 0

const display = computed(() => {
  let n = current.value.toFixed(props.decimals)
  if (props.separator) {
    const [intP, decP] = n.split('.')
    n = intP.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (decP !== undefined ? '.' + decP : '')
  }
  return props.prefix + n + props.suffix
})

function easeOutCubic(t: number) { return 1 - Math.pow(1 - t, 3) }

function animate(from: number, to: number) {
  cancelAnimationFrame(raf)
  const start = performance.now()
  const delta = to - from
  const dur = Math.min(1800, Math.max(260, props.duration))
  function step(t: number) {
    const p = Math.min(1, (t - start) / dur)
    current.value = from + delta * easeOutCubic(p)
    if (p < 1) raf = requestAnimationFrame(step)
  }
  raf = requestAnimationFrame(step)
}

onMounted(() => {
  const t = Number(props.target) || 0
  animate(0, t)
})

watch(() => props.target, (n, o) => {
  const to = Number(n) || 0
  const from = Number(o) || 0
  animate(from, to)
})
</script>

<style scoped lang="scss">
.dq-countup { font-variant-numeric: tabular-nums; }
</style>
