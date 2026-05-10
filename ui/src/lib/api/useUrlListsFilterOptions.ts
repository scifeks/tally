/**
 * Per-dimension filter options for URL Lists. Strict semantics: counts
 * reflect all active filters; zero-count options are omitted by the backend.
 */

import { useQuery } from '@tanstack/react-query'
import { apiFetch } from './client'
import { REST_ENDPOINTS } from './config'

export interface UrlListFilterOption {
  value: string
  count: number
}

export interface UrlListPortFilterOption {
  value: number
  count: number
}

export interface UrlListRepoFilterOption {
  value: number
  label: string
  count: number
}

export interface UrlListFilterOptions {
  method: UrlListFilterOption[]
  protocol: UrlListFilterOption[]
  host: UrlListFilterOption[]
  port: UrlListPortFilterOption[]
  path: UrlListFilterOption[]
  repo: UrlListRepoFilterOption[]
}

export interface UrlListServerFilters {
  method?: string[]
  protocol?: string[]
  host?: string[]
  port?: number[]
  path?: string[]
  repoId?: number[]
  search?: string
}

function buildUrl(projectId: string, filters: UrlListServerFilters | undefined): string {
  const params = new URLSearchParams()
  if (filters) {
    for (const v of filters.method ?? []) params.append('method', v)
    for (const v of filters.protocol ?? []) params.append('protocol', v)
    for (const v of filters.host ?? []) params.append('host', v)
    for (const v of filters.port ?? []) params.append('port', String(v))
    for (const v of filters.path ?? []) params.append('path', v)
    for (const v of filters.repoId ?? []) params.append('repo_id', String(v))
    if (filters.search) params.set('search', filters.search)
  }
  const qs = params.toString()
  const base = REST_ENDPOINTS.urlListFilterOptions(projectId)
  return qs ? `${base}?${qs}` : base
}

export function useUrlListsFilterOptions(projectIdParam: string, filters?: UrlListServerFilters) {
  return useQuery({
    queryKey: ['urlListsFilterOptions', projectIdParam, filters ?? null] as const,
    queryFn: async (): Promise<UrlListFilterOptions> => {
      return apiFetch<UrlListFilterOptions>(buildUrl(projectIdParam, filters))
    },
    staleTime: 10_000,
    enabled: Boolean(projectIdParam),
  })
}
