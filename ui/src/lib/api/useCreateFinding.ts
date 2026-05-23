import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { ApiError } from './client'
import { apiFetch } from './client'
import { REST_ENDPOINTS } from './config'
import { mapFinding } from './useFindings'
import type { Finding } from '../types'

type FindingApiResponse = Parameters<typeof mapFinding>[0]

export interface CreateFindingInput {
  title: string
  severity: string
  segment: string
  repoId?: number
  file?: string
  url?: string
  status?: string
  confidence?: string
  findingType?: string[]
  cwe?: string[]
  vulnerabilityId?: string
  description?: string
  notes?: string
}

interface CreateFindingVariables {
  projectId: string
  input: CreateFindingInput
}

export function useCreateFinding() {
  const queryClient = useQueryClient()

  return useMutation<Finding, ApiError, CreateFindingVariables>({
    mutationFn: async ({ projectId, input }) => {
      const body: Record<string, unknown> = {
        title: input.title,
        severity: input.severity,
        segment: input.segment,
      }
      if (input.repoId !== undefined) body.repo_id = input.repoId
      if (input.file) body.file = input.file
      if (input.url) body.url = input.url
      if (input.status) body.status = input.status
      if (input.confidence) body.confidence = input.confidence
      if (input.findingType?.length) body.finding_type = input.findingType
      if (input.cwe?.length) body.cwe = input.cwe
      if (input.vulnerabilityId) body.vulnerability_id = input.vulnerabilityId
      if (input.description) body.description = input.description
      if (input.notes) body.notes = input.notes
      const data = await apiFetch<FindingApiResponse>(REST_ENDPOINTS.createFinding(projectId), {
        method: 'POST',
        body,
      })
      return mapFinding(data)
    },
    onSuccess: (_data, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['findings', projectId] })
      queryClient.invalidateQueries({ queryKey: ['findingsCounts', projectId] })
    },
  })
}
