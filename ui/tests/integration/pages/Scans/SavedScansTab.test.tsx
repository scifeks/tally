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
  useUI.setState({ activeProjectId: 1, scanMutationError: null })
})

afterEach(() => {
  __setEventSourceFactory(null)
  server.resetHandlers()
})

async function openSavedScansTab() {
  const user = userEvent.setup()
  renderPage()
  await user.click(screen.getByRole('button', { name: /saved scans/i }))
  await screen.findByText('Quick Secrets Sweep')
  return user
}

async function openEditor(user: ReturnType<typeof userEvent.setup>, scanName: string) {
  await user.click(screen.getByText(scanName))
  await screen.findByDisplayValue(scanName)
}

describe('Scans page — SavedScansTab editor multi-select (5.8)', () => {
  it('renders merged tool options including template entries with badge', async () => {
    const user = await openSavedScansTab()
    await openEditor(user, 'Full SAST + SCA')

    // gitleaks/with-config and semgrep/strict-with-rules come from arg-profile fixture ids 3 and 4.
    await screen.findByText(/gitleaks \[with-config\]/i)
    expect(screen.getByText(/semgrep \[strict-with-rules\]/i)).toBeInTheDocument()

    const badges = screen.getAllByText(/^template$/i)
    expect(badges.length).toBeGreaterThanOrEqual(2)
  })

  it('hydrates selection count from toolNames + argProfileIds on an existing scan', async () => {
    const user = await openSavedScansTab()
    await openEditor(user, 'Full SAST + SCA')

    // Scan id=2 has 3 toolNames and 2 argProfileIds, so 5 selected entries total.
    await screen.findByText(/tools \(5 selected\)/i)
  })

  it('posts argProfileIds as a distinct array from toolNames on create', async () => {
    let captured: Record<string, unknown> = {}
    server.use(
      http.post('/api/v1/projects/:projectId/saved-scans', async ({ request }) => {
        captured = (await request.json().catch(() => ({}))) as Record<string, unknown>
        return HttpResponse.json(
          {
            id: 99,
            name: captured.name as string,
            skipEnrichment: false,
            repos: [],
            tools: [],
            argProfiles: [
              { id: 1, toolName: 'gitleaks', name: 'verbose-only' },
              { id: 2, toolName: 'semgrep', name: 'timeout-30s' },
            ],
            skipToolIds: [],
            segments: [],
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
          },
          { status: 201 }
        )
      })
    )

    const user = await openSavedScansTab()
    await user.click(screen.getByRole('button', { name: /^new$/i }))
    await screen.findByPlaceholderText(/full-sast-scan/i)

    await user.type(screen.getByPlaceholderText(/full-sast-scan/i), 'my-profile-only-scan')

    // Template entries only appear in the Tools section, not Skip Tools, so getByText resolves without scoping.
    await screen.findByText(/gitleaks \[verbose-only\]/i)
    await user.click(screen.getByText(/gitleaks \[verbose-only\]/i))
    await user.click(screen.getByText(/semgrep \[timeout-30s\]/i))

    await screen.findByText(/tools \(2 selected\)/i)

    await user.click(screen.getByRole('button', { name: /^create$/i }))

    await waitFor(() => {
      expect(captured.toolNames).toEqual([])
      expect(captured.argProfileIds).toEqual([1, 2])
    })
  })

  it('sends updated argProfileIds on PUT when a template is deselected', async () => {
    let captured: Record<string, unknown> = {}
    server.use(
      http.put(
        '/api/v1/projects/:projectId/saved-scans/:savedScanId',
        async ({ request }) => {
          captured = (await request.json().catch(() => ({}))) as Record<string, unknown>
          return HttpResponse.json(
            {
              id: 2,
              name: 'Full SAST + SCA',
              skipEnrichment: true,
              repos: [],
              tools: [],
              argProfiles: [{ id: 4, toolName: 'semgrep', name: 'strict-with-rules' }],
              skipToolIds: ['xsstrike'],
              segments: ['sast', 'sca', 'secrets'],
              createdAt: new Date().toISOString(),
              updatedAt: new Date().toISOString(),
            },
            { status: 200 }
          )
        }
      )
    )

    const user = await openSavedScansTab()
    await openEditor(user, 'Full SAST + SCA')

    await screen.findByText(/gitleaks \[with-config\]/i)
    await user.click(screen.getByText(/gitleaks \[with-config\]/i))

    await screen.findByText(/tools \(4 selected\)/i)

    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => {
      expect(captured.argProfileIds).toEqual([4])
      expect(captured.toolNames).toEqual(
        expect.arrayContaining(['gitleaks', 'osv-scanner', 'semgrep'])
      )
    })
  })
})
