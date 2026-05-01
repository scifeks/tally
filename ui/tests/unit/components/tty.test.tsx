import { render, screen } from '@testing-library/react'
import { SeverityChip, StatusChip, Panel, Bar } from '@/components/tty'

describe('SeverityChip', () => {
  it.each([
    ['critical', 'CRIT'],
    ['high', 'HIGH'],
    ['medium', 'MED'],
    ['low', 'LOW'],
    ['informational', 'INFO'],
  ] as const)('%s renders label "%s"', (severity, label) => {
    render(<SeverityChip severity={severity} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })
})

describe('StatusChip', () => {
  it.each([
    ['active', 'active'],
    ['fixed', 'fixed'],
    ['wont_fix', 'wont fix'],
    ['false_positive', 'false-pos'],
  ] as const)('%s renders label "%s"', (status, label) => {
    render(<StatusChip status={status} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })
})

describe('Panel', () => {
  it('renders title text', () => {
    render(<Panel title="Overview">body</Panel>)
    expect(screen.getByText('Overview')).toBeInTheDocument()
  })

  it('renders children', () => {
    render(<Panel title="T"><span>Child content</span></Panel>)
    expect(screen.getByText('Child content')).toBeInTheDocument()
  })

  it('renders right slot content when right prop is provided', () => {
    render(<Panel title="T" right={<span>42 items</span>}>body</Panel>)
    expect(screen.getByText('42 items')).toBeInTheDocument()
  })
})

describe('Bar', () => {
  it('exposes 50% progress when value=50 and max=100', () => {
    render(<Bar value={50} max={100} />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '50')
  })

  it('exposes 0% progress when value=0', () => {
    render(<Bar value={0} max={100} />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0')
  })

  it('exposes 100% progress when value=max', () => {
    render(<Bar value={100} max={100} />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100')
  })

  it('exposes 0% when max is 0 to avoid division by zero', () => {
    render(<Bar value={0} max={0} />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0')
  })
})
