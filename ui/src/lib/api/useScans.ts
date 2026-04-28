/**
 * useScans Hooks
 * ==============
 * Fetches scan history and provides mutations for starting/stopping scans.
 * Also provides SSE subscription for live scan events.
 */

import { useInfiniteQuery, useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, useMemo, useRef } from 'react'
import type {
  Scan,
  ScanLogEvent,
  ScanLogEventType,
  ProjectScanConfig,
  ConfiguredRepo,
  ConfiguredTool,
  Segment,
  ScanOptions,
  ApiErrorPayload,
} from '../types'
import { REST_ENDPOINTS, SSE_ENDPOINTS } from './config'
import type { ApiError } from './client'
import { apiFetch } from './client'
import { apiEventSource } from './sse'
import { useUI } from '../store'

// ─── Scan-config: wire-format types & inline mappers ────────────────────────

interface ScanConfigRepoApi {
  id: number
  uuid: string
  name: string
  source: string
  location: string | null
}

interface ScanConfigToolApi {
  id: string
  name: string
  domain: string
  enabled: boolean
}

interface ScanConfigResponseApi {
  repos: ScanConfigRepoApi[]
  tools: ScanConfigToolApi[]
  domains: string[]
}

function mapRepo(api: ScanConfigRepoApi): ConfiguredRepo {
  return {
    id: api.id,
    name: api.name,
    source: api.source,
    location: api.location ?? '',
  }
}

function mapTool(api: ScanConfigToolApi): ConfiguredTool {
  return {
    id: api.id,
    name: api.name,
    segment: api.domain as Segment,
    enabled: api.enabled,
  }
}

function mapScanConfig(api: ScanConfigResponseApi): ProjectScanConfig {
  return {
    repos: api.repos.map(mapRepo),
    tools: api.tools.map(mapTool),
    segments: api.domains as Segment[],
  }
}

// ─── Scan-history: wire-format types & inline mapper ────────────────────────

interface ScanRunSummaryApi {
  id: number
  project_id: number | null
  status: string | null
  started_at: string | null
  finished_at: string | null
  repo_ids: string[]
  tool_ids: string[]
  domains: string[]
  findings_count: number | null
  skip_enrichment: boolean
}

interface ScansListResponseApi {
  items: ScanRunSummaryApi[]
  total: number
  offset: number
  limit: number
}

function mapScan(api: ScanRunSummaryApi): Scan {
  return {
    id: api.id,
    projectId: api.project_id ?? 0,
    status: (api.status ?? 'queued') as Scan['status'],
    startedAt: api.started_at ?? '',
    finishedAt: api.finished_at,
    repoIds: api.repo_ids,
    toolIds: api.tool_ids,
    domains: api.domains as Segment[],
    findingsCount: api.findings_count,
    skipEnrichment: api.skip_enrichment,
  }
}

interface ScansListPage {
  items: Scan[]
  total: number
  offset: number
  limit: number
}

const HISTORY_PAGE_LIMIT = 20

function buildScanHistoryUrl(
  projectId: number,
  offset: number,
  limit: number,
  status?: Scan['status']
): string {
  const params = new URLSearchParams()
  params.set('offset', String(offset))
  params.set('limit', String(limit))
  if (status) params.set('status', status)
  return `${REST_ENDPOINTS.scans(projectId)}?${params.toString()}`
}

// ─── Hooks ──────────────────────────────────────────────────────────────────

/**
 * Fetches scan configuration for a project (available repos, tools, domains).
 * Used to populate the advanced scan options UI. Backend serves snake_case;
 * the inline mapper renames `domain`/`domains` → `segment`/`segments` to
 * match the FE Segment vocabulary.
 */
export function useProjectScanConfig(projectId: number) {
  return useQuery({
    queryKey: ['scanConfig', projectId],
    queryFn: async (): Promise<ProjectScanConfig> => {
      const data = await apiFetch<ScanConfigResponseApi>(REST_ENDPOINTS.scanConfig(projectId))
      return mapScanConfig(data)
    },
    staleTime: 5 * 60 * 1000,
    enabled: Boolean(projectId),
  })
}

export interface UseScanHistoryOptions {
  status?: Scan['status']
  limit?: number
}

/**
 * Paginated scan history for a project, served by GET /api/v1/projects/:id/scans.
 * Mirrors the `useFindings` infinite-query shape: items are flattened across
 * pages, callers see `data: Scan[]` plus the standard load-more controls.
 */
export function useScanHistory(projectId: number, options?: UseScanHistoryOptions) {
  const limit = options?.limit ?? HISTORY_PAGE_LIMIT
  const status = options?.status
  const query = useInfiniteQuery({
    queryKey: ['scans', projectId, { status: status ?? null, limit }] as const,
    initialPageParam: 0,
    queryFn: async ({ pageParam }): Promise<ScansListPage> => {
      const url = buildScanHistoryUrl(projectId, pageParam as number, limit, status)
      const data = await apiFetch<ScansListResponseApi>(url)
      return {
        items: data.items.map(mapScan),
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

/**
 * Returns only the running scans for a project. Useful for the running-badge
 * derive and the "scans running" modal. Backed by `useScanHistory` so it
 * stays consistent with the cached list.
 */
export function useRunningScans(projectId: number) {
  const { data: scans } = useScanHistory(projectId)
  return useMemo(() => scans.filter(s => s.status === 'running'), [scans])
}

/**
 * Starts a new scan run. Body is camelCase per `ScanStartRequest`. On error,
 * routes the failure into the `scanMutationError` slice so the
 * `ScanMutationErrorModal` can surface it (most importantly the 409 raised
 * when a scan is already running for the project).
 */
export function useStartScan() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setScanMutationError)

  return useMutation<Scan, ApiError, { projectId: number; options?: ScanOptions }>({
    mutationFn: async ({ projectId, options }) => {
      const body: Record<string, unknown> = {}
      if (options?.repoIds && options.repoIds.length > 0) body.repoIds = options.repoIds
      if (options?.toolIds && options.toolIds.length > 0) body.toolIds = options.toolIds
      if (options?.segments && options.segments.length > 0) body.domains = options.segments
      if (options?.skipToolIds && options.skipToolIds.length > 0)
        body.skipToolIds = options.skipToolIds
      if (options?.skipEnrichment) body.skipEnrichment = true

      const data = await apiFetch<ScanRunSummaryApi>(REST_ENDPOINTS.startScan(projectId), {
        method: 'POST',
        body,
      })
      return mapScan(data)
    },
    onError: err => {
      const payload: ApiErrorPayload = {
        code: err.code,
        message: err.message,
        details: err.details,
        status: err.status,
      }
      setError(payload)
    },
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['scans', projectId] })
    },
  })
}

interface ScanCancelResponseApi {
  id: number
  status: string
}

/**
 * Cancels an in-flight scan run. The backend returns the run with status
 * `cancelling`; the actual `run_cancelled` SSE event arrives later and is
 * the trigger for the page UI to flip to the cancelled state.
 */
export function useCancelScan() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setScanMutationError)

  return useMutation<ScanCancelResponseApi, ApiError, { projectId: number; runId: number }>({
    mutationFn: async ({ projectId, runId }) => {
      return apiFetch<ScanCancelResponseApi>(REST_ENDPOINTS.cancelScan(projectId, runId), {
        method: 'POST',
      })
    },
    onError: err => {
      const payload: ApiErrorPayload = {
        code: err.code,
        message: err.message,
        details: err.details,
        status: err.status,
      }
      setError(payload)
    },
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['scans', projectId] })
    },
  })
}

// ─── SSE event handling ─────────────────────────────────────────────────────

const SCAN_EVENT_TYPES: readonly ScanLogEventType[] = [
  'run_started',
  'segment_started',
  'tool_started',
  'tool_skipped',
  'tool_completed',
  'tool_failed',
  'enrichment_progress',
  'enrichment_complete',
  'segment_completed',
  'run_completed',
  'run_cancelled',
  'run_failed',
] as const

interface ScanEventPayloadApi {
  run_id: number
  project_id: number | null
  segment?: string
  repo?: string
  tool?: string
  message?: string
  findings_count?: number
  enriched_count?: number
  total_to_enrich?: number
  exit_code?: number
  duration?: number
  skip_reason?: string
}

function mapScanEvent(type: ScanLogEventType, data: ScanEventPayloadApi): ScanLogEvent {
  return {
    id:
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `${type}-${data.run_id}-${Date.now()}-${Math.random()}`,
    runId: data.run_id,
    type,
    timestamp: new Date().toISOString(),
    segment: data.segment as Segment | undefined,
    repo: data.repo,
    tool: data.tool,
    message: data.message ?? '',
    findingsCount: data.findings_count,
    enrichedCount: data.enriched_count,
    totalToEnrich: data.total_to_enrich,
    exitCode: data.exit_code,
    duration: data.duration,
  }
}

export interface SnapshotPayload {
  runId: number | null
  projectId: number | null
  activeRunIds?: number[]
  status?: string
  progress?: number
  currentSegment?: string | null
  segmentLabel?: string | null
}

interface SnapshotPayloadApi {
  run_id: number | null
  project_id: number | null
  active_run_ids?: number[]
  status?: string
  progress?: number
  current_segment?: string | null
  segment_label?: string | null
}

function mapSnapshot(data: SnapshotPayloadApi): SnapshotPayload {
  return {
    runId: data.run_id,
    projectId: data.project_id,
    activeRunIds: data.active_run_ids,
    status: data.status,
    progress: data.progress,
    currentSegment: data.current_segment,
    segmentLabel: data.segment_label,
  }
}

/**
 * Subscribes to project-scoped scan SSE. Forwards each typed event to
 * `onEvent` (mapped to `ScanLogEvent`). Snapshot frames are forwarded
 * separately to `onSnapshot` because the snapshot payload shape differs
 * from the per-event shape (it carries `active_run_ids` instead of the
 * per-run fields).
 *
 * `enrichment_progress` events MUST be rendered by the page consumer in
 * a single state slot (latest-value-wins); never appended to a logs array.
 * That's a §12.7 mandate from the roadmap — repeated enrichment ticks would
 * otherwise grow the log unbounded.
 */
export function useScanEvents(
  projectId: number,
  onEvent: (event: ScanLogEvent) => void,
  options?: { enabled?: boolean; onSnapshot?: (snap: SnapshotPayload) => void }
) {
  const enabled = options?.enabled ?? true
  const onEventRef = useRef(onEvent)
  const onSnapshotRef = useRef(options?.onSnapshot)
  onEventRef.current = onEvent
  onSnapshotRef.current = options?.onSnapshot

  useEffect(() => {
    if (!enabled || !projectId) return
    const url = SSE_ENDPOINTS.scanEvents(projectId)
    const handle = apiEventSource(url, {
      eventTypes: ['snapshot', ...SCAN_EVENT_TYPES],
      onEvent: (type, data) => {
        if (type === 'snapshot') {
          onSnapshotRef.current?.(mapSnapshot(data as SnapshotPayloadApi))
          return
        }
        if ((SCAN_EVENT_TYPES as readonly string[]).includes(type)) {
          onEventRef.current(mapScanEvent(type as ScanLogEventType, data as ScanEventPayloadApi))
        }
      },
    })
    return () => handle.close()
  }, [projectId, enabled])
}

/**
 * useRunningScansCount Hook (SSE)
 * ===============================
 * Returns the number of scan runs currently in flight for `projectId`. Wired
 * to `GET /api/v1/projects/{id}/scans/events` via `apiEventSource`. The
 * snapshot frame on connect carries `active_run_ids: number[]`; subsequent
 * `run_started` / `run_completed` / `run_cancelled` / `run_failed` events
 * update the set.
 *
 * Returns 0 (and skips the subscription) when `projectId` is null.
 */
export function useRunningScansCount(projectId: number | null): number {
  const [count, setCount] = useState(0)

  useEffect(() => {
    if (projectId === null) {
      setCount(0)
      return
    }

    const active = new Set<number>()
    const url = SSE_ENDPOINTS.scanEvents(projectId)

    const handle = apiEventSource(url, {
      eventTypes: ['snapshot', 'run_started', 'run_completed', 'run_cancelled', 'run_failed'],
      onEvent: (type, data) => {
        const payload = data as { run_id?: number | null; active_run_ids?: number[] }
        if (type === 'snapshot') {
          active.clear()
          for (const id of payload.active_run_ids ?? []) {
            active.add(id)
          }
        } else if (type === 'run_started') {
          if (typeof payload.run_id === 'number') active.add(payload.run_id)
        } else {
          if (typeof payload.run_id === 'number') active.delete(payload.run_id)
        }
        setCount(active.size)
      },
    })

    return () => {
      handle.close()
    }
  }, [projectId])

  return count
}
