import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Square, RotateCcw, Brain, AlertTriangle, ChevronDown } from 'lucide-react'
import { cn, toEpoch } from '@/lib/utils'
import { Panel } from '@/components/tty'
import { useUI } from '@/lib/store'
import {
  useProjects,
  useFindingsCounts,
  useActiveTriage,
  useTriageRun,
  useStartTriage,
  useCancelTriage,
  useResumeTriage,
  useTriageEvents,
  useRuntimeDependencies,
  useCapabilities,
  useMcpServeStatus,
  useStartMcpTriage,
  useStopMcpServe,
  useScanHistory,
  fetchTriageMaxBatchId,
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
  const viewedTriageRunId = useUI(s => s.viewedTriageRunId)
  const setViewedTriageRunId = useUI(s => s.setViewedTriageRunId)
  const triageAttemptBoundary = useUI(s => s.triageAttemptBoundary)
  const setTriageAttemptBoundary = useUI(s => s.setTriageAttemptBoundary)
  const projectIdNum = activeProjectId ?? 0
  const queryClient = useQueryClient()

  const { data: projects = [] } = useProjects()
  const project = projects.find(p => p.id === activeProjectId)

  // Eligible-count label uses the cheap counts endpoint (open/active findings).
  const { data: counts } = useFindingsCounts(
    activeProjectId !== null ? String(activeProjectId) : ''
  )
  const eligibleCount = counts?.byStatus?.active ?? 0

  const { data: activeRun } = useActiveTriage(projectIdNum)
  const displayedRunId = activeRun?.scanRunId ?? viewedTriageRunId ?? null

  const currentBoundary =
    projectIdNum > 0 && displayedRunId !== null
      ? (triageAttemptBoundary[`${projectIdNum}:${displayedRunId}`] ?? null)
      : null

  const { data: detailRun, refetch: refetchDetail } = useTriageRun(projectIdNum, displayedRunId, {
    enabled: projectIdNum > 0 && displayedRunId !== null,
    afterBatchId: currentBoundary,
  })

  // Mutations
  const { mutate: startTriageMutation, isPending: isStartPending } = useStartTriage()
  const { mutate: cancelTriageMutation, isPending: isCancelPending } = useCancelTriage()
  const { mutate: resumeTriageMutation, isPending: isResumePending } = useResumeTriage()

  const { data: runtimeDeps } = useRuntimeDependencies()
  const claudeDep = runtimeDeps?.dependencies.find(d => d.name === 'claude')
  const claudeMissing = claudeDep !== undefined && !claudeDep.installed

  const { data: capabilities } = useCapabilities()
  const triageMode = capabilities?.triageMode ?? null
  const { data: mcpStatus } = useMcpServeStatus()
  const startMcpTriage = useStartMcpTriage(projectIdNum)
  const stopMcpServe = useStopMcpServe()

  // Live batches map. Seeded from the detail query, then mutated by SSE.
  const [batches, setBatches] = useState<Map<number, BatchDisplay>>(new Map())
  const [logs, setLogs] = useState<TriageLogEvent[]>([])
  const [expandedBatches, setExpandedBatches] = useState<Set<number>>(new Set())
  const [resume, setResume] = useState<ResumeState | null>(null)
  const [pendingAction, setPendingAction] = useState<'start' | 'resume' | null>(null)
  const [showInjectionWarning, setShowInjectionWarning] = useState(false)
  const [elapsedSec, setElapsedSec] = useState(0)
  const [selectedScanRunId, setSelectedScanRunId] = useState<number | null>(null)
  const [completedStatus, setCompletedStatus] = useState<TriageRunStatus | null>(null)
  const [showRunDropdown, setShowRunDropdown] = useState(false)
  const [mcpToken, setMcpToken] = useState<string | null>(null)
  const runDropdownRef = useRef<HTMLDivElement>(null)

  const logEndRef = useRef<HTMLDivElement>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const { data: scanRuns } = useScanHistory(projectIdNum, { status: 'done' as const })

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

  useEffect(() => {
    setBatches(new Map())
    setLogs([])
  }, [displayedRunId])

  // Reset transient page state when the active project changes.
  useEffect(() => {
    setBatches(new Map())
    setLogs([])
    setResume(null)
    setExpandedBatches(new Set())
    setElapsedSec(0)
    setCompletedStatus(null)
    setViewedTriageRunId(null)
    setMcpToken(null)
  }, [activeProjectId, setViewedTriageRunId])

  // Sync the global page-status flag (used by ProjectSwitchModal to gate
  // project switches mid-run).
  const pageStatus = toPageStatus(activeRun?.status ?? null)
  useEffect(() => {
    setTriageRunStatus(pageStatus)
  }, [pageStatus, setTriageRunStatus])

  // SSE is the source of truth for terminal transitions: once a
  // completed/cancelled/failed event has been observed, the page treats
  // the run as no longer running even if the cached active query hasn't
  // refetched yet. The `run_started`-seen clause covers the reverse
  // window: the SSE snapshot has told us a run is live before the
  // active-run cache is refreshed with the same fact.
  const sawRunStarted = logs.some(l => l.type === 'run_started')
  const isRunning =
    resume === null &&
    completedStatus === null &&
    (isStartPending ||
      isResumePending ||
      (activeRun != null && RUNNING_STATUSES.has(activeRun.status)) ||
      (displayedRunId !== null && sawRunStarted))
  useEffect(() => {
    if (!isRunning || !activeRun?.startedAt) {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
      setElapsedSec(0)
      return
    }
    const startedMs = toEpoch(activeRun.startedAt)
    const tick = () => setElapsedSec(Math.max(0, Math.floor((Date.now() - startedMs) / 1000)))
    tick()
    timerRef.current = setInterval(tick, 1000)
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
  }, [isRunning, activeRun?.startedAt])

  // SSE handlers: snapshot rebuilds the batches map; typed events update it
  // in place. Progress events go to a per-batch slot, never the log array.
  const handleSnapshot = useCallback((snap: TriageSnapshotPayload) => {
    const next = new Map<number, BatchDisplay>()
    for (const batch of snap.batches) {
      next.set(batch.id, batchToDisplay(batch))
    }
    setBatches(next)
  }, [])

  const handleEvent = useCallback(
    (event: TriageLogEvent) => {
      // Ignore anything that isn't for the run this page is watching.
      // Defense in depth: the SSE stream is already run-scoped on the
      // backend; this gate keeps the map safe across the brief window
      // where the subscription is transitioning to a new run id.
      if (displayedRunId === null || event.scanRunId !== displayedRunId) {
        return
      }
      // Defense in depth against the attempt-boundary axis: the backend
      // filter already drops these, but keep the client from surfacing
      // events for batches that belong to a prior attempt.
      if (
        currentBoundary !== null &&
        event.batchId !== undefined &&
        event.batchId <= currentBoundary
      ) {
        return
      }
      // batch_progress is high-frequency; only the latest value matters so
      // it never goes into the log array.
      if (event.type === 'batch_progress') return

      if (event.type === 'run_started') {
        setViewedTriageRunId(event.scanRunId)
      }

      setLogs(prev => [...prev, event])

      if (event.type === 'triage_failed') {
        setCompletedStatus('failed')
        setResume({
          scanRunId: event.scanRunId,
          error: event.error ?? 'triage failed',
          failedAtFindingId: event.failedAtFindingId ?? null,
        })
        queryClient.invalidateQueries({ queryKey: ['triage', projectIdNum] })
        void refetchDetail()
        return
      }

      if (event.type === 'run_completed' || event.type === 'run_cancelled') {
        setCompletedStatus(event.type === 'run_completed' ? 'done' : 'cancelled')
        setResume(null)
        queryClient.invalidateQueries({ queryKey: ['triage', projectIdNum] })
        // Refetch the detail so the map reseeds from the true DB
        // state (including canceled batches), rather than relying on
        // useEffect firing off an unchanged react-query object.
        void refetchDetail()
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
    [
      queryClient,
      projectIdNum,
      displayedRunId,
      setViewedTriageRunId,
      refetchDetail,
      currentBoundary,
    ]
  )

  useTriageEvents(projectIdNum, handleEvent, {
    enabled: projectIdNum > 0 && displayedRunId !== null,
    scanRunId: displayedRunId,
    afterBatchId: currentBoundary,
    onSnapshot: handleSnapshot,
  })

  // Action helpers

  const fireStart = useCallback(() => {
    if (projectIdNum === 0) return
    setLogs([])
    setBatches(new Map())
    setResume(null)
    setCompletedStatus(null)
    startTriageMutation(
      {
        projectId: projectIdNum,
        options: { scanRunId: selectedScanRunId ?? undefined },
      },
      {
        onSuccess: run => setViewedTriageRunId(run.scanRunId),
      }
    )
  }, [projectIdNum, startTriageMutation, selectedScanRunId, setViewedTriageRunId])

  const fireResume = useCallback(() => {
    if (projectIdNum === 0 || resume === null) return
    setCompletedStatus(null)
    setViewedTriageRunId(resume.scanRunId)
    resumeTriageMutation({ projectId: projectIdNum, scanRunId: resume.scanRunId })
  }, [projectIdNum, resume, resumeTriageMutation, setViewedTriageRunId])

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
    if (projectIdNum === 0 || activeRun?.scanRunId == null) return
    cancelTriageMutation({ projectId: projectIdNum, scanRunId: activeRun.scanRunId })
  }, [projectIdNum, activeRun?.scanRunId, cancelTriageMutation])

  const handleReset = useCallback(async () => {
    if (projectIdNum > 0 && displayedRunId !== null) {
      try {
        const max = await fetchTriageMaxBatchId(projectIdNum, displayedRunId)
        setTriageAttemptBoundary(projectIdNum, displayedRunId, max ?? 0)
      } catch {
        // If the fetch fails, fall back to a boundary of 0 so the local
        // clear still happens and future queries won't be filtered
        // incorrectly. The next Start will overwrite this from the
        // mutation response.
        setTriageAttemptBoundary(projectIdNum, displayedRunId, 0)
      }
    }
    setLogs([])
    setBatches(new Map())
    setResume(null)
    setElapsedSec(0)
    setCompletedStatus(null)
    setViewedTriageRunId(null)
  }, [projectIdNum, displayedRunId, setTriageAttemptBoundary, setViewedTriageRunId])

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

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (runDropdownRef.current && !runDropdownRef.current.contains(e.target as Node)) {
        setShowRunDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  // Derived display values

  const batchList = useMemo(() => Array.from(batches.values()), [batches])
  const completedBatches = batchList.filter(b => b.status === 'completed').length
  const failedBatches = batchList.filter(b => b.status === 'failed').length
  const totalProcessed = batchList
    .filter(b => b.status === 'completed')
    .reduce((sum, b) => sum + b.findingCount, 0)
  const totalFindings = batchList.reduce((sum, b) => sum + b.findingCount, 0)
  const progress =
    totalFindings > 0 ? Math.min(100, Math.floor((totalProcessed / totalFindings) * 100)) : 0

  const showResumeAffordance = resume !== null && !isRunning
  const startBusy = isStartPending || isResumePending
  const startDisabled =
    startBusy || claudeMissing || isRunning || (eligibleCount === 0 && !showResumeAffordance)
  const stopDisabled = isCancelPending || activeRun?.status === 'cancelling'
  const showResetButton = !isRunning && batchList.length > 0

  const detailStatus = detailRun?.batches?.length ? (detailRun.status as TriageRunStatus) : null
  const effectiveStatus = activeRun?.status ?? completedStatus ?? detailStatus ?? null
  const hasVisibleRun = isRunning || batchList.length > 0

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

  const statusLabel = effectiveStatus ?? 'idle'
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
            {hasVisibleRun && (
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
            {triageMode !== 'mcp' && claudeMissing && !isRunning && (
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
            {triageMode !== 'mcp' && showResumeAffordance && (
              <div className="text-xs text-high" data-testid="triage-resume-note">
                last run failed at finding #{resume.failedAtFindingId ?? '?'} - {resume.error}
              </div>
            )}

            {/* Buttons */}
            <div className="flex items-center gap-3">
              {triageMode !== 'mcp' && !isRunning && showResumeAffordance && (
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
              {triageMode !== 'mcp' && !isRunning && !showResumeAffordance && (
                <div ref={runDropdownRef} className="relative flex">
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
                    {selectedScanRunId != null
                      ? `Triage Run #${selectedScanRunId}`
                      : 'Start Triage'}
                  </button>
                  {scanRuns.length > 0 && (
                    <button
                      onClick={() => setShowRunDropdown(s => !s)}
                      disabled={startDisabled}
                      aria-label="pick a scan run to triage"
                      data-testid="triage-run-dropdown-toggle"
                      className={cn(
                        'flex items-center px-2 h-9 border-l border-background/30 transition-all',
                        startDisabled
                          ? 'bg-muted text-dim cursor-not-allowed'
                          : 'bg-accent text-background hover:bg-accent/70'
                      )}
                    >
                      <ChevronDown className="h-4 w-4" />
                    </button>
                  )}
                  {showRunDropdown && scanRuns.length > 0 && (
                    <div className="absolute top-full left-0 mt-1 w-72 border border-border bg-background z-50 shadow-lg isolate">
                      <div className="px-3 py-1.5 text-[10px] uppercase tracking-[0.2em] text-dim border-b border-border">
                        [ scan runs ]
                      </div>
                      {scanRuns.map(scan => (
                        <button
                          key={scan.id}
                          onClick={() => {
                            setSelectedScanRunId(scan.id)
                            setViewedTriageRunId(scan.id)
                            setLogs([])
                            setShowRunDropdown(false)
                          }}
                          className={cn(
                            'w-full text-left px-3 py-2 text-xs hover:bg-muted transition-colors border-b border-border last:border-b-0',
                            selectedScanRunId === scan.id && 'bg-accent/20 text-accent'
                          )}
                        >
                          <div className="font-bold tabular-nums">
                            Run #{scan.id}
                            {scan.findingsCount != null && (
                              <span className="ml-2 font-normal text-dim">
                                {scan.findingsCount} findings
                              </span>
                            )}
                          </div>
                          <div className="text-[10px] text-dim">
                            {scan.toolIds.join(', ')}
                            {scan.startedAt && ` · ${scan.startedAt}`}
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {triageMode !== 'mcp' && isRunning && (
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
              {triageMode !== 'mcp' && showResetButton && (
                <button
                  onClick={handleReset}
                  data-testid="triage-reset-button"
                  className="flex items-center gap-2 px-4 h-9 border border-border text-muted-foreground font-bold text-xs uppercase tracking-wider hover:border-primary/50 hover:text-foreground transition-colors"
                >
                  <RotateCcw className="h-4 w-4" />
                  Reset
                </button>
              )}
              {triageMode === 'mcp' && !mcpStatus?.active && (
                <button
                  onClick={() => {
                    startMcpTriage.mutate(undefined, {
                      onSuccess: data => setMcpToken(data.token),
                    })
                  }}
                  disabled={startMcpTriage.isPending}
                  data-testid="triage-mcp-start-button"
                  className={cn(
                    'flex items-center gap-2 px-4 h-9 font-bold text-xs uppercase tracking-wider transition-colors',
                    startMcpTriage.isPending
                      ? 'bg-muted text-dim cursor-not-allowed'
                      : 'bg-accent text-background hover:bg-accent/70'
                  )}
                >
                  <Brain className="h-4 w-4" />
                  Start MCP Triage
                </button>
              )}
              {triageMode === 'mcp' && mcpStatus?.active && (
                <div className="flex items-center gap-4">
                  <button
                    onClick={() => stopMcpServe.mutate()}
                    disabled={stopMcpServe.isPending}
                    data-testid="triage-mcp-stop-button"
                    className="flex items-center gap-2 px-4 h-9 border border-crit text-crit font-bold text-xs uppercase tracking-wider hover:bg-crit/15 hover:shadow-[0_0_10px_rgba(255,77,77,0.2)] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <Square className="h-4 w-4" />
                    Stop MCP Triage
                  </button>
                  <div className="flex items-start gap-2 border border-accent/40 bg-accent/5 px-3 py-2 max-w-2xl">
                    <Brain className="h-4 w-4 text-accent mt-0.5 shrink-0" />
                    <div className="text-xs text-foreground leading-relaxed">
                      <div>
                        MCP server running on{' '}
                        <span className="text-primary">
                          {mcpStatus.host}:{mcpStatus.port}
                        </span>
                      </div>
                      {mcpToken && (
                        <div>
                          Token: <code className="text-accent">{mcpToken}</code>
                        </div>
                      )}
                      <div>
                        Open Claude Code and run <code className="text-accent">/tally-triage</code>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Summary stats */}
            {hasVisibleRun && (
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
                    : triageMode === 'mcp'
                      ? 'Press Start MCP Triage to begin AI analysis.'
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
