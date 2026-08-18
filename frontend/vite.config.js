import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiBase = (env.VITE_API_BASE || 'http://localhost:8000').replace('localhost', '127.0.0.1')
  const wsBase = apiBase.replace(/^http/, 'ws')
  return {
    base: './',
    plugins: [
      vue(),
      AutoImport({ resolvers: [ElementPlusResolver()] }),
      Components({ resolvers: [ElementPlusResolver()] }),
    ],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
        // asyncPage.loadingComponent 内部用 template 写了渲染函数
        // 生产版 vue 不支持运行时编译，必须显式别名到 esm-bundler（或改用 render 函数）
        'vue': 'vue/dist/vue.esm-bundler.js',
      },
    },
    server: {
      host: '0.0.0.0',
      port: 5173,
      strictPort: true,
      proxy: {
        '/api/cloud/ws': { target: wsBase, ws: true, changeOrigin: true },
        '/api':          { target: apiBase, changeOrigin: true },
        '/static':       { target: apiBase, changeOrigin: true },
        '/health':       { target: apiBase, changeOrigin: true },
        '/docs':         { target: apiBase, changeOrigin: true },
        '/openapi.json': { target: apiBase, changeOrigin: true },
      },
      // 让 HMR（热更新 WebSocket）自动跟随当前浏览器访问的 host/port，
      // 这样不管是访问 localhost / 192.168.x.x / 穿透域名（HTTPS 443）都能正常连接
      hmr: {
        protocol: undefined,
        host: undefined,
        clientPort: undefined,
      },
      allowedHosts: true,
    },
  }
})
