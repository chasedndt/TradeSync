import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Libraries every page shares get their own chunks, so a change to one page
        // does not make the browser download React or the chart library again.
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (/[\\/]node_modules[\\/](react|react-dom|react-router|react-router-dom|@remix-run|scheduler)[\\/]/.test(id)) return 'react'
          if (/[\\/]node_modules[\\/]@tanstack[\\/]/.test(id)) return 'query'
          if (/[\\/]node_modules[\\/](lightweight-charts|fancy-canvas)[\\/]/.test(id)) return 'charts'
          if (/[\\/]node_modules[\\/](lucide-react|@phosphor-icons)[\\/]/.test(id)) return 'icons'
          return undefined
        },
      },
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
})
