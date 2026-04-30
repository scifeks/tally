import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import React from 'react'
import { describe, expect, it } from 'vitest'

import { mapUrlEntry, useUrlLists } from '@/lib/api/useUrlLists'
import { server } from '../../../handlers'
import urlListProject1Fixture from '../../../fixtures/url-list-project-1.json'

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
    expect(result.current.data).toEqual([])
    expect(result.current.total).toBe(0)
    expect(result.current.fetchStatus).toBe('idle')
  })

  it('returns the first page of mapped entries for project 1', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useUrlLists('1'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toHaveLength(100)
    expect(result.current.total).toBe(180)
    expect(result.current.hasNextPage).toBe(true)
  })

  it('maps snake_case wire shape to camelCase UrlEntry', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useUrlLists('1'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const first = result.current.data[0]
    const wire = urlListProject1Fixture.items[0]

    expect(first.id).toBe(wire.id)
    expect(typeof first.id).toBe('number')
    expect(first.projectId).toBe(wire.project_id)
    expect(typeof first.projectId).toBe('number')
    expect(first.repoId).toBe(wire.repo_id)
    expect(first.repoName).toBe(wire.repo_name)
    expect(first.source).toBe(wire.source)
    expect(first.tool).toBe(wire.tool)
    expect(first.runId).toBe(wire.run_id)
    expect(first.filePath).toBe(wire.file_path)
    expect(first.createdAt).toBe(wire.created_at)
    expect(first.meta).toEqual(wire.meta)
  })

  it('mapUrlEntry coerces a single wire row directly', () => {
    const wire = {
      id: 99,
      project_id: 7,
      repo_id: 3,
      repo_name: 'gateway',
      source: 'user' as const,
      tool: null,
      run_id: null,
      method: 'POST',
      protocol: 'https',
      host: 'example.com',
      port: 443,
      path: '/api/v1/foo',
      file_path: 'endpoints/openapi.yaml',
      meta: { upload_format: 'openapi3' },
      created_at: '2026-04-26T10:00:00Z',
    }
    const mapped = mapUrlEntry(wire)
    expect(mapped.id).toBe(99)
    expect(mapped.projectId).toBe(7)
    expect(mapped.repoName).toBe('gateway')
    expect(mapped.source).toBe('user')
    expect(mapped.tool).toBeNull()
    expect(mapped.runId).toBeNull()
    expect(mapped.filePath).toBe('endpoints/openapi.yaml')
  })

  it('returns empty array with hasNextPage=false for project with no urls', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useUrlLists('3'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual([])
    expect(result.current.total).toBe(0)
    expect(result.current.hasNextPage).toBe(false)
  })

  it('forwards offset and limit query params', async () => {
    let capturedUrl: URL | null = null
    server.use(
      http.get('/api/v1/projects/:projectId/url-list/entries', ({ request }) => {
        capturedUrl = new URL(request.url)
        return HttpResponse.json({ items: [], total: 0, offset: 0, limit: 25 })
      })
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useUrlLists('1', { limit: 25 }), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(capturedUrl).not.toBeNull()
    const params = capturedUrl!.searchParams
    expect(params.get('limit')).toBe('25')
    expect(params.get('offset')).toBe('0')
  })

  it('forwards multi-value method filter as repeated query params', async () => {
    let capturedUrl: URL | null = null
    server.use(
      http.get('/api/v1/projects/:projectId/url-list/entries', ({ request }) => {
        capturedUrl = new URL(request.url)
        return HttpResponse.json({ items: [], total: 0, offset: 0, limit: 100 })
      })
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(
      () =>
        useUrlLists('1', {
          filters: { method: ['GET', 'POST'], repoId: [1, 2] },
        }),
      { wrapper }
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(capturedUrl).not.toBeNull()
    expect(capturedUrl!.searchParams.getAll('method')).toEqual(['GET', 'POST'])
    expect(capturedUrl!.searchParams.getAll('repo_id')).toEqual(['1', '2'])
  })

  it('forwards search, sort, and order params', async () => {
    let capturedUrl: URL | null = null
    server.use(
      http.get('/api/v1/projects/:projectId/url-list/entries', ({ request }) => {
        capturedUrl = new URL(request.url)
        return HttpResponse.json({ items: [], total: 0, offset: 0, limit: 100 })
      })
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(
      () =>
        useUrlLists('1', {
          filters: { search: 'admin' },
          sort: 'host',
          order: 'desc',
        }),
      { wrapper }
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(capturedUrl!.searchParams.get('search')).toBe('admin')
    expect(capturedUrl!.searchParams.get('sort')).toBe('host')
    expect(capturedUrl!.searchParams.get('order')).toBe('desc')
  })

  it('fetchNextPage appends the next page and clears hasNextPage at total', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useUrlLists('1'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toHaveLength(100)
    expect(result.current.hasNextPage).toBe(true)

    await act(async () => {
      await result.current.fetchNextPage()
    })

    await waitFor(() => expect(result.current.data.length).toBe(180))
    expect(result.current.hasNextPage).toBe(false)
    expect(result.current.total).toBe(180)
  })
})
