import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import React from 'react'
import { describe, expect, it } from 'vitest'

import { useProjectMeta } from '@/lib/api/useProjectMeta'
import { ApiError } from '@/lib/api/client'
import { server } from '../../../handlers'
import populatedFixture from '../../../fixtures/projects/meta-populated.json'

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    wrapper: ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children),
  }
}

describe('useProjectMeta', () => {
  it('maps the populated payload (project 1) to camelCase fields', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useProjectMeta('1'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const meta = result.current.data
    if (!meta) throw new Error('expected meta to be defined')
    expect(meta.id).toBe(populatedFixture.id)
    expect(meta.name).toBe(populatedFixture.name)
    expect(meta.code).toBe(populatedFixture.code)
    expect(meta.repoCount).toBe(populatedFixture.repo_count)
    expect(meta.urlListCount).toBe(populatedFixture.url_list_count)
    expect(meta.findingCount).toBe(populatedFixture.finding_count)
    expect(meta.enabledTools).toEqual(populatedFixture.enabled_tools)
    expect(meta.enabledTools).toHaveLength(populatedFixture.enabled_tools.length)
  })

  it('returns the empty / zero-count shape for project 3', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useProjectMeta('3'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const meta = result.current.data
    if (!meta) throw new Error('expected meta to be defined')
    expect(meta.repoCount).toBe(0)
    expect(meta.urlListCount).toBe(0)
    expect(meta.findingCount).toBe(0)
    expect(meta.enabledTools).toEqual([])
  })

  it('throws ApiError(status=404) when the project does not exist', async () => {
    server.use(
      http.get('/api/v1/projects/:projectId/meta', () =>
        HttpResponse.json(
          { error: { code: 'NOT_FOUND', message: 'Project 999 not found' } },
          { status: 404 }
        )
      )
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useProjectMeta('999'), { wrapper })
    await waitFor(() => expect(result.current.isError).toBe(true))

    const err = result.current.error
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).status).toBe(404)
    expect((err as ApiError).code).toBe('NOT_FOUND')
  })

  it('throws ApiError(status=500) on server error', async () => {
    server.use(
      http.get('/api/v1/projects/:projectId/meta', () =>
        HttpResponse.json({ error: { code: 'SERVER_ERROR', message: 'boom' } }, { status: 500 })
      )
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useProjectMeta('1'), { wrapper })
    await waitFor(() => expect(result.current.isError).toBe(true))

    expect(result.current.error).toBeInstanceOf(ApiError)
    expect((result.current.error as ApiError).status).toBe(500)
  })

  it('stays disabled (data undefined, fetchStatus idle) when projectIdParam is empty', () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useProjectMeta(''), { wrapper })
    expect(result.current.data).toBeUndefined()
    expect(result.current.fetchStatus).toBe('idle')
  })
})
