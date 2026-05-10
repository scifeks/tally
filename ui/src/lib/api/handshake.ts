/**
 * Exchanges the URL `?token=` for `tally_session` + `tally_csrf` cookies.
 * The token is stripped from the URL bar before the POST fires so it
 * cannot leak via the Referer header on subsequent requests. Uses raw
 * `fetch` instead of `apiFetch` because the CSRF cookie doesn't exist yet.
 * No-ops on reload when `?token=` is absent.
 */

export class HandshakeError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'HandshakeError'
  }
}

const EXCHANGE_URL = '/api/v1/auth/exchange'

export async function bootstrapAuth(): Promise<void> {
  const url = new URL(window.location.href)
  const token = url.searchParams.get('token')
  if (!token) return

  // Strip the token from the URL bar BEFORE the POST so any subsequent
  // Referer header (computed from document.URL at request time) does
  // not carry the handshake value.
  url.searchParams.delete('token')
  window.history.replaceState({}, '', url.toString())

  const res = await fetch(EXCHANGE_URL, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  })
  if (!res.ok) {
    throw new HandshakeError(`Handshake failed (${res.status})`)
  }
}
