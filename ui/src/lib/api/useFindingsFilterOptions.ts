/**
 * Per-dimension filter options for the Findings page. Strict semantics:
 * counts reflect all active filters; zero-count options are omitted by
 * the backend.
 */

import { useQuery } from '@tanstack/react-query'
import { apiFetch } from './client'
import { REST_ENDPOINTS } from './config'
import type { FindingFilters } from './useFindings'

export interface FilterOption {
  value: string
  count: number
}

export interface RepoFilterOption {
  value: number
  label: string
  count: number
}

export interface FindingsFilterOptions {
  severity: FilterOption[]
  status: FilterOption[]
  confidence: FilterOption[]
  domain: FilterOption[]
  segment: FilterOption[]
  tool: FilterOption[]
  findingType: FilterOption[]
  repo: RepoFilterOption[]
}

interface FindingsFilterOptionsApi {
  severity: FilterOption[]
  status: FilterOption[]
  confidence: FilterOption[]
  domain: FilterOption[]
  segment: FilterOption[]
  tool: FilterOption[]
  finding_type: FilterOption[]
  repo: RepoFilterOption[]
}

function mapResponse(api: FindingsFilterOptionsApi): FindingsFilterOptions {
  return {
    severity: api.severity,
    status: api.status,
    confidence: api.confidence,
    domain: api.domain,
    segment: api.segment,
    tool: api.tool,
    findingType: api.finding_type,
    repo: api.repo,
  }
}

function buildUrl(projectId: string, filters: FindingFilters | undefined): string {
  const params = new URLSearchParams()
  if (filters) {
    for (const v of filters.severity ?? []) params.append('severity', v)
    for (const v of filters.status ?? []) params.append('status', v)
    for (const v of filters.segment ?? []) params.append('segment', v)
    for (const v of filters.tool ?? []) params.append('tool', v)
    for (const v of filters.domain ?? []) params.append('domain', v)
    if (filters.search) params.set('search', filters.search)
  }
  const qs = params.toString()
  const base = REST_ENDPOINTS.findingsFilterOptions(projectId)
  return qs ? `${base}?${qs}` : base
}

export function useFindingsFilterOptions(projectIdParam: string, filters?: FindingFilters) {
  return useQuery({
    queryKey: ['findingsFilterOptions', projectIdParam, filters ?? null] as const,
    queryFn: async (): Promise<FindingsFilterOptions> => {
      const data = await apiFetch<FindingsFilterOptionsApi>(buildUrl(projectIdParam, filters))
      return mapResponse(data)
    },
    staleTime: 10_000,
    enabled: Boolean(projectIdParam),
  })
}
