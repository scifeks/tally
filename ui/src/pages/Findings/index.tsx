import { useEffect, useMemo, useState } from 'react'
import { Search, X } from 'lucide-react'
import { useFindings as useFindingsHook } from '@/lib/api'
import { useUI } from '@/lib/store'
import { cn } from '@/lib/utils'
import type { Segment, Finding, Severity } from '@/lib/types'
import { SEGMENTS, SEV_ORDER, SEV_LABEL, SEV_COLOR } from './constants'
import { emptyFilters } from './types'
import type { Filters, FilterKey, SortKey, SortState } from './types'
import { EmptyFindingsState } from './EmptyFindingsState'
import { FindingsList } from './FindingsList'
import { FindingDetailPanel } from './FindingDetailPanel'

// ─── Pure helpers (module scope — no component state captured) ────────────────

/**
 * Apply subset of filters. `skip` excludes one filter so that facet
 * counts for that filter are computed against ALL-OTHER filters — this
 * keeps filter options live and in sync with each other.
 */
function applyFilters(rows: Finding[], f: Filters, skip?: FilterKey): Finding[] {
  return rows.filter(r => {
    if (skip !== 'severity' && f.severity.size > 0 && !f.severity.has(r.severity)) return false
    if (skip !== 'status' && f.status.size > 0 && !f.status.has(r.status)) return false
    if (skip !== 'tool' && f.tool.size > 0 && !f.tool.has(r.tool)) return false
    if (skip !== 'search' && f.search) {
      const q = f.search.toLowerCase()
      const hay =
        r.title +
        ' ' +
        r.id +
        ' ' +
        r.tool +
        ' ' +
        (r.file ?? '') +
        ' ' +
        (r.target ?? '') +
        ' ' +
        (r.commitHash ?? '') +
        ' ' +
        (r.cwe ?? '')
      if (!hay.toLowerCase().includes(q)) return false
    }
    return true
  })
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
  const overrides = useUI(s => s.findingOverrides)
  const updateFinding = useUI(s => s.updateFinding)

  const [filters, setFilters] = useState<Filters>(emptyFilters)
  const [sort, setSort] = useState<SortState>(null)
  const [selectedRow, setSelectedRow] = useState<string | null>(null)

  // Reset filters, sort, and selection on project / domain change.
  useEffect(() => {
    setFilters(emptyFilters())
    setSort(null)
    setSelectedRow(null)
    clearSelected()
  }, [activeProjectId, domain, clearSelected])

  // TODO [BACKEND]: This hook returns mock data. Replace with real API call.
  // GET /api/v1/projects/:id/findings
  const { data: baseFindings = [] } = useFindingsHook({ projectId: activeProjectId ?? '' })

  // Merge in-memory edits (e.g. status, notes) on top of base findings.
  // TODO [BACKEND]: When backend is connected, local overrides should trigger
  // PATCH /api/v1/findings/:id and invalidate the query cache instead of
  // maintaining a separate overrides map.
  const allFindings = useMemo<Finding[]>(
    () => baseFindings.map(f => (overrides[f.id] ? { ...f, ...overrides[f.id] } : f)),
    [baseFindings, overrides]
  )

  const projectFindings = useMemo(
    () => allFindings.filter(f => f.projectId === activeProjectId),
    [allFindings, activeProjectId]
  )

  const domainCounts = useMemo(() => {
    const m: Record<Segment, number> = { sast: 0, web: 0, secrets: 0, sca: 0 }
    projectFindings.forEach(f => {
      m[f.segment]++
    })
    return m
  }, [projectFindings])

  const domainFindings = useMemo(
    () => projectFindings.filter(f => f.segment === domain),
    [projectFindings, domain]
  )

  const filteredUnsorted = useMemo(
    () => applyFilters(domainFindings, filters),

    [domainFindings, filters]
  )

  const filtered = useMemo(() => {
    if (!sort) return filteredUnsorted
    const { key, dir } = sort
    const mul = dir === 'asc' ? 1 : -1
    const get = (f: Finding): string | number => {
      switch (key) {
        case 'id':
          return f.id
        case 'severity':
          return f.severity
        case 'title':
          return f.title.toLowerCase()
        case 'tool':
          return f.tool
        case 'location':
          return (f.file ? `${f.file}:${f.line ?? ''}` : f.target).toLowerCase()
        case 'commit':
          return f.commitHash ?? '￿'
        case 'status':
          return f.status
        case 'found':
          return new Date(f.discoveredAt).getTime()
      }
    }
    return [...filteredUnsorted].sort((a, b) => {
      const av = get(a)
      const bv = get(b)
      if (av < bv) return -1 * mul
      if (av > bv) return 1 * mul
      return 0
    })
  }, [filteredUnsorted, sort])

  const sevFacets = useMemo(() => {
    const base = applyFilters(domainFindings, filters, 'severity')
    const counts: Record<Severity, number> = {
      critical: 0,
      high: 0,
      medium: 0,
      low: 0,
      informational: 0,
    }
    base.forEach(r => counts[r.severity]++)
    return counts
  }, [domainFindings, filters])

  const statusFacets = useMemo(() => {
    const base = applyFilters(domainFindings, filters, 'status')
    const counts: Record<string, number> = {}
    base.forEach(r => {
      counts[r.status] = (counts[r.status] ?? 0) + 1
    })
    return counts
  }, [domainFindings, filters])

  const toolFacets = useMemo(() => {
    const base = applyFilters(domainFindings, filters, 'tool')
    const counts: Record<string, number> = {}
    base.forEach(r => {
      counts[r.tool] = (counts[r.tool] ?? 0) + 1
    })
    return counts
  }, [domainFindings, filters])

  const detail = filtered.find(f => f.id === selectedRow) ?? null

  const hasAnyFilter =
    filters.severity.size > 0 ||
    filters.status.size > 0 ||
    filters.tool.size > 0 ||
    filters.search.length > 0

  const clearAllFilters = () => setFilters(emptyFilters())

  const showEmptyState = domainFindings.length === 0

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

  return (
    <div className="h-full flex flex-col min-h-0">
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
            {SEGMENTS.map(d => {
              const active = d.key === domain
              return (
                <button
                  key={d.key}
                  onClick={() => setDomain(d.key)}
                  className={cn(
                    'relative flex items-center gap-2 px-3 h-9 transition-colors',
                    active
                      ? 'text-accent bg-muted'
                      : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                  )}
                  aria-pressed={active}
                >
                  <span className="text-xs font-bold uppercase tracking-[0.2em]">{d.label}</span>
                  <span className="text-[10px] text-dim tabular-nums">({domainCounts[d.key]})</span>
                  {active && <span className="absolute left-0 right-0 bottom-0 h-0.5 bg-accent" />}
                </button>
              )
            })}
          </div>
        </div>

        {/* === SEVERITY SECTION (40px left margin) === */}
        {!showEmptyState && (
          <div className="flex items-stretch bg-muted/30 ml-10">
            <div className="flex items-center px-3 border-r border-border">
              <span className="text-[10px] uppercase tracking-[0.25em] text-dim font-bold">
                <span className="text-accent">[</span>
                <span className="px-1.5">SEVERITY</span>
                <span className="text-accent">]</span>
              </span>
            </div>
            <div className="flex items-stretch divide-x divide-border">
              {SEV_ORDER.map(sev => {
                const count = sevFacets[sev] ?? 0
                const on = filters.severity.has(sev)
                const disabled = count === 0 && !on
                return (
                  <button
                    key={sev}
                    disabled={disabled}
                    onClick={() => toggleSev(sev)}
                    title={on ? `filtering ${SEV_LABEL[sev]}` : `filter ${SEV_LABEL[sev]}`}
                    className={cn(
                      'flex items-center gap-2 px-3 h-9 transition-opacity border-l-2',
                      on
                        ? 'bg-muted opacity-100'
                        : 'opacity-60 hover:opacity-100 hover:bg-muted/50',
                      disabled && 'opacity-20 cursor-not-allowed hover:bg-transparent'
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
              })}
            </div>
          </div>
        )}

        {/* === SEARCH SECTION (40px left margin) === */}
        {!showEmptyState && (
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
              placeholder="title, id, tool, location, commit, cwe..."
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
              {filters.search ? `matches: ${filteredUnsorted.length}` : 'press / to focus'}
            </span>
          </div>
        )}

        {showEmptyState && <div className="flex-1" />}

        {hasAnyFilter && !showEmptyState && (
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
            of {filtered.length} filtered
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
          {showEmptyState ? (
            <EmptyFindingsState segment={domain} />
          ) : (
            <FindingsList
              rows={filtered}
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
            />
          )}
        </div>

        <aside className="hidden xl:flex w-[420px] border-l border-border flex-col shrink-0">
          <FindingDetailPanel
            finding={detail}
            onUpdate={patch => detail && updateFinding(detail.id, patch)}
          />
        </aside>
      </div>
    </div>
  )
}
