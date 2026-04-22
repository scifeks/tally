import { render, screen } from '@testing-library/react'
import { LogRow } from '@/pages/Scans/LogRow'
import type { ScanLogEvent, ScanLogEventType } from '@/lib/types'

function makeEvent(type: ScanLogEventType, overrides: Partial<ScanLogEvent> = {}): ScanLogEvent {
  return {
    id: 'e-1',
    runId: 'SR-1',
    type,
    timestamp: '2024-06-15T14:30:05.000Z',
    message: `message for ${type}`,
    ...overrides,
  }
}

describe('Scans LogRow', () => {
  it('renders timestamp in HH:MM:SS format', () => {
    render(<LogRow event={makeEvent('run_started')} />)
    expect(screen.getByText(/\d{2}:\d{2}:\d{2}/)).toBeInTheDocument()
  })

  it('renders message text', () => {
    render(<LogRow event={makeEvent('tool_started', { message: 'Starting semgrep' })} />)
    expect(screen.getByText('Starting semgrep')).toBeInTheDocument()
  })

  it.each([
    ['tool_started', '[*]'],
    ['tool_completed', '[+]'],
    ['tool_failed', '[!]'],
    ['run_cancelled', 'XXX'],
  ] as [ScanLogEventType, string][])(
    '%s renders prefix "%s"',
    (type, prefix) => {
      render(<LogRow event={makeEvent(type)} />)
      expect(screen.getByText(prefix)).toBeInTheDocument()
    },
  )

  it('run_started renders prefix ">>>"', () => {
    render(<LogRow event={makeEvent('run_started')} />)
    expect(screen.getAllByText('>>>').length).toBeGreaterThan(0)
  })

  it('run_completed renders prefix ">>>"', () => {
    render(<LogRow event={makeEvent('run_completed')} />)
    expect(screen.getAllByText('>>>').length).toBeGreaterThan(0)
  })
})
