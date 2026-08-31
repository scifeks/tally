/**
 * MCP triage-mode hooks: server status polling plus start/stop mutations
 * for the MCP-driven triage flow (as opposed to the auto-triage pipeline).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ApiError } from './client'
import { apiFetch } from './client'
import { REST_ENDPOINTS } from './config'

export interface McpServeStatus {
  active: boolean
  host: string | null
  port: number | null
  source: string | null
}

export interface McpTriageStartResult {
  host: string
  port: number
  token: string
  batch_count: number
  total_findings: number
}

export function useMcpServeStatus() {
  return useQuery<McpServeStatus>({
    queryKey: ['mcp-serve-status'],
    queryFn: async () => apiFetch<McpServeStatus>(REST_ENDPOINTS.mcpServeStatus),
    refetchInterval: 5000,
  })
}

export function useStartMcpTriage(projectId: number) {
  const queryClient = useQueryClient()

  return useMutation<McpTriageStartResult, ApiError, void>({
    mutationFn: async () =>
      apiFetch<McpTriageStartResult>(REST_ENDPOINTS.startMcpTriage(projectId), {
        method: 'POST',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mcp-serve-status'] })
    },
  })
}

export function useStopMcpServe() {
  const queryClient = useQueryClient()

  return useMutation<{ status: string }, ApiError, void>({
    mutationFn: async () =>
      apiFetch<{ status: string }>(REST_ENDPOINTS.stopMcpServe, { method: 'POST' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mcp-serve-status'] })
    },
  })
}
