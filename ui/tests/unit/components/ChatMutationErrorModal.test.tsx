import { describe, expect, it, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ChatMutationErrorModal } from '@/components/ChatMutationErrorModal'
import { useUI } from '@/lib/store'
import type { ApiErrorPayload } from '@/lib/types'

function setError(err: ApiErrorPayload | null) {
  useUI.getState().setChatMutationError(err)
}

describe('ChatMutationErrorModal', () => {
  beforeEach(() => {
    useUI.setState({ chatMutationError: null })
  })

  it('does not render when chatMutationError is null', () => {
    render(<ChatMutationErrorModal />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders the modal when an error is set', () => {
    setError({
      code: 'CHAT_SESSION_EXPIRED',
      message: 'sealed',
      details: {},
      status: 409,
    })
    render(<ChatMutationErrorModal />)
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-label', 'chat action failed')
  })

  it('renders CHAT_SESSION_EXPIRED copy', () => {
    setError({ code: 'CHAT_SESSION_EXPIRED', message: '', details: {}, status: 409 })
    render(<ChatMutationErrorModal />)
    expect(
      screen.getByText(/this chat session was sealed when a scan completed/i)
    ).toBeInTheDocument()
    expect(
      screen.getByText(/create a new session to continue the conversation/i)
    ).toBeInTheDocument()
  })

  it('renders CHAT_STREAM_ALREADY_RUNNING copy', () => {
    setError({ code: 'CHAT_STREAM_ALREADY_RUNNING', message: '', details: {}, status: 409 })
    render(<ChatMutationErrorModal />)
    expect(
      screen.getByText(/another response is already streaming for this session/i)
    ).toBeInTheDocument()
    expect(
      screen.getByText(/wait for the in-flight response to finish, or cancel it first/i)
    ).toBeInTheDocument()
  })

  it('renders CHAT_NO_ACTIVE_STREAM copy', () => {
    setError({ code: 'CHAT_NO_ACTIVE_STREAM', message: '', details: {}, status: 409 })
    render(<ChatMutationErrorModal />)
    expect(screen.getByText(/no in-flight response to cancel/i)).toBeInTheDocument()
    expect(
      screen.getByText(/the stream may have already completed before the cancel arrived/i)
    ).toBeInTheDocument()
  })

  it('renders VALIDATION_ERROR copy', () => {
    setError({ code: 'VALIDATION_ERROR', message: '', details: {}, status: 422 })
    render(<ChatMutationErrorModal />)
    expect(
      screen.getByText(/message content is empty or exceeds the size limit/i)
    ).toBeInTheDocument()
    expect(
      screen.getByText(/enter a non-empty message under the per-turn character limit/i)
    ).toBeInTheDocument()
  })

  it('renders NOT_FOUND copy', () => {
    setError({ code: 'NOT_FOUND', message: '', details: {}, status: 404 })
    render(<ChatMutationErrorModal />)
    expect(screen.getByText(/this chat session no longer exists/i)).toBeInTheDocument()
    expect(
      screen.getByText(/the session may have been purged or deleted in another tab/i)
    ).toBeInTheDocument()
  })

  it('falls back to the raw message and code/status hint for unknown codes', () => {
    setError({ code: 'WAT', message: 'unexpected boom', details: {}, status: 500 })
    render(<ChatMutationErrorModal />)
    expect(screen.getByText(/unexpected boom/i)).toBeInTheDocument()
    expect(screen.getByText(/WAT/)).toBeInTheDocument()
    expect(screen.getByText(/500/)).toBeInTheDocument()
  })

  it('clears the slice when dismiss is clicked', () => {
    setError({ code: 'NOT_FOUND', message: '', details: {}, status: 404 })
    render(<ChatMutationErrorModal />)
    fireEvent.click(screen.getByRole('button', { name: /dismiss/i }))
    expect(useUI.getState().chatMutationError).toBeNull()
  })
})
