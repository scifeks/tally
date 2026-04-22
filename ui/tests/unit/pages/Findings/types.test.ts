import { emptyFilters } from '@/pages/Findings/types'

describe('emptyFilters', () => {
  it('returns severity, status, tool as empty Sets and search as empty string', () => {
    const f = emptyFilters()
    expect(f.severity).toBeInstanceOf(Set)
    expect(f.severity.size).toBe(0)
    expect(f.status).toBeInstanceOf(Set)
    expect(f.status.size).toBe(0)
    expect(f.tool).toBeInstanceOf(Set)
    expect(f.tool.size).toBe(0)
    expect(f.search).toBe('')
  })

  it('two calls produce independent objects — mutating one Set does not affect the other', () => {
    const a = emptyFilters()
    const b = emptyFilters()
    a.severity.add('critical')
    expect(b.severity.size).toBe(0)
  })
})
