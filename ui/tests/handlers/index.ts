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
]

export const server = setupServer(...handlers)
