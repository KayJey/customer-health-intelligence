import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The dashboard calls /api/*; in dev it is proxied to the Flask backend.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': 'http://localhost:5001' } },
})
