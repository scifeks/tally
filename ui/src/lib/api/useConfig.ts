/**
 * useConfig Hooks
 * ===============
 * Hooks for the Config page: project info, repositories, and tool overrides.
 *
 * TODO [BACKEND]: Replace mock data with actual API calls.
 * See REST_ENDPOINTS in config.ts for endpoint paths.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { ProjectInfo, RepositoryConfig, ToolOverrideConfig, ToolCatalogEntry } from '../types'

// ─── Mock Data ────────────────────────────────────────────────────────────────
// TODO [BACKEND]: Remove these mocks once API is connected.

const mockProjectInfo: Record<string, ProjectInfo> = {
  '1': {
    id: '1',
    name: 'acme-platform',
    code: 'ACM',
    company: 'ACME Corporation',
    department: 'Security',
    abbreviation: 'acme',
    createdAt: '2024-01-15T10:30:00Z',
    path: '/opt/tally/projects/acme-platform',
    repoCount: 14,
    findingCount: 220,
  },
  '2': {
    id: '2',
    name: 'atlas-api',
    code: 'ATL',
    company: 'Atlas Inc',
    department: 'Engineering',
    abbreviation: 'atlas',
    createdAt: '2024-02-20T14:00:00Z',
    path: '/opt/tally/projects/atlas-api',
    repoCount: 4,
    findingCount: 35,
  },
  '3': {
    id: '3',
    name: 'northwind-web',
    code: 'NWD',
    company: 'Northwind',
    department: 'Product',
    abbreviation: 'nwd',
    createdAt: '2024-03-10T09:00:00Z',
    path: '/opt/tally/projects/northwind-web',
    repoCount: 0,
    findingCount: 0,
  },
}

const mockRepositories: Record<string, RepositoryConfig[]> = {
  '1': [
    {
      id: 'r-01',
      projectId: '1',
      name: 'dvwa',
      types: ['api', 'ui'],
      locationMode: 'local',
      localPath: '/opt/repos/dvwa',
      languages: ['php', 'javascript'],
      testDirectories: ['tests', 'spec'],
      ignoreDirectories: ['vendor', 'node_modules'],
      baseUrls: ['http://localhost:8080'],
      alsoRunCrawlers: true,
      katana: { headless: false, crawlDepth: 10 },
    },
    {
      id: 'r-02',
      projectId: '1',
      name: 'dvpwa',
      types: ['api'],
      locationMode: 'docker',
      localPath: '/opt/repos/dvpwa',
      docker: { containerName: 'dvpwa-container', mountPoint: '/app' },
      languages: ['python'],
      testDirectories: ['tests'],
      ignoreDirectories: ['__pycache__', '.venv'],
      baseUrls: ['http://localhost:5000'],
      alsoRunCrawlers: true,
      katana: { headless: false, crawlDepth: 8 },
    },
    {
      id: 'r-03',
      projectId: '1',
      name: 'juice-shop',
      types: ['api', 'ui'],
      locationMode: 'local',
      localPath: '/opt/repos/juice-shop',
      languages: ['typescript', 'javascript'],
      testDirectories: ['test', 'e2e'],
      ignoreDirectories: ['node_modules', 'dist'],
      baseUrls: ['http://localhost:3000'],
      alsoRunCrawlers: true,
      katana: { headless: true, crawlDepth: 5 },
      detected: { isSpa: true, languages: ['typescript', 'javascript'], testDirectories: ['test'] },
    },
    {
      id: 'r-04',
      projectId: '1',
      name: 'common-utils',
      types: ['library'],
      locationMode: 'local',
      localPath: '/opt/repos/common-utils',
      languages: ['python'],
      testDirectories: ['tests'],
      ignoreDirectories: ['__pycache__'],
      baseUrls: [],
      alsoRunCrawlers: false,
      katana: { headless: false, crawlDepth: 10 },
    },
    {
      id: 'r-05',
      projectId: '1',
      name: 'php-goof',
      types: ['api'],
      locationMode: 'local',
      localPath: '/opt/repos/php-goof',
      languages: ['php'],
      testDirectories: [],
      ignoreDirectories: ['vendor'],
      baseUrls: ['http://localhost:8081'],
      endpointFile: '/opt/repos/php-goof/openapi.yaml',
      endpointFileFormat: 'openapi3',
      alsoRunCrawlers: false,
      katana: { headless: false, crawlDepth: 10 },
    },
  ],
  '2': [
    {
      id: 'r-10',
      projectId: '2',
      name: 'atl-api',
      types: ['api'],
      locationMode: 'local',
      localPath: '/opt/repos/atl-api',
      languages: ['go'],
      testDirectories: ['test'],
      ignoreDirectories: ['vendor'],
      baseUrls: ['https://api.atlas.dev'],
      alsoRunCrawlers: true,
      katana: { headless: false, crawlDepth: 10 },
    },
    {
      id: 'r-11',
      projectId: '2',
      name: 'atl-web',
      types: ['ui'],
      locationMode: 'local',
      localPath: '/opt/repos/atl-web',
      languages: ['typescript', 'javascript'],
      testDirectories: ['__tests__', 'e2e'],
      ignoreDirectories: ['node_modules', '.next'],
      baseUrls: ['https://atlas.dev'],
      alsoRunCrawlers: true,
      katana: { headless: true, crawlDepth: 5 },
      detected: { isSpa: true, languages: ['typescript'], testDirectories: ['__tests__'] },
    },
  ],
  '3': [],
}

const mockToolCatalog: ToolCatalogEntry[] = [
  { id: 'semgrep', name: 'Semgrep', supportsLocal: true, supportsDocker: true },
  { id: 'gitleaks', name: 'Gitleaks', supportsLocal: true, supportsDocker: true },
  { id: 'osv-scanner', name: 'OSV Scanner', supportsLocal: true, supportsDocker: true },
  { id: 'npm-audit', name: 'NPM Audit', supportsLocal: true, supportsDocker: true },
  { id: 'composer-audit', name: 'Composer Audit', supportsLocal: true, supportsDocker: true },
  { id: 'pip-audit', name: 'Pip Audit', supportsLocal: true, supportsDocker: true },
  { id: 'zap', name: 'ZAP', supportsLocal: true, supportsDocker: true },
  { id: 'xsstrike', name: 'XSStrike', supportsLocal: true, supportsDocker: true },
  { id: 'dalfox', name: 'Dalfox', supportsLocal: true, supportsDocker: true },
  { id: 'katana', name: 'Katana', supportsLocal: true, supportsDocker: false },
  { id: 'noir', name: 'Noir', supportsLocal: true, supportsDocker: false },
]

const mockToolOverrides: Record<string, ToolOverrideConfig[]> = {
  '1': [
    {
      toolId: 'semgrep',
      type: 'repo',
      location: 'docker',
      container: { name: 'semgrep-runner', toolPath: '/usr/local/bin/semgrep' },
    },
    { toolId: 'gitleaks', type: 'repo', location: 'local', path: '/opt/tools/gitleaks-custom' },
  ],
  '2': [
    {
      toolId: 'zap',
      type: 'api',
      location: 'docker',
      container: { name: 'zap-container', toolPath: '/zap/zap.sh' },
    },
  ],
  '3': [],
}

// ─── Project Info Hook ────────────────────────────────────────────────────────

/**
 * useProjectInfo Hook
 * ===================
 * Fetches project info for the config page.
 *
 * TODO [BACKEND]: Replace mock data with actual API call.
 *
 * Expected API response (GET /api/v1/projects/:id/info):
 * ```json
 * {
 *   "id": "1",
 *   "name": "acme-platform",
 *   "code": "ACM",
 *   "company": "ACME Corporation",
 *   "department": "Security",
 *   "abbreviation": "acme",
 *   "createdAt": "2024-01-15T10:30:00Z",
 *   "path": "/opt/tally/projects/acme-platform",
 *   "repoCount": 14,
 *   "findingCount": 220
 * }
 * ```
 */
export function useProjectInfo(projectId: string) {
  return useQuery({
    queryKey: ['projectInfo', projectId],
    queryFn: async (): Promise<ProjectInfo | null> => {
      // ┌────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Replace mock with fetch()                         │
      // │                                                                    │
      // │ const res = await fetch(REST_ENDPOINTS.projectInfo(projectId))    │
      // │ if (!res.ok) throw new Error("Failed to fetch project info")      │
      // │ return res.json()                                                 │
      // └────────────────────────────────────────────────────────────────────┘

      return mockProjectInfo[projectId] ?? null
    },
    staleTime: 5 * 60 * 1000,
    enabled: Boolean(projectId),
  })
}

/**
 * useUpdateProjectInfo Hook
 * =========================
 * Updates project info.
 *
 * TODO [BACKEND]: Wire up to PATCH /api/v1/projects/:id/info
 */
export function useUpdateProjectInfo() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: { projectId: string; updates: Partial<ProjectInfo> }) => {
      // ┌────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Replace mock with fetch()                         │
      // │                                                                    │
      // │ const res = await fetch(REST_ENDPOINTS.updateProjectInfo(projectId), { │
      // │   method: "PATCH",                                                │
      // │   headers: { "Content-Type": "application/json" },                │
      // │   body: JSON.stringify(updates)                                   │
      // │ })                                                                │
      // │ if (!res.ok) throw new Error("Failed to update project info")     │
      // │ return res.json()                                                 │
      // └────────────────────────────────────────────────────────────────────┘

      // Mock: update in-memory
      const current = mockProjectInfo[data.projectId]
      if (current) {
        Object.assign(current, data.updates)
      }
      return current
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['projectInfo', variables.projectId] })
    },
  })
}

// ─── Repositories Hook ────────────────────────────────────────────────────────

/**
 * useRepositories Hook
 * ====================
 * Fetches all repositories for a project.
 *
 * TODO [BACKEND]: Replace mock data with actual API call.
 *
 * Expected API response (GET /api/v1/projects/:id/repositories):
 * ```json
 * {
 *   "repositories": [
 *     { "id": "r-01", "name": "dvwa", "types": ["api", "ui"], ... }
 *   ]
 * }
 * ```
 */
export function useRepositories(projectId: string) {
  return useQuery({
    queryKey: ['repositories', projectId],
    queryFn: async (): Promise<RepositoryConfig[]> => {
      // ┌────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Replace mock with fetch()                         │
      // │                                                                    │
      // │ const res = await fetch(REST_ENDPOINTS.repositories(projectId))   │
      // │ if (!res.ok) throw new Error("Failed to fetch repositories")      │
      // │ const data = await res.json()                                     │
      // │ return data.repositories                                          │
      // └────────────────────────────────────────────────────────────────────┘

      return mockRepositories[projectId] ?? []
    },
    staleTime: 5 * 60 * 1000,
    enabled: Boolean(projectId),
    initialData: mockRepositories[projectId] ?? [],
  })
}

/**
 * useSaveRepository Hook
 * ======================
 * Creates or updates a repository.
 *
 * TODO [BACKEND]: Wire up to POST/PUT /api/v1/repositories
 */
export function useSaveRepository() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: { repo: RepositoryConfig; isNew: boolean }) => {
      // ┌────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Replace mock with fetch()                         │
      // │                                                                    │
      // │ const url = isNew                                                 │
      // │   ? REST_ENDPOINTS.createRepository(repo.projectId)               │
      // │   : REST_ENDPOINTS.updateRepository(repo.id)                      │
      // │ const res = await fetch(url, {                                    │
      // │   method: isNew ? "POST" : "PUT",                                 │
      // │   headers: { "Content-Type": "application/json" },                │
      // │   body: JSON.stringify(repo)                                      │
      // │ })                                                                │
      // │ if (!res.ok) throw new Error("Failed to save repository")         │
      // │ return res.json()                                                 │
      // └────────────────────────────────────────────────────────────────────┘

      // Mock: add/update in-memory
      const list = mockRepositories[data.repo.projectId] ?? []
      if (data.isNew) {
        data.repo.id = `r-${Date.now()}`
        list.push(data.repo)
        mockRepositories[data.repo.projectId] = list
      } else {
        const idx = list.findIndex(r => r.id === data.repo.id)
        if (idx >= 0) list[idx] = data.repo
      }
      return data.repo
    },
    onSuccess: repo => {
      queryClient.invalidateQueries({ queryKey: ['repositories', repo.projectId] })
    },
  })
}

/**
 * useDeleteRepository Hook
 * ========================
 * Deletes a repository.
 *
 * TODO [BACKEND]: Wire up to DELETE /api/v1/repositories/:id
 */
export function useDeleteRepository() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: { repoId: string; projectId: string }) => {
      // ┌────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Replace mock with fetch()                         │
      // │                                                                    │
      // │ const res = await fetch(REST_ENDPOINTS.deleteRepository(repoId), {│
      // │   method: "DELETE"                                                │
      // │ })                                                                │
      // │ if (!res.ok) throw new Error("Failed to delete repository")       │
      // └────────────────────────────────────────────────────────────────────┘

      // Mock: remove from in-memory list
      const list = mockRepositories[data.projectId] ?? []
      const idx = list.findIndex(r => r.id === data.repoId)
      if (idx >= 0) list.splice(idx, 1)
      return { success: true }
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['repositories', variables.projectId] })
    },
  })
}

// ─── Tool Overrides Hook ──────────────────────────────────────────────────────

/**
 * useToolCatalog Hook
 * ===================
 * Fetches the catalog of available tools that can be overridden.
 *
 * TODO [BACKEND]: Replace mock data with actual API call.
 *
 * Expected API response (GET /api/v1/tools/catalog):
 * ```json
 * {
 *   "tools": [
 *     { "id": "semgrep", "name": "Semgrep", "supportsLocal": true, "supportsDocker": true }
 *   ]
 * }
 * ```
 */
export function useToolCatalog() {
  return useQuery({
    queryKey: ['toolCatalog'],
    queryFn: async (): Promise<ToolCatalogEntry[]> => {
      // ┌────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Replace mock with fetch()                         │
      // │                                                                    │
      // │ const res = await fetch(REST_ENDPOINTS.toolCatalog)               │
      // │ if (!res.ok) throw new Error("Failed to fetch tool catalog")      │
      // │ const data = await res.json()                                     │
      // │ return data.tools                                                 │
      // └────────────────────────────────────────────────────────────────────┘

      return mockToolCatalog
    },
    staleTime: 30 * 60 * 1000, // Tools don't change often
    initialData: mockToolCatalog,
  })
}

/**
 * useToolOverrides Hook
 * =====================
 * Fetches tool overrides for a project.
 *
 * TODO [BACKEND]: Replace mock data with actual API call.
 *
 * Expected API response (GET /api/v1/projects/:id/tools/overrides):
 * ```json
 * {
 *   "overrides": [
 *     { "toolId": "semgrep", "type": "repo", "location": "docker", "container": { ... } }
 *   ]
 * }
 * ```
 */
export function useToolOverrides(projectId: string) {
  return useQuery({
    queryKey: ['toolOverrides', projectId],
    queryFn: async (): Promise<ToolOverrideConfig[]> => {
      // ┌────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Replace mock with fetch()                         │
      // │                                                                    │
      // │ const res = await fetch(REST_ENDPOINTS.toolOverrides(projectId))  │
      // │ if (!res.ok) throw new Error("Failed to fetch tool overrides")    │
      // │ const data = await res.json()                                     │
      // │ return data.overrides                                             │
      // └────────────────────────────────────────────────────────────────────┘

      return mockToolOverrides[projectId] ?? []
    },
    staleTime: 5 * 60 * 1000,
    enabled: Boolean(projectId),
    initialData: mockToolOverrides[projectId] ?? [],
  })
}

/**
 * useSaveToolOverride Hook
 * ========================
 * Creates or updates a tool override.
 *
 * TODO [BACKEND]: Wire up to POST/PUT /api/v1/projects/:id/tools/overrides
 */
export function useSaveToolOverride() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: {
      projectId: string
      override: ToolOverrideConfig
      isNew: boolean
    }) => {
      // ┌────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Replace mock with fetch()                         │
      // │                                                                    │
      // │ const url = isNew                                                 │
      // │   ? REST_ENDPOINTS.createToolOverride(projectId)                  │
      // │   : REST_ENDPOINTS.updateToolOverride(projectId, override.toolId) │
      // │ const res = await fetch(url, {                                    │
      // │   method: isNew ? "POST" : "PUT",                                 │
      // │   headers: { "Content-Type": "application/json" },                │
      // │   body: JSON.stringify(override)                                  │
      // │ })                                                                │
      // │ if (!res.ok) throw new Error("Failed to save tool override")      │
      // │ return res.json()                                                 │
      // └────────────────────────────────────────────────────────────────────┘

      // Mock: add/update in-memory
      const list = mockToolOverrides[data.projectId] ?? []
      if (data.isNew) {
        list.push(data.override)
        mockToolOverrides[data.projectId] = list
      } else {
        const idx = list.findIndex(o => o.toolId === data.override.toolId)
        if (idx >= 0) list[idx] = data.override
      }
      return data.override
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['toolOverrides', variables.projectId] })
    },
  })
}

/**
 * useDeleteToolOverride Hook
 * ==========================
 * Deletes a tool override (reverts to global config).
 *
 * TODO [BACKEND]: Wire up to DELETE /api/v1/projects/:id/tools/overrides/:toolId
 */
export function useDeleteToolOverride() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: { projectId: string; toolId: string }) => {
      // ┌────────────────────────────────────────────────────────────────────┐
      // │ TODO [BACKEND]: Replace mock with fetch()                         │
      // │                                                                    │
      // │ const res = await fetch(                                          │
      // │   REST_ENDPOINTS.deleteToolOverride(projectId, toolId),           │
      // │   { method: "DELETE" }                                            │
      // │ )                                                                 │
      // │ if (!res.ok) throw new Error("Failed to delete tool override")    │
      // └────────────────────────────────────────────────────────────────────┘

      // Mock: remove from in-memory list
      const list = mockToolOverrides[data.projectId] ?? []
      const idx = list.findIndex(o => o.toolId === data.toolId)
      if (idx >= 0) list.splice(idx, 1)
      return { success: true }
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['toolOverrides', variables.projectId] })
    },
  })
}
