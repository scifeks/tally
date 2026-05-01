import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  useScanHistory,
  useRunningScans,
  useProjectScanConfig,
  useStartScan,
  useCancelScan,
  useScanEvents,
  useRunningScansCount,
  type SnapshotPayload,
} from '@/lib/api/useScans'
import { __setEventSourceFactory } from '@/lib/api/sse'
import { useUI } from '@/lib/store'
import { server } from '../../../handlers'
import { MockEventSource } from '../../../helpers/sse'
import { setCookie, clearAllCookies } from '../../../helpers/cookies'
import type { ScanLogEvent } from '@/lib/types'

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
  useUI.setState({ scanMutationError: null })
  MockEventSource.reset()
  __setEventSourceFactory(
    (url, init) => new MockEventSource(url, init) as unknown as EventSource
  )
})

afterEach(() => {
  __setEventSourceFactory(null)
  server.resetHandlers()
})

describe('useScanHistory', () => {
  it('resolves with 4 scans for p-01', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useScanHistory(1), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 2000 })
    expect(result.current.data).toHaveLength(4)
    expect(result.current.total).toBe(4)
  })

  it('forwards the status filter to the backend', async () => {
    let capturedStatus: string | null = null
    server.use(
      http.get('/api/v1/projects/:projectId/scans', ({ request }) => {
        const url = new URL(request.url)
        capturedStatus = url.searchParams.get('status')
        return HttpResponse.json({ items: [], total: 0, offset: 0, limit: 20 })
      })
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useScanHistory(1, { status: 'running' }), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(capturedStatus).toBe('running')
  })

  it('returns an empty list for project 3', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useScanHistory(3), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toHaveLength(0)
    expect(result.current.total).toBe(0)
  })
})

describe('useRunningScans', () => {
  it('returns only scans with status running for p-01', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useRunningScans(1), { wrapper })
    await waitFor(() => {
      expect(result.current).toHaveLength(1)
    }, { timeout: 2000 })
    expect(result.current.every(s => s.status === 'running')).toBe(true)
  })
})

describe('useProjectScanConfig', () => {
  it('resolves with repos, segments, and tools arrays for p-01', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useProjectScanConfig(1), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 2000 })
    const config = result.current.data!
    expect(config.repos.length).toBeGreaterThan(0)
    expect(config.tools.length).toBeGreaterThan(0)
  })

  it('returns empty repos for project 3', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useProjectScanConfig(3), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data!.repos).toHaveLength(0)
  })
})

describe('useStartScan', () => {
  it('POSTs camelCase body and resolves with mapped Scan', async () => {
    let capturedBody: unknown = null
    server.use(
      http.post('/api/v1/projects/:projectId/scans', async ({ request }) => {
        capturedBody = await request.json()
        return HttpResponse.json(
          {
            id: 5000,
            project_id: 1,
            status: 'queued',
            started_at: '2026-04-28T12:00:00Z',
            finished_at: null,
            repo_ids: ['dvwa'],
            tool_ids: ['semgrep'],
            domains: ['sast'],
            findings_count: null,
            skip_enrichment: true,
          },
          { status: 202 }
        )
      })
    )

    const { wrapper } = makeWrapper()
    const mut = renderHook(() => useStartScan(), { wrapper })
    let resolved: unknown
    await act(async () => {
      resolved = await mut.result.current.mutateAsync({
        projectId: 1,
        options: { repoIds: [1, 2], toolIds: ['semgrep'], skipEnrichment: true },
      })
    })

    expect(capturedBody).toMatchObject({
      repoIds: [1, 2],
      toolIds: ['semgrep'],
      skipEnrichment: true,
    })
    expect(resolved).toMatchObject({
      id: 5000,
      projectId: 1,
      status: 'queued',
      skipEnrichment: true,
    })
  })

  it('renames segments → domains when serialising the body', async () => {
    let capturedBody: Record<string, unknown> = {}
    server.use(
      http.post('/api/v1/projects/:projectId/scans', async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(
          {
            id: 1,
            project_id: 1,
            status: 'queued',
            started_at: null,
            finished_at: null,
            repo_ids: [],
            tool_ids: [],
            domains: ['sast'],
            findings_count: null,
            skip_enrichment: false,
          },
          { status: 202 }
        )
      })
    )
    const { wrapper } = makeWrapper()
    const mut = renderHook(() => useStartScan(), { wrapper })
    await act(async () => {
      await mut.result.current.mutateAsync({
        projectId: 1,
        options: { segments: ['sast', 'web'] },
      })
    })
    expect(capturedBody).toHaveProperty('domains', ['sast', 'web'])
    expect(capturedBody).not.toHaveProperty('segments')
  })

  it('omits empty option arrays from the request body', async () => {
    let capturedBody: Record<string, unknown> = {}
    server.use(
      http.post('/api/v1/projects/:projectId/scans', async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(
          {
            id: 1,
            project_id: 1,
            status: 'queued',
            started_at: null,
            finished_at: null,
            repo_ids: [],
            tool_ids: [],
            domains: [],
            findings_count: null,
            skip_enrichment: false,
          },
          { status: 202 }
        )
      })
    )
    const { wrapper } = makeWrapper()
    const mut = renderHook(() => useStartScan(), { wrapper })
    await act(async () => {
      await mut.result.current.mutateAsync({ projectId: 1, options: {} })
    })
    expect(capturedBody).toEqual({})
  })

  it('invalidates the scan-history cache on success', async () => {
    const { qc, wrapper } = makeWrapper()
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    const mut = renderHook(() => useStartScan(), { wrapper })
    await act(async () => {
      await mut.result.current.mutateAsync({ projectId: 1, options: {} })
    })
    expect(
      invalidate.mock.calls.some(call => {
        const filter = call[0] as { queryKey?: unknown[] } | undefined
        return (
          Array.isArray(filter?.queryKey) &&
          filter!.queryKey[0] === 'scans' &&
          filter!.queryKey[1] === 1
        )
      })
    ).toBe(true)
  })

  it('routes a 409 conflict into the scanMutationError slice', async () => {
    server.use(
      http.post('/api/v1/projects/:projectId/scans', () =>
        HttpResponse.json(
          {
            error: {
              code: 'SCAN_ALREADY_RUNNING',
              message: 'a scan is already running',
              details: {},
            },
          },
          { status: 409 }
        )
      )
    )
    const { wrapper } = makeWrapper()
    const mut = renderHook(() => useStartScan(), { wrapper })
    await act(async () => {
      try {
        await mut.result.current.mutateAsync({ projectId: 1, options: {} })
      } catch {
        /* expected */
      }
    })
    await waitFor(() => expect(mut.result.current.isError).toBe(true))
    const err = useUI.getState().scanMutationError
    expect(err?.code).toBe('SCAN_ALREADY_RUNNING')
    expect(err?.status).toBe(409)
  })
})

describe('useCancelScan', () => {
  it('POSTs to the cancel endpoint and returns the cancelling status', async () => {
    const { wrapper } = makeWrapper()
    const mut = renderHook(() => useCancelScan(), { wrapper })
    let resolved: unknown
    await act(async () => {
      resolved = await mut.result.current.mutateAsync({ projectId: 1, runId: 2000 })
    })
    expect(resolved).toMatchObject({ id: 2000, status: 'cancelling' })
  })

  it('routes errors into the scanMutationError slice', async () => {
    server.use(
      http.post('/api/v1/projects/:projectId/scans/:runId/cancel', () =>
        HttpResponse.json(
          {
            error: { code: 'SCAN_NOT_FOUND', message: 'not found', details: {} },
          },
          { status: 404 }
        )
      )
    )
    const { wrapper } = makeWrapper()
    const mut = renderHook(() => useCancelScan(), { wrapper })
    await act(async () => {
      try {
        await mut.result.current.mutateAsync({ projectId: 1, runId: 999 })
      } catch {
        /* expected */
      }
    })
    await waitFor(() => expect(mut.result.current.isError).toBe(true))
    expect(useUI.getState().scanMutationError?.code).toBe('SCAN_NOT_FOUND')
  })
})

describe('useScanEvents', () => {
  it('opens an EventSource for the project scan-events endpoint', () => {
    const { wrapper } = makeWrapper()
    renderHook(() => useScanEvents(1, () => undefined), { wrapper })
    expect(MockEventSource.instances).toHaveLength(1)
    expect(MockEventSource.instances[0].url).toContain('/projects/1/scans/events')
  })

  it('does not open a connection when projectId is 0', () => {
    const { wrapper } = makeWrapper()
    renderHook(() => useScanEvents(0, () => undefined), { wrapper })
    expect(MockEventSource.instances).toHaveLength(0)
  })

  it('maps each typed event payload to a ScanLogEvent', () => {
    const events: ScanLogEvent[] = []
    const { wrapper } = makeWrapper()
    renderHook(() => useScanEvents(1, e => events.push(e)), { wrapper })
    const es = MockEventSource.instances[0]

    act(() => {
      es.emitTyped('run_started', { run_id: 7, project_id: 1, message: 'starting' })
      es.emitTyped('tool_started', {
        run_id: 7,
        project_id: 1,
        segment: 'sast',
        repo: 'dvwa',
        tool: 'semgrep',
        message: 'running semgrep',
      })
      es.emitTyped('tool_completed', {
        run_id: 7,
        project_id: 1,
        segment: 'sast',
        repo: 'dvwa',
        tool: 'semgrep',
        message: 'done',
        findings_count: 3,
        duration: 12.5,
        exit_code: 0,
      })
      es.emitTyped('run_completed', {
        run_id: 7,
        project_id: 1,
        message: 'scan complete',
        findings_count: 3,
      })
    })

    expect(events).toHaveLength(4)
    expect(events[0]).toMatchObject({ type: 'run_started', runId: 7, message: 'starting' })
    expect(events[1]).toMatchObject({
      type: 'tool_started',
      runId: 7,
      tool: 'semgrep',
      repo: 'dvwa',
      segment: 'sast',
    })
    expect(events[2]).toMatchObject({
      type: 'tool_completed',
      findingsCount: 3,
      duration: 12.5,
      exitCode: 0,
    })
    expect(events[3]).toMatchObject({ type: 'run_completed' })
  })

  it('forwards every event to the consumer (latest-value-wins is the page consumer\'s job)', () => {
    const events: ScanLogEvent[] = []
    const { wrapper } = makeWrapper()
    renderHook(() => useScanEvents(1, e => events.push(e)), { wrapper })
    const es = MockEventSource.instances[0]

    act(() => {
      for (let i = 1; i <= 5; i++) {
        es.emitTyped('enrichment_progress', {
          run_id: 7,
          project_id: 1,
          enriched_count: i,
          total_to_enrich: 5,
          message: `${i}/5`,
        })
      }
    })

    // The hook itself just forwards; the page is responsible for the
    // single-state-slot replacement that satisfies §12.7.
    expect(events).toHaveLength(5)
    expect(events.every(e => e.type === 'enrichment_progress')).toBe(true)
    expect(events[4].enrichedCount).toBe(5)
  })

  it('forwards snapshot payloads to onSnapshot, not to onEvent', () => {
    const events: ScanLogEvent[] = []
    const snaps: SnapshotPayload[] = []
    const { wrapper } = makeWrapper()
    renderHook(
      () => useScanEvents(1, e => events.push(e), { onSnapshot: s => snaps.push(s) }),
      { wrapper }
    )
    const es = MockEventSource.instances[0]
    act(() => {
      es.emitTyped('snapshot', { run_id: null, project_id: 1, active_run_ids: [7, 9] })
      es.emitTyped('snapshot', {
        run_id: 7,
        project_id: 1,
        status: 'running',
        progress: 40,
        current_segment: 'sast',
        segment_label: '3/14',
      })
    })

    expect(events).toHaveLength(0)
    expect(snaps).toHaveLength(2)
    expect(snaps[0]).toMatchObject({ runId: null, activeRunIds: [7, 9] })
    expect(snaps[1]).toMatchObject({ runId: 7, status: 'running', progress: 40 })
  })
})

describe('useRunningScansCount', () => {
  it('returns 0 and skips the subscription when projectId is null', () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useRunningScansCount(null), { wrapper })
    expect(result.current).toBe(0)
    expect(MockEventSource.instances).toHaveLength(0)
  })

  it('seeds count from the snapshot then increments/decrements on lifecycle events', () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useRunningScansCount(1), { wrapper })

    const es = MockEventSource.instances[0]

    act(() => {
      es.emitTyped('snapshot', { run_id: null, project_id: 1, active_run_ids: [10, 11] })
    })
    expect(result.current).toBe(2)

    act(() => {
      es.emitTyped('run_started', { run_id: 12, project_id: 1, message: '' })
    })
    expect(result.current).toBe(3)

    act(() => {
      es.emitTyped('run_completed', { run_id: 10, project_id: 1, message: '' })
    })
    expect(result.current).toBe(2)

    act(() => {
      es.emitTyped('run_cancelled', { run_id: 11, project_id: 1, message: '' })
    })
    expect(result.current).toBe(1)
  })

  it('decrements on run_failed (regression for the missing event-type entry)', () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useRunningScansCount(1), { wrapper })
    const es = MockEventSource.instances[0]
    act(() => {
      es.emitTyped('snapshot', { run_id: null, project_id: 1, active_run_ids: [42] })
    })
    expect(result.current).toBe(1)
    act(() => {
      es.emitTyped('run_failed', { run_id: 42, project_id: 1, message: 'boom' })
    })
    expect(result.current).toBe(0)
  })
})
