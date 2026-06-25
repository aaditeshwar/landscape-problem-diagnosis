import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const base = env.VITE_BASE_PATH || '/'
  const apiPrefix = `${base.replace(/\/?$/, '')}/api`

  return {
    base,
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      proxy: {
        [apiPrefix]: {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
          rewrite: (path) => path.replace(new RegExp(`^${apiPrefix.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`), '/api'),
        },
      },
    },
  }
})
