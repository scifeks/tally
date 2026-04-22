import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { Play, Square, RotateCcw, Settings2, Terminal, Check } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Panel } from '@/components/tty'
import { useUI } from '@/lib/store'
import {
  useProjects,
  useProjectMeta,
  useScanHistory,
  useProjectScanConfig,
  useStartScan,
  useCancelScan,
} from '@/lib/api'
import type {
  Segment,
  ScanLogEvent,
  ScanLogEventType,
  ScanRunStatus,
  ScanOptions,
} from '@/lib/types'
import { RadarSweep } from './RadarSweep'
import { LogRow } from './LogRow'
import { HistoryTable } from './HistoryTable'

const SEGMENT_LABEL: Record<Segment, string> = {
  sast: 'SAST',
  sca: 'SCA',
  web: 'WEB',
  secrets: 'SECRETS',
}

export default function Scans() {
  const activeProjectId = useUI(s => s.activeProjectId)

  // TODO [BACKEND]: These hooks return mock data. Replace with real API calls.
  // GET /api/v1/projects
  const { data: projects = [] } = useProjects()
  // GET /api/v1/projects/:id/meta
  const { data: projectMetaData } = useProjectMeta(activeProjectId)
  // GET /api/v1/projects/:id/scans (history)
  void useScanHistory(activeProjectId)

  // TODO [BACKEND]: Scan configuration (repos, tools, domains) from server.
  // GET /api/v1/projects/:id/scans/config
  const { data: scanConfig } = useProjectScanConfig(activeProjectId)

  // TODO [BACKEND]: These mutations trigger server actions.
  // POST /api/v1/projects/:id/scans/start
  const { mutate: startScanMutation } = useStartScan()
  // POST /api/v1/scans/:id/cancel
  const { mutate: cancelScanMutation } = useCancelScan()

  void startScanMutation
  void cancelScanMutation

  const project = projects.find(p => p.id === activeProjectId)
  const meta = projectMetaData

  // Derived config data — memoized to avoid new array refs on every render
  const configuredRepos = useMemo(() => scanConfig?.repos ?? [], [scanConfig])
  const configuredTools = useMemo(() => scanConfig?.tools ?? [], [scanConfig])
  const configuredDomains = useMemo(() => scanConfig?.segments ?? [], [scanConfig])

  // Group tools by domain for display
  const toolsByDomain = useMemo(() => {
    const map: Record<Segment, typeof configuredTools> = { sast: [], sca: [], web: [], secrets: [] }
    configuredTools.forEach(t => {
      if (map[t.segment]) map[t.segment].push(t)
    })
    return map
  }, [configuredTools])

  // Scan run state
  const [runStatus, setRunStatus] = useState<ScanRunStatus>('idle')
  const [logs, setLogs] = useState<ScanLogEvent[]>([])
  const [elapsedSec, setElapsedSec] = useState(0)
  const [expandedSegments, setExpandedSegments] = useState<Set<Segment>>(new Set(configuredDomains))

  // Advanced options state
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [selectedRepos, setSelectedRepos] = useState<Set<string>>(new Set()) // empty = all repos
  const [selectedDomains, setSelectedDomains] = useState<Set<Segment>>(new Set())
  const [selectedTools, setSelectedTools] = useState<Set<string>>(new Set())
  const [skipTools, setSkipTools] = useState<Set<string>>(new Set())
  const [skipEnrichment, setSkipEnrichment] = useState(false)

  void expandedSegments
  void setExpandedSegments

  // Reset advanced options when config changes
  useEffect(() => {
    setSelectedRepos(new Set())
    setSelectedDomains(new Set())
    setSelectedTools(new Set())
    setSkipTools(new Set())
    setSkipEnrichment(false)
  }, [activeProjectId])

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

  // Check if any advanced options are set
  const hasAdvancedOptions =
    selectedRepos.size > 0 ||
    selectedDomains.size > 0 ||
    selectedTools.size > 0 ||
    skipTools.size > 0 ||
    skipEnrichment

  // For simulating log stream
  const eventQueueRef = useRef<ScanLogEvent[]>([])
  const eventIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const logEndRef = useRef<HTMLDivElement>(null)

  const [activeTab, setActiveTab] = useState<'live' | 'history'>('live')

  // Generate fake scan log events
  const generateEvents = useCallback((): ScanLogEvent[] => {
    const events: ScanLogEvent[] = []
    const runId = `R-${Date.now()}`
    let ts = Date.now()
    const addEvent = (type: ScanLogEventType, msg: string, extra?: Partial<ScanLogEvent>) => {
      events.push({
        id: `E-${ts}`,
        runId,
        type,
        timestamp: new Date(ts).toISOString(),
        message: msg,
        ...extra,
      })
      ts += Math.random() * 800 + 200
    }

    const opts = buildScanOptions()

    // Determine which repos/tools/domains to run based on options
    const repoIdsSet = new Set(opts.repoIds ?? [])
    const reposToScan =
      repoIdsSet.size > 0 ? configuredRepos.filter(r => repoIdsSet.has(r.id)) : configuredRepos
    const domainsToScan =
      opts.segments && opts.segments.length > 0 ? opts.segments : configuredDomains
    const toolIdsToRun = opts.toolIds && opts.toolIds.length > 0 ? new Set(opts.toolIds) : null // null = all tools
    const toolIdsToSkip = new Set(opts.skipToolIds ?? [])

    addEvent('run_started', `Scan started for project ${project?.name ?? activeProjectId}`)

    for (const segment of domainsToScan) {
      addEvent('segment_started', `${SEGMENT_LABEL[segment]}`, { segment })
      const toolsInSegment = toolsByDomain[segment] ?? []
      for (const repo of reposToScan) {
        for (const toolConfig of toolsInSegment) {
          // Skip if tool is in skip list
          if (toolIdsToSkip.has(toolConfig.id)) {
            addEvent('tool_skipped', `${toolConfig.name}/${repo.name} | SKIPPED (excluded)`, {
              segment,
              repo: repo.name,
              tool: toolConfig.name,
            })
            continue
          }
          // Skip if we have a specific tool list and this tool isn't in it
          if (toolIdsToRun && !toolIdsToRun.has(toolConfig.id)) {
            continue
          }
          // Skip disabled tools unless explicitly selected
          if (!toolConfig.enabled && !toolIdsToRun?.has(toolConfig.id)) {
            addEvent('tool_skipped', `${toolConfig.name}/${repo.name} | SKIPPED (disabled)`, {
              segment,
              repo: repo.name,
              tool: toolConfig.name,
            })
            continue
          }

          const skip = Math.random() < 0.2
          if (skip) {
            addEvent(
              'tool_skipped',
              `${toolConfig.name}/${repo.name} | SKIPPED (no manifest found)`,
              { segment, repo: repo.name, tool: toolConfig.name }
            )
          } else {
            addEvent('tool_started', `Running ${toolConfig.name} (${repo.name})...`, {
              segment,
              repo: repo.name,
              tool: toolConfig.name,
            })
            const duration = Math.random() * 25 + 1
            const findings = Math.floor(Math.random() * 50)
            const exitCode = Math.random() < 0.05 ? 1 : 0
            if (exitCode === 0) {
              addEvent('tool_completed', `Complete (exit 0, ${duration.toFixed(1)}s)`, {
                segment,
                repo: repo.name,
                tool: toolConfig.name,
                duration,
                exitCode: 0,
              })
              if (findings > 0 && !opts.skipEnrichment) {
                const total = findings
                for (let i = 0; i < 3; i++) {
                  const enriched = Math.min(total, Math.floor((i + 1) * (total / 3)))
                  addEvent('enrichment_progress', `Enriching findings... ${enriched}/${total}`, {
                    segment,
                    repo: repo.name,
                    tool: toolConfig.name,
                    enrichedCount: enriched,
                    totalToEnrich: total,
                  })
                }
                addEvent(
                  'enrichment_complete',
                  `Enrichment complete. ${total}/${total} findings enriched.`,
                  {
                    segment,
                    repo: repo.name,
                    tool: toolConfig.name,
                    findingsCount: total,
                  }
                )
              }
              addEvent(
                'tool_completed',
                `${toolConfig.name}/${repo.name.padEnd(14)} | ${findings} findings | ${duration.toFixed(1)}s`,
                {
                  segment,
                  repo: repo.name,
                  tool: toolConfig.name,
                  duration,
                  findingsCount: findings,
                }
              )
            } else {
              addEvent(
                'tool_failed',
                `${toolConfig.name}/${repo.name} | FAILED (exit ${exitCode})`,
                {
                  segment,
                  repo: repo.name,
                  tool: toolConfig.name,
                  exitCode,
                }
              )
            }
          }
        }
      }
      addEvent('segment_completed', `${SEGMENT_LABEL[segment]} complete`, { segment })
    }

    addEvent('run_completed', 'Scan completed successfully')
    return events
  }, [
    activeProjectId,
    project?.name,
    configuredRepos,
    configuredDomains,
    toolsByDomain,
    buildScanOptions,
  ])

  // Start scan
  const startScan = useCallback(() => {
    setRunStatus('running')
    setLogs([])
    setElapsedSec(0)
    setActiveTab('live')
    eventQueueRef.current = generateEvents()

    // Elapsed timer
    timerRef.current = setInterval(() => setElapsedSec(s => s + 1), 1000)

    // Stream events
    eventIntervalRef.current = setInterval(() => {
      if (eventQueueRef.current.length === 0) {
        // Done
        if (eventIntervalRef.current) clearInterval(eventIntervalRef.current)
        if (timerRef.current) clearInterval(timerRef.current)
        setRunStatus('completed')
        return
      }
      const next = eventQueueRef.current.shift()
      if (next) setLogs(prev => [...prev, next])
    }, 120)
  }, [generateEvents])

  // Stop scan
  const stopScan = useCallback(() => {
    if (eventIntervalRef.current) clearInterval(eventIntervalRef.current)
    if (timerRef.current) clearInterval(timerRef.current)
    eventQueueRef.current = []
    setLogs(prev => [
      ...prev,
      {
        id: `E-cancel-${Date.now()}`,
        runId: '',
        type: 'run_cancelled',
        timestamp: new Date().toISOString(),
        message: 'Scan cancelled by user',
      },
    ])
    setRunStatus('cancelled')
  }, [])

  // Reset
  const resetScan = useCallback(() => {
    setRunStatus('idle')
    setLogs([])
    setElapsedSec(0)
  }, [])

  // Auto-scroll log
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (eventIntervalRef.current) clearInterval(eventIntervalRef.current)
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [])

  const formatElapsed = (sec: number) => {
    const m = Math.floor(sec / 60)
    const s = sec % 60
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  const isRunning = runStatus === 'running'
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
    <div className="h-full flex flex-col min-h-0 p-4 gap-4">
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
              {meta?.repositories ?? 0} repos &middot; {meta?.enabledTools ?? 0} tools
            </span>
          </div>

          {/* Status */}
          <div className="flex items-center gap-4">
            <span className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
              <span className="text-accent">[</span> STATUS <span className="text-accent">]</span>
            </span>
            <span
              className={cn(
                'text-sm font-bold uppercase tracking-wider',
                runStatus === 'running' && 'text-high animate-pulse',
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
          </div>

          {/* Buttons */}
          <div className="flex items-center gap-3">
            {canStart && (
              <button
                onClick={startScan}
                className="flex items-center gap-2 px-4 h-9 bg-accent text-background font-bold text-xs uppercase tracking-wider hover:bg-accent/80 transition-colors"
              >
                <Play className="h-4 w-4" />
                Start Scan
              </button>
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
                className="flex items-center gap-2 px-4 h-9 border border-crit text-crit font-bold text-xs uppercase tracking-wider hover:bg-crit/10 transition-colors"
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
                      return (
                        <button
                          key={t.id}
                          onClick={() => {
                            const next = new Set(selectedTools)
                            if (isSelected) next.delete(t.id)
                            else next.add(t.id)
                            setSelectedTools(next)
                          }}
                          className={cn(
                            'w-full flex items-center justify-between px-2 h-6 text-[10px] transition-colors',
                            isSelected
                              ? 'bg-accent/20 text-accent'
                              : 'hover:bg-muted/30 text-muted-foreground'
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
                          <span className="uppercase text-[9px] text-dim">{t.segment}</span>
                        </button>
                      )
                    })
                  )}
                </div>
                <div className="text-[10px] text-dim mt-1">
                  Leave empty to run all enabled tools
                </div>
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
                        return (
                          <button
                            key={t.id}
                            onClick={() => {
                              const next = new Set(skipTools)
                              if (isSelected) next.delete(t.id)
                              else next.add(t.id)
                              setSkipTools(next)
                            }}
                            className={cn(
                              'w-full flex items-center justify-between px-2 h-6 text-[10px] transition-colors',
                              isSelected
                                ? 'bg-crit/20 text-crit'
                                : 'hover:bg-muted/30 text-muted-foreground'
                            )}
                          >
                            <span>{t.name}</span>
                            <span className="uppercase text-[9px] text-dim">{t.segment}</span>
                          </button>
                        )
                      })
                  )}
                </div>
                <div className="text-[10px] text-dim mt-1">
                  Exclude tools from an otherwise full scan
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tabs: Live / History */}
      <div className="flex items-stretch border-b border-border shrink-0">
        {(['live', 'history'] as const).map(tab => (
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
            {tab === 'live' ? 'Live Log' : 'History'}
          </button>
        ))}
      </div>

      {/* Content area */}
      {activeTab === 'live' ? (
        <Panel
          title="scan log"
          className="flex-1 min-h-0"
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
              <div ref={logEndRef} />
            </div>
          )}
        </Panel>
      ) : (
        <Panel title="scan history" className="flex-1 min-h-0" bodyClassName="flex flex-col">
          <HistoryTable projectId={activeProjectId} />
        </Panel>
      )}
    </div>
  )
}
