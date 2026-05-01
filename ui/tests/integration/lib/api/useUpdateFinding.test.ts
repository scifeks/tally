import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useUpdateFinding } from '@/lib/api/useUpdateFinding'
import { useFindings, mapFinding } from '@/lib/api/useFindings'
import { useUI } from '@/lib/store'
import { server } from '../../../handlers'
import { setCookie, clearAllCookies } from '../../../helpers/cookies'
import populatedFixture from '../../../fixtures/findings/populated.json'
import findingUpdatedFixture from '../../../fixtures/findings/finding-updated.json'
import findingLockedFixture from '../../../fixtures/findings/finding-locked-error.json'

interface ProviderArgs {
  client: QueryClient
}

function makeWrapper({ client }: ProviderArgs) {
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children)
}

beforeEach(() => {
  clearAllCookies()
  setCookie('tally_csrf', 'test-csrf-token')
  useUI.setState({ findingMutationError: null })
})

afterEach(() => {
  server.resetHandlers()
})

describe('useUpdateFinding', () => {
  it('optimistically patches the cached finding before the network resolves', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const wrapper = makeWrapper({ client })

    // Seed cache by rendering useFindings.
    const list = renderHook(() => useFindings({ projectId: '1' }), { wrapper })
    await waitFor(() => expect(list.result.current.isSuccess).toBe(true))

    // Hold the PATCH response so we can observe the optimistic state.
    let release: () => void = () => undefined
    const releaseGate = new Promise<void>(resolve => {
      release = resolve
    })
    server.use(
      http.patch('/api/v1/projects/:projectId/findings/:findingId', async () => {
        await releaseGate
        return HttpResponse.json(findingUpdatedFixture)
      })
    )

    const mutHook = renderHook(() => useUpdateFinding(), { wrapper })
    act(() => {
      mutHook.result.current.mutate({
        projectId: '1',
        id: 1,
        patch: { status: 'fixed' },
      })
    })

    // Cache reflects optimistic patch even before network resolves.
    await waitFor(() => {
      const optimistic = list.result.current.data.find(f => f.id === 1)
      expect(optimistic?.status).toBe('fixed')
    })
    expect(mutHook.result.current.isPending).toBe(true)

    // Resolve the network and confirm canonical row replaces optimistic.
    release()
    await waitFor(() => expect(mutHook.result.current.isSuccess).toBe(true))
    const canonical = list.result.current.data.find(f => f.id === 1)
    expect(canonical).toEqual(mapFinding(findingUpdatedFixture as never))
  })

  it('invalidates findingsCounts when severity or status changed', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const wrapper = makeWrapper({ client })

    const list = renderHook(() => useFindings({ projectId: '1' }), { wrapper })
    await waitFor(() => expect(list.result.current.isSuccess).toBe(true))

    const invalidate = vi.spyOn(client, 'invalidateQueries')

    const mutHook = renderHook(() => useUpdateFinding(), { wrapper })
    await act(async () => {
      await mutHook.result.current.mutateAsync({
        projectId: '1',
        id: 1, // false_positive in fixture, fixed in finding-updated → status changed
        patch: { status: 'fixed' },
      })
    })

    expect(
      invalidate.mock.calls.some(call => {
        const filter = call[0] as { queryKey?: unknown[] } | undefined
        return Array.isArray(filter?.queryKey) && filter!.queryKey[0] === 'findingsCounts'
      })
    ).toBe(true)
  })

  it('does not invalidate findingsCounts when neither severity nor status changed', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const wrapper = makeWrapper({ client })

    const list = renderHook(() => useFindings({ projectId: '1' }), { wrapper })
    await waitFor(() => expect(list.result.current.isSuccess).toBe(true))

    // Server response keeps severity/status identical to fixture row.
    server.use(
      http.patch('/api/v1/projects/:projectId/findings/:findingId', () =>
        HttpResponse.json({
          ...findingUpdatedFixture,
          severity: populatedFixture.items[0].severity,
          status: populatedFixture.items[0].status,
          notes: 'Updated note only',
        })
      )
    )

    const invalidate = vi.spyOn(client, 'invalidateQueries')

    const mutHook = renderHook(() => useUpdateFinding(), { wrapper })
    await act(async () => {
      await mutHook.result.current.mutateAsync({
        projectId: '1',
        id: 1,
        patch: { notes: 'Updated note only' },
      })
    })

    const countsCalls = invalidate.mock.calls.filter(call => {
      const filter = call[0] as { queryKey?: unknown[] } | undefined
      return Array.isArray(filter?.queryKey) && filter!.queryKey[0] === 'findingsCounts'
    })
    expect(countsCalls.length).toBe(0)
  })

  it('rolls back the cache and populates findingMutationError on 409 FINDING_LOCKED', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const wrapper = makeWrapper({ client })

    const list = renderHook(() => useFindings({ projectId: '1' }), { wrapper })
    await waitFor(() => expect(list.result.current.isSuccess).toBe(true))
    const beforePatch = list.result.current.data.find(f => f.id === 3)
    expect(beforePatch?.status).toBe('wont_fix')

    server.use(
      http.patch('/api/v1/projects/:projectId/findings/:findingId', () =>
        HttpResponse.json(findingLockedFixture, { status: 409 })
      )
    )

    const mutHook = renderHook(() => useUpdateFinding(), { wrapper })
    await act(async () => {
      try {
        await mutHook.result.current.mutateAsync({
          projectId: '1',
          id: 3,
          patch: { status: 'fixed' },
        })
      } catch {
        /* expected */
      }
    })

    await waitFor(() => expect(mutHook.result.current.isError).toBe(true))

    const restored = list.result.current.data.find(f => f.id === 3)
    expect(restored?.status).toBe('wont_fix')

    const err = useUI.getState().findingMutationError
    expect(err?.code).toBe('FINDING_LOCKED')
    expect(err?.message).toContain('Finding 3')
  })

  it('rolls back and reports a generic 500 error', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const wrapper = makeWrapper({ client })

    const list = renderHook(() => useFindings({ projectId: '1' }), { wrapper })
    await waitFor(() => expect(list.result.current.isSuccess).toBe(true))
    const original = list.result.current.data.find(f => f.id === 1)?.status

    server.use(
      http.patch('/api/v1/projects/:projectId/findings/:findingId', () =>
        HttpResponse.json(
          { error: { code: 'SERVER_ERROR', message: 'boom', details: {} } },
          { status: 500 }
        )
      )
    )

    const mutHook = renderHook(() => useUpdateFinding(), { wrapper })
    await act(async () => {
      try {
        await mutHook.result.current.mutateAsync({
          projectId: '1',
          id: 1,
          patch: { status: 'fixed' },
        })
      } catch {
        /* expected */
      }
    })

    await waitFor(() => expect(mutHook.result.current.isError).toBe(true))
    expect(list.result.current.data.find(f => f.id === 1)?.status).toBe(original)
    expect(useUI.getState().findingMutationError?.code).toBe('SERVER_ERROR')
  })
})
