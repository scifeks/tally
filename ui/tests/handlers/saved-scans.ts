import { http, HttpResponse } from 'msw'
import { errorEnvelope } from './_helpers'
import savedScansEmpty from '../fixtures/saved-scans/empty.json'
import savedScansPopulated from '../fixtures/saved-scans/populated.json'
import savedScanClean from '../fixtures/saved-scans/clean.json'
import savedScanHydrated from '../fixtures/saved-scans/hydrated.json'
import savedScanReplaced from '../fixtures/saved-scans/replaced.json'
import savedScanDetailWithDeletedRepo from '../fixtures/saved-scans/detail-with-deleted-repo.json'
import savedScanRun202 from '../fixtures/saved-scans/run-202.json'

const SAVED_SCAN_NOT_FOUND_ID = '9999'
const SAVED_SCAN_STALE_ID = '7'
const SAVED_SCAN_BUSY_ID = '8'
const SAVED_SCAN_UNIQUE_CONFLICT_NAME = 'Quick Secrets Sweep'

const DETAIL_BY_ID: Record<string, unknown> = {
  '1': savedScanClean,
  '2': savedScanDetailWithDeletedRepo,
}

export const savedScansHandlers = [
  http.get('/api/v1/projects/:projectId/saved-scans', () => {
    const totalRaw = (savedScansPopulated as { total?: number }).total
    if (typeof totalRaw === 'number' && totalRaw === 0) {
      return HttpResponse.json(savedScansEmpty)
    }
    return HttpResponse.json(savedScansPopulated)
  }),
  http.get('/api/v1/projects/:projectId/saved-scans/:savedScanId', ({ params }) => {
    if (params.savedScanId === SAVED_SCAN_NOT_FOUND_ID) {
      return errorEnvelope(404, 'NOT_FOUND', `Saved scan id=${params.savedScanId} not found`)
    }
    const detail = DETAIL_BY_ID[params.savedScanId as string]
    if (!detail) {
      return errorEnvelope(404, 'NOT_FOUND', `Saved scan id=${params.savedScanId} not found`)
    }
    return HttpResponse.json(detail)
  }),
  http.post('/api/v1/projects/:projectId/saved-scans', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as {
      name?: string
      toolNames?: string[]
      argProfileIds?: number[]
    }
    if (!body.name) {
      return errorEnvelope(422, 'VALIDATION_ERROR', 'Request validation failed', {
        fields: [
          {
            field: 'body.name',
            type: 'string_too_short',
            message: 'String should have at least 1 character',
          },
        ],
      })
    }
    const tools = body.toolNames ?? []
    const profiles = body.argProfileIds ?? []
    if (tools.length === 0 && profiles.length === 0) {
      return errorEnvelope(422, 'VALIDATION_ERROR', 'Saved scan validation failed', {
        fields: [
          {
            field: 'toolNames',
            issue: 'at least one of toolNames or argProfileIds must be non-empty',
          },
        ],
      })
    }
    if (body.name === SAVED_SCAN_UNIQUE_CONFLICT_NAME) {
      return errorEnvelope(409, 'CONFLICT', `saved scan '${body.name}' already exists`)
    }
    return HttpResponse.json(profiles.length > 0 ? savedScanHydrated : savedScanClean, {
      status: 201,
    })
  }),
  http.put('/api/v1/projects/:projectId/saved-scans/:savedScanId', async ({ params }) => {
    if (params.savedScanId === SAVED_SCAN_NOT_FOUND_ID) {
      return errorEnvelope(404, 'NOT_FOUND', `saved_scan id ${params.savedScanId} not found`)
    }
    return HttpResponse.json(savedScanReplaced)
  }),
  http.delete('/api/v1/projects/:projectId/saved-scans/:savedScanId', ({ params }) => {
    if (params.savedScanId === SAVED_SCAN_NOT_FOUND_ID) {
      return errorEnvelope(404, 'NOT_FOUND', `Saved scan id=${params.savedScanId} not found`)
    }
    return new HttpResponse(null, { status: 204 })
  }),
  http.post('/api/v1/projects/:projectId/saved-scans/:savedScanId/run', ({ params }) => {
    if (params.savedScanId === SAVED_SCAN_NOT_FOUND_ID) {
      return errorEnvelope(404, 'NOT_FOUND', `Saved scan id=${params.savedScanId} not found`)
    }
    if (params.savedScanId === SAVED_SCAN_STALE_ID) {
      return errorEnvelope(
        409,
        'STALE_SAVED_SCAN',
        'Saved scan references items that no longer exist',
        {
          staleItems: [
            { kind: 'repo', id: 2, name: 'php-goof' },
            { kind: 'tool', name: 'osv-scanner' },
            { kind: 'argProfile', id: 4 },
          ],
        }
      )
    }
    if (params.savedScanId === SAVED_SCAN_BUSY_ID) {
      return errorEnvelope(
        409,
        'JOB_ALREADY_RUNNING',
        "Job 'scan' is already running: held by run-12",
        { kind: 'scan', current_holder: 'run-12' }
      )
    }
    return HttpResponse.json(savedScanRun202, { status: 202 })
  }),
]
