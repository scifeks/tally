import { useState, useEffect } from 'react'
import { Panel } from '@/components/tty'
import { EditableText, EditableSelect } from '@/components/Editable'
import { cn, formatRelative } from '@/lib/utils'
import type { Finding, Severity, Status } from '@/lib/types'
import { useUI } from '@/lib/store'
import { useStartTriage, useRuntimeDependencies, useDeleteFinding } from '@/lib/api'
import { TriagePromptInjectionWarningModal } from '@/components/TriagePromptInjectionWarningModal'
import {
  SEV_ORDER,
  SEV_LABEL,
  SEV_COLOR,
  STATUS_ORDER,
  STATUS_LABEL,
  STATUS_COLOR,
} from './constants'

// ─── Field ────────────────────────────────────────────────────────────────────

function Field({
  label,
  value,
  mono,
  accent,
}: {
  label: string
  value: string
  mono?: boolean
  accent?: boolean
}) {
  return (
    <div className="flex items-baseline gap-3">
      <div className="w-20 shrink-0 text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
        {label}
      </div>
      <div
        className={cn('flex-1', mono && 'font-mono', accent ? 'text-primary' : 'text-foreground')}
      >
        {value}
      </div>
    </div>
  )
}

// ─── FindingDetailPanel ───────────────────────────────────────────────────────

export function FindingDetailPanel({
  finding,
  onUpdate,
  projectId,
  onDelete,
}: {
  finding: Finding | null
  onUpdate: (patch: Partial<Finding> & { triaged?: boolean }) => void
  projectId: number | null
  onDelete?: () => void
}) {
  const activeProjectId = useUI(s => s.activeProjectId)
  const triageInjectionAcked = useUI(s => s.triageInjectionAcked)
  const { mutate: startTriageMutation, isPending: isTriagePending } = useStartTriage()
  const { data: runtimeDeps } = useRuntimeDependencies()
  const claudeDep = runtimeDeps?.dependencies.find(d => d.name === 'claude')
  const claudeMissing = claudeDep !== undefined && !claudeDep.installed
  const [showInjectionWarning, setShowInjectionWarning] = useState(false)
  const deleteMutation = useDeleteFinding()
  const [confirmDelete, setConfirmDelete] = useState(false)

  useEffect(() => {
    setConfirmDelete(false)
  }, [finding?.id])

  if (!finding) {
    return (
      <Panel title="detail" className="h-full">
        <div className="p-6 text-xs text-muted-foreground leading-relaxed">
          <div className="text-dim mb-2">{'// no finding selected'}</div>
          click a row to inspect it.
        </div>
      </Panel>
    )
  }

  const fireTriage = () => {
    if (activeProjectId === null) return
    startTriageMutation({
      projectId: activeProjectId,
      options: { findingIds: [finding.id] },
    })
  }

  const handleTriageClick = () => {
    if (!triageInjectionAcked) {
      setShowInjectionWarning(true)
      return
    }
    fireTriage()
  }

  const handleAcceptInjectionWarning = () => {
    setShowInjectionWarning(false)
    fireTriage()
  }

  const triageDisabled = claudeMissing || isTriagePending || activeProjectId === null

  return (
    <Panel title={`detail :: ${finding.id}`} className="h-full" bodyClassName="overflow-auto">
      <div className="p-4 space-y-4 text-xs">
        {/* Header row: editable severity + status, read-only timestamp */}
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
              severity
            </span>
            <EditableSelect<Severity>
              value={finding.severity}
              options={SEV_ORDER.map(s => ({
                value: s,
                label: SEV_LABEL[s],
                color: SEV_COLOR[s],
              }))}
              onChange={next => onUpdate({ severity: next })}
              ariaLabel="Edit severity"
              renderValue={v => (
                <span
                  className="uppercase tracking-wider font-bold"
                  style={{ color: SEV_COLOR[v] }}
                >
                  {SEV_LABEL[v]}
                </span>
              )}
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
              status
            </span>
            <EditableSelect<Status>
              value={finding.status}
              options={STATUS_ORDER.map(s => ({
                value: s,
                label: STATUS_LABEL[s],
                color: STATUS_COLOR[s],
              }))}
              onChange={next => onUpdate({ status: next })}
              ariaLabel="Edit status"
              renderValue={v => (
                <span className="uppercase tracking-wider" style={{ color: STATUS_COLOR[v] }}>
                  {STATUS_LABEL[v]}
                </span>
              )}
            />
          </div>
          <span className="ml-auto text-muted-foreground">
            {formatRelative(finding.discoveredAt)}
          </span>
        </div>

        {/* Editable title */}
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-1 flex items-center gap-2">
            <span>title</span>
            <span className="text-dim normal-case tracking-normal">{'// click to edit'}</span>
          </div>
          <EditableText
            value={finding.title}
            onChange={next => onUpdate({ title: next })}
            ariaLabel="Edit finding title"
            valueClassName="text-sm text-primary tty-glow leading-relaxed"
            inputClassName="text-sm"
          />
        </div>

        <Field label="segment" value={finding.segment.toUpperCase()} />
        <Field label="tool" value={finding.tool} />
        <Field label="target" value={finding.target} mono />
        {finding.file && (
          <Field label="file" value={`${finding.file}:${finding.line ?? ''}`} mono />
        )}
        <Field
          label="type"
          value={finding.findingType.length > 0 ? finding.findingType.join(', ') : '-'}
        />
        <Field label="cwe" value={finding.cwe.length > 0 ? finding.cwe.join(', ') : '-'} />

        {/* Editable notes */}
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-1 flex items-center gap-2">
            <span>notes</span>
            <span className="text-dim normal-case tracking-normal">{'// click to edit'}</span>
          </div>
          <EditableText
            value={finding.notes ?? ''}
            onChange={next => onUpdate({ notes: next })}
            multiline
            placeholder="// add triage notes..."
            ariaLabel="Edit notes"
          />
        </div>

        {/* Editable description */}
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-1 flex items-center gap-2">
            <span>description</span>
            <span className="text-dim normal-case tracking-normal">{'// click to edit'}</span>
          </div>
          <EditableText
            value={finding.description ?? ''}
            onChange={next => onUpdate({ description: next })}
            multiline
            placeholder="// add description..."
            ariaLabel="Edit finding description"
          />
        </div>

        <TriagePromptInjectionWarningModal
          open={showInjectionWarning}
          onAccept={handleAcceptInjectionWarning}
          onCancel={() => setShowInjectionWarning(false)}
        />

        <div className="grid grid-cols-2 gap-2 pt-2">
          <button
            onClick={handleTriageClick}
            disabled={triageDisabled}
            className={cn(
              'text-[11px] uppercase tracking-wider py-1.5 border transition-colors',
              triageDisabled
                ? 'border-border text-dim opacity-40 cursor-not-allowed'
                : 'border-accent text-accent hover:bg-accent/15 hover:shadow-[0_0_10px_rgba(57,255,20,0.25)]'
            )}
          >
            &gt; triage
          </button>
          <button
            onClick={() => onUpdate({ status: 'fixed' })}
            className="text-[11px] uppercase tracking-wider py-1.5 border border-border-strong text-foreground hover:border-primary/50 hover:bg-muted/50 transition-colors"
          >
            mark fixed
          </button>
          <button
            onClick={() => onUpdate({ status: 'false_positive' })}
            className="text-[11px] uppercase tracking-wider py-1.5 border border-border text-muted-foreground hover:border-primary/50 hover:text-foreground transition-colors"
          >
            false-pos
          </button>
          <button
            onClick={() => onUpdate({ status: 'wont_fix' })}
            className="text-[11px] uppercase tracking-wider py-1.5 border border-border text-muted-foreground hover:border-primary/50 hover:text-foreground transition-colors"
          >
            wontfix
          </button>
          <button
            onClick={() => onUpdate({ shouldReport: !finding.shouldReport })}
            className={cn(
              'text-[11px] uppercase tracking-wider py-1.5 border transition-colors',
              finding.shouldReport
                ? 'border-accent text-accent hover:bg-accent/15 hover:shadow-[0_0_10px_rgba(57,255,20,0.25)]'
                : 'border-border text-muted-foreground hover:border-primary/50 hover:text-foreground'
            )}
          >
            reportable
          </button>
          <button
            onClick={() => onUpdate({ triaged: !finding.triagedBy })}
            className={cn(
              'text-[11px] uppercase tracking-wider py-1.5 border transition-colors',
              finding.triagedBy
                ? 'border-accent text-accent hover:bg-accent/15 hover:shadow-[0_0_10px_rgba(57,255,20,0.25)]'
                : 'border-border text-muted-foreground hover:border-primary/50 hover:text-foreground'
            )}
          >
            triaged
          </button>
        </div>

        {finding.triagedBy && (
          <div className="text-[10px] text-muted-foreground">
            triaged by {finding.triagedBy}{' '}
            {finding.triagedAt ? formatRelative(finding.triagedAt) : ''}
          </div>
        )}

        {finding.tool === 'manual' && (
          <div className="border-t border-border pt-3 mt-1">
            {confirmDelete ? (
              <div className="space-y-2">
                <p className="text-[10px] text-muted-foreground">
                  This cannot be undone. Delete this finding?
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      if (projectId === null) return
                      deleteMutation.mutate(
                        {
                          projectId: String(projectId),
                          findingId: finding.id,
                        },
                        { onSuccess: () => onDelete?.() }
                      )
                      setConfirmDelete(false)
                    }}
                    className="flex-1 text-[11px] uppercase tracking-wider py-1.5 border border-red-900 text-red-400 hover:bg-red-950"
                  >
                    confirm delete
                  </button>
                  <button
                    onClick={() => setConfirmDelete(false)}
                    className="flex-1 text-[11px] uppercase tracking-wider py-1.5 border border-border text-muted-foreground hover:bg-muted"
                  >
                    cancel
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setConfirmDelete(true)}
                className="w-full text-[11px] uppercase tracking-wider py-1.5 border border-red-900/50 text-red-400/80 hover:bg-red-950/50 hover:text-red-400"
              >
                delete finding
              </button>
            )}
          </div>
        )}
      </div>
    </Panel>
  )
}
