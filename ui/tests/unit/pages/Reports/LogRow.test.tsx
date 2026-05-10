import { render, screen } from '@testing-library/react'
import { LogRow } from '@/pages/Reports/LogRow'
import type { ReportLogEvent, ReportLogEventType } from '@/lib/types'

function makeEvent(
  type: ReportLogEventType,
  overrides: Partial<ReportLogEvent> = {},
): ReportLogEvent {
  return {
    id: 'e-1',
    runId: 1,
    type,
    timestamp: '2024-06-15T14:30:05.000Z',
    message: `message for ${type}`,
    ...overrides,
  }
}

describe('Reports LogRow', () => {
  it('renders timestamp in HH:MM:SS format', () => {
    render(<LogRow event={makeEvent('generation_started')} />)
    expect(screen.getByText(/\d{2}:\d{2}:\d{2}/)).toBeInTheDocument()
  })

  it('renders message text', () => {
    render(
      <LogRow
        event={makeEvent('step_started', { message: 'Building executive summary' })}
      />,
    )
    expect(screen.getByText('Building executive summary')).toBeInTheDocument()
  })

  it.each([
    'generation_started',
    'step_started',
    'step_completed',
    'step_failed',
    'generation_completed',
    'generation_failed',
    'draft_started',
    'draft_completed',
    'draft_failed',
  ] as ReportLogEventType[])(
    '%s renders its label with underscores replaced by spaces',
    (type) => {
      render(<LogRow event={makeEvent(type)} />)
      const label = type.replace(/_/g, ' ')
      expect(screen.getByText(label)).toBeInTheDocument()
    },
  )
})
