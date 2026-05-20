import { Download, FileText } from 'lucide-react'
import type { ReportHistoryEntry } from '@/lib/types'
import { downloadReportFile } from '@/lib/api'
import { formatDateTime } from '@/lib/utils'
import { cn } from '@/lib/utils'

export function HistoryTable({
  projectId,
  entries,
  selectedReportId,
  onSelectReport,
}: {
  projectId: number
  entries: ReportHistoryEntry[]
  selectedReportId: number | null
  onSelectReport: (id: number | null) => void
}) {
  if (entries.length === 0) {
    return (
      <div className="text-center py-12 text-dim">
        <FileText className="h-8 w-8 mx-auto mb-2 opacity-50" />
        <p>No reports generated yet</p>
      </div>
    )
  }

  return (
    <div className="border border-border">
      <div className="grid grid-cols-[140px_1fr_80px_80px_40px] gap-4 px-4 py-2 bg-muted/30 border-b border-border text-[10px] uppercase tracking-wider text-dim">
        <span>Date</span>
        <span>Name</span>
        <span>Format</span>
        <span>Size</span>
        <span></span>
      </div>
      {entries.map(entry => (
        <div
          key={entry.id}
          role="button"
          tabIndex={0}
          data-testid={`report-history-row-${entry.id}`}
          onClick={() => onSelectReport(entry.id === selectedReportId ? null : entry.id)}
          onKeyDown={e => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              onSelectReport(entry.id === selectedReportId ? null : entry.id)
            }
          }}
          className={cn(
            'grid grid-cols-[140px_1fr_80px_80px_40px] gap-4 px-4 py-3 border-b border-border last:border-b-0 cursor-pointer transition-colors',
            entry.id === selectedReportId
              ? 'bg-accent/10 border-l-2 border-l-accent'
              : 'hover:bg-muted/20'
          )}
        >
          <span className="text-sm text-muted-foreground">{formatDateTime(entry.generatedAt)}</span>
          <span className="text-sm truncate" title={entry.displayName ?? entry.filename}>
            {entry.displayName ?? entry.filename}
          </span>
          <span className="text-sm uppercase text-accent">{entry.format}</span>
          <span className="text-sm text-muted-foreground tabular-nums">
            {(entry.sizeBytes / 1024).toFixed(0)} KB
          </span>
          <button
            onClick={e => {
              e.stopPropagation()
              void downloadReportFile(projectId, entry.id, entry.filename)
            }}
            data-testid={`report-history-download-${entry.id}`}
            className="text-accent cursor-pointer hover:text-foreground transition-colors"
            title="Download report"
          >
            <Download className="h-4 w-4" />
          </button>
        </div>
      ))}
    </div>
  )
}
