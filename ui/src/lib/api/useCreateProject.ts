import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch, type ApiError } from './client'
import { REST_ENDPOINTS } from './config'
import type { Project } from '../types'

interface ProjectCreateApi {
  id: number
  name: string
  code: string
  created_at: string
}

export interface CreateProjectInput {
  name: string
  companyName?: string
  departmentName?: string
  abbreviation?: string
}

export function useCreateProject() {
  const queryClient = useQueryClient()

  return useMutation<Project, ApiError, CreateProjectInput>({
    mutationFn: async input => {
      const body: Record<string, unknown> = { name: input.name }
      if (input.companyName) body.company_name = input.companyName
      if (input.departmentName) body.department_name = input.departmentName
      if (input.abbreviation) body.abbreviation = input.abbreviation
      const data = await apiFetch<ProjectCreateApi>(REST_ENDPOINTS.createProject, {
        method: 'POST',
        body,
      })
      return { id: data.id, name: data.name, code: data.code }
    },
    onSuccess: data => {
      queryClient.setQueryData<Project[]>(['projects'], old => (old ? [...old, data] : [data]))
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}
