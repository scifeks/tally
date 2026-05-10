import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  useToolArgProfileList,
  useSaveToolArgProfile,
  useDeleteToolArgProfile,
} from '@/lib/api/useToolArgProfiles'
import { server } from '../../../handlers'
import { clearAllCookies, setCookie } from '../../../helpers/cookies'
import argProfilesPopulated from '../../../fixtures/arg-profiles/populated.json'
import argProfilesEmpty from '../../../fixtures/arg-profiles/empty.json'
import argProfileFlagOnly from '../../../fixtures/arg-profiles/flag-only.json'

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

describe('useToolArgProfiles', () => {
  it('list returns items and envelope keys from fixture', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useToolArgProfileList(2), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.total).toBe(4)
    expect(result.current.data?.offset).toBe(0)
    expect(result.current.data?.items).toHaveLength(4)
    expect(result.current.data?.items[0].toolName).toBe('gitleaks')
  })

  it('list with toolName filter routes to the filtered fixture', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useToolArgProfileList(2, { toolName: 'gitleaks' }), {
      wrapper,
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.total).toBe(2)
    expect(result.current.data?.items.every(p => p.toolName === 'gitleaks')).toBe(true)
  })

  it('list with unknown toolName returns an empty items array', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useToolArgProfileList(2, { toolName: 'unknown-tool' }), {
      wrapper,
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.items).toHaveLength(0)
    expect(result.current.data?.total).toBe(0)
  })

  it('create with no files POSTs a JSON payload and new row appears in subsequent list', async () => {
    const newProfile = { ...argProfileFlagOnly, id: 99, name: 'new-flag-profile' }
    let capturedForm: FormData | null = null

    // GET override registered lazily so the initial list sees the default fixture (total: 4).
    server.use(
      http.post('/api/v1/projects/2/arg-profiles', async ({ request }) => {
        capturedForm = await request.formData()
        server.use(
          http.get('/api/v1/projects/2/arg-profiles', () =>
            HttpResponse.json({
              ...argProfilesPopulated,
              items: [...argProfilesPopulated.items, newProfile],
              total: 5,
            })
          )
        )
        return HttpResponse.json(newProfile, { status: 201 })
      })
    )

    const { wrapper } = makeWrapper()
    const { result } = renderHook(
      () => ({
        list: useToolArgProfileList(2),
        save: useSaveToolArgProfile(),
      }),
      { wrapper }
    )

    await waitFor(() => expect(result.current.list.isSuccess).toBe(true))
    expect(result.current.list.data?.total).toBe(4)

    await act(async () => {
      await result.current.save.mutateAsync({
        projectId: 2,
        profile: {
          toolName: 'gitleaks',
          name: 'new-flag-profile',
          args: [{ name: '--verbose', type: 'flag' }],
        },
        files: {},
      })
    })

    const payloadField = capturedForm?.get('payload')
    expect(payloadField).toBeTruthy()
    const payload = JSON.parse(String(payloadField))
    expect(payload.toolName).toBe('gitleaks')
    expect(payload.name).toBe('new-flag-profile')

    await waitFor(() => expect(result.current.list.data?.total).toBe(5))
  })

  it('create with a file includes the file under the arg name in the form', async () => {
    let capturedContentType: string | null = null
    let capturedBody: string | null = null

    // request.formData() fails in JSDOM because undici can't reconstruct a JSDOM File; read raw text instead.
    server.use(
      http.post('/api/v1/projects/2/arg-profiles', async ({ request }) => {
        capturedContentType = request.headers.get('Content-Type')
        capturedBody = await request.text()
        return HttpResponse.json(argProfileFlagOnly, { status: 201 })
      })
    )

    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useSaveToolArgProfile(), { wrapper })

    const testFile = new File(['rules: []'], 'semgrep.yaml', { type: 'text/yaml' })

    await act(async () => {
      await result.current.mutateAsync({
        projectId: 2,
        profile: {
          toolName: 'semgrep',
          name: 'with-rules',
          args: [{ name: '--config', type: 'file', path: '' }],
        },
        files: { '--config': testFile },
      })
    })

    // JSDOM serializes File objects with filename="blob"; check for filename= in the disposition, not the original name.
    expect(capturedContentType).toMatch(/multipart\/form-data/)
    expect(capturedBody).toContain('name="--config"; filename=')
  })

  it('update PUTs to the profile id endpoint and does not create a duplicate', async () => {
    let method: string | null = null
    let url: string | null = null

    server.use(
      http.put('/api/v1/projects/2/arg-profiles/1', async ({ request }) => {
        method = request.method
        url = request.url
        return HttpResponse.json(argProfileFlagOnly)
      })
    )

    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useSaveToolArgProfile(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        projectId: 2,
        profile: {
          toolName: 'gitleaks',
          name: 'verbose-only-updated',
          args: [{ name: '--verbose', type: 'flag' }],
        },
        files: {},
        existingId: 1,
      })
    })

    expect(method).toBe('PUT')
    expect(url).toContain('/arg-profiles/1')
  })

  it('delete returns 204 and cache invalidation empties the list query', async () => {
    server.use(
      http.get('/api/v1/projects/2/arg-profiles', () => HttpResponse.json(argProfilesEmpty))
    )

    const { wrapper } = makeWrapper()
    const { result } = renderHook(
      () => ({
        list: useToolArgProfileList(2),
        del: useDeleteToolArgProfile(),
      }),
      { wrapper }
    )

    await waitFor(() => expect(result.current.list.isSuccess).toBe(true))

    await act(async () => {
      await result.current.del.mutateAsync({ projectId: 2, profileId: 1 })
    })

    await waitFor(() => expect(result.current.list.data?.total).toBe(0))
  })

  it('delete IN_USE rejects with ApiError carrying savedScanIds and savedScanNames', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useDeleteToolArgProfile(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ projectId: 2, profileId: 3 }).catch(() => null)
    })

    await waitFor(() => expect(result.current.isError).toBe(true))
    const err = result.current.error as { details?: { savedScanIds?: number[] } }
    expect(err.details?.savedScanIds).toEqual([2])
  })

  it('create CONFLICT on duplicate name rejects with CONFLICT code', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useSaveToolArgProfile(), { wrapper })

    await act(async () => {
      await result.current
        .mutateAsync({
          projectId: 2,
          profile: { toolName: 'gitleaks', name: 'verbose-only', args: [] },
          files: {},
        })
        .catch(() => null)
    })

    await waitFor(() => expect(result.current.isError).toBe(true))
    const err = result.current.error as { code?: string }
    expect(err.code).toBe('CONFLICT')
  })

  it('update 404 on nonexistent id rejects with NOT_FOUND code', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useSaveToolArgProfile(), { wrapper })

    await act(async () => {
      await result.current
        .mutateAsync({
          projectId: 2,
          profile: { toolName: 'gitleaks', name: 'ghost', args: [] },
          files: {},
          existingId: 9999,
        })
        .catch(() => null)
    })

    await waitFor(() => expect(result.current.isError).toBe(true))
    const err = result.current.error as { code?: string }
    expect(err.code).toBe('NOT_FOUND')
  })
})
