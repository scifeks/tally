import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { __setEventSourceFactory, apiEventSource } from '@/lib/api/sse'
import { MockEventSource } from '../../../helpers/sse'

beforeEach(() => {
  vi.useFakeTimers()
  MockEventSource.reset()
  __setEventSourceFactory(
    (url, init) => new MockEventSource(url, init) as unknown as EventSource,
  )
})

afterEach(() => {
  vi.useRealTimers()
  __setEventSourceFactory(null)
})

describe('apiEventSource', () => {
  it('registers a listener for each event type and routes parsed JSON', () => {
    const onEvent = vi.fn()
    apiEventSource('/api/v1/scans/events', {
      eventTypes: ['scan_started', 'scan_completed'],
      onEvent,
    })
    const [es] = MockEventSource.instances
    expect(es).toBeDefined()
    expect(es.init.withCredentials).toBe(true)

    es.emitTyped('scan_started', { runId: 'r1' })
    es.emitTyped('scan_completed', { runId: 'r1', findings: 4 })

    expect(onEvent).toHaveBeenNthCalledWith(1, 'scan_started', { runId: 'r1' })
    expect(onEvent).toHaveBeenNthCalledWith(2, 'scan_completed', { runId: 'r1', findings: 4 })
  })

  it('reconnects with exponential backoff on error', () => {
    apiEventSource('/api/v1/triage/events', {
      eventTypes: ['triage_started'],
      onEvent: vi.fn(),
      backoffMs: { min: 500, max: 30_000 },
    })
    const first = MockEventSource.instances[0]
    first.emitError()
    expect(MockEventSource.instances).toHaveLength(1)

    vi.advanceTimersByTime(500)
    expect(MockEventSource.instances).toHaveLength(2)

    MockEventSource.instances[1].emitError()
    vi.advanceTimersByTime(999)
    expect(MockEventSource.instances).toHaveLength(2) // not yet
    vi.advanceTimersByTime(1)
    expect(MockEventSource.instances).toHaveLength(3)
  })

  it('resets backoff to min after a successful open', () => {
    apiEventSource('/api/v1/scans/events', {
      eventTypes: ['scan_started'],
      onEvent: vi.fn(),
      backoffMs: { min: 500, max: 30_000 },
    })
    MockEventSource.instances[0].emitError()
    vi.advanceTimersByTime(500)
    MockEventSource.instances[1].emitOpen()
    MockEventSource.instances[1].emitError()
    // Without reset, this would wait 1000ms; with reset, only 500ms.
    vi.advanceTimersByTime(500)
    expect(MockEventSource.instances).toHaveLength(3)
  })

  it('caps backoff at max', () => {
    apiEventSource('/api/v1/scans/events', {
      eventTypes: ['scan_started'],
      onEvent: vi.fn(),
      backoffMs: { min: 1000, max: 4000 },
    })
    // 1000 → 2000 → 4000 → 4000 (capped)
    for (let i = 0; i < 4; i++) {
      MockEventSource.instances[i].emitError()
      vi.advanceTimersByTime(Math.min(1000 * 2 ** i, 4000))
    }
    MockEventSource.instances[4].emitError()
    vi.advanceTimersByTime(4000)
    expect(MockEventSource.instances).toHaveLength(6)
  })

  it('close() halts further reconnects', () => {
    const handle = apiEventSource('/api/v1/scans/events', {
      eventTypes: ['scan_started'],
      onEvent: vi.fn(),
      backoffMs: { min: 100, max: 1000 },
    })
    handle.close()
    MockEventSource.instances[0].emitError()
    vi.advanceTimersByTime(5000)
    expect(MockEventSource.instances).toHaveLength(1)
    expect(MockEventSource.instances[0].closed).toBe(true)
  })

  it('invokes onError callback on transport errors', () => {
    const onError = vi.fn()
    apiEventSource('/api/v1/scans/events', {
      eventTypes: ['scan_started'],
      onEvent: vi.fn(),
      onError,
      backoffMs: { min: 100, max: 1000 },
    })
    MockEventSource.instances[0].emitError()
    expect(onError).toHaveBeenCalledTimes(1)
  })
})
