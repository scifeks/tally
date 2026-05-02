/**
 * Tool Argument Profiles hooks (CLIENT-SIDE MOCK)
 * ===============================================
 * Backs the v0-ported "Argument Templates" panel on the tool override card.
 * Holds `argsMode` and `argumentTemplates` for each (projectId, toolId)
 * pair entirely client-side; the real `useToolOverrides` save flow is not
 * touched, so the production override save endpoint remains unaware of
 * these new fields. State resets on full page reload — intentional.
 *
 * When the backend lands, this module retires in favour of fields on
 * ToolOverrideConfig (or a separate `tool_arg_profiles` resource per the
 * schema doc). The hook signatures stay stable so the consumer doesn't
 * change.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ArgsMode, ArgumentTemplate } from '../types'

export interface ToolArgProfile {
  argsMode: ArgsMode
  argumentTemplates: ArgumentTemplate[]
}

const DEFAULT: ToolArgProfile = { argsMode: 'stock', argumentTemplates: [] }

// ─── Seed data ───────────────────────────────────────────────────────────────

const SEED: Record<number, Record<string, ToolArgProfile>> = {
  1: {
    gitleaks: {
      argsMode: 'custom',
      argumentTemplates: [
        {
          id: 'tmpl-verbose-scan',
          name: 'verbose-scan',
          arguments: [
            { id: 'arg-verbose', flag: '--verbose', valueType: 'none' },
            {
              id: 'arg-config',
              flag: '--config',
              valueType: 'string',
              value: '.gitleaks.toml',
            },
          ],
        },
      ],
    },
  },
}

// ─── In-memory store ─────────────────────────────────────────────────────────

function cloneProfile(p: ToolArgProfile): ToolArgProfile {
  return {
    argsMode: p.argsMode,
    argumentTemplates: p.argumentTemplates.map(t => ({
      ...t,
      arguments: t.arguments.map(a => ({ ...a })),
    })),
  }
}

const store: Map<number, Map<string, ToolArgProfile>> = new Map()
for (const [pid, byTool] of Object.entries(SEED)) {
  const inner = new Map<string, ToolArgProfile>()
  for (const [toolId, profile] of Object.entries(byTool)) {
    inner.set(toolId, cloneProfile(profile))
  }
  store.set(Number(pid), inner)
}

function getProfile(projectId: number, toolId: string): ToolArgProfile {
  const inner = store.get(projectId)
  const found = inner?.get(toolId)
  return found ? cloneProfile(found) : { ...DEFAULT }
}

function setProfile(projectId: number, toolId: string, profile: ToolArgProfile): void {
  let inner = store.get(projectId)
  if (!inner) {
    inner = new Map()
    store.set(projectId, inner)
  }
  inner.set(toolId, cloneProfile(profile))
}

function deleteProfile(projectId: number, toolId: string): void {
  store.get(projectId)?.delete(toolId)
}

/** All profiles for a project, used by SavedScansTab to surface templates. */
export function listProfiles(
  projectId: number
): Array<{ toolId: string; profile: ToolArgProfile }> {
  const inner = store.get(projectId)
  if (!inner) return []
  return Array.from(inner.entries()).map(([toolId, profile]) => ({
    toolId,
    profile: cloneProfile(profile),
  }))
}

// ─── Hooks ───────────────────────────────────────────────────────────────────

const QUERY_KEY = (projectId: number, toolId: string) =>
  ['toolArgProfile', projectId, toolId] as const

const LIST_QUERY_KEY = (projectId: number) => ['toolArgProfiles', projectId] as const

export function useToolArgProfile(projectId: number, toolId: string | null) {
  return useQuery({
    queryKey: QUERY_KEY(projectId, toolId ?? ''),
    queryFn: async (): Promise<ToolArgProfile> => {
      await new Promise(resolve => setTimeout(resolve, 50))
      return getProfile(projectId, toolId ?? '')
    },
    enabled: Boolean(projectId) && Boolean(toolId),
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * Lists every profile in the project. Used by SavedScansTab to render the
 * tool list with `tool:templateId` template entries alongside base tools.
 */
export function useToolArgProfileList(projectId: number) {
  return useQuery({
    queryKey: LIST_QUERY_KEY(projectId),
    queryFn: async (): Promise<Array<{ toolId: string; profile: ToolArgProfile }>> => {
      await new Promise(resolve => setTimeout(resolve, 50))
      return listProfiles(projectId)
    },
    enabled: Boolean(projectId),
    staleTime: 5 * 60 * 1000,
  })
}

export function useSaveToolArgProfile() {
  const queryClient = useQueryClient()

  return useMutation<
    ToolArgProfile,
    Error,
    { projectId: number; toolId: string; profile: ToolArgProfile }
  >({
    mutationFn: async ({ projectId, toolId, profile }) => {
      await new Promise(resolve => setTimeout(resolve, 50))
      setProfile(projectId, toolId, profile)
      return cloneProfile(profile)
    },
    onSuccess: (_, { projectId, toolId }) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY(projectId, toolId) })
      queryClient.invalidateQueries({ queryKey: LIST_QUERY_KEY(projectId) })
    },
  })
}

export function useDeleteToolArgProfile() {
  const queryClient = useQueryClient()

  return useMutation<void, Error, { projectId: number; toolId: string }>({
    mutationFn: async ({ projectId, toolId }) => {
      await new Promise(resolve => setTimeout(resolve, 50))
      deleteProfile(projectId, toolId)
    },
    onSuccess: (_, { projectId, toolId }) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY(projectId, toolId) })
      queryClient.invalidateQueries({ queryKey: LIST_QUERY_KEY(projectId) })
    },
  })
}
