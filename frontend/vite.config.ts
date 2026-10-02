import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 빌드 결과는 FastAPI가 / 에서 서빙한다 (pds/service/app.py). 개발 중에는 /api 를 실행 중인 서버로 넘긴다.
export default defineConfig({
  plugins: [react()],
  build: { outDir: '../web/dist', emptyOutDir: true },
  server: { port: 5173, proxy: { '/api': 'http://127.0.0.1:9001' } },
})
