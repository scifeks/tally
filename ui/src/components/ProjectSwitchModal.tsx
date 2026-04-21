import { Modal, ModalButton } from "./Modal"
import type { Project } from "@/lib/types"
import { AlertTriangle } from "lucide-react"

/**
 * Three forms:
 *   - Confirm switching to a different project.
 *   - Block the switch entirely when scans are running on the current project.
 *   - Block the switch entirely when triage is running on the current project.
 */
export function ProjectSwitchModal({
  open,
  from,
  to,
  runningScansCount,
  triageRunning,
  onConfirm,
  onCancel,
}: {
  open: boolean
  from: Project | null
  to: Project | null
  runningScansCount: number
  triageRunning: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  const blockedByScans = runningScansCount > 0
  const blockedByTriage = triageRunning
  const blocked = blockedByScans || blockedByTriage

  if (blocked) {
    const blockReason = blockedByScans
      ? `${runningScansCount} scan${runningScansCount > 1 ? "s" : ""}`
      : "AI triage"
    const blockVerb = blockedByScans
      ? runningScansCount > 1
        ? "are"
        : "is"
      : "is"
    const cancelHint = blockedByScans
      ? `cancel running scans on`
      : `stop the triage process on`

    return (
      <Modal
        open={open}
        onClose={onCancel}
        title="switch blocked"
        tone="error"
        width="sm"
        footer={<ModalButton onClick={onCancel}>dismiss</ModalButton>}
      >
        <div className="space-y-3">
          <div className="flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 text-crit mt-0.5 shrink-0" />
            <div className="text-foreground leading-relaxed">
              cannot switch projects while{" "}
              <span className="text-crit font-bold">{blockReason}</span>{" "}
              {blockVerb} running on{" "}
              <span className="text-primary tty-glow">{from?.code}</span>.
            </div>
          </div>
          <div className="border border-border bg-muted/30 p-2 text-[11px] text-muted-foreground leading-relaxed">
            <span className="text-dim">//</span> concurrent projects aren&apos;t
            supported. {cancelHint}{" "}
            <span className="text-primary">{from?.name}</span> before switching to{" "}
            <span className="text-primary">{to?.name}</span>.
          </div>
        </div>
      </Modal>
    )
  }

  return (
    <Modal
      open={open}
      onClose={onCancel}
      title="confirm switch"
      width="sm"
      footer={
        <>
          <ModalButton onClick={onCancel}>cancel</ModalButton>
          <ModalButton variant="primary" onClick={onConfirm}>
            &gt; confirm
          </ModalButton>
        </>
      }
    >
      <div className="space-y-3">
        <div className="text-foreground leading-relaxed">
          switch active project from{" "}
          <span className="text-primary tty-glow">{from?.code}</span>{" "}
          <span className="text-muted-foreground">({from?.name})</span>
          <br />
          to{" "}
          <span className="text-accent tty-glow">{to?.code}</span>{" "}
          <span className="text-muted-foreground">({to?.name})</span>?
        </div>
        <div className="border border-border bg-muted/30 p-2 text-[11px] text-muted-foreground leading-relaxed">
          <span className="text-dim">//</span> selections and filters on the
          current project will be cleared.
        </div>
      </div>
    </Modal>
  )
}
