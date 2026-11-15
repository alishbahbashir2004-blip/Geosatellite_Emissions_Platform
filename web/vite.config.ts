import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies /api to uvicorn, so the client is written as if the
// two were one origin and nothing changes when it is built and served by
// FastAPI from web/dist.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } },
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
