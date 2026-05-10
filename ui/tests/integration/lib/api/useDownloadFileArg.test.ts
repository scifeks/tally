import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { useDownloadFileArg } from '@/lib/api/useDownloadFileArg'
import { server } from '../../../handlers'
import { clearAllCookies, setCookie } from '../../../helpers/cookies'

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

describe('useDownloadFileArg', () => {
  it('returns a non-empty Blob with expected content on success', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useDownloadFileArg(), { wrapper })

    let blob: Blob | null = null
    await act(async () => {
      blob = await result.current.mutateAsync({ projectId: 2, profileId: 1, argName: '--config' })
    })

    expect(blob).toBeInstanceOf(Blob)
    if (!(blob instanceof Blob)) return
    expect(blob.size).toBeGreaterThan(0)
    const text = await blob.text()
    expect(text).toContain('example-rule')
  })

  it('encodes the arg name into the URL path', async () => {
    let capturedUrl = ''
    server.use(
      http.get(
        '/api/v1/projects/:projectId/arg-profiles/:profileId/files/:argName',
        ({ request }) => {
          capturedUrl = request.url
          return new HttpResponse('data', {
            status: 200,
            headers: { 'Content-Type': 'application/octet-stream' },
          })
        }
      )
    )

    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useDownloadFileArg(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ projectId: 2, profileId: 1, argName: '--config' })
    })

    expect(capturedUrl).toContain(encodeURIComponent('--config'))
  })

  it('rejects with NOT_FOUND code when the profile does not exist', async () => {
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useDownloadFileArg(), { wrapper })

    await act(async () => {
      await result.current
        .mutateAsync({ projectId: 2, profileId: 9999, argName: '--config' })
        .catch(() => null)
    })

    await waitFor(() => expect(result.current.isError).toBe(true))
    const err = result.current.error as { code?: string }
    expect(err.code).toBe('NOT_FOUND')
  })
})
