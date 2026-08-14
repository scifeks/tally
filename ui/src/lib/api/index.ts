// Configuration
export { API_BASE_URL, SSE_ENDPOINTS, REST_ENDPOINTS } from './config'

// Project hooks
export { useProjects } from './useProjects'
export { useProjectMeta } from './useProjectMeta'
export { useCreateProject } from './useCreateProject'
export type { CreateProjectInput } from './useCreateProject'

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
export { useFieldSpecs } from './useFieldSpecs'
export type { FieldSpecs } from './useFieldSpecs'
export { useCreateFinding } from './useCreateFinding'
export type { CreateFindingInput } from './useCreateFinding'
export { useDeleteFinding } from './useDeleteFinding'

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
  fetchTriageMaxBatchId,
  mapTriageRun,
  mapTriageBatch,
} from './useTriage'
export type {
  StartTriageOptions,
  UseTriageEventsOptions,
  UseTriageHistoryOptions,
} from './useTriage'

// Platform hooks (cross-project)
export { useCapabilities } from './useCapabilities'
export type { Capabilities } from './useCapabilities'

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
  useGenerateDrafts,
  useUploadDraft,
  useDeleteDraft,
  useGenerateReport,
  useCancelReport,
  useUpdateReportMetadata,
  useReportEvents,
  useReportDraftEvents,
  downloadDraftSection,
  downloadReportFile,
  mapReportDraft,
  mapReportHistoryEntry,
  mapReportRun,
} from './useReports'
export type {
  GenerateDraftsVariables,
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
  useAppendChatMessageToCache,
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

// Document hooks
export { useDocuments, useUploadDocument, useDeleteDocument } from './useDocuments'
export type { UploadDocumentVariables, DeleteDocumentVariables } from './useDocuments'

// Saved scans
export {
  useSavedScans,
  useSavedScan,
  useSaveScan,
  useDeleteSavedScan,
  useRunSavedScan,
} from './useSavedScans'
export type { SavedScanListResponse, SavedScanWriteInput } from './useSavedScans'

// Tool argument profiles
export {
  useToolArgProfileList,
  useSaveToolArgProfile,
  useDeleteToolArgProfile,
  mapProfilesToTemplates,
  mapTemplateToWriteInput,
  profileMatchesTemplate,
} from './useToolArgProfiles'
export { useDownloadFileArg } from './useDownloadFileArg'
export type {
  ToolArgProfile,
  ToolArgProfileListResponse,
  ToolArgProfileWriteInput,
  ArgProfileArg,
} from './useToolArgProfiles'

// Global settings hooks
export { useBrowseFilesystem } from './useGlobalSettings'
