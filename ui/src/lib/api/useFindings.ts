/**
 * useFindings Hook
 * ================
 * Fetches findings for a project, optionally filtered by domain.
 *
 * TODO [BACKEND]: Replace mock data with actual API call.
 *
 * Expected API response (GET /api/v1/projects/:id/findings?domain=sast):
 * ```json
 * {
 *   "findings": [
 *     {
 *       "id": "F-1000",
 *       "domain": "sast",
 *       "severity": "critical",
 *       "status": "open",
 *       "title": "SQL injection via unparameterized query",
 *       "tool": "semgrep",
 *       "target": "acme-platform",
 *       "file": "src/api/users.py",
 *       "line": 42,
 *       "cwe": "CWE-89",
 *       "commitHash": "a1b2c3d",
 *       "projectId": "p-01",
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
import type { Finding, Domain } from '../types'

// TODO [BACKEND]: Remove this mock import once API is connected.
import { findings as mockFindings } from '../mock-data'

interface UseFindingsOptions {
  projectId: string
  domain?: Domain
}

export function useFindings({ projectId, domain }: UseFindingsOptions) {
  return useQuery({
    queryKey: ['findings', projectId, domain],
    queryFn: async (): Promise<Finding[]> => {
      // ┌────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Replace mock with fetch()                         │
      // │                                                                    │
      // │ const params = new URLSearchParams()                              │
      // │ if (domain) params.set("domain", domain)                          │
      // │ const url = `${REST_ENDPOINTS.findings(projectId)}?${params}`     │
      // │ const res = await fetch(url)                                      │
      // │ if (!res.ok) throw new Error("Failed to fetch findings")          │
      // │ const data = await res.json()                                     │
      // │ return data.findings                                              │
      // └────────────────────────────────────────────────────────────────────┘

      await new Promise(r => setTimeout(r, 150))
      let result = mockFindings.filter(f => f.projectId === projectId)
      if (domain) {
        result = result.filter(f => f.domain === domain)
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
 *   "status": "triaged",
 *   "notes": "Analyst notes here..."
 * }
 * ```
 *
 * Expected API response:
 * ```json
 * {
 *   "id": "F-1000",
 *   "status": "triaged",
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
