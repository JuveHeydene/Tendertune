import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const proxyTarget =
    env.VITE_DEV_PROXY_TARGET || env.VITE_API_BASE_URL || 'http://localhost:8000'

  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      proxy: {
        '/health': { target: proxyTarget, changeOrigin: true },
        '/auth': { target: proxyTarget, changeOrigin: true },
        '/admin': { target: proxyTarget, changeOrigin: true },
        '/dashboard': { target: proxyTarget, changeOrigin: true },
        '/documents': { target: proxyTarget, changeOrigin: true },
        '/exports': { target: proxyTarget, changeOrigin: true },
        '/conversations': { target: proxyTarget, changeOrigin: true },
        '/dossiers': { target: proxyTarget, changeOrigin: true },
      },
    },
  }
})
