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
  /** SSE stream for scan run events. Query param: ?runId=<id> or ?projectId=<id> */
  scanEvents: `${API_BASE_URL}/scans/events`,
  /** SSE stream for triage run events. Query param: ?runId=<id> or ?projectId=<id> */
  triageEvents: `${API_BASE_URL}/triage/events`,
  /** SSE stream for report generation events. Query param: ?runId=<id> */
  reportEvents: `${API_BASE_URL}/reports/events`,
  /**
   * SSE stream for chat responses. Query param: ?sessionId=<id>
   * Events: stream_start, token (word-by-word), stream_end, error
   */
  chatStream: `${API_BASE_URL}/chat/stream`,
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
  /** GET: list findings for a project. Query params: ?domain=<domain>&status=<status>&severity=<severity> */
  findings: (projectId: string) => `${API_BASE_URL}/projects/${projectId}/findings`,
  /** GET: single finding by ID */
  finding: (id: string) => `${API_BASE_URL}/findings/${id}`,
  /** PATCH: update finding fields (status, severity, notes, title) */
  updateFinding: (id: string) => `${API_BASE_URL}/findings/${id}`,

  // ─── Scans ──────────────────────────────────────────────────────────────────
  /** GET: list scan history for a project */
  scans: (projectId: string) => `${API_BASE_URL}/projects/${projectId}/scans`,
  /** GET: single scan by ID */
  scan: (id: string) => `${API_BASE_URL}/scans/${id}`,
  /**
   * GET: scan configuration for a project (available repos, tools, domains).
   * Used to populate advanced scan options UI.
   */
  scanConfig: (projectId: string) => `${API_BASE_URL}/projects/${projectId}/scans/config`,
  /**
   * POST: start a new scan run.
   * Body: { repoId?, toolIds?, domains?, skipToolIds?, skipEnrichment? }
   */
  startScan: (projectId: string) => `${API_BASE_URL}/projects/${projectId}/scans`,
  /** POST: cancel a running scan */
  cancelScan: (id: string) => `${API_BASE_URL}/scans/${id}/cancel`,

  // ─── Triage ─────────────────────────────────────────────────────────────────
  /** GET: list triage runs for a project */
  triageRuns: (projectId: string) => `${API_BASE_URL}/projects/${projectId}/triage`,
  /** GET: single triage run with batches */
  triageRun: (id: string) => `${API_BASE_URL}/triage/${id}`,
  /** POST: start a new triage run (optionally with specific finding IDs) */
  startTriage: (projectId: string) => `${API_BASE_URL}/projects/${projectId}/triage`,
  /** POST: cancel a running triage */
  cancelTriage: (id: string) => `${API_BASE_URL}/triage/${id}/cancel`,

  // ─── URL Lists ──────────────────────────────────────────────────────────────
  /** GET: URL entries for a project's URL list */
  urlLists: (projectId: string) => `${API_BASE_URL}/projects/${projectId}/url-lists`,

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
  repository: (repoId: string) => `${API_BASE_URL}/repositories/${repoId}`,
  /** POST: create a new repository */
  createRepository: (projectId: string) => `${API_BASE_URL}/projects/${projectId}/repositories`,
  /** PUT: update a repository */
  updateRepository: (repoId: string) => `${API_BASE_URL}/repositories/${repoId}`,
  /** DELETE: delete a repository */
  deleteRepository: (repoId: string) => `${API_BASE_URL}/repositories/${repoId}`,
  /** POST: auto-detect repo settings from local path */
  detectRepoSettings: (projectId: string) =>
    `${API_BASE_URL}/projects/${projectId}/repositories/detect`,
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
