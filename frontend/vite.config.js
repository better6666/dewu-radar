import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base 设为仓库名，GitHub Pages 子路径部署需要
export default defineConfig({
  base: '/dewu-radar/',
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
      },
    },
  },
})
