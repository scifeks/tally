import { AlertTriangle } from 'lucide-react'
import { Modal, ModalButton } from './Modal'
import { useUI } from '@/lib/store'

/**
 * Surfaces a finding-mutation failure (PATCH rollback). Mirrors the
 * `ProjectSwitchModal` blocked-branch layout: AlertTriangle + reason
 * line + small hint block. Dismissing clears the error slice.
 *
 * `FINDING_LOCKED` 409s render the holder's job id from `details.job_id`
 * so the analyst knows what to wait for.
 */
export function FindingMutationErrorModal() {
  const error = useUI(s => s.findingMutationError)
  const setError = useUI(s => s.setFindingMutationError)
  const open = error !== null
  const dismiss = () => setError(null)

  const isLock = error?.code === 'FINDING_LOCKED'
  const jobId = typeof error?.details.job_id === 'string' ? (error.details.job_id as string) : null

  return (
    <Modal
      open={open}
      onClose={dismiss}
      title="update failed"
      tone="error"
      width="sm"
      footer={<ModalButton onClick={dismiss}>dismiss</ModalButton>}
    >
      <div className="space-y-3">
        <div className="flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 text-crit mt-0.5 shrink-0" />
          <div className="text-foreground leading-relaxed">
            {isLock ? (
              <>
                this finding is currently held by{' '}
                <span className="text-crit font-bold">{jobId ?? 'another job'}</span>. your edit was
                rolled back.
              </>
            ) : (
              <>{error?.message ?? 'the request failed'}. your edit was rolled back.</>
            )}
          </div>
        </div>
        <div className="border border-border bg-muted/30 p-2 text-[11px] text-muted-foreground leading-relaxed">
          <span className="text-dim">{'//'}</span>{' '}
          {isLock ? (
            <>wait for the running job to release the finding, then try again.</>
          ) : (
            <>
              <span className="text-dim">code:</span>{' '}
              <span className="text-foreground">{error?.code ?? 'UNKNOWN'}</span>
              {error?.status ? (
                <>
                  {' · '}
                  <span className="text-dim">status:</span>{' '}
                  <span className="text-foreground">{error.status}</span>
                </>
              ) : null}
            </>
          )}
        </div>
      </div>
    </Modal>
  )
}
