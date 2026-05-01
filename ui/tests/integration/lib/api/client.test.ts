import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../../handlers'
import { ApiError, MissingCsrfError, apiFetch, subscribeSessionExpired } from '@/lib/api/client'
import { clearAllCookies, setCookie } from '../../../helpers/cookies'

const ORIGIN = 'http://127.0.0.1'

describe('apiFetch', () => {
  beforeEach(() => clearAllCookies())
  afterEach(() => server.resetHandlers())

  it('GET returns parsed JSON body', async () => {
    server.use(
      http.get(`${ORIGIN}/api/v1/ping`, () => HttpResponse.json({ ok: true })),
    )
    const data = await apiFetch<{ ok: boolean }>(`${ORIGIN}/api/v1/ping`)
    expect(data).toEqual({ ok: true })
  })

  it('GET does not include X-CSRF-Token header', async () => {
    setCookie('tally_csrf', 'csrf-abc')
    let observed: string | null = null
    server.use(
      http.get(`${ORIGIN}/api/v1/ping`, ({ request }) => {
        observed = request.headers.get('x-csrf-token')
        return HttpResponse.json({})
      }),
    )
    await apiFetch(`${ORIGIN}/api/v1/ping`)
    expect(observed).toBeNull()
  })

  it('POST injects X-CSRF-Token from tally_csrf cookie', async () => {
    setCookie('tally_csrf', 'csrf-123')
    let observed: string | null = null
    server.use(
      http.post(`${ORIGIN}/api/v1/widgets`, ({ request }) => {
        observed = request.headers.get('x-csrf-token')
        return HttpResponse.json({ id: 'w1' })
      }),
    )
    await apiFetch(`${ORIGIN}/api/v1/widgets`, { method: 'POST', body: { name: 'x' } })
    expect(observed).toBe('csrf-123')
  })

  it('POST throws MissingCsrfError before issuing the request when cookie is absent', async () => {
    let called = false
    server.use(
      http.post(`${ORIGIN}/api/v1/widgets`, () => {
        called = true
        return HttpResponse.json({})
      }),
    )
    await expect(
      apiFetch(`${ORIGIN}/api/v1/widgets`, { method: 'POST', body: {} }),
    ).rejects.toBeInstanceOf(MissingCsrfError)
    expect(called).toBe(false)
  })

  it('JSON body is encoded and Content-Type set automatically', async () => {
    setCookie('tally_csrf', 'csrf')
    let payload: unknown = null
    let contentType: string | null = null
    server.use(
      http.post(`${ORIGIN}/api/v1/widgets`, async ({ request }) => {
        contentType = request.headers.get('content-type')
        payload = await request.json()
        return HttpResponse.json({ ok: true })
      }),
    )
    await apiFetch(`${ORIGIN}/api/v1/widgets`, {
      method: 'POST',
      body: { name: 'foo', count: 3 },
    })
    expect(contentType).toContain('application/json')
    expect(payload).toEqual({ name: 'foo', count: 3 })
  })

  it('decodes the canonical error envelope into ApiError', async () => {
    server.use(
      http.get(`${ORIGIN}/api/v1/widgets`, () =>
        HttpResponse.json(
          {
            error: {
              code: 'VALIDATION_ERROR',
              message: 'bad input',
              details: { field: 'name' },
            },
          },
          { status: 400 },
        ),
      ),
    )
    await expect(apiFetch(`${ORIGIN}/api/v1/widgets`)).rejects.toMatchObject({
      code: 'VALIDATION_ERROR',
      message: 'bad input',
      status: 400,
      details: { field: 'name' },
    })
  })

  it('falls back to SERVER_ERROR when body is non-JSON', async () => {
    server.use(
      http.get(`${ORIGIN}/api/v1/widgets`, () =>
        new HttpResponse('boom', {
          status: 500,
          headers: { 'content-type': 'text/plain' },
        }),
      ),
    )
    try {
      await apiFetch(`${ORIGIN}/api/v1/widgets`)
      throw new Error('expected throw')
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError)
      expect((e as ApiError).code).toBe('SERVER_ERROR')
      expect((e as ApiError).status).toBe(500)
    }
  })

  it('401 invokes the session-expired subscriber and throws UNAUTHENTICATED', async () => {
    server.use(
      http.get(`${ORIGIN}/api/v1/widgets`, () =>
        HttpResponse.json(
          { error: { code: 'UNAUTHENTICATED', message: 'no session', details: {} } },
          { status: 401 },
        ),
      ),
    )
    const cb = vi.fn()
    const unsub = subscribeSessionExpired(cb)
    try {
      await expect(apiFetch(`${ORIGIN}/api/v1/widgets`)).rejects.toMatchObject({
        code: 'UNAUTHENTICATED',
        status: 401,
      })
      expect(cb).toHaveBeenCalledTimes(1)
    } finally {
      unsub()
    }
  })

  it('returns undefined for 204 No Content', async () => {
    setCookie('tally_csrf', 'csrf')
    server.use(
      http.delete(`${ORIGIN}/api/v1/widgets/1`, () => new HttpResponse(null, { status: 204 })),
    )
    const result = await apiFetch(`${ORIGIN}/api/v1/widgets/1`, { method: 'DELETE' })
    expect(result).toBeUndefined()
  })
})
