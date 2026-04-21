import { useEffect, useMemo, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { useVirtualizer } from "@tanstack/react-virtual"
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronDown,
  Play,
  Search,
  Wrench,
  X,
} from "lucide-react"
import { useFindings as useFindingsHook } from "@/lib/api"
import { useUI } from "@/lib/store"
import { Panel, SeverityChip } from "@/components/tty"
import { EditableText, EditableSelect } from "@/components/Editable"
import { cn, formatRelative } from "@/lib/utils"
import type { Domain, Finding, Severity, Status } from "@/lib/types"

const DOMAINS: { key: Domain; label: string }[] = [
  { key: "sast", label: "SAST" },
  { key: "web", label: "WEB" },
  { key: "secrets", label: "SECRETS" },
  { key: "sca", label: "SCA" },
]

const SEV_ORDER: Severity[] = ["critical", "high", "medium", "low", "info"]
const SEV_LABEL: Record<Severity, string> = {
  critical: "CRIT",
  high: "HIGH",
  medium: "MED",
  low: "LOW",
  info: "INFO",
}
const SEV_COLOR: Record<Severity, string> = {
  critical: "#ff4d4d",
  high: "#ff8c42",
  medium: "#ffd84d",
  low: "#6bd36b",
  info: "#6ac7ff",
}
const SEV_RANK: Record<Severity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
}

const STATUS_ORDER: Status[] = ["open", "triaged", "fixed", "wontfix", "false_positive"]
const STATUS_LABEL: Record<Status, string> = {
  open: "open",
  triaged: "triaged",
  fixed: "fixed",
  wontfix: "wontfix",
  false_positive: "false-pos",
}
const STATUS_RANK: Record<Status, number> = {
  open: 0,
  triaged: 1,
  fixed: 2,
  wontfix: 3,
  false_positive: 4,
}
const STATUS_COLOR: Record<Status, string> = {
  open: "#ff8c42",
  triaged: "#6ac7ff",
  fixed: "#6bd36b",
  wontfix: "#4a7a4a",
  false_positive: "#4a7a4a",
}

type SortKey =
  | "id"
  | "severity"
  | "title"
  | "tool"
  | "location"
  | "commit"
  | "status"
  | "found"
type SortDir = "asc" | "desc"
type SortState = { key: SortKey; dir: SortDir } | null

type Filters = {
  severity: Set<Severity>
  status: Set<Status>
  tool: Set<string>
  search: string
}
type FilterKey = keyof Filters

const emptyFilters = (): Filters => ({
  severity: new Set(),
  status: new Set(),
  tool: new Set(),
  search: "",
})

// Column grid: checkbox | id | sev | title | tool | location | commit | status | found
const GRID_COLS =
  "grid-cols-[32px_80px_76px_minmax(220px,1fr)_120px_minmax(140px,200px)_90px_110px_90px]"

function locationOf(f: Finding): string {
  return f.file ? `${f.file}:${f.line ?? ""}` : f.target
}

export default function Findings() {
  const domain = useUI((s) => s.findingsDomain)
  const setDomain = useUI((s) => s.setFindingsDomain)
  const activeProjectId = useUI((s) => s.activeProjectId)
  const selectedFindingIds = useUI((s) => s.selectedFindingIds)
  const toggleSelected = useUI((s) => s.toggleSelected)
  const setSelected = useUI((s) => s.setSelected)
  const clearSelected = useUI((s) => s.clearSelected)
  const overrides = useUI((s) => s.findingOverrides)
  const updateFinding = useUI((s) => s.updateFinding)

  const [filters, setFilters] = useState<Filters>(emptyFilters)
  const [sort, setSort] = useState<SortState>(null)
  const [selectedRow, setSelectedRow] = useState<string | null>(null)

  // Reset filters, sort, and selection on project / domain change.
  useEffect(() => {
    setFilters(emptyFilters())
    setSort(null)
    setSelectedRow(null)
    clearSelected()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProjectId, domain])

  // TODO [BACKEND]: This hook returns mock data. Replace with real API call.
  // GET /api/v1/projects/:id/findings
  const { data: baseFindings = [] } = useFindingsHook({ projectId: activeProjectId })

  // Merge in-memory edits (e.g. status, notes) on top of base findings.
  // TODO [BACKEND]: When backend is connected, local overrides should trigger
  // PATCH /api/v1/findings/:id and invalidate the query cache instead of
  // maintaining a separate overrides map.
  const allFindings = useMemo<Finding[]>(
    () =>
      baseFindings.map((f) =>
        overrides[f.id] ? { ...f, ...overrides[f.id] } : f,
      ),
    [baseFindings, overrides],
  )

  const projectFindings = useMemo(
    () => allFindings.filter((f) => f.projectId === activeProjectId),
    [allFindings, activeProjectId],
  )

  const domainCounts = useMemo(() => {
    const m: Record<Domain, number> = { sast: 0, web: 0, secrets: 0, sca: 0 }
    projectFindings.forEach((f) => {
      m[f.domain]++
    })
    return m
  }, [projectFindings])

  const domainFindings = useMemo(
    () => projectFindings.filter((f) => f.domain === domain),
    [projectFindings, domain],
  )

  /**
   * Apply subset of filters. `skip` excludes one filter so that facet
   * counts for that filter are computed against ALL-OTHER filters — this
   * keeps filter options live and in sync with each other.
   */
  const applyFilters = (rows: Finding[], f: Filters, skip?: FilterKey) =>
    rows.filter((r) => {
      if (skip !== "severity" && f.severity.size > 0 && !f.severity.has(r.severity))
        return false
      if (skip !== "status" && f.status.size > 0 && !f.status.has(r.status))
        return false
      if (skip !== "tool" && f.tool.size > 0 && !f.tool.has(r.tool)) return false
      if (skip !== "search" && f.search) {
        const q = f.search.toLowerCase()
        const hay =
          r.title +
          " " +
          r.id +
          " " +
          r.tool +
          " " +
          (r.file ?? "") +
          " " +
          (r.target ?? "") +
          " " +
          (r.commitHash ?? "") +
          " " +
          (r.cwe ?? "")
        if (!hay.toLowerCase().includes(q)) return false
      }
      return true
    })

  const filteredUnsorted = useMemo(
    () => applyFilters(domainFindings, filters),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [domainFindings, filters],
  )

  const filtered = useMemo(() => {
    if (!sort) return filteredUnsorted
    const { key, dir } = sort
    const mul = dir === "asc" ? 1 : -1
    const get = (f: Finding): string | number => {
      switch (key) {
        case "id":
          return f.id
        case "severity":
          return SEV_RANK[f.severity]
        case "title":
          return f.title.toLowerCase()
        case "tool":
          return f.tool
        case "location":
          return locationOf(f).toLowerCase()
        case "commit":
          return f.commitHash ?? "\uFFFF" // push missing to end
        case "status":
          return STATUS_RANK[f.status]
        case "found":
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

  // Faceted counts — respect all other active filters.
  const sevFacets = useMemo(() => {
    const base = applyFilters(domainFindings, filters, "severity")
    const counts: Record<Severity, number> = {
      critical: 0,
      high: 0,
      medium: 0,
      low: 0,
      info: 0,
    }
    base.forEach((r) => counts[r.severity]++)
    return counts
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [domainFindings, filters])

  const statusFacets = useMemo(() => {
    const base = applyFilters(domainFindings, filters, "status")
    const counts: Record<string, number> = {}
    base.forEach((r) => {
      counts[r.status] = (counts[r.status] ?? 0) + 1
    })
    return counts
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [domainFindings, filters])

  const toolFacets = useMemo(() => {
    const base = applyFilters(domainFindings, filters, "tool")
    const counts: Record<string, number> = {}
    base.forEach((r) => {
      counts[r.tool] = (counts[r.tool] ?? 0) + 1
    })
    return counts
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [domainFindings, filters])

  const detail = filtered.find((f) => f.id === selectedRow) ?? null

  const hasAnyFilter =
    filters.severity.size > 0 ||
    filters.status.size > 0 ||
    filters.tool.size > 0 ||
    filters.search.length > 0

  const clearAllFilters = () => setFilters(emptyFilters())

  const showEmptyState = domainFindings.length === 0

  const cycleSort = (key: SortKey) =>
    setSort((prev) => {
      if (!prev || prev.key !== key) return { key, dir: "asc" }
      if (prev.dir === "asc") return { key, dir: "desc" }
      return null
    })

  const toggleSev = (sev: Severity) =>
    setFilters((f) => {
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
            {DOMAINS.map((d) => {
              const active = d.key === domain
              return (
                <button
                  key={d.key}
                  onClick={() => setDomain(d.key)}
                  className={cn(
                    "relative flex items-center gap-2 px-3 h-9 transition-colors",
                    active
                      ? "text-accent bg-muted"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted/50",
                  )}
                  aria-pressed={active}
                >
                  <span className="text-xs font-bold uppercase tracking-[0.2em]">
                    {d.label}
                  </span>
                  <span className="text-[10px] text-dim tabular-nums">
                    ({domainCounts[d.key]})
                  </span>
                  {active && (
                    <span className="absolute left-0 right-0 bottom-0 h-0.5 bg-accent" />
                  )}
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
              {SEV_ORDER.map((sev) => {
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
                      "flex items-center gap-2 px-3 h-9 transition-opacity border-l-2",
                      on ? "bg-muted opacity-100" : "opacity-60 hover:opacity-100 hover:bg-muted/50",
                      disabled && "opacity-20 cursor-not-allowed hover:bg-transparent",
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
              onChange={(e) =>
                setFilters((f) => ({ ...f, search: e.target.value }))
              }
              placeholder="title, id, tool, location, commit, cwe..."
              className="bg-transparent outline-none text-sm flex-1 min-w-0 placeholder:text-dim text-foreground"
              aria-label="Search findings"
            />
            {filters.search && (
              <button
                onClick={() => setFilters((f) => ({ ...f, search: "" }))}
                className="text-dim hover:text-foreground shrink-0"
                aria-label="Clear search"
              >
                <X className="h-4 w-4" />
              </button>
            )}
            <span className="text-[10px] text-dim uppercase tracking-wider hidden xl:inline shrink-0">
              {filters.search ? `matches: ${filteredUnsorted.length}` : "press / to focus"}
            </span>
          </div>
        )}

        {/* Empty-state filler pushes the clear-filters button to the right */}
        {showEmptyState && <div className="flex-1" />}

        {/* Clear-filters pinned to the far right, flush with the section row */}
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
          <span className="text-xs text-accent font-bold">
            {selectedFindingIds.size} selected
          </span>
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
            <EmptyFindingsState domain={domain} />
          ) : (
            <FindingsList
              rows={filtered}
              onSelect={setSelectedRow}
              selectedRowId={selectedRow}
              selectedIds={selectedFindingIds}
              onToggle={toggleSelected}
              onSelectAllFiltered={() => setSelected(filtered.map((r) => r.id))}
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
          <DetailPanel
            finding={detail}
            onUpdate={(patch) => detail && updateFinding(detail.id, patch)}
          />
        </aside>
      </div>
    </div>
  )
}

// --- Empty state ------------------------------------------------------------

function EmptyFindingsState({ domain }: { domain: Domain }) {
  const domainLabel = DOMAINS.find((d) => d.key === domain)?.label ?? domain
  return (
    <div className="flex-1 min-h-0 overflow-auto flex items-start justify-center p-8">
      <div className="w-full max-w-xl border border-border bg-background">
        <div className="border-b border-border px-3 h-8 flex items-center text-xs uppercase tracking-[0.18em] text-primary">
          <span className="text-dim mr-1">[</span>no findings yet
          <span className="text-dim ml-1">]</span>
        </div>
        <div className="p-6 space-y-5 text-xs">
          <div className="text-sm text-foreground leading-relaxed">
            <span className="text-dim">$</span> no{" "}
            <span className="text-accent">{domainLabel}</span> findings for the active
            project.
          </div>
          <div className="text-muted-foreground leading-relaxed">
            this can mean one of a few things:
          </div>
          <ul className="space-y-1.5 text-muted-foreground pl-3">
            <li>
              <span className="text-dim">•</span> no scans have been run yet
            </li>
            <li>
              <span className="text-dim">•</span> scans are still running (enrichment
              can take a while)
            </li>
            <li>
              <span className="text-dim">•</span> scans ran clean — nothing to report
              in this domain
            </li>
          </ul>
          <div className="grid grid-cols-2 gap-2 pt-2">
            <Link
              to="/scans"
              className="flex items-center gap-2 border border-accent text-accent px-3 py-2 hover:bg-muted"
            >
              <Play className="h-3.5 w-3.5" />
              <span className="text-[11px] uppercase tracking-[0.18em] font-bold">
                &gt; view scans
              </span>
            </Link>
            <Link
              to="/config/tools"
              className="flex items-center gap-2 border border-border text-foreground px-3 py-2 hover:bg-muted"
            >
              <Wrench className="h-3.5 w-3.5" />
              <span className="text-[11px] uppercase tracking-[0.18em] font-bold">
                configure tools
              </span>
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}

// --- Findings list ----------------------------------------------------------

function FindingsList({
  rows,
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
}: {
  rows: Finding[]
  onSelect: (id: string) => void
  selectedRowId: string | null
  selectedIds: Set<string>
  onToggle: (id: string) => void
  onSelectAllFiltered: () => void
  onClearAll: () => void
  filters: Filters
  setFilters: (updater: (prev: Filters) => Filters) => void
  toolFacets: Record<string, number>
  statusFacets: Record<string, number>
  sevFacets: Record<Severity, number>
  sort: SortState
  onSort: (key: SortKey) => void
}) {
  const parentRef = useRef<HTMLDivElement>(null)
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 36,
    overscan: 12,
  })

  const allFilteredSelected = rows.length > 0 && rows.every((r) => selectedIds.has(r.id))

  const toolOptions = useMemo(() => {
    const keys = new Set<string>([...Object.keys(toolFacets), ...filters.tool])
    return Array.from(keys)
      .map((k) => ({ value: k, label: k, count: toolFacets[k] ?? 0 }))
      .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
  }, [toolFacets, filters.tool])

  const statusOptions = useMemo(() => {
    const keys = new Set<string>([...Object.keys(statusFacets), ...filters.status])
    return STATUS_ORDER.filter((s) => keys.has(s)).map((s) => ({
      value: s,
      label: STATUS_LABEL[s],
      count: statusFacets[s] ?? 0,
    }))
  }, [statusFacets, filters.status])

  const sevOptions = useMemo(
    () =>
      SEV_ORDER.map((s) => ({
        value: s,
        label: SEV_LABEL[s],
        count: sevFacets[s] ?? 0,
      })),
    [sevFacets],
  )

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      {/* Header row */}
      <div
        className={cn(
          "grid items-center text-[10px] uppercase tracking-[0.18em] text-muted-foreground border-b border-border-strong bg-background px-3 h-9 shrink-0",
          GRID_COLS,
        )}
      >
        <div>
          <input
            type="checkbox"
            aria-label={`Select all ${rows.length} filtered findings`}
            checked={allFilteredSelected}
            onChange={(e) => {
              if (e.target.checked) onSelectAllFiltered()
              else onClearAll()
            }}
            className="accent-[var(--color-accent)]"
          />
        </div>
        <SortHeader label="id" sortKey="id" sort={sort} onSort={onSort} />
        <FilterHeader
          label="sev"
          sortKey="severity"
          sort={sort}
          onSort={onSort}
          activeCount={filters.severity.size}
          options={sevOptions as unknown as FilterOption[]}
          selected={filters.severity as unknown as Set<string>}
          onChange={(next) =>
            setFilters((f) => ({ ...f, severity: next as unknown as Set<Severity> }))
          }
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
          onChange={(next) => setFilters((f) => ({ ...f, tool: next }))}
        />
        <SortHeader label="location" sortKey="location" sort={sort} onSort={onSort} />
        <SortHeader label="commit" sortKey="commit" sort={sort} onSort={onSort} />
        <FilterHeader
          label="status"
          sortKey="status"
          sort={sort}
          onSort={onSort}
          activeCount={filters.status.size}
          options={statusOptions}
          selected={filters.status as unknown as Set<string>}
          onChange={(next) =>
            setFilters((f) => ({ ...f, status: next as unknown as Set<Status> }))
          }
        />
        <SortHeader
          label="found"
          sortKey="found"
          sort={sort}
          onSort={onSort}
          align="right"
        />
      </div>

      {/* Body */}
      <div ref={parentRef} className="flex-1 min-h-0 overflow-auto">
        {rows.length === 0 ? (
          <div className="p-8 text-center text-xs">
            <div className="text-dim mb-1">// no findings match current filters</div>
            <div className="text-muted-foreground">
              try clearing filters or switching domains.
            </div>
          </div>
        ) : (
          <div
            style={{
              height: `${virtualizer.getTotalSize()}px`,
              position: "relative",
              width: "100%",
            }}
          >
            {virtualizer.getVirtualItems().map((v) => {
              const f = rows[v.index]
              const isSelected = selectedIds.has(f.id)
              const isFocused = selectedRowId === f.id
              return (
                <div
                  key={f.id}
                  onClick={() => onSelect(f.id)}
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    height: `${v.size}px`,
                    transform: `translateY(${v.start}px)`,
                  }}
                  className={cn(
                    "grid items-center text-xs px-3 border-b border-border cursor-pointer",
                    GRID_COLS,
                    isFocused ? "bg-muted" : "hover:bg-muted/60",
                    isSelected && "bg-muted/80",
                  )}
                >
                  <div onClick={(e) => e.stopPropagation()}>
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
                  <div className="text-muted-foreground truncate tabular-nums">
                    {locationOf(f)}
                  </div>
                  <div className="tabular-nums">
                    {f.commitHash ? (
                      <span className="text-primary">{f.commitHash}</span>
                    ) : (
                      <span className="text-dim">—</span>
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
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between px-3 h-7 border-t border-border text-[10px] uppercase tracking-wider text-muted-foreground shrink-0">
        <span>
          <span className="text-primary tabular-nums">{rows.length}</span> result
          {rows.length !== 1 ? "s" : ""}
          {selectedIds.size > 0 && (
            <>
              {" "}
              · <span className="text-accent tabular-nums">{selectedIds.size}</span>{" "}
              selected
            </>
          )}
          {sort && (
            <>
              {" "}
              · sorted by{" "}
              <span className="text-foreground">{sort.key}</span>{" "}
              <span className="text-dim">{sort.dir}</span>
            </>
          )}
        </span>
        <span className="text-dim">rows streamed via tanstack-virtual</span>
      </div>
    </div>
  )
}

function StatusCell({ status }: { status: Status }) {
  return (
    <span
      className="text-[11px] uppercase tracking-wider"
      style={{ color: STATUS_COLOR[status] }}
    >
      {STATUS_LABEL[status]}
    </span>
  )
}

// --- Column headers ---------------------------------------------------------

function SortIndicator({ state }: { state: "asc" | "desc" | null }) {
  if (state === "asc") return <ArrowUp className="h-3 w-3 text-accent" />
  if (state === "desc") return <ArrowDown className="h-3 w-3 text-accent" />
  return <ArrowUpDown className="h-3 w-3 text-dim opacity-0 group-hover:opacity-100" />
}

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
  align?: "right"
}) {
  const active = sort?.key === sortKey
  const dir = active ? sort!.dir : null
  return (
    <button
      type="button"
      onClick={() => onSort(sortKey)}
      className={cn(
        "group flex items-center gap-1 text-[10px] uppercase tracking-[0.18em] transition-colors h-full",
        align === "right" && "justify-end",
        active ? "text-accent" : "text-muted-foreground hover:text-foreground",
      )}
    >
      <span>{label}</span>
      <SortIndicator state={dir} />
    </button>
  )
}

type FilterOption = { value: string; label: string; count: number }

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
      if (e.key === "Escape") setOpen(false)
    }
    document.addEventListener("mousedown", onDocClick)
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("mousedown", onDocClick)
      document.removeEventListener("keydown", onKey)
    }
  }, [open])

  const toggle = (v: string) => {
    const next = new Set(selected)
    if (next.has(v)) next.delete(v)
    else next.add(v)
    onChange(next)
  }

  const sortActive = sort?.key === sortKey
  const sortDir = sortActive ? sort!.dir : null
  const hasFilter = activeCount > 0

  return (
    <div ref={ref} className="relative flex items-center gap-1 h-full">
      {/* Click label → sort */}
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className={cn(
          "group flex items-center gap-1 text-[10px] uppercase tracking-[0.18em] transition-colors h-full",
          sortActive || hasFilter
            ? "text-accent"
            : "text-muted-foreground hover:text-foreground",
        )}
      >
        <span>{label}</span>
        <SortIndicator state={sortDir} />
      </button>
      {/* Click ▾ → filter dropdown (separate hit target so sort doesn't trigger) */}
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation()
          setOpen((v) => !v)
        }}
        aria-label={`Filter ${label}`}
        className={cn(
          "flex items-center h-5 px-1 border",
          hasFilter
            ? "border-accent text-accent bg-muted"
            : "border-border text-muted-foreground hover:text-foreground hover:border-border-strong",
        )}
      >
        <ChevronDown className="h-3 w-3" />
        {hasFilter && (
          <span className="ml-0.5 text-[9px] tabular-nums">{activeCount}</span>
        )}
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
            {options.map((opt) => {
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
                  <span className={cn("flex-1", on ? "text-accent" : "text-foreground")}>
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

// --- Detail panel -----------------------------------------------------------

function DetailPanel({
  finding,
  onUpdate,
}: {
  finding: Finding | null
  onUpdate: (patch: Partial<Finding>) => void
}) {
  if (!finding) {
    return (
      <Panel title="detail" className="h-full">
        <div className="p-6 text-xs text-muted-foreground leading-relaxed">
          <div className="text-dim mb-2">// no finding selected</div>
          click a row to inspect it.
        </div>
      </Panel>
    )
  }
  return (
    <Panel
      title={`detail :: ${finding.id}`}
      className="h-full"
      bodyClassName="overflow-auto"
    >
      <div className="p-4 space-y-4 text-xs">
        {/* Header row: editable severity + status, read-only timestamp */}
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
              severity
            </span>
            <EditableSelect<Severity>
              value={finding.severity}
              options={SEV_ORDER.map((s) => ({
                value: s,
                label: SEV_LABEL[s],
                color: SEV_COLOR[s],
              }))}
              onChange={(next) => onUpdate({ severity: next })}
              ariaLabel="Edit severity"
              renderValue={(v) => (
                <span
                  className="uppercase tracking-wider font-bold"
                  style={{ color: SEV_COLOR[v] }}
                >
                  {SEV_LABEL[v]}
                </span>
              )}
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
              status
            </span>
            <EditableSelect<Status>
              value={finding.status}
              options={STATUS_ORDER.map((s) => ({
                value: s,
                label: STATUS_LABEL[s],
                color: STATUS_COLOR[s],
              }))}
              onChange={(next) => onUpdate({ status: next })}
              ariaLabel="Edit status"
              renderValue={(v) => (
                <span
                  className="uppercase tracking-wider"
                  style={{ color: STATUS_COLOR[v] }}
                >
                  {STATUS_LABEL[v]}
                </span>
              )}
            />
          </div>
          <span className="ml-auto text-muted-foreground">
            {formatRelative(finding.discoveredAt)}
          </span>
        </div>

        {/* Editable title */}
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-1 flex items-center gap-2">
            <span>title</span>
            <span className="text-dim normal-case tracking-normal">
              // click to edit
            </span>
          </div>
          <EditableText
            value={finding.title}
            onChange={(next) => onUpdate({ title: next })}
            ariaLabel="Edit finding title"
            valueClassName="text-sm text-primary tty-glow leading-relaxed"
            inputClassName="text-sm"
          />
        </div>

        <Field label="domain" value={finding.domain.toUpperCase()} />
        <Field label="tool" value={finding.tool} />
        <Field label="target" value={finding.target} mono />
        {finding.file && (
          <Field label="file" value={`${finding.file}:${finding.line ?? ""}`} mono />
        )}
        {finding.commitHash && (
          <Field label="commit" value={finding.commitHash} mono accent />
        )}
        {finding.cwe && <Field label="cwe" value={finding.cwe} />}

        {/* Editable notes */}
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-1 flex items-center gap-2">
            <span>notes</span>
            <span className="text-dim normal-case tracking-normal">
              // click to edit
            </span>
          </div>
          <EditableText
            value={finding.notes ?? ""}
            onChange={(next) => onUpdate({ notes: next })}
            multiline
            placeholder="// add triage notes..."
            ariaLabel="Edit notes"
          />
        </div>

        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-2">
            description
          </div>
          <div className="border border-border p-3 text-foreground leading-relaxed bg-muted/30">
            <span className="text-dim">$</span> cat finding/{finding.id}.md
            <br />
            Placeholder description rendered by the FastAPI backend. This field
            will carry full remediation guidance, CVSS vector, references, and
            code context when the real API is wired in.
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 pt-2">
          <button
            onClick={() => onUpdate({ status: "triaged" })}
            className="text-[11px] uppercase tracking-wider py-1.5 border border-accent text-accent hover:bg-muted"
          >
            &gt; triage
          </button>
          <button
            onClick={() => onUpdate({ status: "fixed" })}
            className="text-[11px] uppercase tracking-wider py-1.5 border border-border-strong text-foreground hover:bg-muted"
          >
            mark fixed
          </button>
          <button
            onClick={() => onUpdate({ status: "false_positive" })}
            className="text-[11px] uppercase tracking-wider py-1.5 border border-border text-muted-foreground hover:bg-muted"
          >
            false-pos
          </button>
          <button
            onClick={() => onUpdate({ status: "wontfix" })}
            className="text-[11px] uppercase tracking-wider py-1.5 border border-border text-muted-foreground hover:bg-muted"
          >
            wontfix
          </button>
        </div>
      </div>
    </Panel>
  )
}

function Field({
  label,
  value,
  mono,
  accent,
}: {
  label: string
  value: string
  mono?: boolean
  accent?: boolean
}) {
  return (
    <div className="flex items-baseline gap-3">
      <div className="w-20 shrink-0 text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
        {label}
      </div>
      <div
        className={cn(
          "flex-1",
          mono && "font-mono",
          accent ? "text-primary" : "text-foreground",
        )}
      >
        {value}
      </div>
    </div>
  )
}
