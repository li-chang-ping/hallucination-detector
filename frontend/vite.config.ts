import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    host: '127.0.0.1',
    port: 5173,
    // 本地单用户服务必须在端口冲突时立即失败，避免浏览器命中旧进程。
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
