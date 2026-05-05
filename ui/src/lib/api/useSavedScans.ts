import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, type ApiError } from './client'
import { REST_ENDPOINTS } from './config'
import { useUI } from '../store'
import type { ApiErrorPayload, SavedScanListItem, SavedScanDetail, Segment } from '../types'

export interface SavedScanListResponse {
  items: SavedScanListItem[]
  total: number
  offset: number
  limit: number
}

export interface SavedScanWriteInput {
  name: string
  skipEnrichment: boolean
  repoIds: number[]
  toolNames: string[]
  skipToolIds: string[]
  segments: Segment[]
  argProfileIds: number[]
}

const LIST_KEY = (projectId: number, offset?: number, limit?: number) =>
  ['savedScans', projectId, offset ?? null, limit ?? null] as const

const DETAIL_KEY = (projectId: number, id: number) => ['savedScans', projectId, id] as const

function toErrorPayload(err: ApiError): ApiErrorPayload {
  return { code: err.code, message: err.message, details: err.details, status: err.status }
}

export function useSavedScans(projectId: number, opts?: { offset?: number; limit?: number }) {
  const params = new URLSearchParams()
  if (opts?.offset !== undefined) params.set('offset', String(opts.offset))
  if (opts?.limit !== undefined) params.set('limit', String(opts.limit))
  const qs = params.toString()

  return useQuery({
    queryKey: LIST_KEY(projectId, opts?.offset, opts?.limit),
    queryFn: async (): Promise<SavedScanListResponse> => {
      const url = `${REST_ENDPOINTS.listSavedScans(projectId)}${qs ? `?${qs}` : ''}`
      return apiFetch<SavedScanListResponse>(url)
    },
    staleTime: 5 * 60 * 1000,
    enabled: Boolean(projectId),
  })
}

export function useSavedScan(projectId: number, id: number | null) {
  return useQuery({
    queryKey: DETAIL_KEY(projectId, id ?? 0),
    queryFn: async (): Promise<SavedScanDetail> =>
      apiFetch<SavedScanDetail>(REST_ENDPOINTS.getSavedScan(projectId, id as number)),
    staleTime: 5 * 60 * 1000,
    enabled: Boolean(projectId && id),
  })
}

export function useSaveScan() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setConfigMutationError)

  return useMutation<
    SavedScanDetail,
    ApiError,
    { projectId: number; payload: SavedScanWriteInput; existingId?: number }
  >({
    mutationFn: async ({ projectId, payload, existingId }) => {
      const url = existingId
        ? REST_ENDPOINTS.updateSavedScan(projectId, existingId)
        : REST_ENDPOINTS.createSavedScan(projectId)
      return apiFetch<SavedScanDetail>(url, {
        method: existingId ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
    },
    onError: err => setError(toErrorPayload(err)),
    onSuccess: (saved, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['savedScans', projectId] })
      queryClient.invalidateQueries({ queryKey: DETAIL_KEY(projectId, saved.id) })
    },
  })
}

export function useDeleteSavedScan() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setConfigMutationError)

  return useMutation<void, ApiError, { projectId: number; savedScanId: number }>({
    mutationFn: async ({ projectId, savedScanId }) => {
      await apiFetch<void>(REST_ENDPOINTS.deleteSavedScan(projectId, savedScanId), {
        method: 'DELETE',
      })
    },
    onError: err => setError(toErrorPayload(err)),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['savedScans', projectId] })
    },
  })
}
