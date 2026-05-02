import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import React from 'react'
import { describe, expect, it } from 'vitest'

import { useRuntimeDependencies, useInstalledTools } from '@/lib/api/useRuntime'
import { server } from '../../../handlers'

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    wrapper: ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children),
  }
}

describe('useRuntimeDependencies', () => {
  it('reshapes binary_path / install_hint / required_for and drops the wire keys', async () => {
    server.use(
      http.get('/api/v1/runtime-dependencies', () =>
        HttpResponse.json({
          dependencies: [
            {
              name: 'claude',
              installed: true,
              binary_path: '/usr/local/bin/claude',
              version: '1.0.0',
              install_hint: 'see docs',
              required_for: ['triage'],
              error: null,
            },
            {
              name: 'gitleaks',
              installed: false,
              binary_path: null,
              version: null,
              install_hint: 'brew install gitleaks',
              required_for: ['scan'],
              error: 'not on PATH',
            },
          ],
        })
      )
    )

    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useRuntimeDependencies(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const deps = result.current.data!.dependencies
    expect(deps).toHaveLength(2)
    expect(deps[0]).toEqual({
      name: 'claude',
      installed: true,
      binaryPath: '/usr/local/bin/claude',
      version: '1.0.0',
      installHint: 'see docs',
      requiredFor: ['triage'],
      error: null,
    })
    expect(deps[1]).toEqual({
      name: 'gitleaks',
      installed: false,
      binaryPath: null,
      version: null,
      installHint: 'brew install gitleaks',
      requiredFor: ['scan'],
      error: 'not on PATH',
    })

    const wireBleed = deps[0] as unknown as Record<string, unknown>
    expect(wireBleed.binary_path).toBeUndefined()
    expect(wireBleed.install_hint).toBeUndefined()
    expect(wireBleed.required_for).toBeUndefined()
  })
})

describe('useInstalledTools', () => {
  it('passes the wire payload through unchanged', async () => {
    const payload = { installed: ['claude', 'semgrep', 'gitleaks'] }
    server.use(http.get('/api/v1/tools/installed', () => HttpResponse.json(payload)))

    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useInstalledTools(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual(payload)
    expect(Object.keys(result.current.data!)).toEqual(['installed'])
  })
})

describe('useRuntimeDependencies + useInstalledTools', () => {
  it('have independent query keys: one failing does not gate the other', async () => {
    server.use(
      http.get('/api/v1/runtime-dependencies', () =>
        HttpResponse.json({ code: 'BOOM', message: 'down' }, { status: 500 })
      ),
      http.get('/api/v1/tools/installed', () =>
        HttpResponse.json({ installed: ['claude'] })
      )
    )

    const { wrapper } = makeWrapper()
    const { result } = renderHook(
      () => ({
        deps: useRuntimeDependencies(),
        tools: useInstalledTools(),
      }),
      { wrapper }
    )

    await waitFor(() => {
      expect(result.current.deps.isError).toBe(true)
      expect(result.current.tools.isSuccess).toBe(true)
    })
    expect(result.current.tools.data).toEqual({ installed: ['claude'] })
  })
})
