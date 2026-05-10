import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import Config from '@/pages/Config'
import { useUI } from '@/lib/store'
import { __setEventSourceFactory } from '@/lib/api/sse'
import { MockEventSource } from '../../../helpers/sse'
import { clearAllCookies, setCookie } from '../../../helpers/cookies'

function renderConfig() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <Config />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  MockEventSource.reset()
  __setEventSourceFactory(
    (url, init) => new MockEventSource(url, init) as unknown as EventSource,
  )
  clearAllCookies()
  setCookie('tally_csrf', 'test-csrf-token')
  window.localStorage.clear()
  useUI.setState({
    activeProjectId: null,
    findingsSegment: 'sast',
    selectedFindingIds: new Set<number>(),
    findingMutationError: null,
    configMutationError: null,
    triageRunStatus: 'idle',
  })
})

afterEach(() => {
  __setEventSourceFactory(null)
})

describe('Config page', () => {
  it('shows no-project-selected state when activeProjectId is null', () => {
    renderConfig()
    expect(screen.getByText('No Project Selected')).toBeInTheDocument()
  })

  it('renders all three sections with MSW-backed data', async () => {
    useUI.setState({ activeProjectId: 1 })
    renderConfig()

    await waitFor(() => {
      expect(screen.getByText('PROJECT INFO')).toBeInTheDocument()
    })
    expect(screen.getByText('REPOSITORIES')).toBeInTheDocument()
    expect(screen.getByText('TOOL OVERRIDES')).toBeInTheDocument()
  })

  it('renders project info fields from fixture data', async () => {
    useUI.setState({ activeProjectId: 1 })
    renderConfig()

    const companyInput = await screen.findByLabelText('Company Name')
    expect(companyInput).toHaveValue('DVPA')

    const deptInput = screen.getByLabelText('Department Name')
    expect(deptInput).toHaveValue('foosville')

    const abbrInput = screen.getByLabelText(/Abbreviation/)
    expect(abbrInput).toHaveValue('DVP')
  })
})
