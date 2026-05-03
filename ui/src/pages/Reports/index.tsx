import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Play, Square, RotateCcw, AlertTriangle, Loader2, RefreshCw, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Panel, Bar } from '@/components/tty'
import { useUI } from '@/lib/store'
import {
  useProjects,
  useReportDrafts,
  useReportHistory,
  useGenerateDrafts,
  useUploadDraft,
  useDeleteDraft,
  useGenerateReport,
  useCancelReport,
  useReportEvents,
  useReportDraftEvents,
} from '@/lib/api'
import type {
  ReportFormat,
  TestingType,
  ReportDraftSection,
  ReportLogEvent,
  ReportGenerationStatus,
} from '@/lib/types'
import { ReportMutationErrorModal } from '@/components/ReportMutationErrorModal'
import { NoProjectSelectedState } from '@/components/NoProjectSelectedState'
import { SECTION_ORDER, FORMAT_OPTIONS, TESTING_TYPE_OPTIONS } from './constants'
import { PrinterAnimation } from './PrinterAnimation'
import { DraftCard } from './DraftCard'
import { HistoryTable } from './HistoryTable'
import { LogRow } from './LogRow'
import { PreflightChecklist } from './PreflightChecklist'

// ─── Reports Page ─────────────────────────────────────────────────────────────

export default function Reports() {
  const activeProjectId = useUI(s => s.activeProjectId)
  const queryClient = useQueryClient()

  const { data: projects = [] } = useProjects()
  const { data: draftData = [] } = useReportDrafts(activeProjectId)
  const { data: historyData = [] } = useReportHistory(activeProjectId)
  const generateDrafts = useGenerateDrafts()
  const uploadDraft = useUploadDraft()
  const deleteDraft = useDeleteDraft()
  const generateReport = useGenerateReport()
  const cancelReport = useCancelReport()

  const project = projects.find(p => p.id === activeProjectId)

  // Generation form state
  const [format, setFormat] = useState<ReportFormat>('pdf')
  const [testingType, setTestingType] = useState<TestingType>('grey_box')
  const [companyName, setCompanyName] = useState('')
  const [engagementDate, setEngagementDate] = useState(new Date().toISOString().split('T')[0])
  const [skipTriage, setSkipTriage] = useState(false)
  const [showPreflight, setShowPreflight] = useState(false)
  const [showTalWarning, setShowTalWarning] = useState(true)

  // Generation run state - driven by the real SSE stream once a run starts.
  const [runId, setRunId] = useState<number | null>(null)
  const [generationStatus, setGenerationStatus] = useState<ReportGenerationStatus>('idle')
  const [progress, setProgress] = useState(0)
  const [logs, setLogs] = useState<ReportLogEvent[]>([])
  const logContainerRef = useRef<HTMLDivElement>(null)

  // Sections backfilled with `not_generated` so the UI always renders 6 cards
  // even before the first hook resolution.
  const drafts = useMemo(() => {
    const bySection = new Map(draftData.map(d => [d.section, d]))
    return SECTION_ORDER.map(
      section => bySection.get(section) ?? { section, status: 'not_generated' as const }
    )
  }, [draftData])

  const draftCount = drafts.filter(d => d.status === 'draft' || d.status === 'reviewed').length
  const reviewedCount = drafts.filter(d => d.status === 'reviewed').length
  const allDraftsReady = draftCount === SECTION_ORDER.length

  const selectedFormat = FORMAT_OPTIONS.find(f => f.value === format) ?? FORMAT_OPTIONS[0]
  const canGenerate = selectedFormat.requiresDrafts ? allDraftsReady : true

  // Sections currently included in an in-flight POST. The first one is
  // generating; the rest are queued. The SSE stream flips per-section state
  // once each finishes, so we use this only to drive the per-card spinner.
  const generatingSections: ReadonlySet<ReportDraftSection> = useMemo(() => {
    if (!generateDrafts.isPending || !generateDrafts.variables) return new Set()
    return new Set(generateDrafts.variables.sections)
  }, [generateDrafts.isPending, generateDrafts.variables])

  // Auto-scroll logs
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }, [logs])

  const appendEvent = useCallback(
    (event: ReportLogEvent) => {
      setLogs(prev => [...prev, event])
      if (event.type === 'step_completed' && typeof event.progress === 'number') {
        setProgress(event.progress)
      }
      if (event.type === 'generation_started') {
        setGenerationStatus('generating')
      }
      if (event.type === 'generation_completed') {
        setGenerationStatus('completed')
        setProgress(100)
      }
      if (event.type === 'generation_failed') {
        setGenerationStatus('failed')
      }
      if (
        event.type === 'draft_started' ||
        event.type === 'draft_completed' ||
        event.type === 'draft_failed'
      ) {
        queryClient.invalidateQueries({
          queryKey: ['reports', activeProjectId, 'drafts'],
        })
      }
    },
    [activeProjectId, queryClient]
  )

  // Full-report SSE - only subscribe while we actually have a run in flight.
  useReportEvents(activeProjectId, appendEvent, {
    enabled: runId !== null,
    runId,
  })

  // Draft SSE - always-on while a project is selected so per-section
  // generations triggered from any card surface their lifecycle in the log.
  useReportDraftEvents(activeProjectId, appendEvent)

  const handleGenerateDraft = useCallback(
    (section: ReportDraftSection, force: boolean) => {
      if (activeProjectId === null) return
      generateDrafts.mutate({
        projectId: activeProjectId,
        sections: [section],
        force,
        skipTriage,
      })
    },
    [activeProjectId, generateDrafts, skipTriage]
  )

  const handleGenerateAll = useCallback(
    (force: boolean) => {
      if (activeProjectId === null) return
      const sections = force
        ? [...SECTION_ORDER]
        : SECTION_ORDER.filter(s => {
            const d = drafts.find(dr => dr.section === s)
            return !d || d.status === 'not_generated' || d.status === 'failed'
          })
      if (sections.length === 0) return
      generateDrafts.mutate({
        projectId: activeProjectId,
        sections,
        force,
        skipTriage,
      })
    },
    [activeProjectId, drafts, generateDrafts, skipTriage]
  )

  const handleUpload = useCallback(
    (section: ReportDraftSection, file: File) => {
      if (activeProjectId === null) return
      uploadDraft.mutate({ projectId: activeProjectId, section, file })
    },
    [activeProjectId, uploadDraft]
  )

  const handleDelete = useCallback(
    (section: ReportDraftSection) => {
      if (activeProjectId === null) return
      deleteDraft.mutate({ projectId: activeProjectId, section })
    },
    [activeProjectId, deleteDraft]
  )

  const handleStartGeneration = useCallback(async () => {
    if (activeProjectId === null) return
    if (format === 'pdf' && !allDraftsReady) {
      setShowPreflight(true)
      return
    }
    setLogs([])
    setProgress(0)
    setGenerationStatus('generating')
    try {
      const run = await generateReport.mutateAsync({
        projectId: activeProjectId,
        format,
        testingType: format === 'pdf' ? testingType : undefined,
        engagementDate,
        companyName: companyName || undefined,
        skipTriage,
      })
      setRunId(run.id)
    } catch {
      setGenerationStatus('failed')
      setRunId(null)
    }
  }, [
    activeProjectId,
    format,
    allDraftsReady,
    testingType,
    engagementDate,
    companyName,
    skipTriage,
    generateReport,
  ])

  const handleStopGeneration = useCallback(() => {
    if (activeProjectId === null || runId === null) return
    cancelReport.mutate({ projectId: activeProjectId, reportId: runId })
  }, [activeProjectId, runId, cancelReport])

  const handleReset = useCallback(() => {
    setGenerationStatus('idle')
    setProgress(0)
    setRunId(null)
    setLogs([])
  }, [])

  if (activeProjectId === null) {
    return <NoProjectSelectedState projects={projects} />
  }

  const isRunning = generationStatus === 'generating'

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-border">
        <div className="flex items-center gap-6">
          <h1 className="text-lg font-bold tracking-wide">
            <span className="text-accent">[</span>
            <span className="px-1">REPORTS</span>
            <span className="text-accent">]</span>
          </h1>
          <span className="text-sm text-muted-foreground">
            {project?.name} / {draftCount} of {SECTION_ORDER.length} sections ready
            {reviewedCount > 0 && <span className="text-good"> ({reviewedCount} reviewed)</span>}
          </span>
        </div>
      </div>

      {/* TAL ID Warning */}
      {showTalWarning && (
        <div className="mx-6 mt-4 flex items-start gap-2 px-3 py-2 border border-warn/50 bg-warn/10 text-warn text-[11px]">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
          <span className="flex-1">
            Generating a new PDF report will re-assign TAL IDs to all approved findings. If you have
            shared a previous report, IDs may change.
          </span>
          <button
            onClick={() => setShowTalWarning(false)}
            className="shrink-0 p-0.5 hover:bg-warn/20 transition-colors"
            title="Dismiss"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Content - Graphic on LEFT, controls on RIGHT */}
      <div className="flex-1 overflow-auto p-6">
        <div className="flex gap-8">
          {/* Left: Animated Graphic + Status */}
          <div className="shrink-0 flex flex-col items-center gap-4">
            <PrinterAnimation active={isRunning} progress={progress} size={220} />

            {/* Status indicator */}
            <div className="text-center">
              <div
                className={cn(
                  'text-[11px] uppercase tracking-wider font-bold',
                  generationStatus === 'idle' && 'text-dim',
                  generationStatus === 'generating' && 'text-warn',
                  generationStatus === 'completed' && 'text-good',
                  generationStatus === 'failed' && 'text-crit'
                )}
              >
                {generationStatus === 'idle' && 'Ready'}
                {generationStatus === 'generating' && 'Generating...'}
                {generationStatus === 'completed' && 'Complete'}
                {generationStatus === 'failed' && 'Failed'}
              </div>

              {isRunning && (
                <div className="mt-2 w-48">
                  <Bar value={progress} max={100} />
                  <span className="text-[10px] tabular-nums text-accent">{progress}%</span>
                </div>
              )}
            </div>

            {/* Controls */}
            <div className="flex items-center gap-2">
              {generationStatus === 'idle' && (
                <button
                  onClick={handleStartGeneration}
                  disabled={
                    activeProjectId === null ||
                    generateReport.isPending ||
                    (!canGenerate && format === 'pdf')
                  }
                  data-testid="report-generate-button"
                  className={cn(
                    'flex items-center gap-2 px-4 py-2 text-sm font-bold uppercase tracking-wider transition-colors',
                    canGenerate || format !== 'pdf'
                      ? 'bg-accent text-background hover:bg-accent/90'
                      : 'bg-muted text-dim cursor-not-allowed'
                  )}
                >
                  <Play className="h-4 w-4" />
                  Generate
                </button>
              )}
              {isRunning && (
                <button
                  onClick={handleStopGeneration}
                  disabled={cancelReport.isPending || runId === null}
                  data-testid="report-stop-button"
                  className="flex items-center gap-2 px-4 py-2 bg-crit text-background text-sm font-bold uppercase tracking-wider hover:bg-crit/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Square className="h-4 w-4" />
                  Stop
                </button>
              )}
              {(generationStatus === 'completed' || generationStatus === 'failed') && (
                <button
                  onClick={handleReset}
                  data-testid="report-reset-button"
                  className="flex items-center gap-2 px-4 py-2 border border-border text-muted-foreground text-sm font-bold uppercase tracking-wider hover:bg-muted/30 transition-colors"
                >
                  <RotateCcw className="h-4 w-4" />
                  Reset
                </button>
              )}
            </div>
          </div>

          {/* Right: Form + Drafts + Logs */}
          <div className="flex-1 min-w-0 space-y-6">
            {/* Report Options */}
            <Panel title="Report Options">
              <div className="p-4 space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  {/* Format */}
                  <div className="space-y-1">
                    <label
                      htmlFor="report-format"
                      className="text-[10px] uppercase tracking-wider text-dim"
                    >
                      Format
                    </label>
                    <select
                      id="report-format"
                      value={format}
                      onChange={e => setFormat(e.target.value as ReportFormat)}
                      disabled={isRunning}
                      data-testid="report-format-select"
                      className="w-full bg-muted border border-border px-3 py-2 text-sm focus:outline-none focus:border-accent disabled:opacity-50"
                    >
                      {FORMAT_OPTIONS.map(opt => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label} {opt.requiresDrafts ? '(requires drafts)' : '(direct)'}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Testing Type (PDF only) */}
                  <div className="space-y-1">
                    <label
                      htmlFor="report-testing-type"
                      className="text-[10px] uppercase tracking-wider text-dim"
                    >
                      Testing Type
                    </label>
                    <select
                      id="report-testing-type"
                      value={testingType}
                      onChange={e => setTestingType(e.target.value as TestingType)}
                      disabled={isRunning || format !== 'pdf'}
                      data-testid="report-testing-type-select"
                      className="w-full bg-muted border border-border px-3 py-2 text-sm focus:outline-none focus:border-accent disabled:opacity-50"
                    >
                      {TESTING_TYPE_OPTIONS.map(opt => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Company Name */}
                  <div className="space-y-1">
                    <label
                      htmlFor="report-company-name"
                      className="text-[10px] uppercase tracking-wider text-dim"
                    >
                      Company Name
                    </label>
                    <input
                      id="report-company-name"
                      type="text"
                      value={companyName}
                      onChange={e => setCompanyName(e.target.value)}
                      disabled={isRunning}
                      data-testid="report-company-name-input"
                      placeholder="e.g. ACME Corporation"
                      className="w-full bg-muted border border-border px-3 py-2 text-sm focus:outline-none focus:border-accent disabled:opacity-50 placeholder:text-dim"
                    />
                  </div>

                  {/* Engagement Date */}
                  <div className="space-y-1">
                    <label
                      htmlFor="report-engagement-date"
                      className="text-[10px] uppercase tracking-wider text-dim"
                    >
                      Engagement Date
                    </label>
                    <input
                      id="report-engagement-date"
                      type="date"
                      value={engagementDate}
                      onChange={e => setEngagementDate(e.target.value)}
                      disabled={isRunning}
                      data-testid="report-engagement-date-input"
                      className="w-full bg-muted border border-border px-3 py-2 text-sm focus:outline-none focus:border-accent disabled:opacity-50"
                    />
                  </div>
                </div>

                {/* Skip triage toggle */}
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={skipTriage}
                    onChange={e => setSkipTriage(e.target.checked)}
                    disabled={isRunning}
                    data-testid="report-skip-triage-checkbox"
                    className="accent-accent"
                  />
                  <span className="text-sm text-muted-foreground">
                    Skip triage filter (include all findings, not just triaged/reportable)
                  </span>
                </label>

                {/* Format-specific note */}
                {format === 'pdf' && !allDraftsReady && (
                  <div className="flex items-center gap-2 text-[11px] text-warn">
                    <AlertTriangle className="h-3 w-3" />
                    <span>
                      PDF requires all {SECTION_ORDER.length} draft sections.{' '}
                      {SECTION_ORDER.length - draftCount} section(s) still needed.
                    </span>
                  </div>
                )}
              </div>
            </Panel>

            {/* Draft Sections */}
            <Panel
              title="Draft Sections"
              right={
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleGenerateAll(false)}
                    disabled={
                      generateDrafts.isPending || allDraftsReady || activeProjectId === null
                    }
                    data-testid="report-generate-missing-button"
                    className="px-2 py-1 text-[10px] uppercase tracking-wider border border-accent text-accent hover:bg-accent hover:text-background transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {generateDrafts.isPending ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      'Generate Missing'
                    )}
                  </button>
                  <button
                    onClick={() => handleGenerateAll(true)}
                    disabled={generateDrafts.isPending || activeProjectId === null}
                    data-testid="report-regenerate-all-button"
                    className="px-2 py-1 text-[10px] uppercase tracking-wider border border-warn text-warn hover:bg-warn hover:text-background transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    title="Regenerate all (overwrites existing)"
                  >
                    <RefreshCw className="h-3 w-3" />
                  </button>
                </div>
              }
            >
              <div className="divide-y divide-border">
                {drafts.map(draft => (
                  <DraftCard
                    key={draft.section}
                    projectId={activeProjectId ?? 0}
                    draft={draft}
                    onGenerate={force => handleGenerateDraft(draft.section, force)}
                    onUpload={file => handleUpload(draft.section, file)}
                    onDelete={() => handleDelete(draft.section)}
                    isGenerating={generatingSections.has(draft.section)}
                    skipTriage={skipTriage}
                  />
                ))}
              </div>
            </Panel>

            {/* Log stream */}
            {logs.length > 0 && (
              <Panel title="Generation Log">
                <div
                  ref={logContainerRef}
                  className="max-h-48 overflow-y-auto divide-y divide-border/50"
                >
                  {logs.map(event => (
                    <LogRow key={event.id} event={event} />
                  ))}
                </div>
              </Panel>
            )}

            {/* History */}
            <Panel title="Report History">
              <div className="p-4">
                <HistoryTable projectId={activeProjectId ?? 0} entries={historyData} />
              </div>
            </Panel>
          </div>
        </div>
      </div>

      {/* Preflight Modal */}
      {showPreflight && (
        <PreflightChecklist
          drafts={drafts}
          onClose={() => setShowPreflight(false)}
          onConfirm={() => {
            setShowPreflight(false)
            void handleStartGeneration()
          }}
        />
      )}

      <ReportMutationErrorModal />
    </div>
  )
}
