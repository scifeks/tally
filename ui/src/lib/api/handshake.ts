/**
 * Single-shot handshake: exchange the URL `?token=` value for the
 * `tally_session` (HttpOnly) and `tally_csrf` (JS-readable) cookies the
 * rest of the app relies on.
 *
 * Two security-driven ordering choices live here:
 *
 *   1. `history.replaceState` strips the token from the URL bar BEFORE
 *      the POST fires. Browsers compute the Referer header from the
 *      current URL at request time, so cleansing first prevents the
 *      handshake value from leaking out via Referer on any subsequent
 *      cross-origin asset request the SPA might make.
 *   2. We use raw `fetch` (not `apiFetch`) because the CSRF cookie
 *      doesn't exist yet - `apiFetch` would short-circuit with
 *      `MissingCsrfError` on this very request.
 *
 * On a reload (no `?token=` in the URL), `bootstrapAuth` no-ops. The
 * existing `tally_session` cookie either still validates (success) or
 * the next API call returns 401 and `apiFetch` mounts the
 * SessionExpiredModal.
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
