import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { useProjects } from '@/lib/api/useProjects'

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
    const projects = result.current.data
    if (!projects) throw new Error('expected projects to be defined')
    for (const project of projects) {
      expect(typeof project.id).toBe('number')
      expect(typeof project.name).toBe('string')
      expect(typeof project.code).toBe('string')
    }
  })
})
