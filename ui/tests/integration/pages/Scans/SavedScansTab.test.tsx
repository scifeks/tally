import { render, screen, waitFor, within } from '@testing-library/react'
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

describe('Scans page — SavedScansTab editor accordion tools (5.8)', () => {
  it('shows template badges in accordion when a profiled tool is expanded', async () => {
    const user = await openSavedScansTab()
    await openEditor(user, 'Full SAST + SCA')

    // gitleaks has profile "with-config" (id 3) selected; expand its accordion.
    await user.click(await screen.findByRole('button', { name: /gitleaks profiles/i }))

    // Expanded accordion shows profile radio options with TEMPLATE badges.
    const toolsSection = screen.getByTestId('tools-section')
    await within(toolsSection).findByText('with-config')
    const badges = within(toolsSection).getAllByText(/^template$/i)
    expect(badges.length).toBeGreaterThanOrEqual(1)
  })

  it('hydrates selection count from merged toolNames + argProfileIds', async () => {
    const user = await openSavedScansTab()
    await openEditor(user, 'Full SAST + SCA')

    // Scan id=2: toolNames=[gitleaks, osv-scanner, semgrep], argProfileIds=[3, 4].
    // Profiles supersede base entries: gitleaks:3 replaces gitleaks, semgrep:4 replaces semgrep.
    // Result: [osv-scanner, gitleaks:3, semgrep:4] = 3 selected.
    await screen.findByText(/tools \(3 selected\)/i)
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

    // Scope clicks to the Tools section (gitleaks also appears in Skip Tools).
    const toolsSection = screen.getByTestId('tools-section')

    // Select gitleaks (auto-expands accordion), pick the "verbose-only" profile.
    await user.click(within(toolsSection).getByText('gitleaks'))
    await within(toolsSection).findByText('verbose-only')
    await user.click(within(toolsSection).getByText('verbose-only'))

    // Select semgrep (auto-expands), pick "timeout-30s".
    await user.click(within(toolsSection).getByText('semgrep'))
    await within(toolsSection).findByText('timeout-30s')
    await user.click(within(toolsSection).getByText('timeout-30s'))

    await screen.findByText(/tools \(2 selected\)/i)

    await user.click(screen.getByRole('button', { name: /^create$/i }))

    await waitFor(() => {
      expect(captured.toolNames).toEqual([])
      expect(captured.argProfileIds).toEqual([1, 2])
    })
  })

  it('sends updated argProfileIds on PUT when profile reverted to default', async () => {
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

    await screen.findByText(/tools \(3 selected\)/i)

    // Expand gitleaks accordion via its aria-labelled chevron.
    await user.click(screen.getByRole('button', { name: /gitleaks profiles/i }))

    // Click "Default" radio to revert gitleaks from profile to base tool.
    const toolsSection = screen.getByTestId('tools-section')
    await within(toolsSection).findByText('Default')
    await user.click(within(toolsSection).getByText('Default'))

    // Still 3 selected: gitleaks (default), osv-scanner, semgrep:4.
    await screen.findByText(/tools \(3 selected\)/i)

    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => {
      expect(captured.argProfileIds).toEqual([4])
      expect(captured.toolNames).toEqual(
        expect.arrayContaining(['gitleaks', 'osv-scanner'])
      )
    })
  })
})
