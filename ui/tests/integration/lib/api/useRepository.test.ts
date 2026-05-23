import { afterEach, describe, expect, it } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import React from 'react'
import { useRepository } from '@/lib/api/useConfig'
import { server } from '../../../handlers'
import repoFixture from '../../../fixtures/config/repository.json'

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
      http.get('/api/v1/projects/1/repositories/1', () => HttpResponse.json(repoFixture))
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useRepository(1, 1), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 2000 })
    expect(result.current.data?.id).toBe(1)
    expect(result.current.data?.projectId).toBe(1)
    expect(result.current.data?.name).toBe('dvwa')
    expect(result.current.data?.services[0].baseUrls).toEqual(['http://localhost:4280'])
    expect(result.current.data?.services[0].locationMode).toBe('docker')
    expect(result.current.data).not.toHaveProperty('auth')
    expect(result.current.data?.endpointFile).toBe('dvna_oas3.json')
  })

  it('maps endpoint_file → endpointFile when the API supplies a value', async () => {
    server.use(
      http.get('/api/v1/projects/1/repositories/1', () =>
        HttpResponse.json({ ...repoFixture, endpoint_file: 'spec.json' })
      )
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useRepository(1, 1), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 2000 })
    expect(result.current.data?.endpointFile).toBe('spec.json')
  })
})
