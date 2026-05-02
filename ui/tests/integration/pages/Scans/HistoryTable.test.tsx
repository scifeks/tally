import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { HistoryTable } from '@/pages/Scans/HistoryTable'
import { server } from '../../../handlers'
import { clearAllCookies, setCookie } from '../../../helpers/cookies'

function makeQC() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
}

function renderTable(projectId: number) {
  return render(
    <QueryClientProvider client={makeQC()}>
      <HistoryTable projectId={projectId} />
    </QueryClientProvider>
  )
}

interface WireScan {
  id: number
  project_id: number
  status: 'running' | 'done' | 'failed' | 'cancelled' | 'cancelling' | 'queued'
  started_at: string
  finished_at?: string | null
  repo_ids?: string[]
  tool_ids?: string[]
  domains?: string[]
  findings_count?: number | null
  skip_enrichment?: boolean
}

function respondWith(items: WireScan[]) {
  server.use(
    http.get('/api/v1/projects/:projectId/scans', () =>
      HttpResponse.json({ items, total: items.length, offset: 0, limit: 20 })
    )
  )
}

beforeEach(() => {
  clearAllCookies()
  setCookie('tally_csrf', 'test-csrf-token')
})

afterEach(() => server.resetHandlers())

describe('Scans HistoryTable', () => {
  it('renders the empty-state copy when the API returns no items', async () => {
    respondWith([])
    renderTable(7)
    expect(await screen.findByText(/no scan history for this project yet/i)).toBeInTheDocument()
  })

  it('hides running scans and keeps done / failed rows', async () => {
    respondWith([
      {
        id: 7001,
        project_id: 7,
        status: 'running',
        started_at: '2026-04-29T10:00:00Z',
        domains: ['sast'],
        tool_ids: ['semgrep'],
      },
      {
        id: 7002,
        project_id: 7,
        status: 'done',
        started_at: '2026-04-28T10:00:00Z',
        finished_at: '2026-04-28T10:30:00Z',
        domains: ['web'],
        tool_ids: ['zap'],
        findings_count: 12,
      },
      {
        id: 7003,
        project_id: 7,
        status: 'failed',
        started_at: '2026-04-27T10:00:00Z',
        finished_at: '2026-04-27T10:05:00Z',
        domains: ['secrets'],
        tool_ids: ['gitleaks'],
      },
    ])
    renderTable(7)

    await waitFor(() => expect(screen.getByText('7002')).toBeInTheDocument())
    expect(screen.getByText('7003')).toBeInTheDocument()
    expect(screen.queryByText('7001')).toBeNull()
  })

  it('orders rows by started_at descending regardless of payload order', async () => {
    const stub: Pick<WireScan, 'domains' | 'tool_ids' | 'repo_ids'> = {
      domains: [],
      tool_ids: [],
      repo_ids: [],
    }
    respondWith([
      {
        id: 100,
        project_id: 7,
        status: 'done',
        started_at: '2026-04-10T08:00:00Z',
        finished_at: '2026-04-10T08:30:00Z',
        ...stub,
      },
      {
        id: 300,
        project_id: 7,
        status: 'done',
        started_at: '2026-04-30T08:00:00Z',
        finished_at: '2026-04-30T08:30:00Z',
        ...stub,
      },
      {
        id: 200,
        project_id: 7,
        status: 'done',
        started_at: '2026-04-20T08:00:00Z',
        finished_at: '2026-04-20T08:30:00Z',
        ...stub,
      },
    ])
    renderTable(7)

    await waitFor(() => expect(screen.getByText('300')).toBeInTheDocument())

    const ids = screen
      .getAllByRole('cell')
      .filter(cell => /^[123]00$/.test(cell.textContent ?? ''))
      .map(cell => cell.textContent)

    expect(ids).toEqual(['300', '200', '100'])
  })
})
