import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch, type ApiError } from './client'
import { REST_ENDPOINTS } from './config'
import { useUI } from '../store'
import type { GlobalToolSettings, FileSystemBrowseResult } from '../types'

export function useGlobalToolSettings() {
  return useQuery({
    queryKey: ['globalToolSettings'],
    queryFn: async (): Promise<GlobalToolSettings> => {
      const api = await apiFetch<{ ffufWordlistPaths: string[] }>(REST_ENDPOINTS.globalToolSettings)
      return { ffufWordlistPaths: api.ffufWordlistPaths }
    },
    staleTime: 5 * 60 * 1000,
  })
}

export function useUpdateGlobalToolSettings() {
  const queryClient = useQueryClient()
  const showToast = useUI(s => s.showToast)

  return useMutation<GlobalToolSettings, ApiError, GlobalToolSettings>({
    mutationFn: async settings => {
      const api = await apiFetch<{ ffufWordlistPaths: string[] }>(
        REST_ENDPOINTS.globalToolSettings,
        {
          method: 'PUT',
          body: { ffufWordlistPaths: settings.ffufWordlistPaths },
        }
      )
      return { ffufWordlistPaths: api.ffufWordlistPaths }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['globalToolSettings'] })
      showToast('Tool settings saved')
    },
  })
}

export function useBrowseFilesystem(path: string) {
  return useQuery({
    queryKey: ['fsBrowse', path],
    queryFn: async (): Promise<FileSystemBrowseResult> =>
      apiFetch<FileSystemBrowseResult>(REST_ENDPOINTS.fsBrowse(path)),
    enabled: Boolean(path),
    staleTime: 10 * 1000,
  })
}
