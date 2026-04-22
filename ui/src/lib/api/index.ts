/**
 * API Module
 * ==========
 * Central export for all data fetching hooks.
 *
 * BACKEND INTEGRATION GUIDE
 * =========================
 *
 * This module provides a clean abstraction layer between the UI and the backend.
 * Currently all hooks return mock data. To connect to a real FastAPI backend:
 *
 * 1. Update API_BASE_URL in config.ts to point to your server.
 *
 * 2. For each hook, find the TODO [BACKEND] block and:
 *    - Uncomment the fetch() or EventSource code
 *    - Remove the mock data import and usage
 *    - The expected request/response format is documented above each hook
 *
 * 3. For SSE endpoints (scan events, triage events):
 *    - Implement SSE handlers in FastAPI that emit events matching the documented format
 *    - Uncomment the EventSource connection code in the hook
 *    - The mock event simulation in pages can be removed once real SSE is connected
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
 *
 * SEARCH FOR SWAP POINTS:
 * -----------------------
 * grep -r "TODO \[BACKEND\]" src/lib/api/
 *
 * This will show every location where mock data needs to be replaced with
 * real API calls.
 */

// Configuration
export { API_BASE_URL, SSE_ENDPOINTS, REST_ENDPOINTS } from './config'

// Project hooks
export { useProjects, useProjectMeta } from './useProjects'

// Finding hooks
export { useFindings, useUpdateFinding } from './useFindings'

// Scan hooks
export {
  useScanHistory,
  useRunningScans,
  useProjectScanConfig,
  useStartScan,
  useCancelScan,
  useScanEvents,
} from './useScans'

// Triage hooks
export { useTriageHistory, useStartTriage, useCancelTriage, useTriageEvents } from './useTriage'

// URL List hooks
export { useUrlLists } from './useUrlLists'

// Report hooks
export {
  useReportDrafts,
  useGenerateDraft,
  useReportHistory,
  useGenerateReport,
  useReportEvents,
} from './useReports'

// Chat hooks
export {
  useChatSessions,
  useChatMessages,
  useCreateSession,
  useSendMessage,
  useDeleteSession,
} from './useChat'

// Config hooks
export {
  useProjectInfo,
  useUpdateProjectInfo,
  useRepositories,
  useSaveRepository,
  useDeleteRepository,
  useToolCatalog,
  useToolOverrides,
  useSaveToolOverride,
  useDeleteToolOverride,
} from './useConfig'
