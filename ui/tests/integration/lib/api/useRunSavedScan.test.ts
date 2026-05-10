import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useRunSavedScan } from '@/lib/api/useSavedScans'
import { server } from '../../../handlers'
import { clearAllCookies, setCookie } from '../../../helpers/cookies'

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return {
    qc,
    wrapper: ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children),
  }
}

beforeEach(() => {
  clearAllCookies()
  setCookie('tally_csrf', 'test-csrf-token')
})

afterEach(() => server.resetHandlers())

describe('useRunSavedScan', () => {
  it('dispatches a clean run and returns a mapped Scan domain object', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useRunSavedScan(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ projectId: 1, savedScanId: 1 })
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const scan = result.current.data!
    expect(scan.id).toBe(2)
    expect(scan.projectId).toBe(2)
    expect(scan.status).toBe('queued')
    expect(scan.toolIds).toEqual(['gitleaks'])
  })

  it('invalidates the scans cache on success', async () => {
    const { qc, wrapper } = makeWrapper()
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    const { result } = renderHook(() => useRunSavedScan(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ projectId: 1, savedScanId: 1 })
    })

    expect(
      invalidate.mock.calls.some(call => {
        const filter = call[0] as { queryKey?: unknown[] } | undefined
        return (
          Array.isArray(filter?.queryKey) &&
          filter!.queryKey[0] === 'scans' &&
          filter!.queryKey[1] === 1
        )
      })
    ).toBe(true)
  })

  it('surfaces a 409 STALE_SAVED_SCAN with staleItems when the scan is stale', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useRunSavedScan(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ projectId: 1, savedScanId: 7 }).catch(() => null)
    })

    await waitFor(() => expect(result.current.isError).toBe(true))
    const err = result.current.error as { code?: string; status?: number; details?: unknown }
    expect(err.code).toBe('STALE_SAVED_SCAN')
    expect(err.status).toBe(409)
    const details = err.details as { staleItems?: { kind: string }[] }
    expect(details.staleItems).toHaveLength(3)
    expect(details.staleItems![0]).toMatchObject({ kind: 'repo', id: 2, name: 'php-goof' })
    expect(details.staleItems![1]).toMatchObject({ kind: 'tool', name: 'osv-scanner' })
    expect(details.staleItems![2]).toMatchObject({ kind: 'argProfile', id: 4 })
  })

  it('surfaces a 409 JOB_ALREADY_RUNNING when a scan is already in progress', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useRunSavedScan(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ projectId: 1, savedScanId: 8 }).catch(() => null)
    })

    await waitFor(() => expect(result.current.isError).toBe(true))
    const err = result.current.error as { code?: string; status?: number; details?: unknown }
    expect(err.code).toBe('JOB_ALREADY_RUNNING')
    expect(err.status).toBe(409)
    const details = err.details as { kind?: string; current_holder?: string }
    expect(details.kind).toBe('scan')
    expect(details.current_holder).toBe('run-12')
  })
})
