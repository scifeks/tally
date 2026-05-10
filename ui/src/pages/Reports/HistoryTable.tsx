import { Download, FileText } from 'lucide-react'
import type { ReportHistoryEntry } from '@/lib/types'
import { downloadReportFile } from '@/lib/api'
import { formatDateTime } from '@/lib/utils'

export function HistoryTable({
  projectId,
  entries,
}: {
  projectId: number
  entries: ReportHistoryEntry[]
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
      <div className="grid grid-cols-[1fr_80px_140px_80px_60px] gap-4 px-4 py-2 bg-muted/30 border-b border-border text-[10px] uppercase tracking-wider text-dim">
        <span>Filename</span>
        <span>Format</span>
        <span>Generated</span>
        <span>Size</span>
        <span></span>
      </div>
      {entries.map(entry => (
        <div
          key={entry.id}
          data-testid={`report-history-row-${entry.id}`}
          className="grid grid-cols-[1fr_80px_140px_80px_60px] gap-4 px-4 py-3 border-b border-border last:border-b-0 hover:bg-muted/20 transition-colors"
        >
          <span className="text-sm font-mono truncate" title={entry.filename}>
            {entry.filename}
          </span>
          <span className="text-sm uppercase text-accent">{entry.format}</span>
          <span className="text-sm text-muted-foreground">{formatDateTime(entry.generatedAt)}</span>
          <span className="text-sm text-muted-foreground tabular-nums">
            {(entry.sizeBytes / 1024).toFixed(0)} KB
          </span>
          <button
            onClick={() => void downloadReportFile(projectId, entry.id, entry.filename)}
            data-testid={`report-history-download-${entry.id}`}
            className="text-accent hover:text-foreground transition-colors"
            title="Download report"
          >
            <Download className="h-4 w-4" />
          </button>
        </div>
      ))}
    </div>
  )
}
