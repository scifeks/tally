/**
 * useProjects Hook
 * ================
 * Fetches the list of available projects.
 *
 * TODO [BACKEND]: Replace mock data with actual API call.
 *
 * Expected API response (GET /api/v1/projects):
 * ```json
 * {
 *   "projects": [
 *     { "id": "1", "name": "acme-platform", "code": "ACM" },
 *     ...
 *   ]
 * }
 * ```
 */

import { useQuery } from '@tanstack/react-query'
import type { Project } from '../types'

// TODO [BACKEND]: Remove this mock import once API is connected.
import { projects as mockProjects } from '../mock-data'

export function useProjects() {
  return useQuery({
    queryKey: ['projects'],
    queryFn: async (): Promise<Project[]> => {
      // ┌────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Replace mock with fetch()                         │
      // │                                                                    │
      // │ const res = await fetch(REST_ENDPOINTS.projects)                  │
      // │ if (!res.ok) throw new Error("Failed to fetch projects")          │
      // │ const data = await res.json()                                     │
      // │ return data.projects                                              │
      // └────────────────────────────────────────────────────────────────────┘

      // Return mock data immediately (no delay for prototype).
      return mockProjects
    },
    // Provide initial data to avoid loading state flicker.
    initialData: mockProjects,
    staleTime: 5 * 60 * 1000, // Projects rarely change; cache for 5 min.
  })
}

/**
 * useProjectMeta Hook
 * ===================
 * Fetches metadata for a single project (repo count, URL list count, enabled tools).
 *
 * TODO [BACKEND]: Replace mock data with actual API call.
 *
 * Expected API response (GET /api/v1/projects/:id/meta):
 * ```json
 * {
 *   "repositories": 14,
 *   "urlLists": 3,
 *   "enabledTools": 9
 * }
 * ```
 */

// TODO [BACKEND]: Remove this mock import once API is connected.
import { projectMeta as mockProjectMeta } from '../mock-data'

export function useProjectMeta(projectId: string) {
  return useQuery({
    queryKey: ['projectMeta', projectId],
    queryFn: async () => {
      // ┌────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Replace mock with fetch()                         │
      // │                                                                    │
      // │ const res = await fetch(REST_ENDPOINTS.projectMeta(projectId))    │
      // │ if (!res.ok) throw new Error("Failed to fetch project meta")      │
      // │ return res.json()                                                 │
      // └────────────────────────────────────────────────────────────────────┘

      return mockProjectMeta[projectId] ?? { repositories: 0, urlLists: 0, enabledTools: 0 }
    },
    staleTime: 60 * 1000,
    enabled: Boolean(projectId),
  })
}
