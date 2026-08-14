import { Modal, ModalButton } from './Modal'
import { useUI } from '@/lib/store'
import { AlertTriangle } from 'lucide-react'

/** Finding data may carry attacker-controlled prompt injection payloads. */
export function TriagePromptInjectionWarningModal({
  open,
  onAccept,
  onCancel,
  providerLabel,
}: {
  open: boolean
  onAccept: () => void
  onCancel: () => void
  providerLabel: string | null
}) {
  const setAcked = useUI(s => s.setTriageInjectionAcked)
  const label = providerLabel ?? 'the triage agent'

  const handleAccept = () => {
    setAcked(true)
    onAccept()
  }

  return (
    <Modal
      open={open}
      onClose={onCancel}
      title="prompt injection risk"
      tone="warn"
      width="sm"
      footer={
        <>
          <ModalButton onClick={onCancel}>cancel</ModalButton>
          <ModalButton variant="primary" onClick={handleAccept}>
            &gt; accept &amp; continue
          </ModalButton>
        </>
      }
    >
      <div className="space-y-3">
        <div className="flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 text-high mt-0.5 shrink-0" />
          <div className="text-foreground leading-relaxed">
            triage sends finding metadata (titles, descriptions, URLs, file paths) to{' '}
            <span className="text-primary">{label}</span> for analysis.
          </div>
        </div>
        <div className="border border-border bg-muted/30 p-2 text-[11px] text-muted-foreground leading-relaxed">
          <span className="text-dim">{'//'}</span> finding data can carry attacker-controlled
          strings (e.g., a malicious page crawled by ZAP may embed prompt-injection payloads). by
          accepting, you authorize triage to send this data to {label}. you only need to accept once
          per browser.
        </div>
      </div>
    </Modal>
  )
}
