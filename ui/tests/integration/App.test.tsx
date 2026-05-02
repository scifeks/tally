import { beforeEach, afterEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import App from '@/App'
import { __setEventSourceFactory } from '@/lib/api/sse'
import { useUI } from '@/lib/store'
import { MockEventSource } from '../helpers/sse'
import { clearAllCookies } from '../helpers/cookies'

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
    scanMutationError: null,
    triageMutationError: null,
    reportMutationError: null,
    chatMutationError: null,
    configMutationError: null,
    triageInjectionAcked: false,
    triageRunStatus: 'idle',
  })
  clearAllCookies()
})

afterEach(() => {
  __setEventSourceFactory(null)
})

function renderAt(path: string) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <App />
      </QueryClientProvider>
    </MemoryRouter>
  )
}

describe('App routing', () => {
  it('renders NotFound for an unknown URL', async () => {
    renderAt('/foo')

    expect(await screen.findByText('system error')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /return home/i })).toBeInTheDocument()
  })
})
