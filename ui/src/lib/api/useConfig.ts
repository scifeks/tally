/**
 * Config-page hooks for project info, repository CRUD + auth, tool
 * overrides. Snake-case wire shapes are kept private to this module;
 * consumers see camelCase domain types.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch, type ApiError } from './client'
import { REST_ENDPOINTS } from './config'
import { useUI } from '../store'
import type {
  ApiErrorPayload,
  ArgsMode,
  ProjectInfo,
  ProjectInfoUpdate,
  RepoLocationMode,
  RepoType,
  RepositoryAuthUpdate,
  RepositoryConfig,
  ServiceConfig,
  ToolCatalogEntry,
  ToolLocationMode,
  ToolOverrideConfig,
  ToolType,
} from '../types'
import { emptyService } from '../types'

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

interface ServiceApi {
  name: string
  relative_path: string
  type: string[]
  languages: string[]
  docker_path: string
  container_name: string
  base_urls: string[]
  test_dirs: string[]
  ignore_dirs: string[]
  dependencies_file: string
  crawl_enabled: boolean
  katana_headless?: boolean | null
  katana_depth?: number | null
}

interface RepositoryApi {
  id: number
  name: string
  path: string
  services: ServiceApi[]
  xsstrike_crawl_level: number
  xsstrike_headers: Record<string, string>
  dalfox_headers: Record<string, string>
  katana_headless: boolean
  katana_depth: number
  katana_headers: Record<string, string>
  auth_configured?: boolean
  auth_type?: 'form' | 'header'
  auth_headers_meta?: Array<{
    header: string
    value: string
    value_env: string
  }>
  auth_login_url?: string
  endpoint_file: string | null
  garak_config_file: string | null
  // Flat fields kept for backward-compat with pre-migration responses
  type?: string[]
  docker_path?: string
  container_name?: string
  languages?: string[]
  base_urls?: string[]
  test_dirs?: string[]
  ignore_dirs?: string[]
  dependencies_file?: string
  crawl_enabled?: boolean
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
  requires_base_urls: boolean
  requires_url_inventory: boolean
}

interface ToolCatalogResponseApi {
  items: ToolCatalogItemApi[]
  total: number
}

interface ToolOverrideItemApi {
  id: number
  toolName: string
  argsMode: ArgsMode
  type: string
  location: string
  path: string | null
  container: { name: string; toolPath: string } | null
}

interface ToolOverrideResponseApi {
  items: ToolOverrideItemApi[]
  total: number
  offset: number
  limit: number
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

function mapServiceApi(svc: ServiceApi): ServiceConfig {
  const locationMode: RepoLocationMode = svc.container_name ? 'docker' : 'local'
  return {
    name: svc.name,
    relativePath: svc.relative_path || '',
    type: (svc.type || []) as RepoType[],
    languages: svc.languages || [],
    locationMode,
    docker: svc.container_name
      ? {
          containerName: svc.container_name,
          mountPoint: svc.docker_path,
        }
      : undefined,
    baseUrls: svc.base_urls || [],
    testDirectories: svc.test_dirs || [],
    ignoreDirectories: svc.ignore_dirs || [],
    dependenciesFile: svc.dependencies_file || '',
    crawlEnabled: svc.crawl_enabled !== false,
    katanaHeadless: svc.katana_headless ?? null,
    katanaCrawlDepth: svc.katana_depth ?? null,
  }
}

function mapRepository(api: RepositoryApi, projectId: number): RepositoryConfig {
  let services: ServiceConfig[]
  if (api.services && api.services.length > 0) {
    services = api.services.map(mapServiceApi)
  } else {
    // Fallback for pre-migration responses with flat fields
    const svc = emptyService()
    svc.type = (api.type || []) as RepoType[]
    svc.languages = api.languages || []
    svc.locationMode = api.container_name ? 'docker' : 'local'
    if (api.container_name) {
      svc.docker = {
        containerName: api.container_name,
        mountPoint: api.docker_path || '',
      }
    }
    svc.baseUrls = api.base_urls || []
    svc.testDirectories = api.test_dirs || []
    svc.ignoreDirectories = api.ignore_dirs || []
    svc.dependenciesFile = api.dependencies_file || ''
    svc.crawlEnabled = api.crawl_enabled !== false
    services = [svc]
  }

  const result: RepositoryConfig = {
    id: api.id,
    projectId,
    name: api.name,
    localPath: api.path,
    services,
    alsoRunCrawlers: services[0]?.crawlEnabled ?? true,
    katana: {
      headless: api.katana_headless,
      crawlDepth: api.katana_depth,
    },
  }
  if (api.auth_configured) result.authConfigured = true
  if (api.auth_type) result.authType = api.auth_type
  if (api.auth_headers_meta) {
    result.authHeadersMeta = api.auth_headers_meta.map(h => ({
      header: h.header,
      value: h.value,
      valueEnv: h.value_env,
    }))
  }
  if (api.auth_login_url) result.authLoginUrl = api.auth_login_url
  if (api.endpoint_file) result.endpointFile = api.endpoint_file
  if (api.garak_config_file) {
    result.garakConfigFile = api.garak_config_file
  }
  return result
}

function serviceToWire(svc: ServiceConfig): Record<string, unknown> {
  return {
    name: svc.name,
    relative_path: svc.relativePath,
    type: svc.type,
    languages: svc.languages,
    docker_path: svc.docker?.mountPoint ?? '',
    container_name: svc.docker?.containerName ?? '',
    base_urls: svc.baseUrls,
    test_dirs: svc.testDirectories,
    ignore_dirs: svc.ignoreDirectories,
    dependencies_file: svc.dependenciesFile,
    crawl_enabled: svc.crawlEnabled,
    katana_headless: svc.katanaHeadless,
    katana_depth: svc.katanaCrawlDepth,
  }
}

function toRepositoryPayload(repo: RepositoryConfig): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    name: repo.name,
    path: repo.localPath,
    services: repo.services.map(serviceToWire),
    katana_headless: repo.katana.headless,
    katana_depth: repo.katana.crawlDepth,
  }
  if (repo.auth?.loginUrl) {
    payload.auth = {
      login_url: repo.auth.loginUrl,
      username: repo.auth.inlineUsername || '',
      password: repo.auth.inlinePassword || '',
    }
  }
  return payload
}

function mapToolCatalog(api: ToolCatalogItemApi): ToolCatalogEntry {
  return {
    id: api.id,
    name: api.name,
    supportsLocal: api.supports_local,
    supportsDocker: api.supports_docker,
    requiresBaseUrls: api.requires_base_urls,
    requiresUrlInventory: api.requires_url_inventory,
  }
}

function mapToolOverride(api: ToolOverrideItemApi): ToolOverrideConfig {
  const out: ToolOverrideConfig = {
    toolId: api.toolName,
    argsMode: api.argsMode,
    type: api.type as ToolType,
    location: api.location as ToolLocationMode,
  }
  if (api.path) out.path = api.path
  if (api.container) {
    out.container = { name: api.container.name, toolPath: api.container.toolPath }
  }
  return out
}

function toToolOverrideRequest(o: ToolOverrideConfig): Record<string, unknown> {
  return {
    toolName: o.toolId,
    argsMode: o.argsMode,
    type: o.type,
    location: o.location,
    path: o.path ?? null,
    container: o.container ? { name: o.container.name, toolPath: o.container.toolPath } : null,
  }
}

function toRepoAuthPayload(auth: RepositoryAuthUpdate): Record<string, unknown> {
  const payload: Record<string, unknown> = {}
  if (auth.authType !== undefined) payload.auth_type = auth.authType
  if (auth.loginUrl !== undefined) payload.login_url = auth.loginUrl
  if (auth.usernameField !== undefined) payload.username_field = auth.usernameField
  if (auth.passwordField !== undefined) payload.password_field = auth.passwordField
  if (auth.extraFields !== undefined) payload.extra_fields = auth.extraFields
  if (auth.credentialsEnv !== undefined) payload.credentials_env = auth.credentialsEnv
  if (auth.username !== undefined) payload.username = auth.username
  if (auth.password !== undefined) payload.password = auth.password
  if (auth.authHeaders !== undefined) {
    payload.auth_headers = auth.authHeaders.map(h => ({
      header: h.header,
      value: h.value,
      value_env: h.value_env,
    }))
  }
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
      garakConfigFile?: File | null
    }
  >({
    mutationFn: async ({ projectId, repo, isNew, endpointFile, garakConfigFile }) => {
      const formData = new FormData()
      formData.append('payload', JSON.stringify(toRepositoryPayload(repo)))
      if (endpointFile) {
        formData.append('endpoint_file', endpointFile)
      }
      if (garakConfigFile) {
        formData.append('garak_config', garakConfigFile)
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
  const queryClient = useQueryClient()
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
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({
        queryKey: ['repositories', projectId],
      })
    },
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
    gcTime: 30 * 60 * 1000,
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
      const body = toToolOverrideRequest(override)
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
