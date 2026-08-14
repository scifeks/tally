import { useQuery } from '@tanstack/react-query'
import { apiFetch } from './client'
import { REST_ENDPOINTS } from './config'
import type { FileSystemBrowseResult } from '../types'

export function useBrowseFilesystem(path: string) {
  return useQuery({
    queryKey: ['fsBrowse', path],
    queryFn: async (): Promise<FileSystemBrowseResult> =>
      apiFetch<FileSystemBrowseResult>(REST_ENDPOINTS.fsBrowse(path)),
    enabled: Boolean(path),
    staleTime: 10 * 1000,
  })
}
