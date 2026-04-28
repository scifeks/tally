/**
 * Document.cookie reader. JS-only — never touches localStorage / sessionStorage.
 *
 * Used by `apiFetch` to read the JS-readable `tally_csrf` cookie set by the
 * backend during the handshake. The auth session cookie (`tally_session`)
 * is HttpOnly and is therefore NOT readable here — it travels with every
 * fetch automatically because we always send `credentials: "include"`.
 */
export function readCookie(name: string): string | null {
  const target = `${name}=`
  const parts = document.cookie.split(';')
  for (const part of parts) {
    const trimmed = part.trim()
    if (trimmed.startsWith(target)) {
      return decodeURIComponent(trimmed.slice(target.length))
    }
  }
  return null
}
