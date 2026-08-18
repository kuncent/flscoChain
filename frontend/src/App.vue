<template>
  <router-view />
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAppStore } from '@/stores/app'

const app = useAppStore()
onMounted(() => app.refreshStatus())
</script>
