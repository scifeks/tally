import { describe, expect, it, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { FindingMutationErrorModal } from '@/components/FindingMutationErrorModal'
import { useUI } from '@/lib/store'
import type { ApiErrorPayload } from '@/lib/types'

function setError(err: ApiErrorPayload | null) {
  useUI.getState().setFindingMutationError(err)
}

describe('FindingMutationErrorModal', () => {
  beforeEach(() => {
    useUI.setState({ findingMutationError: null })
  })

  it('renders the generic envelope copy with code and status when not FINDING_LOCKED', () => {
    setError({
      code: 'INVALID',
      message: 'validation failed',
      details: {},
      status: 422,
    })
    render(<FindingMutationErrorModal />)

    expect(screen.getByText(/validation failed/i)).toBeInTheDocument()
    expect(screen.getByText('code:')).toBeInTheDocument()
    expect(screen.getByText('INVALID')).toBeInTheDocument()
    expect(screen.getByText('status:')).toBeInTheDocument()
    expect(screen.getByText('422')).toBeInTheDocument()
    expect(screen.queryByText(/wait for the running job to release the finding/i)).toBeNull()
  })

  it('renders the FINDING_LOCKED branch with details.job_id and the lock-specific hint', () => {
    setError({
      code: 'FINDING_LOCKED',
      message: 'locked',
      details: { job_id: 'job-123' },
      status: 409,
    })
    render(<FindingMutationErrorModal />)

    expect(screen.getByText(/held by/i)).toBeInTheDocument()
    expect(screen.getByText('job-123')).toBeInTheDocument()
    expect(
      screen.getByText(/wait for the running job to release the finding/i)
    ).toBeInTheDocument()
    expect(screen.queryByText('code:')).toBeNull()
    expect(screen.queryByText('status:')).toBeNull()
  })
})
