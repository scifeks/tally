import { afterEach, describe, expect, it } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import React from 'react'
import { useRepository } from '@/lib/api/useConfig'
import { server } from '../../../handlers'
import repoFixture from '../../../fixtures/repository.json'

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    wrapper: ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children),
  }
}

describe('useRepository', () => {
  afterEach(() => server.resetHandlers())

  it('stays disabled when projectId or repoId is zero', () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useRepository(0, 0), { wrapper })
    expect(result.current.fetchStatus).toBe('idle')
  })

  it('GETs /projects/:id/repositories/:repo_id and maps to the camelCase domain type', async () => {
    server.use(
      http.get('/api/v1/projects/1/repositories/42', () => HttpResponse.json(repoFixture))
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useRepository(1, 42), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 2000 })
    expect(result.current.data?.id).toBe(42)
    expect(result.current.data?.projectId).toBe(1)
    expect(result.current.data?.name).toBe('dvwa')
    expect(result.current.data?.baseUrls).toEqual(['http://localhost:8080'])
    expect(result.current.data?.locationMode).toBe('local')
    expect(result.current.data).not.toHaveProperty('auth')
    // endpoint_file is null in the fixture, so the camelCase field is absent.
    expect(result.current.data?.endpointFile).toBeUndefined()
  })

  it('maps endpoint_file → endpointFile when the API supplies a value', async () => {
    server.use(
      http.get('/api/v1/projects/1/repositories/42', () =>
        HttpResponse.json({ ...repoFixture, endpoint_file: 'spec.json' })
      )
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useRepository(1, 42), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 2000 })
    expect(result.current.data?.endpointFile).toBe('spec.json')
  })
})
