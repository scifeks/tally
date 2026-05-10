import { act, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ScansRunningModal } from '@/components/ScansRunningModal'
import { __setEventSourceFactory } from '@/lib/api/sse'
import { useUI } from '@/lib/store'
import { MockEventSource } from '../../helpers/sse'

function renderModal() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ScansRunningModal open onClose={vi.fn()} />
      </QueryClientProvider>
    </MemoryRouter>
  )
}

function findScansSse(projectId: number): MockEventSource {
  const url = `/api/v1/projects/${projectId}/scans/events`
  const es = MockEventSource.instances.find(i => i.url.includes(url))
  if (!es) throw new Error(`no MockEventSource opened for ${url}`)
  return es
}

beforeEach(() => {
  MockEventSource.reset()
  __setEventSourceFactory((url, init) => new MockEventSource(url, init) as unknown as EventSource)
  useUI.setState({
    activeProjectId: null,
    findingsSegment: 'sast',
    selectedFindingIds: new Set<number>(),
    findingMutationError: null,
    scanMutationError: null,
    triageMutationError: null,
    reportMutationError: null,
    chatMutationError: null,
    configMutationError: null,
    triageInjectionAcked: false,
    triageRunStatus: 'idle',
  })
})

afterEach(() => {
  __setEventSourceFactory(null)
})

describe('ScansRunningModal', () => {
  it('renders the empty-state copy when no scans are running for the active project', async () => {
    useUI.setState({ activeProjectId: 3 })
    renderModal()

    expect(await screen.findByText(/no scans are currently running/i)).toBeInTheDocument()
    expect(screen.getByText(/system idle/i)).toBeInTheDocument()
  })

  it('a tool_started event populates the running card with `repo/tool` live label', async () => {
    useUI.setState({ activeProjectId: 1 })
    renderModal()

    expect(await screen.findByText('1003')).toBeInTheDocument()

    await waitFor(() =>
      expect(MockEventSource.instances.some(i => i.url.includes('/projects/1/scans/events'))).toBe(
        true
      )
    )
    const sse = findScansSse(1)
    act(() => {
      sse.emitTyped('tool_started', { run_id: 1003, repo: 'svc-a', tool: 'semgrep' })
    })

    expect(await screen.findByText('svc-a/semgrep')).toBeInTheDocument()
  })

  it('tool_completed events advance the progress bar via aria-valuenow', async () => {
    useUI.setState({ activeProjectId: 1 })
    renderModal()

    expect(await screen.findByText('1003')).toBeInTheDocument()

    await waitFor(() =>
      expect(MockEventSource.instances.some(i => i.url.includes('/projects/1/scans/events'))).toBe(
        true
      )
    )
    const sse = findScansSse(1)

    const bar = screen.getByRole('progressbar')
    expect(bar).toHaveAttribute('aria-valuenow', '0')

    act(() => {
      sse.emitTyped('tool_completed', { run_id: 1003 })
      sse.emitTyped('tool_completed', { run_id: 1003 })
      sse.emitTyped('tool_completed', { run_id: 1003 })
    })

    await waitFor(() =>
      expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '50')
    )
  })

  it('snapshot frame seeds the live label without a prior tool_started', async () => {
    useUI.setState({ activeProjectId: 1 })
    renderModal()

    expect(await screen.findByText('1003')).toBeInTheDocument()

    await waitFor(() =>
      expect(MockEventSource.instances.some(i => i.url.includes('/projects/1/scans/events'))).toBe(
        true
      )
    )
    const sse = findScansSse(1)
    act(() => {
      sse.emitTyped('snapshot', {
        run_id: null,
        project_id: 1,
        active_runs: [{ run_id: 1003, repo: 'svc-a', tool: 'semgrep' }],
      })
    })

    expect(await screen.findByText('svc-a/semgrep')).toBeInTheDocument()
  })
})
