import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Search, X } from 'lucide-react'
import {
  useFindings,
  useFindingsCounts,
  useFindingsEvents,
  useFindingsFilterOptions,
  useProjectScanConfig,
  useUpdateFinding,
  type FindingFilters,
  type FindingSortKey,
} from '@/lib/api'
import { FindingMutationErrorModal } from '@/components/FindingMutationErrorModal'
import { NoProjectSelectedState } from '@/components/NoProjectSelectedState'
import { useProjects } from '@/lib/api'
import { useUI } from '@/lib/store'
import { cn } from '@/lib/utils'
import type { Severity } from '@/lib/types'
import { SEV_ORDER, SEV_LABEL, SEV_COLOR } from './constants'
import { emptyFilters } from './types'
import type { Filters, SortKey, SortState } from './types'
import { FindingsList } from './FindingsList'
import { FindingDetailPanel } from './FindingDetailPanel'

const SEARCH_DEBOUNCE_MS = 250

/** Map a UI sort key to the backend `sort=` param. */
const SORT_KEY_TO_SERVER: Record<SortKey, FindingSortKey> = {
  severity: 'severity',
  title: 'title',
  tool: 'tool',
  status: 'status',
  found: 'first_seen',
}

// ─── Findings Page ────────────────────────────────────────────────────────────

export default function Findings() {
  const domain = useUI(s => s.findingsSegment)
  const setDomain = useUI(s => s.setFindingsSegment)
  const activeProjectId = useUI(s => s.activeProjectId)
  const selectedFindingIds = useUI(s => s.selectedFindingIds)
  const toggleSelected = useUI(s => s.toggleSelected)
  const setSelected = useUI(s => s.setSelected)
  const clearSelected = useUI(s => s.clearSelected)

  const { data: projects = [] } = useProjects()

  const [filters, setFilters] = useState<Filters>(emptyFilters)
  const [sort, setSort] = useState<SortState>(null)
  const [selectedRow, setSelectedRow] = useState<number | null>(null)
  const [debouncedSearch, setDebouncedSearch] = useState<string>('')

  // Reset filters, sort, and selection on project / domain change.
  useEffect(() => {
    setFilters(emptyFilters())
    setSort(null)
    setSelectedRow(null)
    clearSelected()
  }, [activeProjectId, domain, clearSelected])

  // Debounce the search box so a fresh query isn't fired on every keystroke.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(filters.search), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(t)
  }, [filters.search])

  const projectIdParam = activeProjectId !== null ? String(activeProjectId) : ''
  const projectIdNum = activeProjectId ?? 0

  const { data: scanConfig } = useProjectScanConfig(projectIdNum)
  const configuredDomains = useMemo(() => scanConfig?.segments ?? [], [scanConfig])

  const { data: counts } = useFindingsCounts(projectIdParam)

  const serverFilters: FindingFilters = useMemo(() => {
    const f: FindingFilters = { segment: [domain] }
    if (filters.severity.size > 0) f.severity = Array.from(filters.severity)
    if (filters.status.size > 0) f.status = Array.from(filters.status)
    if (filters.tool.size > 0) f.tool = Array.from(filters.tool)
    if (debouncedSearch) f.search = debouncedSearch
    if (sort) {
      f.sort = SORT_KEY_TO_SERVER[sort.key]
      f.order = sort.dir
    }
    return f
  }, [domain, filters.severity, filters.status, filters.tool, debouncedSearch, sort])

  // Filter-aware option counts for the severity chips and FilterHeader
  // dropdowns (Phase 12.1). Strict semantics: every count reflects every
  // active filter; zero-count options are dropped by the backend.
  const filterOptionsQuery = useFindingsFilterOptions(projectIdParam, serverFilters)

  const findingsQuery = useFindings({ projectId: projectIdParam, filters: serverFilters })
  const filtered = findingsQuery.data
  const total = findingsQuery.total

  const updateFindingMutation = useUpdateFinding()

  // Subscribe to project-scoped finding_updated SSE events so other tabs /
  // backend mutations land in the cache without a refetch.
  useFindingsEvents(projectIdParam)

  const detail = useMemo(
    () => filtered.find(f => f.id === selectedRow) ?? null,
    [filtered, selectedRow]
  )

  const domainCounts = useMemo(() => {
    const out: Record<string, number> = {}
    for (const d of configuredDomains) {
      out[d] = counts?.bySegment[d] ?? 0
    }
    return out
  }, [counts, configuredDomains])

  const sevFacets = useMemo(() => {
    const empty: Record<Severity, number> = {
      critical: 0,
      high: 0,
      medium: 0,
      low: 0,
      informational: 0,
    }
    const opts = filterOptionsQuery.data?.severity
    if (!opts) return empty
    const out = { ...empty }
    for (const item of opts) out[item.value as Severity] = item.count
    return out
  }, [filterOptionsQuery.data])

  const statusFacets = useMemo(() => {
    const out: Record<string, number> = {}
    for (const item of filterOptionsQuery.data?.status ?? []) {
      out[item.value] = item.count
    }
    return out
  }, [filterOptionsQuery.data])

  const toolFacets = useMemo(() => {
    const out: Record<string, number> = {}
    for (const item of filterOptionsQuery.data?.tool ?? []) {
      out[item.value] = item.count
    }
    return out
  }, [filterOptionsQuery.data])

  const hasAnyFilter =
    filters.severity.size > 0 ||
    filters.status.size > 0 ||
    filters.tool.size > 0 ||
    filters.search.length > 0

  const clearAllFilters = () => setFilters(emptyFilters())

  const cycleSort = (key: SortKey) =>
    setSort(prev => {
      if (!prev || prev.key !== key) return { key, dir: 'asc' }
      if (prev.dir === 'asc') return { key, dir: 'desc' }
      return null
    })

  const toggleSev = (sev: Severity) =>
    setFilters(f => {
      const next = new Set(f.severity)
      if (next.has(sev)) next.delete(sev)
      else next.add(sev)
      return { ...f, severity: next }
    })

  const handleUpdate = useCallback(
    (patch: Parameters<typeof updateFindingMutation.mutate>[0]['patch']) => {
      if (!detail || !activeProjectId) return
      updateFindingMutation.mutate({
        projectId: String(activeProjectId),
        id: detail.id,
        patch,
      })
    },
    [detail, activeProjectId, updateFindingMutation]
  )

  // Infinite-scroll sentinel - when the bottom marker enters the viewport
  // we fetch the next page (if any).
  const sentinelRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = sentinelRef.current
    if (!el) return
    if (!findingsQuery.hasNextPage) return
    if (findingsQuery.isFetchingNextPage) return
    const obs = new IntersectionObserver(entries => {
      if (entries.some(e => e.isIntersecting)) {
        void findingsQuery.fetchNextPage()
      }
    })
    obs.observe(el)
    return () => obs.disconnect()
  }, [findingsQuery])

  if (activeProjectId === null) {
    return <NoProjectSelectedState projects={projects} />
  }

  return (
    <div className="h-full flex flex-col min-h-0">
      <FindingMutationErrorModal />
      {/* Unified filter row: [SEGMENT] + tabs | [SEVERITY] + chips | [SEARCH] + input */}
      <div className="flex items-stretch border-b border-border-strong bg-background shrink-0">
        {/* === SEGMENT SECTION === */}
        <div className="flex items-stretch bg-muted/30">
          <div className="flex items-center px-3 border-r border-border">
            <span className="text-[10px] uppercase tracking-[0.25em] text-dim font-bold">
              <span className="text-accent">[</span>
              <span className="px-1.5">SEGMENT</span>
              <span className="text-accent">]</span>
            </span>
          </div>
          <div className="flex items-stretch divide-x divide-border">
            {configuredDomains.map(d => {
              const active = d === domain
              return (
                <button
                  key={d}
                  onClick={() => setDomain(d)}
                  className={cn(
                    'relative flex items-center gap-2 px-3 h-9 transition-colors',
                    active
                      ? 'text-accent bg-muted'
                      : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                  )}
                  aria-pressed={active}
                >
                  <span className="text-xs font-bold uppercase tracking-[0.2em]">
                    {d.toUpperCase()}
                  </span>
                  <span className="text-[10px] text-dim tabular-nums">({domainCounts[d]})</span>
                  {active && <span className="absolute left-0 right-0 bottom-0 h-0.5 bg-accent" />}
                </button>
              )
            })}
          </div>
        </div>

        {/* === SEVERITY SECTION (40px left margin) === */}
        <div className="flex items-stretch bg-muted/30 ml-10">
          <div className="flex items-center px-3 border-r border-border">
            <span className="text-[10px] uppercase tracking-[0.25em] text-dim font-bold">
              <span className="text-accent">[</span>
              <span className="px-1.5">SEVERITY</span>
              <span className="text-accent">]</span>
            </span>
          </div>
          <div className="flex items-stretch divide-x divide-border">
            {SEV_ORDER.filter(sev => (sevFacets[sev] ?? 0) > 0 || filters.severity.has(sev)).map(
              sev => {
                const count = sevFacets[sev] ?? 0
                const on = filters.severity.has(sev)
                return (
                  <button
                    key={sev}
                    onClick={() => toggleSev(sev)}
                    title={on ? `filtering ${SEV_LABEL[sev]}` : `filter ${SEV_LABEL[sev]}`}
                    className={cn(
                      'flex items-center gap-2 px-3 h-9 transition-opacity border-l-2',
                      on ? 'bg-muted opacity-100' : 'opacity-60 hover:opacity-100 hover:bg-muted/50'
                    )}
                    style={{ borderLeftColor: SEV_COLOR[sev] }}
                    aria-pressed={on}
                  >
                    <span
                      className="text-[11px] font-bold uppercase tracking-[0.2em]"
                      style={{ color: SEV_COLOR[sev] }}
                    >
                      {SEV_LABEL[sev]}
                    </span>
                    <span
                      className="text-[11px] tabular-nums font-bold leading-none"
                      style={{ color: SEV_COLOR[sev] }}
                    >
                      {count}
                    </span>
                  </button>
                )
              }
            )}
          </div>
        </div>

        {/* === SEARCH SECTION (40px left margin) === */}
        <div className="flex-1 min-w-0 flex items-center gap-2 px-4 ml-10 focus-within:bg-muted/30 transition-colors">
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
            placeholder="title, description, tool, location..."
            className="bg-transparent outline-none text-sm flex-1 min-w-0 placeholder:text-dim text-foreground"
            aria-label="Search findings"
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
            {filters.search ? `matches: ${total}` : 'press / to focus'}
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

      {/* Bulk action bar when selection exists */}
      {selectedFindingIds.size > 0 && (
        <div className="flex items-center gap-3 px-4 py-1.5 bg-muted border-b border-accent shrink-0">
          <span className="text-xs text-accent font-bold">{selectedFindingIds.size} selected</span>
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
            of {total} total
          </span>
          <div className="h-4 w-px bg-border-strong" />
          <button className="text-[11px] uppercase tracking-wider px-2 py-0.5 border border-border-strong hover:bg-background">
            &gt; triage
          </button>
          <button className="text-[11px] uppercase tracking-wider px-2 py-0.5 border border-border-strong hover:bg-background">
            mark fixed
          </button>
          <button className="text-[11px] uppercase tracking-wider px-2 py-0.5 border border-border-strong hover:bg-background">
            mark false-pos
          </button>
          <button
            onClick={clearSelected}
            className="ml-auto text-[11px] uppercase tracking-wider text-muted-foreground hover:text-foreground"
          >
            clear
          </button>
        </div>
      )}

      {/* Main split: virtualized list + detail panel */}
      <div className="flex-1 min-h-0 flex">
        <div className="flex-1 min-w-0 flex flex-col">
          <FindingsList
            rows={filtered}
            total={total}
            onSelect={setSelectedRow}
            selectedRowId={selectedRow}
            selectedIds={selectedFindingIds}
            onToggle={toggleSelected}
            onSelectAllFiltered={() => setSelected(filtered.map(r => r.id))}
            onClearAll={clearSelected}
            filters={filters}
            setFilters={setFilters}
            toolFacets={toolFacets}
            statusFacets={statusFacets}
            sevFacets={sevFacets}
            sort={sort}
            onSort={cycleSort}
            sentinelRef={sentinelRef}
            isFetchingNextPage={findingsQuery.isFetchingNextPage}
            hasNextPage={findingsQuery.hasNextPage}
          />
        </div>

        <aside className="hidden xl:flex w-[420px] border-l border-border flex-col shrink-0">
          <FindingDetailPanel finding={detail} onUpdate={handleUpdate} />
        </aside>
      </div>
    </div>
  )
}
