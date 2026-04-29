import { useUI } from '@/lib/store'

const reset = () =>
  useUI.setState({
    activeProjectId: null,
    findingsSegment: 'sast',
    selectedFindingIds: new Set<number>(),
    findingMutationError: null,
    scanMutationError: null,
    triageMutationError: null,
    triageInjectionAcked: false,
    triageRunStatus: 'idle',
    reportMutationError: null,
    chatMutationError: null,
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

  it('findingMutationError defaults to null', () => {
    expect(useUI.getState().findingMutationError).toBeNull()
  })

  it('triageRunStatus defaults to "idle"', () => {
    expect(useUI.getState().triageRunStatus).toBe('idle')
  })

  it('triageMutationError defaults to null', () => {
    expect(useUI.getState().triageMutationError).toBeNull()
  })

  it('triageInjectionAcked defaults to false', () => {
    expect(useUI.getState().triageInjectionAcked).toBe(false)
  })
})

describe('setActiveProject', () => {
  it('updates activeProjectId', () => {
    useUI.getState().setActiveProject(2)
    expect(useUI.getState().activeProjectId).toBe(2)
  })

  it('clears selectedFindingIds', () => {
    useUI.setState({ selectedFindingIds: new Set([1, 2]) })
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
    useUI.setState({ selectedFindingIds: new Set([1]) })
    useUI.getState().setFindingsSegment('web')
    expect(useUI.getState().selectedFindingIds.size).toBe(0)
  })
})

describe('toggleSelected', () => {
  it('adds an id when not already in the Set', () => {
    useUI.getState().toggleSelected(1)
    expect(useUI.getState().selectedFindingIds.has(1)).toBe(true)
  })

  it('removes an id when already in the Set', () => {
    useUI.setState({ selectedFindingIds: new Set([1]) })
    useUI.getState().toggleSelected(1)
    expect(useUI.getState().selectedFindingIds.has(1)).toBe(false)
  })

  it('does not mutate other ids when toggling', () => {
    useUI.setState({ selectedFindingIds: new Set([1, 2]) })
    useUI.getState().toggleSelected(1)
    expect(useUI.getState().selectedFindingIds.has(2)).toBe(true)
  })
})

describe('setSelected', () => {
  it('replaces the Set with the provided ids', () => {
    useUI.setState({ selectedFindingIds: new Set([99]) })
    useUI.getState().setSelected([1, 2])
    const ids = useUI.getState().selectedFindingIds
    expect(ids.has(99)).toBe(false)
    expect(ids.has(1)).toBe(true)
    expect(ids.has(2)).toBe(true)
  })
})

describe('clearSelected', () => {
  it('empties the Set', () => {
    useUI.setState({ selectedFindingIds: new Set([1, 2]) })
    useUI.getState().clearSelected()
    expect(useUI.getState().selectedFindingIds.size).toBe(0)
  })
})

describe('setFindingMutationError', () => {
  it('stores an error payload for the modal', () => {
    useUI.getState().setFindingMutationError({
      code: 'FINDING_LOCKED',
      message: 'Finding is locked',
    })
    expect(useUI.getState().findingMutationError).toEqual({
      code: 'FINDING_LOCKED',
      message: 'Finding is locked',
    })
  })

  it('clears the error when set to null', () => {
    useUI.getState().setFindingMutationError({ code: 'X', message: 'm' })
    useUI.getState().setFindingMutationError(null)
    expect(useUI.getState().findingMutationError).toBeNull()
  })
})

describe('setTriageRunStatus', () => {
  it('updates triageRunStatus', () => {
    useUI.getState().setTriageRunStatus('running')
    expect(useUI.getState().triageRunStatus).toBe('running')
  })
})

describe('setTriageMutationError', () => {
  it('stores an error payload for the modal', () => {
    useUI.getState().setTriageMutationError({
      code: 'JOB_ALREADY_RUNNING',
      message: 'Triage is already running',
      details: {},
      status: 409,
    })
    expect(useUI.getState().triageMutationError).toEqual({
      code: 'JOB_ALREADY_RUNNING',
      message: 'Triage is already running',
      details: {},
      status: 409,
    })
  })

  it('clears the error when set to null', () => {
    useUI.getState().setTriageMutationError({
      code: 'X',
      message: 'm',
      details: {},
      status: 500,
    })
    useUI.getState().setTriageMutationError(null)
    expect(useUI.getState().triageMutationError).toBeNull()
  })
})

describe('setTriageInjectionAcked', () => {
  it('updates the ack flag', () => {
    useUI.getState().setTriageInjectionAcked(true)
    expect(useUI.getState().triageInjectionAcked).toBe(true)
  })
})

describe('setReportMutationError', () => {
  it('defaults to null', () => {
    expect(useUI.getState().reportMutationError).toBeNull()
  })

  it('stores an error payload for the modal', () => {
    useUI.getState().setReportMutationError({
      code: 'JOB_ALREADY_RUNNING',
      message: 'a report generation is already running',
      details: {},
      status: 409,
    })
    expect(useUI.getState().reportMutationError).toEqual({
      code: 'JOB_ALREADY_RUNNING',
      message: 'a report generation is already running',
      details: {},
      status: 409,
    })
  })

  it('clears the error when set to null', () => {
    useUI.getState().setReportMutationError({
      code: 'X',
      message: 'm',
      details: {},
      status: 500,
    })
    useUI.getState().setReportMutationError(null)
    expect(useUI.getState().reportMutationError).toBeNull()
  })
})

describe('setChatMutationError', () => {
  it('defaults to null', () => {
    expect(useUI.getState().chatMutationError).toBeNull()
  })

  it('stores an error payload for the modal', () => {
    useUI.getState().setChatMutationError({
      code: 'CHAT_SESSION_EXPIRED',
      message: 'this chat session has been sealed',
      details: { expired_at: '2026-04-26T11:45:00+00:00' },
      status: 409,
    })
    expect(useUI.getState().chatMutationError).toEqual({
      code: 'CHAT_SESSION_EXPIRED',
      message: 'this chat session has been sealed',
      details: { expired_at: '2026-04-26T11:45:00+00:00' },
      status: 409,
    })
  })

  it('clears the error when set to null', () => {
    useUI.getState().setChatMutationError({
      code: 'X',
      message: 'm',
      details: {},
      status: 500,
    })
    useUI.getState().setChatMutationError(null)
    expect(useUI.getState().chatMutationError).toBeNull()
  })
})
