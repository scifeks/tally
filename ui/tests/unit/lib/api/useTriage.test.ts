import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { useTriageHistory } from '@/lib/api/useTriage'

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    wrapper: ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children),
  }
}

describe('useTriageHistory', () => {
  it('stays disabled when projectId is empty string', () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useTriageHistory(''), { wrapper })
    expect(result.current.data).toBeUndefined()
    expect(result.current.fetchStatus).toBe('idle')
  })

  it('resolves with an array when projectId is provided', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useTriageHistory('p-01'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 2000 })
    expect(Array.isArray(result.current.data)).toBe(true)
  })
})
