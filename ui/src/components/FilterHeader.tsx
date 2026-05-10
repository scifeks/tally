import { useEffect, useRef, useState } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface FilterHeaderOption {
  value: string
  label: string
  count: number
}

export type FilterHeaderSortDir = 'asc' | 'desc' | null

export function FilterHeaderSortIndicator({ state }: { state: FilterHeaderSortDir }) {
  if (state === 'asc') return <ArrowUp className="h-3 w-3 text-accent" />
  if (state === 'desc') return <ArrowDown className="h-3 w-3 text-accent" />
  return <ArrowUpDown className="h-3 w-3 text-dim opacity-0 group-hover:opacity-100" />
}

export interface FilterHeaderProps {
  label: string
  onSort: () => void
  sortDir: FilterHeaderSortDir
  activeCount: number
  options: FilterHeaderOption[]
  selected: Set<string>
  onChange: (next: Set<string>) => void
}

/**
 * Reusable column-header with a chevron filter dropdown. Used by both the
 * Findings table and the URL Lists table (Phase 12.2). The component owns
 * its open/close state, dismiss-on-outside-click, and Escape handling, but
 * leaves the sort key/direction logic to the caller (caller passes a
 * concrete `sortDir` and an `onSort` callback).
 */
export function FilterHeader({
  label,
  onSort,
  sortDir,
  activeCount,
  options,
  selected,
  onChange,
}: FilterHeaderProps) {
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

  const sortActive = sortDir !== null
  const hasFilter = activeCount > 0

  return (
    <div ref={ref} className="relative flex items-center gap-1 h-full">
      <button
        type="button"
        onClick={onSort}
        className={cn(
          'group flex items-center gap-1 text-[10px] uppercase tracking-[0.18em] transition-colors h-full',
          sortActive || hasFilter ? 'text-accent' : 'text-muted-foreground hover:text-foreground'
        )}
      >
        <span>{label}</span>
        <FilterHeaderSortIndicator state={sortDir} />
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
