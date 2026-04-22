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
  function getInnerWidth(container: HTMLElement) {
    return (container.querySelector('.bg-primary') as HTMLElement).style.width
  }

  it('renders inner div at 50% width when value=50 and max=100', () => {
    const { container } = render(<Bar value={50} max={100} />)
    expect(getInnerWidth(container)).toBe('50%')
  })

  it('renders inner div at 0% width when value=0', () => {
    const { container } = render(<Bar value={0} max={100} />)
    expect(getInnerWidth(container)).toBe('0%')
  })

  it('renders inner div at 100% width when value=max', () => {
    const { container } = render(<Bar value={100} max={100} />)
    expect(getInnerWidth(container)).toBe('100%')
  })

  it('renders 0% when max is 0 to avoid division by zero', () => {
    const { container } = render(<Bar value={0} max={0} />)
    expect(getInnerWidth(container)).toBe('0%')
  })
})
