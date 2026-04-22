import type { Severity, Status } from '@/lib/types'

export type SortKey =
  | 'id'
  | 'severity'
  | 'title'
  | 'tool'
  | 'location'
  | 'commit'
  | 'status'
  | 'found'
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
