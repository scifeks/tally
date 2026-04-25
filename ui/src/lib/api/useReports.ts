/**
 * Report API Hooks
 * ================
 * Hooks for report drafts, generation, and history.
 *
 * TODO [BACKEND]: Implement these FastAPI endpoints:
 *
 * GET  /api/v1/projects/{id}/reports/drafts
 *      Returns: { drafts: ReportDraft[] }
 *
 * POST /api/v1/projects/{id}/reports/drafts
 *      Body: { section: string, force?: boolean }
 *      Returns: { draft: ReportDraft }
 *      Triggers LLM draft generation for the specified section.
 *
 * GET  /api/v1/projects/{id}/reports/drafts/{section}/download
 *      Returns: text/markdown file content
 *
 * GET  /api/v1/projects/{id}/reports
 *      Returns: { reports: ReportHistoryEntry[] }
 *
 * POST /api/v1/projects/{id}/reports/generate
 *      Body: { format: "pdf"|"markdown"|"html"|"json", testingType?: string, engagementDate: string }
 *      Returns: { runId: string }
 *      Triggers full report generation. Progress streamed via SSE.
 *
 * GET  /api/v1/reports/{id}/download
 *      Returns: The generated report file (PDF, MD, HTML, or JSON)
 *
 * SSE  /api/v1/reports/events?runId={id}
 *      Event types: generation_started, step_started, step_completed, step_failed,
 *                   generation_completed, generation_failed, draft_started, draft_completed, draft_failed
 *      Data format: ReportLogEvent
 */

import { useCallback, useEffect, useState, useRef } from 'react'
import type {
  ReportDraft,
  ReportDraftSection,
  ReportHistoryEntry,
  ReportFormat,
  TestingType,
  ReportLogEvent,
  ReportGenerationStatus,
} from '../types'

// ─── Mock Data ──────────────────────────────────────────────────────────────

const MOCK_DRAFTS: Record<string, ReportDraft[]> = {
  '1': [
    {
      section: 'executive_summary',
      status: 'draft',
      generatedAt: '2025-03-15T10:30:00Z',
      wordCount: 450,
      preview:
        'This security assessment of ACME Platform identified several critical vulnerabilities that require immediate attention. The engagement covered both static analysis of source code repositories and dynamic testing of web application endpoints...',
    },
    {
      section: 'risk_level',
      status: 'reviewed',
      generatedAt: '2025-03-15T10:32:00Z',
      reviewedAt: '2025-03-15T14:00:00Z',
      wordCount: 280,
      preview:
        'Based on the findings identified during this assessment, the overall risk level is rated as HIGH. This rating reflects the presence of 3 critical vulnerabilities and 12 high-severity issues...',
    },
    {
      section: 'critical_issues',
      status: 'draft',
      generatedAt: '2025-03-15T10:35:00Z',
      wordCount: 1200,
      preview:
        'The following critical issues were identified and require immediate remediation:\n\n1. SQL Injection in User Authentication Module (TAL-001)\n2. Remote Code Execution via Deserialization (TAL-002)...',
    },
    { section: 'improvement_points', status: 'not_generated' },
    { section: 'scope_methodology', status: 'not_generated' },
    {
      section: 'general_recommendations',
      status: 'reviewed',
      generatedAt: '2025-03-14T16:00:00Z',
      reviewedAt: '2025-03-15T09:00:00Z',
      wordCount: 650,
      uploadedFilename: 'general_recommendations_v2.md',
      preview:
        'To improve the overall security posture of the ACME Platform, we recommend implementing the following measures:\n\n1. Adopt a Secure Development Lifecycle (SDL)...',
    },
  ],
  '2': [
    { section: 'executive_summary', status: 'not_generated' },
    { section: 'risk_level', status: 'not_generated' },
    { section: 'critical_issues', status: 'not_generated' },
    { section: 'improvement_points', status: 'not_generated' },
    { section: 'scope_methodology', status: 'not_generated' },
    { section: 'general_recommendations', status: 'not_generated' },
  ],
  '3': [
    { section: 'executive_summary', status: 'not_generated' },
    { section: 'risk_level', status: 'not_generated' },
    { section: 'critical_issues', status: 'not_generated' },
    { section: 'improvement_points', status: 'not_generated' },
    { section: 'scope_methodology', status: 'not_generated' },
    { section: 'general_recommendations', status: 'not_generated' },
  ],
}

const MOCK_HISTORY: Record<string, ReportHistoryEntry[]> = {
  '1': [
    {
      id: 'rpt-001',
      projectId: '1',
      filename: 'ACME-Platform-Security-Assessment-2025-03-10.pdf',
      format: 'pdf',
      generatedAt: '2025-03-10T14:30:00Z',
      sizeBytes: 2450000,
      downloadUrl: '#',
    },
    {
      id: 'rpt-002',
      projectId: '1',
      filename: 'ACME-Platform-Security-Assessment-2025-02-15.pdf',
      format: 'pdf',
      generatedAt: '2025-02-15T09:00:00Z',
      sizeBytes: 2100000,
      downloadUrl: '#',
    },
    {
      id: 'rpt-003',
      projectId: '1',
      filename: 'ACME-Platform-Findings-2025-03-10.json',
      format: 'json',
      generatedAt: '2025-03-10T14:35:00Z',
      sizeBytes: 185000,
      downloadUrl: '#',
    },
  ],
  '2': [
    {
      id: 'rpt-004',
      projectId: '2',
      filename: 'Atlas-API-Assessment-2025-03-01.pdf',
      format: 'pdf',
      generatedAt: '2025-03-01T11:00:00Z',
      sizeBytes: 980000,
      downloadUrl: '#',
    },
  ],
  '3': [],
}

// ─── Draft Hooks ────────────────────────────────────────────────────────────

/**
 * Fetch report drafts for a project.
 */
export function useReportDrafts(projectId: string | null) {
  const [data, setData] = useState<ReportDraft[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, _setError] = useState<Error | null>(null)

  useEffect(() => {
    if (!projectId) {
      setData([])
      setIsLoading(false)
      return
    }

    setIsLoading(true)

    // ┌────────────────────────────────────────────────────────────────────────┐
    // │ TODO [BACKEND]: Replace mock with fetch.                              │
    // │                                                                        │
    // │ const response = await fetch(REST_ENDPOINTS.reportDrafts(projectId))  │
    // │ const json = await response.json()                                    │
    // │ setData(json.drafts)                                                  │
    // └────────────────────────────────────────────────────────────────────────┘

    // Mock: simulate network delay
    const timer = setTimeout(() => {
      setData(MOCK_DRAFTS[projectId] ?? [])
      setIsLoading(false)
    }, 300)

    return () => clearTimeout(timer)
  }, [projectId])

  const refetch = useCallback(() => {
    if (!projectId) return
    setIsLoading(true)
    setTimeout(() => {
      setData(MOCK_DRAFTS[projectId] ?? [])
      setIsLoading(false)
    }, 300)
  }, [projectId])

  return { data, isLoading, error, refetch }
}

/**
 * Generate or regenerate a draft section.
 */
export function useGenerateDraft() {
  const [isLoading, setIsLoading] = useState(false)
  const [error, _setError] = useState<Error | null>(null)

  const generate = useCallback(
    async (
      projectId: string,
      section: ReportDraftSection,
      _force: boolean = false
    ): Promise<ReportDraft | null> => {
      setIsLoading(true)
      _setError(null)

      // ┌────────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Replace mock with fetch.                              │
      // │                                                                        │
      // │ const response = await fetch(REST_ENDPOINTS.generateDraft(projectId), {│
      // │   method: "POST",                                                     │
      // │   headers: { "Content-Type": "application/json" },                    │
      // │   body: JSON.stringify({ section, force }),                           │
      // │ })                                                                     │
      // │ const json = await response.json()                                    │
      // │ return json.draft                                                     │
      // └────────────────────────────────────────────────────────────────────────┘

      // Mock: simulate generation delay
      return new Promise(resolve => {
        setTimeout(
          () => {
            const draft: ReportDraft = {
              section,
              status: 'draft',
              generatedAt: new Date().toISOString(),
              wordCount: Math.floor(Math.random() * 800) + 200,
              preview: `[Generated content for ${section.replace(/_/g, ' ')}]...`,
            }
            setIsLoading(false)
            resolve(draft)
          },
          2000 + Math.random() * 2000
        )
      })
    },
    []
  )

  return { generate, isLoading, error }
}

// ─── History Hooks ──────────────────────────────────────────────────────────

/**
 * Fetch report generation history for a project.
 */
export function useReportHistory(projectId: string | null) {
  const [data, setData] = useState<ReportHistoryEntry[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, _setError] = useState<Error | null>(null)

  useEffect(() => {
    if (!projectId) {
      setData([])
      setIsLoading(false)
      return
    }

    setIsLoading(true)

    // ┌────────────────────────────────────────────────────────────────────────┐
    // │ TODO [BACKEND]: Replace mock with fetch.                              │
    // │                                                                        │
    // │ const response = await fetch(REST_ENDPOINTS.reportHistory(projectId)) │
    // │ const json = await response.json()                                    │
    // │ setData(json.reports)                                                 │
    // └────────────────────────────────────────────────────────────────────────┘

    const timer = setTimeout(() => {
      setData(MOCK_HISTORY[projectId] ?? [])
      setIsLoading(false)
    }, 300)

    return () => clearTimeout(timer)
  }, [projectId])

  const refetch = useCallback(() => {
    if (!projectId) return
    setIsLoading(true)
    setTimeout(() => {
      setData(MOCK_HISTORY[projectId] ?? [])
      setIsLoading(false)
    }, 300)
  }, [projectId])

  return { data, isLoading, error, refetch }
}

// ─── Generation Hooks ───────────────────────────────────────────────────────

export interface GenerateReportParams {
  format: ReportFormat
  testingType?: TestingType
  engagementDate: string
  outputPath?: string
}

/**
 * Trigger full report generation.
 */
export function useGenerateReport() {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const generate = useCallback(
    async (_projectId: string, _params: GenerateReportParams): Promise<string | null> => {
      setIsLoading(true)
      setError(null)

      // ┌────────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Replace mock with fetch.                              │
      // │                                                                        │
      // │ const response = await fetch(REST_ENDPOINTS.generateReport(projectId),│
      // │   {                                                                    │
      // │     method: "POST",                                                   │
      // │     headers: { "Content-Type": "application/json" },                  │
      // │     body: JSON.stringify(params),                                     │
      // │   }                                                                    │
      // │ )                                                                      │
      // │ const json = await response.json()                                    │
      // │ return json.runId                                                     │
      // └────────────────────────────────────────────────────────────────────────┘

      // Mock: return fake run ID after brief delay
      return new Promise(resolve => {
        setTimeout(() => {
          const runId = `run-${Date.now()}`
          setIsLoading(false)
          resolve(runId)
        }, 500)
      })
    },
    []
  )

  return { generate, isLoading, error }
}

// ─── SSE Hook for Report Generation Events ──────────────────────────────────

/**
 * Subscribe to report generation events via SSE.
 */
export function useReportEvents({
  runId,
  enabled = true,
  onEvent,
}: {
  runId: string | null
  enabled?: boolean
  onEvent?: (event: ReportLogEvent) => void
}) {
  const [events, setEvents] = useState<ReportLogEvent[]>([])
  const [status, setStatus] = useState<ReportGenerationStatus>('idle')
  const [error, setError] = useState<Error | null>(null)
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  const connect = useCallback((): EventSource | null => {
    if (!enabled || !runId) return null

    // ┌────────────────────────────────────────────────────────────────────────┐
    // │ TODO [BACKEND]: Uncomment this SSE connection code.                   │
    // │                                                                        │
    // │ const es = new EventSource(`${SSE_ENDPOINTS.reportEvents}?runId=${runId}`)│
    // │                                                                        │
    // │ es.onmessage = (e) => {                                               │
    // │   const event: ReportLogEvent = JSON.parse(e.data)                    │
    // │   setEvents((prev) => [...prev, event])                               │
    // │   onEventRef.current?.(event)                                         │
    // │                                                                        │
    // │   if (event.type === "generation_completed") setStatus("completed")   │
    // │   if (event.type === "generation_failed") setStatus("failed")         │
    // │ }                                                                      │
    // │                                                                        │
    // │ es.onerror = () => {                                                  │
    // │   setError(new Error("SSE connection error"))                         │
    // │   es.close()                                                          │
    // │ }                                                                      │
    // │                                                                        │
    // │ return es                                                              │
    // └────────────────────────────────────────────────────────────────────────┘

    // Mock: no actual SSE connection
    return null
  }, [enabled, runId])

  useEffect(() => {
    const eventSource: EventSource | null = connect()
    return () => {
      eventSource?.close()
    }
  }, [connect])

  const reset = useCallback(() => {
    setEvents([])
    setStatus('idle')
    setError(null)
  }, [])

  return { events, status, setStatus, error, reset, setEvents }
}
