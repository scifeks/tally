/**
 * Browser EventSource wrapper with auto-reconnect + multi-event-type
 * dispatch. Tally streams every long-running operation (scans, triage,
 * report drafts, chat) over SSE, so the same factory backs all of them.
 *
 * `withCredentials: true` is required for the HttpOnly `tally_session`
 * cookie to travel with the SSE handshake.
 */

export interface ApiEventSourceOptions {
  readonly eventTypes: readonly string[]
  readonly onEvent: (type: string, data: unknown) => void
  readonly onError?: (err: Event) => void
  readonly backoffMs?: { min: number; max: number }
}

export interface ApiEventSourceHandle {
  close: () => void
}

const DEFAULT_BACKOFF = { min: 500, max: 30_000 }

type EventSourceFactory = (url: string, init: EventSourceInit) => EventSource

let factory: EventSourceFactory = (url, init) => new EventSource(url, init)

/**
 * Test-only seam for swapping in a fake EventSource. Production code never
 * calls this.
 */
export function __setEventSourceFactory(next: EventSourceFactory | null): void {
  factory = next ?? ((url, init) => new EventSource(url, init))
}

export function apiEventSource(url: string, options: ApiEventSourceOptions): ApiEventSourceHandle {
  const backoff = options.backoffMs ?? DEFAULT_BACKOFF
  let current: EventSource | null = null
  let timer: ReturnType<typeof setTimeout> | null = null
  let nextDelay = backoff.min
  let closed = false

  const open = (): void => {
    if (closed) return
    const es = factory(url, { withCredentials: true })
    current = es

    es.addEventListener('open', () => {
      nextDelay = backoff.min
    })

    for (const type of options.eventTypes) {
      es.addEventListener(type, (raw: Event) => {
        const me = raw as MessageEvent
        let parsed: unknown = me.data
        if (typeof me.data === 'string') {
          try {
            parsed = JSON.parse(me.data)
          } catch {
            parsed = me.data
          }
        }
        options.onEvent(type, parsed)
      })
    }

    es.addEventListener('error', (err: Event) => {
      options.onError?.(err)
      try {
        es.close()
      } catch {
        // ignore
      }
      if (closed) return
      const delay = nextDelay
      nextDelay = Math.min(nextDelay * 2, backoff.max)
      timer = setTimeout(open, delay)
    })
  }

  open()

  return {
    close: () => {
      closed = true
      if (timer) {
        clearTimeout(timer)
        timer = null
      }
      try {
        current?.close()
      } catch {
        // ignore
      }
      current = null
    },
  }
}
