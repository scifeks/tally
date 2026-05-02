import { describe, expect, it, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ScanMutationErrorModal } from '@/components/ScanMutationErrorModal'
import { useUI } from '@/lib/store'
import type { ApiErrorPayload } from '@/lib/types'

function setError(err: ApiErrorPayload | null) {
  useUI.getState().setScanMutationError(err)
}

describe('ScanMutationErrorModal', () => {
  beforeEach(() => {
    useUI.setState({ scanMutationError: null })
  })

  it('renders the generic envelope with code and status when status is not 409', () => {
    setError({
      code: 'INVALID',
      message: 'validation failed',
      details: {},
      status: 422,
    })
    render(<ScanMutationErrorModal />)

    expect(screen.getByText(/validation failed/i)).toBeInTheDocument()
    expect(screen.getByText('code:')).toBeInTheDocument()
    expect(screen.getByText('INVALID')).toBeInTheDocument()
    expect(screen.getByText('status:')).toBeInTheDocument()
    expect(screen.getByText('422')).toBeInTheDocument()
    expect(screen.queryByText(/concurrent scans on the same project/i)).toBeNull()
  })

  it('renders the 409 conflict copy and hides the generic code/status hint', () => {
    setError({
      code: 'SCAN_ALREADY_RUNNING',
      message: 'irrelevant',
      details: {},
      status: 409,
    })
    render(<ScanMutationErrorModal />)

    expect(screen.getByText(/a scan is already running on this project/i)).toBeInTheDocument()
    expect(
      screen.getByText(
        /concurrent scans on the same project aren't supported\. wait for the running scan to complete or cancel it before starting another/i
      )
    ).toBeInTheDocument()
    expect(screen.queryByText('code:')).toBeNull()
    expect(screen.queryByText('status:')).toBeNull()
  })
})
