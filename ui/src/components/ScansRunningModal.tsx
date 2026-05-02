import { useCallback, useState } from 'react'
import { Link } from 'react-router-dom'
import { Modal, ModalButton } from './Modal'
import { useProjects, useProjectMeta, useScanHistory } from '@/lib/api'
import { useScanEvents, type SnapshotPayload } from '@/lib/api/useScans'
import { useUI } from '@/lib/store'
import type { ScanLogEvent } from '@/lib/types'
import { cn, formatRelative } from '@/lib/utils'
import { ArrowRight } from 'lucide-react'

// Tool-unit events that advance the per-run progress bar. tool_skipped
// counts because that slot in the n*y grid is "done", just not run.
const COMPLETION_EVENT_TYPES: ReadonlySet<ScanLogEvent['type']> = new Set([
  'tool_completed',
  'tool_failed',
  'tool_skipped',
])

const TERMINAL_EVENT_TYPES: ReadonlySet<ScanLogEvent['type']> = new Set([
  'run_completed',
  'run_cancelled',
  'run_failed',
])

export function ScansRunningModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const activeProjectId = useUI(s => s.activeProjectId)
  const projectIdNum = activeProjectId ?? 0
  const projectIdParam = activeProjectId !== null ? String(activeProjectId) : ''

  const { data: projects = [] } = useProjects()
  const { data: scans = [] } = useScanHistory(projectIdNum)
  const { data: projectMeta } = useProjectMeta(projectIdParam)

  const running = scans.filter(s => s.status === 'running')

  const [completedByRun, setCompletedByRun] = useState<Record<number, number>>({})
  const [finishedRuns, setFinishedRuns] = useState<Record<number, true>>({})
  const [currentByRun, setCurrentByRun] = useState<Record<number, { repo: string; tool: string }>>(
    {}
  )

  const handleEvent = useCallback((event: ScanLogEvent) => {
    if (TERMINAL_EVENT_TYPES.has(event.type)) {
      setFinishedRuns(prev => ({ ...prev, [event.runId]: true }))
      return
    }
    if (event.type === 'tool_started' && event.repo && event.tool) {
      const repo = event.repo
      const tool = event.tool
      setCurrentByRun(prev => ({ ...prev, [event.runId]: { repo, tool } }))
      return
    }
    if (COMPLETION_EVENT_TYPES.has(event.type)) {
      setCompletedByRun(prev => ({
        ...prev,
        [event.runId]: (prev[event.runId] ?? 0) + 1,
      }))
    }
  }, [])

  const handleSnapshot = useCallback((snap: SnapshotPayload) => {
    // Seed currentByRun from the snapshot frame so a mid-scan
    // subscriber sees the active (repo, tool) immediately rather
    // than waiting for the next tool_started event. The backend
    // mirrors each tool_started into the run registry.
    if (!snap.activeRuns) return
    setCurrentByRun(prev => {
      const next = { ...prev }
      for (const r of snap.activeRuns ?? []) {
        if (r.repo && r.tool && next[r.runId] === undefined) {
          next[r.runId] = { repo: r.repo, tool: r.tool }
        }
      }
      return next
    })
  }, [])

  // Single SSE subscription for the active project - events fan out to
  // all running cards by runId. Subscribed whenever the modal is open
  // (not gated on running.length > 0) so we don't miss the first
  // tool_started event when a scan begins *after* the modal opens.
  // The snapshot frame additionally seeds currentByRun for scans that
  // were already running at connect time.
  useScanEvents(projectIdNum, handleEvent, {
    enabled: open && projectIdNum > 0,
    onSnapshot: handleSnapshot,
  })

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`scans running :: ${running.length}`}
      width="lg"
      footer={
        <>
          <ModalButton onClick={onClose}>close</ModalButton>
          <Link
            to="/scans"
            onClick={onClose}
            className="inline-flex items-center gap-1 px-3 h-7 border border-accent text-accent hover:bg-muted text-[11px] uppercase tracking-[0.18em] font-bold"
          >
            open scans <ArrowRight className="h-3 w-3" />
          </Link>
        </>
      }
    >
      {running.length === 0 ? (
        <div className="text-muted-foreground py-6 text-center">
          <div className="text-dim mb-1">{'// no scans are currently running'}</div>
          <div>system idle.</div>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="text-[11px] text-muted-foreground leading-relaxed">
            <span className="text-dim">{'//'}</span> streaming segment progress via SSE.
            long-running ingestion + enrichment phases are normal.
          </div>
          {running.map(s => {
            const project = projects.find(p => p.id === s.projectId)
            const n = s.repoIds.length || projectMeta?.repoCount || 0
            const y = s.toolIds.length || projectMeta?.enabledTools?.length || 0
            const total = n * y
            const completed = completedByRun[s.id] ?? 0
            const progress = finishedRuns[s.id]
              ? 100
              : total > 0
                ? Math.min(95, (completed / total) * 100)
                : 0
            const domainsLabel = s.domains.length > 0 ? s.domains.join(', ') : '-'
            const current = currentByRun[s.id]
            const toolsLabel = current
              ? `${current.repo}/${current.tool}`
              : s.toolIds.length > 0
                ? s.toolIds.join(', ')
                : '-'
            return (
              <div key={s.id} className="border border-border bg-background">
                <div className="flex items-center gap-3 px-3 h-8 border-b border-border">
                  <span className="text-dim tabular-nums text-[11px]">{s.id}</span>
                  <span className="text-[11px] text-primary font-bold tty-glow">
                    {project?.code ?? '-'}
                  </span>
                  <span className="text-[11px] text-foreground truncate">{project?.name}</span>
                  <span className="text-[10px] uppercase tracking-wider text-muted-foreground truncate">
                    {domainsLabel}
                  </span>
                  <span className="ml-auto text-[10px] text-dim tabular-nums">
                    started {formatRelative(s.startedAt)}
                  </span>
                </div>
                <div className="p-3 space-y-2">
                  <div className="flex items-baseline justify-between">
                    <div className="text-xs text-accent tty-glow">
                      <span className="tty-cursor-inline">&gt;</span> running
                    </div>
                    <div className="text-[11px] text-muted-foreground tabular-nums truncate">
                      {toolsLabel}
                    </div>
                  </div>
                  <ProgressBar value={progress} />
                  <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-muted-foreground">
                    <span>scan in progress</span>
                    <span className="text-dim">sse://tally/scans/events?run_id={s.id}</span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </Modal>
  )
}

function ProgressBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, value))
  return (
    <div className="relative h-2 w-full border border-border bg-muted overflow-hidden">
      <div
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        className={cn('h-full bg-accent transition-[width] duration-[2000ms] ease-out')}
        style={{ width: `${pct}%` }}
      />
      <div
        className="absolute inset-y-0 w-6 bg-gradient-to-r from-transparent via-[rgba(57,255,20,0.35)] to-transparent animate-[scan-sweep_1.4s_linear_infinite]"
        style={{ left: `${pct}%`, transform: 'translateX(-100%)' }}
        aria-hidden
      />
      <style>{`@keyframes scan-sweep {
        0% { transform: translateX(-120%); }
        100% { transform: translateX(20%); }
      }`}</style>
    </div>
  )
}
