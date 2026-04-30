import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
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

async function openAdvanced() {
  const user = userEvent.setup()
  // Wait until the scan-config fixture has loaded — Advanced toggle exists
  // before that point but the tools list is empty until the query resolves.
  await screen.findByRole('button', { name: /start scan/i })
  await user.click(screen.getByTitle(/advanced scan options/i))
  // SECRETS chip is rendered from the `domains` array in the fixture.
  await screen.findByRole('button', { name: /^secrets$/i })
  return user
}

function findToolButton(name: string) {
  // Scope to the "Run Only These Tools" panel by walking up to the section
  // that contains the heading, then searching within for the button.
  const heading = screen.getByText(/run only these tools/i)
  const section = heading.closest('div')!.parentElement!
  // Each tool is rendered as a <button> whose accessible name starts with
  // the tool's display name. Match on the first match within the section.
  const buttons = section.querySelectorAll('button')
  for (const btn of Array.from(buttons)) {
    if (btn.textContent?.toLowerCase().startsWith(name.toLowerCase())) {
      return btn as HTMLButtonElement
    }
  }
  throw new Error(`tool button "${name}" not found in tools panel`)
}

describe('Scans page — domain ↔ tool compatibility (12.5)', () => {
  it('disables SAST/SCA/WEB tools when only the SECRETS domain is selected', async () => {
    renderPage()
    const user = await openAdvanced()

    // Baseline: no domains selected, every tool button is enabled.
    await waitFor(() => expect(findToolButton('semgrep')).not.toBeDisabled())
    expect(findToolButton('gitleaks')).not.toBeDisabled()
    expect(findToolButton('osv-scanner')).not.toBeDisabled()
    expect(findToolButton('zap')).not.toBeDisabled()

    await user.click(screen.getByRole('button', { name: /^secrets$/i }))

    // Only secrets-domain tools stay enabled.
    expect(findToolButton('semgrep')).toBeDisabled()
    expect(findToolButton('codeql')).toBeDisabled()
    expect(findToolButton('osv-scanner')).toBeDisabled()
    expect(findToolButton('zap')).toBeDisabled()
    expect(findToolButton('gitleaks')).not.toBeDisabled()
    expect(findToolButton('trufflehog')).not.toBeDisabled()

    // The "N tool(s) disabled by domain filter" hint reflects the count.
    expect(screen.getByText(/10 tool\(s\) disabled by domain filter/i)).toBeInTheDocument()
  })

  it('prunes a previously selected tool when the domain filter excludes it', async () => {
    renderPage()
    const user = await openAdvanced()

    // Pre-select semgrep.
    await waitFor(() => expect(findToolButton('semgrep')).not.toBeDisabled())
    await user.click(findToolButton('semgrep'))
    expect(screen.getByText(/run only these tools \(1 selected\)/i)).toBeInTheDocument()

    // Selecting SECRETS should drop semgrep from the selection.
    await act(async () => {
      await user.click(screen.getByRole('button', { name: /^secrets$/i }))
    })
    await waitFor(() => {
      expect(screen.queryByText(/run only these tools \(1 selected\)/i)).not.toBeInTheDocument()
    })
  })

  it('re-enables every tool once the last domain is deselected', async () => {
    renderPage()
    const user = await openAdvanced()

    await waitFor(() => expect(findToolButton('semgrep')).not.toBeDisabled())
    await user.click(screen.getByRole('button', { name: /^secrets$/i }))
    expect(findToolButton('semgrep')).toBeDisabled()

    // Click SECRETS again to clear the domain filter.
    await user.click(screen.getByRole('button', { name: /^secrets$/i }))

    expect(findToolButton('semgrep')).not.toBeDisabled()
    expect(findToolButton('gitleaks')).not.toBeDisabled()
    expect(findToolButton('zap')).not.toBeDisabled()
    expect(
      screen.queryByText(/tool\(s\) disabled by domain filter/i)
    ).not.toBeInTheDocument()
  })
})
