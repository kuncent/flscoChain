<template>
  <!--
    FISCO-BCOS 4节点 P2P 网络动态背景 SVG（V2 稳定版）
    - 节点 0~3 成菱形排布，彼此 P2P 连线
    - 纯 SVG + CSS / SMIL 动画，零依赖
    - 关键改进：
      1) 所有 <pattern>/<gradient> 都放在 <defs>
      2) viewBox 使用更紧凑的 0..600 x 0..300，节点更居中不易被裁切
      3) preserveAspectRatio="xMidYMid meet" 保证节点永远可见
      4) 最外层加了 role="img" aria-label 便于调试
  -->
  <div class="dq-chain-net-bg" aria-hidden="true">
    <svg viewBox="0 0 600 300" preserveAspectRatio="xMidYMid meet" class="bg-svg">
      <defs>
        <!-- 背景细网格 pattern（必须放 defs） -->
        <pattern id="cn2-grid" width="32" height="32" patternUnits="userSpaceOnUse">
          <path d="M 32 0 L 0 0 0 32" fill="none" stroke="#1a2440" stroke-width="0.5"/>
        </pattern>
        <!-- 脉冲渐变 -->
        <radialGradient id="cn2-pulse" cx="50%" cy="50%" r="50%">
          <stop offset="0%"  stop-color="#00e6c3" stop-opacity="0.9"/>
          <stop offset="55%" stop-color="#00e6c3" stop-opacity="0.18"/>
          <stop offset="100%" stop-color="#00e6c3" stop-opacity="0"/>
        </radialGradient>
        <!-- 连线渐变 -->
        <linearGradient id="cn2-line-on" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%"  stop-color="#00e6c3" stop-opacity="0"/>
          <stop offset="20%" stop-color="#00e6c3" stop-opacity="0.3"/>
          <stop offset="50%" stop-color="#00e6c3" stop-opacity="0.75"/>
          <stop offset="80%" stop-color="#00e6c3" stop-opacity="0.3"/>
          <stop offset="100%" stop-color="#00e6c3" stop-opacity="0"/>
        </linearGradient>
        <linearGradient id="cn2-line-dim" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%"  stop-color="#4d8dff" stop-opacity="0"/>
          <stop offset="50%" stop-color="#4d8dff" stop-opacity="0.22"/>
          <stop offset="100%" stop-color="#4d8dff" stop-opacity="0"/>
        </linearGradient>
        <!-- 节点光晕 -->
        <radialGradient id="cn2-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%"  stop-color="#00e6c3" stop-opacity="0.5"/>
          <stop offset="100%" stop-color="#00e6c3" stop-opacity="0"/>
        </radialGradient>
      </defs>

      <!-- 背景网格 + 径向晕染 -->
      <rect x="0" y="0" width="600" height="300" fill="url(#cn2-grid)" opacity="0.22"/>
      <circle cx="300" cy="150" r="260" fill="url(#cn2-pulse)" opacity="0.35"/>

      <!-- ======== 6 条 P2P 连线（静态版，已移除 stroke 切换动画避免宽度抖动）======== -->
      <line x1="300" y1="70"  x2="135" y2="150" stroke="url(#cn2-line-dim)" stroke-width="1.1"/>
      <line x1="300" y1="70"  x2="465" y2="150" stroke="url(#cn2-line-on)"  stroke-width="1.1"/>
      <line x1="300" y1="70"  x2="300" y2="230" stroke="url(#cn2-line-dim)" stroke-width="1.1"/>
      <line x1="135" y1="150" x2="465" y2="150" stroke="url(#cn2-line-on)"  stroke-width="1.1"/>
      <line x1="135" y1="150" x2="300" y2="230" stroke="url(#cn2-line-dim)" stroke-width="1.1"/>
      <line x1="465" y1="150" x2="300" y2="230" stroke="url(#cn2-line-on)"  stroke-width="1.1"/>

      <!-- ======== 4 个节点（静态版，已移除 r/stroke-width 半径脉动避免 SVG 包围盒变化引发页面宽度抖动）======== -->
      <g v-for="(n, i) in nodes" :key="i" :transform="`translate(${n.x}, ${n.y})`">
        <!-- 外层脉冲环（固定半径，不再动画变化） -->
        <circle r="36" fill="url(#cn2-pulse)" opacity="0.55"/>
        <!-- 光晕 -->
        <circle r="22" fill="url(#cn2-glow)"/>
        <!-- 节点外框（固定 stroke-width，不再变化） -->
        <circle r="15" fill="#0e1424" stroke="#00e6c3" stroke-width="1.6" opacity="0.95"/>
        <text y="5" text-anchor="middle" font-family="JetBrains Mono, Consolas, monospace" font-size="12" font-weight="700" fill="#00e6c3">{{ i }}</text>
        <!-- 角色标签 -->
        <text y="32" text-anchor="middle" font-family="JetBrains Mono, Consolas, monospace" font-size="9" fill="#6b7c9c" opacity="0.95">node{{ i }} · {{ n.role }}</text>
      </g>
    </svg>
  </div>
</template>

<script setup lang="ts">
const nodes = [
  { x: 300, y:  70, role: 'Leader' },
  { x: 135, y: 150, role: 'Sealer' },
  { x: 465, y: 150, role: 'Sealer' },
  { x: 300, y: 230, role: 'Observer' },
]
</script>

<style scoped lang="scss">
.dq-chain-net-bg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  min-height: 220px;
  pointer-events: none;
  /* 背景兜底：当 SVG 没渲染出来时也有深色渐变不会留白 */
  background:
    radial-gradient(ellipse at 50% 50%, rgba(0,230,195,0.08) 0%, transparent 60%),
    linear-gradient(180deg, rgba(77,141,255,0.06) 0%, rgba(0,230,195,0.04) 100%);
  display: block;
  overflow: hidden;

  .bg-svg {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    /* 往右偏 8%，避免和左栏 hero 文字重叠 */
    transform: translateX(6%) scale(1.05);
    transform-origin: center;
    opacity: 0.95;
    @media (prefers-reduced-motion: reduce) {
      opacity: 0.35;
    }
  }
}
</style>
