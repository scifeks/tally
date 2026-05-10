import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ProjectSwitchModal } from '@/components/ProjectSwitchModal'
import type { Project } from '@/lib/types'

const FROM: Project = { id: 1, name: 'damn vulnerable web app', code: 'DVWA' }
const TO: Project = { id: 2, name: 'damn vulnerable platform alt', code: 'DVPA-alt' }

function renderModal(overrides: Partial<Parameters<typeof ProjectSwitchModal>[0]> = {}) {
  const defaults = {
    open: true,
    from: FROM,
    to: TO,
    runningScansCount: 0,
    triageRunning: false,
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
  }
  return { props: defaults, ...render(<ProjectSwitchModal {...defaults} {...overrides} />) }
}

describe('ProjectSwitchModal', () => {
  it('confirm form fires onConfirm and onCancel for the two footer buttons', async () => {
    const onConfirm = vi.fn()
    const onCancel = vi.fn()
    const user = userEvent.setup()
    renderModal({ onConfirm, onCancel })

    const dialog = screen.getByRole('dialog', { name: 'confirm switch' })
    expect(dialog).toHaveTextContent(/switch active project from DVWA/)
    expect(dialog).toHaveTextContent(/to DVPA-alt/)

    await user.click(screen.getByRole('button', { name: /confirm/i }))
    expect(onConfirm).toHaveBeenCalledOnce()

    await user.click(screen.getByRole('button', { name: /^cancel$/i }))
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('blocked-by-scans form pins pluralized copy and the cancel-scans hint', () => {
    renderModal({ runningScansCount: 2 })

    const dialog = screen.getByRole('dialog', { name: 'switch blocked' })
    expect(dialog).toHaveTextContent(/cannot switch projects while 2 scans are running on DVWA/)
    expect(dialog).toHaveTextContent(
      /cancel running scans on damn vulnerable web app before switching to damn vulnerable platform alt/
    )
  })

  it('blocked-by-triage form pins triage copy and the stop-triage hint', () => {
    renderModal({ triageRunning: true })

    const dialog = screen.getByRole('dialog', { name: 'switch blocked' })
    expect(dialog).toHaveTextContent(/cannot switch projects while AI triage is running on DVWA/)
    expect(dialog).toHaveTextContent(
      /stop the triage process on damn vulnerable web app before switching to damn vulnerable platform alt/
    )
  })
})
