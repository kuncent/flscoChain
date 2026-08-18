<template>
  <!-- 交易流水时间线（Wallet / NFT 通用） -->
  <div class="dq-tx-timeline" v-if="list.length">
    <div class="tl-head">
      <div class="tl-title">
        <span class="ico">📜</span>
        <span>{{ title }}</span>
      </div>
      <span class="dq-tag muted dq-mono">共 {{ list.length }} 笔</span>
    </div>
    <div class="tl-list">
      <div class="tl-item" v-for="(t, i) in list" :key="i">
        <div class="tl-side">
          <div class="tl-dot" :class="t.status || 'ok'">
            <el-icon v-if="t.status === 'ok' || t.status === 'success'"><Check /></el-icon>
            <el-icon v-else-if="t.status === 'fail' || t.status === 'error'"><Close /></el-icon>
            <el-icon v-else><Timer /></el-icon>
          </div>
          <div class="tl-line" v-if="i < list.length - 1"></div>
        </div>
        <div class="tl-body">
          <div class="tl-top">
            <span class="tl-kind dq-tag" :class="kindClass(t.kind)">{{ t.kind }}</span>
            <span class="tl-time dq-mono">{{ t.time }}</span>
          </div>
          <div class="tl-flow">
            <span class="addr dq-mono">{{ short(t.from) }}</span>
            <span class="arrow">
              <el-icon><ArrowRight /></el-icon>
              <b v-if="t.amount" class="amt">{{ t.amount }}</b>
            </span>
            <span class="addr dq-mono" :class="{ is_contract: t.to_is_contract }">
              {{ t.to_is_contract ? '部署合约' : short(t.to) }}
            </span>
          </div>
          <div class="tl-meta">
            <span v-if="t.token" class="m dq-tag info">{{ t.token }}</span>
            <span v-if="t.gas" class="m dq-mono">Gas {{ t.gas }}</span>
            <span v-if="t.tx_hash" class="m tx dq-mono" :title="t.tx_hash">Tx {{ t.tx_hash.slice(0, 12) }}…</span>
            <span v-if="t.status === 'ok' || t.status === 'success'" class="m dq-tag">成功</span>
            <span v-else-if="t.status === 'fail'" class="m dq-tag error">失败</span>
            <span v-else class="m dq-tag warn">处理中</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title?: string
  list: Array<{
    kind: string        // 转账 / 铸造 / 部署 / 购买 等
    from: string
    to: string
    to_is_contract?: boolean
    amount?: string
    token?: string
    gas?: string | number
    tx_hash?: string
    time?: string
    status?: 'ok' | 'fail' | 'pending' | 'success' | 'error'
  }>
}>()

function short(a: string) {
  if (!a) return '-'
  if (a.length <= 14) return a
  return a.slice(0, 10) + '…' + a.slice(-6)
}

function kindClass(k: string) {
  if (/部署|Deploy/i.test(k)) return 'accent'
  if (/铸造|Mint/i.test(k)) return 'warn'
  if (/购买|Buy|Transfer|转账/i.test(k)) return 'info'
  return ''
}
</script>

<style scoped lang="scss">
.dq-tx-timeline { background: var(--dq-grad-panel), var(--dq-panel); border: 1px solid var(--dq-border); border-radius: var(--dq-radius-card); padding: var(--dq-space-md); }
.tl-head { display:flex; align-items:center; justify-content:space-between; margin-bottom: 14px;
  .tl-title { font-weight: 600; color: var(--dq-text); font-size: 14px; display:flex; align-items:center; gap: 6px;
    .ico { font-size: 15px; } }
}
.tl-list { position: relative; }
.tl-item { display:flex; gap: 12px; padding-bottom: 14px; }
.tl-side { width: 22px; position: relative; flex-shrink: 0; display:flex; flex-direction:column; align-items:center;
  .tl-dot {
    width: 22px; height: 22px; border-radius: 50%;
    display:inline-flex; align-items:center; justify-content:center;
    background: rgba(45,212,191,0.15); color: var(--dq-success); border: 1.5px solid var(--dq-success);
    font-size: 12px; flex-shrink: 0; z-index: 2;
    &.fail, &.error { background: rgba(255,84,112,0.15); color: var(--dq-error); border-color: var(--dq-error); }
    &.pending { background: rgba(255,207,77,0.15); color: var(--dq-warn); border-color: var(--dq-warn);
      animation: dq-pulse 1.4s ease-in-out infinite; }
  }
  .tl-line {
    flex: 1; width: 2px; margin-top: 4px;
    background: linear-gradient(180deg, var(--dq-border-2), transparent);
  }
}
.tl-body { flex: 1; min-width: 0; }
.tl-top { display:flex; justify-content:space-between; align-items:center; margin-bottom: 6px;
  .tl-time { font-size: 11px; color: var(--dq-text-dimmer); }
}
.tl-flow { display:flex; align-items:center; gap: 8px; flex-wrap: wrap;
  font-size: 13px; color: var(--dq-text);
  .addr { font-size: 12px; padding: 2px 6px; border-radius: 4px; background: var(--dq-bg-2); color: var(--dq-text-dim);
    &.is_contract { color: var(--dq-accent); background: rgba(245,55,155,0.08); }
  }
  .arrow { display:inline-flex; align-items:center; gap: 6px; color: var(--dq-primary);
    .amt { color: var(--dq-primary); font-family: var(--dq-mono); font-weight: 700; }
  }
}
.tl-meta { margin-top: 6px; display:flex; gap: 6px; flex-wrap: wrap; align-items:center;
  .m { font-size: 11px; }
  .m.tx { color: var(--dq-text-dim); }
}
</style>
