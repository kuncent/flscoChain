<template>
  <div class="grades dq-enter-up">
    <!-- 顶部说明 + 操作 -->
    <section class="dq-card hero">
      <div class="hero-left">
        <div class="hero-title">
          <span class="g-icon">📊</span>
          学生成绩管理
          <span class="dq-tag warn">教师专属</span>
          <span class="dq-live"><span class="dot"></span>已登录 · {{ auth.roleName }}</span>
        </div>
        <div class="hero-sub">
          当前教师：<b>{{ auth.displayName || '—' }}</b>
          · 成绩体系形成闭环：平台自动采集学生链上活动 → 计算实训成绩；教师录入评价分 → 合成综合成绩。
        </div>
      </div>
      <div class="hero-right">
        <el-button type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>&nbsp;新增成绩
        </el-button>
        <el-button type="success" plain @click="onRefreshTraining" :loading="refreshing" :disabled="!rows.length">
          <el-icon><Refresh /></el-icon>&nbsp;刷新实训成绩
        </el-button>
        <el-button @click="loadAll" :loading="loading">
          <el-icon><Search /></el-icon>&nbsp;查询
        </el-button>
      </div>
    </section>

    <!-- 闭环说明 -->
    <section class="dq-card loop-card">
      <div class="loop-flow">
        <div class="loop-step">
          <div class="ls-icon">⛓️</div>
          <div class="ls-title">链上活动</div>
          <div class="ls-sub">学生完成 4 大实训</div>
        </div>
        <div class="loop-arrow">→</div>
        <div class="loop-step">
          <div class="ls-icon accent">⚙️</div>
          <div class="ls-title">实训成绩</div>
          <div class="ls-sub">系统自动按 4 维加权</div>
        </div>
        <div class="loop-arrow">→</div>
        <div class="loop-step">
          <div class="ls-icon info">✍️</div>
          <div class="ls-title">教师评分</div>
          <div class="ls-sub">实训报告 / 课堂表现</div>
        </div>
        <div class="loop-arrow">→</div>
        <div class="loop-step">
          <div class="ls-icon success">🎯</div>
          <div class="ls-title">综合成绩</div>
          <div class="ls-sub">实训 60% + 教师 40%</div>
        </div>
      </div>
    </section>

    <!-- 课程聚合统计 -->
    <section class="dq-card stats-card" v-if="stats.length">
      <div class="dq-card-title">课程成绩统计</div>
      <div class="stats-grid">
        <div class="stat-item" v-for="s in stats" :key="s.course">
          <div class="stat-course">{{ s.course }}<span class="stat-cnt">{{ s.cnt }} 人</span></div>
          <div class="stat-row">
            <span class="sk">实训均分</span><span class="sv accent">{{ s.avg_training ?? '—' }}</span>
          </div>
          <div class="stat-row">
            <span class="sk">教师均分</span><span class="sv">{{ s.avg_manual ?? '—' }}</span>
          </div>
          <div class="stat-row highlight">
            <span class="sk">综合均分</span><span class="sv success">{{ s.avg_final ?? '—' }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 筛选 -->
    <section class="dq-card filter-card">
      <el-form :inline="true" size="small" :model="filter">
        <el-form-item label="学号">
          <el-input v-model="filter.student_id" placeholder="精确学号" clearable @keyup.enter="loadAll" />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="filter.student_name" placeholder="模糊查询" clearable @keyup.enter="loadAll" />
        </el-form-item>
        <el-form-item label="课程">
          <el-input v-model="filter.course" placeholder="模糊查询" clearable @keyup.enter="loadAll" />
        </el-form-item>
        <el-form-item label="班级">
          <el-input v-model="filter.class_id" placeholder="班级 ID" clearable @keyup.enter="loadAll" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadAll" :loading="loading">
            <el-icon><Search /></el-icon>&nbsp;查询
          </el-button>
          <el-button @click="resetFilter">重置</el-button>
        </el-form-item>
      </el-form>
    </section>

    <!-- 成绩列表 -->
    <section class="dq-card list-card">
      <div class="dq-card-title">
        成绩列表
        <span class="dq-tag" style="margin-left:8px">共 {{ rows.length }} 条</span>
      </div>
      <el-table :data="rows" v-loading="loading" stripe size="default" empty-text="暂无成绩记录，点击右上「新增成绩」录入">
        <el-table-column type="index" label="#" width="56" />
        <el-table-column prop="student_id" label="学号" min-width="120" />
        <el-table-column prop="student_name" label="姓名" min-width="90" />
        <el-table-column prop="course" label="课程" min-width="150" />
        <!-- 实训成绩（带 4 维明细 popover）-->
        <el-table-column label="实训成绩" width="130" align="center">
          <template #default="{ row }">
            <el-popover trigger="hover" placement="bottom" :width="320" popper-class="training-pop">
              <template #reference>
                <span class="score-cell training" :class="scoreClass(row.training_score)">
                  {{ fmtScore(row.training_score) }}
                  <el-icon class="cell-info"><InfoFilled /></el-icon>
                </span>
              </template>
              <div class="tp-title">实训成绩明细</div>
              <div class="tp-sub" v-if="row.wallet">钱包：{{ shortAddr(row.wallet) }}</div>
              <div class="tp-sub no-wallet" v-else>未绑定钱包（实训成绩为 0）</div>
              <div class="tp-row" v-for="d in detailRows(row.training_detail)" :key="d.key">
                <div class="tp-row-head">
                  <span class="tp-name">{{ d.name }}</span>
                  <span class="tp-score">{{ d.score }} <small>× {{ d.weight }}</small></span>
                </div>
                <el-progress :percentage="d.score" :stroke-width="6" :color="progColor(d.score)" :show-text="false" />
                <div class="tp-metrics">
                  <span v-for="(v, k) in d.metrics" :key="k" class="tp-metric">
                    <span class="mk">{{ metricLabel(String(k)) }}</span><span class="mv">{{ v }}</span>
                  </span>
                </div>
              </div>
              <div class="tp-foot">合计：{{ fmtScore(row.training_score) }}</div>
            </el-popover>
          </template>
        </el-table-column>
        <!-- 教师评分 -->
        <el-table-column label="教师评分" width="100" align="center">
          <template #default="{ row }">
            <span class="score-cell manual" :class="scoreClass(row.score)">{{ fmtScore(row.score) }}</span>
          </template>
        </el-table-column>
        <!-- 综合成绩（高亮主列）-->
        <el-table-column label="综合成绩" width="120" align="center">
          <template #default="{ row }">
            <span class="score-cell final" :class="scoreClass(row.final_score)">{{ fmtScore(row.final_score) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="class_id" label="班级" width="100" />
        <el-table-column prop="teacher_name" label="录入教师" min-width="90" />
        <el-table-column prop="remark" label="备注" min-width="140" show-overflow-tooltip />
        <el-table-column prop="updated_at" label="更新时间" min-width="150">
          <template #default="{ row }">{{ fmt(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- 新增 / 编辑 对话框 -->
    <el-dialog v-model="dlg.visible" :title="dlg.isEdit ? '编辑成绩' : '新增成绩'" width="560px" align-center>
      <el-form ref="dlgFormRef" :model="dlg.form" :rules="dlgRules" label-width="92px" size="default">
        <el-form-item label="学号" prop="student_id">
          <el-input v-model="dlg.form.student_id" placeholder="学生学号" :disabled="dlg.isEdit" />
        </el-form-item>
        <el-form-item label="姓名" prop="student_name">
          <el-input v-model="dlg.form.student_name" placeholder="学生姓名" />
        </el-form-item>
        <el-form-item label="课程" prop="course">
          <el-input v-model="dlg.form.course" placeholder="课程名称（如：联盟链实训）" :disabled="dlg.isEdit" />
        </el-form-item>
        <el-form-item label="钱包地址">
          <el-input v-model="dlg.form.wallet" placeholder="0x... 学生链上钱包（用于自动算实训成绩）" clearable>
            <template #append>
              <el-button :loading="previewLoading" @click="onPreviewTraining">预览实训成绩</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="教师评分" prop="score">
          <el-input-number v-model="dlg.form.score" :min="0" :max="100" :step="0.5" :precision="1" controls-position="right" style="width:100%" />
        </el-form-item>
        <!-- 预览结果 -->
        <div class="preview-box" v-if="preview">
          <div class="pv-title">预览成绩</div>
          <div class="pv-row"><span class="pv-k">实训成绩</span><span class="pv-v accent">{{ fmtScore(preview.training_score) }}</span></div>
          <div class="pv-row"><span class="pv-k">教师评分</span><span class="pv-v">{{ fmtScore(dlg.form.score) }}</span></div>
          <div class="pv-row highlight"><span class="pv-k">综合成绩</span><span class="pv-v success">{{ fmtScore(preview.final_score) }}</span></div>
        </div>
        <el-form-item label="班级 ID">
          <el-input v-model="dlg.form.class_id" placeholder="可选" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="dlg.form.remark" type="textarea" :rows="2" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg.visible = false">取消</el-button>
        <el-button type="primary" :loading="dlg.saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Plus, Refresh, Search, InfoFilled } from '@element-plus/icons-vue'
import { gradesApi } from '@/api'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const loading = ref(false)
const refreshing = ref(false)
const rows = ref<any[]>([])
const stats = ref<any[]>([])

const filter = reactive({
  student_id: '',
  student_name: '',
  course: '',
  class_id: '',
})

async function loadAll() {
  loading.value = true
  try {
    const params: any = {}
    if (filter.student_id) params.student_id = filter.student_id
    if (filter.student_name) params.student_name = filter.student_name
    if (filter.course) params.course = filter.course
    if (filter.class_id) params.class_id = filter.class_id
    const [listRes, statsRes] = await Promise.all([
      gradesApi.list(params),
      gradesApi.stats(),
    ])
    rows.value = listRes?.items || []
    stats.value = statsRes?.items || []
  } finally {
    loading.value = false
  }
}

function resetFilter() {
  filter.student_id = ''
  filter.student_name = ''
  filter.course = ''
  filter.class_id = ''
  loadAll()
}

/* ---------- 实训明细转可读结构 ---------- */
const _DETAIL_META: Record<string, { name: string; metrics: Record<string, string> }> = {
  chain_setup:  { name: '链搭建',     metrics: { ide_open_builtin: '打开内置合约', ide_save_project: '保存工程' } },
  contract_dev: { name: '合约开发',   metrics: { contract_compile_ok: '编译成功', deployed_contracts: '已部署合约' } },
  chain_verify: { name: '链上验证',   metrics: { interface_invoke: '接口调用', contract_calls: '合约调用', transactions: '链上交易' } },
  alliance_gov: { name: '联盟治理',   metrics: { eco_role_switch: '角色切换', nft_mint: 'NFT 铸造', nft_trade: 'NFT 交易', erc20_transfer: 'ERC20 转账', report_view: '报告查看' } },
}
function detailRows(detail: any) {
  if (!detail || typeof detail !== 'object') return []
  return Object.entries(detail).map(([k, v]: [string, any]) => {
    const meta = _DETAIL_META[k] || { name: k, metrics: {} }
    return {
      key: k,
      name: meta.name,
      score: Number(v?.score ?? 0),
      weight: v?.weight ?? 0,
      metrics: v?.metrics || {},
    }
  })
}
function metricLabel(k: string): string {
  for (const meta of Object.values(_DETAIL_META)) {
    if (meta.metrics[k]) return meta.metrics[k]
  }
  return k
}
function shortAddr(a: string): string {
  if (!a) return '—'
  return a.length > 14 ? `${a.slice(0, 6)}…${a.slice(-4)}` : a
}

/* ---------- 新增 / 编辑 ---------- */
const dlgFormRef = ref<FormInstance>()
const dlg = reactive({
  visible: false,
  isEdit: false,
  saving: false,
  form: {
    student_id: '',
    student_name: '',
    course: '',
    score: 80,
    wallet: '',
    class_id: '',
    remark: '',
  },
})
const dlgRules: FormRules = {
  student_id: [{ required: true, message: '请输入学号', trigger: 'blur' }],
  student_name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  course: [{ required: true, message: '请输入课程名称', trigger: 'blur' }],
  score: [{ required: true, message: '请输入教师评分', trigger: 'blur' }],
}

function openCreate() {
  dlg.isEdit = false
  dlg.form = { student_id: '', student_name: '', course: '', score: 80, wallet: '', class_id: '', remark: '' }
  preview.value = null
  dlg.visible = true
}

function openEdit(row: any) {
  dlg.isEdit = true
  dlg.form = {
    student_id: row.student_id,
    student_name: row.student_name,
    course: row.course,
    score: Number(row.score),
    wallet: row.wallet || '',
    class_id: row.class_id || '',
    remark: row.remark || '',
  }
  preview.value = null
  dlg.visible = true
}

/* ---------- 实训成绩预览 ---------- */
const preview = ref<any>(null)
const previewLoading = ref(false)
async function onPreviewTraining() {
  if (!dlg.form.wallet || !dlg.form.wallet.trim()) {
    ElMessage.warning('请先填写学生钱包地址')
    return
  }
  previewLoading.value = true
  try {
    preview.value = await gradesApi.computeTraining({
      wallet: dlg.form.wallet.trim(),
      manual_score: dlg.form.score,
    })
  } finally {
    previewLoading.value = false
  }
}

async function onSave() {
  if (!dlgFormRef.value) return
  const valid = await dlgFormRef.value.validate().catch(() => false)
  if (!valid) return
  dlg.saving = true
  try {
    await gradesApi.upsert({
      student_id: dlg.form.student_id.trim(),
      student_name: dlg.form.student_name.trim(),
      course: dlg.form.course.trim(),
      score: dlg.form.score,
      wallet: dlg.form.wallet.trim(),
      class_id: dlg.form.class_id,
      remark: dlg.form.remark,
    })
    ElMessage.success(dlg.isEdit ? '成绩已更新' : '成绩已录入')
    dlg.visible = false
    await loadAll()
  } finally {
    dlg.saving = false
  }
}

async function onDelete(row: any) {
  try {
    await ElMessageBox.confirm(
      `确认删除「${row.student_name} · ${row.course}」成绩记录？`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch { return }
  await gradesApi.remove(row.id)
  ElMessage.success('已删除')
  await loadAll()
}

/* ---------- 批量刷新实训成绩（闭环数据再同步） ---------- */
async function onRefreshTraining() {
  try {
    await ElMessageBox.confirm(
      '将根据所有学生钱包的最新链上活动数据，重新计算实训成绩与综合成绩，是否继续？',
      '刷新实训成绩',
      { type: 'info', confirmButtonText: '开始刷新', cancelButtonText: '取消' }
    )
  } catch { return }
  refreshing.value = true
  try {
    const res: any = await gradesApi.refreshTraining()
    ElMessage.success(`已刷新 ${res.refreshed} 条记录的实训成绩`)
    await loadAll()
  } finally {
    refreshing.value = false
  }
}

/* ---------- 工具 ---------- */
function scoreClass(s: number) {
  if (s >= 90) return 'excellent'
  if (s >= 80) return 'good'
  if (s >= 60) return 'pass'
  return 'fail'
}
function progColor(s: number) {
  if (s >= 90) return '#2dd4bf'
  if (s >= 80) return '#00e6c3'
  if (s >= 60) return '#4d8dff'
  return '#ff5470'
}
function fmtScore(s: any): string {
  if (s === null || s === undefined) return '—'
  return Number(s).toFixed(1)
}
function fmt(ts: any): string {
  if (!ts) return '—'
  try {
    const d = new Date(ts.endsWith('Z') ? ts : ts.replace(' ', 'T'))
    if (isNaN(d.getTime())) return String(ts)
    const p = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
  } catch {
    return String(ts)
  }
}

onMounted(() => {
  loadAll()
})
</script>

<style scoped lang="scss">
.grades { display: flex; flex-direction: column; gap: 14px; }

.hero {
  display: flex; align-items: center; justify-content: space-between;
  padding: 18px 22px;
  background:
    linear-gradient(135deg, rgba(0,230,195,0.08) 0%, rgba(77,141,255,0.06) 100%),
    var(--dq-grad-panel);
  .hero-title {
    display: flex; align-items: center; gap: 10px;
    font-size: 18px; font-weight: 700; color: var(--dq-text);
    .g-icon { font-size: 22px; }
  }
  .hero-sub { margin-top: 8px; font-size: 12px; color: var(--dq-text-dim); }
  .hero-right { display: flex; gap: 8px; flex-shrink: 0; }
}

/* 闭环流程图 */
.loop-card { padding: 14px 18px; }
.loop-flow {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
}
.loop-step {
  flex: 1; min-width: 130px;
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: 10px 8px;
  border-radius: 10px;
  background: rgba(7, 11, 22, 0.5);
  border: 1px solid var(--dq-border);
  transition: all .2s;
  &:hover {
    border-color: var(--dq-border-2);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0,230,195,0.08);
  }
  .ls-icon {
    width: 32px; height: 32px; border-radius: 50%;
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 16px;
    background: rgba(0,230,195,0.08); border: 1px solid rgba(0,230,195,0.25);
    &.accent { background: rgba(0,230,195,0.16); border-color: var(--dq-primary); }
    &.info   { background: rgba(77,141,255,0.12); border-color: rgba(77,141,255,0.4); }
    &.success{ background: rgba(45,212,191,0.14); border-color: rgba(45,212,191,0.4); }
  }
  .ls-title { font-size: 13px; font-weight: 700; color: var(--dq-text); }
  .ls-sub   { font-size: 11px; color: var(--dq-text-dimmer); }
}
.loop-arrow {
  color: var(--dq-primary); font-size: 18px; font-weight: 700;
  animation: arrow-pulse 1.8s ease-in-out infinite;
  flex-shrink: 0;
}
@keyframes arrow-pulse {
  0%, 100% { opacity: 0.4; transform: translateX(0); }
  50% { opacity: 1; transform: translateX(3px); }
}

.stats-card { padding: 16px 18px; }
.stats-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px; margin-top: 8px;
}
.stat-item {
  padding: 12px 14px; border-radius: 10px;
  background: rgba(7, 11, 22, 0.5);
  border: 1px solid var(--dq-border);
  .stat-course {
    font-size: 13px; font-weight: 700; color: var(--dq-text);
    margin-bottom: 8px; letter-spacing: 0.3px;
    border-bottom: 1px dashed rgba(31,42,68,0.8); padding-bottom: 6px;
    display: flex; justify-content: space-between; align-items: center;
    .stat-cnt { font-size: 11px; color: var(--dq-text-dimmer); font-weight: 400; }
  }
  .stat-row {
    display: flex; justify-content: space-between; align-items: center;
    font-size: 12px; padding: 3px 0;
    .sk { color: var(--dq-text-dimmer); }
    .sv { color: var(--dq-text); font-family: var(--dq-mono); font-weight: 600; }
    .sv.accent { color: var(--dq-primary); }
    .sv.success { color: var(--dq-success); }
    &.highlight .sv { font-size: 14px; }
  }
}

.filter-card { padding: 14px 18px 0; }
.filter-card :deep(.el-form-item) { margin-bottom: 14px; }

.list-card { padding: 16px 18px; }

/* 成绩单元格配色 */
.score-cell {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 10px; border-radius: 6px;
  font-family: var(--dq-mono); font-weight: 700; font-size: 13px;
  &.training { background: rgba(0,230,195,0.10); cursor: pointer; }
  &.manual   { background: rgba(77,141,255,0.10); }
  &.final    {
    font-size: 14px; padding: 3px 12px;
    background: rgba(45,212,191,0.12); border: 1px solid rgba(45,212,191,0.3);
    box-shadow: 0 0 8px rgba(45,212,191,0.08);
  }
  &.excellent { color: var(--dq-success); }
  &.good      { color: var(--dq-primary); }
  &.pass      { color: var(--dq-info); }
  &.fail      { color: var(--dq-error); }
  .cell-info { font-size: 11px; opacity: 0.6; }
}

/* 实训明细 popover */
.training-pop.el-popper { padding: 14px 16px !important; }
.tp-title { font-size: 13px; font-weight: 700; color: var(--dq-text); margin-bottom: 4px; }
.tp-sub { font-size: 11px; color: var(--dq-text-dim); margin-bottom: 10px; font-family: var(--dq-mono);
  &.no-wallet { color: var(--dq-warn); font-family: inherit; }
}
.tp-row { margin-bottom: 10px; }
.tp-row-head {
  display: flex; justify-content: space-between; align-items: baseline;
  font-size: 12px; margin-bottom: 4px;
  .tp-name { color: var(--dq-text-dim); font-weight: 600; }
  .tp-score { color: var(--dq-text); font-family: var(--dq-mono); font-weight: 700;
    small { color: var(--dq-text-dimmer); font-weight: 400; font-size: 10px; margin-left: 4px; }
  }
}
.tp-metrics {
  display: flex; flex-wrap: wrap; gap: 6px 10px; margin-top: 4px;
  .tp-metric { font-size: 10px; color: var(--dq-text-dimmer);
    .mk { margin-right: 3px; }
    .mv { color: var(--dq-text-dim); font-family: var(--dq-mono); font-weight: 600; }
  }
}
.tp-foot {
  margin-top: 6px; padding-top: 8px;
  border-top: 1px dashed rgba(31,42,68,0.8);
  font-size: 12px; color: var(--dq-primary); font-weight: 700; text-align: right;
}

/* 对话框预览框 */
.preview-box {
  margin: 8px 0 14px 92px;
  padding: 10px 14px;
  border-radius: 8px;
  background: rgba(0,230,195,0.06);
  border: 1px solid rgba(0,230,195,0.22);
  .pv-title { font-size: 12px; font-weight: 700; color: var(--dq-primary); margin-bottom: 6px; }
  .pv-row {
    display: flex; justify-content: space-between; align-items: center;
    font-size: 12px; padding: 2px 0;
    .pv-k { color: var(--dq-text-dim); }
    .pv-v { color: var(--dq-text); font-family: var(--dq-mono); font-weight: 700; }
    .pv-v.accent { color: var(--dq-primary); }
    .pv-v.success { color: var(--dq-success); }
    &.highlight .pv-v { font-size: 14px; }
  }
}
</style>
