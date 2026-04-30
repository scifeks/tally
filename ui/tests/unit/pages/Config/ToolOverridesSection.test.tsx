import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ToolOverridesSection } from '@/pages/Config/ToolOverridesSection'
import type { ToolCatalogEntry, ToolOverrideConfig } from '@/lib/types'

const catalog: ToolCatalogEntry[] = [
  { id: 'semgrep', name: 'Semgrep', supportsLocal: true, supportsDocker: true },
  { id: 'gitleaks', name: 'Gitleaks', supportsLocal: true, supportsDocker: true },
  { id: 'katana', name: 'Katana', supportsLocal: true, supportsDocker: false },
]

const overrides: ToolOverrideConfig[] = [
  {
    toolId: 'semgrep',
    type: 'repo',
    location: 'docker',
    container: { name: 'semgrep-runner', toolPath: '/usr/local/bin/semgrep' },
  },
]

function renderSection(
  props: Partial<React.ComponentProps<typeof ToolOverridesSection>> = {}
) {
  return render(
    <ToolOverridesSection
      catalog={catalog}
      overrides={overrides}
      onSave={vi.fn()}
      onDelete={vi.fn()}
      isSaving={false}
      {...props}
    />
  )
}

describe('ToolOverridesSection', () => {
  it('shows guidance when no override is selected', () => {
    renderSection()
    expect(
      screen.getByText(/select a tool override to edit or add a new one/i)
    ).toBeInTheDocument()
  })

  it('only lists tools without an override in the Add dropdown', () => {
    renderSection()
    const addSelect = screen.getAllByRole('combobox').find(el =>
      Array.from((el as HTMLSelectElement).options).some(o => o.text.includes('Add'))
    ) as HTMLSelectElement
    const optionTexts = Array.from(addSelect.options).map(o => o.text)
    expect(optionTexts).toContain('Gitleaks')
    expect(optionTexts).toContain('Katana')
    expect(optionTexts).not.toContain('Semgrep')
  })

  it('populates the form when an existing override is selected', () => {
    renderSection()
    const overrideSelect = screen.getAllByRole('combobox')[0] as HTMLSelectElement
    fireEvent.change(overrideSelect, { target: { value: 'semgrep' } })
    expect(screen.getByText(/overrides global default/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/container name/i)).toHaveValue('semgrep-runner')
    expect(screen.getByLabelText(/tool path in container/i)).toHaveValue(
      '/usr/local/bin/semgrep'
    )
  })

  it('calls onSave with isNew=true for a new override', () => {
    const onSave = vi.fn()
    renderSection({ onSave })
    // Pick from "Add Override" dropdown.
    const addSelect = screen.getAllByRole('combobox').find(el =>
      Array.from((el as HTMLSelectElement).options).some(o => o.text.includes('Add'))
    ) as HTMLSelectElement
    fireEvent.change(addSelect, { target: { value: 'gitleaks' } })
    // Default location is 'local'; fill in path.
    fireEvent.change(screen.getByLabelText(/^path/i), {
      target: { value: '/opt/tools/gitleaks' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^create$/i }))
    expect(onSave).toHaveBeenCalledTimes(1)
    const [override, isNew] = onSave.mock.calls[0]
    expect(isNew).toBe(true)
    expect(override.toolId).toBe('gitleaks')
    expect(override.location).toBe('local')
    expect(override.path).toBe('/opt/tools/gitleaks')
  })

  it('calls onSave with isNew=false when updating an existing override', () => {
    const onSave = vi.fn()
    renderSection({ onSave })
    fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'semgrep' } })
    fireEvent.change(screen.getByLabelText(/tool path in container/i), {
      target: { value: '/new/path' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))
    expect(onSave).toHaveBeenCalledTimes(1)
    const [override, isNew] = onSave.mock.calls[0]
    expect(isNew).toBe(false)
    expect(override.container.toolPath).toBe('/new/path')
  })

  it('confirms before deleting and calls onDelete with the tool id', async () => {
    const onDelete = vi.fn()
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderSection({ onDelete })
    fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'semgrep' } })
    await userEvent.click(screen.getByRole('button', { name: /remove override/i }))
    expect(confirmSpy).toHaveBeenCalled()
    expect(onDelete).toHaveBeenCalledWith('semgrep')
    confirmSpy.mockRestore()
  })

  it('disables Docker mode for tools that do not support it', () => {
    renderSection({ overrides: [] })
    const addSelect = screen.getAllByRole('combobox').find(el =>
      Array.from((el as HTMLSelectElement).options).some(o => o.text.includes('Add'))
    ) as HTMLSelectElement
    fireEvent.change(addSelect, { target: { value: 'katana' } })
    expect(screen.getByRole('button', { name: /docker/i })).toBeDisabled()
    expect(screen.getByText(/does not support docker mode/i)).toBeInTheDocument()
  })
})
