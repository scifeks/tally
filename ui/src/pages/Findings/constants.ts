import type { Segment, Finding, Severity, Status } from '@/lib/types'

export function locationOf(f: Finding): string {
  return f.file ? `${f.file}:${f.line ?? ''}` : f.target
}

export const SEGMENTS: { key: Segment; label: string }[] = [
  { key: 'sast', label: 'SAST' },
  { key: 'web', label: 'WEB' },
  { key: 'secrets', label: 'SECRETS' },
  { key: 'sca', label: 'SCA' },
]

export const SEV_ORDER: Severity[] = ['critical', 'high', 'medium', 'low', 'informational']
export const SEV_LABEL: Record<Severity, string> = {
  critical: 'CRIT',
  high: 'HIGH',
  medium: 'MED',
  low: 'LOW',
  informational: 'INFO',
}
export const SEV_COLOR: Record<Severity, string> = {
  critical: '#ff4d4d',
  high: '#ff8c42',
  medium: '#ffd84d',
  low: '#6bd36b',
  informational: '#6ac7ff',
}
export const SEV_RANK: Record<Severity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  informational: 4,
}

export const STATUS_ORDER: Status[] = ['active', 'fixed', 'wont_fix', 'false_positive']
export const STATUS_LABEL: Record<Status, string> = {
  active: 'active',
  fixed: 'fixed',
  wont_fix: 'wont fix',
  false_positive: 'false-pos',
}
export const STATUS_RANK: Record<Status, number> = {
  active: 0,
  fixed: 1,
  wont_fix: 2,
  false_positive: 3,
}
export const STATUS_COLOR: Record<Status, string> = {
  active: '#ff8c42',
  fixed: '#6bd36b',
  wont_fix: '#4a7a4a',
  false_positive: '#4a7a4a',
}

// Column grid: checkbox | id | sev | title | tool | location | cwe | status | found
export const GRID_COLS =
  'grid-cols-[32px_80px_76px_minmax(220px,1fr)_120px_minmax(140px,200px)_minmax(120px,1fr)_110px_90px]'
