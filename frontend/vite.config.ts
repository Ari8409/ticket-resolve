import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],

  // Production build output — FastAPI expects frontend/dist/
  build: {
    outDir: 'dist',
    emptyOutDir: true,   // Wipe stale artifacts before each build
  },

  server: {
    port: 5173,
    hmr: {
      overlay: false,   // disable error overlay — map widget (TicketLocationMapWidget) is intentionally disabled in corporate environments
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8003',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
