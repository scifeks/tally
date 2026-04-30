/**
 * API Configuration
 * =================
 * Central configuration for all API endpoints. The base path is a
 * relative `/api/v1` so the SPA is same-origin in production. In
 * development, Vite proxies `/api` to the FastAPI server (see
 * `vite.config.ts`, which reads `VITE_API_BASE_URL` from `.env.local`).
 */

export const API_BASE_URL = '/api/v1'

/**
 * SSE endpoint paths (relative to API_BASE_URL).
 *
 * Each endpoint returns `text/event-stream` with JSON-encoded event
 * data:
 *   event: <event_type>
 *   data: {"field": "value", ...}
 *
 * For scans:   event types match ScanLogEventType
 * For triage:  event types match TriageLogEventType
 */
export const SSE_ENDPOINTS = {
  /**
   * Project-scoped SSE stream for scan run events. Optional `?run_id=<id>`
   * query param filters to a single run; otherwise emits a `snapshot` of
   * `active_run_ids` on connect, then live events for any run in the project.
   */
  scanEvents: (projectId: number) => `${API_BASE_URL}/projects/${projectId}/scans/events`,
  /**
   * Project-scoped SSE stream for triage run events. Optional
   * `?scan_run_id=<id>` query param filters to a single triage run and
   * emits a snapshot of that run's batches on connect; otherwise emits a
   * project-scoped snapshot listing `active_scan_run_ids`.
   */
  triageEvents: (projectId: number) => `${API_BASE_URL}/projects/${projectId}/triage/events`,
  /**
   * Project-scoped SSE stream for full-report generation events. Optional
   * `?run_id=<id>` query param filters to a single run; otherwise emits a
   * project-level snapshot of the active generation (if any) on connect.
   */
  reportEvents: (projectId: number) => `${API_BASE_URL}/projects/${projectId}/reports/events`,
  /**
   * Project-scoped SSE stream for draft-section generation events. Optional
   * `?section=<section>` query param filters to a single section.
   */
  reportDraftEvents: (projectId: number) =>
    `${API_BASE_URL}/projects/${projectId}/reports/drafts/events`,
  /**
   * Project-scoped SSE stream for chat token events. Required query param
   * `?session_id=<id>`. Emits a `snapshot` frame on connect, then live
   * `stream_start` / `token` / `stream_end` / `error` / `stream_cancelled`
   * events for the requested session. Per endpoints.md §15.4.
   */
  chatStream: (projectId: number, sessionId: number) =>
    `${API_BASE_URL}/projects/${projectId}/chat/stream?session_id=${sessionId}`,
  /**
   * Project-scoped SSE stream emitting `finding_updated` events. Tail-only
   * (no snapshot on connect - the SPA already holds the canonical list from
   * GET /findings). Heartbeat every 15s when idle.
   */
  findingsEvents: (projectId: string | number) =>
    `${API_BASE_URL}/projects/${projectId}/findings/events`,
} as const

/**
 * REST endpoint paths (relative to API_BASE_URL).
 */
export const REST_ENDPOINTS = {
  // ─── Projects ───────────────────────────────────────────────────────────────
  /** GET: list all projects */
  projects: `${API_BASE_URL}/projects`,
  /** GET: single project by ID */
  project: (id: string) => `${API_BASE_URL}/projects/${id}`,
  /** GET: project metadata (repo count, url list count, enabled tools) */
  projectMeta: (id: string) => `${API_BASE_URL}/projects/${id}/meta`,

  // ─── Findings ───────────────────────────────────────────────────────────────
  /**
   * GET: paginated, filterable findings list for a project. Query params:
   * `severity`, `status`, `confidence`, `domain`, `tool`, `segment`,
   * `finding_type`, `repo_id`, `search`, `sort`, `order`, `offset`, `limit`.
   */
  findings: (projectId: string | number) => `${API_BASE_URL}/projects/${projectId}/findings`,
  /** GET: aggregate findings counts bucketed by severity, status, domain, segment, repo, tool */
  findingsCounts: (projectId: string | number) =>
    `${API_BASE_URL}/projects/${projectId}/findings/counts`,
  /**
   * GET: per-dimension filter options under the active filter set. Strict
   * semantics: each dimension's counts apply every active filter; zero-count
   * options are omitted. Powers the Findings filter dropdowns. Same query
   * params as `findings` (severity, status, confidence, domain, segment,
   * tool, finding_type, repo_id, search).
   */
  findingsFilterOptions: (projectId: string | number) =>
    `${API_BASE_URL}/projects/${projectId}/findings/filter-options`,
  /** GET: single finding by ID (project-scoped). */
  finding: (projectId: string | number, findingId: string | number) =>
    `${API_BASE_URL}/projects/${projectId}/findings/${findingId}`,
  /** PATCH: update finding fields (status, severity, notes, title, ...). */
  updateFinding: (projectId: string | number, findingId: string | number) =>
    `${API_BASE_URL}/projects/${projectId}/findings/${findingId}`,
  /** GET: audit trail (newest-first) for a single finding. */
  findingHistory: (projectId: string | number, findingId: string | number) =>
    `${API_BASE_URL}/projects/${projectId}/findings/${findingId}/history`,

  // ─── Scans ──────────────────────────────────────────────────────────────────
  /** GET: paginated scan history for a project. Query: status?, offset?, limit?. */
  scans: (projectId: number) => `${API_BASE_URL}/projects/${projectId}/scans`,
  /** GET: single scan by run ID (project-scoped). */
  scan: (projectId: number, runId: number) =>
    `${API_BASE_URL}/projects/${projectId}/scans/${runId}`,
  /**
   * GET: scan configuration for a project (available repos, tools, domains).
   * Used to populate advanced scan options UI.
   */
  scanConfig: (projectId: number) => `${API_BASE_URL}/projects/${projectId}/scans/config`,
  /**
   * POST: start a new scan run. Body is camelCase per `ScanStartRequest`:
   * `{ repoIds?, toolIds?, domains?, skipToolIds?, skipEnrichment? }`.
   */
  startScan: (projectId: number) => `${API_BASE_URL}/projects/${projectId}/scans`,
  /** POST: cancel a running scan (project-scoped). */
  cancelScan: (projectId: number, runId: number) =>
    `${API_BASE_URL}/projects/${projectId}/scans/${runId}/cancel`,

  // ─── Triage ─────────────────────────────────────────────────────────────────
  /** GET: paginated triage run history for a project. Query: offset?, limit?. */
  triageRuns: (projectId: number) => `${API_BASE_URL}/projects/${projectId}/triage`,
  /** GET: single triage run with batches */
  triageRun: (projectId: number, scanRunId: number) =>
    `${API_BASE_URL}/projects/${projectId}/triage/${scanRunId}`,
  /** GET: currently-running triage for a project (or null) */
  activeTriage: (projectId: number) => `${API_BASE_URL}/projects/${projectId}/triage/active`,
  /** GET: most-recent triage run summary for a project */
  latestTriage: (projectId: number) => `${API_BASE_URL}/projects/${projectId}/triage/latest`,
  /** POST: start a new triage run. Body must include `acknowledge_injection_risk: true`. */
  startTriage: (projectId: number) => `${API_BASE_URL}/projects/${projectId}/triage`,
  /** POST: cancel a running triage */
  cancelTriage: (projectId: number, scanRunId: number) =>
    `${API_BASE_URL}/projects/${projectId}/triage/${scanRunId}/cancel`,
  /** POST: resume a failed/stranded triage run. Body must include `acknowledge_injection_risk: true`. */
  resumeTriage: (projectId: number, scanRunId: number) =>
    `${API_BASE_URL}/projects/${projectId}/triage/${scanRunId}/resume`,

  // ─── Runtime / Tools (cross-project) ────────────────────────────────────────
  /** GET: probe status for each registered runtime dependency */
  runtimeDependencies: `${API_BASE_URL}/runtime-dependencies`,
  /** GET: tool wrappers whose binary was probed at process startup */
  installedTools: `${API_BASE_URL}/tools/installed`,

  // ─── URL Lists ──────────────────────────────────────────────────────────────
  /**
   * GET: paginated URL entries for a project. Query params: `search`, `method`,
   * `repo_id`, `source` (`scan|user`), `tool` (`katana|noir`), `sort`
   * (`host|path|method|port`), `order`, `offset`, `limit` (default 100, max 500).
   */
  urlListEntries: (projectId: string | number) =>
    `${API_BASE_URL}/projects/${projectId}/url-list/entries`,

  // ─── Reports ────────────────────────────────────────────────────────────────
  /** GET: list draft sections and their statuses for a project */
  reportDrafts: (projectId: number) => `${API_BASE_URL}/projects/${projectId}/reports/drafts`,
  /** POST: generate a draft for a specific section. Body: { section, force?: boolean } */
  generateDraft: (projectId: number) => `${API_BASE_URL}/projects/${projectId}/reports/drafts`,
  /** GET: download a draft section content. Returns text/markdown */
  downloadDraft: (projectId: number, section: string) =>
    `${API_BASE_URL}/projects/${projectId}/reports/drafts/${section}/download`,
  /** POST (multipart): upload a reviewed draft section to replace the generated version */
  uploadDraft: (projectId: number) => `${API_BASE_URL}/projects/${projectId}/reports/drafts/upload`,
  /** DELETE: remove a draft section, resetting it to `not_generated` */
  deleteDraft: (projectId: number, section: string) =>
    `${API_BASE_URL}/projects/${projectId}/reports/drafts/${section}`,
  /** GET: list previously generated reports (history). Query: offset?, limit?. */
  reportHistory: (projectId: number) => `${API_BASE_URL}/projects/${projectId}/reports`,
  /** GET: most recently generated report for a project (or null) */
  latestReport: (projectId: number) => `${API_BASE_URL}/projects/${projectId}/reports/latest`,
  /** POST: generate a full report. Body uses snake_case wire format. */
  generateReport: (projectId: number) => `${API_BASE_URL}/projects/${projectId}/reports/generate`,
  /** POST: cancel an in-progress report generation run */
  cancelReport: (projectId: number, reportId: number) =>
    `${API_BASE_URL}/projects/${projectId}/reports/${reportId}/cancel`,
  /** GET: download a generated report file (project-scoped) */
  downloadReport: (projectId: number, reportId: number) =>
    `${API_BASE_URL}/projects/${projectId}/reports/${reportId}/download`,

  // ─── Chat ───────────────────────────────────────────────────────────────────
  /** GET: paginated chat sessions for a project. Query: offset?, limit?. */
  chatSessions: (projectId: number) => `${API_BASE_URL}/projects/${projectId}/chat/sessions`,
  /** POST: create a new chat session (empty body; server-set timestamp title). */
  createChatSession: (projectId: number) => `${API_BASE_URL}/projects/${projectId}/chat/sessions`,
  /** DELETE: hard-delete a chat session and its messages. */
  deleteChatSession: (projectId: number, sessionId: number) =>
    `${API_BASE_URL}/projects/${projectId}/chat/sessions/${sessionId}`,
  /** GET: paginated messages in a chat session, oldest-first. */
  chatMessages: (projectId: number, sessionId: number) =>
    `${API_BASE_URL}/projects/${projectId}/chat/sessions/${sessionId}/messages`,
  /** POST: send a user message and start the streaming assistant response. */
  sendChatMessage: (projectId: number, sessionId: number) =>
    `${API_BASE_URL}/projects/${projectId}/chat/sessions/${sessionId}/messages`,
  /** POST: cancel an in-flight assistant response stream. */
  cancelChatResponse: (projectId: number, sessionId: number) =>
    `${API_BASE_URL}/projects/${projectId}/chat/sessions/${sessionId}/cancel`,

  // ─── Configuration ──────────────────────────────────────────────────────────
  /** GET: project info for config page */
  projectInfo: (projectId: number) => `${API_BASE_URL}/projects/${projectId}/info`,
  /** PATCH: update project info */
  updateProjectInfo: (projectId: number) => `${API_BASE_URL}/projects/${projectId}/info`,
  /** GET: list repositories for a project */
  repositories: (projectId: number) => `${API_BASE_URL}/projects/${projectId}/repositories`,
  /** GET: single repository config */
  repository: (projectId: number, repoId: number) =>
    `${API_BASE_URL}/projects/${projectId}/repositories/${repoId}`,
  /** POST (multipart): create a new repository */
  createRepository: (projectId: number) => `${API_BASE_URL}/projects/${projectId}/repositories`,
  /** PATCH (multipart): update a repository */
  updateRepository: (projectId: number, repoId: number) =>
    `${API_BASE_URL}/projects/${projectId}/repositories/${repoId}`,
  /** DELETE: delete a repository */
  deleteRepository: (projectId: number, repoId: number) =>
    `${API_BASE_URL}/projects/${projectId}/repositories/${repoId}`,
  /** PATCH: update a repository's write-only auth block */
  repositoryAuth: (projectId: number, repoId: number) =>
    `${API_BASE_URL}/projects/${projectId}/repositories/${repoId}/auth`,
  /** GET: tool catalog (available tools that can be overridden) */
  toolCatalog: `${API_BASE_URL}/tools/catalog`,
  /** GET: list tool overrides for a project */
  toolOverrides: (projectId: number) => `${API_BASE_URL}/projects/${projectId}/tools/overrides`,
  /** POST: create a tool override */
  createToolOverride: (projectId: number) =>
    `${API_BASE_URL}/projects/${projectId}/tools/overrides`,
  /** PUT: update a tool override */
  updateToolOverride: (projectId: number, toolId: string) =>
    `${API_BASE_URL}/projects/${projectId}/tools/overrides/${toolId}`,
  /** DELETE: remove a tool override (reverts to global) */
  deleteToolOverride: (projectId: number, toolId: string) =>
    `${API_BASE_URL}/projects/${projectId}/tools/overrides/${toolId}`,
} as const
