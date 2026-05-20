import { useRef, useState } from 'react'
import {
  ChevronDown,
  ChevronRight,
  Check,
  X,
  Clock,
  Download,
  FileCheck,
  FileText,
  Loader2,
  RefreshCw,
  Trash2,
  Upload,
} from 'lucide-react'
import { cn, formatDate } from '@/lib/utils'
import type { ReportDraft } from '@/lib/types'
import { downloadDraftSection } from '@/lib/api'
import { SECTION_LABELS } from './constants'

export function DraftCard({
  projectId,
  draft,
  onGenerate,
  onUpload,
  onDelete,
  isGenerating,
  skipTriage,
}: {
  projectId: number
  draft: ReportDraft
  onGenerate: (force: boolean) => void
  onUpload: (file: File) => void
  onDelete: () => void
  isGenerating: boolean
  skipTriage: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const hasDraft = draft.status === 'draft' || draft.status === 'reviewed'
  const isReviewed = draft.status === 'reviewed'

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      onUpload(file)
    }
    e.target.value = ''
  }

  const handleDownload = () => {
    void downloadDraftSection(projectId, draft.section)
  }

  const handleDelete = () => {
    const ok = window.confirm(
      `Delete the ${SECTION_LABELS[draft.section]} draft? This cannot be undone.`
    )
    if (ok) onDelete()
  }

  return (
    <div
      className={cn(
        'border bg-muted/20 transition-colors',
        isReviewed ? 'border-good/50' : 'border-border'
      )}
    >
      <div
        role="button"
        tabIndex={0}
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-muted/30 transition-colors"
        onClick={() => setExpanded(!expanded)}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ' ') setExpanded(v => !v)
        }}
      >
        <button className="shrink-0 text-dim hover:text-foreground">
          {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </button>

        {isReviewed ? (
          <FileCheck className="h-4 w-4 text-good shrink-0" />
        ) : (
          <FileText className="h-4 w-4 text-accent shrink-0" />
        )}

        <span className="flex-1 text-sm font-medium">{SECTION_LABELS[draft.section]}</span>

        {/* Status badge */}
        {draft.status === 'reviewed' && (
          <span className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-good">
            <Check className="h-3 w-3" />
            Reviewed
          </span>
        )}
        {draft.status === 'draft' && (
          <span className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-accent">
            <FileText className="h-3 w-3" />
            Draft Ready
          </span>
        )}
        {draft.status === 'generating' && (
          <span className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-warn">
            <Loader2 className="h-3 w-3 animate-spin" />
            Generating
          </span>
        )}
        {draft.status === 'not_generated' && (
          <span className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-dim">
            <Clock className="h-3 w-3" />
            Not Generated
          </span>
        )}
        {draft.status === 'failed' && (
          <span className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-crit">
            <X className="h-3 w-3" />
            Failed
          </span>
        )}

        {/* Actions */}
        <div
          role="presentation"
          className="flex items-center gap-2"
          onClick={e => e.stopPropagation()}
        >
          {!hasDraft ? (
            <button
              onClick={() => onGenerate(false)}
              disabled={isGenerating}
              data-testid={`report-draft-${draft.section}-generate`}
              className="px-2 py-1 text-[10px] uppercase tracking-wider border border-accent text-accent cursor-pointer hover:bg-accent hover:text-background transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isGenerating ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Generate'}
            </button>
          ) : (
            <button
              onClick={() => onGenerate(true)}
              disabled={isGenerating}
              data-testid={`report-draft-${draft.section}-regenerate`}
              className="p-1.5 text-[10px] border border-border text-muted-foreground cursor-pointer hover:border-accent hover:text-accent transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title="Regenerate (overwrites existing)"
            >
              <RefreshCw className="h-3 w-3" />
            </button>
          )}

          <input
            ref={fileInputRef}
            type="file"
            accept=".md,.txt"
            onChange={handleFileChange}
            className="hidden"
            data-testid={`report-draft-${draft.section}-file-input`}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            data-testid={`report-draft-${draft.section}-upload`}
            className={cn(
              'p-1.5 text-[10px] border transition-colors',
              hasDraft
                ? 'border-border text-muted-foreground cursor-pointer hover:border-good hover:text-good'
                : 'border-border/50 text-dim cursor-not-allowed'
            )}
            disabled={!hasDraft}
            title={hasDraft ? 'Upload reviewed version' : 'Generate draft first'}
          >
            <Upload className="h-3 w-3" />
          </button>

          <button
            onClick={handleDownload}
            data-testid={`report-draft-${draft.section}-download`}
            className={cn(
              'p-1.5 text-[10px] border transition-colors',
              hasDraft
                ? 'border-border text-muted-foreground cursor-pointer hover:border-accent hover:text-accent'
                : 'border-border/50 text-dim cursor-not-allowed'
            )}
            disabled={!hasDraft}
            title={hasDraft ? 'Download draft' : 'No draft to download'}
          >
            <Download className="h-3 w-3" />
          </button>

          <button
            onClick={handleDelete}
            data-testid={`report-draft-${draft.section}-delete`}
            className={cn(
              'p-1.5 text-[10px] border transition-colors',
              hasDraft
                ? 'border-border text-muted-foreground cursor-pointer hover:border-crit hover:text-crit'
                : 'border-border/50 text-dim cursor-not-allowed'
            )}
            disabled={!hasDraft}
            title={hasDraft ? 'Delete draft' : 'No draft to delete'}
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </div>
      </div>

      {expanded && (
        <div className="px-4 py-3 border-t border-border bg-background/50">
          {hasDraft && draft.preview ? (
            <>
              <div className="flex items-center gap-4 mb-2 text-[10px] text-dim">
                <span>{draft.wordCount} words</span>
                {draft.generatedAt && <span>Generated {formatDate(draft.generatedAt)}</span>}
                {draft.reviewedAt && (
                  <span className="text-good">Reviewed {formatDate(draft.reviewedAt)}</span>
                )}
                {draft.uploadedFilename && (
                  <span className="text-good">Uploaded: {draft.uploadedFilename}</span>
                )}
              </div>
              <p className="text-sm text-muted-foreground whitespace-pre-wrap font-mono leading-relaxed">
                {draft.preview}
              </p>
            </>
          ) : draft.error ? (
            <p className="text-sm text-crit">{draft.error}</p>
          ) : (
            <p className="text-sm text-dim italic">
              No content yet. Click &quot;Generate&quot; to create this section using AI.
              {skipTriage
                ? ' (skip-triage mode: includes all findings)'
                : ' (only triaged findings will be included)'}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
