import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRef } from 'react'
import { describe, expect, it, vi, beforeAll } from 'vitest'

import { FindingsList } from '@/pages/Findings/FindingsList'
import type { Finding, Severity, Status } from '@/lib/types'
import { emptyFilters, type Filters, type SortState } from '@/pages/Findings/types'

// tanstack-virtual reads the scroll container's size to decide how many
// rows to paint. jsdom returns zero for every measurement and lacks
// ResizeObserver, so the virtualizer renders nothing without these stubs.
beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', {
    configurable: true,
    get() {
      return 600
    },
  })
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
    configurable: true,
    get() {
      return 600
    },
  })
  HTMLElement.prototype.getBoundingClientRect = function () {
    return {
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: 1000,
      bottom: 600,
      width: 1000,
      height: 600,
      toJSON: () => undefined,
    } as DOMRect
  }
  if (typeof globalThis.ResizeObserver === 'undefined') {
    class StubResizeObserver {
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    }
    ;(globalThis as { ResizeObserver?: unknown }).ResizeObserver = StubResizeObserver
  }
})

function makeFinding(overrides: Partial<Finding> = {}): Finding {
  return {
    id: 1,
    projectId: 1,
    segment: 'sast',
    domain: 'code',
    severity: 'high',
    status: 'active',
    confidence: 'high',
    findingType: ['xss'],
    title: 'Reflected XSS',
    tool: 'semgrep',
    target: 'web-api',
    cwe: ['CWE-79'],
    discoveredAt: '2026-04-26T10:00:00Z',
    isLocked: false,
    lockHolder: null,
    ...overrides,
  }
}

interface RenderOverrides {
  rows?: Finding[]
  total?: number
  selectedIds?: Set<number>
  filters?: Filters
  sort?: SortState
  toolFacets?: Record<string, number>
  statusFacets?: Record<string, number>
  sevFacets?: Record<Severity, number>
  onSelect?: (id: number) => void
  onToggle?: (id: number) => void
  onSelectAllFiltered?: () => void
  onClearAll?: () => void
  setFilters?: (updater: (prev: Filters) => Filters) => void
  onSort?: (key: 'severity' | 'title' | 'tool' | 'status' | 'found') => void
  selectedRowId?: number | null
}

function Harness({ overrides }: { overrides: RenderOverrides }) {
  const sentinelRef = useRef<HTMLDivElement | null>(null)
  return (
    <FindingsList
      rows={overrides.rows ?? []}
      total={overrides.total ?? 0}
      onSelect={overrides.onSelect ?? (() => undefined)}
      selectedRowId={overrides.selectedRowId ?? null}
      selectedIds={overrides.selectedIds ?? new Set()}
      onToggle={overrides.onToggle ?? (() => undefined)}
      onSelectAllFiltered={overrides.onSelectAllFiltered ?? (() => undefined)}
      onClearAll={overrides.onClearAll ?? (() => undefined)}
      filters={overrides.filters ?? emptyFilters()}
      setFilters={overrides.setFilters ?? (() => undefined)}
      toolFacets={overrides.toolFacets ?? {}}
      statusFacets={overrides.statusFacets ?? ({} as Record<Status, number>)}
      sevFacets={overrides.sevFacets ?? ({} as Record<Severity, number>)}
      sort={overrides.sort ?? null}
      onSort={overrides.onSort ?? (() => undefined)}
      sentinelRef={sentinelRef}
      isFetchingNextPage={false}
      hasNextPage={false}
    />
  )
}

function renderList(overrides: RenderOverrides = {}) {
  return render(<Harness overrides={overrides} />)
}

async function openFilter(label: string) {
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: `Filter ${label}` }))
  return user
}

function dropdownOptionLabels(label: string): string[] {
  const heading = screen.getByText(`filter by ${label}`)
  const panel = heading.closest('div')!.parentElement!
  return within(panel)
    .getAllByRole('checkbox')
    .map(cb => (cb.parentElement as HTMLLabelElement).textContent?.replace(/\d+$/, '').trim() ?? '')
}

describe('FindingsList - filter dropdown options', () => {
  it('orders tool options by count desc then label asc', async () => {
    renderList({
      toolFacets: { semgrep: 1, gitleaks: 5, dalfox: 5 },
    })
    await openFilter('tool')
    expect(dropdownOptionLabels('tool')).toEqual(['dalfox', 'gitleaks', 'semgrep'])
  })

  it('includes a selected tool with zero facet count', async () => {
    renderList({
      toolFacets: { semgrep: 3 },
      filters: { ...emptyFilters(), tool: new Set(['noir']) },
    })
    await openFilter('tool')
    expect(dropdownOptionLabels('tool')).toEqual(['semgrep', 'noir'])
  })

  it('omits zero-count sev options unless they are explicitly selected', async () => {
    const sevFacets: Record<Severity, number> = {
      critical: 0,
      high: 4,
      medium: 0,
      low: 0,
      informational: 0,
    }

    const { unmount } = renderList({ sevFacets })
    await openFilter('sev')
    expect(dropdownOptionLabels('sev')).toEqual(['HIGH'])
    unmount()

    renderList({
      sevFacets,
      filters: { ...emptyFilters(), severity: new Set<Severity>(['critical']) },
    })
    await openFilter('sev')
    expect(dropdownOptionLabels('sev')).toEqual(['CRIT', 'HIGH'])
  })
})

describe('FindingsList - selection checkboxes', () => {
  it('master checkbox renders checked when every row is in selectedIds', () => {
    const rows = [makeFinding({ id: 1 }), makeFinding({ id: 2 })]
    renderList({ rows, total: 2, selectedIds: new Set([1, 2]) })
    const master = screen.getByRole('checkbox', { name: /select all 2 loaded findings/i })
    expect((master as HTMLInputElement).checked).toBe(true)
  })

  it('master checkbox click calls onClearAll when every row is selected, onSelectAllFiltered otherwise', async () => {
    const rows = [makeFinding({ id: 1 }), makeFinding({ id: 2 })]
    const onClearAll = vi.fn()
    const onSelectAllFiltered = vi.fn()
    const user = userEvent.setup()

    const { unmount } = renderList({
      rows,
      total: 2,
      selectedIds: new Set([1, 2]),
      onClearAll,
      onSelectAllFiltered,
    })
    await user.click(screen.getByRole('checkbox', { name: /select all 2 loaded findings/i }))
    expect(onClearAll).toHaveBeenCalledTimes(1)
    expect(onSelectAllFiltered).not.toHaveBeenCalled()
    unmount()

    renderList({
      rows,
      total: 2,
      selectedIds: new Set(),
      onClearAll,
      onSelectAllFiltered,
    })
    await user.click(screen.getByRole('checkbox', { name: /select all 2 loaded findings/i }))
    expect(onSelectAllFiltered).toHaveBeenCalledTimes(1)
  })

  it('per-row checkbox click forwards the row id to onToggle', async () => {
    const rows = [makeFinding({ id: 42 })]
    const onToggle = vi.fn()
    const user = userEvent.setup()
    renderList({ rows, total: 1, onToggle })

    await user.click(screen.getByRole('checkbox', { name: 'Select 42' }))
    expect(onToggle).toHaveBeenCalledTimes(1)
    expect(onToggle).toHaveBeenCalledWith(42)
  })
})
