export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info'
export type Status = 'open' | 'triaged' | 'fixed' | 'wontfix' | 'false_positive'
export type Domain = 'sast' | 'web' | 'secrets' | 'sca'

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'HEAD' | 'OPTIONS'

/**
 * Free-form string on purpose — analysts may target protocols we don't know
 * about yet (ws/wss, ftp, smb, sip, coap, ...). Backend is the source of truth.
 */
export type UrlProtocol = string

/**
 * A single URL entry in a URL list. Kept flat + flexible so we can add columns
 * later without a migration — any extra metadata the backend returns lands in
 * `extras` and can be surfaced in the detail panel or as new columns.
 */
export interface UrlEntry {
  id: string
  projectId: string
  method: HttpMethod
  protocol: UrlProtocol
  /** Bare host, no protocol, no port, no trailing slash. e.g. "api.example.com" */
  host: string
  /** Numeric port (80, 443, 8080, ...) */
  port: number
  /** Path portion starting with "/". e.g. "/foo/bar/123" */
  path: string
  /** Any additional backend-provided metadata. */
  extras?: Record<string, string | number | boolean | null>
}

export interface Finding {
  id: string
  domain: Domain
  severity: Severity
  status: Status
  title: string
  tool: string
  target: string
  file?: string
  line?: number
  cwe?: string
  /** Short (7-char) git commit hash that introduced / last touched this finding. */
  commitHash?: string
  /** Free-form analyst notes — editable in the detail panel. */
  notes?: string
  projectId: string
  discoveredAt: string
}

export interface Project {
  id: string
  name: string
  code: string
}

export interface Scan {
  id: string
  projectId: string
  domain: Domain
  tool: string
  status: 'queued' | 'running' | 'done' | 'failed'
  startedAt: string
  finishedAt?: string
  findingsCount?: number
  /** Only present when status === 'running'. Describes the current work unit. */
  currentSegment?: string
  /** 0-100, streamed via WS when running. */
  progress?: number
  /** E.g. "3 / 14 repositories", "1.2k / 5.0k URLs". */
  segmentLabel?: string
}

// ─── Detailed Scan Run Types ────────────────────────────────────────────────
// Used by the Scans page for the live log stream and history view.

export type ScanRunStatus = 'idle' | 'running' | 'completed' | 'cancelled' | 'failed'

// ─── Scan Configuration Types ───────────────────────────────────────────────
// Used by the Scans page for advanced scan options.

/** A repository configured for scanning in the project. */
export interface ConfiguredRepo {
  id: string
  name: string
  /** e.g., "github", "gitlab", "local" */
  source: string
  /** URL or local path */
  location: string
}

/** A scanning tool available for the project. */
export interface ConfiguredTool {
  id: string
  name: string
  domain: Domain
  /** Whether this tool is enabled by default for scans */
  enabled: boolean
}

/** Scan options passed to the backend when starting a scan. */
export interface ScanOptions {
  /** Scope to specific repos (ids). If omitted, scan all repos. */
  repoIds?: string[]
  /** Run only these tools (ids). If omitted, run all enabled tools. */
  toolIds?: string[]
  /** Filter by domain(s). If omitted, run all domains. */
  domains?: Domain[]
  /** Exclude these tools (ids) from an otherwise full scan. */
  skipToolIds?: string[]
  /** Skip LLM enrichment step. */
  skipEnrichment?: boolean
}

/** Project scan configuration fetched from the server. */
export interface ProjectScanConfig {
  repos: ConfiguredRepo[]
  tools: ConfiguredTool[]
  domains: Domain[]
}

export interface ToolRun {
  id: string
  runId: string
  tool: string
  repo: string
  segment: Domain
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
  segments: Domain[]
  /** Tools explicitly selected (empty = all enabled). */
  tools: string[]
  /** Live log of tool runs, updated via simulated WS. */
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

export interface ScanLogEvent {
  id: string
  runId: string
  type: ScanLogEventType
  timestamp: string
  segment?: Domain
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
  segment: Domain
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

export interface TriageLogEvent {
  id: string
  runId: string
  type: TriageLogEventType
  timestamp: string
  batchId?: string
  segment?: Domain
  message: string
  findingsCount?: number
  processedCount?: number
  totalCount?: number
  attempt?: number
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

export type ChatStreamEventType = 'stream_start' | 'token' | 'stream_end' | 'error'

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
