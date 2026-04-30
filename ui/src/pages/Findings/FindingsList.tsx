import { useEffect, useMemo, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronDown } from 'lucide-react'
import { SeverityChip } from '@/components/tty'
import { cn, formatRelative } from '@/lib/utils'
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
import type { Filters, FilterOption, SortKey, SortState } from './types'

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

// ─── FilterHeader ─────────────────────────────────────────────────────────────

function FilterHeader({
  label,
  sortKey,
  sort,
  onSort,
  activeCount,
  options,
  selected,
  onChange,
}: {
  label: string
  sortKey: SortKey
  sort: SortState
  onSort: (key: SortKey) => void
  activeCount: number
  options: FilterOption[]
  selected: Set<string>
  onChange: (next: Set<string>) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const toggle = (v: string) => {
    const next = new Set(selected)
    if (next.has(v)) next.delete(v)
    else next.add(v)
    onChange(next)
  }

  const sortActive = sort?.key === sortKey
  const sortDir = sortActive ? (sort?.dir ?? null) : null
  const hasFilter = activeCount > 0

  return (
    <div ref={ref} className="relative flex items-center gap-1 h-full">
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className={cn(
          'group flex items-center gap-1 text-[10px] uppercase tracking-[0.18em] transition-colors h-full',
          sortActive || hasFilter ? 'text-accent' : 'text-muted-foreground hover:text-foreground'
        )}
      >
        <span>{label}</span>
        <SortIndicator state={sortDir} />
      </button>
      <button
        type="button"
        onClick={e => {
          e.stopPropagation()
          setOpen(v => !v)
        }}
        aria-label={`Filter ${label}`}
        className={cn(
          'flex items-center h-5 px-1 border',
          hasFilter
            ? 'border-accent text-accent bg-muted'
            : 'border-border text-muted-foreground hover:text-foreground hover:border-border-strong'
        )}
      >
        <ChevronDown className="h-3 w-3" />
        {hasFilter && <span className="ml-0.5 text-[9px] tabular-nums">{activeCount}</span>}
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 min-w-[200px] max-h-[320px] border border-border-strong bg-background z-30">
          <div className="px-2 py-1.5 border-b border-border text-[10px] uppercase tracking-[0.2em] text-dim flex items-center justify-between">
            <span>filter by {label}</span>
            {selected.size > 0 && (
              <button
                onClick={() => onChange(new Set())}
                className="text-muted-foreground hover:text-accent normal-case tracking-normal"
              >
                clear
              </button>
            )}
          </div>
          <div className="overflow-auto max-h-[272px]">
            {options.length === 0 && (
              <div className="px-3 py-3 text-[11px] text-muted-foreground">
                no options available for current filters
              </div>
            )}
            {options.map(opt => {
              const on = selected.has(opt.value)
              return (
                <label
                  key={opt.value}
                  className="flex items-center gap-2 px-2 py-1.5 text-xs cursor-pointer hover:bg-muted border-b border-border last:border-b-0"
                >
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={() => toggle(opt.value)}
                    className="accent-[var(--color-accent)]"
                  />
                  <span className={cn('flex-1', on ? 'text-accent' : 'text-foreground')}>
                    {opt.label}
                  </span>
                  <span className="text-[10px] tabular-nums text-muted-foreground">
                    {opt.count}
                  </span>
                </label>
              )
            })}
          </div>
        </div>
      )}
    </div>
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
  sentinelRef,
  isFetchingNextPage,
  hasNextPage,
}: {
  rows: Finding[]
  total: number
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
      SEV_ORDER.map(s => ({
        value: s,
        label: SEV_LABEL[s],
        count: sevFacets[s] ?? 0,
      })),
    [sevFacets]
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
          sortKey="severity"
          sort={sort}
          onSort={onSort}
          activeCount={filters.severity.size}
          options={sevOptions as unknown as FilterOption[]}
          selected={filters.severity as unknown as Set<string>}
          onChange={next => setFilters(f => ({ ...f, severity: next as unknown as Set<Severity> }))}
        />
        <SortHeader label="title" sortKey="title" sort={sort} onSort={onSort} />
        <FilterHeader
          label="tool"
          sortKey="tool"
          sort={sort}
          onSort={onSort}
          activeCount={filters.tool.size}
          options={toolOptions}
          selected={filters.tool as Set<string>}
          onChange={next => setFilters(f => ({ ...f, tool: next }))}
        />
        <PlainHeader label="location" />
        <PlainHeader label="cwe" />
        <FilterHeader
          label="status"
          sortKey="status"
          sort={sort}
          onSort={onSort}
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
          <div className="p-8 text-center text-xs">
            <div className="text-dim mb-1">{'// no findings match current filters'}</div>
            <div className="text-muted-foreground">try clearing filters or switching domains.</div>
          </div>
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
              const cweLabel = f.cwe.length > 0 ? f.cwe.join(', ') : '-'
              return (
                <div
                  key={f.id}
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
                    height: `${v.size}px`,
                    transform: `translateY(${v.start}px)`,
                  }}
                  className={cn(
                    'grid items-center text-xs px-3 border-b border-border cursor-pointer',
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
                  <div className="text-foreground truncate pr-3">{f.title}</div>
                  <div className="text-muted-foreground truncate">{f.tool}</div>
                  <div className="text-muted-foreground truncate tabular-nums">{locationOf(f)}</div>
                  <div className="tabular-nums truncate">
                    {f.cwe.length > 0 ? (
                      <span className="text-primary">{cweLabel}</span>
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
