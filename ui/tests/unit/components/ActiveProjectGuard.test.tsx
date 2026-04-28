import { beforeEach, describe, expect, it } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { ActiveProjectGuard } from '@/components/ActiveProjectGuard'
import { useUI } from '@/lib/store'

function renderGuard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ActiveProjectGuard />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  window.localStorage.clear()
  useUI.setState({
    activeProjectId: null,
    findingsSegment: 'sast',
    selectedFindingIds: new Set<string>(),
    findingOverrides: {},
    triageRunStatus: 'idle',
  })
})

describe('ActiveProjectGuard', () => {
  it('clears activeProjectId when it is missing from the project list', async () => {
    useUI.setState({ activeProjectId: 999 })
    renderGuard()

    await waitFor(() => {
      expect(useUI.getState().activeProjectId).toBeNull()
    })
  })

  it('leaves activeProjectId untouched when it is present in the project list', async () => {
    useUI.setState({ activeProjectId: 2 })
    renderGuard()

    // Wait for the projects query to resolve, then verify state is preserved.
    await waitFor(() => {
      expect(useUI.getState().activeProjectId).toBe(2)
    })
  })

  it('is a no-op when activeProjectId is null', async () => {
    renderGuard()
    await waitFor(() => {
      expect(useUI.getState().activeProjectId).toBeNull()
    })
  })
})
