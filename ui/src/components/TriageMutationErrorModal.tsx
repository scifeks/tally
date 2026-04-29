import { AlertTriangle } from 'lucide-react'
import { Modal, ModalButton } from './Modal'
import { useUI } from '@/lib/store'

/**
 * Surfaces a triage start/cancel/resume failure. Mirrors the
 * `ScanMutationErrorModal` layout: AlertTriangle + reason line + small hint
 * block, dismiss-only footer.
 *
 * Special-cased copy for the codes the backend can return:
 *   - JOB_ALREADY_RUNNING (409)    — another triage holds the lock
 *   - TRIAGE_NOT_CANCELLABLE (409) — already in a terminal state
 *   - TRIAGE_NOT_RESUMABLE (409)   — terminal (done/cancelled), can't resume
 *   - VALIDATION_ERROR (422)       — typically the missing ack flag
 *   - NOT_FOUND (404)              — project has no scans yet, or no batches
 */
export function TriageMutationErrorModal() {
  const error = useUI(s => s.triageMutationError)
  const setError = useUI(s => s.setTriageMutationError)
  const open = error !== null
  const dismiss = () => setError(null)

  const code = error?.code
  const status = error?.status

  const reason = (() => {
    switch (code) {
      case 'JOB_ALREADY_RUNNING':
        return 'a triage run is already active on this project.'
      case 'TRIAGE_NOT_CANCELLABLE':
        return 'this triage run is no longer cancellable (already finished).'
      case 'TRIAGE_NOT_RESUMABLE':
        return 'this triage run is no longer resumable (already finished or cancelled).'
      case 'VALIDATION_ERROR':
        return 'the request was rejected by validation.'
      case 'NOT_FOUND':
        return 'no triage data found for this project — run a scan first.'
      default:
        return `${error?.message ?? 'the request failed'}.`
    }
  })()

  const hint = (() => {
    switch (code) {
      case 'JOB_ALREADY_RUNNING':
        return 'wait for the running triage to complete, or cancel it first.'
      case 'TRIAGE_NOT_CANCELLABLE':
        return 'cancellation only applies to runs that are queued or in progress.'
      case 'TRIAGE_NOT_RESUMABLE':
        return 'resume only applies to failed runs that still have pending or in-progress batches.'
      case 'VALIDATION_ERROR':
        return 'reload the page and try again — if this persists, file a bug.'
      case 'NOT_FOUND':
        return 'a successful scan must complete before triage can run.'
      default:
        return null
    }
  })()

  return (
    <Modal
      open={open}
      onClose={dismiss}
      title="triage failed"
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
