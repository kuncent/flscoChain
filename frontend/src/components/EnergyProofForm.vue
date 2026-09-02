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
      <el-button type="primary" :loading="submitting" @click="submit">
        确认发放 {{ points }} 能量
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  visible: boolean
  /** 角色名（弹窗标题用） */
  roleName?: string
  /** 发放能量点数 */
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
  props.roleName ? `发放绿色能量 · ${props.roleName}业务凭证` : '发放绿色能量 · 业务凭证',
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

/** 前端必填校验（额度校验交给后端，返回的明确提示直接展示） */
const submit = () => {
  const fields = (props.rule?.proof_fields || []) as any[]
  const missing: string[] = []
  for (const f of fields) {
    if (!f.required) continue
    const v = form.value[f.key]
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
</style>