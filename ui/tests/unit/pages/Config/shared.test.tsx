import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TagInput } from '@/pages/Config/shared'

describe('TagInput', () => {
  it('renders existing tags as chips', () => {
    render(<TagInput value={['react', 'vue']} onChange={vi.fn()} />)
    expect(screen.getByText('react')).toBeInTheDocument()
    expect(screen.getByText('vue')).toBeInTheDocument()
  })

  it('calls onChange without the tag when the remove button is clicked', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<TagInput value={['react', 'vue']} onChange={onChange} />)
    const removeButtons = screen.getAllByRole('button')
    await user.click(removeButtons[0])
    expect(onChange).toHaveBeenCalledWith(['vue'])
  })

  it('calls onChange with new tag appended when Enter is pressed', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<TagInput value={['existing']} onChange={onChange} />)
    await user.type(screen.getByRole('textbox'), 'newtag{Enter}')
    expect(onChange).toHaveBeenCalledWith(['existing', 'newtag'])
  })

  it('clears the input field after Enter', async () => {
    const user = userEvent.setup()
    render(<TagInput value={[]} onChange={vi.fn()} />)
    const input = screen.getByRole('textbox')
    await user.type(input, 'something{Enter}')
    expect(input).toHaveValue('')
  })
})
