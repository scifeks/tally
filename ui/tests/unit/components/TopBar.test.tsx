import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import { TopBar } from '@/components/TopBar'
import { useUI } from '@/lib/store'
import { __setEventSourceFactory } from '@/lib/api/sse'
import { server } from '../../handlers'
import { MockEventSource } from '../../helpers/sse'
import claudeMissingFixture from '../../fixtures/runtime/deps-claude-missing.json'

const PERSIST_KEY = 'tally-ui-active-project'

function renderTopBar() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <TopBar />
      </QueryClientProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  MockEventSource.reset()
  __setEventSourceFactory(
    (url, init) => new MockEventSource(url, init) as unknown as EventSource
  )
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

describe('TopBar - project switcher', () => {
  it('shows the placeholder before any project is selected', async () => {
    renderTopBar()
    expect(screen.getByText('-- select project --')).toBeInTheDocument()
  })

  it('renders project codes from the API into the dropdown', async () => {
    const user = userEvent.setup()
    renderTopBar()

    await user.click(screen.getByRole('button', { name: /select project/i }))
    expect(await screen.findByText('DVPA')).toBeInTheDocument()
    expect(screen.getByText('DVPA-alt')).toBeInTheDocument()
  })

  it('first selection sets activeProjectId without showing the confirm modal', async () => {
    const user = userEvent.setup()
    renderTopBar()

    await user.click(screen.getByRole('button', { name: /select project/i }))
    const first = await screen.findByText('DVPA')
    await user.click(first)

    expect(useUI.getState().activeProjectId).toBe(2)
    expect(screen.queryByText(/confirm switch/i)).not.toBeInTheDocument()
  })

  it('subsequent selection opens the confirm modal; confirming switches', async () => {
    useUI.setState({ activeProjectId: 2 })
    const user = userEvent.setup()
    renderTopBar()

    // Open the dropdown using the visible-project switcher button.
    const switcher = await screen.findByRole('button', { name: /DVPA/i })
    await user.click(switcher)
    const alt = await screen.findByText('DVPA-alt')
    await user.click(alt)

    // Confirm modal renders the destination project name.
    expect(await screen.findByText(/confirm switch/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /confirm/i }))

    expect(useUI.getState().activeProjectId).toBe(3)
  })
})

describe('TopBar - persisted activeProjectId', () => {
  it('rehydrates a valid persisted ID across remount', async () => {
    useUI.setState({ activeProjectId: 3 })
    const { unmount } = renderTopBar()
    expect(await screen.findByText('DVPA-alt')).toBeInTheDocument()
    unmount()

    // Active project state is in the singleton store; it should still hold
    // value 3 after the second mount renders.
    renderTopBar()
    expect(await screen.findByText('DVPA-alt')).toBeInTheDocument()
    expect(useUI.getState().activeProjectId).toBe(3)
  })
})

describe('TopBar - triage gate', () => {
  it('hides the TRIAGE nav link when claude is not installed', async () => {
    server.use(
      http.get('/api/v1/runtime-dependencies', () =>
        HttpResponse.json(claudeMissingFixture)
      )
    )
    renderTopBar()

    await waitFor(() => {
      expect(screen.queryByText('TRIAGE')).not.toBeInTheDocument()
    })
    // Sanity: other primary nav links remain.
    expect(screen.getByText('DASHBOARD')).toBeInTheDocument()
  })

  it('renders the TRIAGE nav link when claude is installed', async () => {
    renderTopBar()
    await waitFor(() => {
      expect(screen.getByText('TRIAGE')).toBeInTheDocument()
    })
  })
})

describe('TopBar - scans-running indicator', () => {
  it('renders idle when no scans are active', async () => {
    useUI.setState({ activeProjectId: 1 })
    renderTopBar()

    const [es] = await waitFor(() => {
      expect(MockEventSource.instances.length).toBeGreaterThan(0)
      return MockEventSource.instances
    })
    act(() => {
      es.emitTyped('snapshot', {
        run_id: null,
        project_id: 1,
        active_run_ids: [],
      })
    })

    expect(screen.getByText('idle')).toBeInTheDocument()
  })

  it('reflects a snapshot active_run_ids count', async () => {
    useUI.setState({ activeProjectId: 1 })
    renderTopBar()

    const [es] = await waitFor(() => {
      expect(MockEventSource.instances.length).toBeGreaterThan(0)
      return MockEventSource.instances
    })
    act(() => {
      es.emitTyped('snapshot', {
        run_id: null,
        project_id: 1,
        active_run_ids: [10, 20],
      })
    })

    expect(await screen.findByText(/2 scans running/i)).toBeInTheDocument()
  })

  it('decrements when a run_completed event arrives', async () => {
    useUI.setState({ activeProjectId: 1 })
    renderTopBar()

    const [es] = await waitFor(() => {
      expect(MockEventSource.instances.length).toBeGreaterThan(0)
      return MockEventSource.instances
    })

    act(() => {
      es.emitTyped('snapshot', {
        run_id: null,
        project_id: 1,
        active_run_ids: [10, 20],
      })
    })
    expect(await screen.findByText(/2 scans running/i)).toBeInTheDocument()

    act(() => {
      es.emitTyped('run_completed', {
        id: 'evt_1',
        run_id: 10,
        timestamp: '2026-04-27T18:00:00Z',
      })
    })
    expect(await screen.findByText(/1 scan running/i)).toBeInTheDocument()
  })
})
