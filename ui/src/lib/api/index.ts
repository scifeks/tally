/**
 * API Module
 * ==========
 * Barrel export for all data fetching hooks. Each hook calls the
 * FastAPI backend via `apiFetch` (REST) or `apiEventSource` (SSE).
 *
 * FILE STRUCTURE:
 * ---------------
 * config.ts       - API URLs and endpoint paths
 * useProjects.ts  - Project list and metadata (GET)
 * useFindings.ts  - Findings list and updates (GET, PATCH)
 * useScans.ts     - Scan history, start/cancel, SSE events (GET, POST, SSE)
 * useTriage.ts    - Triage history, start/cancel, SSE events (GET, POST, SSE)
 * useUrlLists.ts  - Project URL list entries (GET)
 * useReports.ts   - Report drafts, generation, history, SSE events (GET, POST, SSE)
 * useChat.ts      - Chat sessions, messages, streaming responses (GET, POST, SSE)
 * useConfig.ts    - Project info, repositories, tool overrides (GET, PATCH, POST, DELETE)
 */

// Configuration
export { API_BASE_URL, SSE_ENDPOINTS, REST_ENDPOINTS } from './config'

// Project hooks
export { useProjects } from './useProjects'
export { useProjectMeta } from './useProjectMeta'

// Finding hooks
export { useFindings, mapFinding } from './useFindings'
export type { FindingFilters, FindingSortKey, UseFindingsOptions } from './useFindings'
export { useUpdateFinding } from './useUpdateFinding'
export type { UpdateFindingPatch } from './useUpdateFinding'
export { useFindingsEvents } from './useFindingsEvents'
export { useFindingsCounts } from './useFindingsCounts'
export { useFindingsFilterOptions } from './useFindingsFilterOptions'
export type {
  FilterOption,
  RepoFilterOption,
  FindingsFilterOptions,
} from './useFindingsFilterOptions'

// Scan hooks
export {
  useScanHistory,
  useRunningScans,
  useRunningScansCount,
  useProjectScanConfig,
  useStartScan,
  useCancelScan,
  useScanEvents,
} from './useScans'

// Triage hooks
export {
  useTriageHistory,
  useActiveTriage,
  useLatestTriage,
  useTriageRun,
  useStartTriage,
  useCancelTriage,
  useResumeTriage,
  useTriageEvents,
  mapTriageRun,
  mapTriageBatch,
} from './useTriage'
export type {
  StartTriageOptions,
  UseTriageEventsOptions,
  UseTriageHistoryOptions,
} from './useTriage'

// Runtime / installed-tools hooks (cross-project)
export { useRuntimeDependencies, useInstalledTools } from './useRuntime'

// URL List hooks
export { useUrlLists, mapUrlEntry } from './useUrlLists'
export type { UseUrlListsOptions, UrlListSortKey, UrlListSortDir } from './useUrlLists'
export { useUrlListsFilterOptions } from './useUrlListsFilterOptions'
export type {
  UrlListFilterOption,
  UrlListPortFilterOption,
  UrlListRepoFilterOption,
  UrlListFilterOptions,
  UrlListServerFilters,
} from './useUrlListsFilterOptions'

// Report hooks
export {
  useReportDrafts,
  useReportHistory,
  useLatestReport,
  useGenerateDraft,
  useUploadDraft,
  useDeleteDraft,
  useGenerateReport,
  useCancelReport,
  useReportEvents,
  useReportDraftEvents,
  downloadDraftSection,
  downloadReportFile,
  mapReportDraft,
  mapReportHistoryEntry,
  mapReportRun,
} from './useReports'
export type {
  GenerateDraftVariables,
  UploadDraftVariables,
  DeleteDraftVariables,
  GenerateReportVariables,
  CancelReportVariables,
  UseReportHistoryOptions,
  UseReportEventsOptions,
  UseReportDraftEventsOptions,
} from './useReports'

// Chat hooks
export {
  useChatSessions,
  useChatMessages,
  useCreateChatSession,
  useSendChatMessage,
  useCancelChatStream,
  useDeleteChatSession,
  useChatStream,
  useInvalidateChatMessages,
  mapChatSession,
  mapChatMessage,
} from './useChat'
export type {
  CreateChatSessionVariables,
  SendChatMessageVariables,
  CancelChatStreamVariables,
  DeleteChatSessionVariables,
  UseChatStreamOptions,
} from './useChat'

// Config hooks
export {
  useProjectInfo,
  useUpdateProjectInfo,
  useRepositories,
  useRepository,
  useSaveRepository,
  useDeleteRepository,
  useUpdateRepoAuth,
  useToolCatalog,
  useToolOverrides,
  useSaveToolOverride,
  useDeleteToolOverride,
} from './useConfig'

// Saved scans (CLIENT-SIDE MOCK — no backend yet)
export { useSavedScans, useSaveScan, useDeleteSavedScan } from './useSavedScans'

// Tool argument profiles (CLIENT-SIDE MOCK — no backend yet)
export {
  useToolArgProfile,
  useToolArgProfileList,
  useSaveToolArgProfile,
  useDeleteToolArgProfile,
} from './useToolArgProfiles'
export type { ToolArgProfile } from './useToolArgProfiles'
