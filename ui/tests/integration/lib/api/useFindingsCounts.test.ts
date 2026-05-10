import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import React from 'react'
import { describe, expect, it } from 'vitest'

import { useFindingsCounts } from '@/lib/api/useFindingsCounts'
import { ApiError } from '@/lib/api/client'
import { server } from '../../../handlers'
import populatedFixture from '../../../fixtures/findings/counts-populated.json'

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    wrapper: ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children),
  }
}

describe('useFindingsCounts', () => {
  it('maps the populated payload (project 1) to camelCase fields', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useFindingsCounts('1'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const counts = result.current.data
    if (!counts) throw new Error('expected counts to be defined')
    expect(counts.total).toBe(populatedFixture.total)
    expect(counts.scansCount).toBe(populatedFixture.scans_count)
    expect(counts.reposCount).toBe(populatedFixture.repos_count)
    expect(counts.urlsCount).toBe(populatedFixture.urls_count)
    expect(counts.lastScanAt).toBe(populatedFixture.last_scan_at)
    expect(counts.lastTriageAt).toBe(populatedFixture.last_triage_at)
    expect(counts.bySeverityStatus.critical.active).toBe(
      populatedFixture.by_severity_status.critical.active
    )
    expect(counts.bySeverityStatus.high.active).toBe(
      populatedFixture.by_severity_status.high.active
    )
    expect(counts.bySeverity.critical).toBe(populatedFixture.by_severity.critical)
    expect(counts.byStatus.active).toBe(populatedFixture.by_status.active)
  })

  it('returns the all-zero / null-timestamp shape for project 3', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useFindingsCounts('3'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const counts = result.current.data
    if (!counts) throw new Error('expected counts to be defined')
    expect(counts.total).toBe(0)
    expect(counts.scansCount).toBe(0)
    expect(counts.reposCount).toBe(0)
    expect(counts.urlsCount).toBe(0)
    expect(counts.lastScanAt).toBeNull()
    expect(counts.lastTriageAt).toBeNull()
    expect(counts.bySeverityStatus.critical.active).toBe(0)
    expect(counts.bySeverityStatus.high.active).toBe(0)
  })

  it('throws ApiError(status=404) when the project does not exist', async () => {
    server.use(
      http.get('/api/v1/projects/:projectId/findings/counts', () =>
        HttpResponse.json(
          { error: { code: 'NOT_FOUND', message: 'Project 999 not found' } },
          { status: 404 }
        )
      )
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useFindingsCounts('999'), { wrapper })
    await waitFor(() => expect(result.current.isError).toBe(true))

    const err = result.current.error
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).status).toBe(404)
    expect((err as ApiError).code).toBe('NOT_FOUND')
  })

  it('throws ApiError(status=500) on server error', async () => {
    server.use(
      http.get('/api/v1/projects/:projectId/findings/counts', () =>
        HttpResponse.json({ error: { code: 'SERVER_ERROR', message: 'boom' } }, { status: 500 })
      )
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useFindingsCounts('1'), { wrapper })
    await waitFor(() => expect(result.current.isError).toBe(true))

    expect(result.current.error).toBeInstanceOf(ApiError)
    expect((result.current.error as ApiError).status).toBe(500)
  })

  it('stays disabled (data undefined, fetchStatus idle) when projectIdParam is empty', () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useFindingsCounts(''), { wrapper })
    expect(result.current.data).toBeUndefined()
    expect(result.current.fetchStatus).toBe('idle')
  })
})
