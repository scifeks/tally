import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { useUrlLists } from '@/lib/api/useUrlLists'

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    wrapper: ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children),
  }
}

describe('useUrlLists', () => {
  it('stays disabled when projectId is empty string', () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useUrlLists(''), { wrapper })
    expect(result.current.data).toBeUndefined()
    expect(result.current.fetchStatus).toBe('idle')
  })

  it('resolves with 180 entries for p-01', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useUrlLists('1'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 2000 })
    expect(result.current.data).toHaveLength(180)
  })

  it('resolves with 42 entries for p-02', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useUrlLists('2'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 2000 })
    expect(result.current.data).toHaveLength(42)
  })

  it('resolves with 0 entries for p-03', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useUrlLists('3'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 2000 })
    expect(result.current.data).toHaveLength(0)
  })

  it('each entry has id, method, protocol, host, port, and path fields', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useUrlLists('1'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 2000 })
    const first = result.current.data![0]
    expect(typeof first.id).toBe('string')
    expect(typeof first.method).toBe('string')
    expect(typeof first.protocol).toBe('string')
    expect(typeof first.host).toBe('string')
    expect(typeof first.port).toBe('number')
    expect(typeof first.path).toBe('string')
  })
})
