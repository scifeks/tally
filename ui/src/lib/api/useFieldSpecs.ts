import { useQuery } from '@tanstack/react-query'
import { apiFetch } from './client'
import { REST_ENDPOINTS } from './config'

interface FieldSpecEnums {
  severities: string[]
  confidence_levels: string[]
  finding_types: string[]
  statuses: string[]
}

interface FieldSpecsApi {
  enums: FieldSpecEnums
}

export interface FieldSpecs {
  severities: string[]
  confidenceLevels: string[]
  findingTypes: string[]
  statuses: string[]
}

export function useFieldSpecs() {
  return useQuery<FieldSpecs>({
    queryKey: ['fieldSpecs'],
    queryFn: async () => {
      const data = await apiFetch<FieldSpecsApi>(REST_ENDPOINTS.fieldSpecs)
      return {
        severities: data.enums.severities,
        confidenceLevels: data.enums.confidence_levels,
        findingTypes: data.enums.finding_types,
        statuses: data.enums.statuses,
      }
    },
    staleTime: 10 * 60 * 1000,
  })
}
