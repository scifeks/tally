/**
 * Report hooks: drafts, full-report generation, history, and SSE. Mutation
 * errors route through the `reportMutationError` Zustand slice.
 */

import { useEffect, useMemo, useRef } from 'react'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type {
  ApiErrorPayload,
  ReportCancelResponse,
  ReportDraft,
  ReportDraftSection,
  ReportDraftSnapshotPayload,
  ReportDraftStatus,
  ReportFormat,
  ReportGenerationRun,
  ReportGenerationStatus,
  ReportGenerationStep,
  ReportHistoryEntry,
  ReportLogEvent,
  ReportLogEventType,
  ReportSnapshotPayload,
  TestingType,
} from '../types'
import { ApiError, apiFetch } from './client'
import { apiEventSource } from './sse'
import { REST_ENDPOINTS, SSE_ENDPOINTS } from './config'
import { useUI } from '../store'

// ─── Wire-format types ──────────────────────────────────────────────────────

interface ReportDraftApi {
  section: ReportDraftSection
  status: ReportDraftStatus
  generated_at?: string | null
  reviewed_at?: string | null
  preview?: string | null
  word_count?: number | null
  uploaded_filename?: string | null
  error?: string | null
}

interface ReportDraftsResponseApi {
  drafts: ReportDraftApi[]
}

interface ReportSummaryApi {
  id: number
  project_id: number | null
  filename: string
  format: ReportFormat
  status: string
  file_size_bytes: number | null
  created_at: string | null
  started_at: string | null
  finished_at: string | null
  download_url: string | null
  pinned?: boolean
}

interface ReportHistoryResponseApi {
  items: ReportSummaryApi[]
  total: number
  offset: number
  limit: number
}

interface ReportGenerationStepApi {
  id: string
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  message?: string | null
  started_at?: string | null
  finished_at?: string | null
}

interface ReportGenerationRunApi {
  id: number
  project_id: number
  status: ReportGenerationStatus
  format: ReportFormat
  testing_type?: TestingType
  engagement_date?: string | null
  started_at: string
  finished_at?: string | null
  output_path?: string | null
  error?: string | null
  steps?: ReportGenerationStepApi[]
}

interface ReportCancelResponseApi {
  id: number
  status: 'cancelling'
}

interface ReportEventPayloadApi {
  id: string
  run_id: number
  timestamp: string
  message?: string
  step?: string
  section?: ReportDraftSection
  progress?: number
  output_path?: string
  word_count?: number
  preview?: string | null
  error?: string
}

interface ReportSnapshotApi {
  run_id: number
  status: ReportGenerationStatus
  steps?: ReportGenerationStepApi[]
}

interface ReportDraftSnapshotApi {
  in_flight?: ReportDraftSection[]
}

// ─── Mappers ────────────────────────────────────────────────────────────────

export function mapReportDraft(api: ReportDraftApi): ReportDraft {
  return {
    section: api.section,
    status: api.status,
    generatedAt: api.generated_at ?? undefined,
    reviewedAt: api.reviewed_at ?? undefined,
    preview: api.preview ?? undefined,
    wordCount: api.word_count ?? undefined,
    uploadedFilename: api.uploaded_filename ?? undefined,
    error: api.error ?? undefined,
  }
}

export function mapReportHistoryEntry(api: ReportSummaryApi): ReportHistoryEntry {
  return {
    id: api.id,
    projectId: api.project_id ?? 0,
    filename: api.filename,
    format: api.format,
    generatedAt: api.finished_at ?? api.started_at ?? api.created_at ?? '',
    sizeBytes: api.file_size_bytes ?? 0,
    downloadUrl: api.download_url ?? '',
    pinned: api.pinned,
  }
}

function mapReportStep(api: ReportGenerationStepApi): ReportGenerationStep {
  return {
    id: api.id,
    name: api.name,
    status: api.status,
    message: api.message ?? undefined,
    startedAt: api.started_at ?? undefined,
    finishedAt: api.finished_at ?? undefined,
  }
}

export function mapReportRun(api: ReportGenerationRunApi): ReportGenerationRun {
  return {
    id: api.id,
    projectId: api.project_id,
    status: api.status,
    format: api.format,
    testingType: api.testing_type,
    engagementDate: api.engagement_date ?? undefined,
    startedAt: api.started_at,
    finishedAt: api.finished_at ?? undefined,
    outputPath: api.output_path ?? undefined,
    error: api.error ?? undefined,
    steps: (api.steps ?? []).map(mapReportStep),
  }
}

function mapReportEvent(type: ReportLogEventType, data: ReportEventPayloadApi): ReportLogEvent {
  return {
    id: data.id,
    runId: data.run_id,
    type,
    timestamp: data.timestamp,
    step: data.step,
    section: data.section,
    message: data.message ?? '',
    progress: data.progress,
    wordCount: data.word_count,
    preview: data.preview ?? undefined,
  }
}

function mapReportSnapshot(data: ReportSnapshotApi): ReportSnapshotPayload {
  return {
    runId: data.run_id,
    status: data.status,
    steps: (data.steps ?? []).map(mapReportStep),
  }
}

function mapDraftSnapshot(data: ReportDraftSnapshotApi): ReportDraftSnapshotPayload {
  return {
    inFlight: data.in_flight ?? [],
  }
}

function toErrorPayload(err: ApiError): ApiErrorPayload {
  return {
    code: err.code,
    message: err.message,
    details: err.details,
    status: err.status,
  }
}

// ─── Read hooks ─────────────────────────────────────────────────────────────

export function useReportDrafts(projectId: number | null) {
  return useQuery({
    queryKey: ['reports', projectId, 'drafts'],
    queryFn: async (): Promise<ReportDraft[]> => {
      const data = await apiFetch<ReportDraftsResponseApi>(
        REST_ENDPOINTS.reportDrafts(projectId as number)
      )
      return data.drafts.map(mapReportDraft)
    },
    enabled: projectId !== null,
    staleTime: 10_000,
  })
}

export interface UseReportHistoryOptions {
  limit?: number
}

interface ReportHistoryPage {
  items: ReportHistoryEntry[]
  total: number
  offset: number
  limit: number
}

const HISTORY_PAGE_LIMIT = 20

function buildReportHistoryUrl(projectId: number, offset: number, limit: number): string {
  const params = new URLSearchParams()
  params.set('offset', String(offset))
  params.set('limit', String(limit))
  return `${REST_ENDPOINTS.reportHistory(projectId)}?${params.toString()}`
}

export function useReportHistory(projectId: number | null, options?: UseReportHistoryOptions) {
  const limit = options?.limit ?? HISTORY_PAGE_LIMIT
  const query = useInfiniteQuery({
    queryKey: ['reports', projectId, 'history', { limit }] as const,
    initialPageParam: 0,
    queryFn: async ({ pageParam }): Promise<ReportHistoryPage> => {
      const url = buildReportHistoryUrl(projectId as number, pageParam as number, limit)
      const data = await apiFetch<ReportHistoryResponseApi>(url)
      return {
        items: data.items.map(mapReportHistoryEntry),
        total: data.total,
        offset: data.offset,
        limit: data.limit,
      }
    },
    getNextPageParam: lastPage => {
      const next = lastPage.offset + lastPage.items.length
      return next < lastPage.total ? next : undefined
    },
    enabled: projectId !== null,
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

export function useLatestReport(projectId: number | null) {
  return useQuery({
    queryKey: ['reports', projectId, 'latest'],
    queryFn: async (): Promise<ReportHistoryEntry | null> => {
      try {
        const data = await apiFetch<ReportSummaryApi | null>(
          REST_ENDPOINTS.latestReport(projectId as number)
        )
        return data ? mapReportHistoryEntry(data) : null
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          return null
        }
        throw err
      }
    },
    enabled: projectId !== null,
    staleTime: 10_000,
    retry: (failureCount, err) => {
      if (err instanceof ApiError && err.status === 404) return false
      return failureCount < 3
    },
  })
}

// ─── Mutations ──────────────────────────────────────────────────────────────

export interface GenerateDraftsVariables {
  projectId: number
  sections: ReportDraftSection[]
  force?: boolean
  skipTriage?: boolean
}

export function useGenerateDrafts() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setReportMutationError)

  return useMutation<ReportDraft[], ApiError, GenerateDraftsVariables>({
    mutationFn: async ({ projectId, sections, force, skipTriage }) => {
      const data = await apiFetch<ReportDraftsResponseApi>(
        REST_ENDPOINTS.generateDraft(projectId),
        {
          method: 'POST',
          body: {
            sections,
            force: force ?? false,
            skip_triage: skipTriage ?? false,
          },
        }
      )
      return data.drafts.map(mapReportDraft)
    },
    onError: err => setError(toErrorPayload(err)),
    onSuccess: (incoming, { projectId }) => {
      // Apply the POST response to the cache so any stale `failed` state
      // from prior runs clears immediately. SSE drives transitions from
      // here on; no GET refetch needed.
      queryClient.setQueryData<ReportDraft[]>(['reports', projectId, 'drafts'], prev => {
        if (!prev) return prev
        const bySection = new Map(incoming.map(d => [d.section, d]))
        return prev.map(existing => {
          const next = bySection.get(existing.section)
          if (!next) return existing
          return {
            ...existing,
            status: next.status,
            error: undefined,
            preview: undefined,
            wordCount: undefined,
            generatedAt: undefined,
          }
        })
      })
    },
  })
}

export interface UploadDraftVariables {
  projectId: number
  section: ReportDraftSection
  file: File
}

export function useUploadDraft() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setReportMutationError)

  return useMutation<ReportDraft, ApiError, UploadDraftVariables>({
    mutationFn: async ({ projectId, section, file }) => {
      const form = new FormData()
      form.append('section', section)
      form.append('file', file)
      const data = await apiFetch<ReportDraftApi>(REST_ENDPOINTS.uploadDraft(projectId), {
        method: 'POST',
        body: form,
      })
      return mapReportDraft(data)
    },
    onError: err => setError(toErrorPayload(err)),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['reports', projectId, 'drafts'] })
    },
  })
}

export interface DeleteDraftVariables {
  projectId: number
  section: ReportDraftSection
}

export function useDeleteDraft() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setReportMutationError)

  return useMutation<void, ApiError, DeleteDraftVariables>({
    mutationFn: async ({ projectId, section }) => {
      await apiFetch<void>(REST_ENDPOINTS.deleteDraft(projectId, section), { method: 'DELETE' })
    },
    onError: err => setError(toErrorPayload(err)),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['reports', projectId, 'drafts'] })
    },
  })
}

export interface GenerateReportVariables {
  projectId: number
  format: ReportFormat
  testingType?: TestingType
  engagementDate?: string
  companyName?: string
  outputPath?: string
  skipTriage?: boolean
}

export function useGenerateReport() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setReportMutationError)

  return useMutation<ReportGenerationRun, ApiError, GenerateReportVariables>({
    mutationFn: async vars => {
      const body: Record<string, unknown> = { format: vars.format }
      if (vars.testingType !== undefined) body.testing_type = vars.testingType
      if (vars.engagementDate !== undefined) body.engagement_date = vars.engagementDate
      if (vars.companyName !== undefined && vars.companyName !== '') {
        body.company_name = vars.companyName
      }
      if (vars.outputPath !== undefined) body.output_path = vars.outputPath
      if (vars.skipTriage !== undefined) body.skip_triage = vars.skipTriage
      const data = await apiFetch<ReportGenerationRunApi>(
        REST_ENDPOINTS.generateReport(vars.projectId),
        { method: 'POST', body }
      )
      return mapReportRun(data)
    },
    onError: err => setError(toErrorPayload(err)),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['reports', projectId] })
    },
  })
}

export interface CancelReportVariables {
  projectId: number
  reportId: number
}

export function useCancelReport() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setReportMutationError)

  return useMutation<ReportCancelResponse, ApiError, CancelReportVariables>({
    mutationFn: async ({ projectId, reportId }) => {
      const data = await apiFetch<ReportCancelResponseApi>(
        REST_ENDPOINTS.cancelReport(projectId, reportId),
        { method: 'POST' }
      )
      return data
    },
    onError: err => setError(toErrorPayload(err)),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['reports', projectId] })
    },
  })
}

// ─── Download helpers ───────────────────────────────────────────────────────

function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export async function downloadDraftSection(
  projectId: number,
  section: ReportDraftSection
): Promise<void> {
  const blob = await apiFetch<Blob>(REST_ENDPOINTS.downloadDraft(projectId, section), {
    headers: { Accept: 'text/markdown' },
    parseAs: 'blob',
  })
  triggerBlobDownload(blob, `${section}.md`)
}

export async function downloadReportFile(
  projectId: number,
  reportId: number,
  filename: string
): Promise<void> {
  const blob = await apiFetch<Blob>(REST_ENDPOINTS.downloadReport(projectId, reportId), {
    parseAs: 'blob',
  })
  triggerBlobDownload(blob, filename)
}

// ─── SSE consumers ──────────────────────────────────────────────────────────

const REPORT_EVENT_TYPES: readonly ReportLogEventType[] = [
  'generation_started',
  'step_started',
  'step_completed',
  'step_failed',
  'generation_completed',
  'generation_failed',
] as const

const DRAFT_EVENT_TYPES: readonly ReportLogEventType[] = [
  'draft_started',
  'draft_completed',
  'draft_failed',
] as const

export interface UseReportEventsOptions {
  enabled?: boolean
  /**
   * Optional run_id query param. When set, the snapshot frame on connect
   * is scoped to that single generation run.
   */
  runId?: number | null
  onSnapshot?: (snap: ReportSnapshotPayload) => void
}

export function useReportEvents(
  projectId: number | null,
  onEvent: (event: ReportLogEvent) => void,
  options?: UseReportEventsOptions
) {
  const enabled = options?.enabled ?? true
  const runId = options?.runId ?? null
  const onEventRef = useRef(onEvent)
  const onSnapshotRef = useRef(options?.onSnapshot)
  onEventRef.current = onEvent
  onSnapshotRef.current = options?.onSnapshot

  useEffect(() => {
    if (!enabled || projectId === null) return
    let url = SSE_ENDPOINTS.reportEvents(projectId)
    if (runId !== null) {
      url = `${url}?run_id=${runId}`
    }
    const handle = apiEventSource(url, {
      eventTypes: ['snapshot', ...REPORT_EVENT_TYPES],
      onEvent: (type, data) => {
        if (type === 'snapshot') {
          onSnapshotRef.current?.(mapReportSnapshot(data as ReportSnapshotApi))
          return
        }
        if ((REPORT_EVENT_TYPES as readonly string[]).includes(type)) {
          onEventRef.current(
            mapReportEvent(type as ReportLogEventType, data as ReportEventPayloadApi)
          )
        }
      },
    })
    return () => handle.close()
  }, [projectId, enabled, runId])
}

export interface UseReportDraftEventsOptions {
  enabled?: boolean
  /**
   * Optional section query param. When set, the snapshot scopes to that
   * section's in-flight state only.
   */
  section?: ReportDraftSection | null
  onSnapshot?: (snap: ReportDraftSnapshotPayload) => void
}

export function useReportDraftEvents(
  projectId: number | null,
  onEvent: (event: ReportLogEvent) => void,
  options?: UseReportDraftEventsOptions
) {
  const enabled = options?.enabled ?? true
  const section = options?.section ?? null
  const onEventRef = useRef(onEvent)
  const onSnapshotRef = useRef(options?.onSnapshot)
  onEventRef.current = onEvent
  onSnapshotRef.current = options?.onSnapshot

  useEffect(() => {
    if (!enabled || projectId === null) return
    let url = SSE_ENDPOINTS.reportDraftEvents(projectId)
    if (section !== null) {
      url = `${url}?section=${section}`
    }
    const handle = apiEventSource(url, {
      eventTypes: ['snapshot', ...DRAFT_EVENT_TYPES],
      onEvent: (type, data) => {
        if (type === 'snapshot') {
          onSnapshotRef.current?.(mapDraftSnapshot(data as ReportDraftSnapshotApi))
          return
        }
        if ((DRAFT_EVENT_TYPES as readonly string[]).includes(type)) {
          onEventRef.current(
            mapReportEvent(type as ReportLogEventType, data as ReportEventPayloadApi)
          )
        }
      },
    })
    return () => handle.close()
  }, [projectId, enabled, section])
}
