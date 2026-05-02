import '@testing-library/jest-dom'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { server } from './handlers'

// jsdom doesn't implement scrollIntoView; auto-scroll log effects call it.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {}
}

// jsdom does not implement URL.createObjectURL / revokeObjectURL; report
// download helpers use them to trigger an `<a download>` click.
if (typeof URL.createObjectURL !== 'function') {
  URL.createObjectURL = () => 'blob:mock'
}
if (typeof URL.revokeObjectURL !== 'function') {
  URL.revokeObjectURL = () => {}
}

// jsdom logs "Not implemented: navigation to another Document" whenever a
// download anchor is clicked. The download helper has nothing to assert in
// jsdom anyway — the test verifies the underlying fetch, not the file save.
const anchorClick = HTMLAnchorElement.prototype.click
HTMLAnchorElement.prototype.click = function (this: HTMLAnchorElement) {
  if (this.hasAttribute('download')) return
  return anchorClick.call(this)
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
