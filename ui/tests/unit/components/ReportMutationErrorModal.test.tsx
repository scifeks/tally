import { describe, expect, it, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ReportMutationErrorModal } from '@/components/ReportMutationErrorModal'
import { useUI } from '@/lib/store'
import type { ApiErrorPayload } from '@/lib/types'

function setError(err: ApiErrorPayload | null) {
  useUI.getState().setReportMutationError(err)
}

describe('ReportMutationErrorModal', () => {
  beforeEach(() => {
    useUI.setState({ reportMutationError: null })
  })

  it('does not render when reportMutationError is null', () => {
    render(<ReportMutationErrorModal />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders the modal when an error is set', () => {
    setError({
      code: 'JOB_ALREADY_RUNNING',
      message: 'already running',
      status: 409,
    })
    render(<ReportMutationErrorModal />)
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-label', 'report action failed')
  })

  it('renders JOB_ALREADY_RUNNING copy', () => {
    setError({ code: 'JOB_ALREADY_RUNNING', message: '', status: 409 })
    render(<ReportMutationErrorModal />)
    expect(
      screen.getByText(/a report generation is already running for this project/i)
    ).toBeInTheDocument()
    expect(
      screen.getByText(/wait for the running generation to complete, or cancel it first/i)
    ).toBeInTheDocument()
  })

  it('renders REPORT_NOT_CANCELLABLE copy', () => {
    setError({ code: 'REPORT_NOT_CANCELLABLE', message: '', status: 409 })
    render(<ReportMutationErrorModal />)
    expect(
      screen.getByText(/no longer cancellable \(already finished\)/i)
    ).toBeInTheDocument()
    expect(
      screen.getByText(/cancellation only applies to runs that are queued or in progress/i)
    ).toBeInTheDocument()
  })

  it('renders VALIDATION_ERROR copy', () => {
    setError({ code: 'VALIDATION_ERROR', message: '', status: 422 })
    render(<ReportMutationErrorModal />)
    expect(
      screen.getByText(/the request was rejected by validation/i)
    ).toBeInTheDocument()
    expect(screen.getByText(/check the form values and try again/i)).toBeInTheDocument()
  })

  it('renders NOT_FOUND copy', () => {
    setError({ code: 'NOT_FOUND', message: '', status: 404 })
    render(<ReportMutationErrorModal />)
    expect(screen.getByText(/the report or draft section was not found/i)).toBeInTheDocument()
    expect(
      screen.getByText(/the section may not have been generated yet/i)
    ).toBeInTheDocument()
  })

  it('renders PATH_TRAVERSAL copy', () => {
    setError({ code: 'PATH_TRAVERSAL', message: '', status: 400 })
    render(<ReportMutationErrorModal />)
    expect(
      screen.getByText(/the server refused the download path \(security guard\)/i)
    ).toBeInTheDocument()
    expect(screen.getByText(/this should never happen with a real report id/i)).toBeInTheDocument()
  })

  it('falls back to the raw message and code/status hint for unknown codes', () => {
    setError({ code: 'WAT', message: 'unexpected boom', status: 500 })
    render(<ReportMutationErrorModal />)
    expect(screen.getByText(/unexpected boom/i)).toBeInTheDocument()
    expect(screen.getByText(/WAT/)).toBeInTheDocument()
    expect(screen.getByText(/500/)).toBeInTheDocument()
  })

  it('clears the slice when dismiss is clicked', () => {
    setError({ code: 'NOT_FOUND', message: '', status: 404 })
    render(<ReportMutationErrorModal />)
    fireEvent.click(screen.getByRole('button', { name: /dismiss/i }))
    expect(useUI.getState().reportMutationError).toBeNull()
  })
})
