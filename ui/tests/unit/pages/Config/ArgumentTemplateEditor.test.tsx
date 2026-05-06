import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ArgumentTemplateEditor } from '@/pages/Config/ArgumentTemplateEditor'
import type { ArgumentTemplate } from '@/lib/types'

function makeTemplate(overrides: Partial<ArgumentTemplate> = {}): ArgumentTemplate {
  return {
    id: 'tmpl-1',
    name: 'full-scan',
    arguments: [{ id: 'arg-1', flag: '--verbose', valueType: 'none' }],
    ...overrides,
  }
}

function renderEditor(template: ArgumentTemplate) {
  const onUpdate = vi.fn()
  const onDelete = vi.fn()
  const onClose = vi.fn()
  const utils = render(
    <ArgumentTemplateEditor
      template={template}
      onUpdate={onUpdate}
      onDelete={onDelete}
      onClose={onClose}
    />
  )
  return { ...utils, onUpdate, onDelete, onClose }
}

describe('ArgumentTemplateEditor', () => {
  it('renders the template name in the editable input', () => {
    renderEditor(makeTemplate({ name: 'quick-scan' }))
    expect(screen.getByLabelText(/template name/i)).toHaveValue('quick-scan')
  })

  it('renders the flag, value-type, and value cell for each argument', () => {
    renderEditor(
      makeTemplate({
        arguments: [
          { id: 'a1', flag: '--target', valueType: 'string', value: 'site.com' },
          { id: 'a2', flag: '--config', valueType: 'file', fileName: 'rules.yml' },
        ],
      })
    )
    const flags = screen.getAllByLabelText(/argument flag/i) as HTMLInputElement[]
    expect(flags.map(f => f.value)).toEqual(['--target', '--config'])
    const valueTypes = screen.getAllByLabelText(/value type/i) as HTMLSelectElement[]
    expect(valueTypes.map(v => v.value)).toEqual(['string', 'file'])
    expect(screen.getByLabelText(/argument value/i)).toHaveValue('site.com')
    expect(screen.getByText('rules.yml')).toBeInTheDocument()
  })

  it('shows the boolean-flag hint when valueType is none', () => {
    renderEditor(makeTemplate())
    expect(screen.getByText(/boolean flag/i)).toBeInTheDocument()
  })

  it('calls onUpdate with the new arguments array when a string value is edited', () => {
    const { onUpdate } = renderEditor(
      makeTemplate({
        arguments: [{ id: 'a1', flag: '-q', valueType: 'string', value: 'old' }],
      })
    )
    fireEvent.change(screen.getByLabelText(/argument value/i), {
      target: { value: 'new' },
    })
    expect(onUpdate).toHaveBeenLastCalledWith({
      arguments: [{ id: 'a1', flag: '-q', valueType: 'string', value: 'new' }],
    })
  })

  it('shows the Browse dropzone when a file argument has no fileName', () => {
    renderEditor(
      makeTemplate({ arguments: [{ id: 'a1', flag: '-c', valueType: 'file' }] })
    )
    expect(screen.getByText(/browse/i)).toBeInTheDocument()
  })

  it('shows the filename chip and clears file state when the X is clicked', async () => {
    const user = userEvent.setup()
    const { onUpdate } = renderEditor(
      makeTemplate({
        arguments: [{ id: 'a1', flag: '-c', valueType: 'file', fileName: 'rules.yml' }],
      })
    )
    expect(screen.getByText('rules.yml')).toBeInTheDocument()
    await user.click(screen.getByLabelText(/remove file/i))
    expect(onUpdate).toHaveBeenLastCalledWith({
      arguments: [
        {
          id: 'a1',
          flag: '-c',
          valueType: 'file',
          value: undefined,
          fileName: undefined,
          file: undefined,
        },
      ],
    })
  })

  it('captures the File object on file pick and forwards it to onUpdate', async () => {
    const user = userEvent.setup()
    const { container, onUpdate } = renderEditor(
      makeTemplate({ arguments: [{ id: 'a1', flag: '-c', valueType: 'file' }] })
    )
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    const picked = new File(['rule-bytes'], 'rules.yml', { type: 'text/yaml' })
    await user.upload(fileInput, picked)
    expect(onUpdate).toHaveBeenCalledTimes(1)
    const [payload] = onUpdate.mock.calls[0]
    expect(payload.arguments).toHaveLength(1)
    const updated = payload.arguments[0]
    expect(updated.fileName).toBe('rules.yml')
    expect(updated.value).toBe('')
    expect(updated.file).toBeInstanceOf(File)
    expect(updated.file.name).toBe('rules.yml')
  })

  it('clears value, fileName, and file when the value type is switched', async () => {
    const user = userEvent.setup()
    const { onUpdate } = renderEditor(
      makeTemplate({
        arguments: [
          {
            id: 'a1',
            flag: '-c',
            valueType: 'file',
            fileName: 'rules.yml',
            value: '/old/path',
          },
        ],
      })
    )
    await user.selectOptions(screen.getByLabelText(/value type/i), 'string')
    expect(onUpdate).toHaveBeenLastCalledWith({
      arguments: [
        {
          id: 'a1',
          flag: '-c',
          valueType: 'string',
          value: undefined,
          fileName: undefined,
          file: undefined,
        },
      ],
    })
  })

  it('calls onUpdate with the new name when the template name is edited', () => {
    const { onUpdate } = renderEditor(makeTemplate({ name: 'old-name' }))
    fireEvent.change(screen.getByLabelText(/template name/i), {
      target: { value: 'new-name' },
    })
    expect(onUpdate).toHaveBeenLastCalledWith({ name: 'new-name' })
  })

  it('appends a none-typed argument with a unique id when Add argument is clicked', async () => {
    const user = userEvent.setup()
    const { onUpdate } = renderEditor(makeTemplate())
    await user.click(screen.getByRole('button', { name: /add argument/i }))
    const [payload] = onUpdate.mock.calls[0]
    expect(payload.arguments).toHaveLength(2)
    expect(payload.arguments[1]).toMatchObject({ flag: '', valueType: 'none' })
    expect(payload.arguments[1].id).not.toBe('arg-1')
  })

  it('removes the targeted argument and disables the remove button when only one remains', async () => {
    const user = userEvent.setup()
    const { onUpdate, rerender } = renderEditor(
      makeTemplate({
        arguments: [
          { id: 'a1', flag: '-q', valueType: 'none' },
          { id: 'a2', flag: '-v', valueType: 'none' },
        ],
      })
    )
    const removeButtons = screen.getAllByLabelText(/remove argument/i)
    expect(removeButtons[0]).not.toBeDisabled()
    await user.click(removeButtons[0])
    expect(onUpdate).toHaveBeenLastCalledWith({
      arguments: [{ id: 'a2', flag: '-v', valueType: 'none' }],
    })

    rerender(
      <ArgumentTemplateEditor
        template={makeTemplate({
          arguments: [{ id: 'a2', flag: '-v', valueType: 'none' }],
        })}
        onUpdate={vi.fn()}
        onDelete={vi.fn()}
        onClose={vi.fn()}
      />
    )
    expect(screen.getByLabelText(/remove argument/i)).toBeDisabled()
  })

  it('calls onClose exactly once when Done is clicked', async () => {
    const user = userEvent.setup()
    const { onClose } = renderEditor(makeTemplate())
    await user.click(screen.getByRole('button', { name: /done/i }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('shows the filename text inside the chip container', () => {
    renderEditor(
      makeTemplate({
        arguments: [
          { id: 'a1', flag: '-c', valueType: 'file', fileName: 'long-rules.yml' },
        ],
      })
    )
    const chipText = screen.getByText('long-rules.yml')
    const chip = chipText.closest('div') as HTMLElement
    expect(within(chip).getByLabelText(/remove file/i)).toBeInTheDocument()
  })
})
