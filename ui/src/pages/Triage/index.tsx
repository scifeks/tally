import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Square, RotateCcw, Brain, AlertTriangle } from 'lucide-react'
import { cn, toEpoch } from '@/lib/utils'
import { Panel } from '@/components/tty'
import { useUI } from '@/lib/store'
import {
  useProjects,
  useFindingsCounts,
  useActiveTriage,
  useLatestTriage,
  useTriageRun,
  useStartTriage,
  useCancelTriage,
  useResumeTriage,
  useTriageEvents,
  useRuntimeDependencies,
  useCapabilities,
} from '@/lib/api'
import type {
  TriageBatch,
  TriageLogEvent,
  TriagePageStatus,
  TriageRunStatus,
  TriageSnapshotPayload,
} from '@/lib/types'
import { NeuralGrid } from './NeuralGrid'
import { BatchRow } from './BatchRow'
import type { BatchDisplay } from './BatchRow'
import { LogRow } from './LogRow'
import { TriageMutationErrorModal } from '@/components/TriageMutationErrorModal'
import { TriagePromptInjectionWarningModal } from '@/components/TriagePromptInjectionWarningModal'
import { NoProjectSelectedState } from '@/components/NoProjectSelectedState'

interface ResumeState {
  scanRunId: number
  error: string
  failedAtFindingId: number | null
}

const RUNNING_STATUSES: ReadonlySet<TriageRunStatus> = new Set(['queued', 'running', 'cancelling'])

function toPageStatus(status: TriageRunStatus | null): TriagePageStatus {
  if (status === null) return 'idle'
  if (status === 'queued' || status === 'running' || status === 'cancelling') return 'running'
  if (status === 'done') return 'completed'
  if (status === 'cancelled') return 'cancelled'
  return 'failed'
}

function batchToDisplay(batch: TriageBatch): BatchDisplay {
  return {
    id: batch.id,
    segment: batch.segment,
    findingCount: batch.findingIds.length,
    status: batch.status,
    attempt: Math.max(1, batch.attempts),
    startedAt: batch.startedAt ?? undefined,
    finishedAt: batch.finishedAt ?? undefined,
  }
}

export default function Triage() {
  const activeProjectId = useUI(s => s.activeProjectId)
  const setTriageRunStatus = useUI(s => s.setTriageRunStatus)
  const triageInjectionAcked = useUI(s => s.triageInjectionAcked)
  const projectIdNum = activeProjectId ?? 0
  const queryClient = useQueryClient()

  const { data: projects = [] } = useProjects()
  const project = projects.find(p => p.id === activeProjectId)

  // Eligible-count label uses the cheap counts endpoint (open/active findings).
  const { data: counts } = useFindingsCounts(
    activeProjectId !== null ? String(activeProjectId) : ''
  )
  const eligibleCount = counts?.byStatus?.active ?? 0

  // Current triage state: prefer the in-flight run; fall back to the latest
  // historical run so the page can resume from a failed/completed view.
  const { data: activeRun } = useActiveTriage(projectIdNum)
  const { data: latestRun } = useLatestTriage(projectIdNum)
  const currentRun = activeRun ?? latestRun ?? null
  const currentScanRunId = currentRun?.scanRunId ?? null

  // Pull batches for the current run (the active/latest endpoints are summary
  // shape and do not include batches).
  const { data: detailRun } = useTriageRun(projectIdNum, currentScanRunId, {
    enabled: projectIdNum > 0 && currentScanRunId !== null,
  })

  // Mutations
  const { mutate: startTriageMutation, isPending: isStartPending } = useStartTriage()
  const { mutate: cancelTriageMutation, isPending: isCancelPending } = useCancelTriage()
  const { mutate: resumeTriageMutation, isPending: isResumePending } = useResumeTriage()

  const { data: runtimeDeps } = useRuntimeDependencies()
  const claudeDep = runtimeDeps?.dependencies.find(d => d.name === 'claude')
  const claudeMissing = claudeDep !== undefined && !claudeDep.installed

  const { data: capabilities } = useCapabilities()

  // Live batches map. Seeded from the detail query, then mutated by SSE.
  const [batches, setBatches] = useState<Map<number, BatchDisplay>>(new Map())
  const [logs, setLogs] = useState<TriageLogEvent[]>([])
  const [expandedBatches, setExpandedBatches] = useState<Set<number>>(new Set())
  const [resume, setResume] = useState<ResumeState | null>(null)
  const [pendingAction, setPendingAction] = useState<'start' | 'resume' | null>(null)
  const [showInjectionWarning, setShowInjectionWarning] = useState(false)
  const [elapsedSec, setElapsedSec] = useState(0)

  const logEndRef = useRef<HTMLDivElement>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Seed batches from the REST detail when its scanRunId matches the current
  // run; replace wholesale on run change.
  useEffect(() => {
    if (!detailRun?.batches) return
    const next = new Map<number, BatchDisplay>()
    for (const batch of detailRun.batches) {
      next.set(batch.id, batchToDisplay(batch))
    }
    setBatches(next)
  }, [detailRun])

  // Reset transient page state when the active project changes.
  useEffect(() => {
    setBatches(new Map())
    setLogs([])
    setResume(null)
    setExpandedBatches(new Set())
    setElapsedSec(0)
  }, [activeProjectId])

  // Sync the global page-status flag (used by ProjectSwitchModal to gate
  // project switches mid-run).
  const pageStatus = toPageStatus(currentRun?.status ?? null)
  useEffect(() => {
    setTriageRunStatus(pageStatus)
  }, [pageStatus, setTriageRunStatus])

  // SSE is the source of truth for terminal transitions: once a
  // triage_failed event has been observed, the page treats the run as no
  // longer running even if the cached active/latest queries haven't
  // refetched yet.
  const isRunning =
    resume === null && currentRun !== null && RUNNING_STATUSES.has(currentRun.status)
  useEffect(() => {
    if (!isRunning || !currentRun?.startedAt) {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
      setElapsedSec(0)
      return
    }
    const startedMs = toEpoch(currentRun.startedAt)
    const tick = () => setElapsedSec(Math.max(0, Math.floor((Date.now() - startedMs) / 1000)))
    tick()
    timerRef.current = setInterval(tick, 1000)
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
  }, [isRunning, currentRun?.startedAt])

  // SSE handlers: snapshot rebuilds the batches map; typed events update it
  // in place. Progress events go to a per-batch slot, never the log array.
  const handleSnapshot = useCallback((snap: TriageSnapshotPayload) => {
    if (snap.scanRunId === null) return
    const next = new Map<number, BatchDisplay>()
    for (const batch of snap.batches) {
      next.set(batch.id, batchToDisplay(batch))
    }
    setBatches(next)
  }, [])

  const handleEvent = useCallback(
    (event: TriageLogEvent) => {
      // batch_progress is high-frequency; only the latest value matters so
      // it never goes into the log array. The summary endpoint already
      // exposes the run-level processed/total fields the page reads.
      if (event.type === 'batch_progress') return

      setLogs(prev => [...prev, event])

      if (event.type === 'triage_failed') {
        setResume({
          scanRunId: event.scanRunId,
          error: event.error ?? 'triage failed',
          failedAtFindingId: event.failedAtFindingId ?? null,
        })
        queryClient.invalidateQueries({ queryKey: ['triage', projectIdNum] })
        return
      }

      if (event.type === 'run_completed' || event.type === 'run_cancelled') {
        setResume(null)
        queryClient.invalidateQueries({ queryKey: ['triage', projectIdNum] })
        return
      }

      // Lifecycle events update the batches map in place.
      if (event.batchId === undefined) return
      const batchId = event.batchId
      setBatches(prev => {
        const next = new Map(prev)
        const existing = next.get(batchId)
        if (event.type === 'batch_created') {
          next.set(batchId, {
            id: batchId,
            segment: event.segment ?? null,
            findingCount: event.findingsCount ?? 0,
            status: 'pending',
            attempt: 1,
          })
        } else if (event.type === 'batch_started' && existing) {
          next.set(batchId, {
            ...existing,
            status: 'in_progress',
            startedAt: event.timestamp,
          })
        } else if (event.type === 'batch_completed' && existing) {
          next.set(batchId, {
            ...existing,
            status: 'completed',
            finishedAt: event.timestamp,
          })
        } else if (event.type === 'batch_failed' && existing) {
          next.set(batchId, { ...existing, status: 'failed' })
        } else if (event.type === 'batch_retry' && existing) {
          next.set(batchId, {
            ...existing,
            status: 'in_progress',
            attempt: event.attempt ?? existing.attempt + 1,
          })
        }
        return next
      })
    },
    [queryClient, projectIdNum]
  )

  useTriageEvents(projectIdNum, handleEvent, {
    enabled: projectIdNum > 0,
    onSnapshot: handleSnapshot,
  })

  // ─── Action helpers ───────────────────────────────────────────────────────

  const fireStart = useCallback(() => {
    if (projectIdNum === 0) return
    setLogs([])
    setBatches(new Map())
    setResume(null)
    startTriageMutation({ projectId: projectIdNum, options: {} })
  }, [projectIdNum, startTriageMutation])

  const fireResume = useCallback(() => {
    if (projectIdNum === 0 || resume === null) return
    resumeTriageMutation({ projectId: projectIdNum, scanRunId: resume.scanRunId })
  }, [projectIdNum, resume, resumeTriageMutation])

  const handleStartClick = useCallback(() => {
    if (!triageInjectionAcked) {
      setPendingAction('start')
      setShowInjectionWarning(true)
      return
    }
    fireStart()
  }, [triageInjectionAcked, fireStart])

  const handleResumeClick = useCallback(() => {
    if (!triageInjectionAcked) {
      setPendingAction('resume')
      setShowInjectionWarning(true)
      return
    }
    fireResume()
  }, [triageInjectionAcked, fireResume])

  const handleStop = useCallback(() => {
    if (projectIdNum === 0 || currentScanRunId === null) return
    cancelTriageMutation({ projectId: projectIdNum, scanRunId: currentScanRunId })
  }, [projectIdNum, currentScanRunId, cancelTriageMutation])

  const handleReset = useCallback(() => {
    setLogs([])
    setBatches(new Map())
    setResume(null)
    setElapsedSec(0)
  }, [])

  const handleAcceptInjectionWarning = useCallback(() => {
    setShowInjectionWarning(false)
    if (pendingAction === 'start') {
      fireStart()
    } else if (pendingAction === 'resume') {
      fireResume()
    }
    setPendingAction(null)
  }, [pendingAction, fireStart, fireResume])

  const handleCancelInjectionWarning = useCallback(() => {
    setShowInjectionWarning(false)
    setPendingAction(null)
  }, [])

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [])

  // ─── Derived display values ───────────────────────────────────────────────

  const batchList = useMemo(() => Array.from(batches.values()), [batches])
  const completedBatches = batchList.filter(b => b.status === 'completed').length
  const failedBatches = batchList.filter(b => b.status === 'failed').length
  const totalProcessed = currentRun?.processedFindings ?? 0
  const totalFindings = currentRun?.totalFindings ?? 0
  const progress =
    totalFindings > 0 ? Math.min(100, Math.floor((totalProcessed / totalFindings) * 100)) : 0

  const showResumeAffordance = resume !== null && !isRunning
  const startBusy = isStartPending || isResumePending
  const startDisabled =
    startBusy || claudeMissing || isRunning || (eligibleCount === 0 && !showResumeAffordance)
  const stopDisabled = isCancelPending || currentRun?.status === 'cancelling'
  const showResetButton =
    !isRunning &&
    currentRun !== null &&
    (currentRun.status === 'done' ||
      currentRun.status === 'cancelled' ||
      currentRun.status === 'failed')

  const formatElapsed = (sec: number) => {
    const m = Math.floor(sec / 60)
    const s = sec % 60
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  const toggleBatch = (id: number) => {
    setExpandedBatches(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const statusLabel = currentRun?.status ?? 'idle'
  const statusClass = cn(
    'text-sm font-bold uppercase tracking-wider',
    statusLabel === 'queued' && 'text-muted-foreground',
    statusLabel === 'running' && 'text-high animate-pulse',
    statusLabel === 'cancelling' && 'text-high animate-pulse',
    statusLabel === 'done' && 'text-low',
    statusLabel === 'cancelled' && 'text-muted-foreground',
    statusLabel === 'failed' && 'text-crit',
    statusLabel === 'idle' && 'text-muted-foreground'
  )

  if (activeProjectId === null) {
    return <NoProjectSelectedState projects={projects} />
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="min-h-full flex flex-col p-4 gap-4">
        <TriageMutationErrorModal />
        <TriagePromptInjectionWarningModal
          open={showInjectionWarning}
          providerLabel={capabilities?.triageBackendLabel ?? null}
          onAccept={handleAcceptInjectionWarning}
          onCancel={handleCancelInjectionWarning}
        />

        {/* Header: graphic + controls + stats */}
        <div className="flex items-start gap-6">
          <NeuralGrid active={isRunning} progress={progress} size={180} />

          <div className="flex-1 flex flex-col gap-4">
            {/* Project line */}
            <div className="flex items-center gap-4">
              <span className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
                <span className="text-accent">[</span> PROJECT{' '}
                <span className="text-accent">]</span>
              </span>
              <span className="text-sm text-primary font-bold">
                {project?.code} / {project?.name}
              </span>
              <span className="text-xs text-dim">{eligibleCount} findings eligible</span>
            </div>

            {/* Status */}
            <div className="flex items-center gap-4">
              <span className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
                <span className="text-accent">[</span> STATUS <span className="text-accent">]</span>
              </span>
              <span className={statusClass}>
                {statusLabel === 'idle'
                  ? 'ready'
                  : statusLabel === 'cancelling'
                    ? 'cancelling…'
                    : statusLabel}
              </span>
              {isRunning && (
                <>
                  <span className="text-xs text-muted-foreground tabular-nums">
                    elapsed: {formatElapsed(elapsedSec)}
                  </span>
                  <span className="text-xs text-accent tabular-nums">{progress}%</span>
                </>
              )}
            </div>

            {/* Progress bar */}
            {currentRun !== null && (
              <div className="h-2 bg-muted border border-border w-full max-w-md">
                <div
                  className="h-full bg-accent transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
            )}

            {/* Backend label */}
            {capabilities?.triageBackendLabel && (
              <span className="text-xs text-zinc-500 dark:text-zinc-400">
                {capabilities.triageBackendLabel}
              </span>
            )}

            {/* Claude-missing gate */}
            {claudeMissing && !isRunning && (
              <div className="flex items-start gap-2 border border-crit bg-crit/5 px-3 py-2 max-w-2xl">
                <AlertTriangle className="h-4 w-4 text-crit mt-0.5 shrink-0" />
                <div className="text-xs text-foreground leading-relaxed">
                  <span className="text-crit font-bold">Claude CLI not installed.</span> Start
                  Triage requires the <span className="text-primary">claude</span> binary on PATH.{' '}
                  {claudeDep?.installHint ?? ''}
                </div>
              </div>
            )}

            {/* Resume note (shown above the button when we just observed a
              failure that left batches in a resumable state) */}
            {showResumeAffordance && (
              <div className="text-xs text-high" data-testid="triage-resume-note">
                last run failed at finding #{resume.failedAtFindingId ?? '?'} - {resume.error}
              </div>
            )}

            {/* Buttons */}
            <div className="flex items-center gap-3">
              {!isRunning && showResumeAffordance && (
                <button
                  onClick={handleResumeClick}
                  disabled={startDisabled}
                  data-testid="triage-resume-button"
                  className={cn(
                    'flex items-center gap-2 px-4 h-9 font-bold text-xs uppercase tracking-wider transition-colors',
                    startDisabled
                      ? 'bg-muted text-dim cursor-not-allowed'
                      : 'bg-high text-background hover:bg-high/70'
                  )}
                >
                  <Brain className="h-4 w-4" />
                  Resume
                </button>
              )}
              {!isRunning && !showResumeAffordance && (
                <button
                  onClick={handleStartClick}
                  disabled={startDisabled}
                  data-testid="triage-start-button"
                  className={cn(
                    'flex items-center gap-2 px-4 h-9 font-bold text-xs uppercase tracking-wider transition-colors',
                    startDisabled
                      ? 'bg-muted text-dim cursor-not-allowed'
                      : 'bg-accent text-background hover:bg-accent/70'
                  )}
                >
                  <Brain className="h-4 w-4" />
                  Start Triage
                </button>
              )}
              {isRunning && (
                <button
                  onClick={handleStop}
                  disabled={stopDisabled}
                  data-testid="triage-stop-button"
                  className="flex items-center gap-2 px-4 h-9 border border-crit text-crit font-bold text-xs uppercase tracking-wider hover:bg-crit/15 hover:shadow-[0_0_10px_rgba(255,77,77,0.2)] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Square className="h-4 w-4" />
                  Stop
                </button>
              )}
              {showResetButton && (
                <button
                  onClick={handleReset}
                  className="flex items-center gap-2 px-4 h-9 border border-border text-muted-foreground font-bold text-xs uppercase tracking-wider hover:border-primary/50 hover:text-foreground transition-colors"
                >
                  <RotateCcw className="h-4 w-4" />
                  Reset
                </button>
              )}
            </div>

            {/* Summary stats */}
            {currentRun !== null && (
              <div className="flex items-center gap-6 text-xs">
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground uppercase tracking-wider">Batches:</span>
                  <span className="text-primary tabular-nums font-bold">
                    {completedBatches}/{batchList.length}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground uppercase tracking-wider">Processed:</span>
                  <span className="text-accent tabular-nums font-bold">
                    {totalProcessed}/{totalFindings}
                  </span>
                </div>
                {failedBatches > 0 && (
                  <div className="flex items-center gap-2">
                    <span className="text-muted-foreground uppercase tracking-wider">Failed:</span>
                    <span className="text-crit tabular-nums font-bold">{failedBatches}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Main content: batches + log */}
        <div className="flex-1 min-h-64 grid grid-cols-2 gap-4">
          {/* Batches panel */}
          <Panel title="batches" className="min-h-0" bodyClassName="overflow-auto">
            {batchList.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground p-4">
                <Brain className="h-10 w-10 text-dim" />
                <div className="text-sm text-center">
                  {eligibleCount === 0
                    ? 'No findings eligible for triage.'
                    : 'Press Start Triage to begin AI analysis.'}
                </div>
              </div>
            ) : (
              <div className="divide-y divide-border">
                {batchList.map(batch => (
                  <BatchRow
                    key={batch.id}
                    batch={batch}
                    expanded={expandedBatches.has(batch.id)}
                    onToggle={() => toggleBatch(batch.id)}
                  />
                ))}
              </div>
            )}
          </Panel>

          {/* Log panel */}
          <Panel
            title="triage log"
            className="min-h-0"
            bodyClassName="overflow-auto bg-background font-mono"
          >
            {logs.length === 0 ? (
              <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
                Waiting for triage to start...
              </div>
            ) : (
              <>
                {logs.map(event => (
                  <LogRow key={event.id} event={event} />
                ))}
                <div ref={logEndRef} />
              </>
            )}
          </Panel>
        </div>
      </div>
    </div>
  )
}
