/**
 * useFindingsCounts Hook
 * ======================
 * Fetches aggregate finding counts for a project, served by
 * `GET /api/v1/projects/:id/findings/counts` (Phase 3.3 endpoint, formerly
 * 10.9). Powers the Dashboard "at a glance" panel and header summary tiles.
 *
 * Backend response (snake_case) is mapped to the camelCase `FindingsCounts`
 * shape consumed by the SPA. The endpoint is read-only (no CSRF), guarded
 * by the auth session; `apiFetch` surfaces non-2xx as `ApiError`.
 *
 * The query is disabled when `projectIdParam` is the empty string, which is
 * the convention pages use to represent "no project selected" (the
 * `activeProjectId !== null ? String(activeProjectId) : ''` derivation).
 */

import { useQuery } from '@tanstack/react-query'
import { apiFetch } from './client'
import { REST_ENDPOINTS } from './config'
import type { FindingsCounts, Severity } from '../types'

interface FindingsCountsResponseApi {
  by_severity: Record<string, number>
  by_status: Record<string, number>
  by_domain: Record<string, number>
  by_segment: Record<string, number>
  by_repo: Record<string, number>
  by_tool: Record<string, number>
  by_severity_status: Record<string, Record<string, number>>
  total: number
  scans_count: number
  repos_count: number
  urls_count: number
  last_scan_at: string | null
  last_triage_at: string | null
}

function mapResponse(api: FindingsCountsResponseApi): FindingsCounts {
  return {
    bySeverity: api.by_severity as Record<Severity, number>,
    byStatus: api.by_status as FindingsCounts['byStatus'],
    byDomain: api.by_domain,
    bySegment: api.by_segment,
    byRepo: api.by_repo,
    byTool: api.by_tool,
    bySeverityStatus: api.by_severity_status as Record<Severity, Record<string, number>>,
    total: api.total,
    scansCount: api.scans_count,
    reposCount: api.repos_count,
    urlsCount: api.urls_count,
    lastScanAt: api.last_scan_at,
    lastTriageAt: api.last_triage_at,
  }
}

export function useFindingsCounts(projectIdParam: string) {
  return useQuery({
    queryKey: ['findingsCounts', projectIdParam],
    queryFn: async (): Promise<FindingsCounts> => {
      const data = await apiFetch<FindingsCountsResponseApi>(
        REST_ENDPOINTS.findingsCounts(projectIdParam)
      )
      return mapResponse(data)
    },
    staleTime: 30 * 1000,
    enabled: Boolean(projectIdParam),
  })
}
