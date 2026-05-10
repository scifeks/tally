import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Send, Square, Plus, Trash2, MessageSquare, Loader2, Lock } from 'lucide-react'
import { cn, parseIso } from '@/lib/utils'
import { useUI } from '@/lib/store'
import {
  useChatSessions,
  useChatMessages,
  useCreateChatSession,
  useSendChatMessage,
  useCancelChatStream,
  useDeleteChatSession,
  useChatStream,
  useProjects,
  useAppendChatMessageToCache,
} from '@/lib/api'
import type { ChatMessage, ChatSession, ChatStreamEvent } from '@/lib/types'
import { ChatMutationErrorModal } from '@/components/ChatMutationErrorModal'
import { NoProjectSelectedState } from '@/components/NoProjectSelectedState'

interface StreamingOverlay {
  assistantContent: string
  assistantTimestamp: string
  status: 'pending' | 'streaming' | 'complete' | 'cancelled' | 'error'
}

// ─── Message Bubble ─────────────────────────────────────────────────────────

function MessageBubble({ message, isLast }: { message: ChatMessage; isLast?: boolean }) {
  const isUser = message.role === 'user'
  const parsed = parseIso(message.timestamp)
  const time = parsed
    ? parsed.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      })
    : '—'

  return (
    <div
      className={cn(
        'flex flex-col gap-1 max-w-[85%]',
        isUser ? 'self-end items-end' : 'self-start items-start'
      )}
    >
      <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
        <span>{isUser ? 'YOU' : 'TALLY'}</span>
        <span className="text-dim">{time}</span>
      </div>
      <div
        className={cn(
          'px-3 py-2 text-[12px] leading-relaxed whitespace-pre-wrap',
          isUser
            ? 'bg-primary/20 border border-primary/40 text-primary'
            : 'bg-muted/50 border border-border text-foreground'
        )}
      >
        {message.content}
        {message.isStreaming && isLast && (
          <span className="inline-block w-2 h-4 ml-0.5 bg-accent animate-pulse" />
        )}
      </div>
    </div>
  )
}

// ─── Session List Item ──────────────────────────────────────────────────────

function SessionItem({
  session,
  isActive,
  onClick,
  onDelete,
}: {
  session: ChatSession
  isActive: boolean
  onClick: () => void
  onDelete: () => void
}) {
  const date = parseIso(session.lastMessageAt ?? session.createdAt)
  const dateStr = date ? date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—'
  const isExpired = session.expiredAt !== null

  return (
    <div
      role="button"
      tabIndex={0}
      className={cn(
        'group flex items-center gap-2 px-2 py-1.5 cursor-pointer transition-colors border-l-2',
        isActive
          ? 'border-accent bg-accent/10 text-accent'
          : 'border-transparent hover:bg-muted/50 text-muted-foreground hover:text-foreground',
        isExpired && 'opacity-60'
      )}
      onClick={onClick}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') onClick()
      }}
      data-testid={`chat-session-${session.id}`}
    >
      <MessageSquare className="h-3 w-3 shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="truncate text-[11px]">{session.title}</div>
        <div className="text-[9px] text-dim">
          {dateStr} · {session.messageCount} msgs{isExpired ? ' · sealed' : ''}
        </div>
      </div>
      <button
        onClick={e => {
          e.stopPropagation()
          onDelete()
        }}
        className="opacity-0 group-hover:opacity-100 p-1 hover:bg-crit/20 hover:text-crit transition-all"
        title="Delete session"
        aria-label="delete session"
      >
        <Trash2 className="h-3 w-3" />
      </button>
    </div>
  )
}

// ─── Main Component ─────────────────────────────────────────────────────────

export default function Chat() {
  const activeProjectId = useUI(s => s.activeProjectId)
  const queryClient = useQueryClient()

  const { data: projects = [] } = useProjects()
  const activeProject = projects.find(p => p.id === activeProjectId)

  const { data: sessions } = useChatSessions(activeProjectId)
  const createSession = useCreateChatSession()
  const deleteSession = useDeleteChatSession()
  const sendMessage = useSendChatMessage()
  const cancelStream = useCancelChatStream()

  const [activeSessionId, setActiveSessionId] = useState<number | null>(null)
  const [inputValue, setInputValue] = useState('')
  const [streamingOverlay, setStreamingOverlay] = useState<StreamingOverlay | null>(null)
  const appendChatMessageToCache = useAppendChatMessageToCache()

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const { data: persistedMessages, isLoading: isLoadingMessages } = useChatMessages(
    activeProjectId,
    activeSessionId
  )

  const isStreaming =
    streamingOverlay !== null &&
    (streamingOverlay.status === 'pending' || streamingOverlay.status === 'streaming')

  const activeSession = sessions.find(s => s.id === activeSessionId) ?? null
  const sessionExpired = activeSession?.expiredAt !== null && activeSession !== null

  useEffect(() => {
    if (sessions.length > 0 && activeSessionId === null) {
      setActiveSessionId(sessions[0].id)
    } else if (sessions.length === 0 && activeSessionId !== null) {
      setActiveSessionId(null)
    }
  }, [sessions, activeSessionId])

  useEffect(() => {
    setStreamingOverlay(null)
  }, [activeSessionId])

  const onStreamEvent = useCallback(
    (event: ChatStreamEvent) => {
      switch (event.type) {
        case 'stream_start':
          setStreamingOverlay(prev => (prev ? { ...prev, status: 'streaming' } : prev))
          break
        case 'token':
          setStreamingOverlay(prev =>
            prev ? { ...prev, assistantContent: prev.assistantContent + event.chunk } : prev
          )
          break
        case 'stream_end':
          if (activeProjectId !== null && activeSessionId !== null) {
            appendChatMessageToCache(activeProjectId, activeSessionId, {
              id: event.messageId,
              sessionId: activeSessionId,
              role: 'assistant',
              content: event.content,
              model: null,
              timestamp: new Date().toISOString(),
              citations: null,
            })
            queryClient.invalidateQueries({
              queryKey: ['chat', activeProjectId, 'sessions'],
            })
          }
          setStreamingOverlay(null)
          break
        case 'stream_cancelled':
          setStreamingOverlay(null)
          break
        case 'error':
          setStreamingOverlay(prev => (prev ? { ...prev, status: 'error' } : prev))
          break
      }
    },
    [activeProjectId, activeSessionId, queryClient, appendChatMessageToCache]
  )

  useChatStream(activeProjectId, activeSessionId, onStreamEvent, {
    enabled: streamingOverlay !== null,
  })

  const messages: ChatMessage[] = useMemo(() => {
    if (!streamingOverlay || activeSessionId === null) return persistedMessages
    return [
      ...persistedMessages,
      {
        id: -1,
        sessionId: activeSessionId,
        role: 'assistant',
        content: streamingOverlay.assistantContent,
        model: null,
        timestamp: streamingOverlay.assistantTimestamp,
        citations: null,
        isStreaming:
          streamingOverlay.status === 'pending' || streamingOverlay.status === 'streaming',
      },
    ]
  }, [persistedMessages, streamingOverlay, activeSessionId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleNewSession = useCallback(async () => {
    if (activeProjectId === null) return
    const session = await createSession
      .mutateAsync({ projectId: activeProjectId })
      .catch(() => null)
    if (session === null) return
    setActiveSessionId(session.id)
    inputRef.current?.focus()
  }, [activeProjectId, createSession])

  const handleDeleteSession = useCallback(
    async (sessionId: number) => {
      if (activeProjectId === null) return
      await deleteSession
        .mutateAsync({ projectId: activeProjectId, sessionId })
        .catch(() => undefined)
      if (activeSessionId === sessionId) {
        setActiveSessionId(null)
      }
    },
    [activeProjectId, activeSessionId, deleteSession]
  )

  const handleSend = useCallback(async () => {
    if (!inputValue.trim()) return
    if (activeProjectId === null || activeSessionId === null) return
    if (isStreaming) return

    const content = inputValue.trim()
    const now = new Date().toISOString()
    setInputValue('')

    const result = await sendMessage
      .mutateAsync({ projectId: activeProjectId, sessionId: activeSessionId, content })
      .catch(() => null)
    if (result === null) {
      setInputValue(content)
      return
    }

    appendChatMessageToCache(activeProjectId, activeSessionId, {
      id: result.userMessageId,
      sessionId: activeSessionId,
      role: 'user',
      content,
      model: null,
      timestamp: now,
      citations: null,
    })

    setStreamingOverlay({
      assistantContent: '',
      assistantTimestamp: new Date().toISOString(),
      status: 'pending',
    })
  }, [
    activeProjectId,
    activeSessionId,
    inputValue,
    isStreaming,
    sendMessage,
    appendChatMessageToCache,
  ])

  const handleCancel = useCallback(() => {
    if (activeProjectId === null || activeSessionId === null) return
    cancelStream.mutate({ projectId: activeProjectId, sessionId: activeSessionId })
  }, [activeProjectId, activeSessionId, cancelStream])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  if (activeProjectId === null) {
    return <NoProjectSelectedState projects={projects} />
  }

  const hasNoSessions = sessions.length === 0
  const hasNoMessages = messages.length === 0
  const projectLabel = activeProject?.code ?? '-'

  const inputDisabled = isStreaming || sessionExpired || activeSessionId === null

  return (
    <div className="h-full flex flex-col">
      <div className="shrink-0 px-6 py-4 border-b border-border">
        <h1 className="text-sm font-bold text-foreground tracking-wide">
          [CHAT] <span className="text-primary tty-glow">{projectLabel}</span>
        </h1>
        <p className="text-[11px] text-muted-foreground mt-0.5">
          RAG-powered assistant for security findings analysis
        </p>
      </div>

      <div className="flex-1 flex min-h-0 overflow-hidden">
        <div className="w-56 shrink-0 border-r border-border flex flex-col">
          <div className="p-2 border-b border-border">
            <button
              onClick={handleNewSession}
              disabled={createSession.isPending || activeProjectId === null}
              className={cn(
                'w-full flex items-center justify-center gap-2 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider border transition-colors',
                createSession.isPending || activeProjectId === null
                  ? 'opacity-50 cursor-not-allowed border-muted text-muted-foreground'
                  : 'border-accent text-accent hover:bg-accent/10'
              )}
            >
              {createSession.isPending ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Plus className="h-3 w-3" />
              )}
              New Chat
            </button>
          </div>

          <div className="flex-1 overflow-y-auto py-2">
            {hasNoSessions ? (
              <div className="px-3 py-4 text-center text-[11px] text-muted-foreground">
                No conversations yet.
                <br />
                Start a new chat to begin.
              </div>
            ) : (
              sessions.map(session => (
                <SessionItem
                  key={session.id}
                  session={session}
                  isActive={session.id === activeSessionId}
                  onClick={() => setActiveSessionId(session.id)}
                  onDelete={() => handleDeleteSession(session.id)}
                />
              ))
            )}
          </div>
        </div>

        <div className="flex-1 flex flex-col min-w-0">
          {activeSessionId === null ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <MessageSquare className="h-12 w-12 mx-auto text-muted-foreground/30" />
                <p className="mt-4 text-sm text-muted-foreground">
                  Select a conversation or start a new one
                </p>
              </div>
            </div>
          ) : (
            <>
              <div className="flex-1 p-4 overflow-hidden">
                <div className="relative h-full border-2 border-primary/30 bg-background flex flex-col">
                  <div className="absolute -top-px -left-px w-4 h-4 border-t-2 border-l-2 border-accent pointer-events-none" />
                  <div className="absolute -top-px -right-px w-4 h-4 border-t-2 border-r-2 border-accent pointer-events-none" />
                  <div className="absolute -bottom-px -left-px w-4 h-4 border-b-2 border-l-2 border-accent pointer-events-none" />
                  <div className="absolute -bottom-px -right-px w-4 h-4 border-b-2 border-r-2 border-accent pointer-events-none" />

                  <div className="shrink-0 px-4 py-1.5 bg-muted/50 border-b border-border flex items-center justify-between">
                    <div className="flex items-center gap-2 text-[10px]">
                      <span className="text-dim">SESSION:</span>
                      <span className="text-muted-foreground font-mono">{activeSessionId}</span>
                      {sessionExpired && (
                        <span
                          className="flex items-center gap-1 px-1.5 py-0.5 bg-warn/30 border border-warn text-warn font-bold uppercase tracking-wider"
                          data-testid="sealed-badge"
                        >
                          <Lock className="h-3 w-3" />
                          Sealed
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {isStreaming ? (
                        <span className="flex items-center gap-1 text-[10px] text-warn">
                          <Loader2 className="h-2.5 w-2.5 animate-spin" />
                          STREAMING
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-[10px] text-accent">
                          <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
                          CONNECTED
                        </span>
                      )}
                    </div>
                  </div>

                  {sessionExpired && (
                    <div
                      className="shrink-0 px-4 py-3 bg-warn/10 border-b border-warn/40 flex items-start gap-3"
                      data-testid="sealed-banner"
                    >
                      <Lock className="h-4 w-4 text-warn shrink-0 mt-0.5" />
                      <div className="flex-1 text-[11px]">
                        <div className="text-warn font-bold uppercase tracking-wider">
                          Session sealed
                        </div>
                        <div className="text-muted-foreground mt-1 leading-relaxed">
                          A scan ran since this chat started, so the findings it references may have
                          changed. Start a new chat to continue your investigation.
                        </div>
                      </div>
                      <button
                        onClick={handleNewSession}
                        disabled={createSession.isPending || activeProjectId === null}
                        className="shrink-0 px-3 py-1 border border-accent text-accent hover:bg-accent/10 text-[10px] uppercase tracking-wider font-bold disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        New Chat
                      </button>
                    </div>
                  )}

                  <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4">
                    {isLoadingMessages ? (
                      <div className="flex items-center justify-center h-full">
                        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                      </div>
                    ) : hasNoMessages ? (
                      <div className="flex items-center justify-center h-full text-center">
                        <div className="text-muted-foreground text-[11px]">
                          <div className="text-dim mb-2">{'// no messages yet'}</div>
                          Ask a question about your security findings
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-col gap-4">
                        {messages.map((message, idx) => (
                          <MessageBubble
                            key={`${message.id}-${idx}`}
                            message={message}
                            isLast={idx === messages.length - 1}
                          />
                        ))}
                        <div ref={messagesEndRef} />
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="shrink-0 p-4 pt-0">
                {sessionExpired ? (
                  <div
                    className="flex items-center gap-3 border-2 border-warn/60 bg-warn/10 px-4 py-3"
                    data-testid="sealed-input-panel"
                  >
                    <Lock className="h-5 w-5 text-warn shrink-0" />
                    <div className="flex-1 text-[11px]">
                      <div className="text-warn font-bold uppercase tracking-wider">
                        Read-only — session sealed
                      </div>
                      <div className="text-muted-foreground mt-0.5">
                        Start a new chat to continue your investigation.
                      </div>
                    </div>
                    <button
                      onClick={handleNewSession}
                      disabled={createSession.isPending || activeProjectId === null}
                      className="shrink-0 px-3 py-1.5 bg-accent/20 border border-accent text-accent hover:bg-accent/30 text-[10px] uppercase tracking-wider font-bold disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Start New Chat
                    </button>
                  </div>
                ) : (
                  <>
                    <div className="flex items-end gap-2 border border-border bg-muted/30 p-2">
                      <span className="text-accent text-sm font-bold pb-1.5">&gt;</span>
                      <textarea
                        ref={inputRef}
                        value={inputValue}
                        onChange={e => setInputValue(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="Ask about your security findings..."
                        disabled={inputDisabled}
                        rows={1}
                        className={cn(
                          'flex-1 bg-transparent text-foreground text-[12px] placeholder:text-muted-foreground resize-none outline-none',
                          'min-h-[24px] max-h-[120px]',
                          inputDisabled && 'opacity-50'
                        )}
                        style={{ height: 'auto' }}
                        onInput={e => {
                          const target = e.target as HTMLTextAreaElement
                          target.style.height = 'auto'
                          target.style.height = `${Math.min(target.scrollHeight, 120)}px`
                        }}
                      />
                      {isStreaming ? (
                        <button
                          onClick={handleCancel}
                          className="shrink-0 p-2 bg-crit/20 border border-crit text-crit hover:bg-crit/30 transition-colors"
                          title="Stop generation"
                          aria-label="cancel stream"
                        >
                          <Square className="h-4 w-4" />
                        </button>
                      ) : (
                        <button
                          onClick={handleSend}
                          disabled={!inputValue.trim() || inputDisabled}
                          className={cn(
                            'shrink-0 p-2 border transition-colors',
                            inputValue.trim() && !inputDisabled
                              ? 'bg-accent/20 border-accent text-accent hover:bg-accent/30'
                              : 'bg-muted border-border text-muted-foreground cursor-not-allowed'
                          )}
                          title="Send message"
                          aria-label="send message"
                        >
                          <Send className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                    <div className="mt-1 text-[9px] text-muted-foreground">
                      Press Enter to send, Shift+Enter for new line
                    </div>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      <ChatMutationErrorModal />
    </div>
  )
}
