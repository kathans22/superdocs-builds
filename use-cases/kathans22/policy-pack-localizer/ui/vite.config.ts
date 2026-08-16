import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Dev-only proxy to the FastAPI backend (see src/localizer/api/), so
    // the browser sees same-origin requests and the backend needs no CORS
    // config. Run `uvicorn localizer.api.app:app --port 8000` alongside
    // `npm run dev` for this to resolve.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
