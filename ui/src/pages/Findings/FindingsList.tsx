import { useMemo, useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react'
import { SeverityChip } from '@/components/tty'
import { FilterHeader } from '@/components/FilterHeader'
import type { FilterHeaderOption } from '@/components/FilterHeader'
import { cn, findingTitle, formatRelative } from '@/lib/utils'
import type { Finding, Severity, Status } from '@/lib/types'
import {
  GRID_COLS,
  SEV_ORDER,
  SEV_LABEL,
  STATUS_ORDER,
  STATUS_LABEL,
  STATUS_COLOR,
  locationOf,
} from './constants'
import type { Filters, SortKey, SortState } from './types'

// ─── StatusCell ───────────────────────────────────────────────────────────────

function StatusCell({ status }: { status: Status }) {
  return (
    <span className="text-[11px] uppercase tracking-wider" style={{ color: STATUS_COLOR[status] }}>
      {STATUS_LABEL[status]}
    </span>
  )
}

// ─── SortIndicator ────────────────────────────────────────────────────────────

function SortIndicator({ state }: { state: 'asc' | 'desc' | null }) {
  if (state === 'asc') return <ArrowUp className="h-3 w-3 text-accent" />
  if (state === 'desc') return <ArrowDown className="h-3 w-3 text-accent" />
  return <ArrowUpDown className="h-3 w-3 text-dim opacity-0 group-hover:opacity-100" />
}

// ─── SortHeader ───────────────────────────────────────────────────────────────

function SortHeader({
  label,
  sortKey,
  sort,
  onSort,
  align,
}: {
  label: string
  sortKey: SortKey
  sort: SortState
  onSort: (key: SortKey) => void
  align?: 'right'
}) {
  const active = sort?.key === sortKey
  const dir = active ? (sort?.dir ?? null) : null
  return (
    <button
      type="button"
      onClick={() => onSort(sortKey)}
      className={cn(
        'group flex items-center gap-1 text-[10px] uppercase tracking-[0.18em] transition-colors h-full',
        align === 'right' && 'justify-end',
        active ? 'text-accent' : 'text-muted-foreground hover:text-foreground'
      )}
    >
      <span>{label}</span>
      <SortIndicator state={dir} />
    </button>
  )
}

// ─── PlainHeader ──────────────────────────────────────────────────────────────
// Header for columns that aren't server-sortable. Replaces the sortable
// affordance for `id`, `location`, and `cwe` (which would only sort the
// currently-loaded page client-side and mislead the user).

function PlainHeader({ label, align }: { label: string; align?: 'right' }) {
  return (
    <span
      className={cn(
        'text-[10px] uppercase tracking-[0.18em] text-muted-foreground h-full inline-flex items-center',
        align === 'right' && 'justify-end'
      )}
    >
      {label}
    </span>
  )
}

// ─── FindingsList ─────────────────────────────────────────────────────────────

export function FindingsList({
  rows,
  total,
  onSelect,
  selectedRowId,
  selectedIds,
  onToggle,
  onSelectAllFiltered,
  onClearAll,
  filters,
  setFilters,
  toolFacets,
  statusFacets,
  sevFacets,
  sort,
  onSort,
  unfilteredTotal,
  sentinelRef,
  isFetchingNextPage,
  hasNextPage,
}: {
  rows: Finding[]
  total: number
  unfilteredTotal: number
  onSelect: (id: number) => void
  selectedRowId: number | null
  selectedIds: Set<number>
  onToggle: (id: number) => void
  onSelectAllFiltered: () => void
  onClearAll: () => void
  filters: Filters
  setFilters: (updater: (prev: Filters) => Filters) => void
  toolFacets: Record<string, number>
  statusFacets: Record<string, number>
  sevFacets: Record<Severity, number>
  sort: SortState
  onSort: (key: SortKey) => void
  sentinelRef: React.RefObject<HTMLDivElement | null>
  isFetchingNextPage: boolean
  hasNextPage: boolean
}) {
  const parentRef = useRef<HTMLDivElement>(null)
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 36,
    overscan: 12,
    measureElement: el => el.getBoundingClientRect().height,
  })

  const allFilteredSelected = rows.length > 0 && rows.every(r => selectedIds.has(r.id))

  const toolOptions = useMemo(() => {
    const keys = new Set<string>([...Object.keys(toolFacets), ...filters.tool])
    return Array.from(keys)
      .map(k => ({ value: k, label: k, count: toolFacets[k] ?? 0 }))
      .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
  }, [toolFacets, filters.tool])

  const statusOptions = useMemo(() => {
    const keys = new Set<string>([...Object.keys(statusFacets), ...filters.status])
    return STATUS_ORDER.filter(s => keys.has(s)).map(s => ({
      value: s,
      label: STATUS_LABEL[s],
      count: statusFacets[s] ?? 0,
    }))
  }, [statusFacets, filters.status])

  const sevOptions = useMemo(
    () =>
      SEV_ORDER.filter(s => (sevFacets[s] ?? 0) > 0 || filters.severity.has(s)).map(s => ({
        value: s,
        label: SEV_LABEL[s],
        count: sevFacets[s] ?? 0,
      })),
    [sevFacets, filters.severity]
  )

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      {/* Header row */}
      <div
        className={cn(
          'grid items-center text-[10px] uppercase tracking-[0.18em] text-muted-foreground border-b border-border-strong bg-background px-3 h-9 shrink-0',
          GRID_COLS
        )}
      >
        <div>
          <input
            type="checkbox"
            aria-label={`Select all ${rows.length} loaded findings`}
            checked={allFilteredSelected}
            onChange={e => {
              if (e.target.checked) onSelectAllFiltered()
              else onClearAll()
            }}
            className="accent-[var(--color-accent)]"
          />
        </div>
        <PlainHeader label="id" />
        <FilterHeader
          label="sev"
          sortDir={sort?.key === 'severity' ? sort.dir : null}
          onSort={() => onSort('severity')}
          activeCount={filters.severity.size}
          options={sevOptions as unknown as FilterHeaderOption[]}
          selected={filters.severity as unknown as Set<string>}
          onChange={next => setFilters(f => ({ ...f, severity: next as unknown as Set<Severity> }))}
        />
        <SortHeader label="title" sortKey="title" sort={sort} onSort={onSort} />
        <FilterHeader
          label="tool"
          sortDir={sort?.key === 'tool' ? sort.dir : null}
          onSort={() => onSort('tool')}
          activeCount={filters.tool.size}
          options={toolOptions}
          selected={filters.tool as Set<string>}
          onChange={next => setFilters(f => ({ ...f, tool: next }))}
        />
        <PlainHeader label="repo" />
        <PlainHeader label="location" />
        <PlainHeader label="cwe" />
        <FilterHeader
          label="status"
          sortDir={sort?.key === 'status' ? sort.dir : null}
          onSort={() => onSort('status')}
          activeCount={filters.status.size}
          options={statusOptions}
          selected={filters.status as unknown as Set<string>}
          onChange={next => setFilters(f => ({ ...f, status: next as unknown as Set<Status> }))}
        />
        <SortHeader label="found" sortKey="found" sort={sort} onSort={onSort} align="right" />
      </div>

      {/* Body */}
      <div ref={parentRef} className="flex-1 min-h-0 overflow-auto">
        {rows.length === 0 ? (
          unfilteredTotal === 0 ? (
            <div className="p-8 text-center text-xs">
              <div className="text-dim mb-1">{'// no findings yet'}</div>
              <div className="text-muted-foreground">run a scan to populate this list.</div>
            </div>
          ) : (
            <div className="p-8 text-center text-xs">
              <div className="text-dim mb-1">{'// no findings match current filters'}</div>
              <div className="text-muted-foreground">
                try clearing filters or switching domains.
              </div>
            </div>
          )
        ) : (
          <div
            style={{
              height: `${virtualizer.getTotalSize()}px`,
              position: 'relative',
              width: '100%',
            }}
          >
            {virtualizer.getVirtualItems().map(v => {
              const f = rows[v.index]
              const isSelected = selectedIds.has(f.id)
              const isFocused = selectedRowId === f.id
              return (
                <div
                  key={f.id}
                  ref={virtualizer.measureElement}
                  data-index={v.index}
                  role="button"
                  tabIndex={0}
                  onClick={() => onSelect(f.id)}
                  onKeyDown={e => {
                    if (e.key === 'Enter' || e.key === ' ') onSelect(f.id)
                  }}
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    transform: `translateY(${v.start}px)`,
                  }}
                  className={cn(
                    'grid items-center text-xs px-3 border-b border-border cursor-pointer min-h-9',
                    GRID_COLS,
                    isFocused ? 'bg-muted' : 'hover:bg-muted/60',
                    isSelected && 'bg-muted/80'
                  )}
                >
                  <div role="presentation" onClick={e => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      aria-label={`Select ${f.id}`}
                      checked={isSelected}
                      onChange={() => onToggle(f.id)}
                      className="accent-[var(--color-accent)]"
                    />
                  </div>
                  <div className="text-dim tabular-nums">{f.id}</div>
                  <div>
                    <SeverityChip severity={f.severity} />
                  </div>
                  <div className="text-foreground truncate pr-3">{findingTitle(f)}</div>
                  <div className="text-muted-foreground truncate">{f.tool}</div>
                  <div className="text-muted-foreground truncate">{f.repoName}</div>
                  <div className="text-muted-foreground truncate tabular-nums">{locationOf(f)}</div>
                  <div className="flex flex-wrap gap-x-1 gap-y-0.5 py-1 tabular-nums">
                    {f.cwe.length > 0 ? (
                      f.cwe.map(c => (
                        <span key={c} className="text-primary">
                          {c}
                        </span>
                      ))
                    ) : (
                      <span className="text-dim">-</span>
                    )}
                  </div>
                  <div>
                    <StatusCell status={f.status} />
                  </div>
                  <div className="text-right text-muted-foreground tabular-nums">
                    {formatRelative(f.discoveredAt)}
                  </div>
                </div>
              )
            })}
          </div>
        )}
        {/* Infinite-scroll sentinel sits below the virtualized body. */}
        <div ref={sentinelRef} className="h-px" aria-hidden />
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between px-3 h-7 border-t border-border text-[10px] uppercase tracking-wider text-muted-foreground shrink-0">
        <span>
          <span className="text-primary tabular-nums">{rows.length}</span> of{' '}
          <span className="text-foreground tabular-nums">{total}</span> loaded
          {selectedIds.size > 0 && (
            <>
              {' '}
              · <span className="text-accent tabular-nums">{selectedIds.size}</span> selected
            </>
          )}
          {sort && (
            <>
              {' '}
              · sorted by <span className="text-foreground">{sort.key}</span>{' '}
              <span className="text-dim">{sort.dir}</span>
            </>
          )}
          {isFetchingNextPage && (
            <>
              {' '}
              · <span className="text-accent">loading more…</span>
            </>
          )}
          {!hasNextPage && rows.length > 0 && rows.length === total && (
            <>
              {' '}
              · <span className="text-dim">end of list</span>
            </>
          )}
        </span>
        <span className="text-dim">rows streamed via tanstack-virtual</span>
      </div>
    </div>
  )
}
