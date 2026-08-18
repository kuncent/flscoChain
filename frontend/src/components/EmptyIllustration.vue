<template>
  <!-- 空状态主题插画：按 type 切换（chain/wallet/nft/contract/explorer/default） -->
  <div class="dq-empty-ill" :class="type">
    <svg viewBox="0 0 320 200" class="ill" aria-hidden="true">
      <!-- 通用底板 -->
      <defs>
        <linearGradient id="ei-g1" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="rgba(0,230,195,0.18)"/>
          <stop offset="100%" stop-color="rgba(0,230,195,0.02)"/>
        </linearGradient>
        <linearGradient id="ei-g2" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="rgba(77,141,255,0.18)"/>
          <stop offset="100%" stop-color="rgba(77,141,255,0.02)"/>
        </linearGradient>
        <linearGradient id="ei-g3" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="rgba(245,55,155,0.18)"/>
          <stop offset="100%" stop-color="rgba(245,55,155,0.02)"/>
        </linearGradient>
      </defs>

      <!-- type: chain 搭链 -->
      <g v-if="type === 'chain'">
        <rect x="20" y="20" width="280" height="160" rx="12" fill="url(#ei-g1)" stroke="rgba(0,230,195,0.3)"/>
        <!-- 4 节点 -->
        <g fill="#0e1424" stroke="#00e6c3" stroke-width="1.5">
          <circle cx="160" cy="70" r="16"/>
          <circle cx="80" cy="130" r="14"/>
          <circle cx="240" cy="130" r="14"/>
          <circle cx="160" cy="170" r="14"/>
        </g>
        <g stroke="#00e6c3" stroke-width="1" opacity="0.55" fill="none">
          <line x1="160" y1="70" x2="80" y2="130"/>
          <line x1="160" y1="70" x2="240" y2="130"/>
          <line x1="160" y1="70" x2="160" y2="170"/>
          <line x1="80" y1="130" x2="240" y2="130"/>
          <line x1="80" y1="130" x2="160" y2="170"/>
          <line x1="240" y1="130" x2="160" y2="170"/>
        </g>
        <g font-family="JetBrains Mono, Consolas, monospace" font-size="10" fill="#00e6c3" font-weight="700" text-anchor="middle">
          <text x="160" y="74">0</text>
          <text x="80" y="134">1</text>
          <text x="240" y="134">2</text>
          <text x="160" y="174">3</text>
        </g>
        <!-- 小方块流动 -->
        <rect x="0" y="0" width="8" height="4" rx="1" fill="#00e6c3" opacity="0.8"/>
      </g>

      <!-- type: wallet 钱包 -->
      <g v-else-if="type === 'wallet'">
        <rect x="20" y="20" width="280" height="160" rx="12" fill="url(#ei-g2)" stroke="rgba(77,141,255,0.3)"/>
        <!-- 钱包本体 -->
        <rect x="70" y="55" width="180" height="110" rx="10" fill="#0e1424" stroke="#4d8dff" stroke-width="1.5"/>
        <rect x="70" y="55" width="180" height="28" rx="10" fill="rgba(77,141,255,0.25)"/>
        <!-- 磁条 -->
        <rect x="88" y="100" width="42" height="28" rx="4" fill="rgba(255,207,77,0.65)"/>
        <!-- 硬币 -->
        <circle cx="225" cy="115" r="14" fill="rgba(0,230,195,0.18)" stroke="#00e6c3" stroke-width="1.2"/>
        <text x="225" y="119" text-anchor="middle" font-family="monospace" font-size="11" font-weight="700" fill="#00e6c3">Ξ</text>
        <circle cx="250" cy="140" r="9" fill="rgba(77,141,255,0.2)" stroke="#4d8dff" stroke-width="1"/>
      </g>

      <!-- type: nft -->
      <g v-else-if="type === 'nft'">
        <rect x="20" y="20" width="280" height="160" rx="12" fill="url(#ei-g3)" stroke="rgba(245,55,155,0.3)"/>
        <!-- 画框 -->
        <rect x="60" y="35" width="100" height="120" rx="8" fill="#0e1424" stroke="#f5379b" stroke-width="1.5"/>
        <rect x="72" y="47" width="76" height="80" rx="4" fill="rgba(245,55,155,0.08)"/>
        <!-- 画里的山 -->
        <path d="M72 107 L100 72 L125 95 L148 82 L148 127 L72 127 Z" fill="rgba(245,55,155,0.35)"/>
        <path d="M72 118 L95 92 L115 108 L135 90 L148 100 L148 127 L72 127 Z" fill="rgba(0,230,195,0.3)"/>
        <circle cx="130" cy="60" r="9" fill="rgba(255,207,77,0.7)"/>
        <!-- 小画框 -->
        <rect x="180" y="55" width="72" height="56" rx="6" fill="#0e1424" stroke="#7b8aab" stroke-width="1"/>
        <rect x="188" y="63" width="56" height="40" rx="3" fill="rgba(77,141,255,0.12)"/>
        <!-- 小画框 -->
        <rect x="180" y="122" width="72" height="42" rx="6" fill="#0e1424" stroke="#7b8aab" stroke-width="1"/>
        <text x="216" y="148" text-anchor="middle" font-family="monospace" font-size="10" fill="#8e9cbb">NFT #001</text>
      </g>

      <!-- type: contract 合约 -->
      <g v-else-if="type === 'contract'">
        <rect x="20" y="20" width="280" height="160" rx="12" fill="url(#ei-g1)" stroke="rgba(0,230,195,0.3)"/>
        <!-- 卷页文档 -->
        <rect x="70" y="35" width="180" height="130" rx="6" fill="#0e1424" stroke="#00e6c3" stroke-width="1.3"/>
        <path d="M220 35 L250 35 L250 65 L220 65 Z" fill="rgba(0,230,195,0.15)" stroke="#00e6c3" stroke-width="1.2"/>
        <g font-family="JetBrains Mono, Consolas, monospace" font-size="9" fill="#5a6b8a">
          <text x="86" y="62">contract MyToken {</text>
          <text x="98" y="82">string public name;</text>
          <text x="98" y="100">uint public supply;</text>
          <text x="98" y="118">function transfer(...)</text>
          <text x="112" y="136">returns (bool ok);</text>
          <text x="86" y="154">}</text>
        </g>
        <circle cx="78" cy="50" r="3" fill="#ff5470"/>
        <circle cx="92" cy="50" r="3" fill="#ffcf4d"/>
        <circle cx="106" cy="50" r="3" fill="#2dd4bf"/>
      </g>

      <!-- type: explorer 浏览器 -->
      <g v-else-if="type === 'explorer'">
        <rect x="20" y="20" width="280" height="160" rx="12" fill="url(#ei-g2)" stroke="rgba(77,141,255,0.3)"/>
        <!-- 放大镜 -->
        <circle cx="150" cy="95" r="42" fill="none" stroke="#4d8dff" stroke-width="2.5"/>
        <circle cx="150" cy="95" r="30" fill="rgba(77,141,255,0.08)"/>
        <line x1="182" y1="127" x2="215" y2="160" stroke="#00e6c3" stroke-width="5" stroke-linecap="round"/>
        <!-- 搜索栏 -->
        <rect x="60" y="30" width="200" height="22" rx="11" fill="#0e1424" stroke="rgba(77,141,255,0.5)"/>
        <circle cx="74" cy="41" r="4" fill="#4d8dff"/>
        <line x1="77" y1="44" x2="86" y2="53" stroke="#4d8dff" stroke-width="1.5" stroke-linecap="round"/>
        <rect x="94" y="36" width="150" height="3" rx="1.5" fill="rgba(123,138,171,0.4)"/>
        <!-- 区块链 -->
        <g transform="translate(60,145)">
          <rect x="0" y="0" width="44" height="24" rx="4" fill="rgba(0,230,195,0.15)" stroke="#00e6c3" stroke-width="1"/>
          <rect x="58" y="0" width="44" height="24" rx="4" fill="rgba(0,230,195,0.15)" stroke="#00e6c3" stroke-width="1"/>
          <rect x="116" y="0" width="44" height="24" rx="4" fill="rgba(0,230,195,0.15)" stroke="#00e6c3" stroke-width="1"/>
          <text x="22" y="16" text-anchor="middle" font-family="monospace" font-size="9" fill="#00e6c3">#0</text>
          <text x="80" y="16" text-anchor="middle" font-family="monospace" font-size="9" fill="#00e6c3">#1</text>
          <text x="138" y="16" text-anchor="middle" font-family="monospace" font-size="9" fill="#00e6c3">#2</text>
        </g>
      </g>

      <!-- type: default 通用 -->
      <g v-else>
        <rect x="20" y="20" width="280" height="160" rx="12" fill="url(#ei-g1)" stroke="rgba(123,138,171,0.3)"/>
        <circle cx="160" cy="95" r="36" fill="rgba(123,138,171,0.1)" stroke="rgba(123,138,171,0.5)" stroke-dasharray="4,3"/>
        <text x="160" y="95" text-anchor="middle" font-family="JetBrains Mono, monospace" font-size="22" fill="#7b8aab" dominant-baseline="central">∅</text>
      </g>
    </svg>
    <div class="msg" v-if="!hideText">
      <div class="msg-t">{{ title || defaultTitle }}</div>
      <div class="msg-s" v-if="subtitle || defaultSubtitle">{{ subtitle || defaultSubtitle }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  type?: 'chain' | 'wallet' | 'nft' | 'contract' | 'explorer' | 'default'
  title?: string
  subtitle?: string
  hideText?: boolean
}>(), {
  type: 'default',
  hideText: false,
})

const map: any = {
  chain:    ['暂无节点数据', '完成第 1 步搭链操作后，这里会显示你的联盟链状态'],
  wallet:   ['钱包空空如也', '先发行一个 ERC20 代币，再从这里进行转账交易'],
  nft:      ['还没有 NFT', '前往 NFT 市场，铸造你的第一枚数字藏品'],
  contract: ['暂无已部署合约', '进入合约 IDE，编译并部署你的第一份智能合约'],
  explorer: ['没有匹配的记录', '尝试搜索 区块高度 / 交易哈希 / 合约地址'],
  default:  ['暂无数据', '完成对应步骤后，数据会出现在这里'],
}
const defaultTitle = computed(() => map[props.type]?.[0])
const defaultSubtitle = computed(() => map[props.type]?.[1])
</script>

<style scoped lang="scss">
.dq-empty-ill {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 18px 20px 14px;
  .ill {
    width: 100%;
    max-width: 340px;
    height: auto;
  }
  .msg {
    margin-top: 14px;
    text-align: center;
    .msg-t {
      font-size: 14px;
      font-weight: 600;
      color: var(--dq-text);
      letter-spacing: 0.3px;
    }
    .msg-s {
      font-size: 12px;
      color: var(--dq-text-dim);
      margin-top: 4px;
      line-height: 1.6;
      max-width: 360px;
    }
  }
}
</style>
