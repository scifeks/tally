/**
 * useUpdateFinding Mutation
 * =========================
 * Project-scoped PATCH against
 * `/api/v1/projects/:projectId/findings/:findingId`.
 *
 * Behavior:
 *  - **Optimistic.** `onMutate` snapshots every cached page of
 *    `['findings', projectId, *]` and patches the matching row in place
 *    so the UI reflects the edit before the network resolves.
 *  - **Rollback + error modal on failure.** On error the snapshot is
 *    restored AND the global `findingMutationError` slice is populated so
 *    the user sees a modal explaining the rollback (especially for
 *    `FINDING_LOCKED` 409s - the analyst can't be allowed to silently
 *    miss an unsaved edit).
 *  - **Counts invalidation.** When the canonical response shows that
 *    `severity` or `status` actually changed, invalidate
 *    `['findingsCounts', projectId]` so the dashboard tiles refresh.
 *  - **Cache merge on success.** The backend-canonical row replaces the
 *    optimistic patch across every cached page that contained the id.
 */

import { useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query'
import type { ApiError } from './client'
import { apiFetch } from './client'
import { REST_ENDPOINTS } from './config'
import { mapFinding } from './useFindings'
import { useUI } from '../store'
import type { Finding, Severity, Status } from '../types'

/** Mutable subset of Finding the detail panel can edit. */
export interface UpdateFindingPatch {
  severity?: Severity
  status?: Status
  title?: string
  notes?: string
  description?: string
  triagedBy?: 'claude-code' | 'analyst_web'
}

interface UpdateFindingVariables {
  projectId: string
  id: number
  patch: UpdateFindingPatch
}

interface FindingsPageShape {
  items: Finding[]
  total: number
  offset: number
  limit: number
}

interface InfiniteFindingsCache {
  pages: FindingsPageShape[]
  pageParams: unknown[]
}

type FindingApiResponse = Parameters<typeof mapFinding>[0]

/**
 * Apply `patcher` to every page of every `['findings', projectId, *]`
 * cache entry. Returns the snapshot of pre-patch entries so callers can
 * restore on rollback.
 */
function patchEveryFindingsCache(
  queryClient: ReturnType<typeof useQueryClient>,
  projectId: string,
  patcher: (item: Finding) => Finding
): Array<[QueryKey, InfiniteFindingsCache | undefined]> {
  const entries = queryClient.getQueriesData<InfiniteFindingsCache>({
    queryKey: ['findings', projectId],
  })
  const snapshot: Array<[QueryKey, InfiniteFindingsCache | undefined]> = []
  for (const [key, cache] of entries) {
    snapshot.push([key, cache ? structuredClone(cache) : undefined])
    if (!cache) continue
    queryClient.setQueryData<InfiniteFindingsCache>(key, {
      ...cache,
      pages: cache.pages.map(p => ({
        ...p,
        items: p.items.map(it => patcher(it)),
      })),
    })
  }
  return snapshot
}

export function useUpdateFinding() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setFindingMutationError)

  return useMutation<
    Finding,
    ApiError,
    UpdateFindingVariables,
    {
      snapshot: Array<[QueryKey, InfiniteFindingsCache | undefined]>
      previous: Finding | undefined
    }
  >({
    mutationFn: async ({ projectId, id, patch }) => {
      const body: Record<string, unknown> = {}
      if (patch.severity !== undefined) body.severity = patch.severity
      if (patch.status !== undefined) body.status = patch.status
      if (patch.title !== undefined) body.title = patch.title
      if (patch.notes !== undefined) body.notes = patch.notes
      if (patch.description !== undefined) body.description = patch.description
      const data = await apiFetch<FindingApiResponse>(REST_ENDPOINTS.updateFinding(projectId, id), {
        method: 'PATCH',
        body,
      })
      return mapFinding(data)
    },
    onMutate: async ({ projectId, id, patch }) => {
      await queryClient.cancelQueries({ queryKey: ['findings', projectId] })
      let previous: Finding | undefined
      const snapshot = patchEveryFindingsCache(queryClient, projectId, item => {
        if (item.id !== id) return item
        if (!previous) previous = item
        return { ...item, ...patch }
      })
      return { snapshot, previous }
    },
    onError: (err, _vars, ctx) => {
      if (ctx?.snapshot) {
        for (const [key, cache] of ctx.snapshot) {
          queryClient.setQueryData(key, cache)
        }
      }
      setError({
        code: err.code,
        message: err.message,
        details: err.details,
        status: err.status,
      })
    },
    onSuccess: (updated, { projectId }, ctx) => {
      patchEveryFindingsCache(queryClient, projectId, item =>
        item.id === updated.id ? updated : item
      )
      const prev = ctx?.previous
      if (prev && (prev.severity !== updated.severity || prev.status !== updated.status)) {
        queryClient.invalidateQueries({ queryKey: ['findingsCounts', projectId] })
      }
    },
  })
}
