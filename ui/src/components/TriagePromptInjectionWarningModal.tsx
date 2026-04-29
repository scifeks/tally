import { Modal, ModalButton } from './Modal'
import { useUI } from '@/lib/store'
import { AlertTriangle } from 'lucide-react'

/**
 * One-time warning shown the first time the user starts (or resumes, or
 * single-finding-triages) a triage run. The triage worker shells out to
 * `claude --print` and feeds it raw finding metadata — strings that may
 * have been crafted by an attacker (e.g., a malicious page crawled by ZAP
 * could embed prompt-injection payloads in the URL or response body).
 *
 * The user has to accept once; acceptance is persisted to localStorage via
 * the `useUI` Zustand `persist` middleware so the modal never shows again
 * on this browser. The modal mirrors the spirit of the REPL's interactive
 * prompt that previously gated triage commands.
 */
export function TriagePromptInjectionWarningModal({
  open,
  onAccept,
  onCancel,
}: {
  open: boolean
  onAccept: () => void
  onCancel: () => void
}) {
  const setAcked = useUI(s => s.setTriageInjectionAcked)

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
            <span className="text-primary">claude</span> for analysis.
          </div>
        </div>
        <div className="border border-border bg-muted/30 p-2 text-[11px] text-muted-foreground leading-relaxed">
          <span className="text-dim">{'//'}</span> finding data can carry attacker-controlled
          strings (e.g., a malicious page crawled by ZAP may embed prompt-injection payloads). by
          accepting, you authorize triage to send this data to claude. you only need to accept once
          per browser.
        </div>
      </div>
    </Modal>
  )
}
