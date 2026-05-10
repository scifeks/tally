import { AlertTriangle } from 'lucide-react'
import { Modal, ModalButton } from './Modal'

type StaleSavedScanItem =
  | { kind: 'repo'; id: number; name?: string | null }
  | { kind: 'tool'; name: string }
  | { kind: 'argProfile'; id: number }

export type { StaleSavedScanItem }

function itemLabel(item: StaleSavedScanItem): string {
  if (item.kind === 'repo') return `repo: ${item.name ?? `id ${item.id}`}`
  if (item.kind === 'tool') return `tool: ${item.name}`
  return `arg profile: id ${item.id}`
}

type Props = {
  open: boolean
  staleItems: StaleSavedScanItem[]
  onDismiss: () => void
}

export function StaleSavedScanModal({ open, staleItems, onDismiss }: Props) {
  return (
    <Modal
      open={open}
      onClose={onDismiss}
      title="saved scan is stale"
      tone="error"
      width="sm"
      footer={<ModalButton onClick={onDismiss}>dismiss</ModalButton>}
    >
      <div className="space-y-3">
        <div className="flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 text-crit mt-0.5 shrink-0" />
          <span>This saved scan references items that no longer exist.</span>
        </div>
        <div className="space-y-1">
          {staleItems.map((item, i) => (
            <div key={i} className="text-[11px] text-muted-foreground font-mono">
              {itemLabel(item)}
            </div>
          ))}
        </div>
        <div className="border border-border bg-muted/30 p-2 text-[11px] text-muted-foreground leading-relaxed">
          <span className="text-dim">{'//'}</span> edit the saved scan to remove or replace the
          stale items, then save and try again.
        </div>
      </div>
    </Modal>
  )
}
