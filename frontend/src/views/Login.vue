<template>
  <div class="login-page">
    <!-- ============ 区块节点星球（左侧偏移 + 半透明） ============ -->
    <canvas ref="canvasRef" class="planet-canvas"></canvas>
    <div class="planet-aura"></div>

    <!-- ============ 环境装饰层 ============ -->
    <div class="bg-decor">
      <svg class="bg-hex" viewBox="0 0 1000 1000" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
        <defs>
          <pattern id="hexmesh" width="60" height="52" patternUnits="userSpaceOnUse">
            <polygon points="30,2 56,17 56,47 30,62 4,47 4,17" fill="none" stroke="rgba(0,230,195,0.07)" stroke-width="1" />
          </pattern>
          <radialGradient id="hex-fade" cx="50%" cy="50%" r="60%">
            <stop offset="0%" stop-color="black" stop-opacity="0.9" />
            <stop offset="100%" stop-color="black" stop-opacity="0" />
          </radialGradient>
          <mask id="hex-mask"><rect width="100%" height="100%" fill="url(#hex-fade)" /></mask>
        </defs>
        <rect width="100%" height="100%" fill="url(#hexmesh)" mask="url(#hex-mask)" />
      </svg>

      <div class="bg-particles">
        <span v-for="n in 40" :key="n" class="bg-particle" :style="particleStyle(n)"></span>
      </div>

      <!-- 星云云团（缓慢漂移） -->
      <div class="bg-nebula">
        <span class="neb neb-1"></span>
        <span class="neb neb-2"></span>
        <span class="neb neb-3"></span>
        <span class="neb neb-4"></span>
      </div>

      <!-- 装饰性星点（闪烁，加量） -->
      <div class="bg-stars">
        <span v-for="n in 80" :key="'s'+n" class="bg-star" :class="{ 'bg-star-lg': n % 13 === 0 }" :style="starStyle(n)"></span>
      </div>
    </div>

    <!-- ============ 顶部栏 ============ -->
    <header class="top-bar">
      <div class="tb-brand">
        <span class="tb-mark">
          <svg viewBox="0 0 32 32" width="20" height="20" aria-hidden="true">
            <polygon points="16,2 28,9 28,23 16,30 4,23 4,9" fill="none" stroke="currentColor" stroke-width="1.6" />
            <polygon points="16,8 23,12 23,20 16,24 9,20 9,12" fill="none" stroke="currentColor" stroke-width="1.2" opacity="0.6" />
            <circle cx="16" cy="16" r="1.8" fill="currentColor" />
          </svg>
        </span>
        <div class="tb-text">
          <div class="tb-t1">天择教育</div>
          <div class="tb-t2">FISCO Chain · 联盟链实训平台</div>
        </div>
      </div>
      <div class="tb-status">
        <span class="status-pill">
          <span class="sp-dot"></span>{{ chainStatusLabel }}
        </span>
        <span class="clock">{{ clockLabel }}</span>
      </div>
    </header>

    <!-- ============ 主内容：右侧堆叠（状态面板 + 登录卡） ============ -->
    <main class="center-row">
      <div class="right-stack">
        <!-- 链网状态面板（右上，块高作为流光目标） -->
        <aside class="stats-panel dq-enter-up">
          <div class="sp-head">
            <span class="sp-pulse"></span>
            <span class="sp-title">链网状态</span>
          </div>
          <div class="sp-row"><span class="sp-k">链模式</span><b class="sp-v">{{ chainStatusLabel }}</b></div>
          <div class="sp-row">
            <span class="sp-k">块高</span>
            <b class="sp-v mono sp-target" :class="{ 'sp-flash': blockFlash }" ref="blockHeightTargetRef">{{ blockHeightLabel }}</b>
          </div>
          <div class="sp-row"><span class="sp-k">共识算法</span><b class="sp-v">PBFT</b></div>
          <div class="sp-row"><span class="sp-k">出块周期</span><b class="sp-v mono">{{ blockPeriodLabel }}</b></div>
          <div class="sp-tps">
            <div class="sp-tps-label">沙盒TPS</div>
            <div class="sp-bars">
              <span v-for="n in 14" :key="n" class="sp-bar" :style="tpsBarStyle(n)"></span>
            </div>
          </div>
          <div class="sp-foot">数据由本地沙盒链路实时聚合</div>
        </aside>

        <!-- 登录卡（右下） -->
        <div class="login-card dq-enter-up">
          <div class="card-glow"></div>

          <header class="card-head">
            <span class="bl-mark">
              <svg viewBox="0 0 32 32" width="22" height="22" aria-hidden="true">
                <polygon points="16,2 28,9 28,23 16,30 4,23 4,9" fill="none" stroke="currentColor" stroke-width="1.6" />
                <polygon points="16,8 23,12 23,20 16,24 9,20 9,12" fill="none" stroke="currentColor" stroke-width="1.2" opacity="0.6" />
                <circle cx="16" cy="16" r="1.8" fill="currentColor" />
              </svg>
            </span>
            <div class="head-text">
              <div class="bl-t1 dq-grad-text">FISCO<span>Chain</span></div>
              <div class="bl-t2">联盟链实训平台</div>
            </div>
          </header>

          <h1 class="card-title">天择教育实训平台</h1>
          <p class="card-sub">基于 FISCO-BCOS 联盟链的绿色低碳实训环境，登录后开启搭链 / 合约 / 治理全流程实战。</p>

          <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-position="top" size="large" @submit.prevent="onPwdLogin">
            <el-form-item label="账号" prop="username">
              <el-input v-model="pwdForm.username" placeholder="请输入账号" clearable :prefix-icon="User" />
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input v-model="pwdForm.password" type="password" placeholder="请输入密码" show-password clearable :prefix-icon="Lock" @keyup.enter="onPwdLogin" />
            </el-form-item>
            <el-button type="primary" class="login-btn" :loading="pwdLoading" @click="onPwdLogin">
            <el-icon v-if="!pwdLoading"><Right /></el-icon>
            <span>登录</span>
          </el-button>
        </el-form>
        </div>
      </div>
    </main>

    <!-- ============ 底部区块浏览器（半透明 + 缓慢右至左滑动） ============ -->
    <footer class="block-strip">
      <div class="bs-label">
        <span class="bs-label-dot"></span>
        <span>区块浏览器</span>
        <span class="bs-label-sub">LIVE</span>
      </div>
      <div class="bs-track">
        <div class="bs-track-inner">
          <div class="bs-block" v-for="(b, i) in chainBlocks" :key="'a'+i">
            <div class="bs-height">#{{ b.num }}</div>
            <div class="bs-hash">0x{{ b.hash }}</div>
            <div class="bs-meta">{{ b.tx }} tx · {{ b.age.toFixed(2) }}s ago</div>
          </div>
          <div class="bs-block" v-for="(b, i) in chainBlocks" :key="'b'+i">
            <div class="bs-height">#{{ b.num }}</div>
            <div class="bs-hash">0x{{ b.hash }}</div>
            <div class="bs-meta">{{ b.tx }} tx · {{ b.age.toFixed(2) }}s ago</div>
          </div>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { User, Lock, Right } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const app = useAppStore()

/* ---------- 链网状态 ---------- */
const chainStatusLabel = computed(() => {
  if (app.chainMode === 'fisco') return 'FISCO 节点已连接'
  if (app.chainMode === 'evm') return 'EVM 真实链运行中'
  return '本地沙盒链路'
})
const blockHeightBase = ref(19_840_000 + Math.floor(Math.random() * 200))
const blockHeightLabel = computed(() => blockHeightBase.value.toLocaleString())
const blockHeightTargetRef = ref<HTMLElement | null>(null)
const blockFlash = ref(false)

/* 出块周期：3-10s 随机跳动（保留两位小数） */
const blockPeriod = ref(Math.round((3 + Math.random() * 7) * 100) / 100)
const blockPeriodLabel = computed(() => `${blockPeriod.value.toFixed(2)}s`)
function rerollBlockPeriod() {
  blockPeriod.value = Math.round((3 + Math.random() * 7) * 100) / 100 // 3.00-9.99
}

/* 块高 +1（流光到达时调用） */
function incrementBlock() {
  blockHeightBase.value += 1
  rerollBlockPeriod()
  blockFlash.value = true
  window.setTimeout(() => { blockFlash.value = false }, 650)
}

/* ---------- 实时时钟 ---------- */
const now = ref(new Date())
const clockLabel = computed(() => {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(now.value.getHours())}:${p(now.value.getMinutes())}:${p(now.value.getSeconds())}`
})
let clockTimer = 0

/* ---------- 背景数据 ---------- */
const chainBlocks = ref(
  Array.from({ length: 14 }, (_, i) => ({
    num: String(19_840_000 + i * 7 + Math.floor(Math.random() * 3)),
    hash: Math.random().toString(16).slice(2, 10).padEnd(8, 'f'),
    tx: 3 + Math.floor(Math.random() * 18),
    age: Math.round((1 + Math.random() * 8) * 100) / 100, // 1.00-8.99s
  }))
)
function particleStyle(n: number) {
  const seed = (n * 73) % 100
  const left = (seed * 1.07) % 100
  const top = (seed * 0.83) % 100
  const dur = 14 + (n % 7) * 3
  const delay = -(n % 9)
  const size = 1.5 + (n % 3)
  return {
    left: `${left}%`, top: `${top}%`,
    width: `${size}px`, height: `${size}px`,
    animationDuration: `${dur}s`, animationDelay: `${delay}s`,
    opacity: 0.3 + (n % 4) * 0.15,
  }
}
function starStyle(n: number) {
  // 使用两个不同质数扰动，避免规整网格
  const seedX = (n * 73 + 17) % 100
  const seedY = (n * 41 + 29) % 100
  const big = n % 13 === 0
  const size = big ? 3 + (n % 3) : 1.4 + (n % 2) * 0.4
  return {
    left: `${(seedX * 1.07) % 100}%`,
    top: `${(seedY * 0.93) % 100}%`,
    width: `${size}px`,
    height: `${size}px`,
    animationDelay: `${-(n % 7)}s`,
    animationDuration: `${2.2 + (n % 6) * 0.5}s`,
    opacity: big ? 0.55 + (n % 3) * 0.18 : 0.22 + (n % 4) * 0.18,
  }
}
function tpsBarStyle(n: number) {
  const h = 24 + ((n * 53) % 60)
  const delay = -(n % 7) * 0.4
  return { height: `${h}%`, animationDelay: `${delay}s` }
}

/* ---------- 账号密码登录 ---------- */
const pwdFormRef = ref<FormInstance>()
const pwdLoading = ref(false)
const pwdForm = reactive({ username: '', password: '' })
const pwdRules: FormRules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}
async function onPwdLogin() {
  if (!pwdFormRef.value) return
  const valid = await pwdFormRef.value.validate().catch(() => false)
  if (!valid) return
  pwdLoading.value = true
  try {
    const u = await auth.loginByPassword(pwdForm.username.trim(), pwdForm.password)
    ElMessage.success(`欢迎回来，${u.name || u.username}`)
    redirectAfterLogin()
  } catch { /* http 拦截器已提示 */ } finally {
    pwdLoading.value = false
  }
}
function redirectAfterLogin() {
  const redirect = (router.currentRoute.value.query.redirect as string) || '/dashboard'
  router.replace(redirect)
}

/* ============================================================
   区块节点星球（Canvas 渲染 + 链路流光特效）
   - 星球偏移至左侧、整体半透明
   - 5 条链路发射流光，3-5s 抵达块高处并将块高 +1
   ============================================================ */
const canvasRef = ref<HTMLCanvasElement | null>(null)
let raf = 0
let resizeFn: (() => void) | null = null

interface Pt { x: number; y: number; z: number }
interface Proj { x: number; y: number; z: number; persp: number; depth: number; i: number }
interface Flow {
  startTime: number
  duration: number
  ai: number  // 链路节点 A
  bi: number  // 链路节点 B
  cx: number  // 贝塞尔控制点（弧线）
  cy: number
  tx: number  // 目标（块高位置）
  ty: number
  done: boolean
}

onMounted(() => {
  /* SSO Token 自动登录：URL 携带 ?token=xxx 时优先用 token 登录 */
  const ssoToken = (route.query.token as string) || ''
  if (ssoToken) {
    auth.loginByToken(ssoToken)
      .then((u) => {
        ElMessage.success(`欢迎回来，${u.name || u.username}`)
        router.replace('/dashboard')
      })
      .catch(() => { /* http 拦截器已提示，回退到账号密码表单 */ })
  }

  /* 时钟（仅刷新时间，块高由流光驱动） */
  clockTimer = window.setInterval(() => {
    now.value = new Date()
  }, 1000)

  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  let w = 0, h = 0
  let cx = 0, cy = 0, R = 0
  let coreGrad: CanvasGradient | null = null
  const dpr = Math.min(window.devicePixelRatio || 1, 2)

  function buildGradient() {
    coreGrad = ctx!.createRadialGradient(cx, cy, R * 0.1, cx, cy, R * 1.05)
    coreGrad.addColorStop(0, 'rgba(0, 230, 195, 0.12)')
    coreGrad.addColorStop(0.55, 'rgba(0, 230, 195, 0.04)')
    coreGrad.addColorStop(1, 'rgba(0, 230, 195, 0)')
  }
  function resize() {
    w = canvas!.clientWidth
    h = canvas!.clientHeight
    canvas!.width = Math.floor(w * dpr)
    canvas!.height = Math.floor(h * dpr)
    ctx!.setTransform(dpr, 0, 0, dpr, 0, 0)
    cx = w * 0.26
    cy = h * 0.52
    R = Math.min(w, h) * 0.34
    buildGradient()
  }
  resizeFn = resize
  resize()
  window.addEventListener('resize', resize)

  // 1. Fibonacci 球面节点
  const N = 150
  const pts: Pt[] = []
  const phi = Math.PI * (3 - Math.sqrt(5)) // 黄金角
  for (let i = 0; i < N; i++) {
    const y = 1 - (i / (N - 1)) * 2
    const r = Math.sqrt(Math.max(0, 1 - y * y))
    const theta = phi * i
    pts.push({ x: Math.cos(theta) * r, y, z: Math.sin(theta) * r })
  }

  // 2. 邻近节点对（连接线）
  const pairs: [number, number][] = []
  const TH = 0.52, TH2 = TH * TH
  for (let i = 0; i < N; i++) {
    for (let j = i + 1; j < N; j++) {
      const dx = pts[i].x - pts[j].x
      const dy = pts[i].y - pts[j].y
      const dz = pts[i].z - pts[j].z
      if (dx * dx + dy * dy + dz * dz < TH2) pairs.push([i, j])
    }
  }

  // 3. 选 5 条链路作为流光通道（间隔分布）
  const channelCount = 5
  const channels: [number, number][] = []
  const stride = Math.max(1, Math.floor(pairs.length / channelCount))
  for (let i = 0; i < channelCount; i++) {
    const offset = Math.floor(Math.random() * Math.min(stride, 3))
    channels.push(pairs[i * stride + offset] || pairs[i * stride])
  }

  // 4. 脉冲节点（模拟链上交易）
  const pulseIdx = new Set<number>()
  for (let k = 0; k < 8; k++) pulseIdx.add(Math.floor(Math.random() * N))

  function rotY(p: Pt, a: number): Pt {
    const c = Math.cos(a), s = Math.sin(a)
    return { x: p.x * c + p.z * s, y: p.y, z: -p.x * s + p.z * c }
  }
  function rotX(p: Pt, a: number): Pt {
    const c = Math.cos(a), s = Math.sin(a)
    return { x: p.x, y: p.y * c - p.z * s, z: p.y * s + p.z * c }
  }

  let angle = 0
  const tiltBase = 0.42
  let t = 0

  // 流光粒子池
  const flows: Flow[] = []
  let lastSpawn = 0
  const spawnInterval = 1400 // 每 1.4s 发射一道流光

  // 块高目标位置缓存（避免每帧 reflow）
  let cachedTarget = { x: 0, y: 0 }
  let lastTargetUpdate = 0
  function updateTarget(nowMs: number) {
    if (nowMs - lastTargetUpdate < 400) return
    lastTargetUpdate = nowMs
    const el = blockHeightTargetRef.value
    if (!el) { cachedTarget = { x: w * 0.78, y: h * 0.36 }; return }
    const r = el.getBoundingClientRect()
    cachedTarget = { x: r.left + r.width / 2, y: r.top + r.height / 2 }
  }

  // 每帧节点投影缓存（供流光取节点坐标）
  const projMap: Record<number, Proj> = {}

  // 连接线深度分桶（批量绘制用，减少 strokeStyle 切换开销）
  const LINE_BUCKETS = 16
  const lineBuckets: Proj[][] = Array.from({ length: LINE_BUCKETS }, () => [])

  function spawnFlow(nowMs: number) {
    if (channels.length === 0) return
    const ch = channels[Math.floor(Math.random() * channels.length)]
    const a = projMap[ch[0]], b = projMap[ch[1]]
    if (!a || !b) return
    const tgt = cachedTarget
    // 弧线控制点：B 与 target 中点，向上偏移形成抛物线
    const mx = (b.x + tgt.x) / 2
    const my = (b.y + tgt.y) / 2 - 70
    flows.push({
      startTime: nowMs,
      duration: 3000 + Math.random() * 2000, // 3-5s
      ai: ch[0], bi: ch[1],
      cx: mx, cy: my,
      tx: tgt.x, ty: tgt.y,
      done: false,
    })
  }

  // 三次贝塞尔取点
  function bezierPoint(f: Flow, p: number, ax: number, ay: number, bx: number, by: number) {
    const om = 1 - p
    return {
      x: om * om * om * ax + 3 * om * om * p * bx + 3 * om * p * p * f.cx + p * p * p * f.tx,
      y: om * om * om * ay + 3 * om * om * p * by + 3 * om * p * p * f.cy + p * p * p * f.ty,
    }
  }

  function frame() {
    t += 1
    const nowMs = performance.now()
    ctx!.clearRect(0, 0, w, h)
    const tilt = tiltBase + Math.sin(t * 0.003) * 0.06
    const focal = 2.6

    // 清空投影缓存与线段分桶
    for (const k in projMap) delete projMap[k]
    for (let bi = 0; bi < LINE_BUCKETS; bi++) lineBuckets[bi].length = 0

    const proj: Proj[] = new Array(N)
    for (let i = 0; i < N; i++) {
      let q = rotY(pts[i], angle)
      q = rotX(q, tilt)
      const persp = focal / (focal - q.z)
      proj[i] = {
        x: cx + q.x * R * persp,
        y: cy + q.y * R * persp,
        z: q.z, persp, depth: (q.z + 1) / 2, i,
      }
      projMap[i] = proj[i]
    }

    // 内核辉光（使用缓存的渐变，避免每帧重建）
    if (coreGrad) {
      ctx!.fillStyle = coreGrad
      ctx!.beginPath()
      ctx!.arc(cx, cy, R * 1.05, 0, Math.PI * 2)
      ctx!.fill()
    }

    // 连接线：按深度分桶批量绘制（大幅减少 strokeStyle 切换与 stroke 调用）
    ctx!.lineWidth = 1
    for (let pi = 0; pi < pairs.length; pi++) {
      const [i, j] = pairs[pi]
      const a = proj[i], b = proj[j]
      const avgD = (a.depth + b.depth) / 2
      const alpha = Math.max(0, (avgD - 0.05) * 0.34)
      if (alpha < 0.02) continue
      const bi = Math.min(LINE_BUCKETS - 1, (avgD * LINE_BUCKETS) | 0)
      lineBuckets[bi].push(a, b)
    }
    for (let bi = 0; bi < LINE_BUCKETS; bi++) {
      const bucket = lineBuckets[bi]
      if (bucket.length === 0) continue
      const avgD = (bi + 0.5) / LINE_BUCKETS
      const alpha = Math.max(0, (avgD - 0.05) * 0.34)
      if (alpha < 0.02) continue
      const r = Math.round(0 + (77 - 0) * (1 - avgD))
      const g = Math.round(230 - (230 - 141) * (1 - avgD))
      const bl = Math.round(195 - (195 - 255) * (1 - avgD))
      ctx!.strokeStyle = `rgba(${r}, ${g}, ${bl}, ${alpha})`
      ctx!.beginPath()
      for (let k = 0; k < bucket.length; k += 2) {
        ctx!.moveTo(bucket[k].x, bucket[k].y)
        ctx!.lineTo(bucket[k + 1].x, bucket[k + 1].y)
      }
      ctx!.stroke()
    }

    // 节点
    for (let i = 0; i < N; i++) {
      const p = proj[i]
      const isPulse = pulseIdx.has(i)
      const pulse = isPulse ? (Math.sin(t * 0.05 + i) * 0.5 + 0.5) : 0
      const base = 1.2 + 2.2 * p.depth * p.persp
      const size = base + (isPulse ? pulse * 1.8 : 0)
      const alpha = Math.min(1, 0.15 + 0.7 * p.depth + pulse * 0.35)
      if (isPulse && pulse > 0.55) {
        ctx!.fillStyle = `rgba(180, 255, 240, ${alpha})`
      } else {
        ctx!.fillStyle = `rgba(0, 230, 195, ${alpha})`
      }
      ctx!.beginPath()
      ctx!.arc(p.x, p.y, size, 0, Math.PI * 2)
      ctx!.fill()
      if (p.depth > 0.55) {
        ctx!.fillStyle = `rgba(0, 230, 195, ${alpha * 0.16})`
        ctx!.beginPath()
        ctx!.arc(p.x, p.y, size * 3.2, 0, Math.PI * 2)
        ctx!.fill()
      }
    }

    // 更新块高目标位置
    updateTarget(nowMs)

    // 流光发射
    if (nowMs - lastSpawn > spawnInterval) {
      lastSpawn = nowMs
      spawnFlow(nowMs)
    }

    // 流光绘制（贝塞尔：A → B → 弧线控制点 → target）
    for (let fi = flows.length - 1; fi >= 0; fi--) {
      const f = flows[fi]
      const a = projMap[f.ai], b = projMap[f.bi]
      if (!a || !b) { flows.splice(fi, 1); continue }
      const elapsed = nowMs - f.startTime
      const p = elapsed / f.duration
      if (p >= 1) {
        if (!f.done) {
          f.done = true
          incrementBlock()
        }
        flows.splice(fi, 1)
        continue
      }
      // 头部当前位置
      const head = bezierPoint(f, p, a.x, a.y, b.x, b.y)
      // 拖尾（12 段，向后采样）
      const samples = 12
      for (let s = 0; s < samples; s++) {
        const sp1 = Math.max(0, p - (s / samples) * 0.32)
        const sp2 = Math.max(0, p - ((s + 1) / samples) * 0.32)
        const p1 = bezierPoint(f, sp1, a.x, a.y, b.x, b.y)
        const p2 = bezierPoint(f, sp2, a.x, a.y, b.x, b.y)
        const alpha = (1 - s / samples) * 0.85
        ctx!.strokeStyle = `rgba(120, 255, 230, ${alpha})`
        ctx!.lineWidth = 2.4 * (1 - s / samples * 0.55)
        ctx!.beginPath()
        ctx!.moveTo(p1.x, p1.y)
        ctx!.lineTo(p2.x, p2.y)
        ctx!.stroke()
      }
      // 流光头部（带辉光）
      ctx!.shadowColor = 'rgba(0, 255, 220, 0.95)'
      ctx!.shadowBlur = 16
      ctx!.fillStyle = 'rgba(230, 255, 248, 1)'
      ctx!.beginPath()
      ctx!.arc(head.x, head.y, 3.4, 0, Math.PI * 2)
      ctx!.fill()
      ctx!.shadowBlur = 0
    }

    angle += 0.0026 // 缓慢旋转
    raf = requestAnimationFrame(frame)
  }

  // 等 DOM 渲染完成，确保块高元素可获取位置
  nextTick(() => { frame() })
})

onUnmounted(() => {
  cancelAnimationFrame(raf)
  if (clockTimer) clearInterval(clockTimer)
  if (resizeFn) window.removeEventListener('resize', resizeFn)
})
</script>

<style scoped lang="scss">
.login-page {
  position: relative;
  width: 100vw; height: 100vh;
  overflow: hidden;
  background:
    radial-gradient(1200px 700px at 18% 8%, rgba(0, 230, 195, 0.08), transparent 60%),
    radial-gradient(900px 600px at 92% 110%, rgba(77, 141, 255, 0.06), transparent 60%),
    radial-gradient(ellipse at center, #0a1024 0%, #050810 100%);
}

/* ============ 区块节点星球（左侧偏移 + 半透明） ============ */
.planet-canvas {
  position: absolute; inset: 0;
  width: 100%; height: 100%;
  z-index: 1;
  opacity: 0.78; /* 稍微透明 */
}
/* 外层大气辉光（偏移至左侧） */
.planet-aura {
  position: absolute; top: 52%; left: 26%;
  width: min(58vmin, 620px); height: min(58vmin, 620px);
  transform: translate(-50%, -50%);
  border-radius: 50%;
  background: radial-gradient(circle, rgba(0,230,195,0.16) 0%, rgba(0,230,195,0.05) 45%, transparent 70%);
  filter: blur(26px);
  z-index: 1; pointer-events: none;
  opacity: 0.7;
  animation: aura-breathe 6s ease-in-out infinite;
}
@keyframes aura-breathe {
  0%, 100% { opacity: 0.55; transform: translate(-50%, -50%) scale(1); }
  50% { opacity: 0.85; transform: translate(-50%, -50%) scale(1.06); }
}

/* ============ 环境装饰层 ============ */
.bg-decor { position: absolute; inset: 0; pointer-events: none; overflow: hidden; z-index: 0; }
.bg-hex { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0.7; }

.bg-particles { position: absolute; inset: 0; }
.bg-particle {
  position: absolute; border-radius: 50%;
  background: var(--dq-primary);
  box-shadow: 0 0 6px var(--dq-primary-glow);
  animation-name: particle-float;
  animation-timing-function: ease-in-out;
  animation-iteration-count: infinite;
}
@keyframes particle-float {
  0%, 100% { transform: translate(0, 0); }
  25% { transform: translate(15px, -25px); }
  50% { transform: translate(-10px, -45px); }
  75% { transform: translate(20px, -20px); }
}

.bg-stars { position: absolute; inset: 0; }
.bg-star {
  position: absolute; width: 2px; height: 2px; border-radius: 50%;
  background: #cfe9ff;
  box-shadow: 0 0 4px rgba(207, 233, 255, 0.7);
  animation: star-twinkle 3s ease-in-out infinite;
}
.bg-star-lg {
  background: #ffffff;
  box-shadow: 0 0 8px rgba(180, 240, 255, 0.95), 0 0 16px rgba(0, 230, 195, 0.5);
  animation: star-twinkle-lg 4s ease-in-out infinite;
}
@keyframes star-twinkle {
  0%, 100% { opacity: 0.2; transform: scale(0.7); }
  50% { opacity: 1; transform: scale(1.15); }
}
@keyframes star-twinkle-lg {
  0%, 100% { opacity: 0.35; transform: scale(0.85); }
  50% { opacity: 1; transform: scale(1.3); }
}

/* ============ 星云云团（缓慢漂移） ============ */
.bg-nebula { position: absolute; inset: 0; }
.neb {
  position: absolute; border-radius: 50%;
  filter: blur(70px);
  mix-blend-mode: screen;
  pointer-events: none;
  will-change: transform;
}
.neb-1 {
  width: 520px; height: 520px; top: 8%; left: 4%;
  background: radial-gradient(circle, rgba(0, 230, 195, 0.16) 0%, rgba(0, 230, 195, 0.04) 50%, transparent 75%);
  animation: neb-drift-1 32s ease-in-out infinite;
}
.neb-2 {
  width: 640px; height: 640px; bottom: 4%; left: 26%;
  background: radial-gradient(circle, rgba(77, 141, 255, 0.14) 0%, rgba(77, 141, 255, 0.03) 50%, transparent 75%);
  animation: neb-drift-2 44s ease-in-out infinite;
}
.neb-3 {
  width: 460px; height: 460px; top: 38%; right: 8%;
  background: radial-gradient(circle, rgba(245, 55, 155, 0.09) 0%, rgba(245, 55, 155, 0.02) 50%, transparent 75%);
  animation: neb-drift-3 38s ease-in-out infinite;
}
.neb-4 {
  width: 380px; height: 380px; top: 62%; left: 8%;
  background: radial-gradient(circle, rgba(120, 90, 255, 0.10) 0%, rgba(120, 90, 255, 0.02) 55%, transparent 75%);
  animation: neb-drift-4 28s ease-in-out infinite;
}
@keyframes neb-drift-1 {
  0%, 100% { transform: translate(0, 0) scale(1); opacity: 0.55; }
  50% { transform: translate(60px, -40px) scale(1.12); opacity: 0.8; }
}
@keyframes neb-drift-2 {
  0%, 100% { transform: translate(0, 0) scale(1); opacity: 0.5; }
  50% { transform: translate(-50px, 50px) scale(1.08); opacity: 0.75; }
}
@keyframes neb-drift-3 {
  0%, 100% { transform: translate(0, 0) scale(1); opacity: 0.45; }
  50% { transform: translate(-40px, -50px) scale(1.15); opacity: 0.7; }
}
@keyframes neb-drift-4 {
  0%, 100% { transform: translate(0, 0) scale(1); opacity: 0.5; }
  50% { transform: translate(45px, -30px) scale(1.1); opacity: 0.72; }
}

/* ============ 顶部栏 ============ */
.top-bar {
  position: absolute; top: 0; left: 0; right: 0; z-index: 4;
  display: flex; align-items: center; justify-content: space-between;
  padding: 22px 40px;
}
.tb-brand { display: flex; align-items: center; gap: 12px;
  .tb-mark {
    width: 40px; height: 40px; border-radius: 10px;
    background: linear-gradient(135deg, rgba(0,230,195,0.18), rgba(0,230,195,0.04));
    border: 1px solid rgba(0,230,195,0.38);
    color: var(--dq-primary);
    display: inline-flex; align-items: center; justify-content: center;
    text-shadow: 0 0 10px var(--dq-primary-glow);
  }
  .tb-t1 { font-weight: 800; font-size: 16px; letter-spacing: 2px; color: var(--dq-text); }
  .tb-t2 { font-size: 11px; color: var(--dq-text-dim); margin-top: 2px; letter-spacing: 0.5px; }
}
.tb-status { display: flex; align-items: center; gap: 14px; }
.status-pill {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 7px 14px; border-radius: 20px;
  font-size: 12px; color: var(--dq-primary);
  background: rgba(0,230,195,0.08);
  border: 1px solid rgba(0,230,195,0.28);
  .sp-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--dq-primary);
    box-shadow: 0 0 8px var(--dq-primary-glow);
    animation: dot-blink 2s ease-in-out infinite;
  }
}
.clock {
  font-family: var(--dq-mono); font-size: 13px;
  color: var(--dq-text-dim); letter-spacing: 1px;
  text-shadow: 0 0 8px rgba(0,230,195,0.25);
}
@keyframes dot-blink { 0%, 100% { opacity: 0.6; } 50% { opacity: 1; } }

/* ============ 主内容行（右侧偏右堆叠，稍向中间靠拢） ============ */
.center-row {
  position: relative; z-index: 3;
  width: 100%; height: 100vh;
  display: flex; align-items: center; justify-content: flex-end;
  padding: 0 5%;
  box-sizing: border-box;
}
.right-stack {
  display: flex; flex-direction: column;
  gap: 16px;
  width: 440px; max-width: calc(100vw - 32px);
  margin-right: clamp(24px, 5vw, 96px); /* 自适应向中间靠拢 */
  align-items: stretch;
}

/* ============ 登录卡 ============ */
.login-card {
  position: relative;
  width: 100%;
  padding: 36px 44px 28px;
  border-radius: 20px;
  background: linear-gradient(180deg, rgba(18, 28, 52, 0.96) 0%, rgba(10, 16, 32, 0.97) 100%);
  border: 1px solid rgba(0, 230, 195, 0.42);
  box-shadow:
    0 30px 90px rgba(0, 0, 0, 0.72),
    0 0 0 1px rgba(0,230,195,0.12) inset,
    0 0 80px rgba(0,230,195,0.18),
    0 0 24px rgba(0,230,195,0.12);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  animation: card-breathe 4s ease-in-out infinite;
}
@keyframes card-breathe {
  0%, 100% { box-shadow: 0 30px 90px rgba(0,0,0,0.72), 0 0 0 1px rgba(0,230,195,0.12) inset, 0 0 80px rgba(0,230,195,0.16), 0 0 24px rgba(0,230,195,0.10); }
  50% { box-shadow: 0 30px 90px rgba(0,0,0,0.72), 0 0 0 1px rgba(0,230,195,0.20) inset, 0 0 100px rgba(0,230,195,0.26), 0 0 32px rgba(0,230,195,0.18); }
}
/* 顶部强调线 */
.login-card::before {
  content: ''; position: absolute; top: 0; left: 12%; right: 12%; height: 2px;
  background: linear-gradient(90deg, transparent, var(--dq-primary), transparent);
  box-shadow: 0 0 12px var(--dq-primary-glow);
  border-radius: 2px;
  animation: accent-glow 3s ease-in-out infinite;
}
@keyframes accent-glow {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 1; }
}
.card-glow {
  position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
  background: radial-gradient(ellipse at 50% 0%, rgba(0,230,195,0.16), transparent 55%);
}

.card-head {
  display: flex; align-items: center; gap: 12px; margin-bottom: 20px;
  position: relative;
  .bl-mark {
    width: 46px; height: 46px; border-radius: 12px;
    background: linear-gradient(135deg, rgba(0,230,195,0.20), rgba(0,230,195,0.04));
    border: 1px solid rgba(0,230,195,0.42);
    color: var(--dq-primary);
    display: inline-flex; align-items: center; justify-content: center;
    text-shadow: 0 0 12px var(--dq-primary-glow);
    animation: mark-pulse 3s ease-in-out infinite;
  }
  @keyframes mark-pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(0,230,195,0.35); }
    50% { box-shadow: 0 0 0 6px rgba(0,230,195,0); }
  }
  .bl-t1 { font-weight: 800; letter-spacing: 2.5px; font-size: 20px; line-height: 1.2; }
  .bl-t1 span { font-weight: 500; margin-left: 4px; opacity: 0.85; }
  .bl-t2 { font-size: 12px; color: var(--dq-text-dim); margin-top: 2px; letter-spacing: 0.5px; }
}

.card-title {
  margin: 0 0 12px;
  font-size: 26px; font-weight: 800; letter-spacing: 2px;
  background: linear-gradient(135deg, var(--dq-text) 0%, var(--dq-primary) 60%, var(--dq-info) 100%);
  background-size: 200% 100%;
  -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: title-shift 6s ease-in-out infinite;
  text-shadow: 0 0 30px rgba(0,230,195,0.25);
}
@keyframes title-shift {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}
.card-sub {
  font-size: 12.5px; color: var(--dq-text-dim); line-height: 1.6;
  margin: 0 0 18px;
}

:deep(.el-form-item__label) {
  font-size: 12px; color: var(--dq-text-dim); font-weight: 600;
  letter-spacing: 0.3px; padding-bottom: 4px;
}
:deep(.el-input__wrapper) {
  background: rgba(7, 11, 22, 0.6);
  border: 1px solid var(--dq-border);
  box-shadow: none !important;
  transition: all .2s;
  &:hover { border-color: var(--dq-border-2); }
  &.is-focus {
    border-color: var(--dq-primary);
    box-shadow: 0 0 0 2px rgba(0,230,195,0.14) inset, 0 0 16px rgba(0,230,195,0.18) !important;
  }
}
:deep(.el-input__inner) { color: var(--dq-text); height: 42px; }

.login-btn {
  position: relative;
  width: 100%; height: 44px; margin-top: 6px;
  font-weight: 600; font-size: 14px; letter-spacing: 1.5px;
  background: var(--dq-grad-primary);
  background-size: 200% 100%;
  border: none; overflow: hidden;
  box-shadow: 0 6px 18px rgba(0, 230, 195, 0.25);
  transition: all .3s;
  animation: btn-breathe 3s ease-in-out infinite;
  &::before {
    content: ''; position: absolute; top: 0; left: -100%; width: 100%; height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.25), transparent);
    transition: left .6s;
  }
  &:hover {
    box-shadow: 0 8px 26px rgba(0, 230, 195, 0.4); transform: translateY(-1px);
    background-position: 100% 50%;
    &::before { left: 100%; }
  }
  &:active { transform: translateY(0); }
}
@keyframes btn-breathe {
  0%, 100% { box-shadow: 0 6px 18px rgba(0, 230, 195, 0.22); }
  50% { box-shadow: 0 6px 22px rgba(0, 230, 195, 0.4); }
}

/* ============ 链网状态面板（弱化以突出登录卡） ============ */
.stats-panel {
  width: 100%;
  padding: 14px 20px;
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(15, 22, 40, 0.5) 0%, rgba(9, 14, 28, 0.55) 100%);
  border: 1px solid rgba(0, 230, 195, 0.16);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  opacity: 0.92;
}
.sp-head {
  display: flex; align-items: center; gap: 8px; margin-bottom: 10px;
  .sp-pulse {
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--dq-primary);
    box-shadow: 0 0 8px var(--dq-primary-glow);
    animation: dot-blink 1.6s ease-in-out infinite;
  }
  .sp-title { font-size: 12px; font-weight: 700; color: var(--dq-text-dim); letter-spacing: 1px; }
}
.sp-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 5px 0;
  border-bottom: 1px dashed rgba(31, 42, 68, 0.6);
  .sp-k { font-size: 11px; color: var(--dq-text-dimmer); }
  .sp-v { font-size: 12px; color: var(--dq-text-dim); font-weight: 600; }
  .sp-v.mono { font-family: var(--dq-mono); color: var(--dq-primary); letter-spacing: 0.5px; }
}
/* 块高流光命中闪烁 */
.sp-target.sp-flash {
  animation: sp-flash 0.65s ease-out;
}
@keyframes sp-flash {
  0% { color: #ffffff; text-shadow: 0 0 18px #00e6c3, 0 0 36px #00e6c3; transform: scale(1.18); }
  100% { color: var(--dq-primary); text-shadow: none; transform: scale(1); }
}
.sp-tps {
  margin-top: 12px; padding-top: 10px;
  border-top: 1px dashed rgba(31, 42, 68, 0.7);
  .sp-tps-label { font-size: 11px; color: var(--dq-text-dim); margin-bottom: 8px; letter-spacing: 0.5px; }
  .sp-bars {
    display: flex; align-items: flex-end; gap: 3px; height: 42px;
    .sp-bar {
      flex: 1; border-radius: 2px 2px 0 0;
      background: linear-gradient(180deg, var(--dq-primary), rgba(0,230,195,0.2));
      box-shadow: 0 0 6px rgba(0,230,195,0.35);
      transform-origin: bottom;
      animation: tps-bounce 1.6s ease-in-out infinite;
    }
  }
}
@keyframes tps-bounce {
  0%, 100% { transform: scaleY(0.6); opacity: 0.55; }
  50% { transform: scaleY(1); opacity: 1; }
}
.sp-foot {
  margin-top: 10px; font-size: 10px; color: var(--dq-text-dimmer);
  text-align: center; letter-spacing: 0.3px;
}

/* ============ 底部区块浏览器（半透明 + 缓慢右至左滑动） ============ */
.block-strip {
  position: absolute; left: 0; right: 0; bottom: 0; z-index: 4;
  display: flex; align-items: center; gap: 16px;
  padding: 14px 40px;
  background: linear-gradient(180deg, transparent, rgba(5, 8, 16, 0.55));
}
.bs-label {
  flex-shrink: 0; display: flex; align-items: center; gap: 8px;
  font-size: 12px; color: var(--dq-text-dim); letter-spacing: 1px;
  .bs-label-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--dq-primary);
    box-shadow: 0 0 8px var(--dq-primary-glow);
    animation: dot-blink 1.4s ease-in-out infinite;
  }
  .bs-label-sub {
    font-family: var(--dq-mono); font-size: 9px;
    padding: 2px 6px; border-radius: 3px;
    color: var(--dq-primary);
    background: rgba(0,230,195,0.1);
    border: 1px solid rgba(0,230,195,0.25);
  }
}
.bs-track {
  flex: 1;
  overflow: hidden;
  mask-image: linear-gradient(90deg, transparent, black 3%, black 97%, transparent);
  -webkit-mask-image: linear-gradient(90deg, transparent, black 3%, black 97%, transparent);
}
.bs-track-inner {
  display: flex; gap: 10px;
  width: max-content;
  animation: bs-scroll 100s linear infinite;
}
@keyframes bs-scroll {
  from { transform: translateX(0); }
  to { transform: translateX(-50%); } /* 右至左滑动，复制内容实现无缝 */
}
.bs-block {
  flex-shrink: 0; min-width: 138px;
  padding: 7px 11px; border-radius: 8px;
  background: rgba(0, 230, 195, 0.035); /* 半透明 */
  border: 1px solid rgba(0, 230, 195, 0.14);
  font-family: var(--dq-mono);
  .bs-height { font-size: 11px; color: var(--dq-primary); letter-spacing: 0.4px; }
  .bs-hash { font-size: 10px; color: var(--dq-text-dim); margin-top: 2px; opacity: 0.8; }
  .bs-meta { font-size: 9.5px; color: var(--dq-text-dimmer); margin-top: 2px; }
}

/* 响应式 */
@media (max-width: 1280px) {
  .right-stack { margin-right: clamp(20px, 3vw, 48px); width: 420px; }
}
@media (max-width: 960px) {
  .stats-panel { display: none; }
  .planet-canvas { opacity: 0.5; }
  .planet-aura { left: 40%; }
  .right-stack { margin-right: 0; }
}
@media (max-width: 640px) {
  .center-row { justify-content: center; padding: 80px 16px 90px; }
  .right-stack { width: 100%; margin-right: 0; }
  .top-bar { padding: 14px 18px; }
  .tb-status .clock { display: none; }
  .block-strip { display: none; }
}
</style>
