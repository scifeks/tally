import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../../handlers'
import { HandshakeError, bootstrapAuth } from '@/lib/api/handshake'

const ORIGIN = window.location.origin

function setLocation(href: string): void {
  window.history.replaceState({}, '', href)
}

describe('bootstrapAuth', () => {
  beforeEach(() => setLocation(`${ORIGIN}/`))
  afterEach(() => server.resetHandlers())

  it('no-ops when no ?token= is present and never fires a request', async () => {
    const spy = vi.fn()
    server.use(http.post('/api/v1/auth/exchange', spy))
    setLocation(`${ORIGIN}/`)
    await expect(bootstrapAuth()).resolves.toBeUndefined()
    expect(spy).not.toHaveBeenCalled()
  })

  it('exchanges ?token= via POST with body {token}', async () => {
    let payload: unknown = null
    server.use(
      http.post('/api/v1/auth/exchange', async ({ request }) => {
        payload = await request.json()
        return HttpResponse.json({ ok: true })
      }),
    )
    setLocation(`${ORIGIN}/?token=abc123`)
    await bootstrapAuth()
    expect(payload).toEqual({ token: 'abc123' })
  })

  it('strips ?token= from window.location BEFORE POST is observed', async () => {
    let observedSearch: string | null = null
    server.use(
      http.post('/api/v1/auth/exchange', () => {
        observedSearch = window.location.search
        return HttpResponse.json({ ok: true })
      }),
    )
    setLocation(`${ORIGIN}/?token=abc123`)
    await bootstrapAuth()
    expect(observedSearch).toBe('')
    expect(window.location.search).toBe('')
  })

  it('throws HandshakeError when exchange returns non-2xx', async () => {
    server.use(
      http.post('/api/v1/auth/exchange', () =>
        HttpResponse.json({ error: { code: 'UNAUTHENTICATED' } }, { status: 401 }),
      ),
    )
    setLocation(`${ORIGIN}/?token=expired`)
    await expect(bootstrapAuth()).rejects.toBeInstanceOf(HandshakeError)
  })

  it('preserves other query params when stripping token', async () => {
    server.use(
      http.post('/api/v1/auth/exchange', () => HttpResponse.json({ ok: true })),
    )
    setLocation(`${ORIGIN}/projects/1?token=abc&tab=findings`)
    await bootstrapAuth()
    expect(window.location.search).toBe('?tab=findings')
    expect(window.location.pathname).toBe('/projects/1')
  })
})
