/**
 * useRuntime Hooks
 * ================
 * Cross-project hooks for runtime dependency probes and installed tool
 * names. Backed by `GET /api/v1/runtime-dependencies` (Phase 2.6) and
 * `GET /api/v1/tools/installed` (Phase 6.8) - both are auth-only and
 * carry no project context.
 *
 * The Triage page consumes `useRuntimeDependencies()` to gate the
 * "Start Triage" button on `claude.installed`.
 */

import { useQuery } from '@tanstack/react-query'
import { apiFetch } from './client'
import { REST_ENDPOINTS } from './config'
import type {
  RuntimeDependenciesResponse,
  RuntimeDependency,
  InstalledToolsResponse,
} from '../types'

interface RuntimeDependencyApiItem {
  name: string
  installed: boolean
  binary_path: string | null
  version: string | null
  install_hint: string
  required_for: string[]
  error: string | null
}

interface RuntimeDependenciesApiResponse {
  dependencies: RuntimeDependencyApiItem[]
}

function toRuntimeDependency(item: RuntimeDependencyApiItem): RuntimeDependency {
  return {
    name: item.name,
    installed: item.installed,
    binaryPath: item.binary_path,
    version: item.version,
    installHint: item.install_hint,
    requiredFor: item.required_for,
    error: item.error,
  }
}

export function useRuntimeDependencies() {
  return useQuery({
    queryKey: ['runtime-dependencies'],
    queryFn: async (): Promise<RuntimeDependenciesResponse> => {
      const data = await apiFetch<RuntimeDependenciesApiResponse>(
        REST_ENDPOINTS.runtimeDependencies
      )
      return {
        dependencies: data.dependencies.map(toRuntimeDependency),
      }
    },
    staleTime: 30 * 1000,
  })
}

export function useInstalledTools() {
  return useQuery({
    queryKey: ['installed-tools'],
    queryFn: async (): Promise<InstalledToolsResponse> => {
      return apiFetch<InstalledToolsResponse>(REST_ENDPOINTS.installedTools)
    },
    staleTime: 30 * 1000,
  })
}
