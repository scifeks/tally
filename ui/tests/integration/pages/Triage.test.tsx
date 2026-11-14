import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { render, screen, act, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import Triage from '@/pages/Triage'
import { useUI } from '@/lib/store'
import { __setEventSourceFactory } from '@/lib/api/sse'
import { server } from '../../handlers'
import { MockEventSource } from '../../helpers/sse'
import { setCookie, clearAllCookies } from '../../helpers/cookies'
import runtimeDepsClaudeMissing from '../../fixtures/runtime/deps-claude-missing.json'

function renderTriage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <Triage />
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
  })
})

afterEach(() => {
  __setEventSourceFactory(null)
  server.resetHandlers()
})

describe('Triage page - Claude missing gate', () => {
  it('disables Start Triage and renders the install warning', async () => {
    server.use(
      http.get('/api/v1/runtime-dependencies', () =>
        HttpResponse.json(runtimeDepsClaudeMissing)
      )
    )
    useUI.setState({ activeProjectId: 2, triageInjectionAcked: true })
    renderTriage()
    expect(await screen.findByText(/claude cli not installed/i)).toBeInTheDocument()
    expect(await screen.findByTestId('triage-start-button')).toBeDisabled()
  })
})

describe('Triage page - start mutation flow', () => {
  it('opens the prompt-injection modal on first click and fires Start after accept', async () => {
    useUI.setState({ activeProjectId: 2 })

    let startBody: Record<string, unknown> | null = null
    server.use(
      http.post('/api/v1/projects/2/triage', async ({ request }) => {
        startBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(
          {
            scan_run_id: 2099,
            project_id: 2,
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

    const user = userEvent.setup()
    renderTriage()

    const startBtn = await screen.findByTestId('triage-start-button')
    await waitFor(() => expect(startBtn).toBeEnabled())
    await user.click(startBtn)

    expect(
      await screen.findByRole('dialog', { name: /prompt injection risk/i })
    ).toBeInTheDocument()
    expect(startBody).toBeNull()

    await user.click(screen.getByRole('button', { name: /accept & continue/i }))

    await waitFor(() => expect(startBody).not.toBeNull())
    expect(startBody).toMatchObject({ acknowledge_injection_risk: true })
    expect(startBody).not.toHaveProperty('finding_ids')
    expect(useUI.getState().triageInjectionAcked).toBe(true)
  })

  it('fires the Start mutation immediately when the ack is already set', async () => {
    useUI.setState({ activeProjectId: 2, triageInjectionAcked: true })

    let postCount = 0
    server.use(
      http.post('/api/v1/projects/2/triage', () => {
        postCount += 1
        return HttpResponse.json(
          {
            scan_run_id: 2099,
            project_id: 2,
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

    const user = userEvent.setup()
    renderTriage()

    const startBtn = await screen.findByTestId('triage-start-button')
    await waitFor(() => expect(startBtn).toBeEnabled())
    await user.click(startBtn)
    expect(
      screen.queryByRole('dialog', { name: /prompt injection risk/i })
    ).not.toBeInTheDocument()
    await waitFor(() => expect(postCount).toBe(1))
  })
})

describe('Triage page - active run', () => {
  it('renders the running state and a working Stop button', async () => {
    useUI.setState({ activeProjectId: 1, triageInjectionAcked: true })
    let cancelCalled = false
    server.use(
      http.post('/api/v1/projects/1/triage/1/cancel', () => {
        cancelCalled = true
        return HttpResponse.json(
          { scan_run_id: 1, status: 'cancelling' },
          { status: 202 }
        )
      })
    )

    const user = userEvent.setup()
    renderTriage()

    const stopBtn = await screen.findByTestId('triage-stop-button')
    await user.click(stopBtn)
    await waitFor(() => expect(cancelCalled).toBe(true))
  })

  it('updates the batches map in place from SSE lifecycle events', async () => {
    useUI.setState({ activeProjectId: 1, triageInjectionAcked: true })
    renderTriage()

    // Detail fixture seeds 4 batches; B-7001 and B-7002 should render.
    await screen.findByText(/B-7001/i)
    expect(screen.getByText(/B-7002/i)).toBeInTheDocument()

    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1))
    const es = MockEventSource.instances[0]
    // Event's scan_run_id must match the run this page is watching (fixture
    // seeds project 1 with scan_run_id=1); otherwise the run-scoped
    // handleEvent gate drops it.
    act(() => {
      es.emitTyped('batch_completed', {
        id: 'evt-c-7002',
        scan_run_id: 1,
        project_id: 1,
        timestamp: '2026-04-28T11:05:00Z',
        batch_id: 7002,
        segment: 'web',
        message: 'B-7002 complete',
      })
    })

    // After the SSE event, batch 7002 transitions from "in progress" to
    // "completed". The fixture already has B-7001 completed, so we
    // expect at least 2 batch rows to show "completed" and the log to
    // show the new event message.
    await waitFor(() => {
      const completed = screen.getAllByText(/^completed$/i)
      expect(completed.length).toBeGreaterThanOrEqual(2)
    })
    expect(screen.getByText(/B-7002 complete/)).toBeInTheDocument()
  })

  it('shows only new batches after Reset + Start (attempt boundary)', async () => {
    useUI.setState({ activeProjectId: 1, triageInjectionAcked: true })

    server.use(
      http.get('/api/v1/capabilities', () =>
        HttpResponse.json({ triageBackendLabel: 'ollama' })
      ),
      http.get('/api/v1/projects/1/triage/active', () =>
        HttpResponse.json({
          scan_run_id: 1,
          project_id: 1,
          status: 'done',
          started_at: '2026-04-30T22:50:34.903973+00:00',
          finished_at: '2026-04-30T23:02:16.579444+00:00',
          total_findings: 572,
          processed_findings: 142,
        })
      ),
      http.get('/api/v1/projects/:projectId/triage/:scanRunId', ({ request }) => {
        const url = new URL(request.url)
        const after = url.searchParams.get('after_batch_id')
        // When after_batch_id filter is set (Reset has been clicked), return
        // only batches from the current attempt (none, since we're in queued state).
        if (after) {
          return HttpResponse.json({
            scan_run_id: 1,
            project_id: 1,
            status: 'queued',
            started_at: null,
            finished_at: null,
            total_findings: 0,
            processed_findings: 0,
            batches: [],
          })
        }
        // Otherwise return batches from the prior completed attempt.
        return HttpResponse.json({
          scan_run_id: 1,
          project_id: 1,
          status: 'done',
          started_at: '2026-04-30T22:50:34.903973+00:00',
          finished_at: '2026-04-30T23:02:16.579444+00:00',
          total_findings: 572,
          processed_findings: 142,
          batches: [
            {
              id: 7001,
              scan_run_id: 1,
              segment: 'sast',
              finding_ids: [1, 2, 3, 4, 5],
              status: 'completed',
              attempts: 1,
              started_at: '2026-04-30T22:50:34.903973+00:00',
              finished_at: '2026-04-30T23:02:16.579444+00:00',
              response_preview: 'Triaged 5 SAST findings; flagged 2 as false_positive.',
              error: null,
            },
            {
              id: 7002,
              scan_run_id: 1,
              segment: 'web',
              finding_ids: [],
              status: 'completed',
              attempts: 1,
              started_at: '2026-04-30T22:50:34.903973+00:00',
              finished_at: '2026-04-30T23:02:16.579444+00:00',
              response_preview: 'All 5 findings confirmed active; remediation suggested.',
              error: null,
            },
          ],
        })
      }),
      http.get('/api/v1/projects/:projectId/triage/:scanRunId/max-batch-id', () =>
        HttpResponse.json({ max_batch_id: 7002 })
      )
    )

    const user = userEvent.setup()
    renderTriage()

    // Historical batches show first (from prior attempt).
    await screen.findByText(/B-7001/i)
    expect(screen.getByText(/B-7002/i)).toBeInTheDocument()

    // Reset clears the batches and sets the attempt boundary.
    await user.click(screen.getByTestId('triage-reset-button'))

    // After reset, historical batches should vanish.
    await waitFor(() => {
      expect(screen.queryByText(/B-7001/i)).not.toBeInTheDocument()
      expect(screen.queryByText(/B-7002/i)).not.toBeInTheDocument()
    })

    // The SSE reconnection must carry the after_batch_id filter.
    await waitFor(() => {
      expect(MockEventSource.instances.length).toBeGreaterThanOrEqual(2)
    })
    const es = MockEventSource.instances[MockEventSource.instances.length - 1]
    expect(es.url).toContain('after_batch_id=7002')
  })
})

describe('Triage page - Resume swap on triage_failed', () => {
  // SSE is now run-scoped: the page only subscribes when a specific run
  // is displayed. These tests seed project 2 with an active run so the
  // Triage page derives a displayedRunId, opens SSE, and can receive
  // triage_failed events whose scan_run_id matches.
  const activeRunProject2 = {
    scan_run_id: 2003,
    project_id: 2,
    status: 'running',
    started_at: '2026-04-28T11:00:00Z',
    finished_at: null,
    total_findings: 23,
    processed_findings: 7,
  }

  it('swaps to Resume on triage_failed { resumable: true } and renders the inline note', async () => {
    useUI.setState({ activeProjectId: 2, triageInjectionAcked: true })
    server.use(
      http.get('/api/v1/projects/2/triage/active', () =>
        HttpResponse.json(activeRunProject2)
      )
    )
    renderTriage()

    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1))
    expect(MockEventSource.instances[0].url).toContain('scan_run_id=2003')
    const es = MockEventSource.instances[0]
    act(() => {
      es.emitTyped('triage_failed', {
        id: 'evt-fail',
        scan_run_id: 2003,
        project_id: 2,
        timestamp: '2026-04-28T11:09:00Z',
        error: 'Claude crashed',
        failed_at_finding_id: 4711,
        resumable: true,
        message: 'failed',
      })
    })

    const resumeBtn = await screen.findByTestId('triage-resume-button')
    expect(resumeBtn).toHaveTextContent(/resume/i)
    expect(screen.getByTestId('triage-resume-note')).toHaveTextContent(/finding #4711/)
    expect(screen.getByTestId('triage-resume-note')).toHaveTextContent(/Claude crashed/)
  })

  it('Resume click fires POST resume with the ack body', async () => {
    useUI.setState({ activeProjectId: 2, triageInjectionAcked: true })

    let resumeBody: Record<string, unknown> | null = null
    server.use(
      http.get('/api/v1/projects/2/triage/active', () =>
        HttpResponse.json(activeRunProject2)
      ),
      http.post('/api/v1/projects/2/triage/2003/resume', async ({ request }) => {
        resumeBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(
          {
            scan_run_id: 2003,
            project_id: 2,
            status: 'queued',
            started_at: null,
            finished_at: null,
            total_findings: 23,
            processed_findings: 7,
          },
          { status: 202 }
        )
      })
    )

    renderTriage()

    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1))
    const es = MockEventSource.instances[0]
    act(() => {
      es.emitTyped('triage_failed', {
        id: 'evt-fail',
        scan_run_id: 2003,
        project_id: 2,
        timestamp: '2026-04-28T11:09:00Z',
        error: 'Claude crashed',
        failed_at_finding_id: 4711,
        resumable: true,
        message: 'failed',
      })
    })

    const user = userEvent.setup()
    const resumeBtn = await screen.findByTestId('triage-resume-button')
    await user.click(resumeBtn)
    await waitFor(() => expect(resumeBody).not.toBeNull())
    expect(resumeBody).toMatchObject({ acknowledge_injection_risk: true })
  })
})
