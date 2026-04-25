/**
 * useTriage Hooks
 * ===============
 * Fetches triage run history and provides mutations for starting/stopping triage.
 * Also provides SSE subscription for live triage events.
 *
 * TODO [BACKEND]: Replace mock data with actual API calls and SSE stream.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useCallback, useRef } from 'react'
import type { TriageRun, TriageLogEvent } from '../types'
import { SSE_ENDPOINTS } from './config'

/**
 * useTriageHistory Hook
 * =====================
 * Fetches triage run history for a project.
 *
 * Expected API response (GET /api/v1/projects/:id/triage):
 * ```json
 * {
 *   "runs": [
 *     {
 *       "id": "TR-100",
 *       "projectId": "1",
 *       "status": "completed",
 *       "startedAt": "2024-01-15T10:00:00Z",
 *       "finishedAt": "2024-01-15T10:15:00Z",
 *       "totalFindings": 45,
 *       "processedFindings": 45,
 *       "batches": [...]
 *     },
 *     ...
 *   ]
 * }
 * ```
 */
export function useTriageHistory(projectId: string) {
  return useQuery({
    queryKey: ['triage', projectId],
    queryFn: async (): Promise<TriageRun[]> => {
      // ┌────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Replace mock with fetch()                         │
      // │                                                                    │
      // │ const res = await fetch(REST_ENDPOINTS.triageRuns(projectId))     │
      // │ if (!res.ok) throw new Error("Failed to fetch triage history")    │
      // │ const data = await res.json()                                     │
      // │ return data.runs                                                  │
      // └────────────────────────────────────────────────────────────────────┘

      await new Promise(r => setTimeout(r, 100))
      // Mock: No historical triage runs in prototype.
      return []
    },
    staleTime: 10 * 1000,
    enabled: Boolean(projectId),
  })
}

/**
 * useStartTriage Mutation
 * =======================
 * Starts a new triage run for a project.
 *
 * Expected API request (POST /api/v1/projects/:id/triage):
 * ```json
 * {
 *   "findingIds": ["F-1000", "F-1001"],  // optional, default = all open findings
 *   "dryRun": false,                      // optional, render prompts only
 *   "batchOnly": false                    // optional, create batches but don't invoke Claude
 * }
 * ```
 *
 * Expected API response:
 * ```json
 * {
 *   "runId": "TR-123",
 *   "status": "running",
 *   "startedAt": "2024-01-15T10:00:00Z",
 *   "totalFindings": 45,
 *   "batchCount": 5
 * }
 * ```
 */
export function useStartTriage() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      projectId: _projectId,
      options: _options,
    }: {
      projectId: string
      options?: {
        findingIds?: string[]
        dryRun?: boolean
        batchOnly?: boolean
      }
    }) => {
      // ┌────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Replace mock with fetch()                         │
      // │                                                                    │
      // │ const res = await fetch(REST_ENDPOINTS.startTriage(projectId), {  │
      // │   method: "POST",                                                 │
      // │   headers: { "Content-Type": "application/json" },                │
      // │   body: JSON.stringify(options ?? {}),                            │
      // │ })                                                                │
      // │ if (!res.ok) throw new Error("Failed to start triage")            │
      // │ return res.json()                                                 │
      // └────────────────────────────────────────────────────────────────────┘

      await new Promise(r => setTimeout(r, 200))
      return {
        runId: `TR-${Date.now()}`,
        status: 'running' as const,
        startedAt: new Date().toISOString(),
        totalFindings: 45,
        batchCount: 5,
      }
    },
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['triage', projectId] })
    },
  })
}

/**
 * useCancelTriage Mutation
 * ========================
 * Cancels a running triage.
 *
 * Expected API request (POST /api/v1/triage/:id/cancel):
 * No body required.
 *
 * Expected API response:
 * ```json
 * { "status": "cancelled" }
 * ```
 */
export function useCancelTriage() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (_runId: string) => {
      // ┌────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Replace mock with fetch()                         │
      // │                                                                    │
      // │ const res = await fetch(REST_ENDPOINTS.cancelTriage(runId), {     │
      // │   method: "POST",                                                 │
      // │ })                                                                │
      // │ if (!res.ok) throw new Error("Failed to cancel triage")           │
      // │ return res.json()                                                 │
      // └────────────────────────────────────────────────────────────────────┘

      await new Promise(r => setTimeout(r, 100))
      return { status: 'cancelled' as const }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['triage'] })
    },
  })
}

/**
 * useTriageEvents Hook (SSE)
 * ==========================
 * Subscribes to server-sent events for live triage progress.
 *
 * TODO [BACKEND]: Implement SSE endpoint at /api/v1/triage/events
 *
 * Expected SSE event format:
 * ```
 * event: batch_started
 * data: {"runId":"TR-123","batchId":"B-1","segment":"sast","findingsCount":10}
 *
 * event: batch_progress
 * data: {"runId":"TR-123","batchId":"B-1","processedCount":5,"totalCount":10}
 *
 * event: batch_completed
 * data: {"runId":"TR-123","batchId":"B-1","findingsCount":10}
 *
 * event: batch_failed
 * data: {"runId":"TR-123","batchId":"B-1","error":"Claude rate limit","attempt":2}
 *
 * event: run_completed
 * data: {"runId":"TR-123","totalProcessed":45}
 * ```
 *
 * Event types: see TriageLogEventType in types.ts
 */
export function useTriageEvents(
  projectId: string,
  onEvent: (event: TriageLogEvent) => void,
  enabled = true
) {
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  const connect = useCallback((): EventSource | null => {
    if (!enabled || !projectId) return null

    // ┌────────────────────────────────────────────────────────────────────────┐
    // │ TODO [BACKEND]: Uncomment this SSE connection code.                   │
    // │                                                                        │
    // │ const url = `${SSE_ENDPOINTS.triageEvents}?projectId=${projectId}`    │
    // │ const eventSource = new EventSource(url)                              │
    // │                                                                        │
    // │ // Listen for all event types defined in TriageLogEventType           │
    // │ const eventTypes = [                                                  │
    // │   "run_started", "batch_created", "batch_started", "batch_progress",  │
    // │   "batch_completed", "batch_failed", "batch_retry",                   │
    // │   "run_completed", "run_cancelled"                                    │
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
    // │   console.error("[SSE] Triage events error:", err)                    │
    // │   eventSource.close()                                                 │
    // │ }                                                                     │
    // │                                                                        │
    // │ return eventSource                                                    │
    // └────────────────────────────────────────────────────────────────────────┘

    // MOCK: No SSE in prototype. Events are simulated in the Triage page.
    console.warn(`[MOCK SSE] Would connect to ${SSE_ENDPOINTS.triageEvents}?projectId=${projectId}`)
    return null
  }, [enabled, projectId])

  useEffect(() => {
    const eventSource: EventSource | null = connect()
    return () => {
      eventSource?.close()
    }
  }, [connect])
}
