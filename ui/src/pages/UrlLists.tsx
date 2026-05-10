import { useEffect, useMemo, useRef, useState } from 'react'
import { Search, X } from 'lucide-react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { cn } from '@/lib/utils'
import { useUI } from '@/lib/store'
import {
  useProjects,
  useUrlLists,
  useUrlListsFilterOptions,
  type UrlListServerFilters,
  type UrlListSortKey,
  type UrlListSortDir,
} from '@/lib/api'
import type { UrlEntry } from '@/lib/types'
import { Panel } from '@/components/tty'
import { NoProjectSelectedState } from '@/components/NoProjectSelectedState'
import { FilterHeader } from '@/components/FilterHeader'
import type { FilterHeaderOption } from '@/components/FilterHeader'

// ─── Filter / sort state ────────────────────────────────────────────────────

type FilterDimension = 'method' | 'protocol' | 'host' | 'port' | 'path' | 'repo'

type UrlListFilters = Record<FilterDimension, Set<string>> & { search: string }

type SortState = { key: UrlListSortKey; dir: UrlListSortDir } | null

const SEARCH_DEBOUNCE_MS = 250

const emptyFilters = (): UrlListFilters => ({
  method: new Set(),
  protocol: new Set(),
  host: new Set(),
  port: new Set(),
  path: new Set(),
  repo: new Set(),
  search: '',
})

const METHOD_COLORS: Record<string, string> = {
  GET: 'var(--color-low)',
  POST: 'var(--color-info)',
  PUT: 'var(--color-med)',
  PATCH: 'var(--color-med)',
  DELETE: 'var(--color-crit)',
  HEAD: 'var(--color-muted-foreground)',
  OPTIONS: 'var(--color-muted-foreground)',
}

// ─── Column config ──────────────────────────────────────────────────────────

interface ColumnDef {
  key: FilterDimension
  label: string
  headerClass: string
  cellClass: string
  render: (u: UrlEntry) => React.ReactNode
}

const COLUMNS: ColumnDef[] = [
  {
    key: 'method',
    label: 'method',
    headerClass: 'w-[90px] shrink-0',
    cellClass: 'w-[90px] shrink-0',
    render: u => (
      <span
        className="inline-flex items-center justify-center h-5 px-1.5 text-[10px] font-bold uppercase tracking-wider border"
        style={{
          color: METHOD_COLORS[u.method] ?? 'var(--color-foreground)',
          borderColor: 'currentColor',
        }}
      >
        {u.method}
      </span>
    ),
  },
  {
    key: 'protocol',
    label: 'protocol',
    headerClass: 'w-[100px] shrink-0',
    cellClass: 'w-[100px] shrink-0 text-muted-foreground uppercase',
    render: u => u.protocol,
  },
  {
    key: 'host',
    label: 'host',
    headerClass: 'flex-1 min-w-[180px]',
    cellClass: 'flex-1 min-w-[180px] truncate',
    render: u => u.host,
  },
  {
    key: 'port',
    label: 'port',
    headerClass: 'w-[70px] shrink-0',
    cellClass: 'w-[70px] shrink-0 text-muted-foreground tabular-nums',
    render: u => String(u.port),
  },
  {
    key: 'path',
    label: 'path',
    headerClass: 'flex-[2] min-w-[240px]',
    cellClass: 'flex-[2] min-w-[240px] truncate text-primary',
    render: u => u.path,
  },
  {
    key: 'repo',
    label: 'repo',
    headerClass: 'w-[160px] shrink-0',
    cellClass: 'w-[160px] shrink-0 text-muted-foreground truncate',
    render: u => u.repoName,
  },
]

// ─── Page ───────────────────────────────────────────────────────────────────

export default function UrlLists() {
  const activeProjectId = useUI(s => s.activeProjectId)
  const { data: projects = [] } = useProjects()
  const projectIdParam = activeProjectId !== null ? String(activeProjectId) : ''

  const [filters, setFilters] = useState<UrlListFilters>(emptyFilters)
  const [sort, setSort] = useState<SortState>(null)
  const [debouncedSearch, setDebouncedSearch] = useState<string>('')

  // Reset filters + sort on project change.
  useEffect(() => {
    setFilters(emptyFilters())
    setSort(null)
  }, [activeProjectId])

  // Debounce the search box so a keystroke storm doesn't refetch on each char.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(filters.search), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(t)
  }, [filters.search])

  const serverFilters: UrlListServerFilters = useMemo(() => {
    const out: UrlListServerFilters = {}
    if (filters.method.size > 0) out.method = Array.from(filters.method)
    if (filters.protocol.size > 0) out.protocol = Array.from(filters.protocol)
    if (filters.host.size > 0) out.host = Array.from(filters.host)
    if (filters.port.size > 0) out.port = Array.from(filters.port).map(p => Number(p))
    if (filters.path.size > 0) out.path = Array.from(filters.path)
    if (filters.repo.size > 0) out.repoId = Array.from(filters.repo).map(r => Number(r))
    if (debouncedSearch) out.search = debouncedSearch
    return out
  }, [filters, debouncedSearch])

  const {
    data: urls,
    total,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useUrlLists(projectIdParam, {
    filters: serverFilters,
    sort: sort?.key,
    order: sort?.dir,
  })

  const filterOptionsQuery = useUrlListsFilterOptions(projectIdParam, serverFilters)

  // Convert filter-options response into FilterHeader-shaped option arrays.
  // Selected values that are no longer in the response must still render so
  // the user can deselect them.
  const optionsByDim = useMemo(() => {
    const data = filterOptionsQuery.data
    const build = (
      apiOptions: { value: string | number; count: number; label?: string }[] | undefined,
      selected: Set<string>,
      formatLabel?: (v: string) => string
    ): FilterHeaderOption[] => {
      const entries = new Map<string, FilterHeaderOption>()
      for (const opt of apiOptions ?? []) {
        const value = String(opt.value)
        const label = opt.label ?? formatLabel?.(value) ?? value
        entries.set(value, { value, label, count: opt.count })
      }
      // Add selected values that didn't come back in the response (count = 0).
      for (const v of selected) {
        if (!entries.has(v)) {
          const label = formatLabel?.(v) ?? v
          entries.set(v, { value: v, label, count: 0 })
        }
      }
      return Array.from(entries.values())
    }
    return {
      method: build(data?.method, filters.method),
      protocol: build(data?.protocol, filters.protocol),
      host: build(data?.host, filters.host),
      port: build(data?.port, filters.port),
      path: build(data?.path, filters.path),
      repo: build(data?.repo, filters.repo),
    }
  }, [filterOptionsQuery.data, filters])

  const cycleSort = (key: UrlListSortKey) =>
    setSort(prev => {
      if (!prev || prev.key !== key) return { key, dir: 'asc' }
      if (prev.dir === 'asc') return { key, dir: 'desc' }
      return null
    })

  const setDimFilter = (dim: FilterDimension, next: Set<string>) =>
    setFilters(f => ({ ...f, [dim]: next }))

  const hasAnyFilter =
    filters.method.size > 0 ||
    filters.protocol.size > 0 ||
    filters.host.size > 0 ||
    filters.port.size > 0 ||
    filters.path.size > 0 ||
    filters.repo.size > 0 ||
    filters.search.length > 0

  const clearAllFilters = () => setFilters(emptyFilters())

  // ─── Virtualized rows ─────────────────────────────────────────────────────
  const scrollRef = useRef<HTMLDivElement>(null)
  const rowVirtualizer = useVirtualizer({
    count: urls.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 32,
    overscan: 12,
  })

  // Infinite-scroll sentinel.
  const sentinelRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = sentinelRef.current
    if (!el) return
    if (!hasNextPage) return
    if (isFetchingNextPage) return
    const obs = new IntersectionObserver(entries => {
      if (entries.some(e => e.isIntersecting)) {
        void fetchNextPage()
      }
    })
    obs.observe(el)
    return () => obs.disconnect()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  if (activeProjectId === null) {
    return <NoProjectSelectedState projects={projects} />
  }

  // The empty-state gate fires only when the unfiltered project has zero URLs.
  // With any filter active we still render the table (which may show "no
  // matches") so the user can adjust filters.
  const showEmptyState = total === 0 && !hasAnyFilter

  return (
    <div className="h-full flex flex-col min-h-0">
      {/* Filter row: server-side search + clear-all */}
      {!showEmptyState && (
        <div className="flex items-stretch h-9 border-b border-border-strong bg-background shrink-0">
          <div className="flex-1 min-w-0 flex items-center gap-2 px-4 focus-within:bg-muted/30 transition-colors">
            <Search className="h-4 w-4 text-accent shrink-0" />
            <span className="text-[10px] uppercase tracking-[0.25em] text-dim font-bold shrink-0">
              <span className="text-accent">[</span>
              <span className="px-1.5">SEARCH</span>
              <span className="text-accent">]</span>
            </span>
            <span className="text-dim shrink-0">/</span>
            <input
              value={filters.search}
              onChange={e => setFilters(f => ({ ...f, search: e.target.value }))}
              placeholder="path substring..."
              className="bg-transparent outline-none text-sm flex-1 min-w-0 placeholder:text-dim text-foreground"
              aria-label="Search URLs"
            />
            {filters.search && (
              <button
                onClick={() => setFilters(f => ({ ...f, search: '' }))}
                className="text-dim hover:text-foreground shrink-0"
                aria-label="Clear search"
              >
                <X className="h-4 w-4" />
              </button>
            )}
            <span className="text-[10px] text-dim uppercase tracking-wider hidden xl:inline shrink-0">
              {urls.length} of {total} loaded
            </span>
          </div>
          {hasAnyFilter && (
            <button
              onClick={clearAllFilters}
              className="shrink-0 flex items-center px-3 h-9 border-l border-border text-[10px] uppercase tracking-wider text-muted-foreground hover:text-accent hover:bg-muted/50 transition-colors"
            >
              clear filters
            </button>
          )}
        </div>
      )}

      {/* Table or empty state */}
      {showEmptyState ? (
        <EmptyState
          title="no urls yet"
          body="This project has no URLs in its URL list. Add entries manually or import a file to populate it before kicking off web scans."
        />
      ) : (
        <Panel className="m-3 flex-1 min-h-0">
          <div className="flex flex-col h-full min-h-0">
            {/* Header row with FilterHeader dropdowns per column */}
            <div className="flex items-center gap-3 px-3 h-8 border-b border-border bg-muted/30 shrink-0">
              {COLUMNS.map(col => (
                <div key={col.key} className={cn('h-full flex items-center', col.headerClass)}>
                  <FilterHeader
                    label={col.label}
                    sortDir={sort?.key === col.key ? sort.dir : null}
                    onSort={() => cycleSort(col.key)}
                    activeCount={filters[col.key].size}
                    options={optionsByDim[col.key]}
                    selected={filters[col.key]}
                    onChange={next => setDimFilter(col.key, next)}
                  />
                </div>
              ))}
            </div>

            {/* Virtualized body */}
            <div ref={scrollRef} className="flex-1 min-h-0 overflow-auto">
              {urls.length === 0 ? (
                <div className="p-6 text-[12px] text-dim italic">
                  no urls match the current filters.
                </div>
              ) : (
                <div
                  style={{
                    height: `${rowVirtualizer.getTotalSize()}px`,
                    position: 'relative',
                  }}
                >
                  {rowVirtualizer.getVirtualItems().map(v => {
                    const u = urls[v.index]
                    return (
                      <div
                        key={u.id}
                        className="absolute left-0 right-0 flex items-center gap-3 px-3 h-8 border-b border-border/50 hover:bg-muted/40 text-xs font-mono"
                        style={{ transform: `translateY(${v.start}px)` }}
                      >
                        {COLUMNS.map(col => (
                          <div key={col.key} className={cn('truncate', col.cellClass)}>
                            {col.render(u)}
                          </div>
                        ))}
                      </div>
                    )
                  })}
                </div>
              )}
              <div ref={sentinelRef} aria-hidden className="h-1" />
            </div>

            {/* Footer status line */}
            <div className="border-t border-border px-3 h-6 flex items-center shrink-0 text-[10px] uppercase tracking-wider text-dim">
              <span>
                {urls.length} of {total} loaded
                {isFetchingNextPage && (
                  <span className="text-muted-foreground ml-2">{'// loading more'}</span>
                )}
                {!isFetchingNextPage && !hasNextPage && total > 0 && (
                  <span className="text-muted-foreground ml-2">{'// end of list'}</span>
                )}
                {sort && (
                  <span className="text-muted-foreground ml-2">
                    {'// sorted by '}
                    {sort.key} {sort.dir}
                  </span>
                )}
              </span>
            </div>
          </div>
        </Panel>
      )}
    </div>
  )
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex-1 p-6 flex items-start justify-center">
      <div className="max-w-xl w-full border border-border bg-background p-6">
        <div className="text-[10px] uppercase tracking-[0.25em] text-dim mb-2">
          <span className="text-accent">[</span>
          <span className="px-1.5">empty</span>
          <span className="text-accent">]</span>
        </div>
        <div className="text-lg text-primary tty-glow mb-2 uppercase tracking-wider">{title}</div>
        <div className="text-xs text-muted-foreground leading-relaxed">{body}</div>
      </div>
    </div>
  )
}
