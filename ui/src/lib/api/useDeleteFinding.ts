import { useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query'
import type { ApiError } from './client'
import { apiFetch } from './client'
import { REST_ENDPOINTS } from './config'
import { useUI } from '../store'
import type { Finding } from '../types'

interface DeleteFindingVariables {
  projectId: string
  findingId: number
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

export function useDeleteFinding() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setFindingMutationError)

  return useMutation<void, ApiError, DeleteFindingVariables>({
    mutationFn: async ({ projectId, findingId }) => {
      await apiFetch(REST_ENDPOINTS.deleteFinding(projectId, findingId), {
        method: 'DELETE',
      })
    },
    onSuccess: (_data, { projectId, findingId }) => {
      const entries = queryClient.getQueriesData<InfiniteFindingsCache>({
        queryKey: ['findings', projectId],
      })
      for (const [key, cache] of entries as Array<[QueryKey, InfiniteFindingsCache | undefined]>) {
        if (!cache) continue
        queryClient.setQueryData<InfiniteFindingsCache>(key, {
          ...cache,
          pages: cache.pages.map(p => ({
            ...p,
            items: p.items.filter(it => it.id !== findingId),
            total: p.total - 1,
          })),
        })
      }
      queryClient.invalidateQueries({ queryKey: ['findingsCounts', projectId] })
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
