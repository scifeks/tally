import type { Severity, Status } from '@/lib/types'

/**
 * Server-supported sort columns. The previous prototype offered client-side
 * sort on `id`, `location`, and `commit`; once the list is paginated those
 * sorts only cover the currently-loaded slice and are misleading, so the
 * affordance is dropped on those columns. CWE and finding-type columns are
 * not server-sortable at all.
 */
export type SortKey = 'severity' | 'title' | 'tool' | 'status' | 'found'
export type SortDir = 'asc' | 'desc'
export type SortState = { key: SortKey; dir: SortDir } | null

export type Filters = {
  severity: Set<Severity>
  status: Set<Status>
  tool: Set<string>
  search: string
}
export type FilterKey = keyof Filters

export const emptyFilters = (): Filters => ({
  severity: new Set(),
  status: new Set(),
  tool: new Set(),
  search: '',
})

export type FilterOption = { value: string; label: string; count: number }
