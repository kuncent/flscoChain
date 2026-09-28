<template>
  <router-view />
  <!-- 单点登录校验中：URL 带 token 时守卫会在页面组件挂载前先把 token 换成平台 JWT（要等
       一次外部 SSO 往返），这段真空期给一条明确提示，而不是全屏空白 -->
  <div v-if="ssoRedeeming" class="sso-redeeming">
    <i class="sr-dot"></i>
    <span>正在校验单点登录凭据…</span>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAppStore } from '@/stores/app'
import { ssoRedeeming } from '@/router'

const app = useAppStore()
onMounted(() => app.refreshStatus())
</script>

<style scoped>
.sso-redeeming {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 3000;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px 0;
  background: var(--dq-bg-2);
  border-bottom: 1px solid var(--dq-border);
  color: var(--dq-text-dim);
  font-size: 12px;
  letter-spacing: 0.04em;
}
.sso-redeeming .sr-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #00e6c3;
  animation: dq-sso-pulse 1s ease-in-out infinite;
}
@keyframes dq-sso-pulse {
  0%, 100% { opacity: 0.35 }
  50% { opacity: 1 }
}
</style>
