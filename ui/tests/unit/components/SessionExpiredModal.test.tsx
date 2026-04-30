import { describe, expect, it } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SessionExpiredModal } from '@/components/SessionExpiredModal'

describe('SessionExpiredModal', () => {
  it('renders dialog with the expired-session copy', () => {
    render(<SessionExpiredModal />)
    const dialog = screen.getByTestId('session-expired-modal')
    expect(dialog).toBeInTheDocument()
    expect(dialog).toHaveAttribute('role', 'dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByText(/session expired/i)).toBeInTheDocument()
    expect(screen.getByText(/tally ui/i)).toBeInTheDocument()
  })

  it('has no close button - modal cannot be dismissed', () => {
    render(<SessionExpiredModal />)
    expect(screen.queryByRole('button', { name: /close/i })).not.toBeInTheDocument()
  })

  it('Escape keypress on the modal does not unmount it', () => {
    render(<SessionExpiredModal />)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.getByTestId('session-expired-modal')).toBeInTheDocument()
  })
})
