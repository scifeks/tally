/**
 * useFindings Hook
 * ================
 * Fetches findings for a project, optionally filtered by segment.
 *
 * TODO [BACKEND]: Replace mock data with actual API call.
 *
 * Expected API response (GET /api/v1/projects/:id/findings?segment=sast):
 * ```json
 * {
 *   "findings": [
 *     {
 *       "id": "F-1000",
 *       "segment": "sast",
 *       "severity": "critical",
 *       "status": "active",
 *       "title": "SQL injection via unparameterized query",
 *       "tool": "semgrep",
 *       "target": "acme-platform",
 *       "file": "src/api/users.py",
 *       "line": 42,
 *       "cwe": "CWE-89",
 *       "commitHash": "a1b2c3d",
 *       "projectId": "1",
 *       "discoveredAt": "2024-01-15T10:30:00Z",
 *       "notes": null
 *     },
 *     ...
 *   ],
 *   "total": 220
 * }
 * ```
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { Finding, Segment } from '../types'

// TODO [BACKEND]: Remove this mock import once API is connected.
import { findings as mockFindings } from '../mock-data'

interface UseFindingsOptions {
  projectId: string
  segment?: Segment
}

export function useFindings({ projectId, segment }: UseFindingsOptions) {
  return useQuery({
    queryKey: ['findings', projectId, segment],
    queryFn: async (): Promise<Finding[]> => {
      // ┌────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Replace mock with fetch()                         │
      // │                                                                    │
      // │ const params = new URLSearchParams()                              │
      // │ if (segment) params.set("segment", segment)                       │
      // │ const url = `${REST_ENDPOINTS.findings(projectId)}?${params}`     │
      // │ const res = await fetch(url)                                      │
      // │ if (!res.ok) throw new Error("Failed to fetch findings")          │
      // │ const data = await res.json()                                     │
      // │ return data.findings                                              │
      // └────────────────────────────────────────────────────────────────────┘

      await new Promise(r => setTimeout(r, 150))
      let result = mockFindings.filter(f => f.projectId === projectId)
      if (segment) {
        result = result.filter(f => f.segment === segment)
      }
      return result
    },
    staleTime: 30 * 1000,
    enabled: Boolean(projectId),
  })
}

/**
 * useUpdateFinding Mutation
 * =========================
 * Updates a finding's editable fields (status, severity, title, notes).
 *
 * TODO [BACKEND]: Replace mock mutation with actual API call.
 *
 * Expected API request (PATCH /api/v1/findings/:id):
 * ```json
 * {
 *   "status": "active",
 *   "notes": "Analyst notes here..."
 * }
 * ```
 *
 * Expected API response:
 * ```json
 * {
 *   "id": "F-1000",
 *   "status": "active",
 *   ... (full updated finding)
 * }
 * ```
 */

export function useUpdateFinding() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      id,
      patch,
    }: {
      id: string
      patch: Partial<Pick<Finding, 'status' | 'severity' | 'title' | 'notes'>>
    }): Promise<Finding> => {
      // ┌────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Replace mock with fetch()                         │
      // │                                                                    │
      // │ const res = await fetch(REST_ENDPOINTS.updateFinding(id), {       │
      // │   method: "PATCH",                                                │
      // │   headers: { "Content-Type": "application/json" },                │
      // │   body: JSON.stringify(patch),                                    │
      // │ })                                                                │
      // │ if (!res.ok) throw new Error("Failed to update finding")          │
      // │ return res.json()                                                 │
      // └────────────────────────────────────────────────────────────────────┘

      // Mock: find the finding and apply the patch in memory.
      await new Promise(r => setTimeout(r, 100))
      const finding = mockFindings.find(f => f.id === id)
      if (!finding) throw new Error(`Finding ${id} not found`)
      // Note: This doesn't persist — real API would persist.
      return { ...finding, ...patch }
    },
    onSuccess: updatedFinding => {
      // Invalidate findings queries so they refetch with updated data.
      queryClient.invalidateQueries({ queryKey: ['findings'] })
      // Also update the single finding cache if we have one.
      queryClient.setQueryData(['finding', updatedFinding.id], updatedFinding)
    },
  })
}
