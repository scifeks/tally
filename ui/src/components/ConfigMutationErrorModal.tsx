import { AlertTriangle } from 'lucide-react'
import { Modal, ModalButton } from './Modal'
import { useUI } from '@/lib/store'

export function ConfigMutationErrorModal() {
  const error = useUI(s => s.configMutationError)
  const setError = useUI(s => s.setConfigMutationError)
  const open = error !== null
  const dismiss = () => setError(null)

  const code = error?.code
  const status = error?.status

  const reason = (() => {
    switch (code) {
      case 'VALIDATION_ERROR':
        return 'one or more fields were rejected by validation.'
      case 'NOT_FOUND':
        return 'the project, repository, or tool override no longer exists.'
      case 'CONFLICT':
        return 'this change conflicts with the current configuration.'
      case 'PATH_TRAVERSAL':
        return 'the server refused the path (security guard).'
      default:
        return `${error?.message ?? 'the request failed'}.`
    }
  })()

  const hint = (() => {
    switch (code) {
      case 'VALIDATION_ERROR':
        return 'check the highlighted fields and try again.'
      case 'NOT_FOUND':
        return 'the row may have been deleted in another tab; reload to refresh.'
      case 'CONFLICT':
        return 'reload to see the latest configuration before retrying.'
      case 'PATH_TRAVERSAL':
        return 'use a path inside the project workspace.'
      default:
        return null
    }
  })()

  return (
    <Modal
      open={open}
      onClose={dismiss}
      title="config action failed"
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
