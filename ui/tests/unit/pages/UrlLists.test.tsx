import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import UrlLists from '@/pages/UrlLists'
import { useUI } from '@/lib/store'
import { server } from '../../handlers'
import urlListFilterOptionsPopulatedFixture from '../../fixtures/url_findings/filter-options-populated.json'

type IOCallback = (entries: IntersectionObserverEntry[]) => void
const ioInstances: { cb: IOCallback; target: Element | null }[] = []

class ControllableIntersectionObserver implements IntersectionObserver {
  readonly root: Element | Document | null = null
  readonly rootMargin: string = ''
  readonly thresholds: ReadonlyArray<number> = []
  private readonly cb: IOCallback
  constructor(cb: IOCallback) {
    this.cb = cb
    ioInstances.push({ cb, target: null })
  }
  observe(target: Element): void {
    const entry = ioInstances.find(i => i.cb === this.cb)
    if (entry) entry.target = target
  }
  unobserve(): void {}
  disconnect(): void {
    const idx = ioInstances.findIndex(i => i.cb === this.cb)
    if (idx >= 0) ioInstances.splice(idx, 1)
  }
  takeRecords(): IntersectionObserverEntry[] {
    return []
  }
}

function fireSentinelIntersection(): void {
  for (const inst of ioInstances) {
    if (!inst.target) continue
    inst.cb([
      {
        isIntersecting: true,
        target: inst.target,
      } as IntersectionObserverEntry,
    ])
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
        <UrlLists />
      </QueryClientProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  ioInstances.length = 0
  vi.stubGlobal('IntersectionObserver', ControllableIntersectionObserver)
  useUI.setState({
    activeProjectId: 1,
    findingsSegment: 'sast',
    selectedFindingIds: new Set<number>(),
    findingMutationError: null,
    triageRunStatus: 'idle',
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  server.resetHandlers()
})

describe('UrlLists page', () => {
  it('renders the first-page loaded count in the footer once urls resolve', async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getAllByText(/100\s*of\s*307\s*loaded/i)[0]).toBeInTheDocument()
    )
  })

  it('renders all six column headers including the new repo column', async () => {
    renderPage()
    await screen.findByText('method')
    expect(screen.getByText('protocol')).toBeInTheDocument()
    expect(screen.getByText('host')).toBeInTheDocument()
    expect(screen.getByText('port')).toBeInTheDocument()
    expect(screen.getByText('path')).toBeInTheDocument()
    expect(screen.getByText('repo')).toBeInTheDocument()
  })

  it('shows the empty state when the project has no urls (project 3)', async () => {
    useUI.setState({ activeProjectId: 3 })
    renderPage()
    await screen.findByText(/no urls yet/i)
  })

  it('selecting a method filter forwards method= to the entries endpoint', async () => {
    const user = userEvent.setup()
    let lastEntriesUrl: URL | null = null
    server.use(
      http.get('/api/v1/projects/:projectId/url-list/entries', ({ request }) => {
        lastEntriesUrl = new URL(request.url)
        return HttpResponse.json({
          items: [
            {
              id: 1,
              project_id: 1,
              repo_id: 1,
              repo_name: 'backend-api',
              source: 'scan',
              tool: 'katana',
              run_id: 1,
              method: 'GET',
              protocol: 'https',
              host: 'api.acme-platform.com',
              port: 443,
              path: '/docs',
              file_path: null,
              meta: {},
              created_at: '2026-04-26T10:00:00.000Z',
            },
          ],
          total: 1,
          offset: 0,
          limit: 100,
        })
      }),
      http.get('/api/v1/projects/:projectId/url-list/filter-options', () =>
        HttpResponse.json(urlListFilterOptionsPopulatedFixture)
      )
    )
    renderPage()
    await waitFor(() => expect(lastEntriesUrl).not.toBeNull())

    const methodFilterButton = screen.getByRole('button', { name: /filter method/i })
    await user.click(methodFilterButton)

    const getCheckbox = await screen.findByRole('checkbox', { name: /GET/i })
    await user.click(getCheckbox)

    await waitFor(() => expect(lastEntriesUrl!.searchParams.getAll('method')).toContain('GET'))
  })

  it('typing in the search input forwards search= after debounce', async () => {
    const user = userEvent.setup()
    let lastEntriesUrl: URL | null = null
    server.use(
      http.get('/api/v1/projects/:projectId/url-list/entries', ({ request }) => {
        lastEntriesUrl = new URL(request.url)
        return HttpResponse.json({
          items: [
            {
              id: 1,
              project_id: 1,
              repo_id: 1,
              repo_name: 'backend-api',
              source: 'scan',
              tool: 'katana',
              run_id: 1,
              method: 'GET',
              protocol: 'https',
              host: 'api.acme-platform.com',
              port: 443,
              path: '/docs',
              file_path: null,
              meta: {},
              created_at: '2026-04-26T10:00:00.000Z',
            },
          ],
          total: 1,
          offset: 0,
          limit: 100,
        })
      })
    )
    renderPage()
    await waitFor(() => expect(lastEntriesUrl).not.toBeNull())

    const input = screen.getByLabelText(/search urls/i)
    await user.type(input, 'admin')

    await waitFor(
      () => expect(lastEntriesUrl!.searchParams.get('search')).toBe('admin'),
      { timeout: 2000 }
    )
  })

  it('clicking a column header forwards sort and order to the server', async () => {
    const user = userEvent.setup()
    let lastEntriesUrl: URL | null = null
    server.use(
      http.get('/api/v1/projects/:projectId/url-list/entries', ({ request }) => {
        lastEntriesUrl = new URL(request.url)
        return HttpResponse.json({
          items: [
            {
              id: 1,
              project_id: 1,
              repo_id: 1,
              repo_name: 'backend-api',
              source: 'scan',
              tool: 'katana',
              run_id: 1,
              method: 'GET',
              protocol: 'https',
              host: 'api.acme-platform.com',
              port: 443,
              path: '/docs',
              file_path: null,
              meta: {},
              created_at: '2026-04-26T10:00:00.000Z',
            },
          ],
          total: 1,
          offset: 0,
          limit: 100,
        })
      })
    )
    renderPage()
    await waitFor(() => expect(lastEntriesUrl).not.toBeNull())

    const hostHeader = screen.getByRole('button', { name: /^host/i })
    await user.click(hostHeader)
    await waitFor(() => expect(lastEntriesUrl!.searchParams.get('sort')).toBe('host'))
    expect(lastEntriesUrl!.searchParams.get('order')).toBe('asc')

    await waitFor(() =>
      expect(screen.getByText(/sorted by\s+host\s+asc/i)).toBeInTheDocument()
    )
  })

  it('forwards active filters to the filter-options endpoint', async () => {
    const user = userEvent.setup()
    let lastFilterOptionsUrl: URL | null = null
    server.use(
      http.get('/api/v1/projects/:projectId/url-list/filter-options', ({ request }) => {
        lastFilterOptionsUrl = new URL(request.url)
        return HttpResponse.json(urlListFilterOptionsPopulatedFixture)
      })
    )
    renderPage()
    await waitFor(() => expect(lastFilterOptionsUrl).not.toBeNull())

    const methodFilterButton = screen.getByRole('button', { name: /filter method/i })
    await user.click(methodFilterButton)
    const getCheckbox = await screen.findByRole('checkbox', { name: /GET/i })
    await user.click(getCheckbox)

    await waitFor(() =>
      expect(lastFilterOptionsUrl!.searchParams.getAll('method')).toContain('GET')
    )
  })

  it('keeps a selected filter value visible in the dropdown even when the response drops it', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('/api/v1/projects/:projectId/url-list/filter-options', ({ request }) => {
        const hasMethodFilter =
          new URL(request.url).searchParams.getAll('method').length > 0
        if (hasMethodFilter) {
          return HttpResponse.json({
            method: [{ value: 'POST', count: 5 }],
            protocol: [],
            host: [],
            port: [],
            path: [],
            repo: [],
          })
        }
        return HttpResponse.json(urlListFilterOptionsPopulatedFixture)
      })
    )
    renderPage()
    const methodFilterButton = await screen.findByRole('button', { name: /filter method/i })
    await user.click(methodFilterButton)
    const getCheckbox = await screen.findByRole('checkbox', { name: /GET/i })
    await user.click(getCheckbox)

    // After response only contains POST, the GET checkbox must still render so
    // the user can deselect it.
    await waitFor(() =>
      expect(screen.getAllByRole('checkbox', { name: /GET/i }).length).toBeGreaterThan(0)
    )
  })

  it('sentinel intersection triggers fetchNextPage and grows the loaded count', async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getAllByText(/100\s*of\s*307\s*loaded/i)[0]).toBeInTheDocument()
    )

    await act(async () => {
      fireSentinelIntersection()
    })

    await waitFor(() =>
      expect(screen.getAllByText(/200\s*of\s*307\s*loaded/i)[0]).toBeInTheDocument()
    )
  })
})
