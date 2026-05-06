import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, type ApiError } from './client'
import { REST_ENDPOINTS } from './config'
import { useUI } from '../store'
import type { ApiErrorPayload, ArgumentTemplate } from '../types'

type ArgProfileFlagArg = { name: string; type: 'flag' }
type ArgProfileStringArg = { name: string; type: 'string'; value: string }
type ArgProfileFileArg = { name: string; type: 'file'; path: string; downloadUrl?: string }

export type ArgProfileArg = ArgProfileFlagArg | ArgProfileStringArg | ArgProfileFileArg

export interface ToolArgProfile {
  id: number
  toolName: string
  name: string
  args: ArgProfileArg[]
  createdAt: string
  updatedAt: string
}

export interface ToolArgProfileListResponse {
  items: ToolArgProfile[]
  total: number
  offset: number
  limit: number
}

export interface ToolArgProfileWriteInput {
  toolName: string
  name: string
  args: ArgProfileArg[]
}

export function mapProfilesToTemplates(profiles: ToolArgProfile[]): ArgumentTemplate[] {
  return profiles.map(p => ({
    id: String(p.id),
    name: p.name,
    arguments: p.args.map(a => {
      if (a.type === 'flag') {
        return { id: a.name, flag: a.name, valueType: 'none' as const }
      }
      if (a.type === 'string') {
        return { id: a.name, flag: a.name, valueType: 'string' as const, value: a.value }
      }
      return {
        id: a.name,
        flag: a.name,
        valueType: 'file' as const,
        value: a.path,
        fileName: a.name,
      }
    }),
  }))
}

export function mapTemplateToWriteInput(
  toolName: string,
  template: ArgumentTemplate
): ToolArgProfileWriteInput {
  return {
    toolName,
    name: template.name,
    args: template.arguments.map(a => {
      if (a.valueType === 'none') return { name: a.flag, type: 'flag' as const }
      if (a.valueType === 'string') {
        return { name: a.flag, type: 'string' as const, value: a.value ?? '' }
      }
      return { name: a.flag, type: 'file' as const, path: '' }
    }),
  }
}

export function profileMatchesTemplate(
  profile: ToolArgProfile,
  template: ArgumentTemplate
): boolean {
  if (profile.name !== template.name) return false
  if (profile.args.length !== template.arguments.length) return false
  return profile.args.every((a, i) => {
    const t = template.arguments[i]
    if (!t) return false
    if (a.type === 'flag') return t.valueType === 'none' && t.flag === a.name
    if (a.type === 'string') {
      return t.valueType === 'string' && t.flag === a.name && t.value === a.value
    }
    return t.valueType === 'file' && t.flag === a.name
  })
}

const LIST_KEY = (projectId: number, toolName?: string, offset?: number, limit?: number) =>
  ['argProfiles', projectId, toolName ?? null, offset ?? null, limit ?? null] as const

const DETAIL_KEY = (projectId: number, id: number) => ['argProfiles', projectId, id] as const

function toErrorPayload(err: ApiError): ApiErrorPayload {
  return { code: err.code, message: err.message, details: err.details, status: err.status }
}

export function useToolArgProfileList(
  projectId: number,
  opts?: { toolName?: string; offset?: number; limit?: number }
) {
  const params = new URLSearchParams()
  if (opts?.toolName) params.set('tool_name', opts.toolName)
  if (opts?.offset !== undefined) params.set('offset', String(opts.offset))
  if (opts?.limit !== undefined) params.set('limit', String(opts.limit))
  const qs = params.toString()

  return useQuery({
    queryKey: LIST_KEY(projectId, opts?.toolName, opts?.offset, opts?.limit),
    queryFn: async (): Promise<ToolArgProfileListResponse> => {
      const url = `${REST_ENDPOINTS.listArgProfiles(projectId)}${qs ? `?${qs}` : ''}`
      return apiFetch<ToolArgProfileListResponse>(url)
    },
    staleTime: 5 * 60 * 1000,
    enabled: Boolean(projectId),
  })
}

export function useSaveToolArgProfile() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setConfigMutationError)

  return useMutation<
    ToolArgProfile,
    ApiError,
    {
      projectId: number
      profile: ToolArgProfileWriteInput
      files: Record<string, File>
      existingId?: number
    }
  >({
    mutationFn: async ({ projectId, profile, files, existingId }) => {
      const formData = new FormData()
      formData.append('payload', JSON.stringify(profile))
      for (const [argName, file] of Object.entries(files)) {
        formData.append(argName, file)
      }
      const url = existingId
        ? REST_ENDPOINTS.updateArgProfile(projectId, existingId)
        : REST_ENDPOINTS.createArgProfile(projectId)
      return apiFetch<ToolArgProfile>(url, {
        method: existingId ? 'PUT' : 'POST',
        body: formData,
      })
    },
    onError: err => setError(toErrorPayload(err)),
    onSuccess: (saved, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['argProfiles', projectId] })
      queryClient.invalidateQueries({ queryKey: DETAIL_KEY(projectId, saved.id) })
    },
  })
}

export function useDeleteToolArgProfile() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setConfigMutationError)

  return useMutation<void, ApiError, { projectId: number; profileId: number }>({
    mutationFn: async ({ projectId, profileId }) => {
      await apiFetch<void>(REST_ENDPOINTS.deleteArgProfile(projectId, profileId), {
        method: 'DELETE',
      })
    },
    onError: err => setError(toErrorPayload(err)),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['argProfiles', projectId] })
    },
  })
}
