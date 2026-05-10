/**
 * Paginated URL entries for a project. Infinite-scroll with server-side
 * filters, search, and sort.
 */

import { useMemo } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { apiFetch } from './client'
import { REST_ENDPOINTS } from './config'
import type { HttpMethod, UrlEntry, UrlProtocol } from '../types'
import type { UrlListServerFilters } from './useUrlListsFilterOptions'

interface UrlEntryApi {
  id: number
  project_id: number
  repo_id: number
  repo_name: string
  source: 'scan' | 'user'
  tool: 'katana' | 'noir' | null
  run_id: number | null
  method: string
  protocol: string
  host: string
  port: number
  path: string
  file_path: string | null
  meta: Record<string, unknown>
  created_at: string
}

interface UrlListPageApi {
  items: UrlEntryApi[]
  total: number
  offset: number
  limit: number
}

interface UrlListPage {
  items: UrlEntry[]
  total: number
  offset: number
  limit: number
}

const DEFAULT_LIMIT = 100

export type UrlListSortKey = 'host' | 'path' | 'method' | 'port' | 'protocol' | 'repo'
export type UrlListSortDir = 'asc' | 'desc'

/**
 * Coerce the snake-cased UrlEntryApi into the camel-cased FE `UrlEntry`.
 * Exported so tests can verify the mapper directly.
 */
export function mapUrlEntry(api: UrlEntryApi): UrlEntry {
  return {
    id: api.id,
    projectId: api.project_id,
    repoId: api.repo_id,
    repoName: api.repo_name,
    source: api.source,
    tool: api.tool,
    runId: api.run_id,
    method: api.method as HttpMethod,
    protocol: api.protocol as UrlProtocol,
    host: api.host,
    port: api.port,
    path: api.path,
    filePath: api.file_path,
    meta: api.meta,
    createdAt: api.created_at,
  }
}

function buildUrl(
  projectId: string,
  offset: number,
  limit: number,
  filters: UrlListServerFilters | undefined,
  sort: UrlListSortKey | undefined,
  order: UrlListSortDir | undefined
): string {
  const params = new URLSearchParams()
  params.set('offset', String(offset))
  params.set('limit', String(limit))
  if (filters) {
    for (const v of filters.method ?? []) params.append('method', v)
    for (const v of filters.protocol ?? []) params.append('protocol', v)
    for (const v of filters.host ?? []) params.append('host', v)
    for (const v of filters.port ?? []) params.append('port', String(v))
    for (const v of filters.path ?? []) params.append('path', v)
    for (const v of filters.repoId ?? []) params.append('repo_id', String(v))
    if (filters.search) params.set('search', filters.search)
  }
  if (sort) params.set('sort', sort)
  if (order) params.set('order', order)
  return `${REST_ENDPOINTS.urlListEntries(projectId)}?${params.toString()}`
}

export interface UseUrlListsOptions {
  /** Optional override; combined with the projectId gate. */
  enabled?: boolean
  /** Page size override. Default 100, max 500 (backend-enforced). */
  limit?: number
  /** Server-side filter set. Forwarded as repeatable query params. */
  filters?: UrlListServerFilters
  /** Server-side sort column. */
  sort?: UrlListSortKey
  /** Sort direction. */
  order?: UrlListSortDir
}

export function useUrlLists(projectId: string, options: UseUrlListsOptions = {}) {
  const { enabled = true, limit = DEFAULT_LIMIT, filters, sort, order } = options

  const query = useInfiniteQuery({
    queryKey: ['urlLists', projectId, limit, filters ?? null, sort ?? null, order ?? null] as const,
    initialPageParam: 0,
    queryFn: async ({ pageParam }): Promise<UrlListPage> => {
      const url = buildUrl(projectId, pageParam as number, limit, filters, sort, order)
      const data = await apiFetch<UrlListPageApi>(url)
      return {
        items: data.items.map(mapUrlEntry),
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
    staleTime: 60_000,
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
