import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import React from 'react'
import { describe, expect, it } from 'vitest'

import { useUrlListsFilterOptions } from '@/lib/api/useUrlListsFilterOptions'
import { server } from '../../../handlers'
import urlListFilterOptionsPopulatedFixture from '../../../fixtures/url_findings/filter-options-populated.json'

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    wrapper: ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children),
  }
}

describe('useUrlListsFilterOptions', () => {
  it('stays disabled when projectIdParam is empty string', () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useUrlListsFilterOptions(''), { wrapper })
    expect(result.current.fetchStatus).toBe('idle')
    expect(result.current.data).toBeUndefined()
  })

  it('emits `repoId` filter values as `repo_id` query params on the request URL', async () => {
    let captured: URL | null = null
    server.use(
      http.get('/api/v1/projects/:projectId/url-list/filter-options', ({ request }) => {
        captured = new URL(request.url)
        return HttpResponse.json(urlListFilterOptionsPopulatedFixture)
      })
    )

    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useUrlListsFilterOptions('1', { repoId: [1, 2] }), {
      wrapper,
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(captured).not.toBeNull()
    expect(captured!.searchParams.getAll('repo_id')).toEqual(['1', '2'])
    expect(result.current.data).toEqual(urlListFilterOptionsPopulatedFixture)
  })
})
