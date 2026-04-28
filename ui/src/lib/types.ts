export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'informational'
export type Status = 'active' | 'false_positive' | 'fixed' | 'wont_fix'
export type Segment = 'sast' | 'web' | 'secrets' | 'sca'

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'HEAD' | 'OPTIONS'

/**
 * Free-form string on purpose — analysts may target protocols we don't know
 * about yet (ws/wss, ftp, smb, sip, coap, ...). Backend is the source of truth.
 */
export type UrlProtocol = string

/**
 * A single URL entry from a project's URL list. Camel-cased mirror of the
 * backend's snake_case row from `GET /api/v1/projects/:id/url-list/entries`.
 * URLs come from two sources: scan tools (Katana, Noir) and user-uploaded
 * endpoint files. `tool` and `runId` are populated only when `source === 'scan'`.
 * `filePath` is populated only when `source === 'user'`.
 */
export interface UrlEntry {
  /** Numeric SQLite primary key (matches backend `id: int`). */
  id: number
  /** Numeric project id (matches backend `project_id: int`). */
  projectId: number
  /** Repository this entry belongs to. */
  repoId: number
  /** Resolved repository name for display. */
  repoName: string
  /** Origin of the entry. */
  source: 'scan' | 'user'
  /** Discovery tool when source is 'scan'; null for user-uploaded entries. */
  tool: 'katana' | 'noir' | null
  /** Scan run that produced this entry; null for user-uploaded entries. */
  runId: number | null
  method: HttpMethod
  protocol: UrlProtocol
  /** Bare host, no protocol, no port, no trailing slash. e.g. "api.example.com" */
  host: string
  /** Numeric port (80, 443, 8080, ...) */
  port: number
  /** Path portion starting with "/". e.g. "/foo/bar/123" */
  path: string
  /** Path of the user-uploaded file when source is 'user'; null for scan entries. */
  filePath: string | null
  /** Tool-specific or upload-specific metadata. */
  meta: Record<string, unknown>
  /** ISO-8601 timestamp when the row was inserted. */
  createdAt: string
}

export interface Finding {
  /** Numeric SQLite primary key (matches backend `id: int`). */
  id: number
  /** Numeric project id (matches backend `project_id: int`). */
  projectId: number
  segment: Segment
  /** `code` or `web`. Distinct from segment (sast/web/secrets/sca). */
  domain: 'code' | 'web'
  severity: Severity
  status: Status
  /** confidence label — confirmed / probable / potential / false_positive. */
  confidence: string
  /** Backend always returns an array (possibly empty) for finding_type. */
  findingType: string[]
  title: string
  description?: string
  tool: string
  target: string
  file?: string
  line?: number
  /** Backend always returns an array (possibly empty) for cwe. */
  cwe: string[]
  /** Free-form analyst notes — editable in the detail panel. */
  notes?: string
  discoveredAt: string
  triagedAt?: string
  triagedBy?: 'claude-code' | 'analyst_web'
  /** Live lock state — true while a scan/triage job holds the row. */
  isLocked: boolean
  /** Identifier of the job currently holding the lock, when locked. */
  lockHolder: string | null
}

/**
 * Mirrors `ApiError` from `lib/api/client.ts` but in plain-object form so it
 * can live in the Zustand UI store without serialising an Error class. Used
 * by the global mutation-error modal to show the user when an optimistic
 * update was rolled back.
 */
export interface ApiErrorPayload {
  code: string
  message: string
  details: Record<string, unknown>
  status: number
}

/**
 * Aggregate finding counts for a project, served by
 * GET /api/v1/projects/:id/findings/counts. Camel-cased mirror of the
 * backend's snake_case FindingsCountsResponse. The inner record on
 * `bySeverityStatus` is `Record<string, number>` (not `Record<Status, number>`)
 * because the endpoint spec permits non-canonical status columns when present
 * in the data.
 */
export interface FindingsCounts {
  bySeverity: Record<Severity, number>
  byStatus: Record<Status, number>
  byDomain: Record<string, number>
  bySegment: Record<string, number>
  byRepo: Record<string, number>
  byTool: Record<string, number>
  bySeverityStatus: Record<Severity, Record<string, number>>
  total: number
  scansCount: number
  reposCount: number
  urlsCount: number
  lastScanAt: string | null
  lastTriageAt: string | null
}

export interface Project {
  id: number
  name: string
  code: string
}

/**
 * Project metadata served by GET /api/v1/projects/:id/meta. CamelCase mirror
 * of the backend's snake_case ProjectMetaResponse. `enabledTools` is the list
 * of tool IDs enabled for the project (not a count); call sites that want a
 * count read `.length`.
 */
export interface ProjectMeta {
  id: number
  name: string
  code: string
  repoCount: number
  urlListCount: number
  findingCount: number
  enabledTools: string[]
}

/**
 * One scan run summary as served by `GET /api/v1/projects/:id/scans`.
 * Mirrors the backend `ScanRunSummary` Pydantic model. The list endpoint
 * does NOT carry `current_segment` / `segment_label` / `progress`; those
 * live on `/scans/:run_id/progress`, which the FE consumes via SSE
 * snapshots instead.
 */
export interface Scan {
  /** Numeric SQLite primary key (matches backend `id: int`). */
  id: number
  /** Numeric project id (matches backend `project_id: int`). */
  projectId: number
  status: 'queued' | 'running' | 'done' | 'failed' | 'cancelling' | 'cancelled'
  startedAt: string
  finishedAt: string | null
  /** Repository names included in the run (backend serialises as strings). */
  repoIds: string[]
  /** Tool ids included in the run. */
  toolIds: string[]
  /** Segments / domains the run covered. */
  domains: Segment[]
  findingsCount: number | null
  skipEnrichment: boolean
}

// ─── Detailed Scan Run Types ────────────────────────────────────────────────
// Used by the Scans page for the live log stream and history view.

export type ScanRunStatus = 'idle' | 'running' | 'completed' | 'cancelling' | 'cancelled' | 'failed'

// ─── Scan Configuration Types ───────────────────────────────────────────────
// Used by the Scans page for advanced scan options.

/** A repository configured for scanning in the project. */
export interface ConfiguredRepo {
  /** Numeric SQLite primary key (matches backend `id: int`). */
  id: number
  name: string
  /** e.g., "github", "gitlab", "local" */
  source: string
  /** URL or local path; empty string when backend has no location. */
  location: string
}

/** A scanning tool available for the project. */
export interface ConfiguredTool {
  id: string
  name: string
  segment: Segment
  /** Whether this tool is enabled by default for scans */
  enabled: boolean
}

/** Scan options passed to the backend when starting a scan. */
export interface ScanOptions {
  /** Scope to specific repos (ids). If omitted, scan all repos. */
  repoIds?: number[]
  /** Run only these tools (ids). If omitted, run all enabled tools. */
  toolIds?: string[]
  /** Filter by segment(s). If omitted, run all segments. */
  segments?: Segment[]
  /** Exclude these tools (ids) from an otherwise full scan. */
  skipToolIds?: string[]
  /** Skip LLM enrichment step. */
  skipEnrichment?: boolean
}

/** Project scan configuration fetched from the server. */
export interface ProjectScanConfig {
  repos: ConfiguredRepo[]
  tools: ConfiguredTool[]
  segments: Segment[]
}

export interface ToolRun {
  id: string
  runId: string
  tool: string
  repo: string
  segment: Segment
  status: 'queued' | 'running' | 'skipped' | 'done' | 'failed'
  startedAt?: string
  finishedAt?: string
  duration?: number // seconds
  findingsCount?: number
  enrichedCount?: number
  totalToEnrich?: number
  exitCode?: number
  skipReason?: string
}

export interface ScanRun {
  id: string
  projectId: string
  status: ScanRunStatus
  startedAt: string
  finishedAt?: string
  /** Repos being scanned (empty = all). */
  repos: string[]
  /** Segments being scanned (empty = all). */
  segments: Segment[]
  /** Tools explicitly selected (empty = all enabled). */
  tools: string[]
  /** Live log of tool runs, updated via SSE events. */
  toolRuns: ToolRun[]
}

export type ScanLogEventType =
  | 'run_started'
  | 'segment_started'
  | 'tool_started'
  | 'tool_skipped'
  | 'tool_completed'
  | 'tool_failed'
  | 'enrichment_progress'
  | 'enrichment_complete'
  | 'segment_completed'
  | 'run_completed'
  | 'run_cancelled'
  | 'run_failed'

export interface ScanLogEvent {
  id: string
  runId: number
  type: ScanLogEventType
  timestamp: string
  segment?: Segment
  repo?: string
  tool?: string
  message: string
  findingsCount?: number
  enrichedCount?: number
  totalToEnrich?: number
  exitCode?: number
  duration?: number
}

// ─── Triage Types ───────────────────────────────────────────────────────────
// Used by the Triage page for batch monitoring and AI pipeline status.

export type TriageRunStatus = 'idle' | 'running' | 'completed' | 'cancelled' | 'failed'

export type TriageBatchStatus = 'pending' | 'in_progress' | 'completed' | 'failed'

export interface TriageBatch {
  id: string
  runId: string
  segment: Segment
  findingIds: string[]
  status: TriageBatchStatus
  attempts: number
  startedAt?: string
  finishedAt?: string
  /** Raw response from Claude, if completed. */
  responsePreview?: string
  error?: string
}

export interface TriageRun {
  id: string
  projectId: string
  status: TriageRunStatus
  startedAt: string
  finishedAt?: string
  /** Total findings queued for triage. */
  totalFindings: number
  /** Findings processed so far. */
  processedFindings: number
  batches: TriageBatch[]
}

export type TriageLogEventType =
  | 'run_started'
  | 'batch_created'
  | 'batch_started'
  | 'batch_progress'
  | 'batch_completed'
  | 'batch_failed'
  | 'batch_retry'
  | 'run_completed'
  | 'run_cancelled'
  | 'triage_failed'

export interface TriageLogEvent {
  id: string
  runId: string
  type: TriageLogEventType
  timestamp: string
  batchId?: string
  segment?: Segment
  message: string
  findingsCount?: number
  processedCount?: number
  totalCount?: number
  attempt?: number
  /** Set on `triage_failed`. Human-readable error message. */
  error?: string
  /** Set on `triage_failed`. First finding id of the most recent in-progress batch. */
  failedAtFindingId?: number
  /** Set on `triage_failed`. True iff the run still has resumable batches. */
  resumable?: boolean
}

// ─── Runtime Dependencies / Installed Tools (Phase 2.6, Phase 6.8) ──────────

export interface RuntimeDependency {
  name: string
  installed: boolean
  binaryPath: string | null
  version: string | null
  installHint: string
  requiredFor: string[]
  error: string | null
}

export interface RuntimeDependenciesResponse {
  dependencies: RuntimeDependency[]
}

export interface InstalledToolsResponse {
  installed: string[]
}

// ─── Report Types ───────────────────────────────────────────────────────────
// Used by the Reports page for draft management and report generation.

export type ReportFormat = 'pdf' | 'markdown' | 'html' | 'json'
export type TestingType = 'white_box' | 'grey_box' | 'black_box'

export type ReportDraftSection =
  | 'executive_summary'
  | 'risk_level'
  | 'critical_issues'
  | 'improvement_points'
  | 'scope_methodology'
  | 'general_recommendations'

export type ReportDraftStatus = 'not_generated' | 'generating' | 'draft' | 'reviewed' | 'failed'

export interface ReportDraft {
  section: ReportDraftSection
  status: ReportDraftStatus
  generatedAt?: string
  reviewedAt?: string
  /** Preview of first ~500 chars */
  preview?: string
  /** Word count for full content */
  wordCount?: number
  /** Filename if user uploaded a reviewed version */
  uploadedFilename?: string
  error?: string
}

export type ReportGenerationStatus = 'idle' | 'generating' | 'completed' | 'failed'

export interface ReportGenerationRun {
  id: string
  projectId: string
  status: ReportGenerationStatus
  format: ReportFormat
  testingType?: TestingType
  engagementDate: string
  startedAt: string
  finishedAt?: string
  outputPath?: string
  error?: string
  /** Progress steps completed */
  steps: ReportGenerationStep[]
}

export interface ReportGenerationStep {
  id: string
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  message?: string
  startedAt?: string
  finishedAt?: string
}

export interface ReportHistoryEntry {
  id: string
  projectId: string
  filename: string
  format: ReportFormat
  generatedAt: string
  sizeBytes: number
  downloadUrl: string
}

export type ReportLogEventType =
  | 'generation_started'
  | 'step_started'
  | 'step_completed'
  | 'step_failed'
  | 'generation_completed'
  | 'generation_failed'
  | 'draft_started'
  | 'draft_completed'
  | 'draft_failed'

export interface ReportLogEvent {
  id: string
  runId: string
  type: ReportLogEventType
  timestamp: string
  step?: string
  section?: ReportDraftSection
  message: string
  progress?: number
}

// ─── Chat Types ─────────────────────────────────────────────────────────────
// Used by the Chat page for RAG-powered LLM conversations.

export type ChatMessageRole = 'user' | 'assistant' | 'system'

export interface ChatMessage {
  id: string
  sessionId: string
  role: ChatMessageRole
  content: string
  timestamp: string
  /** True while the message is still being streamed from the server */
  isStreaming?: boolean
}

export interface ChatSession {
  id: string
  projectId: string
  title?: string
  createdAt: string
  lastMessageAt?: string
  messageCount: number
}

export type ChatStreamEventType =
  | 'stream_start'
  | 'token'
  | 'stream_end'
  | 'error'
  | 'stream_cancelled'

export interface ChatStreamEvent {
  type: ChatStreamEventType
  sessionId: string
  messageId?: string
  /** Token content for "token" events */
  token?: string
  /** Full message content for "stream_end" events */
  content?: string
  /** Error message for "error" events */
  error?: string
}

// ─── Configuration Types ────────────────────────────────────────────────────
// Used by the Config page for project, repository, and tool override management.

/** Repository type - library is mutually exclusive with api/ui */
export type RepoType = 'library' | 'api' | 'ui'

/** Repository location mode */
export type RepoLocationMode = 'local' | 'docker'

/**
 * A repository configuration in a project.
 * Full model for Add/Edit repository form.
 */
export interface RepositoryConfig {
  id: string
  projectId: string
  name: string
  /** At least one required. library is mutually exclusive with api/ui. */
  types: RepoType[]
  locationMode: RepoLocationMode
  /** Required in both local and docker modes */
  localPath: string
  /** Docker-only fields */
  docker?: {
    containerName: string
    mountPoint: string
  }
  /** Auto-detected or user-specified */
  languages: string[]
  /** Directories treated as test code */
  testDirectories: string[]
  /** Directories excluded from scans */
  ignoreDirectories: string[]
  /** API target URLs (first is canonical) */
  baseUrls: string[]
  /** Uploaded endpoint definition file path (if any) */
  endpointFile?: string
  /** Endpoint file format (auto-detected) */
  endpointFileFormat?: 'openapi3' | 'swagger2' | 'postman' | 'har' | 'katana-jsonl'
  /** When both baseUrls and endpointFile set, should crawlers also run? */
  alsoRunCrawlers: boolean
  /** Katana configuration */
  katana: {
    headless: boolean
    /** Capped at 5 when headless is on */
    crawlDepth: number
  }
  /** Auth configuration for crawling */
  auth?: {
    loginUrl: string
    usernameFieldName: string
    passwordFieldName: string
    credentialsEnvVar?: string
    inlineUsername?: string
    inlinePassword?: string
  }
  /** Server-detected flags */
  detected?: {
    isSpa: boolean
    languages: string[]
    testDirectories: string[]
  }
}

/** Tool type */
export type ToolType = 'repo' | 'api'

/** Tool location mode */
export type ToolLocationMode = 'local' | 'docker'

/** Tool catalog entry - the available tools that can be overridden */
export interface ToolCatalogEntry {
  id: string
  name: string
  supportsLocal: boolean
  supportsDocker: boolean
}

/**
 * A tool override configuration in a project.
 * Overrides global tool config with project-specific paths.
 */
export interface ToolOverrideConfig {
  toolId: string
  type: ToolType
  location: ToolLocationMode
  /** Required when location = local */
  path?: string
  /** Required when location = docker */
  container?: {
    name: string
    toolPath: string
  }
}

/**
 * Project information for the config page.
 * Some fields are editable, some are read-only.
 */
export interface ProjectInfo {
  id: string
  name: string
  code: string
  company?: string
  department?: string
  abbreviation?: string
  createdAt: string
  /** Read-only derived data */
  path: string
  repoCount: number
  findingCount: number
}
