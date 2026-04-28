/**
 * useProjectMeta Hook
 * ===================
 * Fetches metadata for a single project, served by
 * `GET /api/v1/projects/:id/meta` (Phase 2.x endpoint). Powers the Dashboard
 * "tools enabled" header tile and the Scans page repo/tool counts.
 *
 * Backend response (snake_case) is mapped to the camelCase `ProjectMeta`
 * shape consumed by the SPA. `enabled_tools` is a list of tool IDs (not a
 * count); call sites that need a count read `enabledTools.length`.
 *
 * The query is disabled when `projectIdParam` is the empty string, which is
 * the convention pages use to represent "no project selected" (the
 * `activeProjectId !== null ? String(activeProjectId) : ''` derivation).
 */

import { useQuery } from '@tanstack/react-query'
import { apiFetch } from './client'
import { REST_ENDPOINTS } from './config'
import type { ProjectMeta } from '../types'

interface ProjectMetaResponseApi {
  id: number
  name: string
  code: string
  repo_count: number
  url_list_count: number
  finding_count: number
  enabled_tools: string[]
}

function mapResponse(api: ProjectMetaResponseApi): ProjectMeta {
  return {
    id: api.id,
    name: api.name,
    code: api.code,
    repoCount: api.repo_count,
    urlListCount: api.url_list_count,
    findingCount: api.finding_count,
    enabledTools: api.enabled_tools,
  }
}

export function useProjectMeta(projectIdParam: string) {
  return useQuery({
    queryKey: ['projectMeta', projectIdParam],
    queryFn: async (): Promise<ProjectMeta> => {
      const data = await apiFetch<ProjectMetaResponseApi>(
        REST_ENDPOINTS.projectMeta(projectIdParam)
      )
      return mapResponse(data)
    },
    staleTime: 60 * 1000,
    enabled: Boolean(projectIdParam),
  })
}
