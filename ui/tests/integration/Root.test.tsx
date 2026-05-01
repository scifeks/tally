import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import Root from '@/Root'
import { apiFetch } from '@/lib/api/client'
import { __setEventSourceFactory } from '@/lib/api/sse'
import { useUI } from '@/lib/store'
import { server } from '../handlers'
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
  window.history.replaceState(null, '', '/')
  clearAllCookies()
})

afterEach(() => {
  __setEventSourceFactory(null)
})

describe('Root', () => {
  it('replaces the application tree with SessionExpiredModal when apiFetch sees a 401', async () => {
    render(<Root />)

    expect(await screen.findByText('DASHBOARD')).toBeInTheDocument()
    expect(screen.queryByTestId('session-expired-modal')).toBeNull()

    server.use(
      http.get('/api/v1/__probe-401', () =>
        HttpResponse.json(
          { error: { code: 'UNAUTHENTICATED', message: 'no session', details: {} } },
          { status: 401 }
        )
      )
    )

    await expect(apiFetch('/api/v1/__probe-401')).rejects.toMatchObject({
      code: 'UNAUTHENTICATED',
      status: 401,
    })

    expect(await screen.findByTestId('session-expired-modal')).toBeInTheDocument()
    expect(screen.queryByText('DASHBOARD')).toBeNull()
  })
})
