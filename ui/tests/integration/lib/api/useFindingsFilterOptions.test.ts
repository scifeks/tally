import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import React from 'react'
import { describe, expect, it } from 'vitest'

import { useFindingsFilterOptions } from '@/lib/api/useFindingsFilterOptions'
import type { FindingFilters } from '@/lib/api/useFindings'
import { server } from '../../../handlers'

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    wrapper: ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children),
  }
}

describe('useFindingsFilterOptions', () => {
  it('stays disabled when projectIdParam is empty string', () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useFindingsFilterOptions(''), { wrapper })
    expect(result.current.fetchStatus).toBe('idle')
    expect(result.current.data).toBeUndefined()
  })

  it('renames the wire `finding_type` key to `findingType` on the FE shape', async () => {
    server.use(
      http.get('/api/v1/projects/:projectId/findings/filter-options', () =>
        HttpResponse.json({
          severity: [],
          status: [],
          confidence: [],
          domain: [],
          segment: [],
          tool: [],
          finding_type: [{ value: 'XSS', count: 3 }],
          repo: [],
        })
      )
    )

    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useFindingsFilterOptions('1'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.findingType).toEqual([{ value: 'XSS', count: 3 }])
    const wireKey = (result.current.data as unknown as { finding_type?: unknown }).finding_type
    expect(wireKey).toBeUndefined()
  })

  it('refetches when filters change because the filter set is part of the query key', async () => {
    server.use(
      http.get('/api/v1/projects/:projectId/findings/filter-options', ({ request }) => {
        const sev = new URL(request.url).searchParams.getAll('severity')
        const tag = sev.includes('critical') ? 'CRITICAL_TAG' : 'HIGH_TAG'
        return HttpResponse.json({
          severity: [],
          status: [],
          confidence: [],
          domain: [],
          segment: [],
          tool: [],
          finding_type: [{ value: tag, count: 1 }],
          repo: [],
        })
      })
    )

    const { wrapper } = makeWrapper()
    const { result, rerender } = renderHook(
      ({ filters }: { filters: FindingFilters }) => useFindingsFilterOptions('1', filters),
      { wrapper, initialProps: { filters: { severity: ['critical'] } } }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.findingType[0].value).toBe('CRITICAL_TAG')

    rerender({ filters: { severity: ['high'] } })

    await waitFor(() => expect(result.current.data?.findingType[0].value).toBe('HIGH_TAG'))
  })
})
