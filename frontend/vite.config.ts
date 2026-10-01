import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        // 把 echarts / react 生态拆成独立 chunk：页面按路由 lazy 加载时
        // 只需下载自己的代码，图表库与框架代码命中浏览器缓存
        manualChunks: {
          echarts: ['echarts'],
          react: ['react', 'react-dom', 'react-router-dom', '@tanstack/react-query'],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
      // SocketIO（推送管理页）：websocket 升级必须走 ws 代理
      '/socket.io': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
