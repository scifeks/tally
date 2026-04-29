import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import Chat from '@/pages/Chat'
import { useUI } from '@/lib/store'
import { __setEventSourceFactory } from '@/lib/api/sse'
import { server } from '../../handlers'
import { MockEventSource } from '../../helpers/sse'
import { setCookie, clearAllCookies } from '../../helpers/cookies'

function renderChat() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <Chat />
      </QueryClientProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  clearAllCookies()
  setCookie('tally_csrf', 'test-csrf-token')
  MockEventSource.reset()
  __setEventSourceFactory((url, init) => new MockEventSource(url, init) as unknown as EventSource)
  window.localStorage.clear()
  useUI.setState({
    activeProjectId: null,
    findingsSegment: 'sast',
    selectedFindingIds: new Set<number>(),
    findingMutationError: null,
    scanMutationError: null,
    triageMutationError: null,
    triageInjectionAcked: false,
    triageRunStatus: 'idle',
    reportMutationError: null,
    chatMutationError: null,
  })
})

afterEach(() => {
  __setEventSourceFactory(null)
  server.resetHandlers()
})

// ─── Session list rendering ────────────────────────────────────────────────

describe('Chat page — session list', () => {
  it('renders project-1 sessions and auto-selects the first one', async () => {
    useUI.setState({ activeProjectId: 1 })
    renderChat()
    await waitFor(() =>
      expect(screen.getByText(/^2026-04-28 10:00$/)).toBeInTheDocument()
    )
    expect(screen.getByText(/^2026-04-27 14:00$/)).toBeInTheDocument()
    expect(screen.getByText(/sealed/i)).toBeInTheDocument()
  })

  it('renders empty state when project has no sessions', async () => {
    useUI.setState({ activeProjectId: 3 })
    renderChat()
    await waitFor(() =>
      expect(screen.getByText(/No conversations yet/i)).toBeInTheDocument()
    )
  })
})

// ─── Persisted message rendering ───────────────────────────────────────────

describe('Chat page — persisted messages', () => {
  it('renders the 4 turns from session 101 fixture', async () => {
    useUI.setState({ activeProjectId: 1 })
    renderChat()
    await waitFor(() =>
      expect(screen.getByText(/What does finding 42 mean\?/i)).toBeInTheDocument()
    )
    expect(
      screen.getByText(/Finding 42 is a SQL injection vulnerability/i)
    ).toBeInTheDocument()
    expect(screen.getByText(/How do I fix it\?/i)).toBeInTheDocument()
  })
})

// ─── Send + stream golden path ─────────────────────────────────────────────

describe('Chat page — send + stream golden path', () => {
  it('sends a message, streams tokens, and reconciles after stream_end', async () => {
    useUI.setState({ activeProjectId: 1 })

    const user = userEvent.setup()
    renderChat()

    // Wait for sessions + messages to load.
    await waitFor(() =>
      expect(screen.getByText(/What does finding 42 mean\?/i)).toBeInTheDocument()
    )

    const textarea = screen.getByPlaceholderText(/Ask about your security findings/i)
    await user.click(textarea)
    await user.keyboard('What is the CVSS?')
    await user.click(screen.getByRole('button', { name: /send message/i }))

    // Optimistic user turn appears.
    await waitFor(() => expect(screen.getByText('What is the CVSS?')).toBeInTheDocument())

    // SSE subscribes.
    await waitFor(() =>
      expect(
        MockEventSource.instances.some(es => es.url.includes('/chat/stream?session_id=101'))
      ).toBe(true)
    )
    const es = MockEventSource.instances.find(es =>
      es.url.includes('/chat/stream?session_id=101')
    )
    if (!es) throw new Error('chat SSE never opened')

    act(() => {
      es.emitTyped('stream_start', { project_id: 1, session_id: 101, message_id: null })
    })
    act(() => {
      es.emitTyped('token', {
        project_id: 1,
        session_id: 101,
        message_id: null,
        chunk: 'CVSS ',
      })
      es.emitTyped('token', {
        project_id: 1,
        session_id: 101,
        message_id: null,
        chunk: '9.8',
      })
    })
    await waitFor(() => expect(screen.getByText(/CVSS 9\.8/)).toBeInTheDocument())

    act(() => {
      es.emitTyped('stream_end', {
        project_id: 1,
        session_id: 101,
        message_id: 7777,
        content: 'CVSS 9.8',
      })
    })
    // After stream_end, the streamingOverlay clears and persisted query
    // is invalidated — UI returns to "CONNECTED" state.
    await waitFor(() => expect(screen.getByText(/CONNECTED/i)).toBeInTheDocument())
  })
})

// ─── Cancel flow ───────────────────────────────────────────────────────────

describe('Chat page — cancel flow', () => {
  it('hits the cancel endpoint and clears overlay on stream_cancelled', async () => {
    useUI.setState({ activeProjectId: 1 })
    let cancelCalled = false
    server.use(
      http.post('/api/v1/projects/1/chat/sessions/101/cancel', () => {
        cancelCalled = true
        return HttpResponse.json({ session_id: 101, cancelled_message_id: null }, { status: 202 })
      })
    )

    const user = userEvent.setup()
    renderChat()

    await waitFor(() =>
      expect(screen.getByText(/What does finding 42 mean\?/i)).toBeInTheDocument()
    )

    const textarea = screen.getByPlaceholderText(/Ask about your security findings/i)
    await user.click(textarea)
    await user.keyboard('Tell me more')
    await user.click(screen.getByRole('button', { name: /send message/i }))

    await waitFor(() =>
      expect(
        MockEventSource.instances.some(es => es.url.includes('session_id=101'))
      ).toBe(true)
    )
    const es = MockEventSource.instances.find(es => es.url.includes('session_id=101'))!
    act(() => {
      es.emitTyped('stream_start', { project_id: 1, session_id: 101, message_id: null })
    })

    const cancelBtn = await screen.findByRole('button', { name: /cancel stream/i })
    await user.click(cancelBtn)
    await waitFor(() => expect(cancelCalled).toBe(true))

    act(() => {
      es.emitTyped('stream_cancelled', {
        project_id: 1,
        session_id: 101,
        message_id: null,
        message: 'stream cancelled',
      })
    })
    await waitFor(() => expect(screen.getByText(/CONNECTED/i)).toBeInTheDocument())
  })
})

// ─── Delete flow ───────────────────────────────────────────────────────────

describe('Chat page — delete flow', () => {
  it('deletes a session and clears active when the deleted session was active', async () => {
    useUI.setState({ activeProjectId: 1 })
    let deleted = false
    server.use(
      http.delete('/api/v1/projects/1/chat/sessions/101', () => {
        deleted = true
        return new HttpResponse(null, { status: 204 })
      })
    )

    const user = userEvent.setup()
    renderChat()

    await waitFor(() =>
      expect(screen.getByText(/^2026-04-28 10:00$/)).toBeInTheDocument()
    )

    const sessionRow = screen.getByTestId('chat-session-101')
    const deleteBtn = sessionRow.querySelector('button[aria-label="delete session"]')!
    await user.click(deleteBtn as HTMLElement)
    await waitFor(() => expect(deleted).toBe(true))
  })
})

// ─── Expired session error flow ────────────────────────────────────────────

describe('Chat page — expired session', () => {
  it('shows the chat-action-failed modal when sending to an expired session', async () => {
    useUI.setState({ activeProjectId: 1 })

    const user = userEvent.setup()
    renderChat()

    await waitFor(() =>
      expect(screen.getByText(/^2026-04-25 09:00$/)).toBeInTheDocument()
    )
    // Click the sealed session (id 103).
    await user.click(screen.getByTestId('chat-session-103'))
    // Input should be disabled (placeholder switches).
    const sealedTextarea = await screen.findByPlaceholderText(/session sealed/i)
    expect(sealedTextarea).toBeDisabled()
  })
})

// ─── Create new session ────────────────────────────────────────────────────

describe('Chat page — new session button', () => {
  it('creates a new session and switches to it', async () => {
    useUI.setState({ activeProjectId: 1 })

    let posted = false
    server.use(
      http.post('/api/v1/projects/1/chat/sessions', () => {
        posted = true
        return HttpResponse.json(
          {
            id: 999,
            project_id: 1,
            title: '2026-04-28 13:00',
            created_at: '2026-04-28T13:00:00+00:00',
            last_message_at: null,
            message_count: 0,
            expired_at: null,
          },
          { status: 201 }
        )
      })
    )

    const user = userEvent.setup()
    renderChat()
    await waitFor(() =>
      expect(screen.getByText(/^2026-04-28 10:00$/)).toBeInTheDocument()
    )
    await user.click(screen.getByRole('button', { name: /New Chat/i }))
    await waitFor(() => expect(posted).toBe(true))
  })
})
