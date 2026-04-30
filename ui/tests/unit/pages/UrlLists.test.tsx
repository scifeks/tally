import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import UrlLists from '@/pages/UrlLists'
import { useUI } from '@/lib/store'
import { server } from '../../handlers'

// Controllable IntersectionObserver - lets the test trigger sentinel
// intersection on demand. jsdom has no native IntersectionObserver.
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
    await waitFor(() => expect(screen.getByText(/100\s*of\s*180\s*loaded/i)).toBeInTheDocument())
  })

  it('renders the column headers', async () => {
    renderPage()
    await screen.findByText('METHOD')
    expect(screen.getByText('PROTO')).toBeInTheDocument()
    expect(screen.getByText('HOST')).toBeInTheDocument()
    expect(screen.getByText('PORT')).toBeInTheDocument()
    expect(screen.getByText('PATH')).toBeInTheDocument()
  })

  it('shows the empty state when the project has no urls (project 3)', async () => {
    useUI.setState({ activeProjectId: 3 })
    renderPage()
    await screen.findByText(/no urls yet/i)
  })

  it('search input filters the loaded entries client-side', async () => {
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => expect(screen.getByText(/100\s*of\s*180\s*loaded/i)).toBeInTheDocument())

    const input = screen.getByLabelText(/search urls/i)
    await user.type(input, 'admin')

    await waitFor(() => {
      const matches = screen.queryByText(/^matches:\s*\d+/i)
      expect(matches).not.toBeNull()
    })
  })

  it('clicking a column header cycles sort direction (asc → desc → off)', async () => {
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => expect(screen.getByText(/100\s*of\s*180\s*loaded/i)).toBeInTheDocument())

    const hostHeader = screen.getByTitle(/sort by host/i)
    await user.click(hostHeader)
    await waitFor(() => expect(screen.getByText(/sorted by\s+host\s+asc/i)).toBeInTheDocument())

    await user.click(hostHeader)
    await waitFor(() => expect(screen.getByText(/sorted by\s+host\s+desc/i)).toBeInTheDocument())

    await user.click(hostHeader)
    await waitFor(() => expect(screen.queryByText(/sorted by/i)).toBeNull())
  })

  it('sentinel intersection triggers fetchNextPage and grows the loaded count to total', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText(/100\s*of\s*180\s*loaded/i)).toBeInTheDocument())

    await act(async () => {
      fireSentinelIntersection()
    })

    await waitFor(() =>
      expect(screen.getByText(/180\s*of\s*180\s*loaded/i)).toBeInTheDocument()
    )
    expect(screen.getByText(/end of list/i)).toBeInTheDocument()
  })
})
