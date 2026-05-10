/**
 * Project metadata query. `enabledTools` is a list of tool IDs, not a count.
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
