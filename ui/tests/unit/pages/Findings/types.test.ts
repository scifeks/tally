import { emptyFilters } from '@/pages/Findings/types'

describe('emptyFilters', () => {
  it('two calls produce independent objects so mutating one Set does not affect the other', () => {
    const a = emptyFilters()
    const b = emptyFilters()
    a.severity.add('critical')
    expect(b.severity.size).toBe(0)
  })
})
