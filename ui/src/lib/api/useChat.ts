/**
 * Chat Hooks
 * ==========
 * Hooks for RAG-powered LLM chat functionality.
 *
 * BACKEND ENDPOINTS NEEDED:
 * -------------------------
 * GET  /projects/:projectId/chat/sessions     - List chat sessions
 * POST /projects/:projectId/chat/sessions     - Create new session
 * GET  /chat/sessions/:sessionId/messages     - List messages in session
 * POST /chat/sessions/:sessionId/messages     - Send message (triggers SSE stream)
 * POST /chat/sessions/:sessionId/cancel       - Cancel in-progress response
 * DELETE /chat/sessions/:sessionId            - Delete session
 *
 * SSE /chat/stream?sessionId=<id>             - Stream response tokens
 *
 * SSE EVENT FORMAT:
 * -----------------
 * event: stream_start
 * data: {"sessionId": "...", "messageId": "..."}
 *
 * event: token
 * data: {"sessionId": "...", "messageId": "...", "token": "word "}
 *
 * event: stream_end
 * data: {"sessionId": "...", "messageId": "...", "content": "full response text"}
 *
 * event: error
 * data: {"sessionId": "...", "error": "Error message"}
 */

import { useState, useCallback, useRef } from 'react'
import type { ChatMessage, ChatSession } from '../types'

// ─── Mock Data ──────────────────────────────────────────────────────────────
// TODO [BACKEND]: Remove mock data once connected to real API.

const MOCK_SESSIONS: Record<string, ChatSession[]> = {
  '1': [
    {
      id: 'chat-001',
      projectId: '1',
      title: 'SQL Injection remediation',
      createdAt: '2025-03-15T10:00:00Z',
      lastMessageAt: '2025-03-15T10:15:00Z',
      messageCount: 6,
    },
    {
      id: 'chat-002',
      projectId: '1',
      title: 'Understanding XSS findings',
      createdAt: '2025-03-14T14:00:00Z',
      lastMessageAt: '2025-03-14T14:30:00Z',
      messageCount: 4,
    },
  ],
  '2': [
    {
      id: 'chat-003',
      projectId: '2',
      title: 'Dependency vulnerabilities',
      createdAt: '2025-03-13T09:00:00Z',
      lastMessageAt: '2025-03-13T09:20:00Z',
      messageCount: 3,
    },
  ],
  '3': [],
}

const MOCK_MESSAGES: Record<string, ChatMessage[]> = {
  'chat-001': [
    {
      id: 'msg-001',
      sessionId: 'chat-001',
      role: 'user',
      content: 'Can you explain the SQL injection vulnerability in TAL-001?',
      timestamp: '2025-03-15T10:00:00Z',
    },
    {
      id: 'msg-002',
      sessionId: 'chat-001',
      role: 'assistant',
      content:
        'Based on the finding TAL-001, there\'s a SQL injection vulnerability in the user authentication module. The issue occurs in `auth/login.py` at line 42 where user input is concatenated directly into the SQL query without proper parameterization.\n\n**Vulnerable code:**\n```python\nquery = f"SELECT * FROM users WHERE username = \'{username}\'"\n```\n\n**Recommended fix:**\n```python\nquery = "SELECT * FROM users WHERE username = ?"\ncursor.execute(query, (username,))\n```\n\nThis vulnerability allows attackers to bypass authentication or extract sensitive data from the database.',
      timestamp: '2025-03-15T10:00:30Z',
    },
    {
      id: 'msg-003',
      sessionId: 'chat-001',
      role: 'user',
      content: "What's the CVSS score for this type of vulnerability?",
      timestamp: '2025-03-15T10:05:00Z',
    },
    {
      id: 'msg-004',
      sessionId: 'chat-001',
      role: 'assistant',
      content:
        'SQL injection vulnerabilities in authentication flows are typically rated as **Critical** with a CVSS 3.1 score of **9.8**.\n\nThe scoring breakdown:\n- **Attack Vector (AV):** Network - exploitable remotely\n- **Attack Complexity (AC):** Low - no special conditions needed\n- **Privileges Required (PR):** None - attacker needs no privileges\n- **User Interaction (UI):** None - no user action required\n- **Scope (S):** Unchanged\n- **Confidentiality (C):** High - full database access possible\n- **Integrity (I):** High - can modify/delete data\n- **Availability (A):** High - can disrupt service\n\nGiven the authentication context, this should be prioritized for immediate remediation.',
      timestamp: '2025-03-15T10:05:45Z',
    },
  ],
  'chat-002': [
    {
      id: 'msg-005',
      sessionId: 'chat-002',
      role: 'user',
      content: 'How many XSS findings do we have?',
      timestamp: '2025-03-14T14:00:00Z',
    },
    {
      id: 'msg-006',
      sessionId: 'chat-002',
      role: 'assistant',
      content:
        'Based on my analysis of the ACME Platform findings, you currently have **7 XSS (Cross-Site Scripting) vulnerabilities**:\n\n- **2 Critical** - Stored XSS in user profile and comment sections\n- **3 High** - Reflected XSS in search and URL parameters\n- **2 Medium** - DOM-based XSS with limited exploitation vectors\n\nThe stored XSS findings are the highest priority as they can affect all users who view the compromised content. Would you like me to provide specific remediation guidance for any of these?',
      timestamp: '2025-03-14T14:00:30Z',
    },
  ],
  'chat-003': [],
}

// Mock response phrases for simulating streaming
const MOCK_RESPONSES = [
  'Based on my analysis of the project findings, ',
  'I can see that there are several key areas to address. ',
  'The most critical issue relates to input validation in the authentication module. ',
  'I recommend implementing parameterized queries and output encoding as immediate fixes. ',
  'Would you like me to provide more specific guidance on any particular finding?',
]

// ─── useChatSessions ────────────────────────────────────────────────────────

/**
 * Fetch chat sessions for a project.
 *
 * TODO [BACKEND]: Replace mock with:
 *   const res = await fetch(REST_ENDPOINTS.chatSessions(projectId))
 *   const sessions = await res.json()
 *   return sessions
 */
export function useChatSessions(projectId: string | null) {
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetch = useCallback(async () => {
    if (!projectId) return

    setIsLoading(true)
    setError(null)

    // ┌────────────────────────────────────────────────────────────────────────┐
    // │ TODO [BACKEND]: Uncomment this fetch code.                            │
    // │                                                                        │
    // │ const res = await fetch(REST_ENDPOINTS.chatSessions(projectId))       │
    // │ if (!res.ok) throw new Error(`Failed to fetch sessions: ${res.status}`)│
    // │ const data = await res.json()                                          │
    // │ setSessions(data)                                                      │
    // └────────────────────────────────────────────────────────────────────────┘

    // Mock: return mock sessions after delay
    await new Promise(r => setTimeout(r, 300))
    setSessions(MOCK_SESSIONS[projectId] ?? [])
    setIsLoading(false)
  }, [projectId])

  return { sessions, isLoading, error, refetch: fetch, setSessions }
}

// ─── useChatMessages ────────────────────────────────────────────────────────

/**
 * Fetch messages for a chat session.
 *
 * TODO [BACKEND]: Replace mock with:
 *   const res = await fetch(REST_ENDPOINTS.chatMessages(sessionId))
 *   const messages = await res.json()
 *   return messages
 */
export function useChatMessages(sessionId: string | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetch = useCallback(async () => {
    if (!sessionId) {
      setMessages([])
      return
    }

    setIsLoading(true)
    setError(null)

    // ┌────────────────────────────────────────────────────────────────────────┐
    // │ TODO [BACKEND]: Uncomment this fetch code.                            │
    // │                                                                        │
    // │ const res = await fetch(REST_ENDPOINTS.chatMessages(sessionId))       │
    // │ if (!res.ok) throw new Error(`Failed to fetch messages: ${res.status}`)│
    // │ const data = await res.json()                                          │
    // │ setMessages(data)                                                      │
    // └────────────────────────────────────────────────────────────────────────┘

    // Mock: return mock messages after delay
    await new Promise(r => setTimeout(r, 200))
    setMessages(MOCK_MESSAGES[sessionId] ?? [])
    setIsLoading(false)
  }, [sessionId])

  return { messages, isLoading, error, refetch: fetch, setMessages }
}

// ─── useCreateSession ───────────────────────────────────────────────────────

/**
 * Create a new chat session.
 *
 * TODO [BACKEND]: Replace mock with:
 *   const res = await fetch(REST_ENDPOINTS.createChatSession(projectId), {
 *     method: "POST",
 *     headers: { "Content-Type": "application/json" },
 *     body: JSON.stringify({ title }),
 *   })
 *   return await res.json()
 */
export function useCreateSession() {
  const [isLoading, setIsLoading] = useState(false)

  const create = useCallback(async (projectId: string, title?: string): Promise<ChatSession> => {
    setIsLoading(true)

    // ┌────────────────────────────────────────────────────────────────────────┐
    // │ TODO [BACKEND]: Uncomment this fetch code.                            │
    // │                                                                        │
    // │ const res = await fetch(REST_ENDPOINTS.createChatSession(projectId), {│
    // │   method: "POST",                                                      │
    // │   headers: { "Content-Type": "application/json" },                     │
    // │   body: JSON.stringify({ title }),                                     │
    // │ })                                                                     │
    // │ if (!res.ok) throw new Error(`Failed to create session: ${res.status}`)│
    // │ return await res.json()                                                │
    // └────────────────────────────────────────────────────────────────────────┘

    // Mock: create a new session
    await new Promise(r => setTimeout(r, 300))
    const session: ChatSession = {
      id: `chat-${Date.now()}`,
      projectId,
      title: title ?? 'New conversation',
      createdAt: new Date().toISOString(),
      messageCount: 0,
    }
    setIsLoading(false)
    return session
  }, [])

  return { create, isLoading }
}

// ─── useSendMessage ─────────────────────────────────────────────────────────

/**
 * Send a message and receive streaming response via SSE.
 *
 * TODO [BACKEND]: Replace mock with:
 *   1. POST to REST_ENDPOINTS.sendChatMessage(sessionId) with { content }
 *   2. Connect to SSE_ENDPOINTS.chatStream?sessionId=<id>&messageId=<id>
 *   3. Process stream_start, token, stream_end, error events
 */
export function useSendMessage() {
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<(() => void) | null>(null)

  const send = useCallback(
    async (
      sessionId: string,
      content: string,
      onToken: (token: string) => void,
      onComplete: (fullContent: string) => void,
      _onError: (error: string) => void
    ): Promise<string> => {
      setIsStreaming(true)
      setError(null)

      // ┌────────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Uncomment this SSE streaming code.                    │
      // │                                                                        │
      // │ // First, POST the message                                             │
      // │ const res = await fetch(REST_ENDPOINTS.sendChatMessage(sessionId), {  │
      // │   method: "POST",                                                      │
      // │   headers: { "Content-Type": "application/json" },                     │
      // │   body: JSON.stringify({ content }),                                   │
      // │ })                                                                     │
      // │ if (!res.ok) {                                                         │
      // │   const err = `Failed to send message: ${res.status}`                  │
      // │   setError(err)                                                        │
      // │   onError(err)                                                         │
      // │   setIsStreaming(false)                                                │
      // │   throw new Error(err)                                                 │
      // │ }                                                                      │
      // │ const { messageId } = await res.json()                                 │
      // │                                                                        │
      // │ // Then connect to SSE for streaming response                          │
      // │ const eventSource = new EventSource(                                   │
      // │   `${SSE_ENDPOINTS.chatStream}?sessionId=${sessionId}&messageId=${messageId}`│
      // │ )                                                                      │
      // │                                                                        │
      // │ abortRef.current = () => eventSource.close()                           │
      // │                                                                        │
      // │ eventSource.addEventListener("token", (e) => {                         │
      // │   const data: ChatStreamEvent = JSON.parse(e.data)                     │
      // │   if (data.token) onToken(data.token)                                  │
      // │ })                                                                     │
      // │                                                                        │
      // │ eventSource.addEventListener("stream_end", (e) => {                    │
      // │   const data: ChatStreamEvent = JSON.parse(e.data)                     │
      // │   eventSource.close()                                                  │
      // │   setIsStreaming(false)                                                │
      // │   if (data.content) onComplete(data.content)                           │
      // │ })                                                                     │
      // │                                                                        │
      // │ eventSource.addEventListener("error", (e) => {                         │
      // │   const data: ChatStreamEvent = JSON.parse(e.data)                     │
      // │   eventSource.close()                                                  │
      // │   setIsStreaming(false)                                                │
      // │   setError(data.error ?? "Unknown error")                              │
      // │   onError(data.error ?? "Unknown error")                               │
      // │ })                                                                     │
      // │                                                                        │
      // │ return messageId                                                       │
      // └────────────────────────────────────────────────────────────────────────┘

      // Mock: simulate streaming response word by word
      const messageId = `msg-${Date.now()}`
      const fullResponse = MOCK_RESPONSES.join('')
      const words = fullResponse.split(' ')
      let accumulated = ''

      abortRef.current = () => {
        setIsStreaming(false)
      }

      for (let i = 0; i < words.length; i++) {
        if (!abortRef.current) break // Check if cancelled
        await new Promise(r => setTimeout(r, 50 + Math.random() * 100))
        const token = words[i] + (i < words.length - 1 ? ' ' : '')
        accumulated += token
        onToken(token)
      }

      setIsStreaming(false)
      onComplete(accumulated)
      return messageId
    },
    []
  )

  const cancel = useCallback(async (_sessionId: string) => {
    // ┌────────────────────────────────────────────────────────────────────────┐
    // │ TODO [BACKEND]: Uncomment this cancel request.                        │
    // │                                                                        │
    // │ await fetch(REST_ENDPOINTS.cancelChatResponse(sessionId), {           │
    // │   method: "POST",                                                      │
    // │ })                                                                     │
    // └────────────────────────────────────────────────────────────────────────┘

    if (abortRef.current) {
      abortRef.current()
      abortRef.current = null
    }
    setIsStreaming(false)
  }, [])

  return { send, cancel, isStreaming, error }
}

// ─── useDeleteSession ───────────────────────────────────────────────────────

/**
 * Delete a chat session.
 *
 * TODO [BACKEND]: Replace mock with:
 *   await fetch(REST_ENDPOINTS.deleteChatSession(sessionId), { method: "DELETE" })
 */
export function useDeleteSession() {
  const [isLoading, setIsLoading] = useState(false)

  const deleteSession = useCallback(async (_sessionId: string): Promise<void> => {
    setIsLoading(true)

    // ┌────────────────────────────────────────────────────────────────────────┐
    // │ TODO [BACKEND]: Uncomment this delete request.                        │
    // │                                                                        │
    // │ const res = await fetch(REST_ENDPOINTS.deleteChatSession(sessionId), {│
    // │   method: "DELETE",                                                    │
    // │ })                                                                     │
    // │ if (!res.ok) throw new Error(`Failed to delete: ${res.status}`)       │
    // └────────────────────────────────────────────────────────────────────────┘

    // Mock: just delay
    await new Promise(r => setTimeout(r, 300))
    setIsLoading(false)
  }, [])

  return { deleteSession, isLoading }
}
