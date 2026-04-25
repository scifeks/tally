/**
 * useUrlLists Hook
 * ================
 * Fetches URL entries for a project's URL list.
 *
 * TODO [BACKEND]: Replace mock data with actual API call.
 */

import { useQuery } from '@tanstack/react-query'
import type { UrlEntry } from '../types'

// TODO [BACKEND]: Remove these mock imports once API is connected.
import { urls as mockUrls } from '../mock-data'

/**
 * Returns the URL entries belonging to a project's URL list.
 *
 * Expected API response (GET /api/v1/projects/:id/url-lists):
 * ```json
 * [
 *   {
 *     "id": "U-5000",
 *     "projectId": "1",
 *     "method": "GET",
 *     "protocol": "https",
 *     "host": "api.acme-platform.com",
 *     "port": 443,
 *     "path": "/api/v1/users"
 *   },
 *   ...
 * ]
 * ```
 */
export function useUrlLists(projectId: string) {
  return useQuery({
    queryKey: ['urlLists', projectId],
    queryFn: async (): Promise<UrlEntry[]> => {
      // ┌────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Replace mock with fetch()                         │
      // │                                                                    │
      // │ const res = await fetch(REST_ENDPOINTS.urlLists(projectId))       │
      // │ if (!res.ok) throw new Error("Failed to fetch URL entries")       │
      // │ return res.json()                                                 │
      // └────────────────────────────────────────────────────────────────────┘

      await new Promise(r => setTimeout(r, 100))
      return mockUrls.filter(u => u.projectId === projectId)
    },
    staleTime: 60 * 1000,
    enabled: Boolean(projectId),
  })
}
