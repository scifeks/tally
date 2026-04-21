import { useState, useEffect, useRef, useCallback } from "react"
import { Send, Square, Plus, Trash2, MessageSquare, AlertTriangle, X, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { useUI } from "@/lib/store"
import {
  useChatSessions,
  useChatMessages,
  useCreateSession,
  useSendMessage,
  useDeleteSession,
  useProjects,
} from "@/lib/api"
import type { ChatMessage, ChatSession } from "@/lib/types"
import { Panel } from "@/components/tty"
import { Modal, ModalButton } from "@/components/Modal"

// ─── Error Modal ────────────────────────────────────────────────────────────

function ErrorModal({
  open,
  message,
  onClose,
}: {
  open: boolean
  message: string
  onClose: () => void
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="connection error"
      tone="error"
      width="sm"
      footer={<ModalButton onClick={onClose}>dismiss</ModalButton>}
    >
      <div className="flex items-start gap-2">
        <AlertTriangle className="h-4 w-4 text-crit mt-0.5 shrink-0" />
        <div className="text-foreground leading-relaxed">
          <span className="text-crit font-bold">Failed to communicate with server.</span>
          <div className="mt-2 text-[11px] text-muted-foreground border border-border bg-muted/30 p-2">
            {message}
          </div>
        </div>
      </div>
    </Modal>
  )
}

// ─── Message Bubble ─────────────────────────────────────────────────────────

function MessageBubble({
  message,
  isLast,
}: {
  message: ChatMessage
  isLast?: boolean
}) {
  const isUser = message.role === "user"
  const time = new Date(message.timestamp).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })

  return (
    <div
      className={cn(
        "flex flex-col gap-1 max-w-[85%]",
        isUser ? "self-end items-end" : "self-start items-start"
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
        <span>{isUser ? "YOU" : "TALLY"}</span>
        <span className="text-dim">{time}</span>
      </div>

      {/* Content */}
      <div
        className={cn(
          "px-3 py-2 text-[12px] leading-relaxed whitespace-pre-wrap",
          isUser
            ? "bg-primary/20 border border-primary/40 text-primary"
            : "bg-muted/50 border border-border text-foreground"
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
  const date = new Date(session.lastMessageAt ?? session.createdAt)
  const dateStr = date.toLocaleDateString("en-US", { month: "short", day: "numeric" })

  return (
    <div
      className={cn(
        "group flex items-center gap-2 px-2 py-1.5 cursor-pointer transition-colors border-l-2",
        isActive
          ? "border-accent bg-accent/10 text-accent"
          : "border-transparent hover:bg-muted/50 text-muted-foreground hover:text-foreground"
      )}
      onClick={onClick}
    >
      <MessageSquare className="h-3 w-3 shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="truncate text-[11px]">{session.title ?? "Untitled"}</div>
        <div className="text-[9px] text-dim">{dateStr} · {session.messageCount} msgs</div>
      </div>
      <button
        onClick={(e) => {
          e.stopPropagation()
          onDelete()
        }}
        className="opacity-0 group-hover:opacity-100 p-1 hover:bg-crit/20 hover:text-crit transition-all"
        title="Delete session"
      >
        <Trash2 className="h-3 w-3" />
      </button>
    </div>
  )
}

// ─── Main Component ─────────────────────────────────────────────────────────

export default function Chat() {
  const activeProjectId = useUI((s) => s.activeProjectId)

  // TODO [BACKEND]: This hook returns mock data. Replace with real API call.
  // GET /api/v1/projects
  const { data: projects = [] } = useProjects()

  const activeProject = projects.find((p) => p.id === activeProjectId) ?? projects[0]

  // TODO [BACKEND]: These hooks manage chat sessions and messages via API.
  // See useChat.ts for endpoint documentation.
  const { sessions, refetch: refetchSessions, setSessions } = useChatSessions(activeProjectId)
  const { create: createSession, isLoading: isCreating } = useCreateSession()
  const { deleteSession } = useDeleteSession()
  const { send: sendMessage, cancel: cancelMessage, isStreaming } = useSendMessage()

  // Local state
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [inputValue, setInputValue] = useState("")
  const [isLoadingMessages, setIsLoadingMessages] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Load sessions on mount
  useEffect(() => {
    refetchSessions()
  }, [refetchSessions])

  // Auto-select first session or none
  useEffect(() => {
    if (sessions.length > 0 && !activeSessionId) {
      setActiveSessionId(sessions[0].id)
    } else if (sessions.length === 0) {
      setActiveSessionId(null)
    }
  }, [sessions, activeSessionId])

  // Load messages when session changes
  useEffect(() => {
    if (!activeSessionId) {
      setMessages([])
      return
    }

    setIsLoadingMessages(true)

    // ┌────────────────────────────────────────────────────────────────────────┐
    // │ TODO [BACKEND]: Replace with useChatMessages hook fetch               │
    // └────────────────────────────────────────────────────────────────────────┘

    // Mock: load from mock data
    const MOCK_MESSAGES: Record<string, ChatMessage[]> = {
      "chat-001": [
        {
          id: "msg-001",
          sessionId: "chat-001",
          role: "user",
          content: "Can you explain the SQL injection vulnerability in TAL-001?",
          timestamp: "2025-03-15T10:00:00Z",
        },
        {
          id: "msg-002",
          sessionId: "chat-001",
          role: "assistant",
          content: "Based on the finding TAL-001, there's a SQL injection vulnerability in the user authentication module. The issue occurs in `auth/login.py` at line 42 where user input is concatenated directly into the SQL query without proper parameterization.\n\n**Vulnerable code:**\n```python\nquery = f\"SELECT * FROM users WHERE username = '{username}'\"\n```\n\n**Recommended fix:**\n```python\nquery = \"SELECT * FROM users WHERE username = ?\"\ncursor.execute(query, (username,))\n```\n\nThis vulnerability allows attackers to bypass authentication or extract sensitive data from the database.",
          timestamp: "2025-03-15T10:00:30Z",
        },
      ],
      "chat-002": [
        {
          id: "msg-005",
          sessionId: "chat-002",
          role: "user",
          content: "How many XSS findings do we have?",
          timestamp: "2025-03-14T14:00:00Z",
        },
        {
          id: "msg-006",
          sessionId: "chat-002",
          role: "assistant",
          content: "Based on my analysis of the ACME Platform findings, you currently have **7 XSS (Cross-Site Scripting) vulnerabilities**:\n\n- **2 Critical** - Stored XSS in user profile and comment sections\n- **3 High** - Reflected XSS in search and URL parameters\n- **2 Medium** - DOM-based XSS with limited exploitation vectors",
          timestamp: "2025-03-14T14:00:30Z",
        },
      ],
    }

    setTimeout(() => {
      setMessages(MOCK_MESSAGES[activeSessionId] ?? [])
      setIsLoadingMessages(false)
    }, 200)
  }, [activeSessionId])

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  // Create new session
  const handleNewSession = useCallback(async () => {
    try {
      const session = await createSession(activeProjectId, "New conversation")
      setSessions((prev) => [session, ...prev])
      setActiveSessionId(session.id)
      setMessages([])
      inputRef.current?.focus()
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to create session")
    }
  }, [activeProjectId, createSession, setSessions])

  // Delete session
  const handleDeleteSession = useCallback(
    async (sessionId: string) => {
      try {
        await deleteSession(sessionId)
        setSessions((prev) => prev.filter((s) => s.id !== sessionId))
        if (activeSessionId === sessionId) {
          setActiveSessionId(null)
        }
      } catch (err) {
        setErrorMessage(err instanceof Error ? err.message : "Failed to delete session")
      }
    },
    [activeSessionId, deleteSession, setSessions]
  )

  // Send message
  const handleSend = useCallback(async () => {
    if (!inputValue.trim() || !activeSessionId || isStreaming) return

    const userMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      sessionId: activeSessionId,
      role: "user",
      content: inputValue.trim(),
      timestamp: new Date().toISOString(),
    }

    // Add user message immediately
    setMessages((prev) => [...prev, userMessage])
    setInputValue("")

    // Create placeholder for assistant response
    const assistantMessageId = `msg-${Date.now() + 1}`
    const assistantMessage: ChatMessage = {
      id: assistantMessageId,
      sessionId: activeSessionId,
      role: "assistant",
      content: "",
      timestamp: new Date().toISOString(),
      isStreaming: true,
    }
    setMessages((prev) => [...prev, assistantMessage])

    try {
      await sendMessage(
        activeSessionId,
        userMessage.content,
        // onToken
        (token) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMessageId
                ? { ...m, content: m.content + token }
                : m
            )
          )
        },
        // onComplete
        (fullContent) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMessageId
                ? { ...m, content: fullContent, isStreaming: false }
                : m
            )
          )
        },
        // onError
        (error) => {
          setErrorMessage(error)
          // Remove the failed assistant message
          setMessages((prev) => prev.filter((m) => m.id !== assistantMessageId))
        }
      )
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to send message")
      setMessages((prev) => prev.filter((m) => m.id !== assistantMessageId))
    }
  }, [activeSessionId, inputValue, isStreaming, sendMessage])

  // Cancel streaming
  const handleCancel = useCallback(() => {
    if (activeSessionId) {
      cancelMessage(activeSessionId)
      // Mark last message as not streaming
      setMessages((prev) =>
        prev.map((m, i) =>
          i === prev.length - 1 ? { ...m, isStreaming: false } : m
        )
      )
    }
  }, [activeSessionId, cancelMessage])

  // Handle enter key
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const hasNoSessions = sessions.length === 0
  const hasNoMessages = messages.length === 0

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="shrink-0 px-6 py-4 border-b border-border">
        <h1 className="text-sm font-bold text-foreground tracking-wide">
          [CHAT] <span className="text-primary tty-glow">{activeProject.code}</span>
        </h1>
        <p className="text-[11px] text-muted-foreground mt-0.5">
          RAG-powered assistant for security findings analysis
        </p>
      </div>

      {/* Main content */}
      <div className="flex-1 flex min-h-0 overflow-hidden">
        {/* Sidebar - Session list */}
        <div className="w-56 shrink-0 border-r border-border flex flex-col">
          <div className="p-2 border-b border-border">
            <button
              onClick={handleNewSession}
              disabled={isCreating}
              className={cn(
                "w-full flex items-center justify-center gap-2 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider border transition-colors",
                isCreating
                  ? "opacity-50 cursor-not-allowed border-muted text-muted-foreground"
                  : "border-accent text-accent hover:bg-accent/10"
              )}
            >
              {isCreating ? (
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
              sessions.map((session) => (
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

        {/* Chat area */}
        <div className="flex-1 flex flex-col min-w-0">
          {!activeSessionId ? (
            // No session selected
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
              {/* Messages area with CRT frame */}
              <div className="flex-1 p-4 overflow-hidden">
                <div className="relative h-full border-2 border-primary/30 bg-background">
                  {/* CRT corner brackets */}
                  <div className="absolute -top-px -left-px w-4 h-4 border-t-2 border-l-2 border-accent" />
                  <div className="absolute -top-px -right-px w-4 h-4 border-t-2 border-r-2 border-accent" />
                  <div className="absolute -bottom-px -left-px w-4 h-4 border-b-2 border-l-2 border-accent" />
                  <div className="absolute -bottom-px -right-px w-4 h-4 border-b-2 border-r-2 border-accent" />

                  {/* Session header */}
                  <div className="absolute top-0 left-0 right-0 px-4 py-1.5 bg-muted/50 border-b border-border flex items-center justify-between">
                    <div className="flex items-center gap-2 text-[10px]">
                      <span className="text-dim">SESSION:</span>
                      <span className="text-muted-foreground font-mono">{activeSessionId}</span>
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

                  {/* Messages */}
                  <div className="absolute top-8 bottom-0 left-0 right-0 overflow-y-auto px-4 py-4">
                    {isLoadingMessages ? (
                      <div className="flex items-center justify-center h-full">
                        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                      </div>
                    ) : hasNoMessages ? (
                      <div className="flex items-center justify-center h-full text-center">
                        <div className="text-muted-foreground text-[11px]">
                          <div className="text-dim mb-2">// no messages yet</div>
                          Ask a question about your security findings
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-col gap-4">
                        {messages.map((message, idx) => (
                          <MessageBubble
                            key={message.id}
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

              {/* Input area */}
              <div className="shrink-0 p-4 pt-0">
                <div className="flex items-end gap-2 border border-border bg-muted/30 p-2">
                  <span className="text-accent text-sm font-bold pb-1.5">&gt;</span>
                  <textarea
                    ref={inputRef}
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Ask about your security findings..."
                    disabled={isStreaming}
                    rows={1}
                    className={cn(
                      "flex-1 bg-transparent text-foreground text-[12px] placeholder:text-muted-foreground resize-none outline-none",
                      "min-h-[24px] max-h-[120px]",
                      isStreaming && "opacity-50"
                    )}
                    style={{ height: "auto" }}
                    onInput={(e) => {
                      const target = e.target as HTMLTextAreaElement
                      target.style.height = "auto"
                      target.style.height = `${Math.min(target.scrollHeight, 120)}px`
                    }}
                  />
                  {isStreaming ? (
                    <button
                      onClick={handleCancel}
                      className="shrink-0 p-2 bg-crit/20 border border-crit text-crit hover:bg-crit/30 transition-colors"
                      title="Stop generation"
                    >
                      <Square className="h-4 w-4" />
                    </button>
                  ) : (
                    <button
                      onClick={handleSend}
                      disabled={!inputValue.trim()}
                      className={cn(
                        "shrink-0 p-2 border transition-colors",
                        inputValue.trim()
                          ? "bg-accent/20 border-accent text-accent hover:bg-accent/30"
                          : "bg-muted border-border text-muted-foreground cursor-not-allowed"
                      )}
                      title="Send message"
                    >
                      <Send className="h-4 w-4" />
                    </button>
                  )}
                </div>
                <div className="mt-1 text-[9px] text-muted-foreground">
                  Press Enter to send, Shift+Enter for new line
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Error Modal */}
      <ErrorModal
        open={errorMessage !== null}
        message={errorMessage ?? ""}
        onClose={() => setErrorMessage(null)}
      />
    </div>
  )
}
