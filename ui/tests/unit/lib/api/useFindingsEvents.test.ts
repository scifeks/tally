import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useFindings } from '@/lib/api/useFindings'
import { useFindingsEvents } from '@/lib/api/useFindingsEvents'
import { __setEventSourceFactory } from '@/lib/api/sse'
import { MockEventSource } from '../../../helpers/sse'
import populatedFixture from '../../../fixtures/findings-populated.json'
import findingUpdatedFixture from '../../../fixtures/finding-updated.json'

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return {
    client,
    wrapper: ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client }, children),
  }
}

beforeEach(() => {
  MockEventSource.reset()
  __setEventSourceFactory(
    (url, init) => new MockEventSource(url, init) as unknown as EventSource
  )
})

afterEach(() => {
  __setEventSourceFactory(null)
})

describe('useFindingsEvents', () => {
  it('is a no-op when projectId is empty', () => {
    const { wrapper } = makeWrapper()
    renderHook(() => useFindingsEvents(''), { wrapper })
    expect(MockEventSource.instances).toHaveLength(0)
  })

  it('opens an EventSource for the project endpoint', () => {
    const { wrapper } = makeWrapper()
    renderHook(() => useFindingsEvents('1'), { wrapper })
    expect(MockEventSource.instances).toHaveLength(1)
    expect(MockEventSource.instances[0].url).toContain('/projects/1/findings/events')
  })

  it('patches the matching cached row when a finding_updated event arrives', async () => {
    const { client, wrapper } = makeWrapper()

    const list = renderHook(() => useFindings({ projectId: '1' }), { wrapper })
    await waitFor(() => expect(list.result.current.isSuccess).toBe(true))
    expect(list.result.current.data.find(f => f.id === 1001)?.status).toBe('active')

    renderHook(() => useFindingsEvents('1'), { wrapper })

    const es = MockEventSource.instances.at(-1)!
    act(() => {
      es.emitTyped('finding_updated', findingUpdatedFixture)
    })

    await waitFor(() =>
      expect(list.result.current.data.find(f => f.id === 1001)?.status).toBe('fixed')
    )
    void client
  })

  it('invalidates findingsCounts when severity or status differs', async () => {
    const { client, wrapper } = makeWrapper()

    const list = renderHook(() => useFindings({ projectId: '1' }), { wrapper })
    await waitFor(() => expect(list.result.current.isSuccess).toBe(true))

    const invalidate = vi.spyOn(client, 'invalidateQueries')

    renderHook(() => useFindingsEvents('1'), { wrapper })
    const es = MockEventSource.instances.at(-1)!
    act(() => {
      es.emitTyped('finding_updated', findingUpdatedFixture)
    })

    await waitFor(() => {
      const calls = invalidate.mock.calls.filter(call => {
        const filter = call[0] as { queryKey?: unknown[] } | undefined
        return Array.isArray(filter?.queryKey) && filter!.queryKey[0] === 'findingsCounts'
      })
      expect(calls.length).toBeGreaterThan(0)
    })
  })

  it('does not invalidate findingsCounts when severity and status match', async () => {
    const { client, wrapper } = makeWrapper()

    const list = renderHook(() => useFindings({ projectId: '1' }), { wrapper })
    await waitFor(() => expect(list.result.current.isSuccess).toBe(true))

    const invalidate = vi.spyOn(client, 'invalidateQueries')

    renderHook(() => useFindingsEvents('1'), { wrapper })
    const es = MockEventSource.instances.at(-1)!

    // Event keeps severity + status from the fixture row.
    const unchanged = {
      ...findingUpdatedFixture,
      severity: populatedFixture.items[0].severity,
      status: populatedFixture.items[0].status,
      notes: 'note only',
    }

    act(() => {
      es.emitTyped('finding_updated', unchanged)
    })

    await waitFor(() =>
      expect(list.result.current.data.find(f => f.id === 1001)?.notes).toBe('note only')
    )

    const countsCalls = invalidate.mock.calls.filter(call => {
      const filter = call[0] as { queryKey?: unknown[] } | undefined
      return Array.isArray(filter?.queryKey) && filter!.queryKey[0] === 'findingsCounts'
    })
    expect(countsCalls.length).toBe(0)
  })

  it('closes the EventSource on unmount', () => {
    const { wrapper } = makeWrapper()
    const hook = renderHook(() => useFindingsEvents('1'), { wrapper })
    const es = MockEventSource.instances.at(-1)!
    expect(es.closed).toBe(false)
    hook.unmount()
    expect(es.closed).toBe(true)
  })
})
