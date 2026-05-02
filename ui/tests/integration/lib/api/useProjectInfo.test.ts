import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { useProjectInfo, useUpdateProjectInfo } from '@/lib/api/useConfig'
import { server } from '../../../handlers'
import { clearAllCookies, setCookie } from '../../../helpers/cookies'
import projectInfoFixture from '../../../fixtures/config/project-info-1.json'

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return {
    wrapper: ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children),
  }
}

beforeEach(() => {
  clearAllCookies()
  setCookie('tally_csrf', 'test-csrf-token')
})

afterEach(() => server.resetHandlers())

describe('useProjectInfo', () => {
  it('reshapes the snake_case wire keys to camelCase domain fields', async () => {
    server.use(
      http.get('/api/v1/projects/2/info', () => HttpResponse.json(projectInfoFixture))
    )
    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useProjectInfo(2), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual({
      id: 2,
      name: 'DVPA',
      code: 'DVP',
      companyName: 'DVPA',
      departmentName: 'foosville',
      abbreviation: 'DVP',
      createdAt: '2026-04-25T03:06:56Z',
      path: '/llm/code/tally/projects/DVPA',
      repoCount: 4,
      findingCount: 572,
    })

    const wireBleed = result.current.data as unknown as Record<string, unknown>
    expect(wireBleed.company_name).toBeUndefined()
    expect(wireBleed.department_name).toBeUndefined()
    expect(wireBleed.created_at).toBeUndefined()
    expect(wireBleed.repo_count).toBeUndefined()
    expect(wireBleed.finding_count).toBeUndefined()
  })
})

describe('useUpdateProjectInfo', () => {
  it('PATCHes a snake_case body containing only the fields the caller supplied', async () => {
    let capturedBody: Record<string, unknown> | null = null
    server.use(
      http.patch('/api/v1/projects/2/info', async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...projectInfoFixture, company_name: 'ACME' })
      })
    )

    const { wrapper } = makeWrapper()
    const { result } = renderHook(() => useUpdateProjectInfo(), { wrapper })

    await result.current.mutateAsync({
      projectId: 2,
      updates: { companyName: 'ACME', abbreviation: 'ACM' },
    })

    expect(capturedBody).toEqual({ company_name: 'ACME', abbreviation: 'ACM' })
    const body = capturedBody as Record<string, unknown> | null
    expect(body).not.toBeNull()
    expect(body!).not.toHaveProperty('department_name')
    expect(body!).not.toHaveProperty('companyName')
  })
})
