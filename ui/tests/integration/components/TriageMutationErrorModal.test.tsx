import { describe, expect, it, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TriageMutationErrorModal } from '@/components/TriageMutationErrorModal'
import { useUI } from '@/lib/store'
import type { ApiErrorPayload } from '@/lib/types'

function setError(err: ApiErrorPayload | null) {
  useUI.getState().setTriageMutationError(err)
}

describe('TriageMutationErrorModal', () => {
  beforeEach(() => {
    useUI.setState({ triageMutationError: null })
  })

  it('does not render when triageMutationError is null', () => {
    render(<TriageMutationErrorModal />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders the modal when an error is set', () => {
    setError({
      code: 'JOB_ALREADY_RUNNING',
      message: 'a triage job is already running',
      status: 409,
    })
    render(<TriageMutationErrorModal />)
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-label', 'triage failed')
  })

  it('renders JOB_ALREADY_RUNNING copy', () => {
    setError({
      code: 'JOB_ALREADY_RUNNING',
      message: 'a triage job is already running',
      status: 409,
    })
    render(<TriageMutationErrorModal />)
    expect(
      screen.getByText(/a triage run is already active on this project/i)
    ).toBeInTheDocument()
    expect(
      screen.getByText(/wait for the running triage to complete, or cancel it first/i)
    ).toBeInTheDocument()
  })

  it('renders TRIAGE_NOT_CANCELLABLE copy', () => {
    setError({
      code: 'TRIAGE_NOT_CANCELLABLE',
      message: 'cannot cancel',
      status: 409,
    })
    render(<TriageMutationErrorModal />)
    expect(
      screen.getByText(/no longer cancellable \(already finished\)/i)
    ).toBeInTheDocument()
    expect(
      screen.getByText(/cancellation only applies to runs that are queued or in progress/i)
    ).toBeInTheDocument()
  })

  it('renders TRIAGE_NOT_RESUMABLE copy', () => {
    setError({
      code: 'TRIAGE_NOT_RESUMABLE',
      message: 'cannot resume',
      status: 409,
    })
    render(<TriageMutationErrorModal />)
    expect(
      screen.getByText(/no longer resumable \(already finished or cancelled\)/i)
    ).toBeInTheDocument()
    expect(
      screen.getByText(/resume only applies to failed runs/i)
    ).toBeInTheDocument()
  })

  it('renders VALIDATION_ERROR copy', () => {
    setError({
      code: 'VALIDATION_ERROR',
      message: 'missing field',
      status: 422,
    })
    render(<TriageMutationErrorModal />)
    expect(
      screen.getByText(/the request was rejected by validation/i)
    ).toBeInTheDocument()
    expect(
      screen.getByText(/reload the page and try again/i)
    ).toBeInTheDocument()
  })

  it('renders NOT_FOUND copy', () => {
    setError({
      code: 'NOT_FOUND',
      message: 'no triage data',
      status: 404,
    })
    render(<TriageMutationErrorModal />)
    expect(
      screen.getByText(/no triage data found for this project/i)
    ).toBeInTheDocument()
    expect(
      screen.getByText(/a successful scan must complete before triage can run/i)
    ).toBeInTheDocument()
  })

  it('falls back to the raw message and code/status hint for unknown codes', () => {
    setError({
      code: 'SOMETHING_ELSE',
      message: 'unexpected boom',
      status: 500,
    })
    render(<TriageMutationErrorModal />)
    expect(screen.getByText(/unexpected boom/i)).toBeInTheDocument()
    expect(screen.getByText(/SOMETHING_ELSE/)).toBeInTheDocument()
    expect(screen.getByText(/500/)).toBeInTheDocument()
  })

  it('clears the slice when dismiss is clicked', async () => {
    const user = userEvent.setup()
    setError({
      code: 'JOB_ALREADY_RUNNING',
      message: 'a triage job is already running',
      status: 409,
    })
    render(<TriageMutationErrorModal />)
    await user.click(screen.getByRole('button', { name: /dismiss/i }))
    expect(useUI.getState().triageMutationError).toBeNull()
  })
})
