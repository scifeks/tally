import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import projectsFixture from '../fixtures/projects.json'
import runtimeDepsClaudeInstalledFixture from '../fixtures/runtime-dependencies-claude-installed.json'
import findingsCountsPopulatedFixture from '../fixtures/findings-counts-populated.json'
import findingsCountsEmptyFixture from '../fixtures/findings-counts-empty.json'
import projectMetaPopulatedFixture from '../fixtures/project-meta-populated.json'
import projectMetaEmptyFixture from '../fixtures/project-meta-empty.json'

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
]

export const server = setupServer(...handlers)
