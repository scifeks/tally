import { render, screen } from '@testing-library/react'
import { LogRow } from '@/pages/Triage/LogRow'
import type { TriageLogEvent, TriageLogEventType } from '@/lib/types'

function makeEvent(
  type: TriageLogEventType,
  overrides: Partial<TriageLogEvent> = {},
): TriageLogEvent {
  return {
    id: 'e-1',
    runId: 'TR-1',
    type,
    timestamp: '2024-06-15T09:05:30.000Z',
    message: `message for ${type}`,
    ...overrides,
  }
}

describe('Triage LogRow', () => {
  it('renders timestamp in HH:MM:SS format', () => {
    render(<LogRow event={makeEvent('run_started')} />)
    expect(screen.getByText(/\d{2}:\d{2}:\d{2}/)).toBeInTheDocument()
  })

  it('renders message text', () => {
    render(<LogRow event={makeEvent('batch_started', { message: 'Batch processing' })} />)
    expect(screen.getByText('Batch processing')).toBeInTheDocument()
  })

  it.each([
    ['batch_started', '[*]'],
    ['batch_completed', '[✓]'],
    ['batch_failed', '[!]'],
    ['batch_retry', '[↻]'],
    ['run_cancelled', 'XXX'],
  ] as [TriageLogEventType, string][])(
    '%s renders prefix "%s"',
    (type, prefix) => {
      render(<LogRow event={makeEvent(type)} />)
      expect(screen.getByText(prefix)).toBeInTheDocument()
    },
  )

  it('renders processedCount/totalCount fraction when both fields are present', () => {
    render(
      <LogRow
        event={makeEvent('batch_progress', { processedCount: 12, totalCount: 50 })}
      />,
    )
    expect(screen.getByText('12/50')).toBeInTheDocument()
  })

  it('does not render fraction when processedCount or totalCount is absent', () => {
    render(<LogRow event={makeEvent('batch_progress', { processedCount: 12 })} />)
    expect(screen.queryByText(/12\/\d+/)).toBeNull()
  })
})
