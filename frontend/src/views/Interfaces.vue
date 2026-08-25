<template>
  <div class="iface dq-enter-up">
    <!-- 左侧：合约选择 + 接口列表 -->
    <div class="left dq-card">
      <div class="dq-card-title">合约接口（自动生成）</div>
      <el-select v-model="addr" filterable placeholder="选择已部署合约" @change="loadContract" style="width:100%;margin-bottom:10px">
        <el-option v-for="c in contracts" :key="c.address" :label="`${c.name} (${c.standard || '自定义'})`" :value="c.address" />
      </el-select>

      <div class="iface-list" v-if="interfaces.length">
        <div
          v-for="(fn, i) in interfaces"
          :key="i"
          class="iface-item"
          :class="{ active: curFn?._idx === i }"
          @click="selectFn(fn, i)"
        >
          <span class="dq-tag">{{ fn.type || 'function' }}</span>
          <span class="dq-mono fn-name">{{ fn.name }}</span>
          <span class="args">({{ (fn.inputs || []).map((a: any) => a.type).join(', ') }})</span>
        </div>
      </div>
      <div v-else>
        <EmptyIllustration type="contract" :hide-text="true" style="padding: 14px 4px;" />
        <div class="empty-tip">{{ contracts.length ? '选择合约后自动生成 ABI 接口列表' : '暂无已部署合约，先去 IDE 部署一份' }}</div>
      </div>
    </div>

    <!-- 右侧：接口调试 -->
    <div class="right dq-card">
      <div class="dq-card-title">在线调试</div>
      <div v-if="curFn" class="debug">
        <div class="fn-sig dq-mono">{{ curFn.name }}({{ (curFn.inputs || []).map((a: any) => `${a.type} ${a.name}`).join(', ') }})</div>
        <div class="args-form">
          <div class="arg" v-for="(a, i) in curFn.inputs || []" :key="i">
            <label class="dq-mono">{{ a.name }} <span class="t">{{ a.type }}</span></label>
            <el-input v-model="args[i]" size="small" :placeholder="`输入 ${a.type} 参数`" />
          </div>
        </div>
        <div class="ops">
          <el-button type="primary" @click="invoke">调用</el-button>
          <el-button @click="result = ''">清空</el-button>
        </div>
        <div class="result">
          <div class="r-label">调用结果（实时输出）</div>
          <pre class="dq-mono">{{ result || '（点击「调用」输出结果）' }}</pre>
        </div>
      </div>
      <div v-else>
        <EmptyIllustration type="explorer" :hide-text="true" style="padding: 30px 4px;" />
        <div class="empty-tip center">从左侧选择一个方法开始调试</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onActivated, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { contractApi } from '@/api'
import { useAppStore } from '@/stores/app'
import { ElMessage } from 'element-plus'
import EmptyIllustration from '@/components/EmptyIllustration.vue'

const route = useRoute()
const app = useAppStore()
const contracts = ref<any[]>([])
const addr = ref('')
const curContract = ref<any>(null)
const interfaces = ref<any[]>([])
const curFn = ref<any>(null)
const args = ref<string[]>([])
const result = ref('')

const loadContracts = async () => {
  contracts.value = (await contractApi.deployed()) as any
  if (route.query.addr) {
    addr.value = route.query.addr as string
    await loadContract()
  }
}

const loadContract = async () => {
  if (!addr.value) return
  curContract.value = await contractApi.getDeployed(addr.value)
  interfaces.value = curContract.value.abi.filter((x: any) => x.type === 'function' || !x.type)
}

const selectFn = (fn: any, i: number) => {
  curFn.value = { ...fn, _idx: i }
  args.value = (fn.inputs || []).map(() => '')
  result.value = ''
}

const invoke = async () => {
  if (!curFn.value) {
    ElMessage.warning('请先在左侧选择一个合约方法')
    return
  }
  // 调用前参数校验：缺失参数时给出明确提示，避免直接调用后端报不明错误
  const inputs: any[] = curFn.value.inputs || []
  const missing: string[] = []
  inputs.forEach((a: any, i: number) => {
    const v = args.value[i]
    if (v === '' || v === null || v === undefined) missing.push(a.name || a.type)
  })
  if (missing.length) {
    ElMessage.warning(`方法 ${curFn.value.name} 缺少参数：${missing.join('、')}（共需 ${inputs.length} 个，已填 ${inputs.length - missing.length} 个），请补全后再调用`)
    result.value = `✗ 方法 ${curFn.value.name} 缺少参数：${missing.join('、')}\n（共需 ${inputs.length} 个，已填 ${inputs.length - missing.length} 个）`
    return
  }
  try {
    const r: any = await contractApi.call({
      address: addr.value,
      method: curFn.value.name,
      args: args.value,
      caller: app.currentWallet,
      abi: curContract.value.abi,
    })
    result.value = JSON.stringify(r, null, 2)
    ElMessage.success('调用完成，监听器已记录')
  } catch (e: any) {
    // 优先透出后端可读错误（如 ABI 无该方法 / 参数不匹配），而不是笼统的请求失败
    const msg = e?.response?.data?.detail || e?.message || '调用失败'
    result.value = '✗ ' + msg
    ElMessage.error(msg)
  }
}

/* 首次进入触发 onMounted，KeepAlive 缓存后再次进入触发 onActivated，两者都执行加载 */
onMounted(loadContracts)
onActivated(loadContracts)
</script>

<style scoped lang="scss">
.iface { display: grid; grid-template-columns: 340px 1fr; gap: 14px; height: calc(100vh - 110px); }
.left { overflow: auto; }
.iface-list { display: flex; flex-direction: column; gap: 6px; }
.iface-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px; border-radius: 4px; cursor: pointer; font-size: 13px;
  color: var(--dq-text-dim);
  &:hover { background: var(--dq-bg-2); color: var(--dq-text); }
  &.active { background: rgba(0,230,195,0.1); color: var(--dq-primary); }
  .fn-name { font-weight: 600; }
  .args { color: var(--dq-text-dim); font-family: var(--dq-mono); font-size: 12px; }
}
.empty-tip { font-size: 12px; color: var(--dq-text-dim); text-align: left; padding: 0 12px 12px; line-height: 1.6;
  &.center { text-align: center; }
}
.right { overflow: auto; }
.debug { display: flex; flex-direction: column; gap: 14px; }
.fn-sig { color: var(--dq-primary); font-size: 15px; padding: 10px; background: var(--dq-bg-2); border-radius: 4px; }
.args-form { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
.arg { display: flex; flex-direction: column; gap: 4px; label { font-size: 12px; color: var(--dq-text-dim); .t { color: var(--dq-accent); } } }
.ops { display: flex; gap: 10px; }
.result { border-top: 1px solid var(--dq-border); padding-top: 10px; .r-label { font-size: 12px; color: var(--dq-text-dim); margin-bottom: 6px; } pre { background: var(--dq-bg); padding: 10px; border-radius: 4px; color: var(--dq-text); font-size: 12px; max-height: 240px; overflow: auto; } }
</style>
