import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  useReportDrafts,
  useReportHistory,
  useLatestReport,
  useGenerateDrafts,
  useUploadDraft,
  useDeleteDraft,
  useGenerateReport,
  useCancelReport,
  useReportEvents,
  useReportDraftEvents,
  downloadDraftSection,
  downloadReportFile,
} from '@/lib/api/useReports'
import { __setEventSourceFactory } from '@/lib/api/sse'
import { useUI } from '@/lib/store'
import type { ReportLogEvent } from '@/lib/types'
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
  useUI.setState({ reportMutationError: null })
  MockEventSource.reset()
  __setEventSourceFactory(
    (url, init) => new MockEventSource(url, init) as unknown as EventSource
  )
})

afterEach(() => {
  __setEventSourceFactory(null)
  server.resetHandlers()
})

// ─── useReportDrafts ────────────────────────────────────────────────────────

describe('useReportDrafts', () => {
  it('resolves with the project-1 fixture (5 sections, mapped)', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useReportDrafts(1), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const drafts = result.current.data ?? []
    expect(drafts).toHaveLength(5)
    const exec = drafts.find(d => d.section === 'executive-summary')
    expect(exec?.status).toBe('draft')
    expect(exec?.wordCount).toBe(412)
    expect(exec?.generatedAt).toBe('2026-04-30T23:02:16.579444+00:00')
    expect(drafts.find(d => d.section === 'risk-level')?.uploadedFilename).toBe(
      'risk-level-reviewed.md'
    )
  })

  it('stays idle when projectId is null', () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useReportDrafts(null), { wrapper })
    expect(result.current.fetchStatus).toBe('idle')
  })
})

// ─── useReportHistory ───────────────────────────────────────────────────────

describe('useReportHistory', () => {
  it('returns project-1 history with entries mapped to integer ids', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useReportHistory(1), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toHaveLength(2)
    expect(result.current.total).toBe(2)
    expect(result.current.data[0].id).toBe(4001)
    expect(result.current.data[0].projectId).toBe(2)
  })

  it('is empty for project 2', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useReportHistory(2), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toHaveLength(0)
    expect(result.current.total).toBe(0)
  })

  it('forwards offset and limit', async () => {
    let capturedOffset: string | null = null
    let capturedLimit: string | null = null
    server.use(
      http.get('/api/v1/projects/:projectId/reports', ({ request }) => {
        const url = new URL(request.url)
        capturedOffset = url.searchParams.get('offset')
        capturedLimit = url.searchParams.get('limit')
        return HttpResponse.json({ items: [], total: 0, offset: 0, limit: 5 })
      })
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useReportHistory(1, { limit: 5 }), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(capturedOffset).toBe('0')
    expect(capturedLimit).toBe('5')
  })
})

// ─── useLatestReport ────────────────────────────────────────────────────────

describe('useLatestReport', () => {
  it('returns the latest fixture for project 1', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useLatestReport(1), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.id).toBe(4001)
    expect(result.current.data?.projectId).toBe(2)
  })

  it('treats 404 as a null result (no history yet)', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useLatestReport(3), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toBeNull()
  })
})

// ─── useGenerateDrafts ──────────────────────────────────────────────────────

describe('useGenerateDrafts', () => {
  it('posts { sections, force } and returns mapped drafts', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      http.post('/api/v1/projects/:projectId/reports/drafts', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(
          {
            drafts: [
              {
                section: 'executive-summary',
                status: 'generating',
                generated_at: null,
                reviewed_at: null,
                preview: null,
                word_count: null,
                uploaded_filename: null,
                error: null,
              },
              {
                section: 'risk-level',
                status: 'queued',
                generated_at: null,
                reviewed_at: null,
                preview: null,
                word_count: null,
                uploaded_filename: null,
                error: null,
              },
            ],
          },
          { status: 202 }
        )
      })
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useGenerateDrafts(), { wrapper })
    let resolved: unknown = null
    await act(async () => {
      resolved = await result.current.mutateAsync({
        projectId: 1,
        sections: ['executive-summary', 'risk-level'],
        force: true,
      })
    })
    expect(body).toEqual({ sections: ['executive-summary', 'risk-level'], force: true })
    expect(resolved).toEqual([
      expect.objectContaining({ section: 'executive-summary', status: 'generating' }),
      expect.objectContaining({ section: 'risk-level', status: 'queued' }),
    ])
  })

  it('routes a 409 JOB_ALREADY_RUNNING through setReportMutationError', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useGenerateDrafts(), { wrapper })
    await act(async () => {
      await result.current
        .mutateAsync({ projectId: 99, sections: ['executive-summary'] })
        .catch(() => undefined)
    })
    const err = useUI.getState().reportMutationError
    expect(err?.code).toBe('JOB_ALREADY_RUNNING')
    expect(err?.status).toBe(409)
  })

  it('routes a 422 VALIDATION_ERROR through setReportMutationError', async () => {
    server.use(
      http.post(
        '/api/v1/projects/:projectId/reports/drafts',
        async () =>
          new HttpResponse(
            JSON.stringify({
              error: { code: 'VALIDATION_ERROR', message: 'bad section', details: {} },
            }),
            { status: 422, headers: { 'Content-Type': 'application/json' } }
          )
      )
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useGenerateDrafts(), { wrapper })
    await act(async () => {
      await result.current
        .mutateAsync({ projectId: 1, sections: ['executive-summary'] })
        .catch(() => undefined)
    })
    expect(useUI.getState().reportMutationError?.code).toBe('VALIDATION_ERROR')
  })
})

// ─── useUploadDraft ─────────────────────────────────────────────────────────

describe('useUploadDraft', () => {
  it('POSTs multipart/form-data with the section + file fields', async () => {
    // jsdom's `File` isn't a real `File` per undici's parser, so we can't
    // call `request.formData()` here. Instead verify the request hit, the
    // method is POST, and the Content-Type begins with "multipart/form-data".
    let calledMethod: string | null = null
    let contentType: string | null = null
    server.use(
      http.post(
        '/api/v1/projects/:projectId/reports/drafts/upload',
        ({ request }) => {
          calledMethod = request.method
          contentType = request.headers.get('Content-Type')
          return HttpResponse.json({
            section: 'risk-level',
            status: 'reviewed',
            generated_at: null,
            reviewed_at: '2026-04-28T13:00:00+00:00',
            preview: null,
            word_count: 200,
            uploaded_filename: 'rl.md',
            error: null,
          })
        }
      )
    )
    const file = new File(['# hi'], 'rl.md', { type: 'text/markdown' })
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useUploadDraft(), { wrapper })
    await act(async () => {
      await result.current.mutateAsync({ projectId: 1, section: 'risk-level', file })
    })
    expect(calledMethod).toBe('POST')
    expect(contentType).toMatch(/^multipart\/form-data/)
  })
})

// ─── useDeleteDraft ─────────────────────────────────────────────────────────

describe('useDeleteDraft', () => {
  it('issues DELETE and resolves to undefined on 204', async () => {
    let calledMethod: string | null = null
    server.use(
      http.delete(
        '/api/v1/projects/:projectId/reports/drafts/:section',
        ({ request }) => {
          calledMethod = request.method
          return new HttpResponse(null, { status: 204 })
        }
      )
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useDeleteDraft(), { wrapper })
    await act(async () => {
      await result.current.mutateAsync({ projectId: 1, section: 'critical-issues' })
    })
    expect(calledMethod).toBe('DELETE')
  })
})

// ─── useGenerateReport ──────────────────────────────────────────────────────

describe('useGenerateReport', () => {
  it('serializes camelCase variables to snake_case wire body', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      http.post('/api/v1/projects/:projectId/reports/generate', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(
          {
            id: 5001,
            project_id: 1,
            status: 'generating',
            format: 'pdf',
            testing_type: 'grey_box',
            engagement_date: '2026-04-28',
            started_at: '2026-04-28T12:00:00+00:00',
            finished_at: null,
            output_path: null,
            error: null,
            steps: [],
          },
          { status: 202 }
        )
      })
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useGenerateReport(), { wrapper })
    let run: unknown = null
    await act(async () => {
      run = await result.current.mutateAsync({
        projectId: 1,
        format: 'pdf',
        testingType: 'grey_box',
        engagementDate: '2026-04-28',
        companyName: 'ACME',
        skipTriage: true,
      })
    })
    expect(body).toEqual({
      format: 'pdf',
      testing_type: 'grey_box',
      engagement_date: '2026-04-28',
      company_name: 'ACME',
      skip_triage: true,
    })
    expect(run).toMatchObject({ id: 5001, projectId: 1, status: 'generating' })
  })

  it('routes 409 JOB_ALREADY_RUNNING through the report-mutation slice', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useGenerateReport(), { wrapper })
    await act(async () => {
      await result.current
        .mutateAsync({ projectId: 99, format: 'pdf' })
        .catch(() => undefined)
    })
    expect(useUI.getState().reportMutationError?.code).toBe('JOB_ALREADY_RUNNING')
  })

  it('omits empty companyName from the wire body', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      http.post('/api/v1/projects/:projectId/reports/generate', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(
          {
            id: 5002,
            project_id: 1,
            status: 'generating',
            format: 'json',
            started_at: '2026-04-28T12:00:00+00:00',
          },
          { status: 202 }
        )
      })
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useGenerateReport(), { wrapper })
    await act(async () => {
      await result.current.mutateAsync({
        projectId: 1,
        format: 'json',
        companyName: '',
      })
    })
    expect(body).not.toHaveProperty('company_name')
  })
})

// ─── useCancelReport ────────────────────────────────────────────────────────

describe('useCancelReport', () => {
  it('returns the cancel response on 202', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useCancelReport(), { wrapper })
    let resp: unknown = null
    await act(async () => {
      resp = await result.current.mutateAsync({ projectId: 1, reportId: 4003 })
    })
    expect(resp).toEqual({ id: 4003, status: 'cancelling' })
  })

  it('routes 409 REPORT_NOT_CANCELLABLE through the report-mutation slice', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useCancelReport(), { wrapper })
    await act(async () => {
      await result.current
        .mutateAsync({ projectId: 1, reportId: 999 })
        .catch(() => undefined)
    })
    expect(useUI.getState().reportMutationError?.code).toBe('REPORT_NOT_CANCELLABLE')
  })
})

// ─── useReportEvents ────────────────────────────────────────────────────────

describe('useReportEvents', () => {
  it('routes typed events through the onEvent callback (with snake→camel)', async () => {
    const seen: ReportLogEvent[] = []
    const { wrapper } = makeWrapper()
    renderHook(
      () =>
        useReportEvents(1, e => seen.push(e), {
          enabled: true,
          runId: 5001,
        }),
      { wrapper }
    )
    await waitFor(() => expect(MockEventSource.instances.length).toBe(1))
    const es = MockEventSource.instances[0]
    expect(es.url).toContain('/projects/1/reports/events?run_id=5001')
    es.emitTyped('generation_started', {
      id: 'evt-1',
      run_id: 5001,
      timestamp: '2026-04-28T12:00:00+00:00',
      message: 'starting',
    })
    es.emitTyped('step_completed', {
      id: 'evt-2',
      run_id: 5001,
      timestamp: '2026-04-28T12:00:05+00:00',
      step: 'compile',
      progress: 50,
      message: 'compiled',
    })
    expect(seen).toHaveLength(2)
    expect(seen[0]).toMatchObject({ type: 'generation_started', runId: 5001 })
    expect(seen[1]).toMatchObject({ type: 'step_completed', progress: 50 })
  })

  it('does not subscribe when enabled is false', () => {
    const { wrapper } = makeWrapper()
    renderHook(() => useReportEvents(1, () => undefined, { enabled: false }), { wrapper })
    expect(MockEventSource.instances).toHaveLength(0)
  })

  it('does not subscribe when projectId is null', () => {
    const { wrapper } = makeWrapper()
    renderHook(() => useReportEvents(null, () => undefined), { wrapper })
    expect(MockEventSource.instances).toHaveLength(0)
  })

  it('omits run_id query param when runId is not provided', async () => {
    const { wrapper } = makeWrapper()
    renderHook(() => useReportEvents(1, () => undefined), { wrapper })
    await waitFor(() => expect(MockEventSource.instances.length).toBe(1))
    expect(MockEventSource.instances[0].url).not.toContain('run_id=')
  })
})

// ─── useReportDraftEvents ───────────────────────────────────────────────────

describe('useReportDraftEvents', () => {
  it('routes draft_* events and forwards optional section param', async () => {
    const seen: ReportLogEvent[] = []
    const { wrapper } = makeWrapper()
    renderHook(
      () =>
        useReportDraftEvents(1, e => seen.push(e), {
          section: 'executive-summary',
        }),
      { wrapper }
    )
    await waitFor(() => expect(MockEventSource.instances.length).toBe(1))
    const es = MockEventSource.instances[0]
    expect(es.url).toContain('/projects/1/reports/drafts/events?section=executive-summary')
    es.emitTyped('draft_completed', {
      id: 'd-1',
      run_id: 7,
      timestamp: '2026-04-28T12:00:10+00:00',
      section: 'executive-summary',
      message: 'done',
    })
    expect(seen).toHaveLength(1)
    expect(seen[0]).toMatchObject({ type: 'draft_completed', section: 'executive-summary' })
  })
})

// ─── download helpers ──────────────────────────────────────────────────────

describe('downloadDraftSection', () => {
  it('fetches text/markdown via apiFetch (parseAs blob) and triggers a download', async () => {
    let acceptHeader: string | null = null
    server.use(
      http.get(
        '/api/v1/projects/:projectId/reports/drafts/:section/download',
        ({ request }) => {
          acceptHeader = request.headers.get('Accept')
          return new HttpResponse('# hello', {
            status: 200,
            headers: { 'Content-Type': 'text/markdown' },
          })
        }
      )
    )
    await downloadDraftSection(1, 'executive-summary')
    expect(acceptHeader).toBe('text/markdown')
  })
})

describe('downloadReportFile', () => {
  it('fetches the binary report blob without forcing an Accept header', async () => {
    let calledUrl = ''
    server.use(
      http.get(
        '/api/v1/projects/:projectId/reports/:reportId/download',
        ({ request }) => {
          calledUrl = request.url
          return new HttpResponse(new Uint8Array([0x25, 0x50, 0x44, 0x46]), {
            status: 200,
            headers: { 'Content-Type': 'application/pdf' },
          })
        }
      )
    )
    await downloadReportFile(1, 4001, 'acme.pdf')
    expect(calledUrl).toContain('/projects/1/reports/4001/download')
  })
})
