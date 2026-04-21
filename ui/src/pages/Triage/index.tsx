import { useState, useEffect, useRef, useMemo, useCallback } from "react"
import { Play, Square, RotateCcw, Brain } from "lucide-react"
import { cn } from "@/lib/utils"
import { Panel } from "@/components/tty"
import { useUI } from "@/lib/store"
import { useProjects, useProjectMeta, useFindings, useStartTriage, useCancelTriage } from "@/lib/api"
import type { Domain, TriageLogEvent, TriageLogEventType, TriageRunStatus } from "@/lib/types"
import { NeuralGrid } from "./NeuralGrid"
import { BatchRow } from "./BatchRow"
import type { BatchDisplay } from "./BatchRow"
import { LogRow } from "./LogRow"

const SEGMENTS: Domain[] = ["sast", "sca", "web", "secrets"]
const SEGMENT_LABEL: Record<Domain, string> = {
  sast: "SAST",
  sca: "SCA",
  web: "WEB",
  secrets: "SECRETS",
}
const BATCH_SIZE = 5 // findings per batch

export default function Triage() {
  const activeProjectId = useUI((s) => s.activeProjectId)
  const setTriageRunStatus = useUI((s) => s.setTriageRunStatus)

  // TODO [BACKEND]: These hooks return mock data. Replace with real API calls.
  // GET /api/v1/projects
  const { data: projects = [] } = useProjects()
  // GET /api/v1/projects/:id/meta
  const { data: projectMetaData } = useProjectMeta(activeProjectId)
  // GET /api/v1/projects/:id/findings
  const { data: findings = [] } = useFindings({ projectId: activeProjectId })

  // TODO [BACKEND]: These mutations trigger server actions.
  // POST /api/v1/projects/:id/triage/start
  const { mutate: startTriageMutation } = useStartTriage()
  // POST /api/v1/triage/:id/cancel
  const { mutate: cancelTriageMutation } = useCancelTriage()

  void startTriageMutation
  void cancelTriageMutation

  const project = projects.find((p) => p.id === activeProjectId)
  const meta = projectMetaData

  // Count findings eligible for triage (open status, no existing triage)
  const eligibleFindings = useMemo(
    () => findings.filter((f) => f.projectId === activeProjectId && f.status === "open"),
    [findings, activeProjectId],
  )

  // Triage run state
  const [runStatus, setRunStatus] = useState<TriageRunStatus>("idle")
  const [logs, setLogs] = useState<TriageLogEvent[]>([])
  const [batches, setBatches] = useState<BatchDisplay[]>([])
  const [expandedBatches, setExpandedBatches] = useState<Set<string>>(new Set())
  const [progress, setProgress] = useState(0)
  const [elapsedSec, setElapsedSec] = useState(0)

  // Refs for simulation
  const eventQueueRef = useRef<TriageLogEvent[]>([])
  const eventIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const logEndRef = useRef<HTMLDivElement>(null)

  void meta

  // Sync global triage status
  useEffect(() => {
    setTriageRunStatus(runStatus)
  }, [runStatus, setTriageRunStatus])

  // Generate simulated triage events
  const generateEvents = useCallback((): { events: TriageLogEvent[]; batches: BatchDisplay[] } => {
    const events: TriageLogEvent[] = []
    const batchList: BatchDisplay[] = []
    const runId = `TR-${Date.now()}`
    let ts = Date.now()
    let batchCounter = 0

    const addEvent = (type: TriageLogEventType, msg: string, extra?: Partial<TriageLogEvent>) => {
      events.push({
        id: `TE-${ts}`,
        runId,
        type,
        timestamp: new Date(ts).toISOString(),
        message: msg,
        ...extra,
      })
      ts += Math.random() * 500 + 200
    }

    addEvent("run_started", `Triage started for ${eligibleFindings.length} findings`)

    // Group by segment and create batches
    for (const segment of SEGMENTS) {
      const segmentFindings = eligibleFindings.filter((f) => f.domain === segment)
      if (segmentFindings.length === 0) continue

      // Split into batches
      for (let i = 0; i < segmentFindings.length; i += BATCH_SIZE) {
        const batchFindings = segmentFindings.slice(i, i + BATCH_SIZE)
        const batchId = `B-${String(batchCounter++).padStart(3, "0")}`

        batchList.push({
          id: batchId,
          segment,
          findingCount: batchFindings.length,
          status: "pending",
          attempt: 1,
        })

        addEvent("batch_created", `Batch ${batchId} created: ${batchFindings.length} ${SEGMENT_LABEL[segment]} findings`, {
          batchId,
          segment,
          findingsCount: batchFindings.length,
        })
      }
    }

    // Process batches
    let processedTotal = 0
    for (const batch of batchList) {
      addEvent("batch_started", `Processing ${batch.id}...`, { batchId: batch.id, segment: batch.segment })

      // Simulate Claude thinking
      const thinkTime = Math.random() * 3 + 1
      for (let p = 0; p < 3; p++) {
        processedTotal += Math.floor(batch.findingCount / 3)
        addEvent("batch_progress", `Claude analyzing... ${Math.min(100, Math.floor((p + 1) * 33))}%`, {
          batchId: batch.id,
          processedCount: processedTotal,
          totalCount: eligibleFindings.length,
        })
      }

      // Random failure (10% chance)
      const fails = Math.random() < 0.1
      if (fails) {
        addEvent("batch_failed", `${batch.id} failed: API timeout`, { batchId: batch.id, segment: batch.segment })
        addEvent("batch_retry", `Retrying ${batch.id} (attempt 2)...`, { batchId: batch.id, attempt: 2 })
        // Retry succeeds
        addEvent("batch_completed", `${batch.id} complete (retry): ${batch.findingCount} findings triaged`, {
          batchId: batch.id,
          segment: batch.segment,
          findingsCount: batch.findingCount,
        })
      } else {
        addEvent("batch_completed", `${batch.id} complete: ${batch.findingCount} findings triaged in ${thinkTime.toFixed(1)}s`, {
          batchId: batch.id,
          segment: batch.segment,
          findingsCount: batch.findingCount,
        })
      }
    }

    addEvent("run_completed", `Triage complete: ${eligibleFindings.length} findings processed across ${batchList.length} batches`)

    return { events, batches: batchList }
  }, [eligibleFindings])

  // Start triage
  const startTriage = useCallback(() => {
    setRunStatus("running")
    setLogs([])
    setProgress(0)
    setElapsedSec(0)

    const { events, batches: newBatches } = generateEvents()
    eventQueueRef.current = events
    setBatches(newBatches.map((b) => ({ ...b, status: "pending" as const })))

    // Elapsed timer
    timerRef.current = setInterval(() => setElapsedSec((s) => s + 1), 1000)

    // Stream events
    let batchIdx = 0
    eventIntervalRef.current = setInterval(() => {
      if (eventQueueRef.current.length === 0) {
        if (eventIntervalRef.current) clearInterval(eventIntervalRef.current)
        if (timerRef.current) clearInterval(timerRef.current)
        setRunStatus("completed")
        setProgress(100)
        setBatches((prev) => prev.map((b) => ({ ...b, status: "completed" as const, finishedAt: new Date().toISOString() })))
        return
      }

      const next = eventQueueRef.current.shift()!
      setLogs((prev) => [...prev, next])

      // Update batch status based on event
      if (next.type === "batch_started" && next.batchId) {
        setBatches((prev) =>
          prev.map((b) =>
            b.id === next.batchId ? { ...b, status: "in_progress" as const, startedAt: next.timestamp } : b,
          ),
        )
      } else if (next.type === "batch_completed" && next.batchId) {
        setBatches((prev) =>
          prev.map((b) =>
            b.id === next.batchId ? { ...b, status: "completed" as const, finishedAt: next.timestamp } : b,
          ),
        )
        batchIdx++
        setProgress(Math.floor((batchIdx / newBatches.length) * 100))
      } else if (next.type === "batch_failed" && next.batchId) {
        setBatches((prev) =>
          prev.map((b) => (b.id === next.batchId ? { ...b, status: "failed" as const } : b)),
        )
      } else if (next.type === "batch_retry" && next.batchId) {
        setBatches((prev) =>
          prev.map((b) =>
            b.id === next.batchId ? { ...b, status: "in_progress" as const, attempt: next.attempt ?? 2 } : b,
          ),
        )
      }
    }, 180)
  }, [generateEvents])

  // Stop triage
  const stopTriage = useCallback(() => {
    if (eventIntervalRef.current) clearInterval(eventIntervalRef.current)
    if (timerRef.current) clearInterval(timerRef.current)
    eventQueueRef.current = []
    setLogs((prev) => [
      ...prev,
      {
        id: `TE-cancel-${Date.now()}`,
        runId: "",
        type: "run_cancelled",
        timestamp: new Date().toISOString(),
        message: "Triage cancelled by user",
      },
    ])
    setRunStatus("cancelled")
  }, [])

  // Reset
  const resetTriage = useCallback(() => {
    setRunStatus("idle")
    setLogs([])
    setBatches([])
    setProgress(0)
    setElapsedSec(0)
  }, [])

  // Auto-scroll log
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [logs])

  // Cleanup
  useEffect(() => {
    return () => {
      if (eventIntervalRef.current) clearInterval(eventIntervalRef.current)
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [])

  const toggleBatch = (id: string) => {
    setExpandedBatches((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const formatElapsed = (sec: number) => {
    const m = Math.floor(sec / 60)
    const s = sec % 60
    return `${m}:${s.toString().padStart(2, "0")}`
  }

  const isRunning = runStatus === "running"
  const canStart = runStatus === "idle" || runStatus === "completed" || runStatus === "cancelled" || runStatus === "failed"

  // Summary stats
  const completedBatches = batches.filter((b) => b.status === "completed").length
  const failedBatches = batches.filter((b) => b.status === "failed").length
  const totalProcessed = batches
    .filter((b) => b.status === "completed")
    .reduce((sum, b) => sum + b.findingCount, 0)

  return (
    <div className="h-full flex flex-col min-h-0 p-4 gap-4">
      {/* Header: graphic + controls + stats */}
      <div className="flex items-start gap-6 shrink-0">
        {/* Neural grid animation */}
        <NeuralGrid active={isRunning} progress={progress} size={180} />

        {/* Controls + info */}
        <div className="flex-1 flex flex-col gap-4">
          {/* Project line */}
          <div className="flex items-center gap-4">
            <span className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
              <span className="text-accent">[</span> PROJECT <span className="text-accent">]</span>
            </span>
            <span className="text-sm text-primary font-bold">{project?.code} / {project?.name}</span>
            <span className="text-xs text-dim">{eligibleFindings.length} findings eligible</span>
          </div>

          {/* Status */}
          <div className="flex items-center gap-4">
            <span className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
              <span className="text-accent">[</span> STATUS <span className="text-accent">]</span>
            </span>
            <span
              className={cn(
                "text-sm font-bold uppercase tracking-wider",
                runStatus === "running" && "text-high animate-pulse",
                runStatus === "completed" && "text-low",
                runStatus === "cancelled" && "text-muted-foreground",
                runStatus === "failed" && "text-crit",
                runStatus === "idle" && "text-muted-foreground",
              )}
            >
              {runStatus === "idle" ? "ready" : runStatus}
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
          {runStatus !== "idle" && (
            <div className="h-2 bg-muted border border-border w-full max-w-md">
              <div
                className="h-full bg-accent transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          )}

          {/* Buttons */}
          <div className="flex items-center gap-3">
            {canStart && (
              <button
                onClick={startTriage}
                disabled={eligibleFindings.length === 0}
                className={cn(
                  "flex items-center gap-2 px-4 h-9 font-bold text-xs uppercase tracking-wider transition-colors",
                  eligibleFindings.length === 0
                    ? "bg-muted text-dim cursor-not-allowed"
                    : "bg-accent text-background hover:bg-accent/80",
                )}
              >
                <Brain className="h-4 w-4" />
                Start Triage
              </button>
            )}
            {isRunning && (
              <button
                onClick={stopTriage}
                className="flex items-center gap-2 px-4 h-9 border border-crit text-crit font-bold text-xs uppercase tracking-wider hover:bg-crit/10 transition-colors"
              >
                <Square className="h-4 w-4" />
                Stop
              </button>
            )}
            {(runStatus === "completed" || runStatus === "cancelled" || runStatus === "failed") && (
              <button
                onClick={resetTriage}
                className="flex items-center gap-2 px-4 h-9 border border-border text-muted-foreground font-bold text-xs uppercase tracking-wider hover:bg-muted/30 transition-colors"
              >
                <RotateCcw className="h-4 w-4" />
                Reset
              </button>
            )}
          </div>

          {/* Summary stats */}
          {runStatus !== "idle" && (
            <div className="flex items-center gap-6 text-xs">
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground uppercase tracking-wider">Batches:</span>
                <span className="text-primary tabular-nums font-bold">
                  {completedBatches}/{batches.length}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground uppercase tracking-wider">Processed:</span>
                <span className="text-accent tabular-nums font-bold">{totalProcessed}</span>
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
      <div className="flex-1 min-h-0 grid grid-cols-2 gap-4">
        {/* Batches panel */}
        <Panel title="batches" className="min-h-0" bodyClassName="overflow-auto">
          {batches.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground p-4">
              <Brain className="h-10 w-10 text-dim" />
              <div className="text-sm text-center">
                {eligibleFindings.length === 0
                  ? "No findings eligible for triage."
                  : "Press Start Triage to begin AI analysis."}
              </div>
              {eligibleFindings.length > 0 && (
                <div className="text-xs text-dim">
                  {Math.ceil(eligibleFindings.length / BATCH_SIZE)} batches will be created
                </div>
              )}
            </div>
          ) : (
            <div className="divide-y divide-border">
              {batches.map((batch) => (
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
        <Panel title="triage log" className="min-h-0" bodyClassName="overflow-auto bg-background font-mono">
          {logs.length === 0 ? (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              Waiting for triage to start...
            </div>
          ) : (
            <>
              {logs.map((event) => (
                <LogRow key={event.id} event={event} />
              ))}
              <div ref={logEndRef} />
            </>
          )}
        </Panel>
      </div>
    </div>
  )
}
