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
        <div class="hero-sub">
          归档口径：<b>成绩按学校归档</b> —— 同一所学校的学生（跨班级）成绩都能查看与录入，下方名单、
          草稿与搭链看板也以本校为准。
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

    <!-- 归档范围与名单口径（成绩按学校归档；P0-1：看板的真话在这里说清 + 自助绑定入口） -->
    <section class="dq-card scope-card" v-if="scope">
      <div class="sc-body">
        <span class="dq-tag warn" v-if="scopeHint">{{ scopeHint }}</span>
        <span class="dq-tag" v-else>{{ scopeScopeText }}</span>
        <span class="sc-src">学校来源：{{ schoolSourceLabel }}
          · {{ rosterScopeText }} {{ scope.roster_count ?? 0 }} 人
          · 班级：{{ classScopeText }}（仅作筛选，不是权限边界）</span>
      </div>
      <el-button size="small" type="primary" plain @click="openBind">绑定任教范围</el-button>
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

    <!-- 搭链进度 · 本校看板（chain_tutorial_progress 聚合 + 本校学生名单） -->
    <section class="dq-card chain-progress-card" v-if="chainProgress">
      <div class="dq-card-title">
        ⛓️ 搭链进度 · {{ chainProgress.scope_mode === 'school' ? '本校看板' : '班级看板' }}
        <span class="dq-tag" style="margin-left:8px">
          {{ chainScopeTag }}
        </span>
        <span class="dq-tag info" style="margin-left:8px">
          平均完成 {{ chainProgress.avg_done_steps ?? 0 }} / {{ chainProgress.items?.[0]?.total_steps ?? 10 }} 步
        </span>
      </div>
      <el-table :data="chainProgress.items || []" v-loading="chainLoading" stripe size="small"
                empty-text="暂无搭链进度数据（学生尚未开始 10 步搭链实训）">
        <el-table-column type="index" label="#" width="48" />
        <el-table-column prop="student_id" label="学号" min-width="110" />
        <el-table-column prop="name" label="姓名" min-width="90" />
        <el-table-column label="钱包" min-width="110">
          <template #default="{ row }">{{ shortAddr(row.wallet) }}</template>
        </el-table-column>
        <el-table-column label="完成步数" width="180">
          <template #default="{ row }">
            <div class="cp-progress">
              <el-progress :percentage="Number(row.progress_pct) || 0" :stroke-width="8"
                           :color="progColor(Number(row.progress_pct) || 0)" :show-text="false" />
              <span class="cp-steps">{{ row.done_steps }}/{{ row.total_steps }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="当前卡点" min-width="230">
          <template #default="{ row }">
            <span v-if="row.stuck_step" class="cp-stuck">Step {{ row.stuck_step }} · {{ row.stuck_title }}</span>
            <el-tag v-else type="success" size="small" effect="plain">全部完成</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="平均耗时/步" width="110" align="center">
          <template #default="{ row }">{{ fmtAvgDur(row.avg_duration_seconds) }}</template>
        </el-table-column>
      </el-table>
    </section>

    <!-- 系统实训草稿（P1-25：草稿不自动进成绩册，必须教师显式同步；范围 = 本校跨班） -->
    <section class="dq-card draft-card">
      <div class="dq-card-title">
        系统实训草稿
        <span class="dq-tag info">{{ drafts.length }} 条待同步</span>
        <span class="dq-tag muted" v-if="draftsScope">范围：{{ draftsScope }}</span>
        <span class="dq-tag warn" v-if="draftsOrphan">含 {{ draftsOrphan }} 条{{ orphanLabel }}</span>
        <span class="dq-tag muted" v-if="dupRows">成绩册重复行 {{ dupRows }} 条（已按主体去重）</span>
      </div>
      <div class="dc-note">
        {{ drafts.length ? '同步后才进入成绩册；已有教师正式行的只刷新实训维度，教师分与备注不会被改写。' : `暂无待同步草稿（学生未刷草稿或${draftsScope === '本校' ? '本校' : '本班'}无学生）。` }}
        <span class="dc-unbound" v-if="draftsOrphan">{{ orphanLabel }}的草稿不会被「全部同步」带走，请逐条点「同步为成绩」（同步时自动归入你的任教学校）。</span>
        <span class="dc-unbound" v-if="draftsUnbound">{{ draftsHint }}</span>
      </div>
      <el-table :data="drafts" v-loading="draftsLoading" stripe size="small" empty-text="暂无待同步草稿">
        <el-table-column type="index" label="#" width="48" />
        <el-table-column prop="student_id" label="学号" min-width="110" />
        <el-table-column prop="student_name" label="姓名" min-width="90" />
        <el-table-column prop="class_id" label="班级 ID" width="90">
          <template #default="{ row }">
            <span v-if="row.class_missing" class="dq-tag warn">未标</span>
            <span v-else>{{ row.class_id }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="school_id" label="学校" min-width="120">
          <template #default="{ row }">
            <span v-if="row.school_missing" class="dq-tag warn">未定</span>
            <!-- 归档只认 ID，名称是按 ID 反查出来给人看的（无名称时降级显示 ID） -->
            <span v-else>{{ row.school_name || row.school_effective || row.school_id }}</span>
          </template>
        </el-table-column>
        <el-table-column label="实训草稿分" width="110" align="center">
          <template #default="{ row }">
            <span class="score-cell training" :class="scoreClass(row.training_score)">{{ fmtScore(row.training_score) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="目标行" width="130">
          <template #default="{ row }">
            <span class="dq-tag" :class="targetTag(row.target_row_kind).cls">{{ targetTag(row.target_row_kind).text }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" min-width="170">
          <template #default="{ row }">{{ fmt(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small"
                       :loading="applyingId === row.id" @click="onApplyDraft(row)">同步为成绩</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="dc-foot" v-if="drafts.length">
        <el-button type="success" plain size="small" :loading="applyingAll" @click="onApplyAll">
          {{ syncAllText }}
        </el-button>
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
        <el-table-column prop="class_id" label="班级 ID" width="100">
          <template #default="{ row }">{{ row.class_id || '—' }}</template>
        </el-table-column>
        <el-table-column prop="school_id" label="学校" min-width="120">
          <template #default="{ row }">
            <span v-if="!row.school_name && !row.school_effective && !row.school_id" class="dq-tag warn">未定</span>
            <span v-else>{{ row.school_name || row.school_effective || row.school_id }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="teacher_name" label="录入教师" min-width="90" />
        <el-table-column prop="remark" label="备注" min-width="140" show-overflow-tooltip />
        <el-table-column prop="updated_at" label="更新时间" min-width="170">
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
    <!-- 绑定任教范围（P0-1：SSO 不给教师返学校 / 班级时的显式入口；学校 = 成绩归档边界） -->
    <el-dialog v-model="bindDlg.visible" title="绑定任教范围" width="460px" align-center>
      <el-form label-width="92px" size="default">
        <el-form-item label="任教学校 ID">
          <el-input v-model="bindDlg.school_id" placeholder="如 232（成绩归档边界）" @keyup.enter="onBindClass" />
        </el-form-item>
        <el-form-item label="班级 ID">
          <el-input v-model="bindDlg.class_id" placeholder="可选，如 c1 / 2024 级 1 班" @keyup.enter="onBindClass" />
        </el-form-item>
      </el-form>
      <div class="bd-tip">
        <b>成绩按学校归档</b>：填了学校，本校所有班级学生的成绩都能看能录；班级只是把看板收窄到某一个班。
        外部 SSO 不返 schoolId / classId 时在这里定一次，学生名单、搭链进度、成绩册与学情看板都以它为准。
      </div>
      <template #footer>
        <el-button @click="bindDlg.visible = false">取消</el-button>
        <el-button type="primary" :loading="bindDlg.saving" @click="onBindClass">保存绑定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Plus, Refresh, Search, InfoFilled } from '@element-plus/icons-vue'
import { gradesApi, chainApi, authApi } from '@/api'
import { fmtDateTime } from '@/utils/time'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const loading = ref(false)
const refreshing = ref(false)
const rows = ref<any[]>([])
const stats = ref<any[]>([])
const dupRows = ref(0)

/* ---------- 归档范围 / 花名册口径自检（成绩按学校归档，P0-1） ---------- */
const scope = ref<any>(null)
const bindDlg = reactive({ visible: false, class_id: '', school_id: '', saving: false })
const SCHOOL_SOURCE_TEXT: Record<string, string> = {
  bind: '显式绑定', user_info: '登录信息', grade_book: '成绩册派生', all: '管理员（全校）',
}
const CLASS_SOURCE_TEXT: Record<string, string> = {
  bind: '显式绑定', user_info: '登录信息', jwt: '登录载荷', grade_book: '成绩册派生',
  all: '管理员（全校）', query: '本次筛选', class_unbound: '未解析到',
}
/** 当前归档边界的人话名字（mode 是后端给的，不在这里重新推一遍） */
const scopeMode = computed(() => String(scope.value?.scope_mode || ''))
const scopeScopeText = computed(() => {
  const s = scope.value || {}
  if (scopeMode.value === 'school') return `本校：${s.school_name || s.school_id || '—'}（跨班都能看能录）`
  if (scopeMode.value === 'class') return `过渡口径：班级 ${s.class_id || '—'}（未定任教学校）`
  if (scopeMode.value === 'all') return '全校（管理员）'
  return '未定任教范围：只看得见你自己录入的行'
})
const rosterScopeText = computed(() => String(scope.value?.roster_scope_text || '范围'))
const schoolSourceLabel = computed(() =>
  SCHOOL_SOURCE_TEXT[String(scope.value?.school_source || '')] || (scope.value?.school_source || '未定'))
const classSourceLabel = computed(() => CLASS_SOURCE_TEXT[String(scope.value?.class_source || '')] || (scope.value?.class_source || '—'))
const classScopeText = computed(() => {
  const s = scope.value || {}
  if (scopeMode.value === 'class') return `${s.class_id || '—'}（来源：${classSourceLabel.value}）`
  return s.class_id ? `${s.class_id}（已筛到单班）` : '不限'
})
const scopeHint = computed(() => {
  const s = scope.value
  if (!s) return ''
  if (s.scope_mode === 'self') return s.hint || '未解析到任教学校，成绩册只能看到你本人录入的行'
  if (s.scope_mode === 'class') {
    return '还没确定任教学校，当前按绑定班级归档。绑定学校后，本校其他班级学生的成绩也会出现'
  }
  if (s.roster_source === 'grade_book') {
    return '花名册（user_info）里还没有学生记录，当前名单由成绩册派生，不代表全校人数'
  }
  if (s.roster_source === 'empty') return '本校暂无任何学生记录（花名册与成绩册都为空），学生登录一次即会自动登记'
  if (s.user_info_registered === false) return '本账号登录信息未落库（user_info 无记录），学校口径可能不准，建议绑定任教学校'
  return ''
})
async function loadScope() {
  try {
    scope.value = await authApi.rosterStatus()
    // 学校口径下不把班级预填进筛选框（预填会把本校筛成一个班）
    if (scope.value?.scope_mode === 'class' && scope.value?.class_id && !filter.class_id) {
      filter.class_id = String(scope.value.class_id)
    }
  } catch {
    scope.value = null   // 自检失败不阻断成绩主流程
  }
}
function openBind() {
  bindDlg.class_id = String(scope.value?.class_id || filter.class_id || '')
  bindDlg.school_id = String(scope.value?.school_id || '')
  bindDlg.visible = true
}
async function onBindClass() {
  const cid = bindDlg.class_id.trim()
  const sid = bindDlg.school_id.trim()
  if (!cid && !sid) {
    ElMessage.warning('请至少填写任教学校 ID 或班级 ID（“0”不是有效值）')
    return
  }
  bindDlg.saving = true
  try {
    const payload: { school_id?: string; class_id?: string } = {}
    if (sid) payload.school_id = sid
    if (cid) payload.class_id = cid
    const res: any = await authApi.bindClass(payload)
    const parts = [res?.school_id ? `学校 ${res.school_id}` : '', res?.class_id ? `班级 ${res.class_id}` : '']
    ElMessage.success(`任教范围已更新：${parts.filter(Boolean).join(' · ') || '已保存'}`)
    bindDlg.visible = false
    // 改完范围就回到“整个学校”的视角，不留上一个班的筛选
    filter.class_id = ''
    await Promise.all([loadScope(), loadAll(), loadDrafts(), loadChainProgress()])
  } finally {
    bindDlg.saving = false
  }
}

/* ---------- 系统草稿与显式同步（P1-25） ---------- */
const drafts = ref<any[]>([])
const draftsLoading = ref(false)
const draftsHint = ref('')
const draftsUnbound = ref(false)
const draftsOrphan = ref(0)
const draftsScopeMode = ref('')
/** 草稿列表的统计范围（与成绩册同源：学校口径下是本校跨班） */
const draftsScope = computed(() => (
  draftsScopeMode.value === 'school' ? '本校'
    : draftsScopeMode.value === 'class' ? '本班'
      : draftsScopeMode.value === 'all' ? '全校' : ''
))
/** 「孤儿草稿」的成因随归档边界变：学校口径看学校定不定得出，过渡班级口径看班级 */
const orphanLabel = computed(() => (draftsScopeMode.value === 'school' ? '未定归属学校' : '未标班级'))
const syncAllText = computed(() => `全部同步为${draftsScope.value || '本班'}成绩`)
const applyingId = ref<number | null>(null)
const applyingAll = ref(false)
async function loadDrafts() {
  draftsLoading.value = true
  try {
    const res: any = await gradesApi.drafts(filter.class_id ? { class_id: filter.class_id } : {})
    drafts.value = res?.items || []
    draftsScopeMode.value = String(res?.scope_mode || '')
    draftsUnbound.value = !!res?.class_unbound
    draftsHint.value = res?.hint || ''
    draftsOrphan.value = Number(res?.orphan_total || 0)
  } catch {
    drafts.value = []   // 草稿列表失败不影响成绩主列表
    draftsOrphan.value = 0
  } finally {
    draftsLoading.value = false
  }
}
function targetTag(kind: string): { text: string; cls: string } {
  if (kind === 'teacher') return { text: '教师行·只刷实训', cls: '' }
  if (kind === 'system') return { text: '系统行·将接管', cls: 'warn' }
  return { text: '新建行', cls: 'muted' }
}
async function onApplyDraft(row: any) {
  applyingId.value = row.id
  try {
    const res: any = await gradesApi.draftApply({ draft_id: row.id })
    const it = res?.items?.[0]
    ElMessage.success(it?.reason || `已同步：${it?.action || 'ok'}（综合 ${fmtScore(it?.final_score)}）`)
    await Promise.all([loadAll(), loadDrafts()])
  } finally {
    applyingId.value = null
  }
}
async function onApplyAll() {
  try {
    await ElMessageBox.confirm(
      `确认把${draftsScope.value || '本班'} ${drafts.value.length} 条系统草稿同步为正式成绩？教师已评分的行只会刷新实训维度。`,
      '批量同步草稿',
      { type: 'warning', confirmButtonText: '全部同步', cancelButtonText: '取消' }
    )
  } catch { return }
  applyingAll.value = true
  try {
    const res: any = await gradesApi.draftApply({ all: true, class_id: filter.class_id || undefined })
    ElMessage.success(`已同步 ${res?.synced ?? 0} 条草稿`)
    await Promise.all([loadAll(), loadDrafts()])
  } finally {
    applyingAll.value = false
  }
}

/* ---------- 搭链进度 · 本校看板（chain_tutorial_progress 聚合） ---------- */
const chainProgress = ref<any>(null)
const chainLoading = ref(false)
const chainScopeTag = computed(() => {
  const cp = chainProgress.value || {}
  if (cp.scope_mode === 'school') {
    return `本校 ${cp.school_name || cp.school_id || ''} · ${cp.total ?? 0} 人${cp.class_id ? ` · 筛到 ${cp.class_id}` : ''}`
  }
  if (cp.scope_mode === 'class') return cp.class_id ? `班级 ${cp.class_id}（未定学校）` : '未定班级'
  if (cp.scope_mode === 'all') return cp.class_id ? `班级 ${cp.class_id}` : '全部班级'
  return cp.class_id ? `班级 ${cp.class_id}` : ''
})
async function loadChainProgress() {
  chainLoading.value = true
  try {
    // 不传 class_id：后端按归档边界（本校）取人，与成绩册 / 名单完整同源
    chainProgress.value = await chainApi.classProgress(filter.class_id || '')
  } catch {
    chainProgress.value = null   // 搭链进度拉取失败不影响成绩主列表
  } finally {
    chainLoading.value = false
  }
}
function fmtAvgDur(sec: any): string {
  if (sec === null || sec === undefined) return '—'
  const n = Number(sec)
  if (!isFinite(n) || n <= 0) return '—'
  if (n < 60) return `${n.toFixed(0)} 秒`
  if (n < 3600) return `${Math.floor(n / 60)} 分 ${Math.round(n % 60)} 秒`
  return `${(n / 3600).toFixed(1)} 小时`
}

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
    dupRows.value = Number(statsRes?.duplicate_rows ?? 0)
    // 后端未绑班级时会回退为“只看自己录入的行”，此处沿用其班级口径
    if (!filter.class_id && listRes?.class_id) filter.class_id = String(listRes.class_id)
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

/* ---------- 实训明细转可读结构 ----------
   指标名必须全部覆盖：没登在这里的 key 会在 popover 里直接露出英文下划线名
   （曾漏 tutorial_done / energy_issue / eco_market_trade，教师看到半中半英的明细无法解读）。 */
const _DETAIL_META: Record<string, { name: string; metrics: Record<string, string> }> = {
  chain_setup:  { name: '链搭建',     metrics: { ide_open_builtin: '打开内置合约', ide_save_project: '保存工程', tutorial_done: '搭链步骤完成' } },
  contract_dev: { name: '合约开发',   metrics: { contract_compile_ok: '编译成功', deployed_contracts: '已部署合约' } },
  chain_verify: { name: '链上验证',   metrics: { interface_invoke: '接口调用', contract_calls: '合约调用', transactions: '链上交易' } },
  alliance_gov: { name: '联盟治理',   metrics: { eco_role_switch: '角色切换', energy_issue: '能量发放', nft_mint: 'NFT 铸造', nft_trade: 'NFT 交易', eco_market_trade: '绿色市场成交', erc20_transfer: 'ERC20 转账', report_view: '报告查看' } },
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
      '将根据任教范围内（本校跨班）学生钱包的最新链上活动数据，重新计算实训成绩与综合成绩，是否继续？',
      '刷新实训成绩',
      { type: 'info', confirmButtonText: '开始刷新', cancelButtonText: '取消' }
    )
  } catch { return }
  refreshing.value = true
  try {
    const res: any = await gradesApi.refreshTraining()
    const extra = res?.school_backfilled ? `，并补全 ${res.school_backfilled} 条行的学校归属` : ''
    ElMessage.success(`已刷新 ${res.refreshed} 条记录的实训成绩${extra}（范围：${res.scope_mode === 'school' ? '本校' : res.scope_mode === 'class' ? '本班+自己录入' : res.scope_mode === 'all' ? '全校' : '仅自己录入的行'}）`)
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
  // 后端写的是 UTC naive ISO（utcnow().isoformat()），统一交给共享工具换算成本地时间
  return ts ? fmtDateTime(ts, '—') : '—'
}

onMounted(async () => {
  await loadScope()      // 先定班级口径，再拉列表/草稿（看板的班级范围依赖它）
  loadAll()
  loadDrafts()
  loadChainProgress()
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

/* ---------- 搭链进度 · 班级看板 ---------- */
.chain-progress-card { padding: 16px 18px; }
.cp-progress {
  display: flex; align-items: center; gap: 8px;
  .el-progress { flex: 1; }
  .cp-steps { font-family: var(--dq-mono); font-size: 12px; font-weight: 700; color: var(--dq-text); flex-shrink: 0; }
}
.cp-stuck {
  font-size: 12px; color: var(--dq-warn);
  background: rgba(255, 207, 77, 0.08);
  border: 1px solid rgba(255, 207, 77, 0.25);
  padding: 2px 8px; border-radius: 4px;
}

/* ---------- 班级 / 名单口径提示（P0-1） ---------- */
.scope-card {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 12px 18px;
  border-color: rgba(255, 207, 77, 0.28);
  background:
    linear-gradient(135deg, rgba(255,207,77,0.07) 0%, rgba(255,207,77,0.02) 100%),
    var(--dq-grad-panel);
  .sc-body { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; min-width: 0; }
  .sc-src { font-size: 11px; color: var(--dq-text-dimmer); }
  :deep(.el-button) { flex-shrink: 0; }
}

/* ---------- 系统实训草稿（P1-25） ---------- */
.draft-card { padding: 16px 18px; }
.dc-note {
  margin: 4px 0 10px; font-size: 12px; color: var(--dq-text-dimmer); line-height: 1.7;
  .dc-unbound {
    display: inline-block; margin-left: 6px;
    color: var(--dq-warn);
    background: rgba(255, 207, 77, 0.08);
    border: 1px solid rgba(255, 207, 77, 0.25);
    padding: 1px 8px; border-radius: 4px;
  }
}
.dc-foot { margin-top: 10px; display: flex; justify-content: flex-end; }
.bd-tip { margin: 6px 0 2px; font-size: 12px; color: var(--dq-text-dimmer); line-height: 1.7; }

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
