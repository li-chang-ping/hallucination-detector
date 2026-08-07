import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  // Vitest 2 bundles Vite 5 types while the application uses Vite 6; runtime APIs are compatible.
  plugins: [vue() as never],
  test: { environment: 'jsdom', globals: true },
})
