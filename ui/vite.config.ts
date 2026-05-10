import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // The REPL `ui serve` command writes ui/.env.local with
  // VITE_API_BASE_URL=http://<host>:<api_port>. We proxy /api → that
  // origin so the SPA can use relative paths (`/api/v1/...`) without
  // CORS, and so Set-Cookie headers from the API land on the same
  // origin the browser already considers home (the Vite dev port).
  // In production the FastAPI server serves the SPA itself, so /api
  // is genuinely same-origin and no proxy is needed.
  const apiTarget = env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      host: process.env.TALLY_HOST ?? '127.0.0.1',
      port: Number(process.env.TALLY_VITE_PORT ?? 3000),
      proxy: {
        '/api': {
          target: apiTarget,
          // Rewrite the Host header to match the target so the API's
          // HostHeaderMiddleware allowlist accepts the proxied request.
          // The browser-set Origin header is forwarded unchanged, and
          // the Vite origin is already in the API's allowed extra
          // origins list (see effective_allowed_origins).
          changeOrigin: true,
        },
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      passWithNoTests: true,
      setupFiles: ['./tests/setup.ts'],
      include: ['tests/**/*.test.{ts,tsx}'],
      coverage: {
        provider: 'v8',
        reporter: ['text', 'lcov'],
        exclude: ['tests/**', '**/*.d.ts', '**/*.config.*'],
      },
    },
  }
})
