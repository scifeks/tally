/**
 * Mock EventSource for unit tests. Captures registered listeners so a
 * test can synthesise `open`, named-typed events, and `error`.
 *
 * The real `EventSource` API surfaces named events through
 * `addEventListener(type, handler)` where the handler receives a
 * `MessageEvent` whose `.data` is always a string. We mirror that here.
 */

export class MockEventSource {
  static readonly instances: MockEventSource[] = []

  readonly url: string
  readonly init: EventSourceInit
  readonly listeners = new Map<string, Set<(e: Event) => void>>()
  closed = false

  constructor(url: string, init: EventSourceInit = {}) {
    this.url = url
    this.init = init
    MockEventSource.instances.push(this)
  }

  addEventListener(type: string, cb: (e: Event) => void): void {
    let set = this.listeners.get(type)
    if (!set) {
      set = new Set()
      this.listeners.set(type, set)
    }
    set.add(cb)
  }

  removeEventListener(type: string, cb: (e: Event) => void): void {
    this.listeners.get(type)?.delete(cb)
  }

  close(): void {
    this.closed = true
  }

  emitOpen(): void {
    this.fire('open', new Event('open'))
  }

  emitTyped(type: string, data: unknown): void {
    const ev = new MessageEvent(type, { data: JSON.stringify(data) })
    this.fire(type, ev)
  }

  emitError(): void {
    this.fire('error', new Event('error'))
  }

  private fire(type: string, ev: Event): void {
    const set = this.listeners.get(type)
    if (!set) return
    for (const cb of set) cb(ev)
  }

  static reset(): void {
    MockEventSource.instances.length = 0
  }
}
