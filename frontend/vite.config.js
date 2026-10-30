import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    // Same-origin /api calls in dev, so the app code never hardcodes a backend URL.
    // Inside compose the backend is reachable by service name, not localhost.
    proxy: {
      '/api': process.env.API_PROXY_TARGET || 'http://localhost:8000',
    },
    // Windows bind mounts don't forward file events into the container.
    watch: { usePolling: process.env.VITE_USE_POLLING === 'true' },
  },
})
