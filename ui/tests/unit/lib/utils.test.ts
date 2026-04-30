import {
  cn,
  formatDate,
  formatDateTime,
  formatRelative,
  formatTime,
  parseIso,
  toEpoch,
} from '@/lib/utils'

const ago = (ms: number) => new Date(Date.now() - ms).toISOString()
const future = () => new Date(Date.now() + 60_000).toISOString()

const INVALID_INPUTS = [null, undefined, '', 'not-a-date', '2026-13-99T99:99:99Z'] as const

describe('cn', () => {
  it('merges class names', () => {
    expect(cn('foo', 'bar')).toBe('foo bar')
  })

  it('deduplicates conflicting Tailwind classes, last one wins', () => {
    expect(cn('w-1/2', 'w-full')).toBe('w-full')
  })

  it('ignores falsy values', () => {
    expect(cn('foo', false, undefined, null, 'bar')).toBe('foo bar')
  })
})

describe('formatRelative', () => {
  it('returns "just now" for a future date', () => {
    expect(formatRelative(future())).toBe('just now')
  })

  it('returns "just now" for 0 seconds ago', () => {
    expect(formatRelative(new Date().toISOString())).toBe('just now')
  })

  it('returns "just now" for 59 seconds ago', () => {
    expect(formatRelative(ago(59_000))).toBe('just now')
  })

  it('returns "1m ago" for exactly 60 seconds ago', () => {
    expect(formatRelative(ago(60_000))).toBe('1m ago')
  })

  it('returns "59m ago" for 59 minutes ago', () => {
    expect(formatRelative(ago(59 * 60_000))).toBe('59m ago')
  })

  it('returns "1h ago" for exactly 60 minutes ago', () => {
    expect(formatRelative(ago(60 * 60_000))).toBe('1h ago')
  })

  it('returns "23h ago" for 23 hours ago', () => {
    expect(formatRelative(ago(23 * 3_600_000))).toBe('23h ago')
  })

  it('returns "1d ago" for exactly 24 hours ago', () => {
    expect(formatRelative(ago(24 * 3_600_000))).toBe('1d ago')
  })

  it.each(INVALID_INPUTS)('returns "—" for invalid input %p', input => {
    expect(formatRelative(input)).toBe('—')
  })
})

describe('parseIso', () => {
  it('parses a valid ISO string into a Date', () => {
    const d = parseIso('2026-04-26T10:00:00Z')
    expect(d).toBeInstanceOf(Date)
    expect(d?.toISOString()).toBe('2026-04-26T10:00:00.000Z')
  })

  it.each(INVALID_INPUTS)('returns null for invalid input %p', input => {
    expect(parseIso(input)).toBeNull()
  })
})

describe('formatDate', () => {
  it('formats a valid ISO string', () => {
    const out = formatDate('2026-04-26T10:00:00Z')
    expect(out).not.toBe('—')
    expect(out).not.toMatch(/NaN|Invalid/)
  })

  it.each(INVALID_INPUTS)('returns "—" for invalid input %p', input => {
    expect(formatDate(input)).toBe('—')
  })
})

describe('formatTime', () => {
  it('formats a valid ISO string in 24h notation', () => {
    const out = formatTime('2026-04-26T10:00:00Z')
    expect(out).not.toBe('—')
    expect(out).not.toMatch(/NaN|Invalid/)
    expect(out).toMatch(/^\d{2}:\d{2}:\d{2}$/)
  })

  it.each(INVALID_INPUTS)('returns "—" for invalid input %p', input => {
    expect(formatTime(input)).toBe('—')
  })
})

describe('formatDateTime', () => {
  it('formats a valid ISO string', () => {
    const out = formatDateTime('2026-04-26T10:00:00Z')
    expect(out).not.toBe('—')
    expect(out).not.toMatch(/NaN|Invalid/)
  })

  it.each(INVALID_INPUTS)('returns "—" for invalid input %p', input => {
    expect(formatDateTime(input)).toBe('—')
  })
})

describe('toEpoch', () => {
  it('returns the epoch ms for a valid ISO string', () => {
    expect(toEpoch('2026-04-26T10:00:00Z')).toBe(Date.UTC(2026, 3, 26, 10, 0, 0))
  })

  it.each(INVALID_INPUTS)('returns 0 for invalid input %p', input => {
    expect(toEpoch(input)).toBe(0)
  })
})
