import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import projectsFixture from '../fixtures/projects.json'
import runtimeDepsClaudeInstalledFixture from '../fixtures/runtime-dependencies-claude-installed.json'

export const handlers = [
  http.get('/api/v1/projects', () => HttpResponse.json(projectsFixture)),
  http.get('/api/v1/runtime-dependencies', () =>
    HttpResponse.json(runtimeDepsClaudeInstalledFixture)
  ),
]

export const server = setupServer(...handlers)
