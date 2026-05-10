/** Fetches the list of available projects. Auth-only, no project scope. */

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
