import { AlertTriangle, Check, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ReportDraft } from '@/lib/types'
import { SECTION_ORDER, SECTION_LABELS } from './constants'

export function PreflightChecklist({
  drafts,
  onClose,
  onConfirm,
}: {
  drafts: ReportDraft[]
  onClose: () => void
  onConfirm: () => void
}) {
  const allReady = drafts.every(d => d.status === 'draft' || d.status === 'reviewed')
  const reviewedCount = drafts.filter(d => d.status === 'reviewed').length

  return (
    <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center">
      <div className="bg-background border border-border w-full max-w-lg">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <h2 className="text-sm font-bold uppercase tracking-wider">
            <span className="text-accent">[</span>
            PDF Pre-flight Check
            <span className="text-accent">]</span>
          </h2>
          <button onClick={onClose} className="text-dim hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-4 space-y-3">
          {SECTION_ORDER.map(section => {
            const draft = drafts.find(d => d.section === section)
            const status = draft?.status ?? 'not_generated'
            const ready = status === 'draft' || status === 'reviewed'

            return (
              <div key={section} className="flex items-center gap-3">
                {ready ? (
                  <Check className="h-4 w-4 text-good" />
                ) : (
                  <X className="h-4 w-4 text-crit" />
                )}
                <span className={cn('flex-1 text-sm', ready ? 'text-foreground' : 'text-dim')}>
                  {SECTION_LABELS[section]}
                </span>
                {status === 'reviewed' && (
                  <span className="text-[10px] uppercase text-good">Reviewed</span>
                )}
                {status === 'draft' && (
                  <span className="text-[10px] uppercase text-accent">Draft</span>
                )}
                {status === 'not_generated' && (
                  <span className="text-[10px] uppercase text-crit">Missing</span>
                )}
              </div>
            )
          })}
        </div>

        <div className="px-4 py-3 border-t border-border bg-muted/20">
          {allReady ? (
            <div className="flex items-center justify-between">
              <span className="text-sm text-good">
                All sections ready ({reviewedCount} reviewed, {6 - reviewedCount} drafts)
              </span>
              <button
                onClick={onConfirm}
                className="px-4 py-2 bg-accent text-background text-sm font-bold uppercase tracking-wider hover:bg-accent/90 transition-colors"
              >
                Generate PDF
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-crit text-sm">
              <AlertTriangle className="h-4 w-4" />
              <span>
                {6 - drafts.filter(d => d.status === 'draft' || d.status === 'reviewed').length}{' '}
                section(s) missing. Generate all drafts before creating PDF.
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
