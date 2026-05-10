import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { BatchRow, type BatchDisplay } from '@/pages/Triage/BatchRow'

function makeBatch(overrides: Partial<BatchDisplay> = {}): BatchDisplay {
  return {
    id: 1,
    segment: 'sast',
    findingCount: 12,
    status: 'completed',
    attempt: 1,
    startedAt: '2026-04-29T10:00:00Z',
    finishedAt: '2026-04-29T10:30:00Z',
    ...overrides,
  }
}

describe('BatchRow', () => {
  it('renders the attempt badge only when attempt > 1', () => {
    const { unmount } = render(
      <BatchRow batch={makeBatch({ attempt: 1 })} expanded={false} onToggle={() => undefined} />
    )
    expect(screen.queryByText(/attempt #/i)).toBeNull()
    unmount()

    render(
      <BatchRow batch={makeBatch({ attempt: 3 })} expanded={false} onToggle={() => undefined} />
    )
    expect(screen.getByText('attempt #3')).toBeInTheDocument()
  })

  it('falls back to the MIXED segment label when segment is null', () => {
    render(
      <BatchRow
        batch={makeBatch({ segment: null, findingCount: 7 })}
        expanded={true}
        onToggle={() => undefined}
      />
    )
    expect(screen.getByText('MIXED')).toBeInTheDocument()
    expect(screen.getByText(/7\s+findings\s+in\s+MIXED/i)).toBeInTheDocument()
  })

  it('hides the body when collapsed and forwards click to onToggle', async () => {
    const onToggle = vi.fn()
    const user = userEvent.setup()
    render(
      <BatchRow batch={makeBatch()} expanded={false} onToggle={onToggle} />
    )

    expect(screen.queryByText(/Claude analysis/i)).toBeNull()
    await user.click(screen.getByRole('button'))
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it('renders the finishedAt time only when provided', () => {
    const { unmount } = render(
      <BatchRow
        batch={makeBatch({ finishedAt: undefined })}
        expanded={false}
        onToggle={() => undefined}
      />
    )
    expect(screen.queryByText(/^\d{1,2}:\d{2}/)).toBeNull()
    unmount()

    render(
      <BatchRow
        batch={makeBatch({ finishedAt: '2026-04-29T10:30:00Z' })}
        expanded={false}
        onToggle={() => undefined}
      />
    )
    expect(screen.getByText(/^\d{1,2}:\d{2}/)).toBeInTheDocument()
  })
})
