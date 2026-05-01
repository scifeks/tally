export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'informational'
export type Status = 'active' | 'false_positive' | 'fixed' | 'wont_fix'
export type Segment = 'sast' | 'web' | 'secrets' | 'sca'

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'HEAD' | 'OPTIONS'

/**
 * Free-form string on purpose - analysts may target protocols we don't know
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
  /** confidence label - confirmed / probable / potential / false_positive. */
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
  /** Free-form analyst notes - editable in the detail panel. */
  notes?: string
  discoveredAt: string
  triagedAt?: string
  triagedBy?: 'claude-code' | 'analyst_web'
  /** Live lock state - true while a scan/triage job holds the row. */
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

/**
 * Backend-shaped run status served by `/api/v1/projects/:id/triage*` and
 * emitted on SSE `snapshot` events. Matches `TriageRun.status` in
 * `web/api/schemas.py`.
 */
export type TriageRunStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelling' | 'cancelled'

/**
 * UI-only page status used by the `useUI` store to gate project switching.
 * The Triage page derives this from `useActiveTriage`. `'idle'` means
 * "no triage is currently active for the active project".
 */
export type TriagePageStatus = 'idle' | 'running' | 'completed' | 'cancelled' | 'failed'

export type TriageBatchStatus = 'pending' | 'in_progress' | 'completed' | 'failed' | 'cancelled'

/**
 * One batch within a triage run. Mirrors `TriageBatchItem` in
 * `web/api/schemas.py`. The backend may emit `segment: null` for
 * cross-segment batches; consumers should fall back to a neutral label.
 */
export interface TriageBatch {
  /** Numeric SQLite primary key. */
  id: number
  /** scan_run_id of the parent triage run (kept as `runId` in FE for brevity). */
  runId: number
  segment: Segment | null
  findingIds: number[]
  status: TriageBatchStatus
  attempts: number
  startedAt: string | null
  finishedAt: string | null
  /** Raw response preview from Claude, if completed. */
  responsePreview: string | null
  error: string | null
}

/**
 * A triage run summary or detail. The summary endpoint returns no `batches`;
 * the detail endpoint and SSE `snapshot` event include them. Mirrors
 * `TriageRunSummary` / `TriageDetailResponse` in `web/api/schemas.py`.
 *
 * Note: a triage run is keyed by its `scan_run_id` (the scan it triages),
 * not by a separate primary key.
 */
export interface TriageRun {
  scanRunId: number
  projectId: number
  status: TriageRunStatus
  startedAt: string | null
  finishedAt: string | null
  totalFindings: number
  processedFindings: number
  /** Present on detail / snapshot; absent on summary list rows. */
  batches?: TriageBatch[]
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
  /** Event identifier (UUID string from `new_event_id()` on the backend). */
  id: string
  scanRunId: number
  projectId: number
  type: TriageLogEventType
  timestamp: string
  batchId?: number
  segment?: Segment
  message: string
  findingsCount?: number
  processedCount?: number
  totalCount?: number
  attempt?: number
  /** Set on `triage_failed`. Human-readable error message. */
  error?: string
  /** Set on `triage_failed`. First finding id of the most recent in-progress batch. */
  failedAtFindingId?: number | null
  /** Set on `triage_failed`. True iff the run still has resumable batches. */
  resumable?: boolean
}

/**
 * Discriminated union for SSE `snapshot` payloads. The backend emits the
 * run-scoped variant when the consumer subscribed with `?scan_run_id=<id>`,
 * and the project-scoped variant otherwise.
 */
export type TriageSnapshotPayload =
  | {
      projectId: number
      scanRunId: number
      status: TriageRunStatus
      totalFindings: number
      processedFindings: number
      startedAt: string | null
      finishedAt: string | null
      batches: TriageBatch[]
    }
  | {
      projectId: number
      scanRunId: null
      activeScanRunIds: number[]
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
  | 'executive-summary'
  | 'risk-level'
  | 'critical-issues'
  | 'improvement-points'
  | 'scope-and-methodology'
  | 'general-recommendations'

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
  id: number
  projectId: number
  status: ReportGenerationStatus
  format: ReportFormat
  testingType?: TestingType
  engagementDate?: string
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
  id: number
  projectId: number
  filename: string
  format: ReportFormat
  generatedAt: string
  sizeBytes: number
  downloadUrl: string
  pinned?: boolean
}

export interface ReportCancelResponse {
  id: number
  status: 'cancelling'
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
  runId: number
  type: ReportLogEventType
  timestamp: string
  step?: string
  section?: ReportDraftSection
  message: string
  progress?: number
}

export interface ReportSnapshotPayload {
  runId: number
  status: ReportGenerationStatus
  steps: ReportGenerationStep[]
}

export interface ReportDraftSnapshotPayload {
  /** Sections currently in flight (server-side state). */
  inFlight: ReportDraftSection[]
}

// ─── Chat Types ─────────────────────────────────────────────────────────────
// Used by the Chat page for RAG-powered LLM conversations.

/**
 * Backend CHECK-constrains chat message roles to exactly these two values
 * (endpoints.md §12.4). No 'system' role on the wire.
 */
export type ChatMessageRole = 'user' | 'assistant'

/**
 * One persisted chat message. CamelCase mirror of the backend's snake_case
 * row served by `GET /api/v1/projects/:id/chat/sessions/:sid/messages`.
 *
 * `model` is null on user turns and the LLM provider's model id on assistant
 * turns. `citations` is reserved for the future RAG citations surface
 * (chat-history.md decision 10) - always `null` in v1.
 */
export interface ChatMessage {
  /** Numeric SQLite primary key. */
  id: number
  /** Numeric session id (matches backend `session_id: int`). */
  sessionId: number
  role: ChatMessageRole
  content: string
  /** LLM model id on assistant turns; null on user turns. */
  model: string | null
  /** ISO-8601 timestamp; backend column name is `created_at`. */
  timestamp: string
  /** Reserved for future RAG citations surface - always null in v1. */
  citations: null
  /** UI-only: true while the assistant turn is streaming tokens. */
  isStreaming?: boolean
}

/**
 * One chat session row served by `GET /api/v1/projects/:id/chat/sessions`.
 * Title is server-set as `'YYYY-MM-DD HH:MM'`; sessions are sealed (their
 * `expiredAt` is set) when a new scan run starts (decisions.md B7).
 */
export interface ChatSession {
  /** Numeric SQLite primary key. */
  id: number
  /** Numeric project id (matches backend `project_id: int`). */
  projectId: number
  /** Server-set timestamp title - never null. */
  title: string
  createdAt: string
  /** Null until the first message is sent. */
  lastMessageAt: string | null
  messageCount: number
  /** Set when the session is sealed by a new scan; null when active. */
  expiredAt: string | null
}

export type ChatStreamEventType =
  | 'stream_start'
  | 'token'
  | 'stream_end'
  | 'error'
  | 'stream_cancelled'

/**
 * SSE snapshot frame emitted once per subscriber on connect (endpoints.md
 * §15.4). When `active` is true, a stream is currently in flight for this
 * session and `userMessageId` is the in-progress user turn's id.
 */
export interface ChatStreamSnapshotPayload {
  projectId: number
  sessionId: number
  active: boolean
  userMessageId: number | null
}

/**
 * Discriminated union of SSE token-stream events (endpoints.md §15.4).
 * `messageId` is null on every event except `stream_end`, where the
 * persisted assistant row id is delivered (write-once semantics, B7.7).
 */
export type ChatStreamEvent =
  | { type: 'stream_start'; projectId: number; sessionId: number; messageId: null }
  | { type: 'token'; projectId: number; sessionId: number; messageId: null; chunk: string }
  | {
      type: 'stream_end'
      projectId: number
      sessionId: number
      messageId: number
      content: string
    }
  | {
      type: 'error'
      projectId: number
      sessionId: number
      messageId: null
      error: string
      message: string
    }
  | {
      type: 'stream_cancelled'
      projectId: number
      sessionId: number
      messageId: null
      message: string
    }

/**
 * 202 response from `POST .../sessions/:sid/messages`. The assistant id is
 * always null here - the SPA learns it from the `stream_end` SSE event.
 */
export interface ChatSendMessageResponse {
  userMessageId: number
  assistantMessageId: null
  sessionId: number
  streamUrl: string
}

/**
 * 202 response from `POST .../sessions/:sid/cancel`. `cancelledMessageId` is
 * always null in v1 - the assistant id is only assigned at stream_end.
 */
export interface ChatCancelResponse {
  sessionId: number
  cancelledMessageId: null
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
  id: number
  projectId: number
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
 * Project information for the config page. Mirrors the backend
 * `ProjectInfoResponse` (canonical snake_case field names from
 * `core/config/schemas/project_config.py::ProjectConfig`). Only
 * `companyName`, `departmentName`, and `abbreviation` are mutable
 * via PATCH; everything else is read-only display.
 */
export interface ProjectInfo {
  id: number
  name: string
  code: string
  companyName: string
  departmentName: string
  abbreviation: string
  createdAt: string
  /** Read-only derived data */
  path: string
  repoCount: number
  findingCount: number
}

/** PATCH body for `useUpdateProjectInfo` - only the three mutable fields. */
export interface ProjectInfoUpdate {
  companyName?: string
  departmentName?: string
  abbreviation?: string
}

/**
 * PATCH body for `useUpdateRepoAuth`. Mirrors the backend
 * `RepoAuthPatchRequest`. All fields optional; provided values
 * overwrite the auth block. Write-only - never echoed by GET.
 */
export interface RepositoryAuthUpdate {
  loginUrl?: string
  usernameField?: string
  passwordField?: string
  extraFields?: Record<string, string>
  credentialsEnv?: string
  username?: string
  password?: string
}
