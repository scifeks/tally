import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EditableText, EditableSelect } from '@/components/Editable'

describe('EditableText', () => {
  it('displays value text in viewing mode with no input', () => {
    render(<EditableText value="hello" onChange={vi.fn()} />)
    expect(screen.getByText('hello')).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).toBeNull()
  })

  it('shows input when clicked and the button disappears', async () => {
    const user = userEvent.setup()
    render(<EditableText value="hello" onChange={vi.fn()} />)
    await user.click(screen.getByRole('button'))
    expect(screen.getByRole('textbox')).toBeInTheDocument()
  })

  it('calls onChange with new value on blur when draft differs from original', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(
      <div>
        <EditableText value="original" onChange={onChange} />
        <button>other</button>
      </div>,
    )
    await user.click(screen.getByRole('button', { name: 'Edit' }))
    const input = screen.getByRole('textbox')
    await user.clear(input)
    await user.type(input, 'updated')
    await user.click(screen.getByRole('button', { name: 'other' }))
    expect(onChange).toHaveBeenCalledWith('updated')
  })

  it('calls onChange on Enter key when draft differs from original', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<EditableText value="original" onChange={onChange} />)
    await user.click(screen.getByRole('button'))
    const input = screen.getByRole('textbox')
    await user.clear(input)
    await user.type(input, 'new{Enter}')
    expect(onChange).toHaveBeenCalledWith('new')
  })

  it('reverts without calling onChange on Escape', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<EditableText value="original" onChange={onChange} />)
    await user.click(screen.getByRole('button'))
    const input = screen.getByRole('textbox')
    await user.clear(input)
    await user.type(input, 'changed')
    await user.keyboard('{Escape}')
    expect(onChange).not.toHaveBeenCalled()
    expect(screen.getByText('original')).toBeInTheDocument()
  })

  it('does not call onChange on blur when draft matches original', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(
      <div>
        <EditableText value="same" onChange={onChange} />
        <button>other</button>
      </div>,
    )
    await user.click(screen.getByRole('button', { name: 'Edit' }))
    await user.click(screen.getByRole('button', { name: 'other' }))
    expect(onChange).not.toHaveBeenCalled()
  })

  it('renders placeholder when value is empty string', () => {
    render(<EditableText value="" onChange={vi.fn()} placeholder="type here" />)
    expect(screen.getByText('type here')).toBeInTheDocument()
  })
})

describe('EditableSelect', () => {
  const options = [
    { value: 'active' as const, label: 'active' },
    { value: 'wont_fix' as const, label: 'wont fix' },
    { value: 'fixed' as const, label: 'fixed' },
  ]

  it('displays current value in viewing mode', () => {
    render(<EditableSelect value="active" options={options} onChange={vi.fn()} />)
    expect(screen.getByText('active')).toBeInTheDocument()
    expect(screen.queryByRole('option')).toBeNull()
  })

  it('opens dropdown with all options when clicked', async () => {
    const user = userEvent.setup()
    render(<EditableSelect value="active" options={options} onChange={vi.fn()} />)
    await user.click(screen.getByRole('button'))
    expect(screen.getByText('wont fix')).toBeInTheDocument()
    expect(screen.getByText('fixed')).toBeInTheDocument()
  })

  it('calls onChange with the new value and closes dropdown when an option is clicked', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<EditableSelect value="active" options={options} onChange={onChange} />)
    await user.click(screen.getByRole('button'))
    const fixedBtn = screen.getAllByRole('button').find(b => b.textContent?.includes('fixed'))!
    await user.click(fixedBtn)
    expect(onChange).toHaveBeenCalledWith('fixed')
    expect(screen.queryByText('wont fix')).toBeNull()
  })

  it('closes dropdown without calling onChange on Escape', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<EditableSelect value="active" options={options} onChange={onChange} />)
    await user.click(screen.getByRole('button'))
    expect(screen.getByText('wont fix')).toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(onChange).not.toHaveBeenCalled()
    expect(screen.queryByText('wont fix')).toBeNull()
  })
})
