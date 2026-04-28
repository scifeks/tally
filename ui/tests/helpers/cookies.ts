/**
 * jsdom cookie helpers — `document.cookie` is read/write but does not
 * actually parse attribute strings, so setting a cookie just appends to
 * the existing value. These helpers keep tests honest by clearing first.
 */

export function setCookie(name: string, value: string): void {
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/`
}

export function clearCookie(name: string): void {
  document.cookie = `${name}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`
}

export function clearAllCookies(): void {
  for (const part of document.cookie.split(';')) {
    const eq = part.indexOf('=')
    const name = (eq >= 0 ? part.slice(0, eq) : part).trim()
    if (name) clearCookie(name)
  }
}
