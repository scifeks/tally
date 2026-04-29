import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ApiErrorPayload, Segment, TriagePageStatus } from './types'

interface UIState {
  /** null means no project selected yet (initial app load state) */
  activeProjectId: number | null
  setActiveProject: (id: number | null) => void

  findingsSegment: Segment
  setFindingsSegment: (d: Segment) => void

  selectedFindingIds: Set<number>
  toggleSelected: (id: number) => void
  setSelected: (ids: number[]) => void
  clearSelected: () => void

  /**
   * Surface mutation failures (especially `FINDING_LOCKED` 409s) so an
   * optimistic rollback is visible to the user. Cleared by the modal's
   * dismiss button. Not persisted.
   */
  findingMutationError: ApiErrorPayload | null
  setFindingMutationError: (err: ApiErrorPayload | null) => void

  /**
   * Surface scan start/cancel failures (most importantly the 409 returned
   * when a scan is already running for the project) so the user can't miss
   * a rejected action. Cleared by the modal's dismiss button. Not persisted.
   */
  scanMutationError: ApiErrorPayload | null
  setScanMutationError: (err: ApiErrorPayload | null) => void

  /**
   * Surface triage start/cancel/resume failures (409 JOB_ALREADY_RUNNING,
   * 409 TRIAGE_NOT_CANCELLABLE, 409 TRIAGE_NOT_RESUMABLE, 422
   * VALIDATION_ERROR, 404 NOT_FOUND). Cleared by the modal's dismiss
   * button. Not persisted.
   */
  triageMutationError: ApiErrorPayload | null
  setTriageMutationError: (err: ApiErrorPayload | null) => void

  /**
   * One-time prompt-injection acknowledgement flag. The user must accept
   * the warning modal before any triage action (start / resume / single-
   * finding triage from the Findings detail panel) can fire. Persisted to
   * localStorage so the modal only shows once per browser.
   */
  triageInjectionAcked: boolean
  setTriageInjectionAcked: (acked: boolean) => void

  /** Track triage page status to block project switches. */
  triageRunStatus: TriagePageStatus
  setTriageRunStatus: (status: TriagePageStatus) => void
}

export const useUI = create<UIState>()(
  persist(
    set => ({
      activeProjectId: null,
      setActiveProject: id => set({ activeProjectId: id, selectedFindingIds: new Set() }),

      findingsSegment: 'sast',
      setFindingsSegment: d => set({ findingsSegment: d, selectedFindingIds: new Set() }),

      selectedFindingIds: new Set<number>(),
      toggleSelected: id =>
        set(s => {
          const next = new Set(s.selectedFindingIds)
          if (next.has(id)) next.delete(id)
          else next.add(id)
          return { selectedFindingIds: next }
        }),
      setSelected: ids => set({ selectedFindingIds: new Set(ids) }),
      clearSelected: () => set({ selectedFindingIds: new Set() }),

      findingMutationError: null,
      setFindingMutationError: err => set({ findingMutationError: err }),

      scanMutationError: null,
      setScanMutationError: err => set({ scanMutationError: err }),

      triageMutationError: null,
      setTriageMutationError: err => set({ triageMutationError: err }),

      triageInjectionAcked: false,
      setTriageInjectionAcked: acked => set({ triageInjectionAcked: acked }),

      triageRunStatus: 'idle',
      setTriageRunStatus: status => set({ triageRunStatus: status }),
    }),
    {
      // Storage key pre-dates the additional persisted flags below; kept
      // unchanged to avoid resetting users' active-project selection.
      name: 'tally-ui-active-project',
      partialize: s => ({
        activeProjectId: s.activeProjectId,
        triageInjectionAcked: s.triageInjectionAcked,
      }),
    }
  )
)
