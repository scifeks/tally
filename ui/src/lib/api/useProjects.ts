/**
 * useProjects Hook
 * ================
 * Fetches the list of available projects.
 *
 * Backed by `GET /api/v1/projects` (Phase 2.1). Auth-only; no project
 * scope. Backend response is paginated:
 *
 * ```json
 * {
 *   "items": [
 *     { "id": 1, "name": "acme-platform", "code": "ACM",
 *       "created_at": "2026-04-01T00:00:00Z" }
 *   ],
 *   "total": 1, "offset": 0, "limit": 50
 * }
 * ```
 *
 * The TopBar consumes `useProjects()` for the project switcher; per-page
 * project metadata flows through `useProjectMeta()` in its own file.
 */

import { useQuery } from '@tanstack/react-query'
import { apiFetch } from './client'
import { REST_ENDPOINTS } from './config'
import type { Project } from '../types'

interface ProjectListItemApi {
  id: number
  name: string
  code: string
  created_at: string
}

interface ProjectListResponseApi {
  items: ProjectListItemApi[]
  total: number
  offset: number
  limit: number
}

export function useProjects() {
  return useQuery({
    queryKey: ['projects'],
    queryFn: async (): Promise<Project[]> => {
      const data = await apiFetch<ProjectListResponseApi>(REST_ENDPOINTS.projects)
      return data.items.map(item => ({
        id: item.id,
        name: item.name,
        code: item.code,
      }))
    },
    staleTime: 5 * 60 * 1000,
  })
}
