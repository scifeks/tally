/**
 * useFindings Hook
 * ================
 * Paginated read of findings for a project, served by
 * `GET /api/v1/projects/:id/findings`. Per `decisions.md` B13 the UI uses
 * infinite-scroll pagination (offset+limit, not page numbers). Filters,
 * sorting, and search are server-driven query params; the SPA does not
 * filter the global pool.
 *
 * The backend always returns array-typed `cwe` and `finding_type`; the
 * inline `mapFinding` mapper coerces nullables to safe defaults so the
 * camel-cased `Finding` type is always well-formed at every render.
 *
 * Returns a flattened `data: Finding[]` (across all loaded pages) so
 * non-paginated consumers (Dashboard, Triage) can keep their
 * `const { data: findings = [] } = useFindings(...)` shape. Pagination
 * controls (`fetchNextPage`, `hasNextPage`, `isFetchingNextPage`) and the
 * server-reported `total` are exposed alongside.
 */

import { useMemo } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { apiFetch } from './client'
import { REST_ENDPOINTS } from './config'
import type { Finding, Segment, Severity, Status } from '../types'

/** Server-supported sort columns for `GET /findings`. */
export type FindingSortKey = 'severity' | 'status' | 'tool' | 'first_seen' | 'last_seen' | 'title'

export interface FindingFilters {
  severity?: Severity[]
  status?: Status[]
  segment?: Segment[]
  tool?: string[]
  domain?: ('code' | 'web')[]
  search?: string
  sort?: FindingSortKey
  order?: 'asc' | 'desc'
  /** Page size. Default 50, max 500 (backend-enforced). */
  limit?: number
}

export interface UseFindingsOptions {
  /**
   * Project id as a string. Empty string disables the query (matches the
   * sibling-hook convention for "no project selected").
   */
  projectId: string
  filters?: FindingFilters
  /** Optional override; combined with the projectId gate. */
  enabled?: boolean
}

interface FindingApi {
  id: number
  project_id: number
  segment: Segment
  domain: 'code' | 'web'
  severity: Severity
  status: Status
  confidence: string
  finding_type: string[] | null
  title: string
  description?: string | null
  tool: string
  target: string
  file?: string | null
  line?: number | null
  cwe: string[] | null
  notes?: string | null
  discovered_at: string
  triaged_at?: string | null
  triaged_by?: 'claude-code' | 'analyst_web' | null
  is_locked: boolean
  lock_holder: string | null
}

interface FindingsListPageApi {
  items: FindingApi[]
  total: number
  offset: number
  limit: number
}

interface FindingsListPage {
  items: Finding[]
  total: number
  offset: number
  limit: number
}

const DEFAULT_LIMIT = 50

/**
 * Coerce the snake-cased FindingResponse into the camel-cased FE `Finding`.
 * Exported so the PATCH mutation and SSE handler can reuse the same mapper.
 */
export function mapFinding(api: FindingApi): Finding {
  return {
    id: api.id,
    projectId: api.project_id,
    segment: api.segment,
    domain: api.domain,
    severity: api.severity,
    status: api.status,
    confidence: api.confidence,
    findingType: api.finding_type ?? [],
    title: api.title,
    description: api.description ?? undefined,
    tool: api.tool,
    target: api.target,
    file: api.file ?? undefined,
    line: api.line ?? undefined,
    cwe: api.cwe ?? [],
    notes: api.notes ?? undefined,
    discoveredAt: api.discovered_at,
    triagedAt: api.triaged_at ?? undefined,
    triagedBy: api.triaged_by ?? undefined,
    isLocked: api.is_locked,
    lockHolder: api.lock_holder,
  }
}

function buildUrl(
  projectId: string,
  filters: FindingFilters | undefined,
  offset: number,
  limit: number
): string {
  const params = new URLSearchParams()
  params.set('offset', String(offset))
  params.set('limit', String(limit))
  if (filters) {
    for (const v of filters.severity ?? []) params.append('severity', v)
    for (const v of filters.status ?? []) params.append('status', v)
    for (const v of filters.segment ?? []) params.append('segment', v)
    for (const v of filters.tool ?? []) params.append('tool', v)
    for (const v of filters.domain ?? []) params.append('domain', v)
    if (filters.search) params.set('search', filters.search)
    if (filters.sort) params.set('sort', filters.sort)
    if (filters.order) params.set('order', filters.order)
  }
  return `${REST_ENDPOINTS.findings(projectId)}?${params.toString()}`
}

export function useFindings({ projectId, filters, enabled = true }: UseFindingsOptions) {
  const limit = filters?.limit ?? DEFAULT_LIMIT
  const query = useInfiniteQuery({
    queryKey: ['findings', projectId, filters ?? null] as const,
    initialPageParam: 0,
    queryFn: async ({ pageParam }): Promise<FindingsListPage> => {
      const url = buildUrl(projectId, filters, pageParam as number, limit)
      const data = await apiFetch<FindingsListPageApi>(url)
      return {
        items: data.items.map(mapFinding),
        total: data.total,
        offset: data.offset,
        limit: data.limit,
      }
    },
    getNextPageParam: lastPage => {
      const next = lastPage.offset + lastPage.items.length
      return next < lastPage.total ? next : undefined
    },
    enabled: enabled && Boolean(projectId),
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
