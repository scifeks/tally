import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { render, screen, waitFor, act, within } from '@testing-library/react'
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

describe('Chat page - session list', () => {
  it('renders project-1 sessions and auto-selects the first one', async () => {
    useUI.setState({ activeProjectId: 1 })
    renderChat()
    await waitFor(() =>
      expect(screen.getByText(/Triage walkthrough — XSS findings/)).toBeInTheDocument()
    )
    expect(screen.getByText(/Investigating gitleaks AWS key/)).toBeInTheDocument()
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

describe('Chat page - persisted messages', () => {
  it('renders the 4 turns from session 101 fixture', async () => {
    useUI.setState({ activeProjectId: 1 })
    renderChat()
    await waitFor(() =>
      expect(screen.getByText(/most severe XSS finding/i)).toBeInTheDocument()
    )
    expect(
      screen.getByText(/dalfox-detected reflected XSS/i)
    ).toBeInTheDocument()
    expect(screen.getByText(/Are there any in php-goof\?/i)).toBeInTheDocument()
  })
})

// ─── Send + stream golden path ─────────────────────────────────────────────

describe('Chat page - send + stream golden path', () => {
  it('sends a message, streams tokens, and reconciles after stream_end', async () => {
    useUI.setState({ activeProjectId: 1 })

    const user = userEvent.setup()
    renderChat()

    // Wait for sessions + messages to load.
    await waitFor(() =>
      expect(screen.getByText(/most severe XSS finding/i)).toBeInTheDocument()
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
    // is invalidated - UI returns to "CONNECTED" state.
    await waitFor(() => expect(screen.getByText(/CONNECTED/i)).toBeInTheDocument())
  })
})

// ─── Cancel flow ───────────────────────────────────────────────────────────

describe('Chat page - cancel flow', () => {
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
      expect(screen.getByText(/most severe XSS finding/i)).toBeInTheDocument()
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

describe('Chat page - delete flow', () => {
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
      expect(screen.getByText(/Triage walkthrough — XSS findings/)).toBeInTheDocument()
    )

    const sessionRow = screen.getByTestId('chat-session-101')
    const deleteBtn = sessionRow.querySelector('button[aria-label="delete session"]')!
    await user.click(deleteBtn as HTMLElement)
    await waitFor(() => expect(deleted).toBe(true))
  })
})

// ─── Sealed session UX (12.7) ──────────────────────────────────────────────

describe('Chat page - sealed session UX (12.7)', () => {
  it('shows the sealed badge, banner, and sealed input panel — and hides the textarea', async () => {
    useUI.setState({ activeProjectId: 1 })

    const user = userEvent.setup()
    renderChat()

    await waitFor(() =>
      expect(screen.getByText(/Old session about pip-audit/)).toBeInTheDocument()
    )
    await user.click(screen.getByTestId('chat-session-103'))

    // Prominent badge in the session header.
    const badge = await screen.findByTestId('sealed-badge')
    expect(badge).toHaveTextContent(/sealed/i)

    // Banner above the messages explains the cause and offers a CTA.
    const banner = screen.getByTestId('sealed-banner')
    expect(banner).toHaveTextContent(/scan ran since this chat started/i)
    expect(banner).toHaveTextContent(/start a new chat/i)
    expect(within(banner).getByRole('button', { name: /new chat/i })).toBeInTheDocument()

    // Bottom panel replaces the chat input so it cannot be confused for an active session.
    const inputPanel = screen.getByTestId('sealed-input-panel')
    expect(inputPanel).toHaveTextContent(/session sealed/i)
    expect(
      within(inputPanel).getByRole('button', { name: /start new chat/i })
    ).toBeInTheDocument()

    // The active-session textarea must NOT render for a sealed session.
    expect(
      screen.queryByPlaceholderText(/Ask about your security findings/i)
    ).not.toBeInTheDocument()
  })

  it('does not show the sealed banner or panel on an active session', async () => {
    useUI.setState({ activeProjectId: 1 })

    renderChat()
    await waitFor(() =>
      expect(screen.getByText(/most severe XSS finding/i)).toBeInTheDocument()
    )

    expect(screen.queryByTestId('sealed-badge')).not.toBeInTheDocument()
    expect(screen.queryByTestId('sealed-banner')).not.toBeInTheDocument()
    expect(screen.queryByTestId('sealed-input-panel')).not.toBeInTheDocument()
    expect(
      screen.getByPlaceholderText(/Ask about your security findings/i)
    ).toBeInTheDocument()
  })
})

// ─── User-prompt dedup hardening (12.8) ────────────────────────────────────

describe('Chat page - prompt dedup after stream end (12.8)', () => {
  it('renders the user prompt exactly once even when persisted and overlay ids drift', async () => {
    useUI.setState({ activeProjectId: 1 })

    // The handler returns user_message_id 5001 from POST. We override the
    // messages GET so that — as if the persisted user-message id and the
    // POST-returned id had drifted — the persisted user message has a
    // different id (id 6001) but the same content the user just typed.
    server.use(
      http.get('/api/v1/projects/1/chat/sessions/101/messages', ({ request }) => {
        const url = new URL(request.url)
        const offset = Number(url.searchParams.get('offset') ?? 0)
        const limit = Number(url.searchParams.get('limit') ?? 50)
        const baseFixture = {
          items: [
            {
              id: 1001,
              session_id: 101,
              role: 'user',
              content: 'What does finding 42 mean?',
              model: null,
              timestamp: '2026-04-28T10:00:00+00:00',
              citations: null,
            },
            {
              id: 6001,
              session_id: 101,
              role: 'user',
              content: 'Drift case prompt',
              model: null,
              timestamp: '2026-04-28T10:10:00+00:00',
              citations: null,
            },
          ],
          total: 2,
          offset: 0,
          limit: 50,
        }
        const slice = baseFixture.items.slice(offset, offset + limit)
        return HttpResponse.json({ items: slice, total: 2, offset, limit })
      })
    )

    const user = userEvent.setup()
    renderChat()

    await waitFor(() =>
      expect(screen.getByText(/What does finding 42 mean\?/i)).toBeInTheDocument()
    )

    const textarea = screen.getByPlaceholderText(/Ask about your security findings/i)
    await user.click(textarea)
    await user.keyboard('Drift case prompt')
    await user.click(screen.getByRole('button', { name: /send message/i }))

    // The messages cache already holds 'Drift case prompt' under id 6001
    // (different from POST's user_message_id 5001). With ID-only dedup
    // there would be two copies; the role+content fallback guarantees one.
    await waitFor(
      () => expect(screen.getAllByText(/^Drift case prompt$/i)).toHaveLength(1),
      { timeout: 2000 }
    )
  })

  it('keeps the user prompt visible across stream_end while the messages refetch resolves', async () => {
    useUI.setState({ activeProjectId: 1 })

    // Block the messages refetch behind a manually-resolved promise so we
    // can observe the page state after stream_end but before the cache
    // updates. Without the deferred-clear fix, the user prompt would
    // disappear here; with it, the overlay survives until the refetch
    // resolves and the persisted user/assistant pair takes over.
    let releaseRefetch: (() => void) | null = null
    let refetchCount = 0
    server.use(
      http.get('/api/v1/projects/1/chat/sessions/101/messages', async () => {
        refetchCount += 1
        if (refetchCount > 1) {
          await new Promise<void>(resolve => {
            releaseRefetch = resolve
          })
          return HttpResponse.json({
            items: [
              {
                id: 1001,
                session_id: 101,
                role: 'user',
                content: 'What does finding 42 mean?',
                model: null,
                timestamp: '2026-04-28T10:00:00+00:00',
                citations: null,
              },
              {
                id: 5001,
                session_id: 101,
                role: 'user',
                content: 'Defer test prompt',
                model: null,
                timestamp: '2026-04-28T10:30:00+00:00',
                citations: null,
              },
              {
                id: 7777,
                session_id: 101,
                role: 'assistant',
                content: 'reply',
                model: 'claude-sonnet-4-6',
                timestamp: '2026-04-28T10:30:05+00:00',
                citations: null,
              },
            ],
            total: 3,
            offset: 0,
            limit: 50,
          })
        }
        return HttpResponse.json({
          items: [
            {
              id: 1001,
              session_id: 101,
              role: 'user',
              content: 'What does finding 42 mean?',
              model: null,
              timestamp: '2026-04-28T10:00:00+00:00',
              citations: null,
            },
          ],
          total: 1,
          offset: 0,
          limit: 50,
        })
      })
    )

    const user = userEvent.setup()
    renderChat()

    await waitFor(() =>
      expect(screen.getByText(/What does finding 42 mean\?/i)).toBeInTheDocument()
    )

    const textarea = screen.getByPlaceholderText(/Ask about your security findings/i)
    await user.click(textarea)
    await user.keyboard('Defer test prompt')
    await user.click(screen.getByRole('button', { name: /send message/i }))

    await waitFor(() => expect(screen.getByText('Defer test prompt')).toBeInTheDocument())

    const es = await waitFor(() => {
      const found = MockEventSource.instances.find(s =>
        s.url.includes('/chat/stream?session_id=101')
      )
      if (!found) throw new Error('chat SSE not opened')
      return found
    })

    act(() => {
      es.emitTyped('stream_start', { project_id: 1, session_id: 101, message_id: null })
    })
    act(() => {
      es.emitTyped('token', {
        project_id: 1,
        session_id: 101,
        message_id: null,
        chunk: 'reply ',
      })
    })
    act(() => {
      es.emitTyped('stream_end', {
        project_id: 1,
        session_id: 101,
        message_id: 7777,
        content: 'reply',
      })
    })

    // Refetch is in flight (paused). The overlay must still render the
    // user prompt — without the deferred clear it would already be gone.
    await waitFor(() => expect(screen.getByText('Defer test prompt')).toBeInTheDocument())

    act(() => {
      releaseRefetch?.()
    })

    await waitFor(() => expect(screen.getByText(/CONNECTED/i)).toBeInTheDocument())
    expect(screen.getAllByText('Defer test prompt')).toHaveLength(1)
  })
})

// ─── Create new session ────────────────────────────────────────────────────

describe('Chat page - new session button', () => {
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
      expect(screen.getByText(/Triage walkthrough — XSS findings/)).toBeInTheDocument()
    )
    await user.click(screen.getByRole('button', { name: /New Chat/i }))
    await waitFor(() => expect(posted).toBe(true))
  })
})
