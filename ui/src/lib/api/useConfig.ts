/**
 * Config-page hooks. Live-wired to the Phase 9 backend (project info,
 * repository CRUD + auth, tool overrides). Snake-case wire shapes are
 * kept private to this module; consumers see camelCase domain types.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch, type ApiError } from './client'
import { REST_ENDPOINTS } from './config'
import { useUI } from '../store'
import type {
  ApiErrorPayload,
  ProjectInfo,
  ProjectInfoUpdate,
  RepoLocationMode,
  RepoType,
  RepositoryAuthUpdate,
  RepositoryConfig,
  ToolCatalogEntry,
  ToolLocationMode,
  ToolOverrideConfig,
  ToolType,
} from '../types'

// ─── Wire types (snake_case mirrors of backend Pydantic models) ──────────────

interface ProjectInfoApi {
  id: number
  name: string
  code: string
  company_name: string
  department_name: string
  abbreviation: string
  created_at: string
  path: string
  repo_count: number
  finding_count: number
}

interface RepositoryApi {
  id: number
  uuid: string
  name: string
  type: string[]
  path: string
  docker_path: string
  container_name: string
  languages: string[]
  base_urls: string[]
  test_dirs: string[]
  ignore_dirs: string[]
  dependencies_file: string
  crawl_enabled: boolean
  xsstrike_crawl_level: number
  xsstrike_headers: Record<string, string>
  dalfox_headers: Record<string, string>
  katana_headless: boolean
  katana_depth: number
  katana_headers: Record<string, string>
  endpoint_file: string | null
}

interface RepositoryListResponseApi {
  items: RepositoryApi[]
  total: number
  offset: number
  limit: number
}

interface ToolCatalogItemApi {
  id: string
  name: string
  domain: string
  supports_local: boolean
  supports_docker: boolean
  description: string
}

interface ToolCatalogResponseApi {
  items: ToolCatalogItemApi[]
  total: number
}

interface ToolOverrideItemApi {
  tool_id: string
  type: string
  location: string
  path: string | null
  container: { name: string; tool_path: string } | null
}

interface ToolOverrideResponseApi {
  items: ToolOverrideItemApi[]
  total: number
}

// ─── Mappers (wire <-> domain) ───────────────────────────────────────────────

function mapProjectInfo(api: ProjectInfoApi): ProjectInfo {
  return {
    id: api.id,
    name: api.name,
    code: api.code,
    companyName: api.company_name,
    departmentName: api.department_name,
    abbreviation: api.abbreviation,
    createdAt: api.created_at,
    path: api.path,
    repoCount: api.repo_count,
    findingCount: api.finding_count,
  }
}

function mapRepository(api: RepositoryApi, projectId: number): RepositoryConfig {
  const types = api.type as RepoType[]
  const locationMode: RepoLocationMode = api.container_name ? 'docker' : 'local'
  const docker = api.container_name
    ? { containerName: api.container_name, mountPoint: api.docker_path }
    : undefined
  const result: RepositoryConfig = {
    id: api.id,
    projectId,
    name: api.name,
    types,
    locationMode,
    localPath: api.path,
    docker,
    languages: api.languages,
    testDirectories: api.test_dirs,
    ignoreDirectories: api.ignore_dirs,
    baseUrls: api.base_urls,
    alsoRunCrawlers: api.crawl_enabled,
    katana: {
      headless: api.katana_headless,
      crawlDepth: api.katana_depth,
    },
  }
  if (api.endpoint_file) result.endpointFile = api.endpoint_file
  return result
}

function toRepositoryPayload(repo: RepositoryConfig): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    name: repo.name,
    type: repo.types,
    path: repo.localPath,
    languages: repo.languages,
    base_urls: repo.baseUrls,
    test_dirs: repo.testDirectories,
    ignore_dirs: repo.ignoreDirectories,
    crawl_enabled: repo.alsoRunCrawlers,
    katana_headless: repo.katana.headless,
    katana_depth: repo.katana.crawlDepth,
  }
  if (repo.locationMode === 'docker') {
    payload.docker_path = repo.docker?.mountPoint ?? ''
    payload.container_name = repo.docker?.containerName ?? ''
  } else {
    payload.docker_path = ''
    payload.container_name = ''
  }
  return payload
}

function mapToolCatalog(api: ToolCatalogItemApi): ToolCatalogEntry {
  return {
    id: api.id,
    name: api.name,
    supportsLocal: api.supports_local,
    supportsDocker: api.supports_docker,
  }
}

function mapToolOverride(api: ToolOverrideItemApi): ToolOverrideConfig {
  const out: ToolOverrideConfig = {
    toolId: api.tool_id,
    type: api.type as ToolType,
    location: api.location as ToolLocationMode,
  }
  if (api.path) out.path = api.path
  if (api.container) {
    out.container = { name: api.container.name, toolPath: api.container.tool_path }
  }
  return out
}

function toToolOverrideRequest(o: ToolOverrideConfig): Record<string, unknown> {
  return {
    type: o.type,
    location: o.location,
    path: o.path ?? '',
    container: o.container ? { name: o.container.name, tool_path: o.container.toolPath } : null,
  }
}

function toRepoAuthPayload(auth: RepositoryAuthUpdate): Record<string, unknown> {
  const payload: Record<string, unknown> = {}
  if (auth.loginUrl !== undefined) payload.login_url = auth.loginUrl
  if (auth.usernameField !== undefined) payload.username_field = auth.usernameField
  if (auth.passwordField !== undefined) payload.password_field = auth.passwordField
  if (auth.extraFields !== undefined) payload.extra_fields = auth.extraFields
  if (auth.credentialsEnv !== undefined) payload.credentials_env = auth.credentialsEnv
  if (auth.username !== undefined) payload.username = auth.username
  if (auth.password !== undefined) payload.password = auth.password
  return payload
}

function toErrorPayload(err: ApiError): ApiErrorPayload {
  return {
    code: err.code,
    message: err.message,
    details: err.details,
    status: err.status,
  }
}

// ─── Project Info ────────────────────────────────────────────────────────────

export function useProjectInfo(projectId: number) {
  return useQuery({
    queryKey: ['projectInfo', projectId],
    queryFn: async (): Promise<ProjectInfo> => {
      const api = await apiFetch<ProjectInfoApi>(REST_ENDPOINTS.projectInfo(projectId))
      return mapProjectInfo(api)
    },
    staleTime: 5 * 60 * 1000,
    enabled: Boolean(projectId),
  })
}

export function useUpdateProjectInfo() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setConfigMutationError)

  return useMutation<ProjectInfo, ApiError, { projectId: number; updates: ProjectInfoUpdate }>({
    mutationFn: async ({ projectId, updates }) => {
      const body: Record<string, unknown> = {}
      if (updates.companyName !== undefined) body.company_name = updates.companyName
      if (updates.departmentName !== undefined) body.department_name = updates.departmentName
      if (updates.abbreviation !== undefined) body.abbreviation = updates.abbreviation
      const api = await apiFetch<ProjectInfoApi>(REST_ENDPOINTS.updateProjectInfo(projectId), {
        method: 'PATCH',
        body,
      })
      return mapProjectInfo(api)
    },
    onError: err => setError(toErrorPayload(err)),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['projectInfo', projectId] })
    },
  })
}

// ─── Repositories ────────────────────────────────────────────────────────────

export function useRepositories(projectId: number) {
  return useQuery({
    queryKey: ['repositories', projectId],
    queryFn: async (): Promise<RepositoryConfig[]> => {
      const url = `${REST_ENDPOINTS.repositories(projectId)}?limit=500`
      const api = await apiFetch<RepositoryListResponseApi>(url)
      return api.items.map(item => mapRepository(item, projectId))
    },
    staleTime: 5 * 60 * 1000,
    enabled: Boolean(projectId),
  })
}

export function useRepository(projectId: number, repoId: number) {
  return useQuery({
    queryKey: ['repository', projectId, repoId],
    queryFn: async (): Promise<RepositoryConfig> => {
      const api = await apiFetch<RepositoryApi>(REST_ENDPOINTS.repository(projectId, repoId))
      return mapRepository(api, projectId)
    },
    staleTime: 5 * 60 * 1000,
    enabled: Boolean(projectId) && Boolean(repoId),
  })
}

export function useSaveRepository() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setConfigMutationError)

  return useMutation<
    RepositoryConfig,
    ApiError,
    {
      projectId: number
      repo: RepositoryConfig
      isNew: boolean
      endpointFile?: File | null
    }
  >({
    mutationFn: async ({ projectId, repo, isNew, endpointFile }) => {
      const formData = new FormData()
      formData.append('payload', JSON.stringify(toRepositoryPayload(repo)))
      if (endpointFile) {
        formData.append('endpoint_file', endpointFile)
      }
      const url = isNew
        ? REST_ENDPOINTS.createRepository(projectId)
        : REST_ENDPOINTS.updateRepository(projectId, repo.id)
      const api = await apiFetch<RepositoryApi>(url, {
        method: isNew ? 'POST' : 'PATCH',
        body: formData,
      })
      return mapRepository(api, projectId)
    },
    onError: err => setError(toErrorPayload(err)),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['repositories', projectId] })
    },
  })
}

export function useDeleteRepository() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setConfigMutationError)

  return useMutation<void, ApiError, { projectId: number; repoId: number }>({
    mutationFn: async ({ projectId, repoId }) => {
      await apiFetch<void>(REST_ENDPOINTS.deleteRepository(projectId, repoId), {
        method: 'DELETE',
      })
    },
    onError: err => setError(toErrorPayload(err)),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['repositories', projectId] })
    },
  })
}

export function useUpdateRepoAuth() {
  const setError = useUI(s => s.setConfigMutationError)

  return useMutation<
    void,
    ApiError,
    { projectId: number; repoId: number; auth: RepositoryAuthUpdate }
  >({
    mutationFn: async ({ projectId, repoId, auth }) => {
      await apiFetch<void>(REST_ENDPOINTS.repositoryAuth(projectId, repoId), {
        method: 'PATCH',
        body: toRepoAuthPayload(auth),
      })
    },
    onError: err => setError(toErrorPayload(err)),
  })
}

// ─── Tool Catalog & Overrides ────────────────────────────────────────────────

export function useToolCatalog() {
  return useQuery({
    queryKey: ['toolCatalog'],
    queryFn: async (): Promise<ToolCatalogEntry[]> => {
      const api = await apiFetch<ToolCatalogResponseApi>(REST_ENDPOINTS.toolCatalog)
      return api.items.map(mapToolCatalog)
    },
    staleTime: 30 * 60 * 1000,
  })
}

export function useToolOverrides(projectId: number) {
  return useQuery({
    queryKey: ['toolOverrides', projectId],
    queryFn: async (): Promise<ToolOverrideConfig[]> => {
      const api = await apiFetch<ToolOverrideResponseApi>(REST_ENDPOINTS.toolOverrides(projectId))
      return api.items.map(mapToolOverride)
    },
    staleTime: 5 * 60 * 1000,
    enabled: Boolean(projectId),
  })
}

export function useSaveToolOverride() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setConfigMutationError)

  return useMutation<
    ToolOverrideConfig,
    ApiError,
    { projectId: number; override: ToolOverrideConfig; isNew: boolean }
  >({
    mutationFn: async ({ projectId, override, isNew }) => {
      const url = isNew
        ? REST_ENDPOINTS.createToolOverride(projectId)
        : REST_ENDPOINTS.updateToolOverride(projectId, override.toolId)
      const body: Record<string, unknown> = isNew
        ? { tool_id: override.toolId, ...toToolOverrideRequest(override) }
        : toToolOverrideRequest(override)
      const api = await apiFetch<ToolOverrideItemApi>(url, {
        method: isNew ? 'POST' : 'PUT',
        body,
      })
      return mapToolOverride(api)
    },
    onError: err => setError(toErrorPayload(err)),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['toolOverrides', projectId] })
    },
  })
}

export function useDeleteToolOverride() {
  const queryClient = useQueryClient()
  const setError = useUI(s => s.setConfigMutationError)

  return useMutation<void, ApiError, { projectId: number; toolId: string }>({
    mutationFn: async ({ projectId, toolId }) => {
      await apiFetch<void>(REST_ENDPOINTS.deleteToolOverride(projectId, toolId), {
        method: 'DELETE',
      })
    },
    onError: err => setError(toErrorPayload(err)),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['toolOverrides', projectId] })
    },
  })
}
