import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  useChatSessions,
  useChatMessages,
  useCreateChatSession,
  useSendChatMessage,
  useCancelChatStream,
  useDeleteChatSession,
  useChatStream,
} from '@/lib/api/useChat'
import { __setEventSourceFactory } from '@/lib/api/sse'
import { useUI } from '@/lib/store'
import type { ChatStreamEvent } from '@/lib/types'
import { server } from '../../../handlers'
import { MockEventSource } from '../../../helpers/sse'
import { setCookie, clearAllCookies } from '../../../helpers/cookies'

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return {
    qc,
    wrapper: ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children),
  }
}

beforeEach(() => {
  clearAllCookies()
  setCookie('tally_csrf', 'test-csrf-token')
  useUI.setState({ chatMutationError: null })
  MockEventSource.reset()
  __setEventSourceFactory(
    (url, init) => new MockEventSource(url, init) as unknown as EventSource
  )
})

afterEach(() => {
  __setEventSourceFactory(null)
  server.resetHandlers()
})

// ─── useChatSessions ────────────────────────────────────────────────────────

describe('useChatSessions', () => {
  it('returns project-1 sessions mapped to camelCase with integer ids', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useChatSessions(1), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toHaveLength(3)
    expect(result.current.total).toBe(3)
    const first = result.current.data[0]
    expect(first.id).toBe(101)
    expect(first.projectId).toBe(2)
    expect(first.title).toBe('Triage walkthrough — XSS findings')
    expect(first.expiredAt).toBeNull()
    expect(result.current.data[2].expiredAt).toBe('2026-04-26T11:45:00+00:00')
  })

  it('returns empty data and total 0 for project with no sessions', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useChatSessions(3), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toHaveLength(0)
    expect(result.current.total).toBe(0)
  })

  it('stays idle when projectId is null', () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useChatSessions(null), { wrapper })
    expect(result.current.isPending).toBe(true)
    expect(result.current.data).toHaveLength(0)
  })
})

// ─── useChatMessages ────────────────────────────────────────────────────────

describe('useChatMessages', () => {
  it('returns mapped messages for session 101 with model + citations fields', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useChatMessages(1, 101), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toHaveLength(4)
    const userMsg = result.current.data[0]
    expect(userMsg.role).toBe('user')
    expect(userMsg.id).toBe(1001)
    expect(userMsg.sessionId).toBe(101)
    expect(userMsg.model).toBeNull()
    expect(userMsg.citations).toBeNull()
    const assistantMsg = result.current.data[1]
    expect(assistantMsg.role).toBe('assistant')
    expect(assistantMsg.model).toBe('claude-sonnet-4-6')
  })

  it('returns empty data for unknown session id', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useChatMessages(1, 102), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toHaveLength(0)
  })

  it('stays idle when sessionId is null', () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useChatMessages(1, null), { wrapper })
    expect(result.current.isPending).toBe(true)
  })

  it('forwards offset and limit query params', async () => {
    let captured: { offset: string | null; limit: string | null } = {
      offset: null,
      limit: null,
    }
    server.use(
      http.get(
        '/api/v1/projects/:projectId/chat/sessions/:sessionId/messages',
        ({ request }) => {
          const url = new URL(request.url)
          captured = {
            offset: url.searchParams.get('offset'),
            limit: url.searchParams.get('limit'),
          }
          return HttpResponse.json({ items: [], total: 0, offset: 0, limit: 50 })
        }
      )
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useChatMessages(1, 101), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(captured.offset).toBe('0')
    expect(captured.limit).toBe('50')
  })
})

// ─── useCreateChatSession ───────────────────────────────────────────────────

describe('useCreateChatSession', () => {
  it('POSTs an empty body and returns the mapped session', async () => {
    let bodyText = ''
    server.use(
      http.post('/api/v1/projects/:projectId/chat/sessions', async ({ request }) => {
        bodyText = await request.text()
        return HttpResponse.json(
          {
            id: 555,
            project_id: 1,
            title: '2026-04-28 14:00',
            created_at: '2026-04-28T14:00:00+00:00',
            last_message_at: null,
            message_count: 0,
            expired_at: null,
          },
          { status: 201 }
        )
      })
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useCreateChatSession(), { wrapper })
    let session: { id: number; projectId: number; title: string } | null = null
    await act(async () => {
      session = (await result.current.mutateAsync({
        projectId: 1,
      })) as unknown as typeof session
    })
    expect(bodyText).toBe('{}')
    expect(session?.id).toBe(555)
    expect(session?.projectId).toBe(1)
    expect(session?.title).toBe('2026-04-28 14:00')
  })

  it('routes 404 NOT_FOUND through setChatMutationError', async () => {
    server.use(
      http.post(
        '/api/v1/projects/:projectId/chat/sessions',
        () =>
          new HttpResponse(
            JSON.stringify({
              error: { code: 'NOT_FOUND', message: 'project not found', details: {} },
            }),
            { status: 404, headers: { 'Content-Type': 'application/json' } }
          )
      )
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useCreateChatSession(), { wrapper })
    await act(async () => {
      await result.current.mutateAsync({ projectId: 1 }).catch(() => undefined)
    })
    expect(useUI.getState().chatMutationError?.code).toBe('NOT_FOUND')
    expect(useUI.getState().chatMutationError?.status).toBe(404)
  })
})

// ─── useSendChatMessage ─────────────────────────────────────────────────────

describe('useSendChatMessage', () => {
  it('POSTs { content } and returns mapped response with assistant id null', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      http.post(
        '/api/v1/projects/:projectId/chat/sessions/:sessionId/messages',
        async ({ request }) => {
          body = (await request.json()) as Record<string, unknown>
          return HttpResponse.json(
            {
              user_message_id: 5001,
              assistant_message_id: null,
              session_id: 101,
              stream_url: '/api/v1/projects/1/chat/stream?session_id=101',
            },
            { status: 202 }
          )
        }
      )
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useSendChatMessage(), { wrapper })
    let resp:
      | { userMessageId: number; assistantMessageId: null; sessionId: number; streamUrl: string }
      | null = null
    await act(async () => {
      resp = (await result.current.mutateAsync({
        projectId: 1,
        sessionId: 101,
        content: 'Hello',
      })) as unknown as typeof resp
    })
    expect(body).toEqual({ content: 'Hello' })
    expect(resp?.userMessageId).toBe(5001)
    expect(resp?.assistantMessageId).toBeNull()
    expect(resp?.sessionId).toBe(101)
    expect(resp?.streamUrl).toContain('session_id=101')
  })

  it('routes 409 CHAT_SESSION_EXPIRED through setChatMutationError', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useSendChatMessage(), { wrapper })
    await act(async () => {
      await result.current
        .mutateAsync({ projectId: 1, sessionId: 901, content: 'hi' })
        .catch(() => undefined)
    })
    expect(useUI.getState().chatMutationError?.code).toBe('CHAT_SESSION_EXPIRED')
    expect(useUI.getState().chatMutationError?.status).toBe(409)
  })

  it('routes 409 CHAT_STREAM_ALREADY_RUNNING through setChatMutationError', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useSendChatMessage(), { wrapper })
    await act(async () => {
      await result.current
        .mutateAsync({ projectId: 1, sessionId: 902, content: 'hi' })
        .catch(() => undefined)
    })
    expect(useUI.getState().chatMutationError?.code).toBe('CHAT_STREAM_ALREADY_RUNNING')
  })

  it('routes 422 VALIDATION_ERROR through setChatMutationError', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useSendChatMessage(), { wrapper })
    await act(async () => {
      await result.current
        .mutateAsync({ projectId: 1, sessionId: 903, content: 'hi' })
        .catch(() => undefined)
    })
    expect(useUI.getState().chatMutationError?.code).toBe('VALIDATION_ERROR')
  })
})

// ─── useCancelChatStream ────────────────────────────────────────────────────

describe('useCancelChatStream', () => {
  it('returns the cancel response on 202', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useCancelChatStream(), { wrapper })
    let resp: { sessionId: number; cancelledMessageId: null } | null = null
    await act(async () => {
      resp = (await result.current.mutateAsync({
        projectId: 1,
        sessionId: 101,
      })) as unknown as typeof resp
    })
    expect(resp?.sessionId).toBe(101)
    expect(resp?.cancelledMessageId).toBeNull()
  })

  it('routes 409 CHAT_NO_ACTIVE_STREAM through setChatMutationError', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useCancelChatStream(), { wrapper })
    await act(async () => {
      await result.current
        .mutateAsync({ projectId: 1, sessionId: 904 })
        .catch(() => undefined)
    })
    expect(useUI.getState().chatMutationError?.code).toBe('CHAT_NO_ACTIVE_STREAM')
  })
})

// ─── useDeleteChatSession ───────────────────────────────────────────────────

describe('useDeleteChatSession', () => {
  it('issues DELETE and resolves to undefined on 204', async () => {
    let calledMethod: string | null = null
    server.use(
      http.delete(
        '/api/v1/projects/:projectId/chat/sessions/:sessionId',
        ({ request }) => {
          calledMethod = request.method
          return new HttpResponse(null, { status: 204 })
        }
      )
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useDeleteChatSession(), { wrapper })
    await act(async () => {
      await result.current.mutateAsync({ projectId: 1, sessionId: 101 })
    })
    expect(calledMethod).toBe('DELETE')
  })

  it('routes 404 NOT_FOUND through setChatMutationError', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useDeleteChatSession(), { wrapper })
    await act(async () => {
      await result.current
        .mutateAsync({ projectId: 1, sessionId: 905 })
        .catch(() => undefined)
    })
    expect(useUI.getState().chatMutationError?.code).toBe('NOT_FOUND')
  })
})

// ─── useChatStream ──────────────────────────────────────────────────────────

describe('useChatStream', () => {
  it('opens a project-scoped SSE with session_id query param', async () => {
    const { wrapper } = makeWrapper()
    renderHook(() => useChatStream(1, 101, () => undefined), { wrapper })
    await waitFor(() => expect(MockEventSource.instances.length).toBe(1))
    const es = MockEventSource.instances[0]
    expect(es.url).toContain('/projects/1/chat/stream?session_id=101')
  })

  it('routes typed events through the onEvent callback (mapped to camelCase)', async () => {
    const seen: ChatStreamEvent[] = []
    const { wrapper } = makeWrapper()
    renderHook(() => useChatStream(1, 101, e => seen.push(e)), { wrapper })
    await waitFor(() => expect(MockEventSource.instances.length).toBe(1))
    const es = MockEventSource.instances[0]
    es.emitTyped('stream_start', {
      project_id: 1,
      session_id: 101,
      message_id: null,
    })
    es.emitTyped('token', {
      project_id: 1,
      session_id: 101,
      message_id: null,
      chunk: 'Hello ',
    })
    es.emitTyped('token', {
      project_id: 1,
      session_id: 101,
      message_id: null,
      chunk: 'world',
    })
    es.emitTyped('stream_end', {
      project_id: 1,
      session_id: 101,
      message_id: 7777,
      content: 'Hello world',
    })
    expect(seen).toHaveLength(4)
    expect(seen[0].type).toBe('stream_start')
    expect(seen[1]).toMatchObject({ type: 'token', chunk: 'Hello ', sessionId: 101 })
    expect(seen[3]).toMatchObject({ type: 'stream_end', messageId: 7777, content: 'Hello world' })
  })

  it('forwards snapshot frames through onSnapshot with mapped fields', async () => {
    let snap: { active: boolean; userMessageId: number | null } | null = null
    const { wrapper } = makeWrapper()
    renderHook(
      () =>
        useChatStream(1, 101, () => undefined, {
          onSnapshot: s => {
            snap = { active: s.active, userMessageId: s.userMessageId }
          },
        }),
      { wrapper }
    )
    await waitFor(() => expect(MockEventSource.instances.length).toBe(1))
    MockEventSource.instances[0].emitTyped('snapshot', {
      project_id: 1,
      session_id: 101,
      active: true,
      user_message_id: 42,
    })
    expect(snap).toEqual({ active: true, userMessageId: 42 })
  })

  it('maps stream_cancelled and error events with messageId null', async () => {
    const seen: ChatStreamEvent[] = []
    const { wrapper } = makeWrapper()
    renderHook(() => useChatStream(1, 101, e => seen.push(e)), { wrapper })
    await waitFor(() => expect(MockEventSource.instances.length).toBe(1))
    const es = MockEventSource.instances[0]
    es.emitTyped('error', {
      project_id: 1,
      session_id: 101,
      message_id: null,
      error: 'LLMAdapterError',
      message: 'rate limited',
    })
    es.emitTyped('stream_cancelled', {
      project_id: 1,
      session_id: 101,
      message_id: null,
      message: 'stream cancelled',
    })
    expect(seen[0]).toMatchObject({
      type: 'error',
      error: 'LLMAdapterError',
      message: 'rate limited',
    })
    expect(seen[1]).toMatchObject({ type: 'stream_cancelled', message: 'stream cancelled' })
  })

  it('does not subscribe when enabled is false', () => {
    const { wrapper } = makeWrapper()
    renderHook(() => useChatStream(1, 101, () => undefined, { enabled: false }), { wrapper })
    expect(MockEventSource.instances).toHaveLength(0)
  })

  it('does not subscribe when sessionId is null', () => {
    const { wrapper } = makeWrapper()
    renderHook(() => useChatStream(1, null, () => undefined), { wrapper })
    expect(MockEventSource.instances).toHaveLength(0)
  })
})
