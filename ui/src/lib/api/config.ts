/**
 * API Configuration
 * =================
 * Central configuration for all API endpoints.
 *
 * TODO [BACKEND]: Update API_BASE_URL to point to your FastAPI server.
 * In development this might be "http://localhost:8000/api/v1".
 * In production, use a relative path "/api/v1" if FastAPI serves the SPA,
 * or the full URL if they're on different domains.
 */

export const API_BASE_URL = '/api/v1'

/**
 * SSE endpoint paths (relative to API_BASE_URL).
 *
 * TODO [BACKEND]: Implement these SSE endpoints in FastAPI.
 * Each should return `text/event-stream` with JSON-encoded event data.
 *
 * Expected event format:
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
  /** SSE stream for triage run events. Query param: ?runId=<id> or ?projectId=<id> */
  triageEvents: `${API_BASE_URL}/triage/events`,
  /** SSE stream for report generation events. Query param: ?runId=<id> */
  reportEvents: `${API_BASE_URL}/reports/events`,
  /**
   * SSE stream for chat responses. Query param: ?sessionId=<id>
   * Events: stream_start, token (word-by-word), stream_end, error
   */
  chatStream: `${API_BASE_URL}/chat/stream`,
  /**
   * Project-scoped SSE stream emitting `finding_updated` events. Tail-only
   * (no snapshot on connect — the SPA already holds the canonical list from
   * GET /findings). Heartbeat every 15s when idle.
   */
  findingsEvents: (projectId: string | number) =>
    `${API_BASE_URL}/projects/${projectId}/findings/events`,
} as const

/**
 * REST endpoint paths (relative to API_BASE_URL).
 *
 * TODO [BACKEND]: Implement these REST endpoints in FastAPI.
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
  /** GET: list triage runs for a project */
  triageRuns: (projectId: string) => `${API_BASE_URL}/projects/${projectId}/triage`,
  /** GET: single triage run with batches */
  triageRun: (projectId: string, scanRunId: string) =>
    `${API_BASE_URL}/projects/${projectId}/triage/${scanRunId}`,
  /** GET: currently-running triage for a project (or null) */
  activeTriage: (projectId: string) => `${API_BASE_URL}/projects/${projectId}/triage/active`,
  /** GET: most-recent triage run summary for a project */
  latestTriage: (projectId: string) => `${API_BASE_URL}/projects/${projectId}/triage/latest`,
  /** POST: start a new triage run (optionally with specific finding IDs) */
  startTriage: (projectId: string) => `${API_BASE_URL}/projects/${projectId}/triage`,
  /** POST: cancel a running triage */
  cancelTriage: (projectId: string, scanRunId: string) =>
    `${API_BASE_URL}/projects/${projectId}/triage/${scanRunId}/cancel`,
  /** POST: resume a failed/stranded triage run */
  resumeTriage: (projectId: string, scanRunId: string) =>
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
  reportDrafts: (projectId: string) => `${API_BASE_URL}/projects/${projectId}/reports/drafts`,
  /** POST: generate a draft for a specific section. Body: { section, force?: boolean } */
  generateDraft: (projectId: string) => `${API_BASE_URL}/projects/${projectId}/reports/drafts`,
  /** GET: download a draft section content. Returns text/markdown */
  downloadDraft: (projectId: string, section: string) =>
    `${API_BASE_URL}/projects/${projectId}/reports/drafts/${section}/download`,
  /** GET: list previously generated reports (history) */
  reportHistory: (projectId: string) => `${API_BASE_URL}/projects/${projectId}/reports`,
  /** POST: generate a full report. Body: { format, testingType?, engagementDate, outputPath? } */
  generateReport: (projectId: string) => `${API_BASE_URL}/projects/${projectId}/reports/generate`,
  /** GET: download a generated report by ID */
  downloadReport: (reportId: string) => `${API_BASE_URL}/reports/${reportId}/download`,

  // ─── Chat ───────────────────────────────────────────────────────────────────
  /** GET: list chat sessions for a project */
  chatSessions: (projectId: string) => `${API_BASE_URL}/projects/${projectId}/chat/sessions`,
  /** POST: create a new chat session */
  createChatSession: (projectId: string) => `${API_BASE_URL}/projects/${projectId}/chat/sessions`,
  /** GET: list messages in a chat session */
  chatMessages: (sessionId: string) => `${API_BASE_URL}/chat/sessions/${sessionId}/messages`,
  /** POST: send a message and start streaming response. Body: { content: string } */
  sendChatMessage: (sessionId: string) => `${API_BASE_URL}/chat/sessions/${sessionId}/messages`,
  /** POST: cancel an in-progress chat response */
  cancelChatResponse: (sessionId: string) => `${API_BASE_URL}/chat/sessions/${sessionId}/cancel`,
  /** DELETE: delete a chat session */
  deleteChatSession: (sessionId: string) => `${API_BASE_URL}/chat/sessions/${sessionId}`,

  // ─── Configuration ──────────────────────────────────────────────────────────
  /** GET: project info for config page */
  projectInfo: (projectId: string) => `${API_BASE_URL}/projects/${projectId}/info`,
  /** PATCH: update project info */
  updateProjectInfo: (projectId: string) => `${API_BASE_URL}/projects/${projectId}/info`,
  /** GET: list repositories for a project */
  repositories: (projectId: string) => `${API_BASE_URL}/projects/${projectId}/repositories`,
  /** GET: single repository config */
  repository: (projectId: string, repoId: string) =>
    `${API_BASE_URL}/projects/${projectId}/repositories/${repoId}`,
  /** POST: create a new repository */
  createRepository: (projectId: string) => `${API_BASE_URL}/projects/${projectId}/repositories`,
  /** PATCH: update a repository */
  updateRepository: (projectId: string, repoId: string) =>
    `${API_BASE_URL}/projects/${projectId}/repositories/${repoId}`,
  /** DELETE: delete a repository */
  deleteRepository: (projectId: string, repoId: string) =>
    `${API_BASE_URL}/projects/${projectId}/repositories/${repoId}`,
  /** GET: tool catalog (available tools that can be overridden) */
  toolCatalog: `${API_BASE_URL}/tools/catalog`,
  /** GET: list tool overrides for a project */
  toolOverrides: (projectId: string) => `${API_BASE_URL}/projects/${projectId}/tools/overrides`,
  /** POST: create a tool override */
  createToolOverride: (projectId: string) =>
    `${API_BASE_URL}/projects/${projectId}/tools/overrides`,
  /** PUT: update a tool override */
  updateToolOverride: (projectId: string, toolId: string) =>
    `${API_BASE_URL}/projects/${projectId}/tools/overrides/${toolId}`,
  /** DELETE: remove a tool override (reverts to global) */
  deleteToolOverride: (projectId: string, toolId: string) =>
    `${API_BASE_URL}/projects/${projectId}/tools/overrides/${toolId}`,
} as const
