import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ApiError } from './client'
import { apiFetch } from './client'
import { REST_ENDPOINTS } from './config'

interface BurpPollStatusApi {
  project_id: number
  configured: boolean
  active: boolean
}

export interface BurpPollStatus {
  projectId: number
  configured: boolean
  active: boolean
}

function mapStatus(api: BurpPollStatusApi): BurpPollStatus {
  return {
    projectId: api.project_id,
    configured: api.configured,
    active: api.active,
  }
}

export function useBurpPollStatus(projectId: number) {
  return useQuery<BurpPollStatus>({
    queryKey: ['burpPoll', projectId, 'status'],
    queryFn: async () => {
      const data = await apiFetch<BurpPollStatusApi>(REST_ENDPOINTS.burpPollStatus(projectId))
      return mapStatus(data)
    },
    enabled: projectId > 0,
    refetchInterval: 5000,
  })
}

export function useStartBurpPoll() {
  const queryClient = useQueryClient()

  return useMutation<{ projectId: number; status: string }, ApiError, { projectId: number }>({
    mutationFn: async ({ projectId }) => {
      const data = await apiFetch<{
        project_id: number
        status: string
      }>(REST_ENDPOINTS.startBurpPoll(projectId), {
        method: 'POST',
      })
      return {
        projectId: data.project_id,
        status: data.status,
      }
    },
    onSuccess: (_, { projectId }) => {
      queryClient.setQueryData<BurpPollStatus>(['burpPoll', projectId, 'status'], prev =>
        prev ? { ...prev, active: true } : prev
      )
    },
  })
}

export function useCancelBurpPoll() {
  const queryClient = useQueryClient()

  return useMutation<{ projectId: number; status: string }, ApiError, { projectId: number }>({
    mutationFn: async ({ projectId }) => {
      const data = await apiFetch<{
        project_id: number
        status: string
      }>(REST_ENDPOINTS.cancelBurpPoll(projectId), {
        method: 'POST',
      })
      return {
        projectId: data.project_id,
        status: data.status,
      }
    },
    onSuccess: (_, { projectId }) => {
      queryClient.setQueryData<BurpPollStatus>(['burpPoll', projectId, 'status'], prev =>
        prev ? { ...prev, active: false } : prev
      )
    },
  })
}
