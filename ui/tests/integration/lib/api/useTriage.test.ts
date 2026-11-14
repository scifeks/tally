import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  useTriageHistory,
  useActiveTriage,
  useLatestTriage,
  useTriageRun,
  useStartTriage,
  useCancelTriage,
  useResumeTriage,
  useTriageEvents,
} from '@/lib/api/useTriage'
import { __setEventSourceFactory } from '@/lib/api/sse'
import { useUI } from '@/lib/store'
import type { TriageLogEvent, TriageSnapshotPayload } from '@/lib/types'
import { server } from '../../../handlers'
import { MockEventSource } from '../../../helpers/sse'
import { setCookie, clearAllCookies } from '../../../helpers/cookies'

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return {
    qc,
    wrapper: ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children),
  }
}

beforeEach(() => {
  clearAllCookies()
  setCookie('tally_csrf', 'test-csrf-token')
  useUI.setState({ triageMutationError: null })
  MockEventSource.reset()
  __setEventSourceFactory(
    (url, init) => new MockEventSource(url, init) as unknown as EventSource
  )
})

afterEach(() => {
  __setEventSourceFactory(null)
  server.resetHandlers()
})

// --- useTriageHistory ---

describe('useTriageHistory', () => {
  it('resolves with the project-1 fixture (3 runs)', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useTriageHistory(1), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 2000 })
    expect(result.current.data).toHaveLength(3)
    expect(result.current.total).toBe(3)
    // Mapper translates scan_run_id to scanRunId
    expect(result.current.data[0].scanRunId).toBe(1)
  })

  it('returns an empty list for project 3', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useTriageHistory(3), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toHaveLength(0)
    expect(result.current.total).toBe(0)
  })

  it('forwards offset and limit to the backend', async () => {
    let capturedOffset: string | null = null
    let capturedLimit: string | null = null
    server.use(
      http.get('/api/v1/projects/:projectId/triage', ({ request }) => {
        const url = new URL(request.url)
        capturedOffset = url.searchParams.get('offset')
        capturedLimit = url.searchParams.get('limit')
        return HttpResponse.json({ items: [], total: 0, offset: 0, limit: 5 })
      })
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useTriageHistory(1, { limit: 5 }), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(capturedOffset).toBe('0')
    expect(capturedLimit).toBe('5')
  })

  it('stays disabled when projectId is 0', () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useTriageHistory(0), { wrapper })
    expect(result.current.fetchStatus).toBe('idle')
  })
})

// --- useActiveTriage ---

describe('useActiveTriage', () => {
  it('resolves with the running fixture for project 1', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useActiveTriage(1), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 2000 })
    expect(result.current.data?.scanRunId).toBe(1)
    expect(result.current.data?.status).toBe('running')
  })

  it('resolves with null when the backend body is null', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useActiveTriage(2), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toBeNull()
  })
})

// --- useLatestTriage ---

describe('useLatestTriage', () => {
  it('resolves with the latest fixture for project 1', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useLatestTriage(1), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 2000 })
    expect(result.current.data?.scanRunId).toBe(1)
    expect(result.current.data?.status).toBe('done')
  })

  it('resolves with null on 404 (project has no history)', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useLatestTriage(3), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 2000 })
    expect(result.current.data).toBeNull()
  })
})

// --- useTriageRun (detail) ---

describe('useTriageRun', () => {
  it('resolves with batches for an existing run', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useTriageRun(1, 1), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.batches).toHaveLength(3)
    expect(result.current.data?.batches?.[0].id).toBe(7001)
    expect(result.current.data?.batches?.[0].findingIds).toEqual([1, 2, 3, 4, 5])
  })

  it('stays disabled when scanRunId is null', () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useTriageRun(1, null), { wrapper })
    expect(result.current.fetchStatus).toBe('idle')
  })

  it('resolves with a queued placeholder on 404', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(
      () => useTriageRun(1, 997),
      { wrapper },
    )
    await waitFor(
      () => expect(result.current.isSuccess).toBe(true),
      { timeout: 2000 },
    )
    expect(result.current.data).toMatchObject({
      scanRunId: 997,
      projectId: 1,
      status: 'queued',
      totalFindings: 0,
      processedFindings: 0,
      batches: [],
    })
  })
})

// --- useStartTriage ---

describe('useStartTriage', () => {
  it('always sends acknowledge_injection_risk: true in the body', async () => {
    let capturedBody: Record<string, unknown> = {}
    server.use(
      http.post('/api/v1/projects/:projectId/triage', async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(
          {
            scan_run_id: 2010,
            project_id: 1,
            status: 'queued',
            started_at: null,
            finished_at: null,
            total_findings: 0,
            processed_findings: 0,
          },
          { status: 202 }
        )
      })
    )
    const { wrapper } = makeWrapper()
    const mut = renderHook(() => useStartTriage(), { wrapper })
    await act(async () => {
      await mut.result.current.mutateAsync({ projectId: 1 })
    })
    expect(capturedBody.acknowledge_injection_risk).toBe(true)
    expect(capturedBody).not.toHaveProperty('finding_ids')
  })

  it('omits finding_ids when caller passes none', async () => {
    let capturedBody: Record<string, unknown> = {}
    server.use(
      http.post('/api/v1/projects/:projectId/triage', async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(
          {
            scan_run_id: 1,
            project_id: 1,
            status: 'queued',
            started_at: null,
            finished_at: null,
            total_findings: 0,
            processed_findings: 0,
          },
          { status: 202 }
        )
      })
    )
    const { wrapper } = makeWrapper()
    const mut = renderHook(() => useStartTriage(), { wrapper })
    await act(async () => {
      await mut.result.current.mutateAsync({ projectId: 1, options: {} })
    })
    expect(capturedBody).not.toHaveProperty('finding_ids')
  })

  it('forwards finding_ids when caller passes them', async () => {
    let capturedBody: Record<string, unknown> = {}
    server.use(
      http.post('/api/v1/projects/:projectId/triage', async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(
          {
            scan_run_id: 1,
            project_id: 1,
            status: 'queued',
            started_at: null,
            finished_at: null,
            total_findings: 1,
            processed_findings: 0,
          },
          { status: 202 }
        )
      })
    )
    const { wrapper } = makeWrapper()
    const mut = renderHook(() => useStartTriage(), { wrapper })
    await act(async () => {
      await mut.result.current.mutateAsync({
        projectId: 1,
        options: { findingIds: [42, 43] },
      })
    })
    expect(capturedBody).toMatchObject({
      acknowledge_injection_risk: true,
      finding_ids: [42, 43],
    })
  })

  it('routes a 409 JOB_ALREADY_RUNNING into triageMutationError', async () => {
    const { wrapper } = makeWrapper()
    const mut = renderHook(() => useStartTriage(), { wrapper })
    await act(async () => {
      try {
        await mut.result.current.mutateAsync({ projectId: 99 })
      } catch {
        /* expected */
      }
    })
    await waitFor(() => expect(mut.result.current.isError).toBe(true))
    const err = useUI.getState().triageMutationError
    expect(err?.code).toBe('JOB_ALREADY_RUNNING')
    expect(err?.status).toBe(409)
  })

  it('routes a 404 NOT_FOUND into triageMutationError', async () => {
    const { wrapper } = makeWrapper()
    const mut = renderHook(() => useStartTriage(), { wrapper })
    await act(async () => {
      try {
        await mut.result.current.mutateAsync({ projectId: 98 })
      } catch {
        /* expected */
      }
    })
    await waitFor(() => expect(mut.result.current.isError).toBe(true))
    const err = useUI.getState().triageMutationError
    expect(err?.code).toBe('NOT_FOUND')
    expect(err?.status).toBe(404)
  })
})

// --- useCancelTriage ---

describe('useCancelTriage', () => {
  it('POSTs to the cancel endpoint and returns the cancelling status', async () => {
    const { wrapper } = makeWrapper()
    const mut = renderHook(() => useCancelTriage(), { wrapper })
    let resolved: unknown
    await act(async () => {
      resolved = await mut.result.current.mutateAsync({ projectId: 1, scanRunId: 1 })
    })
    expect(resolved).toMatchObject({ scan_run_id: 1, status: 'cancelling' })
  })

  it('routes a 409 TRIAGE_NOT_CANCELLABLE into the error slice', async () => {
    const { wrapper } = makeWrapper()
    const mut = renderHook(() => useCancelTriage(), { wrapper })
    await act(async () => {
      try {
        await mut.result.current.mutateAsync({ projectId: 1, scanRunId: 999 })
      } catch {
        /* expected */
      }
    })
    await waitFor(() => expect(mut.result.current.isError).toBe(true))
    expect(useUI.getState().triageMutationError?.code).toBe('TRIAGE_NOT_CANCELLABLE')
  })

  it('optimistically sets active run status to cancelling', async () => {
    const { qc, wrapper } = makeWrapper()
    qc.setQueryData(['triage', 1, 'active'], {
      scanRunId: 1,
      projectId: 1,
      status: 'running',
      startedAt: null,
      finishedAt: null,
      totalFindings: 10,
      processedFindings: 0,
    })
    const mut = renderHook(() => useCancelTriage(), { wrapper })
    await act(async () => {
      await mut.result.current.mutateAsync({
        projectId: 1,
        scanRunId: 1,
      })
    })
    const cached = qc.getQueryData(['triage', 1, 'active']) as {
      status: string
    } | null
    expect(cached?.status).toBe('cancelling')
  })
})

// --- useResumeTriage ---

describe('useResumeTriage', () => {
  it('always sends acknowledge_injection_risk: true in the body', async () => {
    let capturedBody: Record<string, unknown> = {}
    server.use(
      http.post(
        '/api/v1/projects/:projectId/triage/:scanRunId/resume',
        async ({ request }) => {
          capturedBody = (await request.json()) as Record<string, unknown>
          return HttpResponse.json(
            {
              scan_run_id: 2010,
              project_id: 1,
              status: 'running',
              started_at: '2026-04-28T11:00:00Z',
              finished_at: null,
              total_findings: 18,
              processed_findings: 7,
            },
            { status: 202 }
          )
        }
      )
    )
    const { wrapper } = makeWrapper()
    const mut = renderHook(() => useResumeTriage(), { wrapper })
    await act(async () => {
      await mut.result.current.mutateAsync({ projectId: 1, scanRunId: 2010 })
    })
    expect(capturedBody).toEqual({ acknowledge_injection_risk: true })
  })

  it('routes a 409 TRIAGE_NOT_RESUMABLE into the error slice', async () => {
    const { wrapper } = makeWrapper()
    const mut = renderHook(() => useResumeTriage(), { wrapper })
    await act(async () => {
      try {
        await mut.result.current.mutateAsync({ projectId: 1, scanRunId: 998 })
      } catch {
        /* expected */
      }
    })
    await waitFor(() => expect(mut.result.current.isError).toBe(true))
    expect(useUI.getState().triageMutationError?.code).toBe('TRIAGE_NOT_RESUMABLE')
  })
})

// --- useTriageEvents ---

describe('useTriageEvents', () => {
  it('opens an EventSource scoped to the given scan_run_id', () => {
    const { wrapper } = makeWrapper()
    renderHook(() => useTriageEvents(1, () => undefined, { scanRunId: 2010 }), {
      wrapper,
    })
    expect(MockEventSource.instances).toHaveLength(1)
    expect(MockEventSource.instances[0].url).toContain('/projects/1/triage/events')
    expect(MockEventSource.instances[0].url).toContain('scan_run_id=2010')
  })

  it('does not open a connection when scanRunId is null', () => {
    const { wrapper } = makeWrapper()
    renderHook(() => useTriageEvents(1, () => undefined, { scanRunId: null }), {
      wrapper,
    })
    expect(MockEventSource.instances).toHaveLength(0)
  })

  it('does not open a connection when projectId is 0', () => {
    const { wrapper } = makeWrapper()
    renderHook(() => useTriageEvents(0, () => undefined, { scanRunId: 2010 }), {
      wrapper,
    })
    expect(MockEventSource.instances).toHaveLength(0)
  })

  it('routes snapshot frames to onSnapshot, not to onEvent', () => {
    const events: TriageLogEvent[] = []
    const snaps: TriageSnapshotPayload[] = []
    const { wrapper } = makeWrapper()
    renderHook(
      () =>
        useTriageEvents(1, e => events.push(e), {
          scanRunId: 2010,
          onSnapshot: s => snaps.push(s),
        }),
      { wrapper }
    )
    const es = MockEventSource.instances[0]
    act(() => {
      es.emitTyped('snapshot', {
        project_id: 1,
        scan_run_id: 2010,
        status: 'running',
        total_findings: 5,
        processed_findings: 2,
        started_at: '2026-04-28T11:00:00Z',
        finished_at: null,
        batches: [],
      })
    })
    expect(events).toHaveLength(0)
    expect(snaps).toHaveLength(1)
    expect(snaps[0]).toMatchObject({ scanRunId: 2010, status: 'running' })
  })

  it('maps each typed event payload to a TriageLogEvent', () => {
    const events: TriageLogEvent[] = []
    const { wrapper } = makeWrapper()
    renderHook(() => useTriageEvents(1, e => events.push(e), { scanRunId: 2010 }), {
      wrapper,
    })
    const es = MockEventSource.instances[0]
    act(() => {
      es.emitTyped('run_started', {
        id: 'evt-1',
        scan_run_id: 2010,
        project_id: 1,
        timestamp: '2026-04-28T11:00:00Z',
        message: 'starting',
      })
      es.emitTyped('batch_progress', {
        id: 'evt-2',
        scan_run_id: 2010,
        project_id: 1,
        timestamp: '2026-04-28T11:01:00Z',
        batch_id: 7001,
        processed_count: 3,
        total_count: 5,
        message: '3/5',
      })
      es.emitTyped('triage_failed', {
        id: 'evt-3',
        scan_run_id: 2010,
        project_id: 1,
        timestamp: '2026-04-28T11:02:00Z',
        error: 'Claude crashed',
        failed_at_finding_id: 4711,
        completed_count: 7,
        total_count: 18,
        resumable: true,
        message: 'failed',
      })
    })
    expect(events).toHaveLength(3)
    expect(events[0]).toMatchObject({
      type: 'run_started',
      scanRunId: 2010,
      projectId: 1,
      message: 'starting',
    })
    expect(events[1]).toMatchObject({
      type: 'batch_progress',
      batchId: 7001,
      processedCount: 3,
      totalCount: 5,
    })
    expect(events[2]).toMatchObject({
      type: 'triage_failed',
      error: 'Claude crashed',
      failedAtFindingId: 4711,
      processedCount: 7,
      totalCount: 18,
      resumable: true,
    })
  })
})
