import { useMemo, useRef, useState } from "react"
import { Search, X, ChevronUp, ChevronDown } from "lucide-react"
import { useVirtualizer } from "@tanstack/react-virtual"
import { cn } from "@/lib/utils"
import { useUI } from "@/lib/store"
import { useUrlLists, useUrlListEntries } from "@/lib/api"
import type { UrlEntry } from "@/lib/types"
import { Panel } from "@/components/tty"

// ─── Column config ──────────────────────────────────────────────────────────
// Add a column later by pushing another entry here. `cellClass` controls the
// column width; `render` is optional (defaults to stringified value).
// `sortValue` lets a column sort on something different from what's displayed
// (e.g. numeric port even though we format it).

type SortDir = "asc" | "desc" | null
type ColumnKey = "method" | "protocol" | "host" | "port" | "path"

interface ColumnDef {
  key: ColumnKey
  label: string
  /** Width + alignment classes applied to both header and cell. */
  cellClass: string
  /** How to pull the sort-comparable value for this row. */
  sortValue: (u: UrlEntry) => string | number
  /** How to render the cell. Defaults to the raw field. */
  render?: (u: UrlEntry) => React.ReactNode
}

const METHOD_COLORS: Record<string, string> = {
  GET: "var(--color-low)",
  POST: "var(--color-info)",
  PUT: "var(--color-med)",
  PATCH: "var(--color-med)",
  DELETE: "var(--color-crit)",
  HEAD: "var(--color-muted-foreground)",
  OPTIONS: "var(--color-muted-foreground)",
}

const COLUMNS: ColumnDef[] = [
  {
    key: "method",
    label: "METHOD",
    cellClass: "w-[90px] shrink-0",
    sortValue: (u) => u.method,
    render: (u) => (
      <span
        className="inline-flex items-center justify-center h-5 px-1.5 text-[10px] font-bold uppercase tracking-wider border"
        style={{ color: METHOD_COLORS[u.method] ?? "var(--color-foreground)", borderColor: "currentColor" }}
      >
        {u.method}
      </span>
    ),
  },
  {
    key: "protocol",
    label: "PROTO",
    cellClass: "w-[70px] shrink-0 text-muted-foreground uppercase",
    sortValue: (u) => u.protocol,
  },
  {
    key: "host",
    label: "HOST",
    cellClass: "flex-1 min-w-[180px] truncate",
    sortValue: (u) => u.host,
  },
  {
    key: "port",
    label: "PORT",
    cellClass: "w-[70px] shrink-0 text-muted-foreground tabular-nums",
    sortValue: (u) => u.port,
  },
  {
    key: "path",
    label: "PATH",
    cellClass: "flex-[2] min-w-[240px] truncate text-primary",
    sortValue: (u) => u.path,
  },
]

// ─── Page ───────────────────────────────────────────────────────────────────

export default function UrlLists() {
  const activeProjectId = useUI((s) => s.activeProjectId)

  // TODO [BACKEND]: These hooks return mock data. Replace with real API calls.
  // GET /api/v1/projects/:id/url-lists
  const { data: urlLists = [] } = useUrlLists(activeProjectId)

  const projectLists = useMemo(
    () => urlLists.filter((l) => l.projectId === activeProjectId),
    [urlLists, activeProjectId],
  )

  const [activeListId, setActiveListId] = useState<string | null>(
    projectLists[0]?.id ?? null,
  )

  // If project changes and current list no longer belongs to it, reset.
  useMemo(() => {
    if (activeListId && !projectLists.some((l) => l.id === activeListId)) {
      setActiveListId(projectLists[0]?.id ?? null)
    }
  }, [activeListId, projectLists])

  const activeList = projectLists.find((l) => l.id === activeListId) ?? null

  // TODO [BACKEND]: Get URL entries for the active list.
  // GET /api/v1/url-lists/:id/entries
  const { data: urls = [] } = useUrlListEntries(activeListId ?? "")

  const [search, setSearch] = useState("")
  const [sortKey, setSortKey] = useState<ColumnKey | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>(null)

  // URLs in the active list, filtered by search.
  const listUrls = useMemo(
    () => (activeList ? urls.filter((u) => u.urlListId === activeList.id) : []),
    [activeList, urls],
  )

  const filtered = useMemo(() => {
    if (!search.trim()) return listUrls
    const q = search.toLowerCase()
    return listUrls.filter((u) => {
      return (
        u.method.toLowerCase().includes(q) ||
        u.protocol.toLowerCase().includes(q) ||
        u.host.toLowerCase().includes(q) ||
        u.path.toLowerCase().includes(q) ||
        String(u.port).includes(q) ||
        u.id.toLowerCase().includes(q)
      )
    })
  }, [listUrls, search])

  // Apply sort only if user clicked a header. Otherwise preserve insertion
  // order (i.e. whatever the API returned).
  const sorted = useMemo(() => {
    if (!sortKey || !sortDir) return filtered
    const col = COLUMNS.find((c) => c.key === sortKey)
    if (!col) return filtered
    const mul = sortDir === "asc" ? 1 : -1
    return [...filtered].sort((a, b) => {
      const va = col.sortValue(a)
      const vb = col.sortValue(b)
      if (typeof va === "number" && typeof vb === "number") return (va - vb) * mul
      return String(va).localeCompare(String(vb)) * mul
    })
  }, [filtered, sortKey, sortDir])

  function cycleSort(key: ColumnKey) {
    if (sortKey !== key) {
      setSortKey(key)
      setSortDir("asc")
      return
    }
    // same column — cycle asc → desc → off
    if (sortDir === "asc") setSortDir("desc")
    else if (sortDir === "desc") {
      setSortKey(null)
      setSortDir(null)
    } else {
      setSortDir("asc")
    }
  }

  // ─── Virtualized rows ─────────────────────────────────────────────────────
  const scrollRef = useRef<HTMLDivElement>(null)
  const rowVirtualizer = useVirtualizer({
    count: sorted.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 32,
    overscan: 12,
  })

  // ─── Empty states ─────────────────────────────────────────────────────────
  const noLists = projectLists.length === 0
  const noUrlsInList = !noLists && activeList && listUrls.length === 0

  return (
    <div className="h-full flex flex-col min-h-0">
      {/* Filter row: [LIST] tabs | [SEARCH] */}
      <div className="flex items-stretch border-b border-border-strong bg-background shrink-0">
        {/* === LIST SECTION === */}
        <div className="flex items-stretch bg-muted/30">
          <div className="flex items-center px-3 border-r border-border">
            <span className="text-[10px] uppercase tracking-[0.25em] text-dim font-bold">
              <span className="text-accent">[</span>
              <span className="px-1.5">LIST</span>
              <span className="text-accent">]</span>
            </span>
          </div>
          {noLists ? (
            <div className="flex items-center px-3 h-9 text-[11px] text-dim italic">
              no lists for this project
            </div>
          ) : (
            <div className="flex items-stretch divide-x divide-border">
              {projectLists.map((l) => {
                const active = l.id === activeListId
                const count = urls.filter((u) => u.urlListId === l.id).length
                return (
                  <button
                    key={l.id}
                    onClick={() => setActiveListId(l.id)}
                    className={cn(
                      "relative flex items-center gap-2 px-3 h-9 transition-colors",
                      active
                        ? "text-accent bg-muted"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted/50",
                    )}
                    aria-pressed={active}
                  >
                    <span className="text-xs font-bold uppercase tracking-[0.2em]">
                      {l.name}
                    </span>
                    <span className="text-[10px] text-dim tabular-nums">
                      ({count})
                    </span>
                    {active && (
                      <span className="absolute left-0 right-0 bottom-0 h-0.5 bg-accent" />
                    )}
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {/* 40px spacer between list and search */}
        {!noLists && <div aria-hidden className="w-10 shrink-0" />}

        {/* === SEARCH SECTION === */}
        {!noLists && (
          <div className="flex-1 min-w-0 flex items-center gap-2 px-4 focus-within:bg-muted/30 transition-colors">
            <Search className="h-4 w-4 text-accent shrink-0" />
            <span className="text-[10px] uppercase tracking-[0.25em] text-dim font-bold shrink-0">
              <span className="text-accent">[</span>
              <span className="px-1.5">SEARCH</span>
              <span className="text-accent">]</span>
            </span>
            <span className="text-dim shrink-0">/</span>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="method, host, path, port, protocol..."
              className="bg-transparent outline-none text-sm flex-1 min-w-0 placeholder:text-dim text-foreground"
              aria-label="Search URLs"
            />
            {search && (
              <button
                onClick={() => setSearch("")}
                className="text-dim hover:text-foreground shrink-0"
                aria-label="Clear search"
              >
                <X className="h-4 w-4" />
              </button>
            )}
            <span className="text-[10px] text-dim uppercase tracking-wider hidden xl:inline shrink-0">
              {search ? `matches: ${filtered.length}` : `${listUrls.length} entries`}
            </span>
          </div>
        )}

        {/* Clear sort pinned right when an ad-hoc sort is active */}
        {!noLists && sortKey && (
          <button
            onClick={() => {
              setSortKey(null)
              setSortDir(null)
            }}
            className="shrink-0 flex items-center px-3 h-9 border-l border-border text-[10px] uppercase tracking-wider text-muted-foreground hover:text-accent hover:bg-muted/50 transition-colors"
          >
            clear sort
          </button>
        )}
      </div>

      {/* ─── Table or empty state ──────────────────────────────────────────── */}
      {noLists ? (
        <EmptyState
          title="no url lists yet"
          body="This project has no URL lists configured. Create one in Config → URL Lists, then add targets (manually, via file upload, or by importing from a crawler) before kicking off web scans."
        />
      ) : noUrlsInList ? (
        <EmptyState
          title={`list "${activeList?.name}" is empty`}
          body="No URLs have been added to this list yet. Add entries manually or import a file to populate it."
        />
      ) : (
        <Panel className="m-3 flex-1 min-h-0">
          <div className="flex flex-col h-full min-h-0">
            {/* Header row */}
            <div className="flex items-center gap-3 px-3 h-8 border-b border-border bg-muted/30 shrink-0 text-[10px] uppercase tracking-[0.25em] text-muted-foreground font-bold">
              {COLUMNS.map((col) => {
                const active = sortKey === col.key
                const dir = active ? sortDir : null
                // Preview direction shown on hover for inactive columns.
                // First click on an unsorted column sorts ascending (see
                // cycleSort), so we hint with an ascending chevron.
                const previewDir: SortDir = active ? null : "asc"
                return (
                  <button
                    key={col.key}
                    onClick={() => cycleSort(col.key)}
                    className={cn(
                      "group flex items-center gap-1 text-left hover:text-foreground transition-colors",
                      active && "text-accent",
                      col.cellClass,
                    )}
                    title={`Sort by ${col.label.toLowerCase()}`}
                  >
                    <span>{col.label}</span>
                    {/* Active-sort indicator (always visible) */}
                    {dir === "asc" && <ChevronUp className="h-3 w-3" />}
                    {dir === "desc" && <ChevronDown className="h-3 w-3" />}
                    {/* Hover preview for inactive columns (dimmed) */}
                    {!active && previewDir === "asc" && (
                      <ChevronUp
                        className="h-3 w-3 opacity-0 group-hover:opacity-60 transition-opacity text-dim"
                        aria-hidden
                      />
                    )}
                  </button>
                )
              })}
            </div>

            {/* Virtualized body */}
            <div ref={scrollRef} className="flex-1 min-h-0 overflow-auto">
              {sorted.length === 0 ? (
                <div className="p-6 text-[12px] text-dim italic">
                  no urls match the current search.
                </div>
              ) : (
                <div
                  style={{
                    height: `${rowVirtualizer.getTotalSize()}px`,
                    position: "relative",
                  }}
                >
                  {rowVirtualizer.getVirtualItems().map((v) => {
                    const u = sorted[v.index]
                    return (
                      <div
                        key={u.id}
                        className="absolute left-0 right-0 flex items-center gap-3 px-3 h-8 border-b border-border/50 hover:bg-muted/40 text-xs font-mono"
                        style={{ transform: `translateY(${v.start}px)` }}
                      >
                        {COLUMNS.map((col) => (
                          <div key={col.key} className={cn("truncate", col.cellClass)}>
                            {col.render ? col.render(u) : String(u[col.key as keyof UrlEntry] ?? "")}
                          </div>
                        ))}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Footer status line */}
            <div className="border-t border-border px-3 h-6 flex items-center justify-between shrink-0 text-[10px] uppercase tracking-wider text-dim">
              <span>
                {sorted.length} of {listUrls.length} urls
                {sortKey && sortDir && (
                  <span className="text-muted-foreground ml-2">
                    // sorted by {sortKey} {sortDir}
                  </span>
                )}
              </span>
              <span>
                list: <span className="text-foreground">{activeList?.name}</span>
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
        <div className="text-lg text-primary tty-glow mb-2 uppercase tracking-wider">
          {title}
        </div>
        <div className="text-xs text-muted-foreground leading-relaxed">{body}</div>
      </div>
    </div>
  )
}
