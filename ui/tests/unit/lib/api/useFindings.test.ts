import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { useFindings } from '@/lib/api/useFindings'

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    wrapper: ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children),
  }
}

describe('useFindings', () => {
  it('stays disabled when projectId is empty string', () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useFindings({ projectId: '' }), { wrapper })
    expect(result.current.data).toBeUndefined()
    expect(result.current.fetchStatus).toBe('idle')
  })

  it('resolves with 220 findings for p-01', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useFindings({ projectId: 'p-01' }), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 2000 })
    expect(result.current.data).toHaveLength(220)
  })

  it('resolves with 35 findings for p-02', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useFindings({ projectId: 'p-02' }), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 2000 })
    expect(result.current.data).toHaveLength(35)
  })

  it('resolves with 0 findings for p-03', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useFindings({ projectId: 'p-03' }), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 2000 })
    expect(result.current.data).toHaveLength(0)
  })

  it('filters by segment when segment option is provided', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(
      () => useFindings({ projectId: 'p-01', segment: 'sast' }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 2000 })
    const findings = result.current.data!
    expect(findings.length).toBeGreaterThan(0)
    expect(findings.every(f => f.segment === 'sast')).toBe(true)
  })

  it('each finding has id, severity, status, segment, and tool fields', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useFindings({ projectId: 'p-01' }), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 2000 })
    const first = result.current.data![0]
    expect(typeof first.id).toBe('string')
    expect(typeof first.severity).toBe('string')
    expect(typeof first.status).toBe('string')
    expect(typeof first.segment).toBe('string')
    expect(typeof first.tool).toBe('string')
  })
})
