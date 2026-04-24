import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: process.env.TALLY_HOST ?? '127.0.0.1',
    port: Number(process.env.TALLY_VITE_PORT ?? 3000),
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
})
