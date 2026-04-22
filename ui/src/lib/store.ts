import { create } from 'zustand'
import type { Domain, Finding, TriageRunStatus } from './types'

interface UIState {
  activeProjectId: string
  setActiveProject: (id: string) => void

  findingsDomain: Domain
  setFindingsDomain: (d: Domain) => void

  selectedFindingIds: Set<string>
  toggleSelected: (id: string) => void
  setSelected: (ids: string[]) => void
  clearSelected: () => void

  /**
   * Prototype: in-memory overrides for editable finding fields.
   * Real app will PATCH the backend and invalidate the query cache.
   */
  findingOverrides: Record<string, Partial<Finding>>
  updateFinding: (id: string, patch: Partial<Finding>) => void

  /** Track triage run status to block project switches. */
  triageRunStatus: TriageRunStatus
  setTriageRunStatus: (status: TriageRunStatus) => void
}

export const useUI = create<UIState>(set => ({
  activeProjectId: 'p-01',
  setActiveProject: id => set({ activeProjectId: id, selectedFindingIds: new Set() }),

  findingsDomain: 'sast',
  setFindingsDomain: d => set({ findingsDomain: d, selectedFindingIds: new Set() }),

  selectedFindingIds: new Set<string>(),
  toggleSelected: id =>
    set(s => {
      const next = new Set(s.selectedFindingIds)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return { selectedFindingIds: next }
    }),
  setSelected: ids => set({ selectedFindingIds: new Set(ids) }),
  clearSelected: () => set({ selectedFindingIds: new Set() }),

  findingOverrides: {},
  updateFinding: (id, patch) =>
    set(s => ({
      findingOverrides: {
        ...s.findingOverrides,
        [id]: { ...(s.findingOverrides[id] ?? {}), ...patch },
      },
    })),

  triageRunStatus: 'idle',
  setTriageRunStatus: status => set({ triageRunStatus: status }),
}))
