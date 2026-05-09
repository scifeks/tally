import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { StaleSavedScanModal } from '@/components/StaleSavedScanModal'
import type { StaleSavedScanItem } from '@/components/StaleSavedScanModal'

function renderModal(items: StaleSavedScanItem[], open = true, onDismiss = vi.fn()) {
  return render(<StaleSavedScanModal open={open} staleItems={items} onDismiss={onDismiss} />)
}

describe('StaleSavedScanModal', () => {
  it('renders a stale repo item with its name', () => {
    renderModal([{ kind: 'repo', id: 5, name: 'old-repo' }])
    expect(screen.getByText('repo: old-repo')).toBeInTheDocument()
  })

  it('falls back to id when repo name is missing', () => {
    renderModal([{ kind: 'repo', id: 7 }])
    expect(screen.getByText('repo: id 7')).toBeInTheDocument()
  })

  it('renders a stale tool item', () => {
    renderModal([{ kind: 'tool', name: 'osv-scanner' }])
    expect(screen.getByText('tool: osv-scanner')).toBeInTheDocument()
  })

  it('renders a stale arg-profile item', () => {
    renderModal([{ kind: 'argProfile', id: 4 }])
    expect(screen.getByText('arg profile: id 4')).toBeInTheDocument()
  })

  it('renders all three kinds together', () => {
    renderModal([
      { kind: 'repo', id: 1, name: 'php-goof' },
      { kind: 'tool', name: 'osv-scanner' },
      { kind: 'argProfile', id: 4 },
    ])
    expect(screen.getByText('repo: php-goof')).toBeInTheDocument()
    expect(screen.getByText('tool: osv-scanner')).toBeInTheDocument()
    expect(screen.getByText('arg profile: id 4')).toBeInTheDocument()
  })

  it('calls onDismiss when the dismiss button is clicked', async () => {
    const onDismiss = vi.fn()
    renderModal([{ kind: 'tool', name: 'semgrep' }], true, onDismiss)
    await userEvent.click(screen.getByRole('button', { name: /dismiss/i }))
    expect(onDismiss).toHaveBeenCalledOnce()
  })

  it('does not render the modal title when open is false', () => {
    renderModal([{ kind: 'tool', name: 'semgrep' }], false)
    expect(screen.queryByText(/saved scan is stale/i)).not.toBeInTheDocument()
  })
})
