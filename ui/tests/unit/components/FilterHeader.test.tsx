import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  FilterHeader,
  type FilterHeaderOption,
  type FilterHeaderProps,
} from '@/components/FilterHeader'

const OPTIONS: FilterHeaderOption[] = [
  { value: 'critical', label: 'critical', count: 12 },
  { value: 'high', label: 'high', count: 7 },
  { value: 'medium', label: 'medium', count: 3 },
]

function renderFilterHeader(overrides: Partial<FilterHeaderProps> = {}) {
  const defaults: FilterHeaderProps = {
    label: 'Severity',
    onSort: vi.fn(),
    sortDir: null,
    activeCount: 0,
    options: OPTIONS,
    selected: new Set(),
    onChange: vi.fn(),
  }
  return render(<FilterHeader {...defaults} {...overrides} />)
}

describe('FilterHeader', () => {
  it('opens the dropdown when the filter button is clicked', async () => {
    const user = userEvent.setup()
    renderFilterHeader()
    expect(screen.queryByText('filter by Severity')).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Filter Severity' }))
    expect(screen.getByText('filter by Severity')).toBeInTheDocument()
  })

  it('closes the dropdown when an outside element is clicked', async () => {
    const user = userEvent.setup()
    render(
      <>
        <FilterHeader
          label="Severity"
          onSort={vi.fn()}
          sortDir={null}
          activeCount={0}
          options={OPTIONS}
          selected={new Set()}
          onChange={vi.fn()}
        />
        <button>outside</button>
      </>,
    )
    await user.click(screen.getByRole('button', { name: 'Filter Severity' }))
    expect(screen.getByText('filter by Severity')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'outside' }))
    expect(screen.queryByText('filter by Severity')).toBeNull()
  })

  it('closes the dropdown when Escape is pressed', async () => {
    const user = userEvent.setup()
    renderFilterHeader()
    await user.click(screen.getByRole('button', { name: 'Filter Severity' }))
    expect(screen.getByText('filter by Severity')).toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(screen.queryByText('filter by Severity')).toBeNull()
  })

  it('calls onSort when the label sort button is clicked', async () => {
    const onSort = vi.fn()
    const user = userEvent.setup()
    renderFilterHeader({ onSort })
    await user.click(screen.getByRole('button', { name: 'Severity' }))
    expect(onSort).toHaveBeenCalledOnce()
  })

  it('renders the active-count badge when activeCount > 0', () => {
    renderFilterHeader({ activeCount: 3 })
    const filterButton = screen.getByRole('button', { name: 'Filter Severity' })
    expect(filterButton).toHaveTextContent('3')
  })
})
