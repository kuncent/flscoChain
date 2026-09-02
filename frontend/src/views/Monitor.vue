<template>
  <div class="monitor dq-enter-up">
    <div class="top dq-card">
      <div class="dq-card-title">合约调用监听器</div>
      <div class="sel">
        <el-select v-model="addr" filterable placeholder="选择合约地址" @change="load" style="width:420px">
          <el-option v-for="c in contracts" :key="c.address" :label="`${c.name} - ${c.address}`" :value="c.address" />
        </el-select>
        <el-button @click="load" :disabled="!addr">刷新</el-button>
      </div>
    </div>

    <template v-if="data">
      <div class="grid">
        <div class="dq-card stat">
          <div class="lbl">总调用次数</div>
          <div class="val">{{ data.total }}</div>
        </div>
        <div class="dq-card stat">
          <div class="lbl">方法数</div>
          <div class="val">{{ Object.keys(data.methods || {}).length }}</div>
        </div>
        <div class="dq-card stat">
          <div class="lbl">最近状态</div>
          <div class="val" style="color:var(--dq-success)">实时监听中</div>
        </div>
      </div>

      <div class="grid-2">
        <div class="dq-card">
          <div class="dq-card-title">方法调用分布</div>
          <v-chart class="chart" :option="methodOption" autoresize v-if="methodData.length" />
          <EmptyIllustration
            v-else
            type="contract"
            :hide-text="true"
            style="padding: 20px 0;"
          />
          <div v-if="!methodData.length" class="empty-tip">暂无方法调用，前往「接口调试」页调用合约方法</div>
        </div>
        <div class="dq-card">
          <div class="dq-card-title">最近调用记录</div>
          <el-table :data="data.recent" border size="small" max-height="320" v-if="data.recent?.length">
            <el-table-column prop="method" label="方法" min-width="120" />
            <el-table-column prop="caller" label="调用者" min-width="160">
              <template #default="{ row }"><span class="dq-mono dim">{{ short(row.caller) }}</span></template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }"><span class="dq-tag">{{ row.status }}</span></template>
            </el-table-column>
            <el-table-column prop="created_at" label="时间" width="170" />
          </el-table>
          <EmptyIllustration
            v-else
            type="explorer"
            :hide-text="true"
            style="padding: 20px 0;"
          />
          <div v-if="!data.recent?.length" class="empty-tip">暂无调用记录</div>
        </div>
      </div>
    </template>

    <div class="dq-card" style="margin-top:14px" v-else>
      <EmptyIllustration
        type="contract"
        title="选择合约开始监听"
        subtitle="选择上方已部署的合约，实时观察合约方法被调用的情况"
      />
    </div>

    <!-- 监管审计视角：全链只读聚合（绿色低碳联盟链） -->
    <div class="dq-card audit-card">
      <div class="dq-card-title">
        <span class="title-icon">🌐</span>
        监管审计视角 · 绿色低碳联盟链
        <span class="dq-tag info" style="margin-left: 8px">只读聚合 · 无副作用</span>
        <el-button size="small" style="margin-left: auto" :loading="auditLoading" @click="loadAudit">刷新</el-button>
      </div>

      <div class="grid" style="margin-top: 14px">
        <div class="dq-card stat">
          <div class="lbl">当前块高</div>
          <div class="val">{{ audit?.block_height ?? '-' }}</div>
          <div class="sub">get_chain_client 实时读取</div>
        </div>
        <div class="dq-card stat">
          <div class="lbl">合约调用总数</div>
          <div class="val">{{ audit?.calls?.total ?? 0 }}</div>
          <div class="sub">成功率 {{ audit?.calls?.success_rate ?? '0.0' }}%</div>
        </div>
        <div class="dq-card stat">
          <div class="lbl">异常调用</div>
          <div class="val" :class="{ bad: (audit?.abnormal_calls?.count ?? 0) > 0 }">
            {{ audit?.abnormal_calls?.count ?? 0 }}
          </div>
          <div class="sub">status ≠ success（reverted / 0 / failed）</div>
        </div>
        <div class="dq-card stat">
          <div class="lbl">绿色能量发放总量</div>
          <div class="val">{{ audit?.role_energy?.total_points ?? 0 }}</div>
          <div class="sub">共 {{ audit?.role_energy?.total_issue_count ?? 0 }} 次发放</div>
        </div>
      </div>

      <div class="grid-2" style="margin-top: 14px">
        <!-- 异常调用明细 -->
        <div class="dq-card">
          <div class="dq-card-title sub-title">异常调用明细（最近 20 条）</div>
          <el-table
            :data="audit?.abnormal_calls?.items || []"
            border size="small" max-height="320"
            v-if="audit?.abnormal_calls?.items?.length"
          >
            <el-table-column prop="method" label="方法" min-width="120" />
            <el-table-column prop="caller" label="调用者" min-width="140">
              <template #default="{ row }"><span class="dq-mono dim">{{ short(row.caller) }}</span></template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }"><span class="abn-tag">{{ row.status }}</span></template>
            </el-table-column>
            <el-table-column prop="created_at" label="时间" width="170" />
          </el-table>
          <div v-else class="empty-tip">暂无异常调用，链上运行健康</div>
        </div>

        <!-- 各角色能量发放对比 -->
        <div class="dq-card">
          <div class="dq-card-title sub-title">各角色绿色能量发放对比</div>
          <div v-if="roleEnergyBars.length" class="role-bars">
            <div class="rb-row" v-for="b in roleEnergyBars" :key="b.role_key">
              <span class="rb-name">{{ b.icon }} {{ b.role_name }}</span>
              <div class="rb-track">
                <div class="rb-fill" :style="{ width: b.percent + '%', background: b.color }"></div>
              </div>
              <span class="rb-val dq-mono">{{ b.total_points }}<em>（{{ b.issue_count }}次）</em></span>
            </div>
          </div>
          <div v-else class="empty-tip">暂无能量发放记录</div>
        </div>
      </div>
    </div>

    <!-- ==================== 任务 #22：运营沙盘 · 链上运维演练 ==================== -->
    <div class="dq-card sandbox-card">
      <div class="dq-card-title">
        <span class="title-icon">🛰️</span>
        运营沙盘 · 链上运维演练
        <span class="sb-lamp" :class="sbActive ? 'on' : 'off'"></span>
        <span class="sb-state">{{ sbActive ? `轮次 #${sbActive.id} 进行中` : '待命' }}</span>
        <el-button
          v-if="isOpsManager && sbActive"
          type="danger" size="small" style="margin-left:auto"
          :loading="sbBusy" @click="stopSbRound"
        >⏹ 一键停止</el-button>
      </div>

      <!-- 教师：场景管理 -->
      <div v-if="isOpsManager" class="sb-ctl">
        <div class="sb-ctl-row">
          <el-select v-model="sbForm.scenario_type" style="width:200px" size="small">
            <el-option v-for="t in SB_TYPES" :key="t.value" :label="`${t.icon} ${t.label}`" :value="t.value" />
          </el-select>
          <span class="sb-lbl">目标 TPS</span>
          <el-input-number v-model="sbForm.target_tps" :min="0.1" :max="5" :step="0.5" size="small" style="width:130px" />
          <span class="sb-lbl">时长(秒)</span>
          <el-input-number v-model="sbForm.duration_s" :min="10" :max="600" :step="30" size="small" style="width:130px" />
          <el-button type="primary" size="small" :loading="sbBusy" @click="createSbScenario">创建场景</el-button>
        </div>
        <el-table :data="sbScenarios" size="small" border max-height="220" v-if="sbScenarios.length" style="margin-top:10px">
          <el-table-column prop="title" label="场景" min-width="140" />
          <el-table-column label="故障类型" width="150">
            <template #default="{ row }"><span class="dq-tag warn">{{ sbTypeLabel(row.scenario_type) }}</span></template>
          </el-table-column>
          <el-table-column label="配置" min-width="160">
            <template #default="{ row }">
              <span class="dq-mono dim sb-cfg">TPS {{ row.config?.target_tps }} · {{ row.config?.duration_s }}s · 配额 {{ row.config?.quota }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }"><span class="dq-tag" :class="row.status === 'ready' ? 'ok' : ''">{{ row.status === 'ready' ? '待启动' : '已演练' }}</span></template>
          </el-table-column>
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-button size="small" type="primary" plain :disabled="!!sbActive" :loading="sbBusy" @click="startSbRound(row)">启动</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-else class="empty-tip">暂无场景：选择故障类型与目标 TPS 后点「创建场景」</div>
      </div>

      <template v-if="sbActive">
        <!-- 故障横幅 -->
        <div class="sb-fault" v-if="sbFaultText">⚠ {{ sbFaultText }}</div>

        <!-- KPI 记分板（订阅 sandbox_kpi 事件实时刷新） -->
        <div class="sb-board">
          <div class="sb-kpi">
            <div class="k">MTTD<em>故障→首次处置</em></div>
            <div class="v" :class="{ good: (sbKpis?.mttd_seconds ?? -1) >= 0 }">{{ fmtSec(sbKpis?.mttd_seconds) }}</div>
          </div>
          <div class="sb-kpi">
            <div class="k">MTTR<em>故障→对症恢复</em></div>
            <div class="v" :class="{ good: (sbKpis?.mttr_seconds ?? -1) >= 0 }">{{ fmtSec(sbKpis?.mttr_seconds) }}</div>
          </div>
          <div class="sb-kpi">
            <div class="k">处置率<em>对症动作覆盖</em></div>
            <div class="v" :class="{ good: (sbKpis?.handle_rate ?? 0) >= 100 }">{{ sbKpis?.handle_rate ?? 0 }}<small>%</small></div>
          </div>
          <div class="sb-kpi">
            <div class="k">交易成功率<em>合成负载 {{ sbKpis?.tx_succeeded ?? 0 }}/{{ sbKpis?.tx_attempted ?? 0 }}</em></div>
            <div class="v">{{ sbKpis?.success_rate ?? 100 }}<small>%</small></div>
          </div>
        </div>

        <!-- 处置动作提交 + 实时流水 -->
        <div class="sb-action-grid">
          <div class="dq-card sb-form">
            <div class="dq-card-title sub-title">提交处置动作</div>
            <div class="sb-form-row">
              <el-select v-model="sbAction.action_type" size="small" style="width:170px">
                <el-option v-for="a in sbActionOptions" :key="a.value" :label="a.label" :value="a.value" />
              </el-select>
              <el-input v-model="sbAction.description" size="small" placeholder="处置说明（可选）" maxlength="200" style="flex:1" />
              <el-button type="primary" size="small" :loading="sbActionBusy" @click="submitSbAction">提交</el-button>
            </div>
            <div class="sb-hint">对症动作：{{ (sbActive.resolution_actions || []).map((a: string) => sbActionLabel(a)).join('、') || '—' }}（命中即推进处置率 / 结算 MTTR）</div>
          </div>
          <div class="dq-card sb-feed">
            <div class="dq-card-title sub-title">处置流水</div>
            <div v-if="sbActions.length" class="sb-feed-list">
              <div class="sb-feed-item" v-for="(a, i) in sbActions" :key="i">
                <span class="t dq-mono">+{{ a.elapsed_s.toFixed(1) }}s</span>
                <span class="a">{{ a.action_label || sbActionLabel(a.action_type) }}</span>
                <span class="w">{{ a.user_name || a.user_id || '未知' }}</span>
                <span class="d" v-if="a.description">{{ a.description }}</span>
              </div>
            </div>
            <div v-else class="empty-tip">暂无处置动作，快定位故障并提交处置！</div>
          </div>
        </div>
      </template>
      <div v-else class="empty-tip" style="padding:16px 0">当前无进行中的演练轮次{{ isOpsManager ? '，可在上方创建场景并启动' : '，等待教师启动演练' }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onActivated, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart } from 'echarts/charts'
import { LegendComponent, TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { contractApi, monitorApi, ecoApi, sandboxApi } from '@/api'
// 任务 #21：SSE 推送触发刷新（与既有拉取逻辑叠加，不替换）
import { onBusEvent } from '@/api/events'
import { useAuthStore } from '@/stores/auth'
import EmptyIllustration from '@/components/EmptyIllustration.vue'

use([CanvasRenderer, PieChart, LegendComponent, TooltipComponent])

const route = useRoute()
const contracts = ref<any[]>([])
const addr = ref('')
const data = ref<any>(null)

/* ==================== 监管审计视角（全链只读聚合） ==================== */
const audit = ref<any>(null)
const auditLoading = ref(false)

/** 各角色能量发放对比条（按最大值归一化，空数据时安全返回空数组） */
const roleEnergyBars = computed(() => {
  const items: any[] = audit.value?.role_energy?.items || []
  const max = Math.max(...items.map((i: any) => Number(i.total_points) || 0), 1)
  return items.map((i: any) => ({
    ...i,
    percent: Math.round(((Number(i.total_points) || 0) / max) * 100),
  }))
})

const loadAudit = async () => {
  auditLoading.value = true
  try {
    audit.value = await ecoApi.auditOverview()
  } catch {
    audit.value = null
  } finally {
    auditLoading.value = false
  }
}

const methodData = computed(() => Object.entries(data.value?.methods || {}).map(([name, count]) => ({ name, value: count })))
const methodOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0, textStyle: { color: '#7b8aab' } },
  series: [{ type: 'pie', radius: ['40%', '70%'], data: methodData.value, itemStyle: { borderColor: '#151c2c', borderWidth: 2 }, label: { color: '#d6e2ff' } }],
}))

const short = (h: string) => h ? h.slice(0, 14) + '...' : ''

const load = async () => {
  if (!addr.value) return
  data.value = await monitorApi.monitor(addr.value)
}

const loadAll = async () => {
  contracts.value = (await contractApi.deployed()) as any
  loadAudit()
  loadSandbox()
  if (route.query.addr) {
    addr.value = route.query.addr as string
    await load()
  }
}

/* ==================== 任务 #22：运营沙盘 ==================== */
const auth = useAuthStore()
/** 教师/管理员：可见场景管理与启停；学生仅可见记分板与提交处置 */
const isOpsManager = computed(() => auth.isTeacher || auth.isAdmin)

const SB_TYPES = [
  { value: 'node_down', label: '节点宕机', icon: '💥' },
  { value: 'consensus_stall', label: '共识停滞', icon: '⏸️' },
  { value: 'replay_attack', label: '凭证重放攻击', icon: '🎭' },
  { value: 'gas_spike', label: 'gas 飙升', icon: '⛽' },
]
const SB_ACTION_LABELS: Record<string, string> = {
  restart_node: '重启节点',
  audit_replay: '重放审计',
  fix_redeploy: '修复重部署',
  throttle_tx: '交易限流',
}
/** 各场景的对症处置动作（与后端 RESOLUTION_ACTIONS 一致） */
const SB_RESOLUTION: Record<string, string[]> = {
  node_down: ['restart_node'],
  consensus_stall: ['restart_node', 'fix_redeploy'],
  replay_attack: ['audit_replay'],
  gas_spike: ['fix_redeploy', 'throttle_tx'],
}

const sb = ref<any>(null)
const sbScenarios = ref<any[]>([])
const sbBusy = ref(false)
const sbActionBusy = ref(false)
const sbForm = reactive({ scenario_type: 'node_down', target_tps: 1, duration_s: 120 })
const sbAction = reactive({ action_type: 'restart_node', description: '' })

const sbActive = computed<any>(() => sb.value?.round || null)
const sbKpis = computed<any>(() => sb.value?.kpis || null)
const sbActions = computed<any[]>(() => sb.value?.actions || [])
const sbActionOptions = computed(() => {
  const st = sbActive.value?.scenario_type || sbForm.scenario_type
  return (SB_RESOLUTION[st] || Object.keys(SB_ACTION_LABELS)).map((v) => ({ value: v, label: SB_ACTION_LABELS[v] || v }))
})
const sbFaultText = computed(() => {
  const r = sbActive.value
  if (!r) return ''
  const f = sb.value?.fault || {}
  switch (r.scenario_type) {
    case 'node_down': {
      const idx = f.node_fault?.node_index ?? 0
      return `模拟节点 node${idx} 已离线（内存标记）——请重启节点恢复服务`
    }
    case 'consensus_stall':
      return f.consensus_stalled ? '班级链出块已暂停（共识停滞）——请重启节点或修复重部署' : '共识停滞演练进行中'
    case 'replay_attack':
      return '检测到重复 proof_no 的可疑能量记录——请审计重放凭证'
    case 'gas_spike':
      return '大量低价值交易抬高 gas 均值——请修复重部署或限流'
    default:
      return ''
  }
})

const sbTypeLabel = (t: string) => SB_TYPES.find((x) => x.value === t)?.label || t
const sbActionLabel = (a: string) => SB_ACTION_LABELS[a] || a
const fmtSec = (v: number | null | undefined) => (v == null || v < 0) ? '—' : `${v.toFixed(1)}s`

const loadSandbox = async () => {
  try {
    sb.value = await sandboxApi.activeRound()
  } catch {
    sb.value = null
  }
  // 默认选中当前场景的首个对症动作，降低学生操作成本
  const opts = sbActionOptions.value
  if (opts.length && !opts.some((o) => o.value === sbAction.action_type)) {
    sbAction.action_type = opts[0].value
  }
}

const loadSbScenarios = async () => {
  if (!isOpsManager.value) return
  try {
    const r: any = await sandboxApi.scenarios()
    sbScenarios.value = r?.items || []
  } catch {
    sbScenarios.value = []
  }
}

const createSbScenario = async () => {
  sbBusy.value = true
  try {
    await sandboxApi.createScenario({
      scenario_type: sbForm.scenario_type,
      target_tps: sbForm.target_tps,
      duration_s: sbForm.duration_s,
    })
    ElMessage.success('场景已创建，可点「启动」开始演练')
    await loadSbScenarios()
  } catch { /* http 拦截器已提示 */ } finally {
    sbBusy.value = false
  }
}

const startSbRound = async (row: any) => {
  sbBusy.value = true
  try {
    await sandboxApi.startRound(row.id)
    ElMessage.success('演练已启动，故障已注入')
    await Promise.all([loadSandbox(), loadSbScenarios()])
  } catch { /* ignore */ } finally {
    sbBusy.value = false
  }
}

const stopSbRound = async () => {
  if (!sbActive.value) return
  sbBusy.value = true
  try {
    await sandboxApi.stopRound(sbActive.value.id)
    ElMessage.success('演练已停止，故障态已恢复')
    await Promise.all([loadSandbox(), loadSbScenarios()])
  } catch { /* ignore */ } finally {
    sbBusy.value = false
  }
}

const submitSbAction = async () => {
  if (!sbActive.value) return
  sbActionBusy.value = true
  try {
    const res: any = await sandboxApi.submitAction(sbActive.value.id, {
      action_type: sbAction.action_type,
      description: sbAction.description,
    })
    if (res?.kpis) sb.value = { ...sb.value, kpis: res.kpis }
    sbAction.description = ''
    ElMessage.success('处置动作已记录')
    await loadSandbox()
  } catch { /* ignore */ } finally {
    sbActionBusy.value = false
  }
}

/* 首次进入触发 onMounted，KeepAlive 缓存后再次进入触发 onActivated，两者都执行加载 */
onMounted(loadAll)
onActivated(loadAll)

/* ---------- 任务 #21：SSE 推送触发刷新 ----------
 * 合约部署成功 → 全量重载；能量发放成功 → 仅刷审计聚合（保留既有拉取，纯叠加） */
const offPushDeploy = onBusEvent('deployed', () => { loadAll() })
const offPushEnergy = onBusEvent('energy_issued', () => { loadAudit() })
/* ---------- 任务 #22：沙盘事件实时记分板 ---------- */
const offSbKpi = onBusEvent('sandbox_kpi', (ev) => {
  if (sbActive.value && ev?.payload?.round_id === sbActive.value.id && ev?.payload?.kpis) {
    sb.value = { ...sb.value, kpis: ev.payload.kpis }
  }
})
const offSbAction = onBusEvent('sandbox_action', () => { loadSandbox() })
const offSbFault = onBusEvent('sandbox_fault_injected', () => { loadSandbox(); loadSbScenarios() })
const offSbStopped = onBusEvent('sandbox_round_stopped', () => { loadSandbox(); loadSbScenarios() })
onMounted(loadSbScenarios)
onActivated(loadSbScenarios)
onUnmounted(() => {
  offPushDeploy()
  offPushEnergy()
  offSbKpi()
  offSbAction()
  offSbFault()
  offSbStopped()
})
</script>

<style scoped lang="scss">
.sel { display: flex; gap: 10px; }
.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin: 14px 0; }
.stat { .lbl { color: var(--dq-text-dim); font-size: 13px; } .val { font-size: 28px; font-weight: 700; color: var(--dq-primary); margin-top: 6px; font-family: var(--dq-mono); } }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.chart { height: 320px; }
.dim { color: var(--dq-text-dim); }
.empty-tip { font-size: 12px; color: var(--dq-text-dim); text-align: center; padding: 0 12px 10px; }

/* ---- 监管审计视角 ---- */
.audit-card {
  .grid { grid-template-columns: repeat(4, 1fr); margin-bottom: 0; }
  .stat .val {
    &.bad { color: #ff5c7a; }
  }
  .sub { font-size: 11px; color: var(--dq-text-dim); margin-top: 4px; }
  .abn-tag {
    font-family: var(--dq-mono);
    font-size: 11px;
    color: #ff5c7a;
    background: rgba(255, 92, 122, 0.08);
    border: 1px solid rgba(255, 92, 122, 0.35);
    padding: 1px 8px;
    border-radius: 3px;
  }
}
@media (max-width: 1180px) {
  .audit-card .grid { grid-template-columns: repeat(2, 1fr); }
}
.role-bars {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 4px 0 8px;
  .rb-row {
    display: grid;
    grid-template-columns: 130px 1fr 120px;
    align-items: center;
    gap: 10px;
  }
  .rb-name { font-size: 12px; color: var(--dq-text); }
  .rb-track {
    height: 10px;
    border-radius: 5px;
    background: var(--dq-bg-2);
    border: 1px solid var(--dq-border);
    overflow: hidden;
  }
  .rb-fill {
    height: 100%;
    border-radius: 5px;
    min-width: 2px;
    transition: width .6s ease;
  }
  .rb-val {
    font-size: 12px;
    color: var(--dq-text-dim);
    text-align: right;
    em { font-style: normal; font-size: 10px; }
  }
}

/* ==================== 任务 #22：运营沙盘（运维指挥舱风格） ==================== */
.sandbox-card {
  margin-top: 14px;
  border: 1px solid var(--dq-border);
  background:
    linear-gradient(180deg, rgba(0, 230, 195, 0.03), transparent 120px),
    var(--dq-bg-1, #151c2c);

  .sb-lamp {
    width: 9px; height: 9px; border-radius: 50%;
    margin-left: 10px; display: inline-block;
    &.on { background: #00e6c3; box-shadow: 0 0 8px rgba(0, 230, 195, .9); animation: dq-sb-blink 1.2s ease-in-out infinite; }
    &.off { background: #3a4763; }
  }
  .sb-state { font-size: 12px; color: var(--dq-text-dim); margin-left: 8px; font-family: var(--dq-mono); }

  .sb-ctl {
    margin-top: 12px;
    padding: 12px;
    border: 1px dashed var(--dq-border);
    border-radius: 6px;
    .sb-ctl-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .sb-lbl { font-size: 12px; color: var(--dq-text-dim); }
    .sb-cfg { font-size: 11px; }
  }

  .sb-fault {
    margin-top: 12px;
    padding: 9px 14px;
    font-size: 12.5px;
    color: #ffb454;
    background: rgba(255, 180, 84, 0.07);
    border: 1px solid rgba(255, 180, 84, 0.35);
    border-left: 3px solid #ffb454;
    border-radius: 4px;
    letter-spacing: .3px;
  }

  .sb-board {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin-top: 12px;
  }
  .sb-kpi {
    position: relative;
    padding: 14px 14px 12px;
    border: 1px solid var(--dq-border);
    border-radius: 6px;
    background: var(--dq-bg-2, #101624);
    overflow: hidden;
    &::before {
      content: ''; position: absolute; inset: 0 0 auto 0; height: 2px;
      background: linear-gradient(90deg, transparent, rgba(0, 230, 195, .55), transparent);
    }
    .k {
      font-size: 12px; color: var(--dq-text);
      display: flex; align-items: baseline; gap: 6px;
      em { font-style: normal; font-size: 10px; color: var(--dq-text-dim); }
    }
    .v {
      margin-top: 8px;
      font-family: var(--dq-mono);
      font-size: 26px; font-weight: 700;
      color: var(--dq-text-dim);
      transition: color .4s ease;
      small { font-size: 13px; margin-left: 2px; color: var(--dq-text-dim); }
      &.good { color: #00e6c3; text-shadow: 0 0 14px rgba(0, 230, 195, .35); }
    }
  }

  .sb-action-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px;
    .dq-card { margin: 0; }
  }
  .sb-form-row { display: flex; gap: 8px; margin-top: 10px; }
  .sb-hint { font-size: 11px; color: var(--dq-text-dim); margin-top: 8px; }
  .sb-feed-list {
    margin-top: 8px; max-height: 150px; overflow: auto;
    display: flex; flex-direction: column; gap: 6px;
  }
  .sb-feed-item {
    display: flex; align-items: center; gap: 8px;
    font-size: 12px; padding: 6px 8px;
    border: 1px solid var(--dq-border); border-radius: 4px;
    background: var(--dq-bg-2, #101624);
    .t { color: #00e6c3; min-width: 58px; }
    .a { color: var(--dq-text); font-weight: 600; }
    .w { color: var(--dq-text-dim); }
    .d { color: var(--dq-text-dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  }
}
@keyframes dq-sb-blink { 0%, 100% { opacity: 1; } 50% { opacity: .35; } }
@media (max-width: 1180px) {
  .sandbox-card .sb-board { grid-template-columns: repeat(2, 1fr); }
  .sandbox-card .sb-action-grid { grid-template-columns: 1fr; }
}
</style>
