import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import React from 'react'
import { describe, expect, it } from 'vitest'

import { useFindings } from '@/lib/api/useFindings'
import { server } from '../../../handlers'
import populatedFixture from '../../../fixtures/findings/populated.json'
import page2Fixture from '../../../fixtures/findings/page-2.json'

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
    expect(result.current.data).toEqual([])
    expect(result.current.total).toBe(0)
    expect(result.current.fetchStatus).toBe('idle')
  })

  it('maps the populated page (snake → camel) and exposes total', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useFindings({ projectId: '1' }), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toHaveLength(populatedFixture.items.length)
    expect(result.current.total).toBe(populatedFixture.items.length)

    const first = result.current.data[0]
    expect(first.id).toBe(populatedFixture.items[0].id)
    expect(typeof first.id).toBe('number')
    expect(first.projectId).toBe(populatedFixture.items[0].project_id)
    expect(typeof first.projectId).toBe('number')
    expect(first.severity).toBe(populatedFixture.items[0].severity)
    expect(first.findingType).toEqual(populatedFixture.items[0].finding_type)
    expect(first.cwe).toEqual(populatedFixture.items[0].cwe)
    expect(first.discoveredAt).toBe(populatedFixture.items[0].first_seen)
    expect(first.isLocked).toBe(populatedFixture.items[0].is_locked)
    expect(first.lockHolder).toBe(populatedFixture.items[0].lock_holder)
  })

  it('coerces null finding_type and cwe to empty arrays', async () => {
    server.use(
      http.get('/api/v1/projects/:projectId/findings', () =>
        HttpResponse.json({
          items: [
            {
              ...populatedFixture.items[0],
              finding_type: null,
              cwe: null,
            },
          ],
          total: 1,
          offset: 0,
          limit: 50,
        })
      )
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useFindings({ projectId: '1' }), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data[0].findingType).toEqual([])
    expect(result.current.data[0].cwe).toEqual([])
  })

  it('returns an empty list when the project has no findings', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useFindings({ projectId: '3' }), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([])
    expect(result.current.total).toBe(0)
    expect(result.current.hasNextPage).toBe(false)
  })

  it('forwards filter parameters to the request URL', async () => {
    let capturedUrl: URL | null = null
    server.use(
      http.get('/api/v1/projects/:projectId/findings', ({ request }) => {
        capturedUrl = new URL(request.url)
        return HttpResponse.json({ items: [], total: 0, offset: 0, limit: 50 })
      })
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(
      () =>
        useFindings({
          projectId: '1',
          filters: {
            severity: ['critical', 'high'],
            status: ['active'],
            sort: 'severity',
            order: 'desc',
            limit: 10,
          },
        }),
      { wrapper }
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(capturedUrl).not.toBeNull()
    const params = capturedUrl!.searchParams
    expect(params.getAll('severity')).toEqual(['critical', 'high'])
    expect(params.getAll('status')).toEqual(['active'])
    expect(params.get('sort')).toBe('severity')
    expect(params.get('order')).toBe('desc')
    expect(params.get('limit')).toBe('10')
    expect(params.get('offset')).toBe('0')
  })

  it('exposes hasNextPage when the first page does not cover total', async () => {
    server.use(
      http.get('/api/v1/projects/:projectId/findings', () =>
        HttpResponse.json({
          items: populatedFixture.items,
          total: 60,
          offset: 0,
          limit: 5,
        })
      )
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(
      () => useFindings({ projectId: '1', filters: { limit: 5 } }),
      { wrapper }
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.hasNextPage).toBe(true)
  })

  it('fetchNextPage appends the next page and disables hasNextPage when total is reached', async () => {
    let calls = 0
    server.use(
      http.get('/api/v1/projects/:projectId/findings', ({ request }) => {
        calls += 1
        const url = new URL(request.url)
        const offset = Number(url.searchParams.get('offset') ?? 0)
        if (offset === 0) {
          return HttpResponse.json({
            items: populatedFixture.items,
            total: populatedFixture.items.length + page2Fixture.items.length,
            offset: 0,
            limit: populatedFixture.items.length,
          })
        }
        return HttpResponse.json({
          items: page2Fixture.items,
          total: populatedFixture.items.length + page2Fixture.items.length,
          offset: populatedFixture.items.length,
          limit: page2Fixture.items.length,
        })
      })
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(
      () => useFindings({ projectId: '1', filters: { limit: populatedFixture.items.length } }),
      { wrapper }
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toHaveLength(populatedFixture.items.length)
    expect(result.current.hasNextPage).toBe(true)

    await act(async () => {
      await result.current.fetchNextPage()
    })

    await waitFor(() =>
      expect(result.current.data.length).toBe(
        populatedFixture.items.length + page2Fixture.items.length
      )
    )
    expect(result.current.hasNextPage).toBe(false)
    expect(calls).toBe(2)
  })
})
