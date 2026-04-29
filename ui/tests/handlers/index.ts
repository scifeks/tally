import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import projectsFixture from '../fixtures/projects.json'
import runtimeDepsClaudeInstalledFixture from '../fixtures/runtime-dependencies-claude-installed.json'
import findingsCountsPopulatedFixture from '../fixtures/findings-counts-populated.json'
import findingsCountsEmptyFixture from '../fixtures/findings-counts-empty.json'
import projectMetaPopulatedFixture from '../fixtures/project-meta-populated.json'
import projectMetaEmptyFixture from '../fixtures/project-meta-empty.json'
import findingsPopulatedFixture from '../fixtures/findings-populated.json'
import findingsPage2Fixture from '../fixtures/findings-page-2.json'
import findingsEmptyFixture from '../fixtures/findings-empty.json'
import findingUpdatedFixture from '../fixtures/finding-updated.json'
import urlListProject1Fixture from '../fixtures/url-list-project-1.json'
import urlListProject2Fixture from '../fixtures/url-list-project-2.json'
import urlListEmptyFixture from '../fixtures/url-list-empty.json'
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
 * the FE forwards the right server-side filters. Honours offset, limit,
 * severity, status, segment, tool, and search. Sort/order are honoured
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
]

export const server = setupServer(...handlers)
