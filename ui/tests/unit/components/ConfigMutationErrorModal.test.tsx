import { describe, expect, it, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ConfigMutationErrorModal } from '@/components/ConfigMutationErrorModal'
import { useUI } from '@/lib/store'
import type { ApiErrorPayload } from '@/lib/types'

function setError(err: ApiErrorPayload | null) {
  useUI.getState().setConfigMutationError(err)
}

describe('ConfigMutationErrorModal', () => {
  beforeEach(() => {
    useUI.setState({ configMutationError: null })
  })

  it('does not render when configMutationError is null', () => {
    render(<ConfigMutationErrorModal />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders the modal when an error is set', () => {
    setError({
      code: 'VALIDATION_ERROR',
      message: 'rejected',
      details: {},
      status: 422,
    })
    render(<ConfigMutationErrorModal />)
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-label', 'config action failed')
  })

  it('renders VALIDATION_ERROR copy', () => {
    setError({ code: 'VALIDATION_ERROR', message: '', details: {}, status: 422 })
    render(<ConfigMutationErrorModal />)
    expect(
      screen.getByText(/one or more fields were rejected by validation/i)
    ).toBeInTheDocument()
    expect(screen.getByText(/check the highlighted fields and try again/i)).toBeInTheDocument()
  })

  it('renders NOT_FOUND copy', () => {
    setError({ code: 'NOT_FOUND', message: '', details: {}, status: 404 })
    render(<ConfigMutationErrorModal />)
    expect(
      screen.getByText(/the project, repository, or tool override no longer exists/i)
    ).toBeInTheDocument()
    expect(
      screen.getByText(/the row may have been deleted in another tab; reload to refresh/i)
    ).toBeInTheDocument()
  })

  it('renders CONFLICT copy', () => {
    setError({ code: 'CONFLICT', message: '', details: {}, status: 409 })
    render(<ConfigMutationErrorModal />)
    expect(
      screen.getByText(/this change conflicts with the current configuration/i)
    ).toBeInTheDocument()
    expect(
      screen.getByText(/reload to see the latest configuration before retrying/i)
    ).toBeInTheDocument()
  })

  it('renders PATH_TRAVERSAL copy', () => {
    setError({ code: 'PATH_TRAVERSAL', message: '', details: {}, status: 400 })
    render(<ConfigMutationErrorModal />)
    expect(
      screen.getByText(/the server refused the path \(security guard\)/i)
    ).toBeInTheDocument()
    expect(screen.getByText(/use a path inside the project workspace/i)).toBeInTheDocument()
  })

  it('falls back to the raw message and code/status hint for unknown codes', () => {
    setError({ code: 'WAT', message: 'unexpected boom', details: {}, status: 500 })
    render(<ConfigMutationErrorModal />)
    expect(screen.getByText(/unexpected boom/i)).toBeInTheDocument()
    expect(screen.getByText(/WAT/)).toBeInTheDocument()
    expect(screen.getByText(/500/)).toBeInTheDocument()
  })

  it('clears the slice when dismiss is clicked', () => {
    setError({ code: 'NOT_FOUND', message: '', details: {}, status: 404 })
    render(<ConfigMutationErrorModal />)
    fireEvent.click(screen.getByRole('button', { name: /dismiss/i }))
    expect(useUI.getState().configMutationError).toBeNull()
  })
})
