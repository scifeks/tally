import { useState, useEffect, useRef, useCallback } from 'react'
import { Play, Square, RotateCcw, AlertTriangle, Loader2, RefreshCw, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Panel, Bar } from '@/components/tty'
import { useUI } from '@/lib/store'
import {
  useProjects,
  useReportDrafts,
  useReportHistory,
  useGenerateDraft,
  useGenerateReport,
} from '@/lib/api'
import type {
  ReportFormat,
  TestingType,
  ReportDraftSection,
  ReportDraft,
  ReportLogEvent,
  ReportGenerationStatus,
  ReportHistoryEntry,
  ReportDraftStatus,
} from '@/lib/types'
import { SECTION_ORDER, SECTION_LABELS, FORMAT_OPTIONS, TESTING_TYPE_OPTIONS } from './constants'
import { PrinterAnimation } from './PrinterAnimation'
import { DraftCard } from './DraftCard'
import { HistoryTable } from './HistoryTable'
import { LogRow } from './LogRow'
import { PreflightChecklist } from './PreflightChecklist'

// ─── Reports Page ─────────────────────────────────────────────────────────────

export default function Reports() {
  const activeProjectId = useUI(s => s.activeProjectId)

  const projectIdParam = activeProjectId !== null ? String(activeProjectId) : null

  // TODO [BACKEND]: These hooks return mock data. Replace with real API calls.
  // GET /api/v1/projects
  const { data: projects = [] } = useProjects()
  // GET /api/v1/projects/:id/reports/drafts
  const { data: draftData } = useReportDrafts(projectIdParam)
  // GET /api/v1/projects/:id/reports (history)
  const { data: historyData = [] } = useReportHistory(projectIdParam)

  // TODO [BACKEND]: These mutations trigger server actions.
  // POST /api/v1/projects/:id/reports/drafts
  const { generate: generateDraftMutation, isLoading: isGeneratingDraft } = useGenerateDraft()
  // POST /api/v1/projects/:id/reports/generate
  const { generate: generateReportMutation, isLoading: isGeneratingReport } = useGenerateReport()

  // Suppress unused warnings — hooks are wired for future backend integration
  void draftData
  void historyData
  void generateDraftMutation
  void isGeneratingDraft
  void generateReportMutation
  void isGeneratingReport

  const project = projects.find(p => p.id === activeProjectId)

  // Generation form state
  const [format, setFormat] = useState<ReportFormat>('pdf')
  const [testingType, setTestingType] = useState<TestingType>('grey_box')
  const [companyName, setCompanyName] = useState('')
  const [engagementDate, setEngagementDate] = useState(new Date().toISOString().split('T')[0])
  const [skipTriage, setSkipTriage] = useState(false)
  const [showPreflight, setShowPreflight] = useState(false)
  const [showTalWarning, setShowTalWarning] = useState(true)

  // Generation run state
  const [runId, setRunId] = useState<string | null>(null)
  const [generationStatus, setGenerationStatus] = useState<ReportGenerationStatus>('idle')
  const [progress, setProgress] = useState(0)
  const [logs, setLogs] = useState<ReportLogEvent[]>([])
  const logContainerRef = useRef<HTMLDivElement>(null)

  // Draft generation state
  const [generatingSection, setGeneratingSection] = useState<ReportDraftSection | null>(null)
  const [generatingAll, setGeneratingAll] = useState(false)

  // Mock draft data - in real app, this comes from useReportDrafts hook
  const [drafts, setDrafts] = useState<ReportDraft[]>(() =>
    SECTION_ORDER.map(section => ({
      section,
      status:
        activeProjectId === 1
          ? section === 'executive_summary' || section === 'risk_level'
            ? 'draft'
            : 'not_generated'
          : 'not_generated',
      generatedAt:
        activeProjectId === 1 && (section === 'executive_summary' || section === 'risk_level')
          ? new Date(Date.now() - 86400000).toISOString()
          : undefined,
      preview:
        activeProjectId === 1 && (section === 'executive_summary' || section === 'risk_level')
          ? `# ${SECTION_LABELS[section]}\n\nThis is a preview of the generated content for the ${SECTION_LABELS[section].toLowerCase()} section. The full document contains detailed analysis based on the security findings from this engagement...`
          : undefined,
      wordCount:
        activeProjectId === 1 && (section === 'executive_summary' || section === 'risk_level')
          ? 450 + Math.floor(Math.random() * 200)
          : undefined,
    }))
  )

  // Mock history data
  const [history] = useState<ReportHistoryEntry[]>(() =>
    activeProjectId === 1
      ? [
          {
            id: 'rpt-001',
            projectId: '1',
            filename: 'ACME_Platform_Security_Assessment_2024-03-15.pdf',
            format: 'pdf',
            generatedAt: new Date(Date.now() - 7 * 86400000).toISOString(),
            sizeBytes: 2450000,
            downloadUrl: '#',
          },
          {
            id: 'rpt-002',
            projectId: '1',
            filename: 'ACME_Platform_Findings_Export.json',
            format: 'json',
            generatedAt: new Date(Date.now() - 14 * 86400000).toISOString(),
            sizeBytes: 156000,
            downloadUrl: '#',
          },
        ]
      : []
  )

  const draftCount = drafts.filter(d => d.status === 'draft' || d.status === 'reviewed').length
  const reviewedCount = drafts.filter(d => d.status === 'reviewed').length
  const allDraftsReady = draftCount === 6

  const selectedFormat = FORMAT_OPTIONS.find(f => f.value === format) ?? FORMAT_OPTIONS[0]
  const canGenerate = selectedFormat.requiresDrafts ? allDraftsReady : true

  // Auto-scroll logs
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }, [logs])

  const handleGenerateDraft = useCallback((section: ReportDraftSection, force: boolean) => {
    setGeneratingSection(section)
    setDrafts(prev =>
      prev.map(d =>
        d.section === section ? { ...d, status: 'generating' as ReportDraftStatus } : d
      )
    )
    setTimeout(
      () => {
        setDrafts(prev =>
          prev.map(d =>
            d.section === section
              ? {
                  ...d,
                  status: 'draft' as ReportDraftStatus,
                  generatedAt: new Date().toISOString(),
                  preview: `# ${SECTION_LABELS[section]}\n\nThis is a preview of the generated content for the ${SECTION_LABELS[section].toLowerCase()} section. The full document contains detailed analysis based on the security findings from this engagement...`,
                  wordCount: 450 + Math.floor(Math.random() * 200),
                }
              : d
          )
        )
        setGeneratingSection(null)
      },
      1500 + Math.random() * 1000
    )
    void force
  }, [])

  const handleGenerateAll = useCallback(
    async (force: boolean) => {
      setGeneratingAll(true)
      const toGenerate = force
        ? SECTION_ORDER
        : SECTION_ORDER.filter(s => {
            const d = drafts.find(dr => dr.section === s)
            return !d || d.status === 'not_generated' || d.status === 'failed'
          })

      for (const section of toGenerate) {
        await new Promise<void>(resolve => {
          setDrafts(prev =>
            prev.map(d =>
              d.section === section ? { ...d, status: 'generating' as ReportDraftStatus } : d
            )
          )
          setTimeout(
            () => {
              setDrafts(prev =>
                prev.map(d =>
                  d.section === section
                    ? {
                        ...d,
                        status: 'draft' as ReportDraftStatus,
                        generatedAt: new Date().toISOString(),
                        preview: `# ${SECTION_LABELS[section]}\n\nThis is a preview of the generated content...`,
                        wordCount: 450 + Math.floor(Math.random() * 200),
                      }
                    : d
                )
              )
              resolve()
            },
            800 + Math.random() * 400
          )
        })
      }
      setGeneratingAll(false)
    },
    [drafts]
  )

  const handleUpload = useCallback((section: ReportDraftSection, file: File) => {
    setDrafts(prev =>
      prev.map(d =>
        d.section === section
          ? {
              ...d,
              status: 'reviewed' as ReportDraftStatus,
              reviewedAt: new Date().toISOString(),
              uploadedFilename: file.name,
            }
          : d
      )
    )
  }, [])

  // Simulate report generation progress
  useEffect(() => {
    if (generationStatus !== 'generating') return

    const steps = [
      'Validating findings data...',
      'Loading draft sections...',
      'Compiling executive summary...',
      'Formatting risk assessment...',
      'Building critical issues section...',
      'Adding improvement points...',
      'Generating scope & methodology...',
      'Compiling recommendations...',
      'Rendering PDF...',
      'Writing output file...',
    ]

    let stepIndex = 0
    const interval = setInterval(
      () => {
        if (stepIndex < steps.length) {
          const newProgress = Math.min(100, Math.round(((stepIndex + 1) / steps.length) * 100))
          setProgress(newProgress)
          setLogs(prev => [
            ...prev,
            {
              id: `log-${Date.now()}`,
              runId: runId || '',
              type: 'step_completed',
              timestamp: new Date().toISOString(),
              step: steps[stepIndex],
              message: steps[stepIndex],
              progress: newProgress,
            },
          ])
          stepIndex++
        } else {
          clearInterval(interval)
          setGenerationStatus('completed')
          setLogs(prev => [
            ...prev,
            {
              id: `log-${Date.now()}`,
              runId: runId || '',
              type: 'generation_completed',
              timestamp: new Date().toISOString(),
              message: 'Report generated successfully',
              progress: 100,
            },
          ])
        }
      },
      600 + Math.random() * 300
    )

    return () => clearInterval(interval)
  }, [generationStatus, runId])

  const handleStartGeneration = () => {
    if (format === 'pdf' && !allDraftsReady) {
      setShowPreflight(true)
      return
    }

    setLogs([])
    setProgress(0)
    setGenerationStatus('generating')
    const newRunId = `run-${Date.now()}`
    setRunId(newRunId)
    setLogs([
      {
        id: `log-${Date.now()}`,
        runId: newRunId,
        type: 'generation_started',
        timestamp: new Date().toISOString(),
        message: `Starting ${format.toUpperCase()} report generation...`,
      },
    ])
  }

  const handleStopGeneration = () => {
    setGenerationStatus('idle')
    setProgress(0)
    setRunId(null)
  }

  const handleReset = () => {
    setGenerationStatus('idle')
    setProgress(0)
    setRunId(null)
    setLogs([])
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
            {project?.name} / {draftCount} of 6 sections ready
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
                  disabled={!canGenerate && format === 'pdf'}
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
                  className="flex items-center gap-2 px-4 py-2 bg-crit text-background text-sm font-bold uppercase tracking-wider hover:bg-crit/90 transition-colors"
                >
                  <Square className="h-4 w-4" />
                  Stop
                </button>
              )}
              {(generationStatus === 'completed' || generationStatus === 'failed') && (
                <button
                  onClick={handleReset}
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
                      PDF requires all 6 draft sections. {6 - draftCount} section(s) still needed.
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
                    disabled={generatingAll || allDraftsReady}
                    className="px-2 py-1 text-[10px] uppercase tracking-wider border border-accent text-accent hover:bg-accent hover:text-background transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {generatingAll ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      'Generate Missing'
                    )}
                  </button>
                  <button
                    onClick={() => handleGenerateAll(true)}
                    disabled={generatingAll}
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
                    draft={draft}
                    onGenerate={force => handleGenerateDraft(draft.section, force)}
                    onUpload={file => handleUpload(draft.section, file)}
                    isGenerating={generatingSection === draft.section || generatingAll}
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
                <HistoryTable entries={history} />
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
            handleStartGeneration()
          }}
        />
      )}
    </div>
  )
}
