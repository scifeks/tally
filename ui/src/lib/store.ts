import { create } from 'zustand'
import type { Segment, Finding, TriageRunStatus } from './types'

interface UIState {
  /** null means no project selected yet (initial app load state) */
  activeProjectId: string | null
  setActiveProject: (id: string | null) => void

  findingsSegment: Segment
  setFindingsSegment: (d: Segment) => void

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
  activeProjectId: null,
  setActiveProject: id => set({ activeProjectId: id, selectedFindingIds: new Set() }),

  findingsSegment: 'sast',
  setFindingsSegment: d => set({ findingsSegment: d, selectedFindingIds: new Set() }),

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
