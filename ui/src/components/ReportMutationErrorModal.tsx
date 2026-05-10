import { AlertTriangle } from 'lucide-react'
import { Modal, ModalButton } from './Modal'
import { useUI } from '@/lib/store'

/**
 * Surfaces a report draft / generate / cancel / upload / delete failure.
 * Mirrors the `TriageMutationErrorModal` layout: AlertTriangle + reason
 * line + small hint block, dismiss-only footer.
 *
 * Special-cased copy for the codes the backend can return:
 *   - JOB_ALREADY_RUNNING (409)     - another report generation is in flight
 *   - REPORT_NOT_CANCELLABLE (409)  - already in a terminal state
 *   - VALIDATION_ERROR (422)        - bad body / missing required fields
 *   - NOT_FOUND (404)               - report or draft section missing
 *   - PATH_TRAVERSAL (400)          - server refused the resolved path
 */
export function ReportMutationErrorModal() {
  const error = useUI(s => s.reportMutationError)
  const setError = useUI(s => s.setReportMutationError)
  const open = error !== null
  const dismiss = () => setError(null)

  const code = error?.code
  const status = error?.status

  const reason = (() => {
    switch (code) {
      case 'JOB_ALREADY_RUNNING':
        return 'a report generation is already running for this project.'
      case 'REPORT_NOT_CANCELLABLE':
        return 'this report run is no longer cancellable (already finished).'
      case 'VALIDATION_ERROR':
        return 'the request was rejected by validation.'
      case 'NOT_FOUND':
        return 'the report or draft section was not found.'
      case 'PATH_TRAVERSAL':
        return 'the server refused the download path (security guard).'
      default:
        return `${error?.message ?? 'the request failed'}.`
    }
  })()

  const hint = (() => {
    switch (code) {
      case 'JOB_ALREADY_RUNNING':
        return 'wait for the running generation to complete, or cancel it first.'
      case 'REPORT_NOT_CANCELLABLE':
        return 'cancellation only applies to runs that are queued or in progress.'
      case 'VALIDATION_ERROR':
        return 'check the form values and try again - if this persists, file a bug.'
      case 'NOT_FOUND':
        return 'the section may not have been generated yet, or the report has been deleted.'
      case 'PATH_TRAVERSAL':
        return 'this should never happen with a real report id - file a bug.'
      default:
        return null
    }
  })()

  return (
    <Modal
      open={open}
      onClose={dismiss}
      title="report action failed"
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
