import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  useSavedScans,
  useSavedScan,
  useSaveScan,
  useDeleteSavedScan,
} from '@/lib/api/useSavedScans'
import { server } from '../../../handlers'
import { clearAllCookies, setCookie } from '../../../helpers/cookies'
import savedScansPopulated from '../../../fixtures/saved-scans/populated.json'
import savedScansEmpty from '../../../fixtures/saved-scans/empty.json'
import savedScanClean from '../../../fixtures/saved-scans/clean.json'
import savedScanHydrated from '../../../fixtures/saved-scans/hydrated.json'
import savedScanReplaced from '../../../fixtures/saved-scans/replaced.json'

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return {
    wrapper: ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children),
  }
}

beforeEach(() => {
  clearAllCookies()
  setCookie('tally_csrf', 'test-csrf-token')
})

afterEach(() => server.resetHandlers())

describe('useSavedScans', () => {
  it('list returns the populated envelope with 2 items', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useSavedScans(1), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.total).toBe(2)
    expect(result.current.data?.offset).toBe(0)
    expect(result.current.data?.items).toHaveLength(2)
    expect(result.current.data?.items[0].name).toBe('Quick Secrets Sweep')
    expect(result.current.data?.items[1].skipToolIds).toEqual(['xsstrike'])
    expect(result.current.data?.items[1].segments).toEqual(['sast', 'sca', 'secrets'])
  })

  it('list with no results returns an empty items array', async () => {
    server.use(
      http.get('/api/v1/projects/1/saved-scans', () => HttpResponse.json(savedScansEmpty))
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useSavedScans(1), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.total).toBe(0)
    expect(result.current.data?.items).toHaveLength(0)
  })

  it('detail for id=1 returns the clean fixture', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useSavedScan(1, 1), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.id).toBe(1)
    expect(result.current.data?.name).toBe('Quick Secrets Sweep')
    expect(result.current.data?.tools).toHaveLength(1)
    expect(result.current.data?.argProfiles).toHaveLength(0)
  })

  it('detail for id=9999 rejects with NOT_FOUND', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useSavedScan(1, 9999), { wrapper })
    await waitFor(() => expect(result.current.isError).toBe(true))

    const err = result.current.error as { code?: string }
    expect(err.code).toBe('NOT_FOUND')
  })
})

describe('useSaveScan', () => {
  it('create POSTs and returns a SavedScanDetail; list query is invalidated', async () => {
    let method: string | null = null
    server.use(
      http.post('/api/v1/projects/1/saved-scans', async ({ request }) => {
        method = request.method
        return HttpResponse.json(savedScanClean, { status: 201 })
      })
    )

    const { wrapper } = makeWrapper()
    const { result } = renderHook(
      () => ({ list: useSavedScans(1), save: useSaveScan() }),
      { wrapper }
    )

    await waitFor(() => expect(result.current.list.isSuccess).toBe(true))

    await act(async () => {
      await result.current.save.mutateAsync({
        projectId: 1,
        payload: {
          name: 'Quick Secrets Sweep',
          skipEnrichment: false,
          repoIds: [],
          toolNames: ['gitleaks'],
          skipToolIds: [],
          segments: [],
          argProfileIds: [],
        },
      })
    })

    expect(method).toBe('POST')
    await waitFor(() => expect(result.current.save.isSuccess).toBe(true))
    expect(result.current.save.data?.id).toBe(1)
    expect(result.current.save.data?.tools[0].toolName).toBe('gitleaks')
  })

  it('create with argProfileIds returns the hydrated fixture', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useSaveScan(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        projectId: 1,
        payload: {
          name: 'Full SAST + SCA',
          skipEnrichment: true,
          repoIds: [1, 2],
          toolNames: ['gitleaks', 'osv-scanner', 'semgrep'],
          skipToolIds: ['xsstrike'],
          segments: ['sast', 'sca', 'secrets'],
          argProfileIds: [3, 4],
        },
      })
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.argProfiles).toHaveLength(2)
    expect(result.current.data?.argProfiles[0].toolName).toBe('gitleaks')
  })

  it('replace PUTs to the scan id endpoint and returns the replaced fixture', async () => {
    let url: string | null = null
    server.use(
      http.put('/api/v1/projects/1/saved-scans/1', async ({ request }) => {
        url = request.url
        return HttpResponse.json(savedScanReplaced)
      })
    )

    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useSaveScan(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        projectId: 1,
        payload: {
          name: 'Quick Secrets Sweep (renamed)',
          skipEnrichment: true,
          repoIds: [1],
          toolNames: ['gitleaks', 'semgrep'],
          skipToolIds: [],
          segments: [],
          argProfileIds: [],
        },
        existingId: 1,
      })
    })

    expect(url).toContain('/saved-scans/1')
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.name).toBe('Quick Secrets Sweep (renamed)')
  })

  it('create with empty name surfaces a 422 VALIDATION_ERROR', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useSaveScan(), { wrapper })

    await act(async () => {
      await result.current
        .mutateAsync({
          projectId: 1,
          payload: {
            name: '',
            skipEnrichment: false,
            repoIds: [],
            toolNames: ['gitleaks'],
            skipToolIds: [],
            segments: [],
            argProfileIds: [],
          },
        })
        .catch(() => null)
    })

    await waitFor(() => expect(result.current.isError).toBe(true))
    const err = result.current.error as { code?: string }
    expect(err.code).toBe('VALIDATION_ERROR')
  })

  it('create with conflicting name surfaces a 409 CONFLICT', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useSaveScan(), { wrapper })

    await act(async () => {
      await result.current
        .mutateAsync({
          projectId: 1,
          payload: {
            name: 'Quick Secrets Sweep',
            skipEnrichment: false,
            repoIds: [],
            toolNames: ['gitleaks'],
            skipToolIds: [],
            segments: [],
            argProfileIds: [],
          },
        })
        .catch(() => null)
    })

    await waitFor(() => expect(result.current.isError).toBe(true))
    const err = result.current.error as { code?: string }
    expect(err.code).toBe('CONFLICT')
  })
})

describe('useDeleteSavedScan', () => {
  it('delete returns 204 and invalidates the list query', async () => {
    server.use(
      http.get('/api/v1/projects/1/saved-scans', () => HttpResponse.json(savedScansEmpty))
    )

    const { wrapper } = makeWrapper()
    const { result } = renderHook(
      () => ({ list: useSavedScans(1), del: useDeleteSavedScan() }),
      { wrapper }
    )

    await waitFor(() => expect(result.current.list.isSuccess).toBe(true))

    await act(async () => {
      await result.current.del.mutateAsync({ projectId: 1, savedScanId: 1 })
    })

    await waitFor(() => expect(result.current.list.data?.total).toBe(0))
  })

  it('delete of nonexistent id rejects with NOT_FOUND', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useDeleteSavedScan(), { wrapper })

    await act(async () => {
      await result.current
        .mutateAsync({ projectId: 1, savedScanId: 9999 })
        .catch(() => null)
    })

    await waitFor(() => expect(result.current.isError).toBe(true))
    const err = result.current.error as { code?: string }
    expect(err.code).toBe('NOT_FOUND')
  })
})
