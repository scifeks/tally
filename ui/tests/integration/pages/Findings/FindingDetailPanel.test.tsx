import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { FindingDetailPanel } from '@/pages/Findings/FindingDetailPanel'
import type { Finding } from '@/lib/types'
import { useUI } from '@/lib/store'
import { server } from '../../../handlers'
import { clearAllCookies, setCookie } from '../../../helpers/cookies'

const fixtureFinding: Finding = {
  id: 1001,
  projectId: 1,
  segment: 'sast',
  domain: 'code',
  severity: 'critical',
  status: 'active',
  confidence: 'high',
  findingType: ['sql-injection'],
  title: 'SQL injection in user search',
  tool: 'semgrep',
  target: 'acme-api',
  file: 'src/handlers/users.py',
  line: 42,
  cwe: ['CWE-89'],
  discoveredAt: '2026-04-26T10:00:00Z',
  isLocked: false,
  lockHolder: null,
}

function makeQC() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
}

function renderPanel(onUpdate: (patch: Partial<Finding>) => void) {
  return render(
    <MemoryRouter>
      <QueryClientProvider client={makeQC()}>
        <FindingDetailPanel finding={fixtureFinding} onUpdate={onUpdate} />
      </QueryClientProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  clearAllCookies()
  setCookie('tally_csrf', 'test-csrf-token')
  useUI.setState({ activeProjectId: 1, triageInjectionAcked: true })
})

afterEach(() => server.resetHandlers())

describe('FindingDetailPanel - quick-status buttons', () => {
  it.each([
    ['mark fixed', 'fixed'],
    ['false-pos', 'false_positive'],
    ['wontfix', 'wont_fix'],
  ] as const)('"%s" button click fires onUpdate({ status: %s })', async (label, status) => {
    const onUpdate = vi.fn()
    const user = userEvent.setup()
    renderPanel(onUpdate)

    await user.click(screen.getByRole('button', { name: new RegExp(`^${label}$`, 'i') }))

    expect(onUpdate).toHaveBeenCalledTimes(1)
    expect(onUpdate).toHaveBeenCalledWith({ status })
  })
})
