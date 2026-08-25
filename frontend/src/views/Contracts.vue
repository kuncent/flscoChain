<template>
  <div class="contracts dq-enter-up">
    <div class="dq-card">
      <div class="dq-card-title">
        已部署合约
        <span class="legend">
          <span class="lg"><i class="dot erc20"></i>ERC20</span>
          <span class="lg"><i class="dot erc721"></i>ERC721</span>
          <span class="lg"><i class="dot erc1155"></i>ERC1155</span>
          <span class="lg"><i class="dot custom"></i>自定义</span>
        </span>
        <el-button size="small" @click="load" style="margin-left:auto">刷新</el-button>
      </div>
      <el-table :data="list" border stripe v-if="list.length">
        <el-table-column prop="name" label="合约名" min-width="200">
          <template #default="{ row }">
            <span class="name-cell">{{ row.name }}</span>
            <span v-if="row.builtin" class="dq-tag info" style="margin-left:6px">系统内置</span>
          </template>
        </el-table-column>
        <el-table-column prop="address" label="地址" min-width="220">
          <template #default="{ row }">
            <span class="dq-mono addr" @click="$router.push('/explorer/address/' + row.address)">{{ row.address }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="standard" label="标准" width="120">
          <template #default="{ row }">
            <span class="std-badge" :class="stdClass(row.standard)" v-if="row.standard">{{ row.standard }}</span>
            <span class="std-badge custom" v-else>自定义</span>
          </template>
        </el-table-column>
        <el-table-column prop="deployer" label="部署者" min-width="180">
          <template #default="{ row }"><span class="dq-mono dim">{{ short(row.deployer) }}</span></template>
        </el-table-column>
        <el-table-column prop="tx_hash" label="交易哈希" min-width="180">
          <template #default="{ row }"><span class="dq-mono dim">{{ short(row.tx_hash) }}</span></template>
        </el-table-column>
        <el-table-column prop="created_at" label="部署时间" width="170" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" @click="$router.push('/interfaces?addr=' + row.address)">接口调试</el-button>
            <el-button size="small" @click="$router.push('/monitor?addr=' + row.address)">监听</el-button>
          </template>
        </el-table-column>
      </el-table>
      <EmptyIllustration
        v-else
        type="contract"
        title="暂无已部署合约"
        subtitle="进入「合约 IDE」编译并部署你的第一份智能合约后，合约信息会出现在这里"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onActivated, onMounted } from 'vue'
import { contractApi } from '@/api'
import EmptyIllustration from '@/components/EmptyIllustration.vue'

const list = ref<any[]>([])
const load = async () => { list.value = (await contractApi.deployed()) as any }
const short = (h: string) => h ? (h.length > 16 ? h.slice(0, 12) + '...' + h.slice(-4) : h) : ''
const stdClass = (s: string) => {
  if (!s) return 'custom'
  const k = s.toUpperCase()
  if (k === 'ERC20') return 'erc20'
  if (k === 'ERC721') return 'erc721'
  if (k === 'ERC1155') return 'erc1155'
  return 'custom'
}
/* 首次进入触发 onMounted，KeepAlive 缓存后再次进入触发 onActivated，两者都执行加载 */
onMounted(load)
onActivated(load)
</script>

<style scoped lang="scss">
.addr { color: var(--dq-primary); cursor: pointer; &:hover { text-decoration: underline; } }
.dim { color: var(--dq-text-dim); }
.name-cell { color: var(--dq-text); font-weight: 500; }

.legend {
  display: inline-flex; align-items: center; gap: 14px; margin-left: 16px;
  .lg { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; color: var(--dq-text-dim); font-family: var(--dq-mono); }
  .dot { width: 8px; height: 8px; border-radius: 2px; display: inline-block; }
  .dot.erc20 { background: #4d8dff; }
  .dot.erc721 { background: #f5379b; }
  .dot.erc1155 { background: #ffcf4d; }
  .dot.custom { background: #7b8aab; }
}

.std-badge {
  display: inline-block; padding: 2px 10px; border-radius: 4px;
  font-size: 11px; font-family: var(--dq-mono); font-weight: 600;
  border: 1px solid transparent; line-height: 1.6;
  &.erc20 { background: rgba(77,141,255,0.12); color: #6ea3ff; border-color: rgba(77,141,255,0.3); }
  &.erc721 { background: rgba(245,55,155,0.12); color: #f86bb0; border-color: rgba(245,55,155,0.3); }
  &.erc1155 { background: rgba(255,207,77,0.12); color: #ffd970; border-color: rgba(255,207,77,0.3); }
  &.custom { background: rgba(123,138,171,0.12); color: #9fadc4; border-color: rgba(123,138,171,0.25); }
}
</style>
