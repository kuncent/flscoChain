<template>
  <el-dialog
    :model-value="visible"
    :title="title"
    width="520px"
    @update:model-value="$emit('update:visible', $event)"
    @closed="reset"
  >
    <div class="pf-tip" v-if="thresholdHint">
      <span class="pf-tip-label">校验规则</span>{{ thresholdHint }}
    </div>
    <!-- 实时核算：按已填业务量估本次发行能量，口径与后端 calc_energy_points 一致 -->
    <div class="pf-est" :class="{ 'is-bad': est.belowMin }">
      <div class="pf-est-head">
        <span class="pf-est-label">{{ hasRule ? '预计发放' : '发放' }}</span>
        <span class="pf-est-num">+{{ estPoints }}{{ estSuffix }}</span>
        <span class="pf-est-unit">绿色能量</span>
      </div>
      <div class="pf-est-calc">{{ estCalc }}</div>
    </div>
    <el-form label-width="120px" size="small" style="margin-top: 12px">
      <el-form-item v-for="f in proofFields" :key="f.key" :label="f.label" :required="f.required">
        <el-input-number
          v-if="f.type === 'number'"
          v-model="form[f.key]"
          :min="0"
          :step="0.5"
          :style="{ width: '100%' }"
          :placeholder="f.placeholder"
        />
        <el-switch
          v-else-if="f.type === 'switch'"
          v-model="form[f.key]"
          active-text="已选择"
          inactive-text="未选择"
        />
        <el-input v-else v-model="form[f.key]" :placeholder="f.placeholder" />
      </el-form-item>
      <el-form-item v-if="showProofNo" :label="proofNoLabel" required>
        <el-input v-model="form[proofNoKey]" placeholder="业务单号（同一单号不可重复发放）" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" :disabled="est.belowMin" @click="submit">
        提交凭证 · 预计 +{{ estPoints }}{{ estSuffix }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { estimateEnergy, energyCalcText } from '@/utils/energy'

const props = defineProps<{
  visible: boolean
  /** 角色名（弹窗标题用） */
  roleName?: string
  /** 兜底发放点数：仅在拿不到 rule 时使用；有 rule 时一律按规则实时核算 */
  points?: number
  /** 后端 ROLES 中的 energy_rule（含 proof_fields / proof_field / min / unit / proof_no_field） */
  rule?: Record<string, any> | null
  /** 阈值提示，如 "distance_km ≥ 10 km" */
  thresholdHint?: string
  /** 业务单号标签（如 地铁乘车号 / 外卖订单号） */
  proofNoLabel?: string
  /** 业务单号字段名（如 trip_no / order_id） */
  proofNoField?: string
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'submit', proof: Record<string, any>): void
}>()

const submitting = ref(false)
/** 动态表单数据：key -> 值 */
const form = ref<Record<string, any>>({})

const title = computed(() =>
  // 只能由居民提交凭证、节点核算发行（节点侧无手动发放入口），标题用「申领」而非「发放」
  props.roleName ? `申领绿色能量 · ${props.roleName}业务凭证` : '申领绿色能量 · 业务凭证',
)

/** 是否拿到了后端能量规则（有规则才能按量核算） */
const hasRule = computed(() => !!props.rule)
/** 本次预计发行量（用户每改一个业务数值即重算） */
const est = computed(() => estimateEnergy(props.rule, form.value))
const estPoints = computed(() =>
  hasRule.value ? est.value.points : Math.trunc(Number(props.points || 0)),
)
/** 计量值未填时不能拍板一个具体数字（那只是基础分），加「起」避免又是一口径错误 */
const estSuffix = computed(() => (est.value.pending && est.value.per > 0 ? ' 起' : ''))
const estCalc = computed(() =>
  hasRule.value
    ? energyCalcText(est.value)
    : '未获取到该节点的发行规则，实际发放量以后端核算为准',
)

/** 必填业务字段（进站口 / 出站口 / 订单号 / 重量 …）。
 * 注意：不可过滤业务单号字段——共享单车/外卖/回收的单号字段（order_id / order_no）
 * 就在 proof_fields 内，过滤后下方 showProofNo 又为 false，单号输入框会整个丢失 */
const proofFields = computed(() => (props.rule?.proof_fields || []) as any[])

const showProofNo = computed(() => {
  if (!props.rule?.proof_no_field) return false
  const fields = (props.rule?.proof_fields || []) as any[]
  return !fields.some((f) => f.key === props.rule?.proof_no_field)
})

/** 业务单号字段名（模板索引用，规避可选 prop 的 undefined 索引类型报错） */
const proofNoKey = computed(() => props.proofNoField || props.rule?.proof_no_field || '')

/** 重置表单 */
const reset = () => {
  form.value = {}
  submitting.value = false
}

/** 父组件打开时初始化表单默认值 */
watch(
  () => props.visible,
  (v) => {
    if (v) {
      form.value = {}
      const fields = (props.rule?.proof_fields || []) as any[]
      fields.forEach((f) => {
        form.value[f.key] = f.type === 'switch' ? false : undefined
      })
      if (showProofNo.value && props.rule?.proof_no_field) {
        form.value[props.rule.proof_no_field] = ''
      }
    }
  },
)

/** 前端必填与门槛校验（额度校验交给后端，返回的明确提示直接展示） */
const submit = () => {
  if (est.value.belowMin) {
    ElMessage.warning(estCalc.value)
    return
  }
  const fields = (props.rule?.proof_fields || []) as any[]
  const missing: string[] = []
  for (const f of fields) {
    if (!f.required) continue
    const v = form.value[f.key]
    // 开关型必填字段：未打开（false）等于未提供凭证，不能当作“已填写”放行
    if (f.type === 'switch') {
      if (v !== true) missing.push(f.label || f.key)
      continue
    }
    if (v === undefined || v === null || v === '' || (typeof v === 'string' && !v.trim())) {
      missing.push(f.label || f.key)
    }
  }
  if (showProofNo.value && props.rule?.proof_no_field) {
    const n = form.value[props.rule.proof_no_field]
    if (!n || !String(n).trim()) {
      missing.push(props.proofNoLabel || '业务单号')
    }
  }
  if (missing.length) {
    ElMessage.warning(`请补全必填业务数据：${missing.join('、')}`)
    return
  }
  submitting.value = true
  emit('submit', { ...form.value })
}

/** 供父组件在请求结束后复位按钮 loading */
const setSubmitting = (v: boolean) => {
  submitting.value = v
}

defineExpose({ setSubmitting, reset })
</script>

<style scoped>
.pf-tip {
  padding: 10px 12px;
  background: rgba(0, 230, 195, 0.06);
  border: 1px solid rgba(0, 230, 195, 0.25);
  border-radius: 6px;
  font-size: 12px;
  color: var(--dq-text-dim);
  line-height: 1.6;
}
.pf-tip-label {
  display: inline-block;
  margin-right: 8px;
  font-weight: 600;
  color: var(--dq-primary);
  background: rgba(0, 230, 195, 0.12);
  padding: 1px 8px;
  border-radius: 3px;
}
.pf-est {
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid rgba(77, 141, 255, 0.28);
  background: rgba(77, 141, 255, 0.07);
}
.pf-est.is-bad {
  border-color: rgba(255, 120, 73, 0.45);
  background: rgba(255, 120, 73, 0.08);
}
.pf-est-head {
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.pf-est-label {
  font-size: 12px;
  color: var(--dq-text-dim);
}
.pf-est-num {
  font-size: 20px;
  font-weight: 700;
  color: var(--dq-primary);
  font-variant-numeric: tabular-nums;
}
.pf-est.is-bad .pf-est-num {
  color: #ff7849;
}
.pf-est-unit {
  font-size: 12px;
  color: var(--dq-text-dim);
}
.pf-est-calc {
  margin-top: 2px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--dq-text-dim);
}
</style>