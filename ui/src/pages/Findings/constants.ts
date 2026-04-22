import type { Domain, Finding, Severity, Status } from '@/lib/types'

export function locationOf(f: Finding): string {
  return f.file ? `${f.file}:${f.line ?? ''}` : f.target
}

export const DOMAINS: { key: Domain; label: string }[] = [
  { key: 'sast', label: 'SAST' },
  { key: 'web', label: 'WEB' },
  { key: 'secrets', label: 'SECRETS' },
  { key: 'sca', label: 'SCA' },
]

export const SEV_ORDER: Severity[] = ['critical', 'high', 'medium', 'low', 'info']
export const SEV_LABEL: Record<Severity, string> = {
  critical: 'CRIT',
  high: 'HIGH',
  medium: 'MED',
  low: 'LOW',
  info: 'INFO',
}
export const SEV_COLOR: Record<Severity, string> = {
  critical: '#ff4d4d',
  high: '#ff8c42',
  medium: '#ffd84d',
  low: '#6bd36b',
  info: '#6ac7ff',
}
export const SEV_RANK: Record<Severity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
}

export const STATUS_ORDER: Status[] = ['open', 'triaged', 'fixed', 'wontfix', 'false_positive']
export const STATUS_LABEL: Record<Status, string> = {
  open: 'open',
  triaged: 'triaged',
  fixed: 'fixed',
  wontfix: 'wontfix',
  false_positive: 'false-pos',
}
export const STATUS_RANK: Record<Status, number> = {
  open: 0,
  triaged: 1,
  fixed: 2,
  wontfix: 3,
  false_positive: 4,
}
export const STATUS_COLOR: Record<Status, string> = {
  open: '#ff8c42',
  triaged: '#6ac7ff',
  fixed: '#6bd36b',
  wontfix: '#4a7a4a',
  false_positive: '#4a7a4a',
}

// Column grid: checkbox | id | sev | title | tool | location | commit | status | found
export const GRID_COLS =
  'grid-cols-[32px_80px_76px_minmax(220px,1fr)_120px_minmax(140px,200px)_90px_110px_90px]'
