/**
 * Full-screen, non-dismissable modal shown when the backend rejects a
 * request with 401. The user cannot recover in-tab — the desktop entry
 * point requires re-running `tally ui` to mint a fresh handshake.
 */

import { createPortal } from 'react-dom'

export function SessionExpiredModal() {
  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Session expired"
      data-testid="session-expired-modal"
      className="fixed inset-0 z-[200] flex items-center justify-center p-6"
    >
      <div className="absolute inset-0 bg-background/95" />
      <div className="relative w-full max-w-md border-2 border-crit bg-background p-6 text-xs">
        <h2 className="text-crit text-sm uppercase tracking-[0.22em] font-bold mb-3">
          Session expired
        </h2>
        <p className="text-foreground leading-relaxed">
          Your session is no longer valid. Close this tab and re-run{' '}
          <code className="text-accent">tally ui</code> to start a new session.
        </p>
      </div>
    </div>,
    document.body
  )
}
