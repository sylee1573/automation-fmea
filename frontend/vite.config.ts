import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/setup': 'http://localhost:8000',
      '/upload': 'http://localhost:8000',
      '/generate': 'http://localhost:8000',
      '/stream': 'http://localhost:8000',
      '/download': 'http://localhost:8000',
      '/chat': 'http://localhost:8000',
      '/license': 'http://localhost:8000',
      '/session': 'http://localhost:8000',
      '/template': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
  },
})
