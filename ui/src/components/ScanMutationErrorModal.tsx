import { AlertTriangle } from 'lucide-react'
import { Modal, ModalButton } from './Modal'
import { useUI } from '@/lib/store'

/**
 * Surfaces a scan start/cancel failure. Mirrors the `FindingMutationErrorModal`
 * layout: AlertTriangle + reason line + small hint block, dismiss-only footer.
 *
 * The 409 case (`SCAN_ALREADY_RUNNING` / similar) gets a special hint matching
 * the `ProjectSwitchModal` "concurrent projects aren't supported" pattern,
 * since concurrent scans on the same project are also rejected by the
 * orchestrator.
 */
export function ScanMutationErrorModal() {
  const error = useUI(s => s.scanMutationError)
  const setError = useUI(s => s.setScanMutationError)
  const open = error !== null
  const dismiss = () => setError(null)

  const isConflict = error?.status === 409

  return (
    <Modal
      open={open}
      onClose={dismiss}
      title="scan failed"
      tone="error"
      width="sm"
      footer={<ModalButton onClick={dismiss}>dismiss</ModalButton>}
    >
      <div className="space-y-3">
        <div className="flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 text-crit mt-0.5 shrink-0" />
          <div className="text-foreground leading-relaxed">
            {isConflict ? (
              <>a scan is already running on this project.</>
            ) : (
              <>{error?.message ?? 'the request failed'}.</>
            )}
          </div>
        </div>
        <div className="border border-border bg-muted/30 p-2 text-[11px] text-muted-foreground leading-relaxed">
          <span className="text-dim">{'//'}</span>{' '}
          {isConflict ? (
            <>
              concurrent scans on the same project aren&apos;t supported. wait for the running scan
              to complete or cancel it before starting another.
            </>
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
