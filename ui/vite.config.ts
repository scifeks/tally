import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import fs from 'node:fs'
import path from 'node:path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // `ui serve` writes .env.local with VITE_API_BASE_URL, TLS cert
  // paths, and host/port values. The proxy forwards /api to the
  // HTTPS API server. In production FastAPI serves the SPA itself.
  const apiTarget = env.VITE_API_BASE_URL || 'https://127.0.0.1:8000'

  const tlsCert = env.TALLY_TLS_CERT
  const tlsKey = env.TALLY_TLS_KEY
  const httpsConfig =
    tlsCert && tlsKey
      ? { cert: fs.readFileSync(tlsCert), key: fs.readFileSync(tlsKey) }
      : undefined

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
      https: httpsConfig,
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
          // Accept the self-signed cert on the API server.
          secure: false,
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
