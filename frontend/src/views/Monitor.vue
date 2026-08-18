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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onActivated, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart } from 'echarts/charts'
import { LegendComponent, TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { contractApi, monitorApi } from '@/api'
import EmptyIllustration from '@/components/EmptyIllustration.vue'

use([CanvasRenderer, PieChart, LegendComponent, TooltipComponent])

const route = useRoute()
const contracts = ref<any[]>([])
const addr = ref('')
const data = ref<any>(null)

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
  if (route.query.addr) {
    addr.value = route.query.addr as string
    await load()
  }
}

/* 首次进入触发 onMounted，KeepAlive 缓存后再次进入触发 onActivated，两者都执行加载 */
onMounted(loadAll)
onActivated(loadAll)
</script>

<style scoped lang="scss">
.sel { display: flex; gap: 10px; }
.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin: 14px 0; }
.stat { .lbl { color: var(--dq-text-dim); font-size: 13px; } .val { font-size: 28px; font-weight: 700; color: var(--dq-primary); margin-top: 6px; font-family: var(--dq-mono); } }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.chart { height: 320px; }
.dim { color: var(--dq-text-dim); }
.empty-tip { font-size: 12px; color: var(--dq-text-dim); text-align: center; padding: 0 12px 10px; }
</style>
