<template>
  <div class="cloud dq-enter-up">
    <!-- 左侧：步骤导航 + 进度 -->
    <div class="left">
      <div class="dq-card steps-card">
        <div class="dq-card-title">
          联盟链搭建实训
          <span class="dq-live" style="margin-left:auto"><span class="dot"></span>真实 EVM</span>
        </div>

        <!-- 总进度环 + 数据行 -->
        <div class="progress-head">
          <!-- SVG 进度环 -->
          <div class="ring-wrap">
            <svg class="ring" viewBox="0 0 120 120">
              <defs>
                <linearGradient id="cd-ring-g" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0%" stop-color="#00e6c3"/>
                  <stop offset="100%" stop-color="#4d8dff"/>
                </linearGradient>
              </defs>
              <circle cx="60" cy="60" r="48" fill="none" stroke="var(--dq-border)" stroke-width="9"/>
              <circle
                cx="60" cy="60" r="48" fill="none"
                stroke="url(#cd-ring-g)" stroke-width="9" stroke-linecap="round"
                :stroke-dasharray="ringDash" :stroke-dashoffset="ringOffset"
                transform="rotate(-90 60 60)"
                style="transition: stroke-dashoffset .6s cubic-bezier(0.4, 0, 0.2, 1)"
              />
            </svg>
            <div class="ring-inner">
              <div class="ring-pct dq-grad-text">{{ progressPct }}%</div>
              <div class="ring-sub">总进度</div>
            </div>
          </div>
          <!-- 进度信息 -->
          <div class="ph-info">
            <div class="ph-row">
              <span class="ph-k">已完成</span>
              <span class="ph-v dq-mono"><b>{{ doneSteps.length }}</b> / {{ steps.length }} 步</span>
            </div>
            <div class="ph-row">
              <span class="ph-k">累计耗时</span>
              <span class="ph-v dq-mono">{{ totalDuration }}</span>
            </div>
            <div class="ph-row">
              <span class="ph-k">当前块高</span>
              <span class="ph-v dq-mono">#{{ chainHeight }}</span>
            </div>
            <div class="ph-ops">
              <el-button size="small" @click="resetAll" :disabled="!doneSteps.length">
                <el-icon><RefreshLeft /></el-icon>重置全部
              </el-button>
              <el-button size="small" @click="rollback" :disabled="!doneSteps.length">
                <el-icon><Back /></el-icon>回退上一步
              </el-button>
            </div>
          </div>
        </div>

        <!-- 小进度条（与环互补） -->
        <div class="progress-bar">
          <div class="pb-fill" :style="{ width: progressPct + '%' }"></div>
        </div>

        <el-steps direction="vertical" :active="active" finish-status="success" class="dq-steps">
          <el-step
            v-for="(s, i) in steps"
            :key="s.step"
            :title="stepTitle(s, i)"
            :description="stepDesc(s, i)"
            :status="doneSteps.includes(s.step) ? 'success' : (i === active ? 'process' : 'wait')"
            @click.native="active = i"
          />
        </el-steps>
      </div>

      <!-- 当前步骤详情 -->
      <div class="dq-card step-detail" v-if="cur">
        <div class="step-head">
          <span class="step-no">步骤 {{ cur.step }}</span>
          <span class="step-title">{{ cur.title }}</span>
          <span class="step-duration dq-tag info" v-if="stepDurations[cur.step]">
            <el-icon><Timer /></el-icon>耗时 {{ stepDurations[cur.step] }}
          </span>
          <span class="step-done-at dq-tag" v-else-if="doneSteps.includes(cur.step)">
            <el-icon><CircleCheckFilled /></el-icon>已完成
          </span>
        </div>
        <p class="desc">{{ cur.desc }}</p>

        <!-- 原理讲解 -->
        <div class="dq-principle" v-if="cur.principle">
          <div class="dp-label">◆ 原理讲解</div>
          <div>{{ cur.principle }}</div>
        </div>

        <!-- 真实命令 -->
        <div class="section-label">真实命令</div>
        <div class="cmds">
          <div class="dq-cmd-line" v-for="(c, i) in cur.commands" :key="i">
            <span class="prompt">$</span>
            <code>{{ c }}</code>
          </div>
        </div>

        <!-- 预期输出 -->
        <div class="section-label">预期输出</div>
        <el-alert :title="cur.expected" type="info" :closable="false" show-icon />

        <!-- 提示 -->
        <div class="dq-tip" v-if="cur.tip">
          <span class="dt-label">学习提示:</span>{{ cur.tip }}
        </div>

        <!-- 知识点小结 -->
        <div class="knowledge-box">
          <div class="kb-head">
            <span class="kb-icon">💡</span>
            <span class="kb-title">知识点小结 · Step {{ cur.step }}</span>
            <el-button type="text" size="small" class="kb-toggle" @click="kbOpen = !kbOpen">
              <el-icon><component :is="kbOpen ? 'ArrowUp' : 'ArrowDown'" /></el-icon>
            </el-button>
          </div>
          <div class="kb-body" v-show="kbOpen">
            <ul class="kb-list">
              <li v-for="(k, i) in curKnowledge" :key="i"><i class="kb-dot"></i>{{ k }}</li>
            </ul>
          </div>
        </div>

        <div class="ops">
          <el-button size="small" @click="goPrev" :disabled="active === 0">
            <el-icon><ArrowLeft /></el-icon>上一步
          </el-button>
          <el-button type="primary" @click="exec" :loading="loading">
            <el-icon><VideoPlay /></el-icon>&nbsp;{{ doneSteps.includes(cur.step) ? '重新执行' : '在真实链执行' }}
          </el-button>
          <el-button @click="goNext" :disabled="active >= steps.length - 1">
            下一步&nbsp;<el-icon><ArrowRight /></el-icon>
          </el-button>
        </div>
      </div>
    </div>

    <!-- 右侧：云桌面终端 -->
    <div class="dq-card terminal-card">
      <div class="dq-card-title">
        云桌面终端
        <span class="dq-tag info" style="margin-left:auto">真实输出 · 实时</span>
      </div>
      <div class="term-wrap">
        <div class="term" ref="termRef"></div>
      </div>
      <div class="term-foot">
        <span class="tf-hint">💡 左侧「在真实链执行」会在此终端输出真实链返回结果（合约地址、交易哈希、Gas 等）</span>
        <div class="tf-kw">
          <span>PBFT</span>
          <span>EVM</span>
          <span>Solidity</span>
          <span>Web3</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, onActivated, computed, nextTick, watch } from 'vue'
import { Terminal } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'
import 'xterm/css/xterm.css'
import { chainApi } from '@/api'
import { useAppStore } from '@/stores/app'
import { ElMessage, ElMessageBox } from 'element-plus'
import { safeGet, safeSet, fmtDuration } from '@/utils/storage'

const app = useAppStore()
const steps = ref<any[]>([])
const active = ref(0)
const loading = ref(false)
const termRef = ref<HTMLElement>()
const kbOpen = ref(true)

/* ---------- 持久化键 ---------- */
const DONE_KEY = 'cloud_done_v1'
const DUR_KEY = 'cloud_step_dur_v1'      // { stepNum: seconds }
const START_KEY = 'cloud_step_start_v1' // 执行开始时间戳（用于当前步）

/* ---------- 已完成步骤持久化（双写：localStorage + 服务端，换浏览器/换设备也能续） ---------- */
function loadDoneSteps(): number[] {
  const raw = safeGet<any[]>(DONE_KEY, [])
  return Array.isArray(raw) ? raw.filter((x) => typeof x === 'number') : []
}
const doneSteps = ref<number[]>(loadDoneSteps())
const persistDone = () => safeSet(DONE_KEY, doneSteps.value)

/** 从服务端拉取该钱包的搭链进度（优先级高于 localStorage，取两者并集） */
async function syncProgressFromServer() {
  try {
    const wallet = app.currentWallet || '0xlearner'
    const r: any = await chainApi.progress(wallet)
    if (!r || !Array.isArray(r.steps)) return
    const serverDone = (r.steps || []).filter((s: any) => s.done).map((s: any) => s.step)
    const merged = Array.from(new Set([...doneSteps.value, ...serverDone]))
    if (merged.length > doneSteps.value.length) {
      doneSteps.value = merged
      persistDone()
    }
  } catch {
    /* 服务端拉取失败不阻塞，继续用 localStorage */
  }
}

/* ---------- 每步耗时持久化 ---------- */
type DurMap = Record<number, number>
function loadDurations(): DurMap {
  const raw = safeGet<DurMap>(DUR_KEY, {})
  const out: DurMap = {}
  if (raw && typeof raw === 'object') {
    for (const k of Object.keys(raw)) {
      const v = Number((raw as any)[k])
      if (v > 0) out[Number(k)] = v
    }
  }
  return out
}
const stepDurationsRaw = ref<DurMap>(loadDurations())
const stepDurations = computed<Record<number, string>>(() => {
  const out: Record<number, string> = {}
  for (const [k, v] of Object.entries(stepDurationsRaw.value)) {
    out[Number(k)] = fmtDuration(v)
  }
  return out
})
const persistDur = () => safeSet(DUR_KEY, stepDurationsRaw.value)

/* 累计总耗时 */
const totalDuration = computed(() => {
  const total = Object.values(stepDurationsRaw.value).reduce((a, b) => a + b, 0)
  return fmtDuration(total)
})

/* 当前执行开始时间（临时，存内存 + localStorage 防止刷新中断丢失） */
const curStartTs = ref<number | null>(null)
function startTimer() {
  curStartTs.value = Date.now()
  safeSet(START_KEY, curStartTs.value)
}
function stopTimer(stepNum: number): number {
  const start = curStartTs.value || safeGet<number | null>(START_KEY, null)
  safeSet(START_KEY, null)
  curStartTs.value = null
  if (!start) return 0
  const sec = Math.max(1, Math.round((Date.now() - start) / 1000))
  stepDurationsRaw.value[stepNum] = (stepDurationsRaw.value[stepNum] || 0) + sec
  persistDur()
  return sec
}

/* ---------- 进度环 ---------- */
const RING_CIRCUM = 2 * Math.PI * 48
const ringDash = `${RING_CIRCUM} ${RING_CIRCUM}`
const ringOffset = computed(() => {
  const pct = steps.value.length ? doneSteps.value.length / steps.value.length : 0
  return String(RING_CIRCUM * (1 - pct))
})

/* ---------- 步骤标题 / 描述扩展（注入耗时 badge） ---------- */
function stepTitle(s: any, _i: number) {
  return `${s.step}. ${s.title}`
}
/* 10 步 el-step__description 精简摘要（侧栏卡片短描述；详情在下方 principle/commands/expected 面板） */
const STEP_DESC_SHORT: Record<number, string> = {
  1: '4 节点 PBFT 配置+启动，6 组织映射',
  2: '4 fisco-bcos 进程存活+6 组织对照',
  3: 'tail 日志，PBFT 持续出块（+seal/Report）',
  4: 'console 4 命令验链（块高/Peer/Sealer/Group）',
  5: '6 成员↔4 节点↔钱包地址 三元映射表',
  6: '6 角色能量梯度：0/50/20/15/10/100',
  7: '6 钱包地址 + Step 9 后试发 1000 押金',
  8: '3 项验收：节点/余额/合约查询通过',
  9: '部署 GreenEnergy ERC20 (1,000,000)',
  10: 'name/balanceOf + 地铁+50、外卖+10 验证',
}
function stepDesc(s: any, _i: number) {
  const dur = stepDurations.value[s.step]
  const txt = STEP_DESC_SHORT[s.step] ?? s.desc
  if (dur) return `${txt} · ⏱ ${dur}`
  return txt
}

let term: Terminal
let fit: FitAddon
let ws: WebSocket
const curCmd = ref('')

const cur = computed(() => steps.value[active.value])
const chainHeight = computed(() => app.chainHeight)
const progressPct = computed(() => steps.value.length ? Math.round(doneSteps.value.length / steps.value.length * 100) : 0)

/* 每步知识点（10 步版：Step 5-8 专门覆盖 6 大联盟节点） */
const KNOWLEDGE: Record<number, string[]> = {
  1: [
    '绿色低碳联盟链由 6 个组织共建：🛡️管理员 / 🚇地铁 / 🚌公交 / 🚲单车 / 📦外卖 / ♻️回收，实训用 4 节点复用承载',
    '4 共识节点承载映射：node0=管理员+地铁；node1=公交+单车；node2=外卖+回收；node3=热备/监管',
    'PBFT 共识：3f+1 节点可容忍 f 个拜占庭节点，4 节点 = 容忍 1 个恶意节点',
    'build_chain.sh 自动生成：节点证书、genesis 创世块、config.ini 配置、启动脚本；生产可改 6 物理节点',
  ],
  2: [
    '4 个进程对应 4 个逻辑节点，但通过「钱包地址 + 角色白名单」隔离出 6 个业务组织',
    '6 角色盘点：0xadmin 管理员 / 0xmetro 地铁 / 0xbus 公交 / 0xbike 单车 / 0xtakeout 外卖 / 0xrecycle 回收',
    '进程存活 ≠ 业务可用，还需要：钱包链上存在 + 角色白名单 + 合约权限 三件事同时成立',
    '生产环境通常用 systemd/supervisor 守护进程，异常退出自动重启',
  ],
  3: [
    '绿色低碳链的每笔能量发放（mint）和资产兑换都会在这些区块里打包',
    'node0 出块时：多为地铁发能量、管理员部署合约类交易',
    'node1 出块时：多为公交/单车发能量类交易',
    'node2 出块时：多为外卖/回收发能量 + NFT 兑换类交易；node3 可切 observer 只验不包',
    '`+++Generating seal` 表示 sealer 开始打包，`Report` 表示 PBFT 三阶段完成、区块落盘',
  ],
  4: [
    '控制台通过 Channel 协议连接节点（双向长连接 + 证书认证），比 JSON-RPC 更安全',
    'getBlockNumber / getPeers / getSealerList / getGroupPeers 是联盟链运维四件套',
    '6 个业务组织（admin/metro/bus/bike/takeout/recycle）共享同一个 groupId=1，通过钱包地址区分角色',
    '后续 Step 5~8 将逐一落实 6 角色的职责、能量规则、钱包注册、验收',
  ],
  // ==================== Step 5-8：6 大联盟节点组织配置（新增） ====================
  5: [
    '6 联盟组织 ↔ 4 共识节点映射（实训复用版）：node0=管理员+地铁；node1=公交+单车；node2=外卖+回收；node3=热备',
    '6 组织「四要素」：组织名 → 角色 → 承载节点 → 钱包地址，任意一步发能量都要求四要素同时匹配',
    '管理员（🛡️0xadmin）在 node0：部署合约、管理树种，不发能量（避免利益冲突）',
    '5 个业务角色在对应节点：地铁🚇+50 / 公交🚌+20 / 单车🚲+15 / 外卖📦+10 / 回收♻️+100',
  ],
  6: [
    '能量发放值按「减碳贡献」梯度设计：回收 100 > 地铁 50 > 公交 20 > 单车 15 > 外卖 10 > 管理员 0',
    '管理员发 0 能量是刻意设计：治理角色不直接发币，防止自交易（self-dealing）',
    '前端 /eco 的角色卡片顺序和能量值就来自这张规则表，后端 emit_energy 也按此表做白名单校验',
    '回收 1kg 对应 100 能量，是为了鼓励用户回收行为、配合绿色外卖减塑场景形成正循环',
  ],
  7: [
    '6 组织用 6 个独立钱包地址：0xadmin / 0xmetro / 0xbus / 0xbike / 0xtakeout / 0xrecycle',
    'ERC20 两种发能量模式：① mint（所有者造币）② transfer（余额转账），实训用 mint 白名单更直观',
    'mintRole 白名单 = [ metro, bus, bike, takeout, recycle ] 共 5 个；admin 保留 owner 权限可增删白名单',
    '生产环境推荐「管理员 → 业务角色预拨押金 + transferFrom」模型，比 mint 更合规便于审计',
  ],
  8: [
    '联盟链「上线」有 4 件事要同时通过：① 共识节点在线 ② 6 钱包链上有余额 ③ 合约权限白名单 ④ 前端角色卡片放开',
    'GreenEnergy.mint → 6 角色（owner + 5 业务角色）可调用；PlantCertificate.mint → 仅 admin（防作弊）',
    'EcoBadge.mint → admin 发勋章，bike + admin 联合发骑行券（对应单车业务）',
    '6 角色验收通过 = Step 9/10 部署代币合约后，联盟运营模块 /eco 就可以完全放开使用',
  ],
  // Step 9-10 = 原 Step 5-6（顺延）
  9: [
    'GreenEnergy 是 ERC20 标准代币，构造函数仅需 initialSupply 参数，decimals=0（整数积分）',
    '部署交易 to 字段为空、data = 字节码 + 构造函数参数 ABI 编码；EVM 执行构造函数初始化状态',
    '合约地址 = keccak256(rlp([sender,nonce]))[12:] 后 20 字节，确定性生成',
    'Deployer 用 0xadmin（管理员身份部署），6 角色通过 mintRole 白名单获得发能量授权',
  ],
  10: [
    'name() / balanceOf() 是 view 函数，本地执行不消耗 Gas 不上链',
    'mint() / transfer() 是状态变更函数，广播交易、消耗 Gas、产生 Transfer 事件日志',
    '6 角色发放链路已打通：🚇地铁→alice+50；📦外卖→learner+10；♻️回收→learner+100',
    'Step 10 完成 → 进入绿色低碳联盟链（/eco）即可体验完整 6 角色运营闭环：发放→累积→兑换→挂牌→购买→下架',
  ],
}
const curKnowledge = computed(() => (cur.value ? KNOWLEDGE[cur.value.step] || [] : []))

/* ---------- 上一步 / 下一步 ---------- */
function goPrev() { active.value = Math.max(0, active.value - 1) }
function goNext() { active.value = Math.min(steps.value.length - 1, active.value + 1) }

/* ---------- 回退上一步 ---------- */
async function rollback() {
  if (!doneSteps.value.length) return
  const last = doneSteps.value[doneSteps.value.length - 1]
  try {
    await ElMessageBox.confirm(
      `确定回退「步骤 ${last}」吗？已完成标记会移除（链上数据不会回滚）。`,
      '回退步骤',
      { type: 'warning', confirmButtonText: '确认回退', cancelButtonText: '取消' },
    )
  } catch { return }
  doneSteps.value.pop()
  persistDone()
  // 同时移除该步骤的耗时
  if (stepDurationsRaw.value[last]) {
    delete stepDurationsRaw.value[last]
    persistDur()
  }
  // 跳到被回退那步
  const idx = steps.value.findIndex((s) => s.step === last)
  if (idx >= 0) active.value = idx
  ElMessage.success(`已回退步骤 ${last}`)
}

/* ---------- 重置全部（服务端 + 本地双清） ---------- */
async function resetAll() {
  if (!doneSteps.value.length) return
  try {
    await ElMessageBox.confirm(
      '确定重置整个搭链教程进度吗？所有步骤的完成状态与耗时都将清空（链上数据不会回滚）。',
      '重置进度',
      { type: 'warning', confirmButtonText: '确认重置', cancelButtonText: '取消' },
    )
  } catch { return }
  doneSteps.value = []
  stepDurationsRaw.value = {}
  persistDone()
  persistDur()
  try { await chainApi.resetProgress(app.currentWallet || '0xlearner') } catch {}
  active.value = 0
  ElMessage.success('进度已重置，从第 1 步重新开始')
}

/* ---------- 核心：执行当前步骤 ---------- */
async function exec() {
  if (!cur.value) return
  loading.value = true
  startTimer()
  try {
    const wallet = app.currentWallet || '0xlearner'
    const r: any = await chainApi.execStep(cur.value.step, wallet)
    term.writeln(`\x1b[36m┌─ 步骤 ${cur.value.step}: ${cur.value.title}\x1b[0m`)
    cur.value.commands.forEach((c: string) => term.writeln(`\x1b[32m$ ${c}\x1b[0m`))
    term.writeln('')
    // 输出真实结果，高亮关键信息
    const out = r.output || ''
    out.split('\n').forEach((line: string) => {
      if (line.includes('contract address') || line.includes('transaction hash') || line.includes('block number')) {
        term.writeln(`\x1b[33m${line}\x1b[0m`)
      } else if (line.includes('[完成]') || line.includes('返回:')) {
        term.writeln(`\x1b[32m${line}\x1b[0m`)
      } else {
        term.writeln(line)
      }
    })
    const elapsed = stopTimer(cur.value.step)
    term.writeln(`\x1b[36m└─────────── 耗时 ${fmtDuration(elapsed)} ──────────────\x1b[0m`)
    term.writeln('')
    // 以服务端 ok 为准；只要服务端说 done 才算完成（避免前端误判"已完成"，但后端进度没同步）
    const stepOk = !!r.ok
    if (!stepOk) {
      ElMessage.warning(`步骤 ${cur.value.step} 执行未成功，已记录但未标记完成。请按终端输出提示检查后再执行。`)
    }
    const wasNew = stepOk && !doneSteps.value.includes(cur.value.step)
    if (wasNew) {
      // 用新数组引用触发 el-steps / 进度环 / 计数器立即重渲染（避免 .push 不触发 diff 的滞后）
      doneSteps.value = [...doneSteps.value, cur.value.step]
      persistDone()
      try { app.confetti({ particleCount: 60, spread: 60, origin: { y: 0.55 }, ticks: 140 }) } catch {}
    }
    // 同步服务端进度：确保本地 doneSteps 与 chain_tutorial_progress 表取并集，
    // 换浏览器/换设备也能续学，且计数器立即反映最新服务端状态
    syncProgressFromServer()
    if (doneSteps.value.length === steps.value.length) {
      ElMessage({
        type: 'success',
        duration: 5500,
        message: '🎉 恭喜完成全部 10 步搭链教程！6 大联盟节点（管理员/地铁/公交/单车/外卖/回收）配置完成，前往绿色低碳联盟链开始完整运营体验吧',
      })
      try { app.confetti({ particleCount: 160, spread: 90, startVelocity: 50, origin: { y: 0.5 }, ticks: 220 }) } catch {}
    } else if (wasNew) {
      ElMessage.success(`步骤 ${cur.value.step} 完成 · 耗时 ${fmtDuration(elapsed)} · 真实链已写入 (${progressPct.value}%)`)
    } else {
      ElMessage.success(`重新执行完成 · 累计耗时 ${stepDurations.value[cur.value.step] || fmtDuration(elapsed)}`)
    }
    app.refreshStatus()
    // 自动跳到下一步（最后一步不跳）
    if (wasNew && active.value < steps.value.length - 1) {
      nextTick(() => { active.value = Math.min(steps.value.length - 1, active.value + 1) })
    }
  } finally {
    if (curStartTs.value) stopTimer(cur.value?.step || 0)
    loading.value = false
  }
}

/* ---------- 终端初始化 ---------- */
function initTerm() {
  term = new Terminal({
    theme: {
      background: '#070b16',
      foreground: '#d6e2ff',
      cursor: '#00e6c3',
      selectionBackground: '#1f2a44',
      green: '#00e6c3',
      yellow: '#ffcf4d',
      cyan: '#4d8dff',
    },
    fontFamily: "'JetBrains Mono', Consolas, monospace",
    fontSize: 13,
    cursorBlink: true,
  })
  fit = new FitAddon()
  term.loadAddon(fit)
  term.open(termRef.value!)
  fit.fit()
  term.writeln('\x1b[36m╔══════════════════════════════════════════════╗\x1b[0m')
  term.writeln('\x1b[36m║   FISCO 联盟链云桌面 · 真实 EVM 实训终端     ║\x1b[0m')
  term.writeln('\x1b[36m╚══════════════════════════════════════════════╝\x1b[0m')
  term.writeln('')
  term.writeln('提示：点击左侧「在真实链执行」按钮，每一步都会在真实链上执行并输出真实结果。')
  term.writeln('       （合约地址、交易哈希、Gas 消耗均为真实 EVM 返回）')
  if (Object.keys(stepDurationsRaw.value).length) {
    term.writeln(`\x1b[33m已记录 ${Object.keys(stepDurationsRaw.value).length} 步历史耗时，累计 ${totalDuration.value}\x1b[0m`)
  }
  term.writeln('')
  term.write('\x1b[32m$ \x1b[0m')

  // WebSocket
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  try {
    ws = new WebSocket(`${proto}://${location.host}/api/cloud/ws/terminal`)
    ws.onmessage = (e) => { term.write(e.data) }
  } catch {
    /* WebSocket 连接不阻塞核心功能（后端可能未启用） */
  }

  term.onData((data) => {
    if (data === '\r') {
      term.write('\r\n')
      try { ws?.send(curCmd.value) } catch {}
      curCmd.value = ''
      term.write('\x1b[32m$ \x1b[0m')
    } else if (data === '\u007f') {
      if (curCmd.value.length > 0) {
        curCmd.value = curCmd.value.slice(0, -1)
        term.write('\b \b')
      }
    } else {
      curCmd.value += data
      term.write(data)
    }
  })
}

/* ---------- 生命周期 ---------- */
onMounted(async () => {
  const wallet = app.currentWallet || '0xlearner'
  const r: any = await chainApi.tutorial(wallet)
  steps.value = r.steps
  // 服务端进度 → 合并到本地（换浏览器也能续学）
  await syncProgressFromServer()
  // 如果 localStorage 里有未完成的 timer，防止其永远挂着
  const pending = safeGet<number | null>(START_KEY, null)
  if (pending) safeSet(START_KEY, null)
  await nextTick()
  initTerm()
  window.addEventListener('resize', onResize)
})

onActivated(() => {
  app.refreshStatus()
  // 重新加载持久化数据，保证从其他页切回来时数据最新
  doneSteps.value = loadDoneSteps()
  stepDurationsRaw.value = loadDurations()
  syncProgressFromServer()
})

/* storage 事件：多标签页时互相通知 */
watch(() => app.chainHeight, () => { /* noop */ })

function onResize() { try { fit?.fit() } catch {} }

onBeforeUnmount(() => {
  ws?.close()
  term?.dispose()
  window.removeEventListener('resize', onResize)
})
</script>

<style scoped lang="scss">
.cloud { display: grid; grid-template-columns: 450px 1fr; gap: 14px; height: calc(100vh - 110px); }
.left { display: flex; flex-direction: column; gap: 14px; overflow-y: auto; min-width: 0; padding-right: 4px; }
.steps-card { flex-shrink: 0; min-width: 0; }

/* ---------- 进度头：环 + 信息 ---------- */
.progress-head {
  display: flex; gap: 16px; align-items: center; margin-bottom: 10px;
  padding: 10px; border-radius: 10px;
  background: linear-gradient(135deg, rgba(0,230,195,0.04), rgba(77,141,255,0.03));
  border: 1px solid rgba(255,255,255,0.04);
}
.ring-wrap { position: relative; width: 104px; height: 104px; flex-shrink: 0; }
.ring { width: 100%; height: 100%; }
.ring-inner {
  position: absolute; inset: 0;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
}
.ring-pct {
  font-size: 22px; font-weight: 800;
  background: var(--dq-grad-primary);
  -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent;
  font-family: var(--dq-mono);
  letter-spacing: -0.5px;
}
.ring-sub { font-size: 10px; color: var(--dq-text-dim); margin-top: 1px; letter-spacing: 0.5px; }

.ph-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.ph-row {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 12px;
  .ph-k { color: var(--dq-text-dim); }
  .ph-v { color: var(--dq-text); font-size: 12px; b { color: var(--dq-primary); font-size: 14px; } }
}
.ph-ops {
  display: flex; gap: 6px; margin-top: 6px; flex-wrap: wrap;
  .el-button { font-size: 11px !important; padding: 5px 10px !important; }
}

.progress-bar {
  height: 6px; background: var(--dq-bg-2); border-radius: 3px; overflow: hidden; margin-bottom: 6px;
  .pb-fill { height: 100%; background: var(--dq-grad-primary); border-radius: 3px; transition: width .4s; box-shadow: 0 0 8px var(--dq-primary-glow); }
}
.dq-steps { cursor: pointer; }
:deep(.el-steps) {
  .el-step { max-width: 100%; flex-basis: auto !important; }
  .el-step__main { padding-right: 6px; }
  .el-step__title { color: var(--dq-text-dim); word-break: break-word; line-height: 1.4; &.is-process, &.is-finish { color: var(--dq-primary); } }
  .el-step__description { color: var(--dq-text-dimmer); font-size: 12px; word-break: break-word; white-space: normal; line-height: 1.5; padding-right: 0; }
  .el-step__icon { flex-shrink: 0; }
}

/* ---------- 步骤详情 ---------- */
.step-detail {
  min-width: 0;
  .step-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
  .step-no { font-family: var(--dq-mono); font-size: 12px; color: var(--dq-primary); background: rgba(0,230,195,0.1); padding: 2px 8px; border-radius: 4px; flex-shrink: 0; }
  .step-title { font-size: 16px; font-weight: 600; color: var(--dq-text); }
  .step-duration, .step-done-at { margin-left: auto; font-size: 11px; gap: 4px; }
  .desc { color: var(--dq-text-dim); margin: 0 0 12px; line-height: 1.6; word-break: break-word; }
}
.section-label { font-size: 12px; color: var(--dq-text-dim); margin: 14px 0 8px; text-transform: uppercase; letter-spacing: 1px; }
.cmds { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; min-width: 0; }
.cmds :deep(.dq-cmd-line) { max-width: 100%; code { word-break: break-all; white-space: normal; } }
.ops { margin-top: 16px; display: flex; gap: 8px; align-items: center; }

/* ---------- 知识点卡片 ---------- */
.knowledge-box {
  margin-top: 14px;
  border: 1px solid rgba(255, 207, 77, 0.25);
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(255,207,77,0.06), rgba(255,207,77,0.01));
  overflow: hidden;
  transition: border-color .2s;
  &:hover { border-color: rgba(255, 207, 77, 0.4); }
}
.kb-head {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px dashed rgba(255,207,77,0.2);
}
.kb-icon { font-size: 14px; }
.kb-title { font-weight: 600; color: #e6c97a; font-size: 13px; }
.kb-toggle { margin-left: auto; color: var(--dq-text-dim) !important; padding: 2px !important; }
.kb-body { padding: 10px 12px; }
.kb-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }
.kb-list li {
  display: flex; gap: 8px; align-items: flex-start;
  font-size: 12.5px; color: var(--dq-text); line-height: 1.65;
  .kb-dot {
    flex-shrink: 0; margin-top: 6px;
    width: 5px; height: 5px; border-radius: 50%;
    background: var(--dq-warn); box-shadow: 0 0 4px rgba(255, 207, 77, 0.5);
  }
}

/* ---------- 终端卡片 ---------- */
.terminal-card { display: flex; flex-direction: column; min-width: 0; }
.dq-card-title { display: flex; align-items: center; }
.term-wrap {
  flex: 1; overflow: hidden;
  padding: 10px;
  background: var(--dq-bg);
  border-radius: 8px;
  border: 1px solid var(--dq-border);
  box-shadow: inset 0 2px 8px rgba(0,0,0,0.4);
  position: relative;
  &::before {
    content: '';
    position: absolute; top: 0; left: 0; right: 0;
    height: 22px;
    background: linear-gradient(180deg, rgba(14,20,36,0.95), rgba(14,20,36,0));
    pointer-events: none;
    z-index: 2;
  }
  &::after {
    content: '● ● ●  terminal@fisco-dev';
    position: absolute; top: 4px; left: 14px;
    font-size: 10px; color: var(--dq-text-dimmer);
    font-family: var(--dq-mono);
    z-index: 3;
    letter-spacing: 1px;
    opacity: 0.7;
  }
}
.term { height: 100%; padding-top: 24px; }
:deep(.xterm) { padding: 4px 8px; }
.term-foot {
  padding-top: 10px;
  display: flex; justify-content: space-between; align-items: center;
  .tf-hint { font-size: 11px; color: var(--dq-text-dimmer); }
  .tf-kw {
    display: flex; gap: 8px;
    span {
      font-family: var(--dq-mono); font-size: 10px;
      padding: 1px 6px; border-radius: 3px;
      color: var(--dq-text-dim);
      background: rgba(255,255,255,0.03);
      border: 1px solid var(--dq-border);
    }
  }
}

@media (max-width: 1180px) {
  .cloud { grid-template-columns: 1fr; height: auto; }
  .terminal-card { min-height: 480px; }
}
</style>
