import { useState, useEffect, useRef, useMemo, useCallback } from "react"
import {
  Play,
  Square,
  RotateCcw,
  Download,
  Upload,
  FileText,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  Check,
  X,
  Clock,
  Loader2,
  AlertTriangle,
  FileCheck,
  FilePlus,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Panel, Bar } from "@/components/tty"
import { useUI } from "@/lib/store"
import { useProjects, useReportDrafts, useReportHistory, useGenerateDraft, useGenerateReport } from "@/lib/api"
import type {
  ReportFormat,
  TestingType,
  ReportDraftSection,
  ReportDraft,
  ReportLogEvent,
  ReportGenerationStatus,
  ReportHistoryEntry,
  ReportDraftStatus,
} from "@/lib/types"

// ─── Constants ──────────────────────────────────────────────────────────────

const SECTION_LABELS: Record<ReportDraftSection, string> = {
  executive_summary: "Executive Summary",
  risk_level: "Risk Level Assessment",
  critical_issues: "Critical Issues",
  improvement_points: "Improvement Points",
  scope_methodology: "Scope & Methodology",
  general_recommendations: "General Recommendations",
}

const SECTION_ORDER: ReportDraftSection[] = [
  "executive_summary",
  "risk_level",
  "critical_issues",
  "improvement_points",
  "scope_methodology",
  "general_recommendations",
]

const FORMAT_OPTIONS: { value: ReportFormat; label: string; requiresDrafts: boolean }[] = [
  { value: "pdf", label: "PDF", requiresDrafts: true },
  { value: "markdown", label: "Markdown", requiresDrafts: false },
  { value: "html", label: "HTML", requiresDrafts: false },
  { value: "json", label: "JSON", requiresDrafts: false },
]

const TESTING_TYPE_OPTIONS: { value: TestingType; label: string }[] = [
  { value: "white_box", label: "White Box" },
  { value: "grey_box", label: "Grey Box" },
  { value: "black_box", label: "Black Box" },
]

// ─── Document Printer Animation ─────────────────────────────────────────────

function PrinterAnimation({
  active,
  progress,
  size = 220,
}: {
  active: boolean
  progress: number
  size?: number
}) {
  const pageCount = 6
  const pagesComplete = Math.floor((progress / 100) * pageCount)

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 220 220"
      className="shrink-0"
      aria-hidden
    >
      {/* Corner brackets */}
      <g stroke="var(--color-accent)" strokeWidth={2} fill="none">
        <path d="M 15 5 L 5 5 L 5 15" />
        <path d="M 205 5 L 215 5 L 215 15" />
        <path d="M 15 215 L 5 215 L 5 205" />
        <path d="M 205 215 L 215 215 L 215 205" />
      </g>

      {/* Outer frame */}
      <rect
        x="30"
        y="50"
        width="160"
        height="120"
        fill="none"
        stroke="var(--color-border)"
        strokeWidth="2"
        rx="4"
      />

      {/* Paper tray (input) */}
      <rect
        x="60"
        y="30"
        width="100"
        height="25"
        fill="var(--color-muted)"
        stroke="var(--color-border)"
        strokeWidth="1"
        rx="2"
      />

      {/* Document stack in tray */}
      {[0, 1, 2].map((i) => (
        <rect
          key={i}
          x={65 + i * 2}
          y={35 + i * 2}
          width={86 - i * 4}
          height={15}
          fill="var(--color-background)"
          stroke="var(--color-dim)"
          strokeWidth="0.5"
        />
      ))}

      {/* Printer body */}
      <rect
        x="40"
        y="60"
        width="140"
        height="70"
        fill="var(--color-muted)"
        stroke="var(--color-border)"
        strokeWidth="1"
        rx="2"
      />

      {/* Status lights */}
      <circle
        cx="60"
        cy="75"
        r="4"
        fill={active ? "var(--color-accent)" : "var(--color-dim)"}
        className={active ? "tty-glow" : ""}
      />
      <circle
        cx="75"
        cy="75"
        r="4"
        fill={active ? "var(--color-warn)" : "var(--color-dim)"}
        className={active ? "animate-pulse" : ""}
      />

      {/* LCD display area */}
      <rect
        x="90"
        y="68"
        width="80"
        height="16"
        fill="var(--color-background)"
        stroke="var(--color-border)"
        strokeWidth="1"
      />
      <text
        x="130"
        y="80"
        textAnchor="middle"
        fill="var(--color-accent)"
        fontSize="8"
        fontFamily="monospace"
        className={active ? "tty-glow" : ""}
      >
        {active ? `PRINTING ${progress}%` : "READY"}
      </text>

      {/* Paper output slot */}
      <rect
        x="60"
        y="125"
        width="100"
        height="8"
        fill="var(--color-background)"
        stroke="var(--color-border)"
        strokeWidth="1"
      />

      {/* Output tray */}
      <path
        d="M 55 170 L 60 135 L 160 135 L 165 170 Z"
        fill="var(--color-muted)"
        stroke="var(--color-border)"
        strokeWidth="1"
      />

      {/* Printed pages in output tray */}
      {Array.from({ length: pagesComplete }).map((_, i) => (
        <g key={i}>
          <rect
            x={65 + i * 1.5}
            y={140 + i * 3}
            width={90 - i * 3}
            height={25}
            fill="var(--color-background)"
            stroke="var(--color-accent)"
            strokeWidth="0.5"
            className="tty-glow"
          />
          {[0, 1, 2].map((line) => (
            <line
              key={line}
              x1={70 + i * 1.5}
              y1={148 + i * 3 + line * 5}
              x2={145 - i * 3}
              y2={148 + i * 3 + line * 5}
              stroke="var(--color-dim)"
              strokeWidth="0.5"
            />
          ))}
        </g>
      ))}

      {/* Currently printing page (animated) */}
      {active && pagesComplete < pageCount && (
        <g className="animate-pulse">
          <rect
            x="70"
            y="110"
            width="80"
            height="20"
            fill="var(--color-background)"
            stroke="var(--color-accent)"
            strokeWidth="1"
          />
        </g>
      )}
    </svg>
  )
}

// ─── Draft Section Card ─────────────────────────────────────────────────────

function DraftCard({
  draft,
  onGenerate,
  onUpload,
  isGenerating,
  skipTriage,
}: {
  draft: ReportDraft
  onGenerate: (force: boolean) => void
  onUpload: (file: File) => void
  isGenerating: boolean
  skipTriage: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const hasDraft = draft.status === "draft" || draft.status === "reviewed"
  const isReviewed = draft.status === "reviewed"

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      onUpload(file)
    }
    e.target.value = ""
  }

  return (
    <div className={cn(
      "border bg-muted/20 transition-colors",
      isReviewed ? "border-good/50" : "border-border"
    )}>
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-muted/30 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <button className="shrink-0 text-dim hover:text-foreground">
          {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </button>

        {isReviewed ? (
          <FileCheck className="h-4 w-4 text-good shrink-0" />
        ) : (
          <FileText className="h-4 w-4 text-accent shrink-0" />
        )}

        <span className="flex-1 text-sm font-medium">
          {SECTION_LABELS[draft.section]}
        </span>

        {/* Status badge */}
        {draft.status === "reviewed" && (
          <span className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-good">
            <Check className="h-3 w-3" />
            Reviewed
          </span>
        )}
        {draft.status === "draft" && (
          <span className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-accent">
            <FileText className="h-3 w-3" />
            Draft Ready
          </span>
        )}
        {draft.status === "generating" && (
          <span className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-warn">
            <Loader2 className="h-3 w-3 animate-spin" />
            Generating
          </span>
        )}
        {draft.status === "not_generated" && (
          <span className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-dim">
            <Clock className="h-3 w-3" />
            Not Generated
          </span>
        )}
        {draft.status === "failed" && (
          <span className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-crit">
            <X className="h-3 w-3" />
            Failed
          </span>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
          {/* Generate / Regenerate */}
          {!hasDraft ? (
            <button
              onClick={() => onGenerate(false)}
              disabled={isGenerating}
              className="px-2 py-1 text-[10px] uppercase tracking-wider border border-accent text-accent hover:bg-accent hover:text-background transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isGenerating ? <Loader2 className="h-3 w-3 animate-spin" /> : "Generate"}
            </button>
          ) : (
            <button
              onClick={() => onGenerate(true)}
              disabled={isGenerating}
              className="p-1.5 text-[10px] border border-border text-muted-foreground hover:border-warn hover:text-warn transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title="Regenerate (overwrites existing)"
            >
              <RefreshCw className="h-3 w-3" />
            </button>
          )}

          {/* Upload reviewed version */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".md,.txt"
            onChange={handleFileChange}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            className={cn(
              "p-1.5 text-[10px] border transition-colors",
              hasDraft
                ? "border-border text-muted-foreground hover:border-good hover:text-good"
                : "border-border/50 text-dim cursor-not-allowed"
            )}
            disabled={!hasDraft}
            title={hasDraft ? "Upload reviewed version" : "Generate draft first"}
          >
            <Upload className="h-3 w-3" />
          </button>

          {/* Download */}
          <button
            className={cn(
              "p-1.5 text-[10px] border transition-colors",
              hasDraft
                ? "border-border text-muted-foreground hover:border-accent hover:text-accent"
                : "border-border/50 text-dim cursor-not-allowed"
            )}
            disabled={!hasDraft}
            title={hasDraft ? "Download draft" : "No draft to download"}
          >
            <Download className="h-3 w-3" />
          </button>
        </div>
      </div>

      {/* Expanded preview */}
      {expanded && (
        <div className="px-4 py-3 border-t border-border bg-background/50">
          {hasDraft && draft.preview ? (
            <>
              <div className="flex items-center gap-4 mb-2 text-[10px] text-dim">
                <span>{draft.wordCount} words</span>
                {draft.generatedAt && (
                  <span>Generated {new Date(draft.generatedAt).toLocaleDateString()}</span>
                )}
                {draft.reviewedAt && (
                  <span className="text-good">
                    Reviewed {new Date(draft.reviewedAt).toLocaleDateString()}
                  </span>
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
              {skipTriage ? " (skip-triage mode: includes all findings)" : " (only triaged findings will be included)"}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

// ─── History Table ──────────────────────────────────────────────────────────

function HistoryTable({ entries }: { entries: ReportHistoryEntry[] }) {
  if (entries.length === 0) {
    return (
      <div className="text-center py-12 text-dim">
        <FileText className="h-8 w-8 mx-auto mb-2 opacity-50" />
        <p>No reports generated yet</p>
      </div>
    )
  }

  return (
    <div className="border border-border">
      <div className="grid grid-cols-[1fr_80px_140px_80px_60px] gap-4 px-4 py-2 bg-muted/30 border-b border-border text-[10px] uppercase tracking-wider text-dim">
        <span>Filename</span>
        <span>Format</span>
        <span>Generated</span>
        <span>Size</span>
        <span></span>
      </div>
      {entries.map((entry) => (
        <div
          key={entry.id}
          className="grid grid-cols-[1fr_80px_140px_80px_60px] gap-4 px-4 py-3 border-b border-border last:border-b-0 hover:bg-muted/20 transition-colors"
        >
          <span className="text-sm font-mono truncate" title={entry.filename}>
            {entry.filename}
          </span>
          <span className="text-sm uppercase text-accent">{entry.format}</span>
          <span className="text-sm text-muted-foreground">
            {new Date(entry.generatedAt).toLocaleString()}
          </span>
          <span className="text-sm text-muted-foreground tabular-nums">
            {(entry.sizeBytes / 1024).toFixed(0)} KB
          </span>
          <button className="text-accent hover:text-foreground transition-colors">
            <Download className="h-4 w-4" />
          </button>
        </div>
      ))}
    </div>
  )
}

// ─── Log Event Row ──────────────────────────────────────────────────────────

function LogRow({ event }: { event: ReportLogEvent }) {
  const time = new Date(event.timestamp).toLocaleTimeString("en-US", { hour12: false })

  const typeColors: Record<string, string> = {
    generation_started: "text-accent",
    step_started: "text-muted-foreground",
    step_completed: "text-good",
    step_failed: "text-crit",
    generation_completed: "text-good",
    generation_failed: "text-crit",
    draft_started: "text-warn",
    draft_completed: "text-good",
    draft_failed: "text-crit",
  }

  return (
    <div className="flex items-start gap-3 px-3 py-1.5 font-mono text-[11px] hover:bg-muted/20">
      <span className="text-dim shrink-0">{time}</span>
      <span className={cn("uppercase shrink-0 w-24", typeColors[event.type] ?? "text-foreground")}>
        {event.type.replace(/_/g, " ")}
      </span>
      <span className="text-foreground flex-1">{event.message}</span>
      {event.progress !== undefined && (
        <span className="text-accent tabular-nums">{event.progress}%</span>
      )}
    </div>
  )
}

// ─── Pre-flight Checklist ───────────────────────────────────────────────────

function PreflightChecklist({
  drafts,
  onClose,
  onConfirm,
}: {
  drafts: ReportDraft[]
  onClose: () => void
  onConfirm: () => void
}) {
  const allReady = drafts.every((d) => d.status === "draft" || d.status === "reviewed")
  const reviewedCount = drafts.filter((d) => d.status === "reviewed").length

  return (
    <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center">
      <div className="bg-background border border-border w-full max-w-lg">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <h2 className="text-sm font-bold uppercase tracking-wider">
            <span className="text-accent">[</span>
            PDF Pre-flight Check
            <span className="text-accent">]</span>
          </h2>
          <button onClick={onClose} className="text-dim hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-4 space-y-3">
          {SECTION_ORDER.map((section) => {
            const draft = drafts.find((d) => d.section === section)
            const status = draft?.status ?? "not_generated"
            const ready = status === "draft" || status === "reviewed"

            return (
              <div key={section} className="flex items-center gap-3">
                {ready ? (
                  <Check className="h-4 w-4 text-good" />
                ) : (
                  <X className="h-4 w-4 text-crit" />
                )}
                <span className={cn("flex-1 text-sm", ready ? "text-foreground" : "text-dim")}>
                  {SECTION_LABELS[section]}
                </span>
                {status === "reviewed" && (
                  <span className="text-[10px] uppercase text-good">Reviewed</span>
                )}
                {status === "draft" && (
                  <span className="text-[10px] uppercase text-accent">Draft</span>
                )}
                {status === "not_generated" && (
                  <span className="text-[10px] uppercase text-crit">Missing</span>
                )}
              </div>
            )
          })}
        </div>

        <div className="px-4 py-3 border-t border-border bg-muted/20">
          {allReady ? (
            <div className="flex items-center justify-between">
              <span className="text-sm text-good">
                All sections ready ({reviewedCount} reviewed, {6 - reviewedCount} drafts)
              </span>
              <button
                onClick={onConfirm}
                className="px-4 py-2 bg-accent text-background text-sm font-bold uppercase tracking-wider hover:bg-accent/90 transition-colors"
              >
                Generate PDF
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-crit text-sm">
              <AlertTriangle className="h-4 w-4" />
              <span>
                {6 - drafts.filter((d) => d.status === "draft" || d.status === "reviewed").length} section(s) missing. Generate all drafts before creating PDF.
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Main Component ─────────────────────────────────────────────────────────

export default function Reports() {
  const activeProjectId = useUI((s) => s.activeProjectId)

  // TODO [BACKEND]: These hooks return mock data. Replace with real API calls.
  // GET /api/v1/projects
  const { data: projects = [] } = useProjects()
  // GET /api/v1/projects/:id/reports/drafts
  const { data: draftData } = useReportDrafts(activeProjectId)
  // GET /api/v1/projects/:id/reports (history)
  const { data: historyData = [] } = useReportHistory(activeProjectId)

  // TODO [BACKEND]: These mutations trigger server actions.
  // POST /api/v1/projects/:id/reports/drafts
  const { generate: generateDraftMutation, isLoading: isGeneratingDraft } = useGenerateDraft()
  // POST /api/v1/projects/:id/reports/generate
  const { generate: generateReportMutation, isLoading: isGeneratingReport } = useGenerateReport()

  const project = projects.find((p) => p.id === activeProjectId)

  // Generation form state
  const [format, setFormat] = useState<ReportFormat>("pdf")
  const [testingType, setTestingType] = useState<TestingType>("grey_box")
  const [companyName, setCompanyName] = useState("")
  const [engagementDate, setEngagementDate] = useState(
    new Date().toISOString().split("T")[0]
  )
  const [skipTriage, setSkipTriage] = useState(false)
  const [showPreflight, setShowPreflight] = useState(false)
  const [showTalWarning, setShowTalWarning] = useState(true)

  // Generation run state
  const [runId, setRunId] = useState<string | null>(null)
  const [generationStatus, setGenerationStatus] = useState<ReportGenerationStatus>("idle")
  const [progress, setProgress] = useState(0)
  const [logs, setLogs] = useState<ReportLogEvent[]>([])
  const logContainerRef = useRef<HTMLDivElement>(null)

  // Draft generation state
  const [generatingSection, setGeneratingSection] = useState<ReportDraftSection | null>(null)
  const [generatingAll, setGeneratingAll] = useState(false)

  // Mock draft data - in real app, this comes from useReportDrafts hook
  const [drafts, setDrafts] = useState<ReportDraft[]>(() =>
    SECTION_ORDER.map((section) => ({
      section,
      status: activeProjectId === "p-01"
        ? (section === "executive_summary" || section === "risk_level" ? "draft" : "not_generated")
        : "not_generated",
      generatedAt: activeProjectId === "p-01" && (section === "executive_summary" || section === "risk_level")
        ? new Date(Date.now() - 86400000).toISOString()
        : undefined,
      preview: activeProjectId === "p-01" && (section === "executive_summary" || section === "risk_level")
        ? `# ${SECTION_LABELS[section]}\n\nThis is a preview of the generated content for the ${SECTION_LABELS[section].toLowerCase()} section. The full document contains detailed analysis based on the security findings from this engagement...`
        : undefined,
      wordCount: activeProjectId === "p-01" && (section === "executive_summary" || section === "risk_level")
        ? 450 + Math.floor(Math.random() * 200)
        : undefined,
    }))
  )

  // Mock history data
  const [history] = useState<ReportHistoryEntry[]>(() =>
    activeProjectId === "p-01"
      ? [
          {
            id: "rpt-001",
            projectId: "p-01",
            filename: "ACME_Platform_Security_Assessment_2024-03-15.pdf",
            format: "pdf",
            generatedAt: new Date(Date.now() - 7 * 86400000).toISOString(),
            sizeBytes: 2450000,
            downloadUrl: "#",
          },
          {
            id: "rpt-002",
            projectId: "p-01",
            filename: "ACME_Platform_Findings_Export.json",
            format: "json",
            generatedAt: new Date(Date.now() - 14 * 86400000).toISOString(),
            sizeBytes: 156000,
            downloadUrl: "#",
          },
        ]
      : []
  )

  // Counts
  const draftCount = drafts.filter((d) => d.status === "draft" || d.status === "reviewed").length
  const reviewedCount = drafts.filter((d) => d.status === "reviewed").length
  const allDraftsReady = draftCount === 6

  const selectedFormat = FORMAT_OPTIONS.find((f) => f.value === format)!
  const canGenerate = selectedFormat.requiresDrafts ? allDraftsReady : true

  // Auto-scroll logs
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }, [logs])

  // Simulate draft generation
  const handleGenerateDraft = useCallback((section: ReportDraftSection, force: boolean) => {
    setGeneratingSection(section)

    // Update draft to generating status
    setDrafts((prev) =>
      prev.map((d) =>
        d.section === section ? { ...d, status: "generating" as ReportDraftStatus } : d
      )
    )

    // Simulate generation delay
    setTimeout(() => {
      setDrafts((prev) =>
        prev.map((d) =>
          d.section === section
            ? {
                ...d,
                status: "draft" as ReportDraftStatus,
                generatedAt: new Date().toISOString(),
                preview: `# ${SECTION_LABELS[section]}\n\nThis is a preview of the generated content for the ${SECTION_LABELS[section].toLowerCase()} section. The full document contains detailed analysis based on the security findings from this engagement...`,
                wordCount: 450 + Math.floor(Math.random() * 200),
              }
            : d
        )
      )
      setGeneratingSection(null)
    }, 1500 + Math.random() * 1000)
  }, [])

  // Generate all drafts
  const handleGenerateAll = useCallback(async (force: boolean) => {
    setGeneratingAll(true)
    const toGenerate = force
      ? SECTION_ORDER
      : SECTION_ORDER.filter((s) => {
          const d = drafts.find((dr) => dr.section === s)
          return !d || d.status === "not_generated" || d.status === "failed"
        })

    for (const section of toGenerate) {
      await new Promise<void>((resolve) => {
        setDrafts((prev) =>
          prev.map((d) =>
            d.section === section ? { ...d, status: "generating" as ReportDraftStatus } : d
          )
        )
        setTimeout(() => {
          setDrafts((prev) =>
            prev.map((d) =>
              d.section === section
                ? {
                    ...d,
                    status: "draft" as ReportDraftStatus,
                    generatedAt: new Date().toISOString(),
                    preview: `# ${SECTION_LABELS[section]}\n\nThis is a preview of the generated content...`,
                    wordCount: 450 + Math.floor(Math.random() * 200),
                  }
                : d
            )
          )
          resolve()
        }, 800 + Math.random() * 400)
      })
    }
    setGeneratingAll(false)
  }, [drafts])

  // Handle file upload for reviewed version
  const handleUpload = useCallback((section: ReportDraftSection, file: File) => {
    setDrafts((prev) =>
      prev.map((d) =>
        d.section === section
          ? {
              ...d,
              status: "reviewed" as ReportDraftStatus,
              reviewedAt: new Date().toISOString(),
              uploadedFilename: file.name,
            }
          : d
      )
    )
  }, [])

  // Simulate report generation progress
  useEffect(() => {
    if (generationStatus !== "generating") return

    const steps = [
      "Validating findings data...",
      "Loading draft sections...",
      "Compiling executive summary...",
      "Formatting risk assessment...",
      "Building critical issues section...",
      "Adding improvement points...",
      "Generating scope & methodology...",
      "Compiling recommendations...",
      "Rendering PDF...",
      "Writing output file...",
    ]

    let stepIndex = 0
    const interval = setInterval(() => {
      if (stepIndex < steps.length) {
        const newProgress = Math.min(100, Math.round(((stepIndex + 1) / steps.length) * 100))
        setProgress(newProgress)
        setLogs((prev) => [
          ...prev,
          {
            id: `log-${Date.now()}`,
            runId: runId || "",
            type: "step_completed",
            timestamp: new Date().toISOString(),
            step: steps[stepIndex],
            message: steps[stepIndex],
            progress: newProgress,
          },
        ])
        stepIndex++
      } else {
        clearInterval(interval)
        setGenerationStatus("completed")
        setLogs((prev) => [
          ...prev,
          {
            id: `log-${Date.now()}`,
            runId: runId || "",
            type: "generation_completed",
            timestamp: new Date().toISOString(),
            message: "Report generated successfully",
            progress: 100,
          },
        ])
      }
    }, 600 + Math.random() * 300)

    return () => clearInterval(interval)
  }, [generationStatus, runId])

  const handleStartGeneration = () => {
    if (format === "pdf" && !allDraftsReady) {
      setShowPreflight(true)
      return
    }

    setLogs([])
    setProgress(0)
    setGenerationStatus("generating")
    const newRunId = `run-${Date.now()}`
    setRunId(newRunId)
    setLogs([
      {
        id: `log-${Date.now()}`,
        runId: newRunId,
        type: "generation_started",
        timestamp: new Date().toISOString(),
        message: `Starting ${format.toUpperCase()} report generation...`,
      },
    ])
  }

  const handleStopGeneration = () => {
    setGenerationStatus("idle")
    setProgress(0)
    setRunId(null)
  }

  const handleReset = () => {
    setGenerationStatus("idle")
    setProgress(0)
    setRunId(null)
    setLogs([])
  }

  const isRunning = generationStatus === "generating"

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
        Generating a new PDF report will re-assign TAL IDs to all approved findings. If you have shared a previous report, IDs may change.
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
            <PrinterAnimation
              active={isRunning}
              progress={progress}
              size={220}
            />

            {/* Status indicator */}
            <div className="text-center">
              <div className={cn(
                "text-[11px] uppercase tracking-wider font-bold",
                generationStatus === "idle" && "text-dim",
                generationStatus === "generating" && "text-warn",
                generationStatus === "completed" && "text-good",
                generationStatus === "failed" && "text-crit",
              )}>
                {generationStatus === "idle" && "Ready"}
                {generationStatus === "generating" && "Generating..."}
                {generationStatus === "completed" && "Complete"}
                {generationStatus === "failed" && "Failed"}
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
              {generationStatus === "idle" && (
                <button
                  onClick={handleStartGeneration}
                  disabled={!canGenerate && format === "pdf"}
                  className={cn(
                    "flex items-center gap-2 px-4 py-2 text-sm font-bold uppercase tracking-wider transition-colors",
                    canGenerate || format !== "pdf"
                      ? "bg-accent text-background hover:bg-accent/90"
                      : "bg-muted text-dim cursor-not-allowed"
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
              {(generationStatus === "completed" || generationStatus === "failed") && (
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
                    <label className="text-[10px] uppercase tracking-wider text-dim">Format</label>
                    <select
                      value={format}
                      onChange={(e) => setFormat(e.target.value as ReportFormat)}
                      disabled={isRunning}
                      className="w-full bg-muted border border-border px-3 py-2 text-sm focus:outline-none focus:border-accent disabled:opacity-50"
                    >
                      {FORMAT_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label} {opt.requiresDrafts ? "(requires drafts)" : "(direct)"}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Testing Type (PDF only) */}
                  <div className="space-y-1">
                    <label className="text-[10px] uppercase tracking-wider text-dim">Testing Type</label>
                    <select
                      value={testingType}
                      onChange={(e) => setTestingType(e.target.value as TestingType)}
                      disabled={isRunning || format !== "pdf"}
                      className="w-full bg-muted border border-border px-3 py-2 text-sm focus:outline-none focus:border-accent disabled:opacity-50"
                    >
                      {TESTING_TYPE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Company Name */}
                  <div className="space-y-1">
                    <label className="text-[10px] uppercase tracking-wider text-dim">Company Name</label>
                    <input
                      type="text"
                      value={companyName}
                      onChange={(e) => setCompanyName(e.target.value)}
                      disabled={isRunning}
                      placeholder="e.g. ACME Corporation"
                      className="w-full bg-muted border border-border px-3 py-2 text-sm focus:outline-none focus:border-accent disabled:opacity-50 placeholder:text-dim"
                    />
                  </div>

                  {/* Engagement Date */}
                  <div className="space-y-1">
                    <label className="text-[10px] uppercase tracking-wider text-dim">Engagement Date</label>
                    <input
                      type="date"
                      value={engagementDate}
                      onChange={(e) => setEngagementDate(e.target.value)}
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
                    onChange={(e) => setSkipTriage(e.target.checked)}
                    disabled={isRunning}
                    className="accent-accent"
                  />
                  <span className="text-sm text-muted-foreground">
                    Skip triage filter (include all findings, not just triaged/reportable)
                  </span>
                </label>

                {/* Format-specific note */}
                {format === "pdf" && !allDraftsReady && (
                  <div className="flex items-center gap-2 text-[11px] text-warn">
                    <AlertTriangle className="h-3 w-3" />
                    <span>PDF requires all 6 draft sections. {6 - draftCount} section(s) still needed.</span>
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
                    {generatingAll ? <Loader2 className="h-3 w-3 animate-spin" /> : "Generate Missing"}
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
                {drafts.map((draft) => (
                  <DraftCard
                    key={draft.section}
                    draft={draft}
                    onGenerate={(force) => handleGenerateDraft(draft.section, force)}
                    onUpload={(file) => handleUpload(draft.section, file)}
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
                  {logs.map((event) => (
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
