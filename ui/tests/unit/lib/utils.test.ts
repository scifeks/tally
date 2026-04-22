import { cn, formatRelative } from '@/lib/utils'

const ago = (ms: number) => new Date(Date.now() - ms).toISOString()
const future = () => new Date(Date.now() + 60_000).toISOString()

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
})
