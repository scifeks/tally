import { useUI } from '@/lib/store'

const reset = () =>
  useUI.setState({
    activeProjectId: null,
    findingsSegment: 'sast',
    selectedFindingIds: new Set<string>(),
    findingOverrides: {},
    triageRunStatus: 'idle',
  })

beforeEach(reset)

describe('useUI — initial state', () => {
  it('activeProjectId defaults to null (no project selected)', () => {
    expect(useUI.getState().activeProjectId).toBeNull()
  })

  it('findingsSegment defaults to "sast"', () => {
    expect(useUI.getState().findingsSegment).toBe('sast')
  })

  it('selectedFindingIds is an empty Set', () => {
    expect(useUI.getState().selectedFindingIds.size).toBe(0)
  })

  it('findingOverrides is an empty object', () => {
    expect(useUI.getState().findingOverrides).toEqual({})
  })

  it('triageRunStatus defaults to "idle"', () => {
    expect(useUI.getState().triageRunStatus).toBe('idle')
  })
})

describe('setActiveProject', () => {
  it('updates activeProjectId', () => {
    useUI.getState().setActiveProject(2)
    expect(useUI.getState().activeProjectId).toBe(2)
  })

  it('clears selectedFindingIds', () => {
    useUI.setState({ selectedFindingIds: new Set(['f-1', 'f-2']) })
    useUI.getState().setActiveProject(2)
    expect(useUI.getState().selectedFindingIds.size).toBe(0)
  })
})

describe('setFindingsSegment', () => {
  it('updates findingsSegment', () => {
    useUI.getState().setFindingsSegment('web')
    expect(useUI.getState().findingsSegment).toBe('web')
  })

  it('clears selectedFindingIds', () => {
    useUI.setState({ selectedFindingIds: new Set(['f-1']) })
    useUI.getState().setFindingsSegment('web')
    expect(useUI.getState().selectedFindingIds.size).toBe(0)
  })
})

describe('toggleSelected', () => {
  it('adds an id when not already in the Set', () => {
    useUI.getState().toggleSelected('f-1')
    expect(useUI.getState().selectedFindingIds.has('f-1')).toBe(true)
  })

  it('removes an id when already in the Set', () => {
    useUI.setState({ selectedFindingIds: new Set(['f-1']) })
    useUI.getState().toggleSelected('f-1')
    expect(useUI.getState().selectedFindingIds.has('f-1')).toBe(false)
  })

  it('does not mutate other ids when toggling', () => {
    useUI.setState({ selectedFindingIds: new Set(['f-1', 'f-2']) })
    useUI.getState().toggleSelected('f-1')
    expect(useUI.getState().selectedFindingIds.has('f-2')).toBe(true)
  })
})

describe('setSelected', () => {
  it('replaces the Set with the provided ids', () => {
    useUI.setState({ selectedFindingIds: new Set(['old-1']) })
    useUI.getState().setSelected(['f-a', 'f-b'])
    const ids = useUI.getState().selectedFindingIds
    expect(ids.has('old-1')).toBe(false)
    expect(ids.has('f-a')).toBe(true)
    expect(ids.has('f-b')).toBe(true)
  })
})

describe('clearSelected', () => {
  it('empties the Set', () => {
    useUI.setState({ selectedFindingIds: new Set(['f-1', 'f-2']) })
    useUI.getState().clearSelected()
    expect(useUI.getState().selectedFindingIds.size).toBe(0)
  })
})

describe('updateFinding', () => {
  it('merges a patch into findingOverrides for the given id', () => {
    useUI.getState().updateFinding('f-1', { status: 'fixed' })
    expect(useUI.getState().findingOverrides['f-1']).toEqual({ status: 'fixed' })
  })

  it('merges subsequent patches without replacing earlier fields', () => {
    useUI.getState().updateFinding('f-1', { status: 'fixed' })
    useUI.getState().updateFinding('f-1', { severity: 'low' })
    expect(useUI.getState().findingOverrides['f-1']).toEqual({
      status: 'fixed',
      severity: 'low',
    })
  })

  it('keeps other finding overrides untouched', () => {
    useUI.getState().updateFinding('f-1', { status: 'fixed' })
    useUI.getState().updateFinding('f-2', { status: 'active' })
    expect(useUI.getState().findingOverrides['f-1']).toEqual({ status: 'fixed' })
    expect(useUI.getState().findingOverrides['f-2']).toEqual({ status: 'active' })
  })
})

describe('setTriageRunStatus', () => {
  it('updates triageRunStatus', () => {
    useUI.getState().setTriageRunStatus('running')
    expect(useUI.getState().triageRunStatus).toBe('running')
  })
})
