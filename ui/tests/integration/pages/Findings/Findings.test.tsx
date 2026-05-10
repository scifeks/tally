import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import Findings from '@/pages/Findings/index'
import { FindingDetailPanel } from '@/pages/Findings/FindingDetailPanel'
import { useUI } from '@/lib/store'
import { __setEventSourceFactory } from '@/lib/api/sse'
import { server } from '../../../handlers'
import { setCookie, clearAllCookies } from '../../../helpers/cookies'
import { MockEventSource } from '../../../helpers/sse'
import populatedFixture from '../../../fixtures/findings/populated.json'
import findingUpdatedFixture from '../../../fixtures/findings/finding-updated.json'

class StubIntersectionObserver implements IntersectionObserver {
  readonly root: Element | Document | null = null
  readonly rootMargin: string = ''
  readonly thresholds: ReadonlyArray<number> = []
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): IntersectionObserverEntry[] {
    return []
  }
}

function makeQC() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
}

function renderPage(qc = makeQC()) {
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <Findings />
      </QueryClientProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  clearAllCookies()
  setCookie('tally_csrf', 'test-csrf-token')
  vi.stubGlobal('IntersectionObserver', StubIntersectionObserver)
  MockEventSource.reset()
  __setEventSourceFactory((url, init) => new MockEventSource(url, init) as unknown as EventSource)
  useUI.setState({
    activeProjectId: 1,
    findingsSegment: 'sast',
    selectedFindingIds: new Set<number>(),
    findingMutationError: null,
    triageMutationError: null,
    triageInjectionAcked: false,
    triageRunStatus: 'idle',
  })
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  __setEventSourceFactory(null)
  server.resetHandlers()
})

describe('Findings page - server-driven list', () => {
  it('renders the loaded total in the footer once findings resolve', async () => {
    renderPage()
    // All 50 page-1 items are SAST; with segment=sast the filtered total is 50.
    await waitFor(() =>
      expect(screen.getByText(/loaded/i).textContent ?? '').toMatch(/50.+of.+50/)
    )
  })

  it('renders the cwe column header (commit column was removed)', async () => {
    renderPage()
    await screen.findByText('cwe')
    expect(screen.queryByText(/^commit$/)).toBeNull()
  })

  it('shows the empty state when the segment has no findings (project 3)', async () => {
    useUI.setState({ activeProjectId: 3 })
    renderPage()
    await screen.findByText(/no findings yet/i)
  })

  it('forwards the segment filter to the request URL', async () => {
    let observedSegments: string[] = []
    server.use(
      http.get('/api/v1/projects/:projectId/findings', ({ request }) => {
        observedSegments = new URL(request.url).searchParams.getAll('segment')
        return HttpResponse.json({ items: [], total: 0, offset: 0, limit: 50 })
      })
    )
    renderPage()
    await waitFor(() => expect(observedSegments).toEqual(['sast']))
  })

  it('forwards a severity facet click to a new request with severity= param', async () => {
    const user = userEvent.setup()
    const observedRequests: string[][] = []
    server.use(
      http.get('/api/v1/projects/:projectId/findings', ({ request }) => {
        observedRequests.push(new URL(request.url).searchParams.getAll('severity'))
        return HttpResponse.json({ items: [], total: 0, offset: 0, limit: 50 })
      })
    )
    renderPage()
    await waitFor(() => expect(observedRequests.length).toBeGreaterThan(0))

    await user.click(screen.getByTitle('filter CRIT'))
    await waitFor(() => expect(observedRequests.some(arr => arr.includes('critical'))).toBe(true))
  })

  it('debounces the search box and forwards search= when it stabilises', async () => {
    const observed: Array<string | null> = []
    server.use(
      http.get('/api/v1/projects/:projectId/findings', ({ request }) => {
        observed.push(new URL(request.url).searchParams.get('search'))
        return HttpResponse.json({ items: [], total: 0, offset: 0, limit: 50 })
      })
    )
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => expect(observed.length).toBeGreaterThan(0))

    await user.type(screen.getByRole('textbox', { name: 'Search findings' }), 'sql')
    // Real-timer wait past the 250ms debounce.
    await waitFor(() => expect(observed.some(v => v === 'sql')).toBe(true), {
      timeout: 1500,
    })
  })

  it('opens an SSE connection scoped to the active project', async () => {
    renderPage()
    await waitFor(() => {
      const opened = MockEventSource.instances.find(es =>
        es.url.includes('/projects/1/findings/events')
      )
      expect(opened).toBeDefined()
    })
  })

  it('forwards active filters to /findings/filter-options on chip click', async () => {
    const user = userEvent.setup()
    const observedSeverity: string[][] = []
    server.use(
      http.get('/api/v1/projects/:projectId/findings/filter-options', ({ request }) => {
        observedSeverity.push(new URL(request.url).searchParams.getAll('severity'))
        return HttpResponse.json({
          severity: [
            { value: 'critical', count: 3 },
            { value: 'high', count: 5 },
            { value: 'medium', count: 2 },
          ],
          status: [{ value: 'active', count: 10 }],
          confidence: [],
          domain: [{ value: 'code', count: 10 }],
          segment: [{ value: 'sast', count: 10 }],
          tool: [{ value: 'semgrep', count: 10 }],
          finding_type: [],
          repo: [],
        })
      })
    )
    renderPage()
    await waitFor(() => expect(observedSeverity.length).toBeGreaterThan(0))

    await user.click(screen.getByTitle('filter CRIT'))
    await waitFor(() => expect(observedSeverity.some(arr => arr.includes('critical'))).toBe(true))
  })

  it('hides severity chips with zero count from filter-options', async () => {
    server.use(
      http.get('/api/v1/projects/:projectId/findings/filter-options', () =>
        HttpResponse.json({
          severity: [{ value: 'high', count: 4 }],
          status: [{ value: 'active', count: 4 }],
          confidence: [],
          domain: [{ value: 'code', count: 4 }],
          segment: [{ value: 'sast', count: 4 }],
          tool: [{ value: 'semgrep', count: 4 }],
          finding_type: [],
          repo: [],
        })
      )
    )
    renderPage()
    await screen.findByTitle('filter HIGH')
    expect(screen.queryByTitle('filter CRIT')).toBeNull()
    expect(screen.queryByTitle('filter MED')).toBeNull()
    expect(screen.queryByTitle('filter LOW')).toBeNull()
    expect(screen.queryByTitle('filter INFO')).toBeNull()
  })

  it('keeps a selected severity chip visible even when its count drops to zero', async () => {
    const user = userEvent.setup()
    let chipsClicked = false
    server.use(
      http.get('/api/v1/projects/:projectId/findings/filter-options', () =>
        HttpResponse.json(
          chipsClicked
            ? {
                severity: [{ value: 'high', count: 4 }],
                status: [{ value: 'active', count: 4 }],
                confidence: [],
                domain: [{ value: 'code', count: 4 }],
                segment: [{ value: 'sast', count: 4 }],
                tool: [{ value: 'semgrep', count: 4 }],
                finding_type: [],
                repo: [],
              }
            : {
                severity: [
                  { value: 'critical', count: 3 },
                  { value: 'high', count: 4 },
                ],
                status: [{ value: 'active', count: 7 }],
                confidence: [],
                domain: [{ value: 'code', count: 7 }],
                segment: [{ value: 'sast', count: 7 }],
                tool: [{ value: 'semgrep', count: 7 }],
                finding_type: [],
                repo: [],
              }
        )
      )
    )
    renderPage()
    const critChip = await screen.findByTitle('filter CRIT')
    chipsClicked = true
    await user.click(critChip)
    // Even though "critical" no longer appears in the new filter-options
    // response, the selected chip must still render so the user can deselect.
    await waitFor(() => expect(screen.getByTitle('filtering CRIT')).toBeInTheDocument())
  })

  it('reflects an SSE finding_updated event in the cache without refetching the list', async () => {
    let listFetches = 0
    server.use(
      http.get('/api/v1/projects/:projectId/findings', () => {
        listFetches += 1
        return HttpResponse.json(populatedFixture)
      })
    )
    renderPage()
    await waitFor(() => expect(listFetches).toBe(1))

    const es = MockEventSource.instances.find(e => e.url.includes('/findings/events'))!
    act(() => {
      es.emitTyped('finding_updated', findingUpdatedFixture)
    })

    // Give the cache patch a tick - and assert no extra GET happened.
    await waitFor(() => expect(listFetches).toBe(1))
  })
})

describe('Findings detail panel - Triage button', () => {
  // The full Findings page uses TanStack Virtual which doesn't paint rows
  // in jsdom (zero element heights), so render the detail panel directly
  // with a known finding.
  const fixtureFinding = {
    id: 1001,
    projectId: 1,
    segment: 'sast' as const,
    domain: 'code' as const,
    severity: 'critical' as const,
    status: 'active' as const,
    confidence: 'high',
    findingType: ['sql-injection'],
    title: 'SQL injection in user search',
    tool: 'semgrep',
    target: 'acme-api',
    file: 'src/handlers/users.py',
    line: 42,
    cwe: ['CWE-89'],
    discoveredAt: '2026-04-26T10:00:00Z',
    isLocked: false,
    lockHolder: null,
  }

  function renderPanel() {
    const qc = makeQC()
    return render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <FindingDetailPanel finding={fixtureFinding} onUpdate={() => undefined} />
        </QueryClientProvider>
      </MemoryRouter>
    )
  }

  it('opens the prompt-injection warning modal on first click and fires single-finding triage on accept', async () => {
    let startBody: Record<string, unknown> | null = null
    server.use(
      http.post('/api/v1/projects/1/triage', async ({ request }) => {
        startBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(
          {
            scan_run_id: 2099,
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

    const user = userEvent.setup()
    renderPanel()

    const triageBtn = await screen.findByRole('button', { name: /^>\s*triage$/i })
    await user.click(triageBtn)

    expect(
      await screen.findByRole('dialog', { name: /prompt injection risk/i })
    ).toBeInTheDocument()
    expect(startBody).toBeNull()

    await user.click(screen.getByRole('button', { name: /accept & continue/i }))

    await waitFor(() => expect(startBody).not.toBeNull())
    expect(startBody).toMatchObject({
      acknowledge_injection_risk: true,
      finding_ids: [1001],
    })
    expect(useUI.getState().triageInjectionAcked).toBe(true)
  })

  it('fires single-finding triage immediately when the ack is already set', async () => {
    useUI.setState({ triageInjectionAcked: true })

    let startBody: Record<string, unknown> | null = null
    server.use(
      http.post('/api/v1/projects/1/triage', async ({ request }) => {
        startBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(
          {
            scan_run_id: 2099,
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

    const user = userEvent.setup()
    renderPanel()

    const triageBtn = await screen.findByRole('button', { name: /^>\s*triage$/i })
    await user.click(triageBtn)

    expect(screen.queryByRole('dialog', { name: /prompt injection risk/i })).not.toBeInTheDocument()
    await waitFor(() => expect(startBody).not.toBeNull())
    expect(startBody).toMatchObject({
      acknowledge_injection_risk: true,
      finding_ids: [1001],
    })
  })
})
