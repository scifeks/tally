/**
 * Triage hooks: project-scoped REST + SSE, paginated history, mutation
 * errors routed through the `triageMutationError` Zustand slice.
 */

import { useEffect, useMemo, useRef } from 'react'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type {
  ApiErrorPayload,
  Segment,
  TriageBatch,
  TriageBatchStatus,
  TriageLogEvent,
  TriageLogEventType,
  TriageRun,
  TriageRunStatus,
  TriageSnapshotPayload,
} from '../types'
import { ApiError, apiFetch } from './client'
import { apiEventSource } from './sse'
import { REST_ENDPOINTS, SSE_ENDPOINTS } from './config'
import { useUI } from '../store'

// Wire-format types

interface TriageBatchApi {
  id: number
  scan_run_id: number
  segment: string | null
  finding_ids: number[]
  status: string
  attempts: number
  started_at: string | null
  finished_at: string | null
  response_preview: string | null
  error: string | null
}

interface TriageRunSummaryApi {
  scan_run_id: number
  project_id: number | null
  status: string
  started_at: string | null
  finished_at: string | null
  total_findings: number
  processed_findings: number
}

interface TriageRunDetailApi extends TriageRunSummaryApi {
  batches: TriageBatchApi[]
}

interface TriageHistoryResponseApi {
  items: TriageRunSummaryApi[]
  total: number
  offset: number
  limit: number
}

interface TriageCancelResponseApi {
  scan_run_id: number
  status: string
}

interface TriageEventPayloadApi {
  id: string
  scan_run_id: number
  project_id: number | null
  timestamp: string
  message?: string
  batch_id?: number
  segment?: string | null
  findings_count?: number
  processed_count?: number
  total_count?: number
  attempt?: number
  error?: string
  failed_at_finding_id?: number | null
  resumable?: boolean
  completed_count?: number
}

interface TriageSnapshotApi {
  project_id: number
  scan_run_id: number | null
  status?: string
  total_findings?: number
  processed_findings?: number
  started_at?: string | null
  finished_at?: string | null
  batches?: TriageBatchApi[]
  active_scan_run_ids?: number[]
}

// Mappers

export function mapTriageBatch(api: TriageBatchApi): TriageBatch {
  return {
    id: api.id,
    runId: api.scan_run_id,
    segment: (api.segment ?? null) as Segment | null,
    findingIds: api.finding_ids,
    status: api.status as TriageBatchStatus,
    attempts: api.attempts,
    startedAt: api.started_at,
    finishedAt: api.finished_at,
    responsePreview: api.response_preview,
    error: api.error,
  }
}

export function mapTriageRun(api: TriageRunSummaryApi | TriageRunDetailApi): TriageRun {
  const base: TriageRun = {
    scanRunId: api.scan_run_id,
    projectId: api.project_id ?? 0,
    status: api.status as TriageRunStatus,
    startedAt: api.started_at,
    finishedAt: api.finished_at,
    totalFindings: api.total_findings,
    processedFindings: api.processed_findings,
  }
  if ('batches' in api && api.batches) {
    base.batches = api.batches.map(mapTriageBatch)
  }
  return base
}

function mapTriageEvent(type: TriageLogEventType, data: TriageEventPayloadApi): TriageLogEvent {
  // For triage_failed the backend uses `completed_count` rather than
  // `processed_count`; surface it under the same FE field so the page can
  // render a uniform "X / Y" progress fragment regardless of event type.
  const processed = data.processed_count ?? data.completed_count
  return {
    id: data.id,
    scanRunId: data.scan_run_id,
    projectId: data.project_id ?? 0,
    type,
    timestamp: data.timestamp,
    batchId: data.batch_id,
    segment: data.segment ? (data.segment as Segment) : undefined,
    message: data.message ?? '',
    findingsCount: data.findings_count,
    processedCount: processed,
    totalCount: data.total_count,
    attempt: data.attempt,
    error: data.error,
    failedAtFindingId: data.failed_at_finding_id,
    resumable: data.resumable,
  }
}

function mapSnapshot(data: TriageSnapshotApi): TriageSnapshotPayload {
  if (data.scan_run_id === null) {
    return {
      projectId: data.project_id,
      scanRunId: null,
      activeScanRunIds: data.active_scan_run_ids ?? [],
    }
  }
  return {
    projectId: data.project_id,
    scanRunId: data.scan_run_id,
    status: (data.status ?? 'queued') as TriageRunStatus,
    totalFindings: data.total_findings ?? 0,
    processedFindings: data.processed_findings ?? 0,
    startedAt: data.started_at ?? null,
    finishedAt: data.finished_at ?? null,
    batches: (data.batches ?? []).map(mapTriageBatch),
  }
}

// History (paginated)────

export interface UseTriageHistoryOptions {
  limit?: number
}

interface TriageHistoryPage {
  items: TriageRun[]
  total: number
  offset: number
  limit: number
}

const HISTORY_PAGE_LIMIT = 20

function buildTriageHistoryUrl(projectId: number, offset: number, limit: number): string {
  const params = new URLSearchParams()
  params.set('offset', String(offset))
  params.set('limit', String(limit))
  return `${REST_ENDPOINTS.triageRuns(projectId)}?${params.toString()}`
}

export function useTriageHistory(projectId: number, options?: UseTriageHistoryOptions) {
  const limit = options?.limit ?? HISTORY_PAGE_LIMIT
  const query = useInfiniteQuery({
    queryKey: ['triage', projectId, 'history', { limit }] as const,
    initialPageParam: 0,
    queryFn: async ({ pageParam }): Promise<TriageHistoryPage> => {
      const url = buildTriageHistoryUrl(projectId, pageParam as number, limit)
      const data = await apiFetch<TriageHistoryResponseApi>(url)
      return {
        items: data.items.map(mapTriageRun),
        total: data.total,
        offset: data.offset,
        limit: data.limit,
      }
    },
    getNextPageParam: lastPage => {
      const next = lastPage.offset + lastPage.items.length
      return next < lastPage.total ? next : undefined
    },
    enabled: Boolean(projectId),
    staleTime: 10_000,
  })

  const items = useMemo(() => query.data?.pages.flatMap(p => p.items) ?? [], [query.data])
  const total = query.data?.pages[0]?.total ?? 0

  return {
    data: items,
    total,
    fetchNextPage: query.fetchNextPage,
    hasNextPage: query.hasNextPage ?? false,
    isFetchingNextPage: query.isFetchingNextPage,
    isLoading: query.isLoading,
    isPending: query.isPending,
    isError: query.isError,
    error: query.error,
    fetchStatus: query.fetchStatus,
    refetch: query.refetch,
    isSuccess: query.isSuccess,
  }
}

// Active / Latest / Detail

export function useActiveTriage(projectId: number) {
  return useQuery({
    queryKey: ['triage', projectId, 'active'],
    queryFn: async (): Promise<TriageRun | null> => {
      const data = await apiFetch<TriageRunSummaryApi | null>(
        REST_ENDPOINTS.activeTriage(projectId)
      )
      return data ? mapTriageRun(data) : null
    },
    enabled: Boolean(projectId),
    staleTime: 5_000,
    refetchInterval: query => (query.state.data != null ? 3_000 : false),
  })
}

export function useLatestTriage(projectId: number) {
  return useQuery({
    queryKey: ['triage', projectId, 'latest'],
    queryFn: async (): Promise<TriageRun | null> => {
      try {
        const data = await apiFetch<TriageRunSummaryApi>(REST_ENDPOINTS.latestTriage(projectId))
        return mapTriageRun(data)
      } catch (err) {
        // 404 = project has no triage history yet. Treat as a null result so
        // the caller doesn't have to special-case the error path.
        if (err instanceof ApiError && err.status === 404) {
          return null
        }
        throw err
      }
    },
    enabled: Boolean(projectId),
    staleTime: 10_000,
    retry: (failureCount, err) => {
      if (err instanceof ApiError && err.status === 404) return false
      return failureCount < 3
    },
  })
}

export function useTriageRun(
  projectId: number,
  scanRunId: number | null,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: ['triage', projectId, 'detail', scanRunId],
    queryFn: async (): Promise<TriageRun> => {
      try {
        const data = await apiFetch<TriageRunDetailApi>(
          REST_ENDPOINTS.triageRun(projectId, scanRunId as number)
        )
        return mapTriageRun(data)
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          return {
            scanRunId: scanRunId as number,
            projectId,
            status: 'queued' as TriageRunStatus,
            startedAt: null,
            finishedAt: null,
            totalFindings: 0,
            processedFindings: 0,
            batches: [],
          }
        }
        throw err
      }
    },
    enabled: (options?.enabled ?? true) && Boolean(projectId) && scanRunId !== null,
    staleTime: 5_000,
    retry: (failureCount, err) => {
      if (err instanceof ApiError && err.status === 404) return false
      return failureCount < 3
    },
  })
}

// Mutations

export interface StartTriageOptions {
  /**
   * Optional list of finding IDs to scope the triage to. When omitted, the
   * backend triages every untriaged finding from the latest scan_run.
   */
  findingIds?: number[]
  /**
   * Optional scan run ID to triage findings from. When omitted, the backend
   * triages findings from the latest scan run.
   */
  scanRunId?: number
}

function toErrorPayload(err: ApiError): ApiErrorPayload {
  return {
    code: err.code,
    message: err.message,
    details: err.details,
    status: err.status,
  }
}

export function useStartTriage() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setTriageMutationError)

  return useMutation<TriageRun, ApiError, { projectId: number; options?: StartTriageOptions }>({
    mutationFn: async ({ projectId, options }) => {
      const body: Record<string, unknown> = {
        acknowledge_injection_risk: true,
      }
      if (options?.findingIds && options.findingIds.length > 0) {
        body.finding_ids = options.findingIds
      }
      if (options?.scanRunId != null) {
        body.scan_run_id = options.scanRunId
      }
      const data = await apiFetch<TriageRunSummaryApi>(REST_ENDPOINTS.startTriage(projectId), {
        method: 'POST',
        body,
      })
      return mapTriageRun(data)
    },
    onError: err => setError(toErrorPayload(err)),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['triage', projectId] })
    },
  })
}

export function useCancelTriage() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setTriageMutationError)

  return useMutation<TriageCancelResponseApi, ApiError, { projectId: number; scanRunId: number }>({
    mutationFn: async ({ projectId, scanRunId }) => {
      return apiFetch<TriageCancelResponseApi>(REST_ENDPOINTS.cancelTriage(projectId, scanRunId), {
        method: 'POST',
      })
    },
    onError: err => setError(toErrorPayload(err)),
    onSuccess: (_, { projectId }) => {
      queryClient.setQueryData<TriageRun | null>(['triage', projectId, 'active'], prev =>
        prev ? { ...prev, status: 'cancelling' as TriageRunStatus } : prev
      )
      queryClient.invalidateQueries({
        queryKey: ['triage', projectId],
      })
    },
  })
}

export function useResumeTriage() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setTriageMutationError)

  return useMutation<TriageRun, ApiError, { projectId: number; scanRunId: number }>({
    mutationFn: async ({ projectId, scanRunId }) => {
      const data = await apiFetch<TriageRunSummaryApi>(
        REST_ENDPOINTS.resumeTriage(projectId, scanRunId),
        {
          method: 'POST',
          body: { acknowledge_injection_risk: true },
        }
      )
      return mapTriageRun(data)
    },
    onError: err => setError(toErrorPayload(err)),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['triage', projectId] })
    },
  })
}

// SSE consumer

const TRIAGE_EVENT_TYPES: readonly TriageLogEventType[] = [
  'run_started',
  'batch_created',
  'batch_started',
  'batch_progress',
  'batch_completed',
  'batch_failed',
  'batch_retry',
  'run_completed',
  'run_cancelled',
  'triage_failed',
] as const

export interface UseTriageEventsOptions {
  enabled?: boolean
  /**
   * Optional scan_run_id query param. When set, the snapshot frame on
   * connect is the run-scoped variant (with batches); otherwise it's the
   * project-scoped variant (with `activeScanRunIds`).
   */
  scanRunId?: number | null
  onSnapshot?: (snap: TriageSnapshotPayload) => void
}

export function useTriageEvents(
  projectId: number,
  onEvent: (event: TriageLogEvent) => void,
  options?: UseTriageEventsOptions
) {
  const enabled = options?.enabled ?? true
  const scanRunId = options?.scanRunId ?? null
  const onEventRef = useRef(onEvent)
  const onSnapshotRef = useRef(options?.onSnapshot)
  onEventRef.current = onEvent
  onSnapshotRef.current = options?.onSnapshot

  useEffect(() => {
    if (!enabled || !projectId) return
    let url = SSE_ENDPOINTS.triageEvents(projectId)
    if (scanRunId !== null) {
      url = `${url}?scan_run_id=${scanRunId}`
    }
    const handle = apiEventSource(url, {
      eventTypes: ['snapshot', ...TRIAGE_EVENT_TYPES],
      onEvent: (type, data) => {
        if (type === 'snapshot') {
          onSnapshotRef.current?.(mapSnapshot(data as TriageSnapshotApi))
          return
        }
        if ((TRIAGE_EVENT_TYPES as readonly string[]).includes(type)) {
          onEventRef.current(
            mapTriageEvent(type as TriageLogEventType, data as TriageEventPayloadApi)
          )
        }
      },
    })
    return () => handle.close()
  }, [projectId, enabled, scanRunId])
}
