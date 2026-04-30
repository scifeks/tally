import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

const INVALID_TIMESTAMP = '—'

export function parseIso(value: string | null | undefined): Date | null {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d
}

export function formatRelative(value: string | null | undefined): string {
  const d = parseIso(value)
  if (!d) return INVALID_TIMESTAMP
  const diff = Math.max(0, Date.now() - d.getTime())
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

export function formatDate(value: string | null | undefined): string {
  const d = parseIso(value)
  return d ? d.toLocaleDateString() : INVALID_TIMESTAMP
}

export function formatTime(value: string | null | undefined): string {
  const d = parseIso(value)
  return d ? d.toLocaleTimeString('en-US', { hour12: false }) : INVALID_TIMESTAMP
}

export function formatDateTime(value: string | null | undefined): string {
  const d = parseIso(value)
  return d ? d.toLocaleString() : INVALID_TIMESTAMP
}

export function toEpoch(value: string | null | undefined): number {
  const d = parseIso(value)
  return d ? d.getTime() : 0
}
