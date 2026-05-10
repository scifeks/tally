import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

  it('Escape keypress on the modal does not unmount it', async () => {
    const user = userEvent.setup()
    render(<SessionExpiredModal />)
    await user.keyboard('{Escape}')
    expect(screen.getByTestId('session-expired-modal')).toBeInTheDocument()
  })
})
