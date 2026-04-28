import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { useProjects, useProjectMeta } from '@/lib/api/useProjects'

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    wrapper: ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children),
  }
}

describe('useProjects', () => {
  it('resolves with the array of projects served by the API', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useProjects(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toHaveLength(3)
  })

  it('each project has id (number), name, and code fields', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useProjects(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    for (const project of result.current.data!) {
      expect(typeof project.id).toBe('number')
      expect(typeof project.name).toBe('string')
      expect(typeof project.code).toBe('string')
    }
  })
})

describe('useProjectMeta', () => {
  it('stays disabled (data undefined) when projectId is empty string', () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useProjectMeta(''), { wrapper })
    expect(result.current.data).toBeUndefined()
    expect(result.current.fetchStatus).toBe('idle')
  })

  it('resolves with numeric repo, urlLists, and tool counts for p-01', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useProjectMeta('1'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const meta = result.current.data!
    expect(typeof meta.repositories).toBe('number')
    expect(typeof meta.urlLists).toBe('number')
    expect(typeof meta.enabledTools).toBe('number')
  })
})
