import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import projectsFixture from '../fixtures/projects.json'
import runtimeDepsClaudeInstalledFixture from '../fixtures/runtime-dependencies-claude-installed.json'
import findingsCountsPopulatedFixture from '../fixtures/findings-counts-populated.json'
import findingsCountsEmptyFixture from '../fixtures/findings-counts-empty.json'
import findingsFilterOptionsPopulatedFixture from '../fixtures/findings-filter-options-populated.json'
import findingsFilterOptionsEmptyFixture from '../fixtures/findings-filter-options-empty.json'
import projectMetaPopulatedFixture from '../fixtures/project-meta-populated.json'
import projectMetaEmptyFixture from '../fixtures/project-meta-empty.json'
import findingsPopulatedFixture from '../fixtures/findings-populated.json'
import findingsPage2Fixture from '../fixtures/findings-page-2.json'
import findingsEmptyFixture from '../fixtures/findings-empty.json'
import findingUpdatedFixture from '../fixtures/finding-updated.json'
import urlListProject1Fixture from '../fixtures/url-list-project-1.json'
import urlListProject2Fixture from '../fixtures/url-list-project-2.json'
import urlListEmptyFixture from '../fixtures/url-list-empty.json'
import urlListFilterOptionsPopulatedFixture from '../fixtures/url-list-filter-options-populated.json'
import urlListFilterOptionsEmptyFixture from '../fixtures/url-list-filter-options-empty.json'
import scanConfigProject1Fixture from '../fixtures/scan-config-project-1.json'
import scanConfigProject2Fixture from '../fixtures/scan-config-project-2.json'
import scanConfigEmptyFixture from '../fixtures/scan-config-empty.json'
import scanHistoryProject1Fixture from '../fixtures/scan-history-project-1.json'
import scanHistoryProject2Fixture from '../fixtures/scan-history-project-2.json'
import scanHistoryEmptyFixture from '../fixtures/scan-history-empty.json'
import triageHistoryProject1Fixture from '../fixtures/triage-history-project-1.json'
import triageHistoryProject2Fixture from '../fixtures/triage-history-project-2.json'
import triageHistoryEmptyFixture from '../fixtures/triage-history-empty.json'
import triageActiveRunningFixture from '../fixtures/triage-active-running.json'
import triageLatestCompletedFixture from '../fixtures/triage-latest-completed.json'
import triageDetailProject1Fixture from '../fixtures/triage-detail-project-1.json'
import triageStart202Fixture from '../fixtures/triage-start-202.json'
import triageCancel202Fixture from '../fixtures/triage-cancel-202.json'
import triageResume202Fixture from '../fixtures/triage-resume-202.json'
import reportDraftsProject1Fixture from '../fixtures/report-drafts-project-1.json'
import reportDraftsProject2Fixture from '../fixtures/report-drafts-project-2.json'
import reportDraftsEmptyFixture from '../fixtures/report-drafts-empty.json'
import reportHistoryProject1Fixture from '../fixtures/report-history-project-1.json'
import reportHistoryEmptyFixture from '../fixtures/report-history-empty.json'
import reportLatestProject1Fixture from '../fixtures/report-latest-project-1.json'
import reportGenerate202Fixture from '../fixtures/report-generate-202.json'
import reportDraftStart202Fixture from '../fixtures/report-draft-start-202.json'
import reportCancel202Fixture from '../fixtures/report-cancel-202.json'
import reportDraftUpload200Fixture from '../fixtures/report-draft-upload-200.json'
import chatSessionsProject1Fixture from '../fixtures/chat-sessions-project-1.json'
import chatSessionsProject2Fixture from '../fixtures/chat-sessions-project-2.json'
import chatSessionsEmptyFixture from '../fixtures/chat-sessions-empty.json'
import chatMessagesSession101Fixture from '../fixtures/chat-messages-session-101.json'
import chatMessagesEmptyFixture from '../fixtures/chat-messages-empty.json'
import chatCreateSession201Fixture from '../fixtures/chat-create-session-201.json'
import chatSendMessage202Fixture from '../fixtures/chat-send-message-202.json'
import chatCancel202Fixture from '../fixtures/chat-cancel-202.json'
import configProjectInfo1Fixture from '../fixtures/config-project-info-1.json'
import configProjectInfo2Fixture from '../fixtures/config-project-info-2.json'
import configProjectInfo3Fixture from '../fixtures/config-project-info-3.json'
import configRepositoriesProject1Fixture from '../fixtures/config-repositories-project-1.json'
import configRepositoriesProject2Fixture from '../fixtures/config-repositories-project-2.json'
import configRepositoriesEmptyFixture from '../fixtures/config-repositories-empty.json'
import configToolCatalogFixture from '../fixtures/config-tool-catalog.json'
import configToolOverridesProject1Fixture from '../fixtures/config-tool-overrides-project-1.json'
import configToolOverridesProject2Fixture from '../fixtures/config-tool-overrides-project-2.json'
import configToolOverridesEmptyFixture from '../fixtures/config-tool-overrides-empty.json'
const reportDraftDownloadMarkdown = `# Executive Summary

This is a sample reviewed draft section served as \`text/markdown\`.
`

interface UrlListPage {
  items: Array<Record<string, unknown> & { id: number }>
  total: number
  offset: number
  limit: number
}

const URL_LIST_FIXTURES: Record<string, UrlListPage> = {
  '1': urlListProject1Fixture as UrlListPage,
  '2': urlListProject2Fixture as UrlListPage,
  '3': urlListEmptyFixture as UrlListPage,
}

const SCAN_CONFIG_FIXTURES: Record<string, unknown> = {
  '1': scanConfigProject1Fixture,
  '2': scanConfigProject2Fixture,
  '3': scanConfigEmptyFixture,
}

interface ScanHistoryPage {
  items: Array<Record<string, unknown> & { id: number; status: string | null }>
  total: number
  offset: number
  limit: number
}

const SCAN_HISTORY_FIXTURES: Record<string, ScanHistoryPage> = {
  '1': scanHistoryProject1Fixture as ScanHistoryPage,
  '2': scanHistoryProject2Fixture as ScanHistoryPage,
  '3': scanHistoryEmptyFixture as ScanHistoryPage,
}

interface TriageHistoryPage {
  items: Array<Record<string, unknown> & { scan_run_id: number; status: string }>
  total: number
  offset: number
  limit: number
}

const TRIAGE_HISTORY_FIXTURES: Record<string, TriageHistoryPage> = {
  '1': triageHistoryProject1Fixture as TriageHistoryPage,
  '2': triageHistoryProject2Fixture as TriageHistoryPage,
  '3': triageHistoryEmptyFixture as TriageHistoryPage,
}

interface ReportDraftsFixture {
  drafts: Array<Record<string, unknown> & { section: string; status: string }>
}

const REPORT_DRAFTS_FIXTURES: Record<string, ReportDraftsFixture> = {
  '1': reportDraftsProject1Fixture as ReportDraftsFixture,
  '2': reportDraftsProject2Fixture as ReportDraftsFixture,
  '3': reportDraftsEmptyFixture as ReportDraftsFixture,
}

interface ReportHistoryPage {
  items: Array<Record<string, unknown> & { id: number }>
  total: number
  offset: number
  limit: number
}

const REPORT_HISTORY_FIXTURES: Record<string, ReportHistoryPage> = {
  '1': reportHistoryProject1Fixture as ReportHistoryPage,
  '2': reportHistoryEmptyFixture as ReportHistoryPage,
  '3': reportHistoryEmptyFixture as ReportHistoryPage,
}

/**
 * Test trigger ids:
 *   projectId 99  → POST /triage returns 409 JOB_ALREADY_RUNNING
 *   projectId 98  → POST /triage returns 404 NOT_FOUND (no scans)
 *   scanRunId 999 → POST /cancel returns 409 TRIAGE_NOT_CANCELLABLE
 *   scanRunId 998 → POST /resume returns 409 TRIAGE_NOT_RESUMABLE
 *   scanRunId 997 → GET /triage/:scanRunId returns 404 NOT_FOUND
 */
const PROJECT_TRIAGE_CONFLICT = '99'
const PROJECT_TRIAGE_NOT_FOUND = '98'
const SCAN_RUN_NOT_CANCELLABLE = '999'
const SCAN_RUN_NOT_RESUMABLE = '998'
const SCAN_RUN_DETAIL_NOT_FOUND = '997'

/**
 * Reports test trigger ids (separate namespace from triage above):
 *   projectId 99   → POST /reports/generate or /reports/drafts → 409 JOB_ALREADY_RUNNING
 *   projectId 98   → POST /reports/generate or /reports/drafts → 404 NOT_FOUND
 *   projectId 3    → GET /reports/latest → 404 (treated as null by hook)
 *   reportId  999  → POST /reports/:id/cancel → 409 REPORT_NOT_CANCELLABLE
 */
const PROJECT_REPORT_CONFLICT = '99'
const PROJECT_REPORT_NOT_FOUND = '98'
const REPORT_NOT_CANCELLABLE = '999'

/**
 * Chat test trigger ids:
 *   sessionId 901 → POST .../messages → 409 CHAT_SESSION_EXPIRED
 *   sessionId 902 → POST .../messages → 409 CHAT_STREAM_ALREADY_RUNNING
 *   sessionId 903 → POST .../messages → 422 VALIDATION_ERROR
 *   sessionId 904 → POST .../cancel   → 409 CHAT_NO_ACTIVE_STREAM
 *   sessionId 905 → GET messages or POST anything → 404 NOT_FOUND
 */
const CHAT_SESSION_EXPIRED_ID = '901'
const CHAT_STREAM_ALREADY_RUNNING_ID = '902'
const CHAT_VALIDATION_ERROR_ID = '903'
const CHAT_NO_ACTIVE_STREAM_ID = '904'
const CHAT_SESSION_NOT_FOUND_ID = '905'

interface ChatSessionsFixture {
  items: Array<Record<string, unknown> & { id: number; project_id: number }>
  total: number
  offset: number
  limit: number
}

const CHAT_SESSIONS_FIXTURES: Record<string, ChatSessionsFixture> = {
  '1': chatSessionsProject1Fixture as ChatSessionsFixture,
  '2': chatSessionsProject2Fixture as ChatSessionsFixture,
  '3': chatSessionsEmptyFixture as ChatSessionsFixture,
}

interface ChatMessagesFixture {
  items: Array<Record<string, unknown> & { id: number; session_id: number }>
  total: number
  offset: number
  limit: number
}

const CHAT_MESSAGES_FIXTURES: Record<string, ChatMessagesFixture> = {
  '101': chatMessagesSession101Fixture as ChatMessagesFixture,
}

interface ProjectInfoFixture {
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

const PROJECT_INFO_FIXTURES: Record<string, ProjectInfoFixture> = {
  '1': configProjectInfo1Fixture as ProjectInfoFixture,
  '2': configProjectInfo2Fixture as ProjectInfoFixture,
  '3': configProjectInfo3Fixture as ProjectInfoFixture,
}

interface RepositoriesPage {
  items: Array<Record<string, unknown> & { id: number }>
  total: number
  offset: number
  limit: number
}

const REPOSITORIES_FIXTURES: Record<string, RepositoriesPage> = {
  '1': configRepositoriesProject1Fixture as RepositoriesPage,
  '2': configRepositoriesProject2Fixture as RepositoriesPage,
  '3': configRepositoriesEmptyFixture as RepositoriesPage,
}

interface ToolOverridesFixture {
  items: Array<Record<string, unknown> & { tool_id: string }>
  total: number
}

const TOOL_OVERRIDES_FIXTURES: Record<string, ToolOverridesFixture> = {
  '1': configToolOverridesProject1Fixture as ToolOverridesFixture,
  '2': configToolOverridesProject2Fixture as ToolOverridesFixture,
  '3': configToolOverridesEmptyFixture as ToolOverridesFixture,
}

/**
 * Config test trigger ids:
 *   projectId 99   → PATCH /info → 422 VALIDATION_ERROR
 *   projectId 98   → GET /info → 404 NOT_FOUND
 *   repoId    999  → DELETE /repositories/:id → 404 NOT_FOUND
 *   toolId    "missing" → PUT/DELETE override → 404 NOT_FOUND
 */
const CONFIG_PROJECT_INFO_VALIDATION = '99'
const CONFIG_PROJECT_INFO_NOT_FOUND = '98'
const CONFIG_REPO_NOT_FOUND = '999'
const CONFIG_TOOL_OVERRIDE_NOT_FOUND = 'missing'

function errorEnvelope(
  status: number,
  code: string,
  message: string,
  details: Record<string, unknown> = {}
) {
  return HttpResponse.json({ error: { code, message, details } }, { status })
}

interface FindingsPage {
  items: Array<Record<string, unknown> & { id: number; severity: string; status: string }>
  total: number
  offset: number
  limit: number
}

/**
 * Slice the populated fixture by query params so tests can assert that
 * the FE forwards the right server-side filters. Honors offset, limit,
 * severity, status, segment, tool, and search. Sort/order are honored
 * only insofar as the response is left in fixture order.
 */
function buildFindingsResponse(url: URL, base: FindingsPage): FindingsPage {
  const offset = Number(url.searchParams.get('offset') ?? 0)
  const limit = Number(url.searchParams.get('limit') ?? 50)
  const severity = url.searchParams.getAll('severity')
  const status = url.searchParams.getAll('status')
  const segment = url.searchParams.getAll('segment')
  const tool = url.searchParams.getAll('tool')
  const search = url.searchParams.get('search')?.toLowerCase()

  let filtered = base.items
  if (severity.length > 0) {
    filtered = filtered.filter(item => severity.includes(item.severity))
  }
  if (status.length > 0) {
    filtered = filtered.filter(item => status.includes(item.status))
  }
  if (segment.length > 0) {
    filtered = filtered.filter(item => segment.includes(item.segment as string))
  }
  if (tool.length > 0) {
    filtered = filtered.filter(item => tool.includes(item.tool as string))
  }
  if (search) {
    filtered = filtered.filter(item => String(item.title).toLowerCase().includes(search))
  }

  const total = filtered.length
  const slice = filtered.slice(offset, offset + limit)
  return { items: slice, total, offset, limit }
}

export const handlers = [
  http.get('/api/v1/projects', () => HttpResponse.json(projectsFixture)),
  http.get('/api/v1/runtime-dependencies', () =>
    HttpResponse.json(runtimeDepsClaudeInstalledFixture)
  ),
  http.get('/api/v1/projects/:projectId/findings/counts', ({ params }) => {
    const fixture =
      params.projectId === '3' ? findingsCountsEmptyFixture : findingsCountsPopulatedFixture
    return HttpResponse.json(fixture)
  }),
  http.get('/api/v1/projects/:projectId/findings/filter-options', ({ params }) => {
    const fixture =
      params.projectId === '3'
        ? findingsFilterOptionsEmptyFixture
        : findingsFilterOptionsPopulatedFixture
    return HttpResponse.json(fixture)
  }),
  http.get('/api/v1/projects/:projectId/meta', ({ params }) => {
    const fixture =
      params.projectId === '3' ? projectMetaEmptyFixture : projectMetaPopulatedFixture
    return HttpResponse.json(fixture)
  }),
  http.get('/api/v1/projects/:projectId/findings', ({ params, request }) => {
    if (params.projectId === '3') {
      return HttpResponse.json(findingsEmptyFixture)
    }
    const url = new URL(request.url)
    const offset = Number(url.searchParams.get('offset') ?? 0)
    // The fixture has 5 items; treat any offset >= 50 as page 2 so
    // infinite-scroll tests get a deterministic second page.
    if (offset >= 50) {
      return HttpResponse.json(findingsPage2Fixture)
    }
    return HttpResponse.json(
      buildFindingsResponse(url, findingsPopulatedFixture as FindingsPage)
    )
  }),
  http.patch('/api/v1/projects/:projectId/findings/:findingId', () => {
    return HttpResponse.json(findingUpdatedFixture)
  }),
  http.get('/api/v1/projects/:projectId/url-list/entries', ({ params, request }) => {
    const fixture = URL_LIST_FIXTURES[params.projectId as string] ?? urlListEmptyFixture
    const url = new URL(request.url)
    const offset = Number(url.searchParams.get('offset') ?? 0)
    const limit = Number(url.searchParams.get('limit') ?? 100)
    const slice = (fixture as UrlListPage).items.slice(offset, offset + limit)
    return HttpResponse.json({ items: slice, total: fixture.total, offset, limit })
  }),
  http.get('/api/v1/projects/:projectId/url-list/filter-options', ({ params }) => {
    const fixture =
      params.projectId === '3'
        ? urlListFilterOptionsEmptyFixture
        : urlListFilterOptionsPopulatedFixture
    return HttpResponse.json(fixture)
  }),
  http.get('/api/v1/projects/:projectId/scans/config', ({ params }) => {
    const fixture = SCAN_CONFIG_FIXTURES[params.projectId as string] ?? scanConfigEmptyFixture
    return HttpResponse.json(fixture)
  }),
  http.get('/api/v1/projects/:projectId/scans', ({ params, request }) => {
    const fixture = SCAN_HISTORY_FIXTURES[params.projectId as string] ?? scanHistoryEmptyFixture
    const url = new URL(request.url)
    const offset = Number(url.searchParams.get('offset') ?? 0)
    const limit = Number(url.searchParams.get('limit') ?? 20)
    const status = url.searchParams.get('status')
    let items = fixture.items
    if (status) {
      items = items.filter(it => it.status === status)
    }
    const total = items.length
    const slice = items.slice(offset, offset + limit)
    return HttpResponse.json({ items: slice, total, offset, limit })
  }),
  http.post('/api/v1/projects/:projectId/scans', async ({ params, request }) => {
    const projectId = Number(params.projectId)
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
    return HttpResponse.json(
      {
        id: 9999,
        project_id: projectId,
        status: 'queued',
        started_at: new Date().toISOString(),
        finished_at: null,
        repo_ids: (body.repoIds as unknown[] | undefined)?.map(String) ?? [],
        tool_ids: (body.toolIds as string[] | undefined) ?? [],
        domains: (body.domains as string[] | undefined) ?? [],
        findings_count: null,
        skip_enrichment: Boolean(body.skipEnrichment ?? false),
      },
      { status: 202 }
    )
  }),
  http.post('/api/v1/projects/:projectId/scans/:runId/cancel', ({ params }) => {
    return HttpResponse.json(
      { id: Number(params.runId), status: 'cancelling' },
      { status: 202 }
    )
  }),

  // ─── Triage ───────────────────────────────────────────────────────────────
  // Literal-segment routes registered BEFORE the parameterized
  // `:scanRunId` route so MSW doesn't bind 'active'/'latest'/'events' to
  // the param.
  http.get('/api/v1/projects/:projectId/triage/active', ({ params }) => {
    if (params.projectId === '1') {
      return HttpResponse.json(triageActiveRunningFixture)
    }
    return HttpResponse.json(null)
  }),
  http.get('/api/v1/projects/:projectId/triage/latest', ({ params }) => {
    if (params.projectId === '3') {
      return errorEnvelope(404, 'NOT_FOUND', 'no triage history for this project')
    }
    return HttpResponse.json(triageLatestCompletedFixture)
  }),
  http.get('/api/v1/projects/:projectId/triage/:scanRunId', ({ params }) => {
    if (params.scanRunId === SCAN_RUN_DETAIL_NOT_FOUND) {
      return errorEnvelope(404, 'NOT_FOUND', 'triage run not found')
    }
    return HttpResponse.json(triageDetailProject1Fixture)
  }),
  http.get('/api/v1/projects/:projectId/triage', ({ params, request }) => {
    const fixture =
      TRIAGE_HISTORY_FIXTURES[params.projectId as string] ?? triageHistoryEmptyFixture
    const url = new URL(request.url)
    const offset = Number(url.searchParams.get('offset') ?? 0)
    const limit = Number(url.searchParams.get('limit') ?? 20)
    const items = fixture.items
    const total = items.length
    const slice = items.slice(offset, offset + limit)
    return HttpResponse.json({ items: slice, total, offset, limit })
  }),
  http.post('/api/v1/projects/:projectId/triage', async ({ params, request }) => {
    if (params.projectId === PROJECT_TRIAGE_CONFLICT) {
      return errorEnvelope(409, 'JOB_ALREADY_RUNNING', 'triage is already running')
    }
    if (params.projectId === PROJECT_TRIAGE_NOT_FOUND) {
      return errorEnvelope(404, 'NOT_FOUND', 'no scan runs for this project')
    }
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
    if (body.acknowledge_injection_risk !== true) {
      return errorEnvelope(
        422,
        'VALIDATION_ERROR',
        'acknowledge_injection_risk must be true to dispatch triage',
        { field: 'acknowledge_injection_risk' }
      )
    }
    return HttpResponse.json(triageStart202Fixture, { status: 202 })
  }),
  http.post('/api/v1/projects/:projectId/triage/:scanRunId/cancel', ({ params }) => {
    if (params.scanRunId === SCAN_RUN_NOT_CANCELLABLE) {
      return errorEnvelope(
        409,
        'TRIAGE_NOT_CANCELLABLE',
        'triage run is no longer cancellable'
      )
    }
    return HttpResponse.json(triageCancel202Fixture, { status: 202 })
  }),
  http.post(
    '/api/v1/projects/:projectId/triage/:scanRunId/resume',
    async ({ params, request }) => {
      if (params.scanRunId === SCAN_RUN_NOT_RESUMABLE) {
        return errorEnvelope(
          409,
          'TRIAGE_NOT_RESUMABLE',
          'triage run is not in a resumable state'
        )
      }
      const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
      if (body.acknowledge_injection_risk !== true) {
        return errorEnvelope(
          422,
          'VALIDATION_ERROR',
          'acknowledge_injection_risk must be true to resume triage',
          { field: 'acknowledge_injection_risk' }
        )
      }
      return HttpResponse.json(triageResume202Fixture, { status: 202 })
    }
  ),

  // ─── Reports ──────────────────────────────────────────────────────────────
  // Literal-segment routes registered BEFORE the parameterized
  // `:reportId` route so MSW doesn't bind 'drafts'/'latest'/'generate'/
  // 'events' to the param.
  http.get('/api/v1/projects/:projectId/reports/drafts', ({ params }) => {
    const fixture =
      REPORT_DRAFTS_FIXTURES[params.projectId as string] ?? reportDraftsEmptyFixture
    return HttpResponse.json(fixture)
  }),
  http.post('/api/v1/projects/:projectId/reports/drafts', async ({ params, request }) => {
    if (params.projectId === PROJECT_REPORT_CONFLICT) {
      return errorEnvelope(409, 'JOB_ALREADY_RUNNING', 'a draft generation is already running')
    }
    if (params.projectId === PROJECT_REPORT_NOT_FOUND) {
      return errorEnvelope(404, 'NOT_FOUND', 'project not found')
    }
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
    if (typeof body.section !== 'string') {
      return errorEnvelope(422, 'VALIDATION_ERROR', 'section is required', { field: 'section' })
    }
    return HttpResponse.json(
      { ...reportDraftStart202Fixture, section: body.section },
      { status: 202 }
    )
  }),
  http.get(
    '/api/v1/projects/:projectId/reports/drafts/:section/download',
    ({ params }) => {
      // Return 404 for the failed section in fixture-1 to exercise the
      // not-yet-generated path. All others get the sample markdown body.
      if (params.projectId === '1' && params.section === 'general_recommendations') {
        return errorEnvelope(404, 'NOT_FOUND', 'draft not generated')
      }
      return new HttpResponse(reportDraftDownloadMarkdown, {
        status: 200,
        headers: { 'Content-Type': 'text/markdown' },
      })
    }
  ),
  http.post('/api/v1/projects/:projectId/reports/drafts/upload', async ({ request }) => {
    const form = await request.formData()
    const section = form.get('section')
    if (typeof section !== 'string' || section === '') {
      return errorEnvelope(422, 'VALIDATION_ERROR', 'section is required', { field: 'section' })
    }
    return HttpResponse.json({ ...reportDraftUpload200Fixture, section })
  }),
  http.delete(
    '/api/v1/projects/:projectId/reports/drafts/:section',
    () => new HttpResponse(null, { status: 204 })
  ),
  http.get('/api/v1/projects/:projectId/reports/latest', ({ params }) => {
    if (params.projectId === '3') {
      return errorEnvelope(404, 'NOT_FOUND', 'no reports for this project')
    }
    return HttpResponse.json(reportLatestProject1Fixture)
  }),
  http.post('/api/v1/projects/:projectId/reports/generate', async ({ params, request }) => {
    if (params.projectId === PROJECT_REPORT_CONFLICT) {
      return errorEnvelope(409, 'JOB_ALREADY_RUNNING', 'a report generation is already running')
    }
    if (params.projectId === PROJECT_REPORT_NOT_FOUND) {
      return errorEnvelope(404, 'NOT_FOUND', 'project not found')
    }
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
    if (typeof body.format !== 'string') {
      return errorEnvelope(422, 'VALIDATION_ERROR', 'format is required', { field: 'format' })
    }
    return HttpResponse.json(
      { ...reportGenerate202Fixture, format: body.format },
      { status: 202 }
    )
  }),
  http.get('/api/v1/projects/:projectId/reports', ({ params, request }) => {
    const fixture =
      REPORT_HISTORY_FIXTURES[params.projectId as string] ?? reportHistoryEmptyFixture
    const url = new URL(request.url)
    const offset = Number(url.searchParams.get('offset') ?? 0)
    const limit = Number(url.searchParams.get('limit') ?? 20)
    const items = fixture.items
    const total = items.length
    const slice = items.slice(offset, offset + limit)
    return HttpResponse.json({ items: slice, total, offset, limit })
  }),
  http.post('/api/v1/projects/:projectId/reports/:reportId/cancel', ({ params }) => {
    if (params.reportId === REPORT_NOT_CANCELLABLE) {
      return errorEnvelope(
        409,
        'REPORT_NOT_CANCELLABLE',
        'report run is no longer cancellable'
      )
    }
    return HttpResponse.json(reportCancel202Fixture, { status: 202 })
  }),
  http.get('/api/v1/projects/:projectId/reports/:reportId/download', () => {
    return new HttpResponse(new Uint8Array([0x25, 0x50, 0x44, 0x46]), {
      status: 200,
      headers: { 'Content-Type': 'application/pdf' },
    })
  }),

  // ─── Chat ─────────────────────────────────────────────────────────────────
  http.get('/api/v1/projects/:projectId/chat/sessions', ({ params, request }) => {
    const fixture =
      CHAT_SESSIONS_FIXTURES[params.projectId as string] ?? chatSessionsEmptyFixture
    const url = new URL(request.url)
    const offset = Number(url.searchParams.get('offset') ?? 0)
    const limit = Number(url.searchParams.get('limit') ?? 50)
    const items = fixture.items
    const total = items.length
    const slice = items.slice(offset, offset + limit)
    return HttpResponse.json({ items: slice, total, offset, limit })
  }),
  http.post('/api/v1/projects/:projectId/chat/sessions', () => {
    return HttpResponse.json(chatCreateSession201Fixture, { status: 201 })
  }),
  http.delete(
    '/api/v1/projects/:projectId/chat/sessions/:sessionId',
    ({ params }) => {
      if (params.sessionId === CHAT_SESSION_NOT_FOUND_ID) {
        return errorEnvelope(404, 'NOT_FOUND', 'session not found')
      }
      return new HttpResponse(null, { status: 204 })
    }
  ),
  http.get(
    '/api/v1/projects/:projectId/chat/sessions/:sessionId/messages',
    ({ params, request }) => {
      if (params.sessionId === CHAT_SESSION_NOT_FOUND_ID) {
        return errorEnvelope(404, 'NOT_FOUND', 'session not found')
      }
      const fixture =
        CHAT_MESSAGES_FIXTURES[params.sessionId as string] ?? chatMessagesEmptyFixture
      const url = new URL(request.url)
      const offset = Number(url.searchParams.get('offset') ?? 0)
      const limit = Number(url.searchParams.get('limit') ?? 50)
      const items = fixture.items
      const total = items.length
      const slice = items.slice(offset, offset + limit)
      return HttpResponse.json({ items: slice, total, offset, limit })
    }
  ),
  http.post(
    '/api/v1/projects/:projectId/chat/sessions/:sessionId/messages',
    async ({ params, request }) => {
      if (params.sessionId === CHAT_SESSION_EXPIRED_ID) {
        return errorEnvelope(
          409,
          'CHAT_SESSION_EXPIRED',
          'this chat session has been sealed',
          { expired_at: '2026-04-26T11:45:00+00:00' }
        )
      }
      if (params.sessionId === CHAT_STREAM_ALREADY_RUNNING_ID) {
        return errorEnvelope(
          409,
          'CHAT_STREAM_ALREADY_RUNNING',
          'a stream is already running for this session',
          { session_id: Number(params.sessionId) }
        )
      }
      if (params.sessionId === CHAT_SESSION_NOT_FOUND_ID) {
        return errorEnvelope(404, 'NOT_FOUND', 'session not found')
      }
      const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
      if (params.sessionId === CHAT_VALIDATION_ERROR_ID || typeof body.content !== 'string') {
        return errorEnvelope(422, 'VALIDATION_ERROR', 'content is required', {
          field: 'content',
        })
      }
      return HttpResponse.json(chatSendMessage202Fixture, { status: 202 })
    }
  ),
  http.post(
    '/api/v1/projects/:projectId/chat/sessions/:sessionId/cancel',
    ({ params }) => {
      if (params.sessionId === CHAT_NO_ACTIVE_STREAM_ID) {
        return errorEnvelope(
          409,
          'CHAT_NO_ACTIVE_STREAM',
          'no in-flight stream to cancel',
          { session_id: Number(params.sessionId) }
        )
      }
      if (params.sessionId === CHAT_SESSION_NOT_FOUND_ID) {
        return errorEnvelope(404, 'NOT_FOUND', 'session not found')
      }
      return HttpResponse.json(chatCancel202Fixture, { status: 202 })
    }
  ),

  // ─── Config ───────────────────────────────────────────────────────────────
  http.get('/api/v1/projects/:projectId/info', ({ params }) => {
    if (params.projectId === CONFIG_PROJECT_INFO_NOT_FOUND) {
      return errorEnvelope(404, 'NOT_FOUND', 'project not found')
    }
    const fixture = PROJECT_INFO_FIXTURES[params.projectId as string]
    if (!fixture) {
      return errorEnvelope(404, 'NOT_FOUND', 'project not found')
    }
    return HttpResponse.json(fixture)
  }),
  http.patch('/api/v1/projects/:projectId/info', async ({ params, request }) => {
    if (params.projectId === CONFIG_PROJECT_INFO_VALIDATION) {
      return errorEnvelope(
        422,
        'VALIDATION_ERROR',
        'abbreviation must be at most 3 characters',
        { field: 'abbreviation' }
      )
    }
    const fixture = PROJECT_INFO_FIXTURES[params.projectId as string]
    if (!fixture) {
      return errorEnvelope(404, 'NOT_FOUND', 'project not found')
    }
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
    if (typeof body.abbreviation === 'string' && body.abbreviation.length > 3) {
      return errorEnvelope(
        422,
        'VALIDATION_ERROR',
        'abbreviation must be at most 3 characters',
        { field: 'abbreviation' }
      )
    }
    return HttpResponse.json({
      ...fixture,
      company_name:
        typeof body.company_name === 'string' ? body.company_name : fixture.company_name,
      department_name:
        typeof body.department_name === 'string'
          ? body.department_name
          : fixture.department_name,
      abbreviation:
        typeof body.abbreviation === 'string' ? body.abbreviation : fixture.abbreviation,
    })
  }),

  http.get('/api/v1/projects/:projectId/repositories', ({ params, request }) => {
    const fixture =
      REPOSITORIES_FIXTURES[params.projectId as string] ??
      (configRepositoriesEmptyFixture as RepositoriesPage)
    const url = new URL(request.url)
    const offset = Number(url.searchParams.get('offset') ?? 0)
    const limit = Number(url.searchParams.get('limit') ?? 500)
    const slice = fixture.items.slice(offset, offset + limit)
    return HttpResponse.json({ items: slice, total: fixture.total, offset, limit })
  }),
  http.post('/api/v1/projects/:projectId/repositories', async ({ request }) => {
    const form = await request.formData()
    const payloadRaw = form.get('payload')
    if (typeof payloadRaw !== 'string') {
      return errorEnvelope(422, 'VALIDATION_ERROR', 'payload is required', {
        field: 'payload',
      })
    }
    const payload = JSON.parse(payloadRaw) as Record<string, unknown>
    return HttpResponse.json(
      {
        id: 9001,
        name: payload.name ?? '',
        type: payload.type ?? [],
        path: payload.path ?? '',
        docker_path: payload.docker_path ?? '',
        container_name: payload.container_name ?? '',
        languages: payload.languages ?? [],
        base_urls: payload.base_urls ?? [],
        test_dirs: payload.test_dirs ?? [],
        ignore_dirs: payload.ignore_dirs ?? [],
        dependencies_file: payload.dependencies_file ?? '',
        crawl_enabled: payload.crawl_enabled ?? false,
        xsstrike_crawl_level: 10,
        xsstrike_headers: {},
        dalfox_headers: {},
        katana_headless: payload.katana_headless ?? false,
        katana_depth: payload.katana_depth ?? 10,
        katana_headers: {},
        endpoint_file: null,
      },
      { status: 201 }
    )
  }),
  http.patch(
    '/api/v1/projects/:projectId/repositories/:repoId/auth',
    () => new HttpResponse(null, { status: 204 })
  ),
  http.get('/api/v1/projects/:projectId/repositories/:repoId', ({ params }) => {
    const fixture = REPOSITORIES_FIXTURES[params.projectId as string]
    if (!fixture) {
      return errorEnvelope(404, 'NOT_FOUND', 'project not found')
    }
    const repoId = Number(params.repoId)
    const repo = fixture.items.find(item => item.id === repoId)
    if (!repo) {
      return errorEnvelope(404, 'NOT_FOUND', 'repository not found')
    }
    return HttpResponse.json(repo)
  }),
  http.patch(
    '/api/v1/projects/:projectId/repositories/:repoId',
    async ({ params, request }) => {
      const fixture = REPOSITORIES_FIXTURES[params.projectId as string]
      if (!fixture) {
        return errorEnvelope(404, 'NOT_FOUND', 'project not found')
      }
      const repoId = Number(params.repoId)
      const repo = fixture.items.find(item => item.id === repoId)
      if (!repo) {
        return errorEnvelope(404, 'NOT_FOUND', 'repository not found')
      }
      const form = await request.formData()
      const payloadRaw = form.get('payload')
      if (typeof payloadRaw !== 'string') {
        return errorEnvelope(422, 'VALIDATION_ERROR', 'payload is required', {
          field: 'payload',
        })
      }
      const payload = JSON.parse(payloadRaw) as Record<string, unknown>
      return HttpResponse.json({ ...repo, ...payload })
    }
  ),
  http.delete('/api/v1/projects/:projectId/repositories/:repoId', ({ params }) => {
    if (params.repoId === CONFIG_REPO_NOT_FOUND) {
      return errorEnvelope(404, 'NOT_FOUND', 'repository not found')
    }
    return new HttpResponse(null, { status: 204 })
  }),

  http.get('/api/v1/tools/catalog', () => HttpResponse.json(configToolCatalogFixture)),
  http.get('/api/v1/projects/:projectId/tools/overrides', ({ params }) => {
    const fixture =
      TOOL_OVERRIDES_FIXTURES[params.projectId as string] ?? configToolOverridesEmptyFixture
    return HttpResponse.json(fixture)
  }),
  http.post('/api/v1/projects/:projectId/tools/overrides', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
    return HttpResponse.json(body, { status: 201 })
  }),
  http.put(
    '/api/v1/projects/:projectId/tools/overrides/:toolId',
    async ({ params, request }) => {
      if (params.toolId === CONFIG_TOOL_OVERRIDE_NOT_FOUND) {
        return errorEnvelope(404, 'NOT_FOUND', 'tool override not found')
      }
      const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
      return HttpResponse.json({ tool_id: params.toolId, ...body })
    }
  ),
  http.delete('/api/v1/projects/:projectId/tools/overrides/:toolId', ({ params }) => {
    if (params.toolId === CONFIG_TOOL_OVERRIDE_NOT_FOUND) {
      return errorEnvelope(404, 'NOT_FOUND', 'tool override not found')
    }
    return new HttpResponse(null, { status: 204 })
  }),
]

export const server = setupServer(...handlers)
