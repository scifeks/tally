/**
 * Document hooks: list, upload, delete.
 * Mutation errors route through the configMutationError Zustand slice.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { ApiError } from './client'
import { apiFetch } from './client'
import { REST_ENDPOINTS } from './config'
import { useUI } from '../store'
import type { ApiErrorPayload, DocumentSource } from '../types'

interface DocumentListResponseApi {
  items: DocumentSource[]
}

interface DocumentUploadResponseApi {
  filename: string
  chunks: number
}

function toErrorPayload(err: ApiError): ApiErrorPayload {
  return {
    code: err.code,
    message: err.message,
    details: err.details,
    status: err.status,
  }
}

export function useDocuments(projectId: number | null) {
  return useQuery<DocumentSource[]>({
    queryKey: ['documents', projectId],
    queryFn: async () => {
      const data = await apiFetch<DocumentListResponseApi>(
        REST_ENDPOINTS.documents(projectId as number)
      )
      return data.items
    },
    enabled: projectId !== null && projectId > 0,
    staleTime: 10_000,
  })
}

export interface UploadDocumentVariables {
  projectId: number
  file: File
}

export function useUploadDocument() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setConfigMutationError)

  return useMutation<DocumentUploadResponseApi, ApiError, UploadDocumentVariables>({
    mutationFn: async ({ projectId, file }) => {
      const form = new FormData()
      form.append('file', file)
      return apiFetch<DocumentUploadResponseApi>(REST_ENDPOINTS.uploadDocument(projectId), {
        method: 'POST',
        body: form,
      })
    },
    onError: err => setError(toErrorPayload(err)),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['documents', projectId] })
    },
  })
}

export interface DeleteDocumentVariables {
  projectId: number
  filename: string
}

export function useDeleteDocument() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setConfigMutationError)

  return useMutation<void, ApiError, DeleteDocumentVariables>({
    mutationFn: async ({ projectId, filename }) => {
      await apiFetch<void>(REST_ENDPOINTS.deleteDocument(projectId, filename), {
        method: 'DELETE',
      })
    },
    onError: err => setError(toErrorPayload(err)),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['documents', projectId] })
    },
  })
}
