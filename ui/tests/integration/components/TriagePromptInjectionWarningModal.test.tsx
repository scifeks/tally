import { describe, expect, it, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TriagePromptInjectionWarningModal } from '@/components/TriagePromptInjectionWarningModal'
import { useUI } from '@/lib/store'

describe('TriagePromptInjectionWarningModal', () => {
  beforeEach(() => {
    useUI.setState({ triageInjectionAcked: false })
  })

  it('does not render when open is false', () => {
    const onAccept = vi.fn()
    const onCancel = vi.fn()
    render(
      <TriagePromptInjectionWarningModal
        open={false}
        onAccept={onAccept}
        onCancel={onCancel}
        providerLabel="Claude Code"
      />
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders the warning copy when open', () => {
    render(
      <TriagePromptInjectionWarningModal
        open={true}
        onAccept={vi.fn()}
        onCancel={vi.fn()}
        providerLabel="Claude Code"
      />
    )
    const dialog = screen.getByRole('dialog')
    expect(dialog).toBeInTheDocument()
    expect(dialog).toHaveAttribute('aria-label', 'prompt injection risk')
    expect(screen.getByText(/prompt injection risk/i)).toBeInTheDocument()
    expect(screen.getByText(/triage sends finding metadata/i)).toBeInTheDocument()
    expect(screen.getByText(/accept & continue/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
  })

  it('persists triageInjectionAcked and fires onAccept when the user accepts', async () => {
    const user = userEvent.setup()
    const onAccept = vi.fn()
    const onCancel = vi.fn()
    render(
      <TriagePromptInjectionWarningModal
        open={true}
        onAccept={onAccept}
        onCancel={onCancel}
        providerLabel="Claude Code"
      />
    )
    await user.click(screen.getByRole('button', { name: /accept & continue/i }))
    expect(useUI.getState().triageInjectionAcked).toBe(true)
    expect(onAccept).toHaveBeenCalledTimes(1)
    expect(onCancel).not.toHaveBeenCalled()
  })

  it('does not set the ack flag when the user cancels', async () => {
    const user = userEvent.setup()
    const onAccept = vi.fn()
    const onCancel = vi.fn()
    render(
      <TriagePromptInjectionWarningModal
        open={true}
        onAccept={onAccept}
        onCancel={onCancel}
        providerLabel="Claude Code"
      />
    )
    await user.click(screen.getByRole('button', { name: /^cancel$/i }))
    expect(useUI.getState().triageInjectionAcked).toBe(false)
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onAccept).not.toHaveBeenCalled()
  })

  it('treats Escape as cancel (no ack mutation)', async () => {
    const user = userEvent.setup()
    const onAccept = vi.fn()
    const onCancel = vi.fn()
    render(
      <TriagePromptInjectionWarningModal
        open={true}
        onAccept={onAccept}
        onCancel={onCancel}
        providerLabel="Claude Code"
      />
    )
    await user.keyboard('{Escape}')
    expect(useUI.getState().triageInjectionAcked).toBe(false)
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onAccept).not.toHaveBeenCalled()
  })

  it('renders the configured provider label in the warning text', () => {
    render(
      <TriagePromptInjectionWarningModal
        open={true}
        providerLabel="OpenCode (Ollama)"
        onAccept={vi.fn()}
        onCancel={vi.fn()}
      />
    )
    expect(screen.getAllByText(/OpenCode \(Ollama\)/)).toHaveLength(2)
  })

  it('falls back to "the triage agent" when providerLabel is null', () => {
    render(
      <TriagePromptInjectionWarningModal
        open={true}
        providerLabel={null}
        onAccept={vi.fn()}
        onCancel={vi.fn()}
      />
    )
    expect(screen.getAllByText(/the triage agent/)).toHaveLength(2)
  })
})
