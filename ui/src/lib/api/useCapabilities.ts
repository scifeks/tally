/**
 * Hook to fetch platform-level capabilities (chat, triage, report retention).
 */

import { useQuery } from '@tanstack/react-query'
import { apiFetch } from './client'
import { REST_ENDPOINTS } from './config'

export interface Capabilities {
  chatEnabled: boolean
  triageEnabled: boolean
  reportRetentionEnabled: boolean
  maxReportHistory: number
  triageBackendLabel: string | null
}

interface CapabilitiesApi {
  chat_enabled: boolean
  triage_enabled: boolean
  report_retention_enabled: boolean
  max_report_history: number
  triage_backend_label: string | null
}

function mapCapabilities(api: CapabilitiesApi): Capabilities {
  return {
    chatEnabled: api.chat_enabled,
    triageEnabled: api.triage_enabled,
    reportRetentionEnabled: api.report_retention_enabled,
    maxReportHistory: api.max_report_history,
    triageBackendLabel: api.triage_backend_label,
  }
}

export function useCapabilities() {
  return useQuery({
    queryKey: ['capabilities'],
    queryFn: async (): Promise<Capabilities> => {
      const api = await apiFetch<CapabilitiesApi>(REST_ENDPOINTS.capabilities)
      return mapCapabilities(api)
    },
    staleTime: 30 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
  })
}
