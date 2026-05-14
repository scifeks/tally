import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import Scans from '@/pages/Scans/index'
import { useUI } from '@/lib/store'
import { __setEventSourceFactory } from '@/lib/api/sse'
import { server } from '../../../handlers'
import { setCookie, clearAllCookies } from '../../../helpers/cookies'
import { MockEventSource } from '../../../helpers/sse'

function makeQC() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
}

function renderPage() {
  return render(
    <MemoryRouter>
      <QueryClientProvider client={makeQC()}>
        <Scans />
      </QueryClientProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  clearAllCookies()
  setCookie('tally_csrf', 'test-csrf-token')
  MockEventSource.reset()
  __setEventSourceFactory(
    (url, init) => new MockEventSource(url, init) as unknown as EventSource
  )
  useUI.setState({
    activeProjectId: 1,
    scanMutationError: null,
    scanWatchState: null,
  })
})

afterEach(() => {
  __setEventSourceFactory(null)
  server.resetHandlers()
})

async function openAdvanced() {
  const user = userEvent.setup()
  await screen.findByRole('button', { name: /start scan/i })
  await user.click(screen.getByTitle(/advanced scan options/i))
  // Wait for the scan config to load so the panel is populated.
  await screen.findByRole('button', { name: /^secrets$/i })
  return user
}

describe('Scans page — arg profile multi-select (5.7)', () => {
  it('renders all four custom arg profiles in the new section', async () => {
    renderPage()
    await openAdvanced()

    await screen.findByText(/run only these custom profiles/i)
    expect(screen.getByText(/gitleaks — verbose-only/i)).toBeInTheDocument()
    expect(screen.getByText(/semgrep — timeout-30s/i)).toBeInTheDocument()
    expect(screen.getByText(/gitleaks — with-config/i)).toBeInTheDocument()
    expect(screen.getByText(/semgrep — strict-with-rules/i)).toBeInTheDocument()
  })

  it('posts argProfileIds for selected profiles when Start Scan is clicked', async () => {
    let captured: Record<string, unknown> = {}
    server.use(
      http.post('/api/v1/projects/:projectId/scans', async ({ params, request }) => {
        captured = (await request.json().catch(() => ({}))) as Record<string, unknown>
        return HttpResponse.json(
          {
            id: 9999,
            project_id: Number(params.projectId),
            status: 'queued',
            started_at: new Date().toISOString(),
            finished_at: null,
            repo_ids: [],
            tool_ids: [],
            domains: [],
            findings_count: null,
            skip_enrichment: false,
          },
          { status: 202 }
        )
      })
    )

    renderPage()
    const user = await openAdvanced()

    await screen.findByText(/gitleaks — verbose-only/i)
    await user.click(screen.getByText(/gitleaks — verbose-only/i))
    await user.click(screen.getByText(/semgrep — timeout-30s/i))

    await screen.findByText(/run only these custom profiles \(2 selected\)/i)

    await user.click(screen.getByRole('button', { name: /start scan/i }))

    await waitFor(() => {
      expect(captured.argProfileIds).toEqual([1, 2])
    })
  })

  it('clears profile selection when Reset All is clicked', async () => {
    renderPage()
    const user = await openAdvanced()

    await screen.findByText(/gitleaks — verbose-only/i)
    await user.click(screen.getByText(/gitleaks — verbose-only/i))
    await screen.findByText(/run only these custom profiles \(1 selected\)/i)

    await user.click(screen.getByRole('button', { name: /reset all/i }))

    await waitFor(() => {
      expect(
        screen.queryByText(/run only these custom profiles \(1 selected\)/i)
      ).not.toBeInTheDocument()
    })
  })

  it('shows the (custom) badge on the Advanced toggle when a profile is selected', async () => {
    renderPage()
    const user = await openAdvanced()

    // Before any selection, no (custom) badge should appear.
    expect(screen.queryByText(/\(custom\)/i)).not.toBeInTheDocument()

    await screen.findByText(/gitleaks — verbose-only/i)
    await user.click(screen.getByText(/gitleaks — verbose-only/i))

    await waitFor(() => {
      expect(screen.getByText(/\(custom\)/i)).toBeInTheDocument()
    })
  })
})
