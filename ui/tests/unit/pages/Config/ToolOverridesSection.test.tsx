import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
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

  it('populates the form when an existing override is selected', async () => {
    const user = userEvent.setup()
    renderSection()
    const overrideSelect = screen.getAllByRole('combobox')[0] as HTMLSelectElement
    await user.selectOptions(overrideSelect, 'semgrep')
    expect(screen.getByText(/overrides global default/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/container name/i)).toHaveValue('semgrep-runner')
    expect(screen.getByLabelText(/tool path in container/i)).toHaveValue(
      '/usr/local/bin/semgrep'
    )
  })

  it('calls onSave with isNew=true for a new override', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    renderSection({ onSave })
    const addSelect = screen.getAllByRole('combobox').find(el =>
      Array.from((el as HTMLSelectElement).options).some(o => o.text.includes('Add'))
    ) as HTMLSelectElement
    await user.selectOptions(addSelect, 'gitleaks')
    await user.type(screen.getByLabelText(/^path/i), '/opt/tools/gitleaks')
    await user.click(screen.getByRole('button', { name: /^create$/i }))
    expect(onSave).toHaveBeenCalledTimes(1)
    const [override, isNew] = onSave.mock.calls[0]
    expect(isNew).toBe(true)
    expect(override.toolId).toBe('gitleaks')
    expect(override.location).toBe('local')
    expect(override.path).toBe('/opt/tools/gitleaks')
  })

  it('calls onSave with isNew=false when updating an existing override', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    renderSection({ onSave })
    await user.selectOptions(screen.getAllByRole('combobox')[0], 'semgrep')
    const toolPath = screen.getByLabelText(/tool path in container/i)
    await user.clear(toolPath)
    await user.type(toolPath, '/new/path')
    await user.click(screen.getByRole('button', { name: /^save$/i }))
    expect(onSave).toHaveBeenCalledTimes(1)
    const [override, isNew] = onSave.mock.calls[0]
    expect(isNew).toBe(false)
    expect(override.container.toolPath).toBe('/new/path')
  })

  it('confirms before deleting and calls onDelete with the tool id', async () => {
    const user = userEvent.setup()
    const onDelete = vi.fn()
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderSection({ onDelete })
    await user.selectOptions(screen.getAllByRole('combobox')[0], 'semgrep')
    await user.click(screen.getByRole('button', { name: /remove override/i }))
    expect(confirmSpy).toHaveBeenCalled()
    expect(onDelete).toHaveBeenCalledWith('semgrep')
    confirmSpy.mockRestore()
  })

  it('disables Docker mode for tools that do not support it', async () => {
    const user = userEvent.setup()
    renderSection({ overrides: [] })
    const addSelect = screen.getAllByRole('combobox').find(el =>
      Array.from((el as HTMLSelectElement).options).some(o => o.text.includes('Add'))
    ) as HTMLSelectElement
    await user.selectOptions(addSelect, 'katana')
    expect(screen.getByRole('button', { name: /docker/i })).toBeDisabled()
    expect(screen.getByText(/does not support docker mode/i)).toBeInTheDocument()
  })
})
