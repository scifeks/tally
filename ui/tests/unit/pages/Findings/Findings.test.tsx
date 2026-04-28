import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import Findings from '@/pages/Findings/index'
import { useUI } from '@/lib/store'
import { __setEventSourceFactory } from '@/lib/api/sse'
import { server } from '../../../handlers'
import { setCookie, clearAllCookies } from '../../../helpers/cookies'
import { MockEventSource } from '../../../helpers/sse'
import populatedFixture from '../../../fixtures/findings-populated.json'
import findingUpdatedFixture from '../../../fixtures/finding-updated.json'

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
  __setEventSourceFactory(
    (url, init) => new MockEventSource(url, init) as unknown as EventSource
  )
  useUI.setState({
    activeProjectId: 1,
    findingsSegment: 'sast',
    selectedFindingIds: new Set<number>(),
    findingMutationError: null,
    triageRunStatus: 'idle',
  })
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  __setEventSourceFactory(null)
  server.resetHandlers()
})

describe('Findings page — server-driven list', () => {
  it('renders the loaded total in the footer once findings resolve', async () => {
    renderPage()
    // SAST count from fixture: 2 items (1001, 1002).
    await waitFor(() =>
      expect(screen.getByText(/loaded/i).textContent ?? '').toMatch(/2.+of.+2/)
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
    await waitFor(() =>
      expect(observedRequests.some(arr => arr.includes('critical'))).toBe(true)
    )
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

    const es = MockEventSource.instances.find(e =>
      e.url.includes('/findings/events')
    )!
    act(() => {
      es.emitTyped('finding_updated', findingUpdatedFixture)
    })

    // Give the cache patch a tick — and assert no extra GET happened.
    await waitFor(() => expect(listFetches).toBe(1))
  })
})
