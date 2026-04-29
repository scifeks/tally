import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import Reports from '@/pages/Reports'
import { useUI } from '@/lib/store'
import { __setEventSourceFactory } from '@/lib/api/sse'
import { server } from '../../handlers'
import { MockEventSource } from '../../helpers/sse'
import { setCookie, clearAllCookies } from '../../helpers/cookies'

function renderReports() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <Reports />
      </QueryClientProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  clearAllCookies()
  setCookie('tally_csrf', 'test-csrf-token')
  MockEventSource.reset()
  __setEventSourceFactory((url, init) => new MockEventSource(url, init) as unknown as EventSource)
  window.localStorage.clear()
  useUI.setState({
    activeProjectId: null,
    findingsSegment: 'sast',
    selectedFindingIds: new Set<number>(),
    findingMutationError: null,
    scanMutationError: null,
    triageMutationError: null,
    triageInjectionAcked: false,
    triageRunStatus: 'idle',
    reportMutationError: null,
  })
})

afterEach(() => {
  __setEventSourceFactory(null)
  server.resetHandlers()
})

describe('Reports page — generate flow', () => {
  it('starts a generation, sets runId from the response, and lets SSE drive logs + status', async () => {
    useUI.setState({ activeProjectId: 1 })

    let body: Record<string, unknown> | null = null
    server.use(
      http.post('/api/v1/projects/1/reports/generate', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(
          {
            id: 5001,
            project_id: 1,
            status: 'generating',
            format: body.format,
            started_at: '2026-04-28T12:00:00+00:00',
            steps: [],
          },
          { status: 202 }
        )
      })
    )

    const user = userEvent.setup()
    renderReports()

    // Switch to a non-PDF format so the preflight gate doesn't intercept.
    const fmt = await screen.findByTestId('report-format-select')
    await user.selectOptions(fmt, 'json')

    const btn = await screen.findByTestId('report-generate-button')
    await waitFor(() => expect(btn).toBeEnabled())
    await user.click(btn)

    await waitFor(() => expect(body).not.toBeNull())
    expect(body).toMatchObject({ format: 'json' })

    // After 202 lands, the report-events SSE subscribes filtered by run_id.
    await waitFor(() =>
      expect(
        MockEventSource.instances.some(es => es.url.includes('reports/events?run_id=5001'))
      ).toBe(true)
    )

    const reportSse = MockEventSource.instances.find(es =>
      es.url.includes('reports/events?run_id=5001')
    )
    if (!reportSse) throw new Error('reports SSE never opened')
    act(() => {
      reportSse.emitTyped('step_completed', {
        id: 'evt-1',
        run_id: 5001,
        timestamp: '2026-04-28T12:00:05+00:00',
        step: 'compile',
        message: 'compiled',
        progress: 50,
      })
    })
    // PrinterAnimation also renders "PRINTING 50%" on its LCD; assert that
    // the progress label appears at least once anywhere on the page.
    await waitFor(() => expect(screen.getAllByText(/50%/).length).toBeGreaterThan(0))

    act(() => {
      reportSse.emitTyped('generation_completed', {
        id: 'evt-2',
        run_id: 5001,
        timestamp: '2026-04-28T12:00:10+00:00',
        message: 'done',
      })
    })
    await screen.findByTestId('report-reset-button')
    expect(screen.getByText(/^Complete$/)).toBeInTheDocument()
  })

  it('opens the preflight modal when format is PDF and not all drafts are ready', async () => {
    useUI.setState({ activeProjectId: 1 })
    const user = userEvent.setup()
    renderReports()

    const btn = await screen.findByTestId('report-generate-button')
    // Project 1 has 3/6 ready (executive_summary=draft, risk_level=reviewed,
    // critical_issues=draft), so PDF should gate.
    await waitFor(() =>
      expect(screen.getByText(/3 of 6 sections ready/i)).toBeInTheDocument()
    )
    expect(btn).toBeDisabled()
  })

  it('Stop button hits the cancel endpoint while a run is in flight', async () => {
    useUI.setState({ activeProjectId: 1 })

    server.use(
      http.post('/api/v1/projects/1/reports/generate', () =>
        HttpResponse.json(
          {
            id: 5050,
            project_id: 1,
            status: 'generating',
            format: 'json',
            started_at: '2026-04-28T12:00:00+00:00',
            steps: [],
          },
          { status: 202 }
        )
      )
    )
    let cancelled = false
    server.use(
      http.post('/api/v1/projects/1/reports/5050/cancel', () => {
        cancelled = true
        return HttpResponse.json({ id: 5050, status: 'cancelling' }, { status: 202 })
      })
    )

    const user = userEvent.setup()
    renderReports()

    await user.selectOptions(await screen.findByTestId('report-format-select'), 'json')
    await user.click(await screen.findByTestId('report-generate-button'))

    const stopBtn = await screen.findByTestId('report-stop-button')
    await waitFor(() => expect(stopBtn).toBeEnabled())
    await user.click(stopBtn)
    await waitFor(() => expect(cancelled).toBe(true))
  })
})

describe('Reports page — draft generation', () => {
  it('per-section Generate fires the mutation with the chosen section', async () => {
    useUI.setState({ activeProjectId: 1 })

    let body: Record<string, unknown> | null = null
    server.use(
      http.post('/api/v1/projects/1/reports/drafts', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(
          {
            section: body.section,
            status: 'generating',
            generated_at: null,
            reviewed_at: null,
            preview: null,
            word_count: null,
            uploaded_filename: null,
            error: null,
          },
          { status: 202 }
        )
      })
    )

    const user = userEvent.setup()
    renderReports()

    // The improvement_points section is `not_generated` in fixture-1 so the
    // Generate button (not the Regenerate icon) is rendered.
    const generateBtn = await screen.findByTestId('report-draft-improvement_points-generate')
    await user.click(generateBtn)

    await waitFor(() => expect(body).not.toBeNull())
    expect(body).toMatchObject({ section: 'improvement_points', force: false })
  })

  it('surfaces 409 JOB_ALREADY_RUNNING through the report-mutation-error modal', async () => {
    // Use project 99 which the MSW handler treats as the conflict trigger.
    useUI.setState({ activeProjectId: 99 })

    const user = userEvent.setup()
    renderReports()

    const generateBtn = await screen.findByTestId('report-draft-executive_summary-generate')
    await user.click(generateBtn)

    expect(
      await screen.findByRole('dialog', { name: /report action failed/i })
    ).toBeInTheDocument()
    expect(useUI.getState().reportMutationError?.code).toBe('JOB_ALREADY_RUNNING')
  })
})

describe('Reports page — DraftCard download + delete', () => {
  it('Download button on a generated draft fetches text/markdown', async () => {
    useUI.setState({ activeProjectId: 1 })
    let calledUrl: string | null = null
    server.use(
      http.get(
        '/api/v1/projects/1/reports/drafts/executive_summary/download',
        ({ request }) => {
          calledUrl = request.url
          return new HttpResponse('# hi', {
            status: 200,
            headers: { 'Content-Type': 'text/markdown' },
          })
        }
      )
    )

    const user = userEvent.setup()
    renderReports()

    await user.click(await screen.findByTestId('report-draft-executive_summary-download'))
    await waitFor(() => expect(calledUrl).toContain('reports/drafts/executive_summary/download'))
  })

  it('Delete button confirms then issues DELETE', async () => {
    useUI.setState({ activeProjectId: 1 })

    let deleted = false
    server.use(
      http.delete(
        '/api/v1/projects/1/reports/drafts/executive_summary',
        () => {
          deleted = true
          return new HttpResponse(null, { status: 204 })
        }
      )
    )

    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    renderReports()

    await user.click(await screen.findByTestId('report-draft-executive_summary-delete'))
    await waitFor(() => expect(deleted).toBe(true))
    confirmSpy.mockRestore()
  })

  it('Delete button is a no-op when the user cancels the confirm prompt', async () => {
    useUI.setState({ activeProjectId: 1 })
    let deleted = false
    server.use(
      http.delete(
        '/api/v1/projects/1/reports/drafts/executive_summary',
        () => {
          deleted = true
          return new HttpResponse(null, { status: 204 })
        }
      )
    )
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const user = userEvent.setup()
    renderReports()
    await user.click(await screen.findByTestId('report-draft-executive_summary-delete'))
    // No way to deterministically assert "didn't fire"; settle the queue and check.
    await new Promise(r => setTimeout(r, 30))
    expect(deleted).toBe(false)
    confirmSpy.mockRestore()
  })
})

describe('Reports page — HistoryTable', () => {
  it('renders the project-1 fixture row and wires the download button', async () => {
    useUI.setState({ activeProjectId: 1 })
    let calledUrl = ''
    server.use(
      http.get('/api/v1/projects/1/reports/4001/download', ({ request }) => {
        calledUrl = request.url
        return new HttpResponse(new Uint8Array([0x25, 0x50, 0x44, 0x46]), {
          status: 200,
          headers: { 'Content-Type': 'application/pdf' },
        })
      })
    )
    const user = userEvent.setup()
    renderReports()
    await user.click(await screen.findByTestId('report-history-download-4001'))
    await waitFor(() => expect(calledUrl).toContain('/projects/1/reports/4001/download'))
  })
})

describe('Reports page — draft SSE → log surface', () => {
  it('appends draft_completed events to the log panel', async () => {
    useUI.setState({ activeProjectId: 1 })
    renderReports()

    await waitFor(() =>
      expect(
        MockEventSource.instances.some(es => es.url.includes('reports/drafts/events'))
      ).toBe(true)
    )
    const draftSse = MockEventSource.instances.find(es =>
      es.url.includes('reports/drafts/events')
    )
    if (!draftSse) throw new Error('draft SSE never opened')

    act(() => {
      draftSse.emitTyped('draft_completed', {
        id: 'd-1',
        run_id: 0,
        timestamp: '2026-04-28T12:00:00+00:00',
        section: 'executive_summary',
        // Use a string that can't collide with DraftCard's "Draft Ready" badge
        // (the project-1 fixture has 2 sections in `draft` status).
        message: 'compiled the executive summary content',
        word_count: 400,
      })
    })
    expect(
      await screen.findByText(/compiled the executive summary content/i)
    ).toBeInTheDocument()
  })
})
