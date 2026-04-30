/**
 * useChat Hooks
 * =============
 * Wires the Chat page (sessions, messages, send + streaming, cancel,
 * delete) to the real backend. Mirrors `useReports.ts`: project-scoped
 * REST + SSE, `useInfiniteQuery` for paginated message history, inline
 * snake→camel mappers, mutation errors routed through the
 * `chatMutationError` Zustand slice for the dedicated mutation-error
 * modal.
 *
 * Endpoint contract (endpoints.md §12):
 *   GET    /api/v1/projects/:id/chat/sessions
 *   POST   /api/v1/projects/:id/chat/sessions                    - empty body
 *   DELETE /api/v1/projects/:id/chat/sessions/:sid
 *   GET    /api/v1/projects/:id/chat/sessions/:sid/messages      - paginated
 *   POST   /api/v1/projects/:id/chat/sessions/:sid/messages      - body { content }
 *   POST   /api/v1/projects/:id/chat/sessions/:sid/cancel        - empty body
 *   GET    /api/v1/projects/:id/chat/stream?session_id=:sid      - SSE
 */

import { useEffect, useMemo, useRef } from 'react'
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type {
  ApiErrorPayload,
  ChatCancelResponse,
  ChatMessage,
  ChatMessageRole,
  ChatSendMessageResponse,
  ChatSession,
  ChatStreamEvent,
  ChatStreamEventType,
  ChatStreamSnapshotPayload,
} from '../types'
import type { ApiError } from './client'
import { apiFetch } from './client'
import { apiEventSource } from './sse'
import { REST_ENDPOINTS, SSE_ENDPOINTS } from './config'
import { useUI } from '../store'

// ─── Wire-format types ──────────────────────────────────────────────────────

interface ChatSessionApi {
  id: number
  project_id: number
  title: string
  created_at: string
  last_message_at: string | null
  message_count: number
  expired_at: string | null
}

interface ChatSessionsResponseApi {
  items: ChatSessionApi[]
  total: number
  offset: number
  limit: number
}

interface ChatMessageApi {
  id: number
  session_id: number
  role: ChatMessageRole
  content: string
  model: string | null
  timestamp: string
  citations: null
}

interface ChatMessagesResponseApi {
  items: ChatMessageApi[]
  total: number
  offset: number
  limit: number
}

interface ChatSendMessageResponseApi {
  user_message_id: number
  assistant_message_id: null
  session_id: number
  stream_url: string
}

interface ChatCancelResponseApi {
  session_id: number
  cancelled_message_id: null
}

interface ChatStreamSnapshotApi {
  project_id: number
  session_id: number
  active: boolean
  user_message_id?: number | null
}

interface ChatTokenEventApi {
  project_id: number
  session_id: number
  message_id: number | null
  chunk?: string
  content?: string
  error?: string
  message?: string
}

// ─── Mappers ────────────────────────────────────────────────────────────────

export function mapChatSession(api: ChatSessionApi): ChatSession {
  return {
    id: api.id,
    projectId: api.project_id,
    title: api.title,
    createdAt: api.created_at,
    lastMessageAt: api.last_message_at,
    messageCount: api.message_count,
    expiredAt: api.expired_at,
  }
}

export function mapChatMessage(api: ChatMessageApi): ChatMessage {
  return {
    id: api.id,
    sessionId: api.session_id,
    role: api.role,
    content: api.content,
    model: api.model,
    timestamp: api.timestamp,
    citations: null,
  }
}

function mapSendMessageResponse(api: ChatSendMessageResponseApi): ChatSendMessageResponse {
  return {
    userMessageId: api.user_message_id,
    assistantMessageId: null,
    sessionId: api.session_id,
    streamUrl: api.stream_url,
  }
}

function mapCancelResponse(api: ChatCancelResponseApi): ChatCancelResponse {
  return {
    sessionId: api.session_id,
    cancelledMessageId: null,
  }
}

function mapChatSnapshot(api: ChatStreamSnapshotApi): ChatStreamSnapshotPayload {
  return {
    projectId: api.project_id,
    sessionId: api.session_id,
    active: api.active,
    userMessageId: api.user_message_id ?? null,
  }
}

function mapChatStreamEvent(type: ChatStreamEventType, data: ChatTokenEventApi): ChatStreamEvent {
  switch (type) {
    case 'stream_start':
      return {
        type: 'stream_start',
        projectId: data.project_id,
        sessionId: data.session_id,
        messageId: null,
      }
    case 'token':
      return {
        type: 'token',
        projectId: data.project_id,
        sessionId: data.session_id,
        messageId: null,
        chunk: data.chunk ?? '',
      }
    case 'stream_end':
      return {
        type: 'stream_end',
        projectId: data.project_id,
        sessionId: data.session_id,
        messageId: data.message_id as number,
        content: data.content ?? '',
      }
    case 'error':
      return {
        type: 'error',
        projectId: data.project_id,
        sessionId: data.session_id,
        messageId: null,
        error: data.error ?? 'unknown',
        message: data.message ?? '',
      }
    case 'stream_cancelled':
      return {
        type: 'stream_cancelled',
        projectId: data.project_id,
        sessionId: data.session_id,
        messageId: null,
        message: data.message ?? 'stream cancelled',
      }
  }
}

function toErrorPayload(err: ApiError): ApiErrorPayload {
  return {
    code: err.code,
    message: err.message,
    details: err.details,
    status: err.status,
  }
}

// ─── Read hooks ─────────────────────────────────────────────────────────────

const SESSIONS_PAGE_LIMIT = 50
const MESSAGES_PAGE_LIMIT = 50

function buildChatSessionsUrl(projectId: number, offset: number, limit: number): string {
  const params = new URLSearchParams()
  params.set('offset', String(offset))
  params.set('limit', String(limit))
  return `${REST_ENDPOINTS.chatSessions(projectId)}?${params.toString()}`
}

interface ChatSessionsPage {
  items: ChatSession[]
  total: number
  offset: number
  limit: number
}

export function useChatSessions(projectId: number | null) {
  const limit = SESSIONS_PAGE_LIMIT
  const query = useInfiniteQuery({
    queryKey: ['chat', projectId, 'sessions', { limit }] as const,
    initialPageParam: 0,
    queryFn: async ({ pageParam }): Promise<ChatSessionsPage> => {
      const url = buildChatSessionsUrl(projectId as number, pageParam as number, limit)
      const data = await apiFetch<ChatSessionsResponseApi>(url)
      return {
        items: data.items.map(mapChatSession),
        total: data.total,
        offset: data.offset,
        limit: data.limit,
      }
    },
    getNextPageParam: lastPage => {
      const next = lastPage.offset + lastPage.items.length
      return next < lastPage.total ? next : undefined
    },
    enabled: projectId !== null,
    staleTime: 10_000,
  })

  const items = useMemo(() => query.data?.pages.flatMap(p => p.items) ?? [], [query.data])
  const total = query.data?.pages[0]?.total ?? 0

  return {
    data: items,
    total,
    fetchNextPage: query.fetchNextPage,
    hasNextPage: query.hasNextPage ?? false,
    isFetchingNextPage: query.isFetchingNextPage,
    isLoading: query.isLoading,
    isPending: query.isPending,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
    isSuccess: query.isSuccess,
  }
}

function buildChatMessagesUrl(
  projectId: number,
  sessionId: number,
  offset: number,
  limit: number
): string {
  const params = new URLSearchParams()
  params.set('offset', String(offset))
  params.set('limit', String(limit))
  return `${REST_ENDPOINTS.chatMessages(projectId, sessionId)}?${params.toString()}`
}

interface ChatMessagesPage {
  items: ChatMessage[]
  total: number
  offset: number
  limit: number
}

export function useChatMessages(projectId: number | null, sessionId: number | null) {
  const limit = MESSAGES_PAGE_LIMIT
  const enabled = projectId !== null && sessionId !== null
  const query = useInfiniteQuery({
    queryKey: ['chat', projectId, 'messages', sessionId, { limit }] as const,
    initialPageParam: 0,
    queryFn: async ({ pageParam }): Promise<ChatMessagesPage> => {
      const url = buildChatMessagesUrl(
        projectId as number,
        sessionId as number,
        pageParam as number,
        limit
      )
      const data = await apiFetch<ChatMessagesResponseApi>(url)
      return {
        items: data.items.map(mapChatMessage),
        total: data.total,
        offset: data.offset,
        limit: data.limit,
      }
    },
    getNextPageParam: lastPage => {
      const next = lastPage.offset + lastPage.items.length
      return next < lastPage.total ? next : undefined
    },
    enabled,
    staleTime: 10_000,
  })

  const items = useMemo(() => query.data?.pages.flatMap(p => p.items) ?? [], [query.data])
  const total = query.data?.pages[0]?.total ?? 0

  return {
    data: items,
    total,
    fetchNextPage: query.fetchNextPage,
    hasNextPage: query.hasNextPage ?? false,
    isFetchingNextPage: query.isFetchingNextPage,
    isLoading: query.isLoading,
    isPending: query.isPending,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
    isSuccess: query.isSuccess,
  }
}

// ─── Mutations ──────────────────────────────────────────────────────────────

export interface CreateChatSessionVariables {
  projectId: number
}

export function useCreateChatSession() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setChatMutationError)

  return useMutation<ChatSession, ApiError, CreateChatSessionVariables>({
    mutationFn: async ({ projectId }) => {
      const data = await apiFetch<ChatSessionApi>(REST_ENDPOINTS.createChatSession(projectId), {
        method: 'POST',
        body: {},
      })
      return mapChatSession(data)
    },
    onError: err => setError(toErrorPayload(err)),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['chat', projectId, 'sessions'] })
    },
  })
}

export interface SendChatMessageVariables {
  projectId: number
  sessionId: number
  content: string
}

export function useSendChatMessage() {
  const setError = useUI(s => s.setChatMutationError)

  return useMutation<ChatSendMessageResponse, ApiError, SendChatMessageVariables>({
    mutationFn: async ({ projectId, sessionId, content }) => {
      const data = await apiFetch<ChatSendMessageResponseApi>(
        REST_ENDPOINTS.sendChatMessage(projectId, sessionId),
        { method: 'POST', body: { content } }
      )
      return mapSendMessageResponse(data)
    },
    onError: err => setError(toErrorPayload(err)),
  })
}

export interface CancelChatStreamVariables {
  projectId: number
  sessionId: number
}

export function useCancelChatStream() {
  const setError = useUI(s => s.setChatMutationError)

  return useMutation<ChatCancelResponse, ApiError, CancelChatStreamVariables>({
    mutationFn: async ({ projectId, sessionId }) => {
      const data = await apiFetch<ChatCancelResponseApi>(
        REST_ENDPOINTS.cancelChatResponse(projectId, sessionId),
        { method: 'POST' }
      )
      return mapCancelResponse(data)
    },
    onError: err => setError(toErrorPayload(err)),
  })
}

export interface DeleteChatSessionVariables {
  projectId: number
  sessionId: number
}

export function useDeleteChatSession() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setChatMutationError)

  return useMutation<void, ApiError, DeleteChatSessionVariables>({
    mutationFn: async ({ projectId, sessionId }) => {
      await apiFetch<void>(REST_ENDPOINTS.deleteChatSession(projectId, sessionId), {
        method: 'DELETE',
      })
    },
    onError: err => setError(toErrorPayload(err)),
    onSuccess: (_, { projectId, sessionId }) => {
      queryClient.invalidateQueries({ queryKey: ['chat', projectId, 'sessions'] })
      queryClient.removeQueries({ queryKey: ['chat', projectId, 'messages', sessionId] })
    },
  })
}

// ─── SSE consumer ───────────────────────────────────────────────────────────

const CHAT_STREAM_EVENT_TYPES: readonly ChatStreamEventType[] = [
  'stream_start',
  'token',
  'stream_end',
  'error',
  'stream_cancelled',
] as const

export interface UseChatStreamOptions {
  enabled?: boolean
  onSnapshot?: (snap: ChatStreamSnapshotPayload) => void
}

export function useChatStream(
  projectId: number | null,
  sessionId: number | null,
  onEvent: (event: ChatStreamEvent) => void,
  options?: UseChatStreamOptions
) {
  const enabled = options?.enabled ?? true
  const onEventRef = useRef(onEvent)
  const onSnapshotRef = useRef(options?.onSnapshot)
  onEventRef.current = onEvent
  onSnapshotRef.current = options?.onSnapshot

  useEffect(() => {
    if (!enabled || projectId === null || sessionId === null) return
    const url = SSE_ENDPOINTS.chatStream(projectId, sessionId)
    const handle = apiEventSource(url, {
      eventTypes: ['snapshot', ...CHAT_STREAM_EVENT_TYPES],
      onEvent: (type, data) => {
        if (type === 'snapshot') {
          onSnapshotRef.current?.(mapChatSnapshot(data as ChatStreamSnapshotApi))
          return
        }
        if ((CHAT_STREAM_EVENT_TYPES as readonly string[]).includes(type)) {
          onEventRef.current(
            mapChatStreamEvent(type as ChatStreamEventType, data as ChatTokenEventApi)
          )
        }
      },
    })
    return () => handle.close()
  }, [projectId, sessionId, enabled])
}

/**
 * Hook helper to invalidate the cached message list for a session, useful
 * after `stream_end` so the SPA refetches the persisted assistant turn
 * (with its real DB id and `model` value).
 */
export function useInvalidateChatMessages() {
  const queryClient = useQueryClient()
  return (projectId: number, sessionId: number) =>
    queryClient.invalidateQueries({
      queryKey: ['chat', projectId, 'messages', sessionId],
    })
}
