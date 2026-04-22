import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import Findings from '@/pages/Findings/index'
import { useUI } from '@/lib/store'
import type { Finding } from '@/lib/types'

const baseFinding: Omit<Finding, 'id' | 'severity' | 'status' | 'title' | 'tool'> = {
  projectId: 'p-01',
  segment: 'sast',
  target: 'acme',
  discoveredAt: '2024-01-01T00:00:00Z',
}

const FINDINGS: Finding[] = [
  {
    ...baseFinding,
    id: 'f-1',
    severity: 'critical',
    status: 'active',
    title: 'SQL injection',
    tool: 'semgrep',
  },
  {
    ...baseFinding,
    id: 'f-2',
    severity: 'high',
    status: 'active',
    title: 'XSS vulnerability',
    tool: 'bandit',
  },
  {
    ...baseFinding,
    id: 'f-3',
    severity: 'medium',
    status: 'fixed',
    title: 'Path traversal',
    tool: 'semgrep',
  },
  {
    ...baseFinding,
    id: 'f-4',
    severity: 'critical',
    status: 'fixed',
    title: 'Remote code execution',
    tool: 'bandit',
  },
]

// The footer renders <span>{count}</span> result(s) — getNodeText only sees the
// direct text node (" results"), so we must match via element.textContent.
function byResultCount(n: number) {
  const expected = n === 1 ? '1 result' : `${n} results`
  return (_: string, el: Element | null) => el?.textContent?.trim() === expected
}

function makeQC() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  qc.setQueryData(['findings', 'p-01', undefined], FINDINGS)
  return qc
}

function renderPage(qc = makeQC()) {
  render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <Findings />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  useUI.setState({
    activeProjectId: 'p-01',
    findingsSegment: 'sast',
    selectedFindingIds: new Set<string>(),
    findingOverrides: {},
    triageRunStatus: 'idle',
  })
})

describe('Findings page — applyFilters', () => {
  it('shows all findings in the footer when no filters are active', async () => {
    renderPage()
    await screen.findByText(byResultCount(4))
  })

  it('removes non-matching findings when severity filter is applied', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText(byResultCount(4))
    await user.click(screen.getByTitle('filter CRIT'))
    // critical: f-1, f-4
    await screen.findByText(byResultCount(2))
  })

  it('uses OR when multiple severity filters are selected', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText(byResultCount(4))
    await user.click(screen.getByTitle('filter CRIT'))
    await user.click(screen.getByTitle('filter HIGH'))
    // critical (f-1, f-4) OR high (f-2) = 3
    await screen.findByText(byResultCount(3))
  })

  it('uses AND between severity and status filters', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText(byResultCount(4))
    await user.click(screen.getByTitle('filter CRIT'))
    await screen.findByText(byResultCount(2))
    await user.click(screen.getByRole('button', { name: 'Filter status' }))
    await user.click(screen.getByRole('checkbox', { name: /^active/ }))
    // critical AND active = only f-1
    await screen.findByText(byResultCount(1))
  })

  it('matches findings by title substring case-insensitively', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText(byResultCount(4))
    await user.type(screen.getByRole('textbox', { name: 'Search findings' }), 'sql')
    // "SQL injection" (f-1) contains "sql" case-insensitively
    await screen.findByText(byResultCount(1))
  })

  it('search also matches the tool field', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText(byResultCount(4))
    await user.type(screen.getByRole('textbox', { name: 'Search findings' }), 'bandit')
    // f-2 and f-4 both have tool "bandit"
    await screen.findByText(byResultCount(2))
  })

  it('shows the no-match message when no findings pass filters', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText(byResultCount(4))
    await user.type(
      screen.getByRole('textbox', { name: 'Search findings' }),
      'zzznomatch',
    )
    await screen.findByText('// no findings match current filters')
  })

  it('shows the empty-state component when the domain has no findings', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText(byResultCount(4))
    // WEB domain has no findings in seeded data (all are sast)
    await user.click(screen.getByRole('button', { name: /^WEB/ }))
    await screen.findByText(/no findings yet/i)
  })
})
