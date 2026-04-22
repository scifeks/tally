import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PreflightChecklist } from '@/pages/Reports/PreflightChecklist'
import type { ReportDraft } from '@/lib/types'
import { SECTION_ORDER } from '@/pages/Reports/constants'

function makeDrafts(status: ReportDraft['status']): ReportDraft[] {
  return SECTION_ORDER.map(section => ({ section, status }))
}

describe('PreflightChecklist', () => {
  it('does not show Generate PDF button when any draft has status not_generated', () => {
    render(
      <PreflightChecklist
        drafts={makeDrafts('not_generated')}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />,
    )
    expect(screen.queryByRole('button', { name: /generate pdf/i })).toBeNull()
  })

  it('does not show Generate PDF button when any draft has status failed', () => {
    render(
      <PreflightChecklist
        drafts={makeDrafts('failed')}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />,
    )
    expect(screen.queryByRole('button', { name: /generate pdf/i })).toBeNull()
  })

  it('shows Generate PDF button when all drafts have status draft', () => {
    render(
      <PreflightChecklist
        drafts={makeDrafts('draft')}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: /generate pdf/i })).toBeInTheDocument()
  })

  it('shows Generate PDF button when all drafts have status reviewed', () => {
    render(
      <PreflightChecklist
        drafts={makeDrafts('reviewed')}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: /generate pdf/i })).toBeInTheDocument()
  })

  it('calls onConfirm when Generate PDF is clicked', async () => {
    const onConfirm = vi.fn()
    const user = userEvent.setup()
    render(
      <PreflightChecklist
        drafts={makeDrafts('draft')}
        onClose={vi.fn()}
        onConfirm={onConfirm}
      />,
    )
    await user.click(screen.getByRole('button', { name: /generate pdf/i }))
    expect(onConfirm).toHaveBeenCalledOnce()
  })

  it('calls onClose when the close (X) button is clicked', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(
      <PreflightChecklist
        drafts={makeDrafts('not_generated')}
        onClose={onClose}
        onConfirm={vi.fn()}
      />,
    )
    const closeButtons = screen.getAllByRole('button')
    await user.click(closeButtons[0])
    expect(onClose).toHaveBeenCalledOnce()
  })
})
