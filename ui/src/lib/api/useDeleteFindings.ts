import { useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query'
import type { ApiError } from './client'
import { apiFetch } from './client'
import { REST_ENDPOINTS } from './config'
import { useUI } from '../store'
import type { Finding } from '../types'

interface DeleteFindingsVariables {
  projectId: string
  ids: number[]
}

interface BatchDeleteFindingsResponse {
  deleted: number[]
  skipped_locked: number[]
  not_found: number[]
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

export function useDeleteFindings() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setFindingMutationError)
  const clearSelected = useUI(s => s.clearSelected)

  return useMutation<BatchDeleteFindingsResponse, ApiError, DeleteFindingsVariables>({
    mutationFn: async ({ projectId, ids }) =>
      apiFetch<BatchDeleteFindingsResponse>(REST_ENDPOINTS.batchDeleteFindings(projectId), {
        method: 'POST',
        body: { ids },
      }),
    onSuccess: (data, { projectId }) => {
      const deletedIds = new Set(data.deleted)
      const entries = queryClient.getQueriesData<InfiniteFindingsCache>({
        queryKey: ['findings', projectId],
      })
      for (const [key, cache] of entries as Array<[QueryKey, InfiniteFindingsCache | undefined]>) {
        if (!cache) continue
        queryClient.setQueryData<InfiniteFindingsCache>(key, {
          ...cache,
          pages: cache.pages.map(p => {
            const removed = p.items.filter(it => deletedIds.has(it.id)).length
            return {
              ...p,
              items: p.items.filter(it => !deletedIds.has(it.id)),
              total: p.total - removed,
            }
          }),
        })
      }
      queryClient.invalidateQueries({ queryKey: ['findingsCounts', projectId] })
      queryClient.invalidateQueries({ queryKey: ['findingsFilterOptions', projectId] })
      clearSelected()
    },
    onError: err => {
      setError({
        code: err.code,
        message: err.message,
        details: err.details,
        status: err.status,
      })
    },
  })
}
