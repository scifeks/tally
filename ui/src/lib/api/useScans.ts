/**
 * useScans Hooks
 * ==============
 * Fetches scan history and provides mutations for starting/stopping scans.
 * Also provides SSE subscription for live scan events.
 *
 * TODO [BACKEND]: Replace mock data with actual API calls and SSE stream.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useCallback, useRef } from 'react'
import type { Scan, ScanLogEvent, ProjectScanConfig } from '../types'
import { SSE_ENDPOINTS } from './config'

// TODO [BACKEND]: Remove this mock import once API is connected.
import { scans as mockScans } from '../mock-data'

// ─── Mock Scan Config Data ─────────────────────────────────────────────────
// TODO [BACKEND]: Remove these mocks once API is connected.

const mockScanConfig: Record<string, ProjectScanConfig> = {
  '1': {
    repos: [
      { id: 'r-01', name: 'dvwa', source: 'github', location: 'github.com/digininja/DVWA' },
      { id: 'r-02', name: 'dvpwa', source: 'github', location: 'github.com/example/dvpwa' },
      {
        id: 'r-03',
        name: 'juice-shop',
        source: 'github',
        location: 'github.com/juice-shop/juice-shop',
      },
      { id: 'r-04', name: 'php-goof', source: 'gitlab', location: 'gitlab.com/example/php-goof' },
      { id: 'r-05', name: 'vuln-nodejs', source: 'local', location: '/opt/repos/vuln-nodejs' },
    ],
    tools: [
      { id: 't-01', name: 'semgrep', segment: 'sast', enabled: true },
      { id: 't-02', name: 'codeql', segment: 'sast', enabled: true },
      { id: 't-03', name: 'bandit', segment: 'sast', enabled: false },
      { id: 't-04', name: 'osv-scanner', segment: 'sca', enabled: true },
      { id: 't-05', name: 'npm-audit', segment: 'sca', enabled: true },
      { id: 't-06', name: 'pip-audit', segment: 'sca', enabled: true },
      { id: 't-07', name: 'composer-audit', segment: 'sca', enabled: false },
      { id: 't-08', name: 'zap', segment: 'web', enabled: true },
      { id: 't-09', name: 'nuclei', segment: 'web', enabled: true },
      { id: 't-10', name: 'nikto', segment: 'web', enabled: false },
      { id: 't-11', name: 'gitleaks', segment: 'secrets', enabled: true },
      { id: 't-12', name: 'trufflehog', segment: 'secrets', enabled: true },
    ],
    segments: ['sast', 'sca', 'web', 'secrets'],
  },
  '2': {
    repos: [
      { id: 'r-10', name: 'atl-api', source: 'github', location: 'github.com/atl/api' },
      { id: 'r-11', name: 'atl-web', source: 'github', location: 'github.com/atl/web' },
    ],
    tools: [
      { id: 't-01', name: 'semgrep', segment: 'sast', enabled: true },
      { id: 't-04', name: 'osv-scanner', segment: 'sca', enabled: true },
      { id: 't-08', name: 'zap', segment: 'web', enabled: true },
      { id: 't-11', name: 'gitleaks', segment: 'secrets', enabled: true },
    ],
    segments: ['sast', 'sca', 'web', 'secrets'],
  },
  '3': {
    repos: [],
    tools: [],
    segments: ['sast', 'sca', 'web', 'secrets'],
  },
}

/**
 * useProjectScanConfig Hook
 * =========================
 * Fetches scan configuration for a project (available repos, tools, domains).
 * Used to populate the advanced scan options UI.
 *
 * TODO [BACKEND]: Replace mock data with actual API call.
 *
 * Expected API response (GET /api/v1/projects/:id/scans/config):
 * ```json
 * {
 *   "repos": [
 *     { "id": "r-01", "name": "dvwa", "source": "github", "location": "github.com/..." }
 *   ],
 *   "tools": [
 *     { "id": "t-01", "name": "semgrep", "segment": "sast", "enabled": true }
 *   ],
 *   "segments": ["sast", "sca", "web", "secrets"]
 * }
 * ```
 */
export function useProjectScanConfig(projectId: string) {
  return useQuery({
    queryKey: ['scanConfig', projectId],
    queryFn: async (): Promise<ProjectScanConfig> => {
      // ┌────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Replace mock with fetch()                         │
      // │                                                                    │
      // │ const res = await fetch(REST_ENDPOINTS.scanConfig(projectId))     │
      // │ if (!res.ok) throw new Error("Failed to fetch scan config")       │
      // │ return res.json()                                                 │
      // └────────────────────────────────────────────────────────────────────┘

      return mockScanConfig[projectId] ?? { repos: [], tools: [], segments: [] }
    },
    staleTime: 5 * 60 * 1000,
    enabled: Boolean(projectId),
  })
}

/**
 * useScanHistory Hook
 * ===================
 * Fetches completed/failed scan history for a project.
 *
 * Expected API response (GET /api/v1/projects/:id/scans):
 * ```json
 * {
 *   "scans": [
 *     {
 *       "id": "S-2000",
 *       "projectId": "1",
 *       "segment": "sast",
 *       "tool": "semgrep",
 *       "status": "done",
 *       "startedAt": "2024-01-15T10:00:00Z",
 *       "finishedAt": "2024-01-15T10:08:00Z",
 *       "findingsCount": 23
 *     },
 *     ...
 *   ]
 * }
 * ```
 */
export function useScanHistory(projectId: string) {
  return useQuery({
    queryKey: ['scans', projectId],
    queryFn: async (): Promise<Scan[]> => {
      // ┌────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Replace mock with fetch()                         │
      // │                                                                    │
      // │ const res = await fetch(REST_ENDPOINTS.scans(projectId))          │
      // │ if (!res.ok) throw new Error("Failed to fetch scans")             │
      // │ const data = await res.json()                                     │
      // │ return data.scans                                                 │
      // └────────────────────────────────────────────────────────────────────┘

      await new Promise(r => setTimeout(r, 100))
      return mockScans.filter(s => s.projectId === projectId)
    },
    staleTime: 10 * 1000,
    enabled: Boolean(projectId),
  })
}

/**
 * useRunningScans Hook
 * ====================
 * Returns only currently running scans for a project.
 * Useful for the TopBar indicator and project switch blocking.
 */
export function useRunningScans(projectId: string) {
  const { data: scans = [] } = useScanHistory(projectId)
  return scans.filter(s => s.status === 'running')
}

/**
 * useStartScan Mutation
 * =====================
 * Starts a new scan run for a project.
 *
 * Expected API request (POST /api/v1/projects/:id/scans):
 * ```json
 * {
 *   "segments": ["sast", "web"], // optional, default = all
 *   "tools": ["semgrep"],        // optional, default = all enabled
 *   "repos": ["repo-name"]       // optional, default = all
 * }
 * ```
 *
 * Expected API response:
 * ```json
 * {
 *   "runId": "SR-123",
 *   "status": "running",
 *   "startedAt": "2024-01-15T10:00:00Z"
 * }
 * ```
 */
export function useStartScan() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      projectId: _projectId,
      options: _options,
    }: {
      projectId: string
      options?: {
        segments?: string[]
        tools?: string[]
        repos?: string[]
      }
    }) => {
      // ┌────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Replace mock with fetch()                         │
      // │                                                                    │
      // │ const res = await fetch(REST_ENDPOINTS.startScan(projectId), {    │
      // │   method: "POST",                                                 │
      // │   headers: { "Content-Type": "application/json" },                │
      // │   body: JSON.stringify(options ?? {}),                            │
      // │ })                                                                │
      // │ if (!res.ok) throw new Error("Failed to start scan")              │
      // │ return res.json()                                                 │
      // └────────────────────────────────────────────────────────────────────┘

      await new Promise(r => setTimeout(r, 200))
      return {
        runId: `SR-${Date.now()}`,
        status: 'running' as const,
        startedAt: new Date().toISOString(),
      }
    },
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['scans', projectId] })
    },
  })
}

/**
 * useCancelScan Mutation
 * ======================
 * Cancels a running scan.
 *
 * Expected API request (POST /api/v1/scans/:id/cancel):
 * No body required.
 *
 * Expected API response:
 * ```json
 * { "status": "cancelled" }
 * ```
 */
export function useCancelScan() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (_scanId: string) => {
      // ┌────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Replace mock with fetch()                         │
      // │                                                                    │
      // │ const res = await fetch(REST_ENDPOINTS.cancelScan(scanId), {      │
      // │   method: "POST",                                                 │
      // │ })                                                                │
      // │ if (!res.ok) throw new Error("Failed to cancel scan")             │
      // │ return res.json()                                                 │
      // └────────────────────────────────────────────────────────────────────┘

      await new Promise(r => setTimeout(r, 100))
      return { status: 'cancelled' as const }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scans'] })
    },
  })
}

/**
 * useScanEvents Hook (SSE)
 * ========================
 * Subscribes to server-sent events for live scan progress.
 *
 * TODO [BACKEND]: Implement SSE endpoint at /api/v1/scans/events
 *
 * Expected SSE event format:
 * ```
 * event: tool_started
 * data: {"runId":"SR-123","tool":"semgrep","repo":"acme-api","segment":"sast","message":"Starting semgrep on acme-api..."}
 *
 * event: tool_completed
 * data: {"runId":"SR-123","tool":"semgrep","repo":"acme-api","findingsCount":12,"duration":45}
 *
 * event: run_completed
 * data: {"runId":"SR-123","message":"Scan completed","totalFindings":87}
 * ```
 *
 * Event types: see ScanLogEventType in types.ts
 */
export function useScanEvents(
  projectId: string,
  onEvent: (event: ScanLogEvent) => void,
  enabled = true
) {
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  const connect = useCallback((): EventSource | null => {
    if (!enabled || !projectId) return null

    // ┌────────────────────────────────────────────────────────────────────────┐
    // │ TODO [BACKEND]: Uncomment this SSE connection code.                   │
    // │                                                                        │
    // │ const url = `${SSE_ENDPOINTS.scanEvents}?projectId=${projectId}`      │
    // │ const eventSource = new EventSource(url)                              │
    // │                                                                        │
    // │ // Listen for all event types defined in ScanLogEventType             │
    // │ const eventTypes = [                                                  │
    // │   "run_started", "segment_started", "tool_started", "tool_skipped",   │
    // │   "tool_completed", "tool_failed", "enrichment_progress",             │
    // │   "enrichment_complete", "segment_completed", "run_completed",        │
    // │   "run_cancelled"                                                     │
    // │ ]                                                                     │
    // │                                                                        │
    // │ eventTypes.forEach((type) => {                                        │
    // │   eventSource.addEventListener(type, (e) => {                         │
    // │     const data = JSON.parse(e.data)                                   │
    // │     onEventRef.current({ ...data, type, id: crypto.randomUUID() })    │
    // │   })                                                                  │
    // │ })                                                                    │
    // │                                                                        │
    // │ eventSource.onerror = (err) => {                                      │
    // │   console.error("[SSE] Scan events error:", err)                      │
    // │   eventSource.close()                                                 │
    // │ }                                                                     │
    // │                                                                        │
    // │ return eventSource                                                    │
    // └────────────────────────────────────────────────────────────────────────┘

    // MOCK: No SSE in prototype. Events are simulated in the Scans page.
    console.warn(`[MOCK SSE] Would connect to ${SSE_ENDPOINTS.scanEvents}?projectId=${projectId}`)
    return null
  }, [enabled, projectId])

  useEffect(() => {
    const eventSource: EventSource | null = connect()
    return () => {
      eventSource?.close()
    }
  }, [connect])
}
