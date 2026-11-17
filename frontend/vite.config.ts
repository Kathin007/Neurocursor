import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import { defineConfig } from 'vitest/config'

const BACKEND = 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, './src') } },
  // Fixed port: Tauri's devUrl points here.
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': BACKEND,
      '/ws': { target: BACKEND, ws: true },
    },
  },
  test: {
    environment: 'jsdom',
    testTimeout: 20000, // the Recharts/Motion screens are slow to render when the machine is busy
    setupFiles: ['./src/test-setup.ts'],
  },
})

