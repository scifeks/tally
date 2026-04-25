import { locationOf } from '@/pages/Findings/constants'
import type { Finding } from '@/lib/types'

const base: Finding = {
  id: 'f-1',
  target: 'https://example.com/path',
  severity: 'high',
  status: 'active',
  segment: 'sast',
  tool: 'semgrep',
  title: 'Example finding',
  projectId: '1',
  discoveredAt: '2024-01-01T00:00:00Z',
}

describe('locationOf', () => {
  it('returns "file:line" when both file and line are present', () => {
    expect(locationOf({ ...base, file: 'src/app.py', line: 42 })).toBe(
      'src/app.py:42',
    )
  })

  it('returns "file:" when file is present but line is undefined', () => {
    expect(locationOf({ ...base, file: 'src/app.py', line: undefined })).toBe(
      'src/app.py:',
    )
  })

  it('returns target when file is undefined', () => {
    expect(locationOf({ ...base, file: undefined })).toBe(base.target)
  })

  it('returns target when file is an empty string (falsy)', () => {
    expect(locationOf({ ...base, file: '' })).toBe(base.target)
  })
})
