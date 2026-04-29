import { AlertTriangle } from 'lucide-react'
import { Modal, ModalButton } from './Modal'
import { useUI } from '@/lib/store'

/**
 * Surfaces a chat session create / delete / send / cancel failure.
 * Mirrors the `ReportMutationErrorModal` layout: AlertTriangle + reason
 * line + small hint block, dismiss-only footer.
 *
 * Special-cased copy for the codes the chat backend can return
 * (endpoints.md §12):
 *   - CHAT_SESSION_EXPIRED (409)        — sealed by a new scan run
 *   - CHAT_STREAM_ALREADY_RUNNING (409) — one in-flight stream per session
 *   - CHAT_NO_ACTIVE_STREAM (409)       — cancel with nothing to cancel
 *   - VALIDATION_ERROR (422)            — empty / over-length content
 *   - NOT_FOUND (404)                   — session or project missing
 */
export function ChatMutationErrorModal() {
  const error = useUI(s => s.chatMutationError)
  const setError = useUI(s => s.setChatMutationError)
  const open = error !== null
  const dismiss = () => setError(null)

  const code = error?.code
  const status = error?.status

  const reason = (() => {
    switch (code) {
      case 'CHAT_SESSION_EXPIRED':
        return 'this chat session was sealed when a scan completed.'
      case 'CHAT_STREAM_ALREADY_RUNNING':
        return 'another response is already streaming for this session.'
      case 'CHAT_NO_ACTIVE_STREAM':
        return 'no in-flight response to cancel.'
      case 'VALIDATION_ERROR':
        return 'message content is empty or exceeds the size limit.'
      case 'NOT_FOUND':
        return 'this chat session no longer exists.'
      default:
        return `${error?.message ?? 'the request failed'}.`
    }
  })()

  const hint = (() => {
    switch (code) {
      case 'CHAT_SESSION_EXPIRED':
        return 'create a new session to continue the conversation.'
      case 'CHAT_STREAM_ALREADY_RUNNING':
        return 'wait for the in-flight response to finish, or cancel it first.'
      case 'CHAT_NO_ACTIVE_STREAM':
        return 'the stream may have already completed before the cancel arrived.'
      case 'VALIDATION_ERROR':
        return 'enter a non-empty message under the per-turn character limit.'
      case 'NOT_FOUND':
        return 'the session may have been purged or deleted in another tab.'
      default:
        return null
    }
  })()

  return (
    <Modal
      open={open}
      onClose={dismiss}
      title="chat action failed"
      tone="error"
      width="sm"
      footer={<ModalButton onClick={dismiss}>dismiss</ModalButton>}
    >
      <div className="space-y-3">
        <div className="flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 text-crit mt-0.5 shrink-0" />
          <div className="text-foreground leading-relaxed">{reason}</div>
        </div>
        <div className="border border-border bg-muted/30 p-2 text-[11px] text-muted-foreground leading-relaxed">
          <span className="text-dim">{'//'}</span>{' '}
          {hint ? (
            hint
          ) : (
            <>
              <span className="text-dim">code:</span>{' '}
              <span className="text-foreground">{code ?? 'UNKNOWN'}</span>
              {status ? (
                <>
                  {' · '}
                  <span className="text-dim">status:</span>{' '}
                  <span className="text-foreground">{status}</span>
                </>
              ) : null}
            </>
          )}
        </div>
      </div>
    </Modal>
  )
}
