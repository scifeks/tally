import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { useScanHistory, useRunningScans, useProjectScanConfig } from '@/lib/api/useScans'

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    wrapper: ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children),
  }
}

describe('useScanHistory', () => {
  it('resolves with 9 scans for p-01', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useScanHistory('p-01'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 2000 })
    expect(result.current.data).toHaveLength(9)
  })
})

describe('useRunningScans', () => {
  it('returns only scans with status running for p-01', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useRunningScans('p-01'), { wrapper })
    await waitFor(() => {
      expect(result.current).toHaveLength(2)
    }, { timeout: 2000 })
    expect(result.current.every(s => s.status === 'running')).toBe(true)
  })
})

describe('useProjectScanConfig', () => {
  it('resolves with repos, segments, and tools arrays for p-01', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useProjectScanConfig('p-01'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 2000 })
    const config = result.current.data!
    expect(Array.isArray(config.repos)).toBe(true)
    expect(Array.isArray(config.segments)).toBe(true)
    expect(Array.isArray(config.tools)).toBe(true)
    expect(config.repos.length).toBeGreaterThan(0)
    expect(config.tools.length).toBeGreaterThan(0)
  })
})
