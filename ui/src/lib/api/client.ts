/**
 * Every request carries `credentials: "include"` for the session cookie.
 * Mutating verbs echo the `tally_csrf` cookie as an `X-CSRF-Token` header
 * (double-submit CSRF). Non-2xx responses surface as typed `ApiError`
 * instances. On 401 the session-expired subscriber fires before the throw
 * so callers don't need to special-case authentication.
 */

import { readCookie } from './cookies'

const MUTATING = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

export class ApiError extends Error {
  readonly code: string
  readonly details: Record<string, unknown>
  readonly status: number

  constructor(code: string, message: string, details: Record<string, unknown>, status: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.details = details
    this.status = status
  }
}

export class MissingCsrfError extends Error {
  constructor() {
    super('CSRF cookie missing - session not initialized')
    this.name = 'MissingCsrfError'
  }
}

type SessionExpiredHandler = () => void

let sessionExpiredHandler: SessionExpiredHandler | null = null

/**
 * Register a callback invoked on the first 401 response. The SPA mounts a
 * full-screen blocking modal instructing the user to re-launch `tally ui`.
 *
 * Returns an unsubscribe function (used by tests; the production app
 * registers exactly once at startup).
 */
export function subscribeSessionExpired(cb: SessionExpiredHandler): () => void {
  sessionExpiredHandler = cb
  return () => {
    if (sessionExpiredHandler === cb) {
      sessionExpiredHandler = null
    }
  }
}

export type ApiResponseFormat = 'json' | 'blob' | 'text'

export type ApiFetchInit = Omit<RequestInit, 'body'> & {
  body?: unknown
  /**
   * How to decode a successful (2xx) response body. Defaults to `'json'`.
   * Set to `'blob'` for file downloads or `'text'` for raw markdown / plain
   * text. Error responses still use the canonical JSON envelope.
   */
  parseAs?: ApiResponseFormat
}

function isRawBody(body: unknown): body is BodyInit {
  return (
    body instanceof FormData ||
    body instanceof URLSearchParams ||
    body instanceof Blob ||
    body instanceof ArrayBuffer ||
    typeof body === 'string'
  )
}

function shouldParseBody(res: Response): boolean {
  if (res.status === 204) return false
  const len = res.headers.get('Content-Length')
  if (len === '0') return false
  return true
}

export async function apiFetch<T = unknown>(input: string, init: ApiFetchInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)

  let body: BodyInit | undefined
  if (init.body !== undefined && init.body !== null) {
    if (isRawBody(init.body)) {
      body = init.body
    } else {
      body = JSON.stringify(init.body)
      if (!headers.has('Content-Type')) {
        headers.set('Content-Type', 'application/json')
      }
    }
  }

  if (MUTATING.has(method)) {
    const csrf = readCookie('tally_csrf')
    if (!csrf) {
      throw new MissingCsrfError()
    }
    headers.set('X-CSRF-Token', csrf)
  }

  const res = await fetch(input, {
    ...init,
    method,
    headers,
    credentials: 'include',
    body,
  })

  if (res.ok) {
    if (!shouldParseBody(res)) {
      return undefined as T
    }
    const parseAs: ApiResponseFormat = init.parseAs ?? 'json'
    if (parseAs === 'blob') {
      const bytes = await res.arrayBuffer()
      return new Blob([bytes], { type: res.headers.get('Content-Type') ?? '' }) as T
    }
    if (parseAs === 'text') {
      return (await res.text()) as T
    }
    return (await res.json()) as T
  }

  if (res.status === 401 && sessionExpiredHandler) {
    sessionExpiredHandler()
  }

  let code = 'SERVER_ERROR'
  let message = res.statusText || 'Request failed'
  let details: Record<string, unknown> = {}

  const contentType = res.headers.get('Content-Type') ?? ''
  if (contentType.includes('application/json')) {
    try {
      const payload = (await res.json()) as {
        error?: { code?: string; message?: string; details?: Record<string, unknown> }
      }
      const env = payload.error
      if (env) {
        code = env.code ?? code
        message = env.message ?? message
        details = env.details ?? {}
      }
    } catch {
      // fall through with defaults
    }
  }

  throw new ApiError(code, message, details, res.status)
}
