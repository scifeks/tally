import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { Play, Square, RotateCcw, Settings2, Terminal, Check, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Panel } from '@/components/tty'
import { useUI } from '@/lib/store'
import {
  useProjects,
  useProjectMeta,
  useProjectScanConfig,
  useStartScan,
  useCancelScan,
  useSavedScans,
  useSaveScan,
  useDeleteSavedScan,
  useToolArgProfileList,
} from '@/lib/api'
import { useScanEvents, type SnapshotPayload } from '@/lib/api/useScans'
import type { Segment, ScanLogEvent, ScanRunStatus, ScanOptions } from '@/lib/types'
import { RadarSweep } from './RadarSweep'
import { LogRow } from './LogRow'
import { HistoryTable } from './HistoryTable'
import { SavedScansTab } from './SavedScansTab'
import { ScanMutationErrorModal } from '@/components/ScanMutationErrorModal'
import { NoProjectSelectedState } from '@/components/NoProjectSelectedState'

const SEGMENT_LABEL: Record<Segment, string> = {
  sast: 'SAST',
  sca: 'SCA',
  web: 'WEB',
  secrets: 'SECRETS',
}

export default function Scans() {
  const activeProjectId = useUI(s => s.activeProjectId)

  const projectIdParam = activeProjectId !== null ? String(activeProjectId) : ''
  const projectIdNum = activeProjectId ?? 0

  const { data: projects = [] } = useProjects()
  const { data: projectMetaData } = useProjectMeta(projectIdParam)
  const { data: scanConfig } = useProjectScanConfig(projectIdNum)

  const { mutate: startScanMutation } = useStartScan()
  const { mutate: cancelScanMutation } = useCancelScan()

  const project = projects.find(p => p.id === activeProjectId)
  const meta = projectMetaData

  // Derived config data - memoized to avoid new array refs on every render
  const configuredRepos = useMemo(() => scanConfig?.repos ?? [], [scanConfig])
  const configuredTools = useMemo(() => scanConfig?.tools ?? [], [scanConfig])
  const configuredDomains = useMemo(() => scanConfig?.segments ?? [], [scanConfig])

  // Scan run state
  const [runStatus, setRunStatus] = useState<ScanRunStatus>('idle')
  const [runId, setRunId] = useState<number | null>(null)
  const [logs, setLogs] = useState<ScanLogEvent[]>([])
  const [enrichmentProgress, setEnrichmentProgress] = useState<{
    enrichedCount: number
    totalToEnrich: number
    timestamp: string
  } | null>(null)
  const [elapsedSec, setElapsedSec] = useState(0)

  // Advanced options state
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [selectedRepos, setSelectedRepos] = useState<Set<number>>(new Set()) // empty = all repos
  const [selectedDomains, setSelectedDomains] = useState<Set<Segment>>(new Set())
  const [selectedTools, setSelectedTools] = useState<Set<string>>(new Set())
  const [skipTools, setSkipTools] = useState<Set<string>>(new Set())
  const [skipEnrichment, setSkipEnrichment] = useState(false)

  // Reset advanced options when project changes
  useEffect(() => {
    setSelectedRepos(new Set())
    setSelectedDomains(new Set())
    setSelectedTools(new Set())
    setSkipTools(new Set())
    setSkipEnrichment(false)
    setSelectedSavedScanId(null)
  }, [activeProjectId])

  // Saved scans (CLIENT-SIDE MOCK — see useSavedScans).
  const { data: savedScans = [] } = useSavedScans(projectIdNum)
  const { data: toolArgProfiles = [] } = useToolArgProfileList(projectIdNum)
  const saveScan = useSaveScan()
  const deleteSavedScan = useDeleteSavedScan()

  // Currently-staged saved scan (UI surface only — does not influence the
  // real Start Scan flow, which still posts ad-hoc scan options).
  const [selectedSavedScanId, setSelectedSavedScanId] = useState<string | null>(null)
  const selectedSavedScan = useMemo(
    () => savedScans.find(s => s.id === selectedSavedScanId) ?? null,
    [savedScans, selectedSavedScanId]
  )

  // Split-button dropdown state for picking a saved scan.
  const [showScanDropdown, setShowScanDropdown] = useState(false)
  const scanDropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (scanDropdownRef.current && !scanDropdownRef.current.contains(e.target as Node)) {
        setShowScanDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  // Tool ↔ domain compatibility. Selecting domains restricts the tools list
  // to those whose `segment` is in the selected set; with no domains chosen,
  // every configured tool is compatible.
  const compatibleToolIds = useMemo(() => {
    if (selectedDomains.size === 0) {
      return new Set(configuredTools.map(t => t.id))
    }
    return new Set(configuredTools.filter(t => selectedDomains.has(t.segment)).map(t => t.id))
  }, [configuredTools, selectedDomains])

  // Drop selected/skip tools that fall outside the currently compatible set
  // when the domain selection changes. The size guard avoids a render when
  // no pruning is needed.
  useEffect(() => {
    if (selectedDomains.size === 0) return
    setSelectedTools(prev => {
      const next = new Set<string>()
      for (const id of prev) if (compatibleToolIds.has(id)) next.add(id)
      return next.size === prev.size ? prev : next
    })
    setSkipTools(prev => {
      const next = new Set<string>()
      for (const id of prev) if (compatibleToolIds.has(id)) next.add(id)
      return next.size === prev.size ? prev : next
    })
  }, [compatibleToolIds, selectedDomains])

  // Build scan options from state
  const buildScanOptions = useCallback((): ScanOptions => {
    const opts: ScanOptions = {}
    if (selectedRepos.size > 0) opts.repoIds = Array.from(selectedRepos)
    if (selectedDomains.size > 0) opts.segments = Array.from(selectedDomains)
    if (selectedTools.size > 0) opts.toolIds = Array.from(selectedTools)
    if (skipTools.size > 0) opts.skipToolIds = Array.from(skipTools)
    if (skipEnrichment) opts.skipEnrichment = true
    return opts
  }, [selectedRepos, selectedDomains, selectedTools, skipTools, skipEnrichment])

  const hasAdvancedOptions =
    selectedRepos.size > 0 ||
    selectedDomains.size > 0 ||
    selectedTools.size > 0 ||
    skipTools.size > 0 ||
    skipEnrichment

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const logEndRef = useRef<HTMLDivElement>(null)
  const runIdRef = useRef<number | null>(null)
  runIdRef.current = runId

  const [activeTab, setActiveTab] = useState<'live' | 'history' | 'saved'>('live')

  const stopElapsedTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const startElapsedTimer = useCallback(() => {
    stopElapsedTimer()
    setElapsedSec(0)
    timerRef.current = setInterval(() => setElapsedSec(s => s + 1), 1000)
  }, [stopElapsedTimer])

  // Per-event SSE handler. `enrichment_progress` is stored in a single state
  // slot (latest-value-wins) per the §12.7 mandate - never appended to logs.
  // The live row in the scan log is rendered from that same slot below.
  const handleScanEvent = useCallback((event: ScanLogEvent) => {
    if (event.type === 'enrichment_progress') {
      setEnrichmentProgress({
        enrichedCount: event.enrichedCount ?? 0,
        totalToEnrich: event.totalToEnrich ?? 0,
        timestamp: event.timestamp,
      })
      return
    }

    // Filter to the current run once one has been claimed by this page.
    const currentRunId = runIdRef.current
    if (currentRunId !== null && event.runId !== currentRunId) return

    setLogs(prev => [...prev, event])

    if (event.type === 'enrichment_complete') {
      setEnrichmentProgress(null)
    } else if (event.type === 'run_started') {
      setRunStatus('running')
    } else if (event.type === 'run_completed') {
      setRunStatus('completed')
      setEnrichmentProgress(null)
    } else if (event.type === 'run_cancelled') {
      setRunStatus('cancelled')
      setEnrichmentProgress(null)
    } else if (event.type === 'run_failed') {
      setRunStatus('failed')
      setEnrichmentProgress(null)
    }
  }, [])

  // Snapshot frame on (re)connect - seed runId/runStatus only when there is
  // exactly one active run for the project so we don't latch onto a stranger.
  const handleSnapshot = useCallback((snap: SnapshotPayload) => {
    if (snap.runId === null) {
      const ids = snap.activeRunIds ?? []
      if (ids.length === 1 && runIdRef.current === null) {
        setRunId(ids[0])
        setRunStatus('running')
      }
      return
    }
    if (snap.status === 'running' || snap.status === 'queued') {
      setRunId(snap.runId)
      setRunStatus('running')
    } else if (snap.status === 'cancelling') {
      setRunId(snap.runId)
      setRunStatus('cancelling')
    }
  }, [])

  useScanEvents(projectIdNum, handleScanEvent, {
    enabled: projectIdNum > 0,
    onSnapshot: handleSnapshot,
  })

  // Stop the elapsed timer once the run leaves a live-running state.
  useEffect(() => {
    if (runStatus !== 'running') stopElapsedTimer()
  }, [runStatus, stopElapsedTimer])

  // Start scan - POST to backend, capture runId from 202, flip to live tab.
  const startScan = useCallback(() => {
    if (projectIdNum === 0) return
    setLogs([])
    setEnrichmentProgress(null)
    setActiveTab('live')
    startScanMutation(
      { projectId: projectIdNum, options: buildScanOptions() },
      {
        onSuccess: scan => {
          setRunId(scan.id)
          setRunStatus('running')
          startElapsedTimer()
        },
      }
    )
  }, [projectIdNum, startScanMutation, buildScanOptions, startElapsedTimer])

  // Cancel scan - POST cancel; UI flips to 'cancelled' on the run_cancelled
  // SSE event, not synthetically. While the backend is processing the cancel,
  // show 'cancelling'.
  const stopScan = useCallback(() => {
    if (runId === null || projectIdNum === 0) return
    setRunStatus('cancelling')
    cancelScanMutation({ projectId: projectIdNum, runId })
  }, [runId, projectIdNum, cancelScanMutation])

  // Reset
  const resetScan = useCallback(() => {
    setRunStatus('idle')
    setRunId(null)
    setLogs([])
    setEnrichmentProgress(null)
    setElapsedSec(0)
    setSelectedSavedScanId(null)
  }, [])

  // Auto-scroll log
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [])

  if (activeProjectId === null) {
    return <NoProjectSelectedState projects={projects} />
  }

  const formatElapsed = (sec: number) => {
    const m = Math.floor(sec / 60)
    const s = sec % 60
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  const isRunning = runStatus === 'running' || runStatus === 'cancelling'
  const canStart =
    runStatus === 'idle' ||
    runStatus === 'completed' ||
    runStatus === 'cancelled' ||
    runStatus === 'failed'

  // Summary stats from logs
  const toolsRun = logs.filter(e => e.type === 'tool_completed' || e.type === 'tool_failed').length
  const toolsSkipped = logs.filter(e => e.type === 'tool_skipped').length
  const totalFindings = logs.reduce((sum, e) => sum + (e.findingsCount ?? 0), 0)
  const failures = logs.filter(e => e.type === 'tool_failed').length

  return (
    <div className="h-full flex flex-col overflow-y-auto p-4 gap-4">
      <ScanMutationErrorModal />
      {/* Header row: radar + controls + stats */}
      <div className="flex items-start gap-6 shrink-0">
        {/* Radar */}
        <RadarSweep active={isRunning} size={180} />

        {/* Controls + info */}
        <div className="flex-1 flex flex-col gap-4">
          {/* Project + status line */}
          <div className="flex items-center gap-4">
            <span className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
              <span className="text-accent">[</span> PROJECT <span className="text-accent">]</span>
            </span>
            <span className="text-sm text-primary font-bold">
              {project?.code} / {project?.name}
            </span>
            <span className="text-xs text-dim">
              {meta?.repoCount ?? 0} repos &middot; {meta?.enabledTools?.length ?? 0} tools
            </span>
          </div>

          {/* Status */}
          <div className="flex items-center gap-4">
            <span className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
              <span className="text-accent">[</span> STATUS <span className="text-accent">]</span>
            </span>
            {selectedSavedScan && runStatus === 'idle' && (
              <span className="text-xs text-high font-bold">{selectedSavedScan.name}</span>
            )}
            <span
              className={cn(
                'text-sm font-bold uppercase tracking-wider',
                runStatus === 'running' && 'text-high animate-pulse',
                runStatus === 'cancelling' && 'text-high animate-pulse',
                runStatus === 'completed' && 'text-low',
                runStatus === 'cancelled' && 'text-muted-foreground',
                runStatus === 'failed' && 'text-crit',
                runStatus === 'idle' && 'text-muted-foreground'
              )}
            >
              {runStatus === 'idle' ? 'ready' : runStatus}
            </span>
            {isRunning && (
              <span className="text-xs text-muted-foreground tabular-nums">
                elapsed: {formatElapsed(elapsedSec)}
              </span>
            )}
            {selectedSavedScan && runStatus === 'idle' && (
              <button
                onClick={() => setSelectedSavedScanId(null)}
                className="text-[10px] text-dim hover:text-muted-foreground"
              >
                (clear)
              </button>
            )}
          </div>

          {/* Buttons */}
          <div className="flex items-center gap-3">
            {canStart && (
              <div ref={scanDropdownRef} className="relative flex">
                <button
                  onClick={startScan}
                  className="flex items-center gap-2 px-4 h-9 bg-accent text-background font-bold text-xs uppercase tracking-wider hover:bg-accent/80 transition-colors"
                >
                  <Play className="h-4 w-4" />
                  Start Scan
                </button>
                {savedScans.length > 0 && (
                  <button
                    onClick={() => setShowScanDropdown(s => !s)}
                    aria-label="pick a saved scan"
                    className="flex items-center px-2 h-9 bg-accent text-background border-l border-background/30 hover:bg-accent/80 transition-colors"
                  >
                    <ChevronDown className="h-4 w-4" />
                  </button>
                )}
                {showScanDropdown && savedScans.length > 0 && (
                  <div className="absolute top-full left-0 mt-1 w-64 border border-border bg-background z-50 shadow-lg">
                    <div className="px-3 py-1.5 text-[10px] uppercase tracking-[0.2em] text-dim border-b border-border">
                      [ saved scans ]
                    </div>
                    {savedScans.map(scan => (
                      <button
                        key={scan.id}
                        onClick={() => {
                          setSelectedSavedScanId(scan.id)
                          setShowScanDropdown(false)
                        }}
                        className={cn(
                          'w-full text-left px-3 py-2 text-xs hover:bg-muted transition-colors border-b border-border last:border-b-0',
                          selectedSavedScanId === scan.id && 'bg-accent/20 text-accent'
                        )}
                      >
                        <div className="font-bold">{scan.name}</div>
                        <div className="text-[10px] text-dim">
                          {scan.toolIds.length} tools &middot;{' '}
                          {scan.segments.length > 0
                            ? scan.segments.map(s => SEGMENT_LABEL[s]).join(', ')
                            : 'all domains'}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
            {canStart && (
              <button
                onClick={() => setShowAdvanced(!showAdvanced)}
                className={cn(
                  'flex items-center gap-2 px-3 h-9 border font-bold text-xs uppercase tracking-wider transition-colors',
                  showAdvanced || hasAdvancedOptions
                    ? 'border-accent text-accent hover:bg-accent/10'
                    : 'border-border text-muted-foreground hover:bg-muted/30'
                )}
                title="Advanced scan options"
              >
                <Settings2 className="h-4 w-4" />
                {hasAdvancedOptions && <span className="text-[10px]">(custom)</span>}
              </button>
            )}
            {isRunning && (
              <button
                onClick={stopScan}
                disabled={runStatus === 'cancelling'}
                className="flex items-center gap-2 px-4 h-9 border border-crit text-crit font-bold text-xs uppercase tracking-wider hover:bg-crit/10 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Square className="h-4 w-4" />
                Stop
              </button>
            )}
            {(runStatus === 'completed' || runStatus === 'cancelled' || runStatus === 'failed') && (
              <button
                onClick={resetScan}
                className="flex items-center gap-2 px-4 h-9 border border-border text-muted-foreground font-bold text-xs uppercase tracking-wider hover:bg-muted/30 transition-colors"
              >
                <RotateCcw className="h-4 w-4" />
                Reset
              </button>
            )}
          </div>

          {/* Summary stats (when not idle) */}
          {runStatus !== 'idle' && (
            <div className="flex items-center gap-6 text-xs">
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground uppercase tracking-wider">Tools:</span>
                <span className="text-primary tabular-nums font-bold">{toolsRun}</span>
                {toolsSkipped > 0 && <span className="text-dim">({toolsSkipped} skipped)</span>}
              </div>
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground uppercase tracking-wider">Findings:</span>
                <span className="text-accent tabular-nums font-bold">{totalFindings}</span>
              </div>
              {failures > 0 && (
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground uppercase tracking-wider">Failures:</span>
                  <span className="text-crit tabular-nums font-bold">{failures}</span>
                </div>
              )}
              {enrichmentProgress && (
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground uppercase tracking-wider">Enriching:</span>
                  <span className="text-accent tabular-nums font-bold">
                    {enrichmentProgress.enrichedCount} / {enrichmentProgress.totalToEnrich}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Advanced Options Panel (collapsible) */}
      {showAdvanced && canStart && (
        <div className="shrink-0 border border-border bg-muted/20 p-4">
          <div className="flex items-center justify-between mb-4">
            <span className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
              <span className="text-accent">[</span> ADVANCED OPTIONS{' '}
              <span className="text-accent">]</span>
            </span>
            <button
              onClick={() => {
                setSelectedRepos(new Set())
                setSelectedDomains(new Set())
                setSelectedTools(new Set())
                setSkipTools(new Set())
                setSkipEnrichment(false)
              }}
              className="text-[10px] text-dim hover:text-muted-foreground uppercase tracking-wider"
            >
              Reset All
            </button>
          </div>

          <div className="grid grid-cols-2 gap-6">
            {/* Left column: Repo + Domain */}
            <div className="space-y-4">
              {/* Repository multi-select */}
              <div>
                <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
                  Repositories {selectedRepos.size > 0 && `(${selectedRepos.size} selected)`}
                </div>
                <div className="max-h-32 overflow-y-auto border border-border bg-background p-2 space-y-1">
                  {configuredRepos.length === 0 ? (
                    <div className="text-[10px] text-dim">No repositories configured</div>
                  ) : (
                    configuredRepos.map(r => {
                      const isSelected = selectedRepos.has(r.id)
                      return (
                        <button
                          key={r.id}
                          onClick={() => {
                            const next = new Set(selectedRepos)
                            if (isSelected) next.delete(r.id)
                            else next.add(r.id)
                            setSelectedRepos(next)
                          }}
                          className={cn(
                            'w-full flex items-center justify-between px-2 h-6 text-[10px] transition-colors',
                            isSelected
                              ? 'bg-accent/20 text-accent'
                              : 'hover:bg-muted/30 text-muted-foreground'
                          )}
                        >
                          <span>{r.name}</span>
                          <span className="uppercase text-[9px] text-dim">{r.source}</span>
                        </button>
                      )
                    })
                  )}
                </div>
                <div className="text-[10px] text-dim mt-1">
                  Leave empty to scan all repositories
                </div>
              </div>

              {/* Domain chips */}
              <div>
                <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
                  Domains {selectedDomains.size > 0 && `(${selectedDomains.size} selected)`}
                </div>
                <div className="flex flex-wrap gap-2">
                  {configuredDomains.map(d => {
                    const isSelected = selectedDomains.has(d)
                    return (
                      <button
                        key={d}
                        onClick={() => {
                          const next = new Set(selectedDomains)
                          if (isSelected) next.delete(d)
                          else next.add(d)
                          setSelectedDomains(next)
                        }}
                        className={cn(
                          'px-3 h-7 text-[10px] uppercase tracking-wider border transition-colors',
                          isSelected
                            ? 'border-accent bg-accent/20 text-accent'
                            : 'border-border text-muted-foreground hover:border-muted-foreground'
                        )}
                      >
                        {SEGMENT_LABEL[d]}
                      </button>
                    )
                  })}
                </div>
                <div className="text-[10px] text-dim mt-1">Leave empty to scan all domains</div>
              </div>

              {/* Skip enrichment */}
              <div>
                <div className="flex items-center gap-2 cursor-pointer">
                  <button
                    onClick={() => setSkipEnrichment(!skipEnrichment)}
                    className={cn(
                      'w-4 h-4 border flex items-center justify-center transition-colors',
                      skipEnrichment
                        ? 'border-accent bg-accent text-background'
                        : 'border-border hover:border-muted-foreground'
                    )}
                  >
                    {skipEnrichment && <Check className="h-3 w-3" />}
                  </button>
                  <span className="text-xs text-foreground">Skip LLM enrichment</span>
                </div>
                <div className="text-[10px] text-dim mt-1 ml-6">
                  Persist findings to ChromaDB without enrichment fields
                </div>
              </div>
            </div>

            {/* Right column: Tools + Skip Tools */}
            <div className="space-y-4">
              {/* Tools multi-select */}
              <div>
                <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
                  Run Only These Tools{' '}
                  {selectedTools.size > 0 && `(${selectedTools.size} selected)`}
                </div>
                <div className="max-h-32 overflow-y-auto border border-border bg-background p-2 space-y-1">
                  {configuredTools.length === 0 ? (
                    <div className="text-[10px] text-dim">No tools configured</div>
                  ) : (
                    configuredTools.map(t => {
                      const isSelected = selectedTools.has(t.id)
                      const isCompatible = compatibleToolIds.has(t.id)
                      return (
                        <button
                          key={t.id}
                          disabled={!isCompatible}
                          onClick={() => {
                            const next = new Set(selectedTools)
                            if (isSelected) next.delete(t.id)
                            else next.add(t.id)
                            setSelectedTools(next)
                          }}
                          className={cn(
                            'w-full flex items-center justify-between px-2 h-6 text-[10px] transition-colors',
                            !isCompatible && 'opacity-40 cursor-not-allowed',
                            isCompatible &&
                              (isSelected
                                ? 'bg-accent/20 text-accent'
                                : 'hover:bg-muted/30 text-muted-foreground')
                          )}
                        >
                          <span className="flex items-center gap-2">
                            <span
                              className={cn(
                                'w-1.5 h-1.5 rounded-full',
                                t.enabled ? 'bg-low' : 'bg-dim'
                              )}
                            />
                            {t.name}
                          </span>
                          <span
                            className={cn(
                              'uppercase text-[9px]',
                              !isCompatible ? 'text-muted-foreground font-bold' : 'text-dim'
                            )}
                          >
                            {t.segment}
                          </span>
                        </button>
                      )
                    })
                  )}
                </div>
                <div className="text-[10px] text-dim mt-1">
                  Leave empty to run all enabled tools
                </div>
                {selectedDomains.size > 0 && (
                  <div className="text-[10px] text-muted-foreground mt-1">
                    {configuredTools.length - compatibleToolIds.size} tool(s) disabled by domain
                    filter
                  </div>
                )}
              </div>

              {/* Skip tools multi-select */}
              <div>
                <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
                  Skip These Tools {skipTools.size > 0 && `(${skipTools.size} selected)`}
                </div>
                <div className="max-h-24 overflow-y-auto border border-border bg-background p-2 space-y-1">
                  {configuredTools.length === 0 ? (
                    <div className="text-[10px] text-dim">No tools configured</div>
                  ) : (
                    configuredTools
                      .filter(t => t.enabled)
                      .map(t => {
                        const isSelected = skipTools.has(t.id)
                        const isCompatible = compatibleToolIds.has(t.id)
                        return (
                          <button
                            key={t.id}
                            disabled={!isCompatible}
                            onClick={() => {
                              const next = new Set(skipTools)
                              if (isSelected) next.delete(t.id)
                              else next.add(t.id)
                              setSkipTools(next)
                            }}
                            className={cn(
                              'w-full flex items-center justify-between px-2 h-6 text-[10px] transition-colors',
                              !isCompatible && 'opacity-40 cursor-not-allowed',
                              isCompatible &&
                                (isSelected
                                  ? 'bg-crit/20 text-crit'
                                  : 'hover:bg-muted/30 text-muted-foreground')
                            )}
                          >
                            <span>{t.name}</span>
                            <span
                              className={cn(
                                'uppercase text-[9px]',
                                !isCompatible ? 'text-muted-foreground font-bold' : 'text-dim'
                              )}
                            >
                              {t.segment}
                            </span>
                          </button>
                        )
                      })
                  )}
                </div>
                <div className="text-[10px] text-dim mt-1">
                  Exclude tools from an otherwise full scan
                </div>
                {selectedDomains.size > 0 && (
                  <div className="text-[10px] text-muted-foreground mt-1">
                    {configuredTools.filter(t => t.enabled && !compatibleToolIds.has(t.id)).length}{' '}
                    tool(s) disabled by domain filter
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tabs: Live / History / Saved Scans */}
      <div className="flex items-stretch border-b border-border shrink-0">
        {(['live', 'history', 'saved'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={cn(
              'px-4 h-9 text-xs font-bold uppercase tracking-[0.2em] border-b-2 transition-colors',
              activeTab === tab
                ? 'text-accent border-accent'
                : 'text-muted-foreground border-transparent hover:text-foreground'
            )}
          >
            {tab === 'live' ? 'Live Log' : tab === 'history' ? 'History' : 'Saved Scans'}
          </button>
        ))}
      </div>

      {/* Content area */}
      {activeTab === 'live' && (
        <Panel
          title="scan log"
          className="flex-1 min-h-[400px]"
          bodyClassName="overflow-auto bg-background"
        >
          {logs.length === 0 && runStatus === 'idle' ? (
            <div className="flex flex-col items-center justify-center h-full gap-4 text-muted-foreground">
              <Terminal className="h-12 w-12 text-dim" />
              <div className="text-sm">
                No active scan. Press <span className="text-accent font-bold">Start Scan</span> to
                begin.
              </div>
              <div className="text-xs text-dim max-w-md text-center">
                The scan will iterate through each segment (SAST, SCA, WEB, SECRETS), run configured
                tools against each repository, and stream results here in real time.
              </div>
            </div>
          ) : (
            <div className="py-2">
              {logs.map(event => (
                <LogRow key={event.id} event={event} />
              ))}
              {enrichmentProgress && runId !== null && (
                <LogRow
                  key="_live_enrichment"
                  event={{
                    id: '_live_enrichment',
                    runId,
                    type: 'enrichment_progress',
                    timestamp: enrichmentProgress.timestamp,
                    message: `Enriching findings... ${enrichmentProgress.enrichedCount}/${enrichmentProgress.totalToEnrich}`,
                  }}
                />
              )}
              <div ref={logEndRef} />
            </div>
          )}
        </Panel>
      )}

      {activeTab === 'history' && (
        <Panel title="scan history" className="flex-1 min-h-[400px]" bodyClassName="flex flex-col">
          <HistoryTable projectId={projectIdNum} />
        </Panel>
      )}

      {activeTab === 'saved' && (
        <SavedScansTab
          projectId={projectIdNum}
          savedScans={savedScans}
          configuredRepos={configuredRepos}
          configuredTools={configuredTools}
          toolArgProfiles={toolArgProfiles}
          configuredSegments={configuredDomains}
          onSave={(scan, isNew) => saveScan.mutate({ scan, isNew })}
          onDelete={scanId => deleteSavedScan.mutate({ projectId: projectIdNum, scanId })}
          onSelect={scanId => {
            // CLIENT-SIDE MOCK: "Run This" stages the saved scan in the
            // status bar; it does NOT trigger a real scan run. The plain
            // Start Scan button continues to use ad-hoc options against
            // the real backend.
            setSelectedSavedScanId(scanId)
            setActiveTab('live')
          }}
          isSaving={saveScan.isPending}
        />
      )}
    </div>
  )
}
