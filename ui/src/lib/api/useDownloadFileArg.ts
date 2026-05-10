import { useMutation } from '@tanstack/react-query'
import { apiFetch, type ApiError } from './client'
import { REST_ENDPOINTS } from './config'

export function useDownloadFileArg() {
  return useMutation<Blob, ApiError, { projectId: number; profileId: number; argName: string }>({
    mutationFn: ({ projectId, profileId, argName }) =>
      apiFetch<Blob>(REST_ENDPOINTS.downloadArgProfileFile(projectId, profileId, argName), {
        parseAs: 'blob',
      }),
  })
}
