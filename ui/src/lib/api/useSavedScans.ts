/**
 * Saved Scans hooks (CLIENT-SIDE MOCK)
 * ====================================
 * Backs the v0-ported "Saved Scans" tab on the Scans page. The store is a
 * module-level Map keyed by projectId. State resets on full page reload —
 * intentional. No fetch, no MSW handler. Once the backend lands, swap the
 * three queryFn / mutationFn bodies for `apiFetch` calls and delete the
 * in-memory store.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { SavedScan } from '../types'

// ─── Seed data (mirrors v0's mockSavedScans) ─────────────────────────────────

const SEED: Record<number, SavedScan[]> = {
  1: [
    {
      id: 'scan-1',
      projectId: 1,
      name: 'Full SAST + SCA',
      repoIds: [],
      toolIds: ['semgrep', 'osv-scanner', 'gitleaks'],
      skipToolIds: [],
      segments: ['sast', 'sca', 'secrets'],
      skipEnrichment: false,
      createdAt: '2025-01-10T08:00:00Z',
      updatedAt: '2025-01-10T08:00:00Z',
    },
    {
      id: 'scan-2',
      projectId: 1,
      name: 'Quick Web Scan',
      repoIds: [1],
      toolIds: ['noir', 'katana'],
      skipToolIds: ['xsstrike'],
      segments: ['web'],
      skipEnrichment: true,
      createdAt: '2025-01-12T14:30:00Z',
      updatedAt: '2025-01-15T09:00:00Z',
    },
  ],
}

// ─── In-memory store ─────────────────────────────────────────────────────────

const store: Map<number, SavedScan[]> = new Map(
  Object.entries(SEED).map(([k, v]) => [Number(k), v.map(s => ({ ...s }))])
)

function getList(projectId: number): SavedScan[] {
  return store.get(projectId) ?? []
}

function setList(projectId: number, list: SavedScan[]): void {
  store.set(projectId, list)
}

// ─── Hooks ───────────────────────────────────────────────────────────────────

const QUERY_KEY = (projectId: number) => ['savedScans', projectId] as const

export function useSavedScans(projectId: number) {
  return useQuery({
    queryKey: QUERY_KEY(projectId),
    queryFn: async (): Promise<SavedScan[]> => {
      await new Promise(resolve => setTimeout(resolve, 100))
      return getList(projectId).map(s => ({ ...s }))
    },
    enabled: Boolean(projectId),
    staleTime: 5 * 60 * 1000,
  })
}

export function useSaveScan() {
  const queryClient = useQueryClient()

  return useMutation<SavedScan, Error, { scan: SavedScan; isNew: boolean }>({
    mutationFn: async ({ scan, isNew }) => {
      await new Promise(resolve => setTimeout(resolve, 100))
      const now = new Date().toISOString()
      const list = getList(scan.projectId)
      if (isNew) {
        const created: SavedScan = {
          ...scan,
          id: `scan-${Date.now()}`,
          createdAt: now,
          updatedAt: now,
        }
        setList(scan.projectId, [...list, created])
        return created
      }
      const updated: SavedScan = { ...scan, updatedAt: now }
      setList(
        scan.projectId,
        list.map(s => (s.id === scan.id ? updated : s))
      )
      return updated
    },
    onSuccess: (_, { scan }) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY(scan.projectId) })
    },
  })
}

export function useDeleteSavedScan() {
  const queryClient = useQueryClient()

  return useMutation<void, Error, { projectId: number; scanId: string }>({
    mutationFn: async ({ projectId, scanId }) => {
      await new Promise(resolve => setTimeout(resolve, 100))
      setList(
        projectId,
        getList(projectId).filter(s => s.id !== scanId)
      )
    },
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY(projectId) })
    },
  })
}
