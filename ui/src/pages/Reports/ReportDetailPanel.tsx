import { X } from 'lucide-react'
import { EditableText } from '@/components/Editable'
import { formatDateTime } from '@/lib/utils'
import type { ReportHistoryEntry } from '@/lib/types'

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-3">
      <div className="w-20 shrink-0 text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
        {label}
      </div>
      <div className="flex-1 text-foreground text-xs">{value}</div>
    </div>
  )
}

export function ReportDetailPanel({
  report,
  onUpdateName,
  onUpdateNotes,
  onClose,
}: {
  report: ReportHistoryEntry
  onUpdateName: (name: string) => void
  onUpdateNotes: (notes: string) => void
  onClose: () => void
}) {
  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span
          className="text-xs font-mono text-muted-foreground truncate flex-1"
          title={report.filename}
        >
          {report.filename}
        </span>
        <button
          onClick={onClose}
          className="text-dim hover:text-foreground transition-colors ml-2"
          aria-label="Close detail panel"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Editable Name */}
      <div className="space-y-1">
        <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Name</div>
        <EditableText
          value={report.displayName ?? ''}
          onChange={onUpdateName}
          placeholder="click to name this report"
          ariaLabel="Report name"
        />
      </div>

      {/* Editable Notes */}
      <div className="space-y-1">
        <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Notes</div>
        <EditableText
          value={report.notes ?? ''}
          onChange={onUpdateNotes}
          placeholder="click to add notes"
          multiline
          ariaLabel="Report notes"
        />
      </div>

      {/* Read-only fields */}
      <div className="space-y-2 pt-2 border-t border-border">
        <Field label="Date" value={formatDateTime(report.generatedAt)} />
        <Field label="Format" value={report.format.toUpperCase()} />
        <Field label="Size" value={`${(report.sizeBytes / 1024).toFixed(0)} KB`} />
      </div>
    </div>
  )
}
