import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/chat': 'http://localhost:8001',
      '/health': 'http://localhost:8001',
      '/threads': 'http://localhost:8001',
      '/api': 'http://localhost:8001'
    }
  },
  build: {
    outDir: path.resolve(__dirname, '../static/app'),
    emptyOutDir: true
  }
})
