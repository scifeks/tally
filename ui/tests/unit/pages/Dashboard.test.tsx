import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import Dashboard from '@/pages/Dashboard'
import { useUI } from '@/lib/store'
import { __setEventSourceFactory } from '@/lib/api/sse'
import { server } from '../../handlers'
import { MockEventSource } from '../../helpers/sse'
import populatedFixture from '../../fixtures/findings-counts-populated.json'
import projectMetaPopulatedFixture from '../../fixtures/project-meta-populated.json'

function renderDashboard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <Dashboard />
      </QueryClientProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  MockEventSource.reset()
  __setEventSourceFactory((url, init) => new MockEventSource(url, init) as unknown as EventSource)
  window.localStorage.clear()
  useUI.setState({
    activeProjectId: null,
    findingsSegment: 'sast',
    selectedFindingIds: new Set<number>(),
    findingMutationError: null,
    triageRunStatus: 'idle',
  })
})

afterEach(() => {
  __setEventSourceFactory(null)
})

describe('Dashboard - no project selected', () => {
  it('renders the picker with all projects from the API', async () => {
    renderDashboard()
    expect(screen.getByText('No Project Selected')).toBeInTheDocument()
    expect(await screen.findByText('ACM')).toBeInTheDocument()
    expect(screen.getByText('ATL')).toBeInTheDocument()
    expect(screen.getByText('NWD')).toBeInTheDocument()
    expect(screen.getByText('acme-platform')).toBeInTheDocument()
  })

  it('clicking a project sets activeProjectId and transitions to the project view', async () => {
    const user = userEvent.setup()
    renderDashboard()

    const acm = await screen.findByText('ACM')
    await user.click(acm)

    expect(useUI.getState().activeProjectId).toBe(1)
    // The project view renders the active-project header label.
    expect(await screen.findByText('active project')).toBeInTheDocument()
  })
})

describe('Dashboard - project selected (populated counts)', () => {
  it('renders header tiles + at-a-glance from /findings/counts and /meta', async () => {
    useUI.setState({ activeProjectId: 1 })
    renderDashboard()

    // Header tiles: repositories, urls, tools enabled, scans (4 cols).
    expect(await screen.findByText('repositories')).toBeInTheDocument()
    expect(screen.getByText('urls')).toBeInTheDocument()
    expect(screen.getByText('tools enabled')).toBeInTheDocument()
    expect(screen.getByText('scans')).toBeInTheDocument()
    expect(screen.queryByText('url lists')).not.toBeInTheDocument()

    // Tile values come from the populated fixtures (counts + meta).
    expect(screen.getByText(String(populatedFixture.repos_count))).toBeInTheDocument()
    expect(screen.getByText(String(populatedFixture.urls_count))).toBeInTheDocument()
    expect(
      screen.getByText(String(projectMetaPopulatedFixture.enabled_tools.length))
    ).toBeInTheDocument()

    // At-a-glance rows from the same fixture (wait for hasScans branch - mock
    // useScanHistory resolves on a 100ms timer). Value mapping for the
    // by_severity_status crosstab is covered by the hook unit test; here we
    // assert the rows render and the unambiguous total is shown.
    expect(await screen.findByText('total findings')).toBeInTheDocument()
    expect(screen.getByText(String(populatedFixture.total))).toBeInTheDocument()
    expect(screen.getByText('open critical')).toBeInTheDocument()
    expect(screen.getByText('open high')).toBeInTheDocument()

    // "scans running" defaults to 0 with no SSE event emitted.
    expect(screen.getByText('scans running')).toBeInTheDocument()
  })
})

describe('Dashboard - project selected (empty counts)', () => {
  it('renders the EmptyProjectState onboarding for a brand-new project', async () => {
    useUI.setState({ activeProjectId: 3 })
    renderDashboard()

    // EmptyProjectState - onboarding copy plus the welcome panel header.
    expect(await screen.findByText(/welcome :: NWD/i)).toBeInTheDocument()
    expect(screen.getByText(/no scans have been run/i)).toBeInTheDocument()
    expect(screen.getByText(/add a repository or URL list/i)).toBeInTheDocument()
  })
})

describe('Dashboard - recent high-severity findings panel', () => {
  it('requests findings filtered to critical+high active sorted by severity desc, limit 10', async () => {
    let observedUrl: URL | null = null
    server.use(
      http.get('/api/v1/projects/:projectId/findings', ({ request }) => {
        observedUrl = new URL(request.url)
        return HttpResponse.json({
          items: [
            {
              id: 1001,
              project_id: 1,
              segment: 'sast',
              domain: 'code',
              severity: 'critical',
              status: 'active',
              confidence: 'high',
              finding_type: ['sql-injection'],
              title: 'SQL injection in user search',
              description: null,
              tool: 'semgrep',
              target: 'acme-api',
              file: null,
              line: null,
              cwe: ['CWE-89'],
              notes: null,
              discovered_at: '2026-04-26T10:00:00Z',
              triaged_at: null,
              triaged_by: null,
              is_locked: false,
              lock_holder: null,
            },
          ],
          total: 1,
          offset: 0,
          limit: 10,
        })
      })
    )

    useUI.setState({ activeProjectId: 1 })
    renderDashboard()

    await screen.findByText('SQL injection in user search')

    expect(observedUrl).not.toBeNull()
    const params = observedUrl!.searchParams
    expect(params.getAll('severity').sort()).toEqual(['critical', 'high'])
    expect(params.getAll('status')).toEqual(['active'])
    expect(params.get('sort')).toBe('severity')
    expect(params.get('order')).toBe('desc')
    expect(params.get('limit')).toBe('10')
  })

  it('hides the recent high-severity panel when the filtered query returns zero items', async () => {
    server.use(
      http.get('/api/v1/projects/:projectId/findings', () =>
        HttpResponse.json({ items: [], total: 0, offset: 0, limit: 10 })
      )
    )
    useUI.setState({ activeProjectId: 1 })
    renderDashboard()

    await screen.findByText('repositories')
    expect(screen.queryByText('recent high-severity findings')).toBeNull()
  })
})

describe('Dashboard - counts endpoint error handling', () => {
  it('renders gracefully (zero defaults) when counts returns 500', async () => {
    server.use(
      http.get('/api/v1/projects/:projectId/findings/counts', () =>
        HttpResponse.json({ error: { code: 'SERVER_ERROR', message: 'boom' } }, { status: 500 })
      )
    )
    useUI.setState({ activeProjectId: 1 })
    renderDashboard()

    // Header still mounts; at-a-glance shows once mock useScanHistory resolves.
    expect(await screen.findByText('repositories')).toBeInTheDocument()
    expect(await screen.findByText('open critical')).toBeInTheDocument()
  })

  it('renders gracefully when counts errors at the network layer', async () => {
    server.use(http.get('/api/v1/projects/:projectId/findings/counts', () => HttpResponse.error()))
    useUI.setState({ activeProjectId: 1 })
    renderDashboard()

    expect(await screen.findByText('repositories')).toBeInTheDocument()
    expect(await screen.findByText('open critical')).toBeInTheDocument()
  })
})
