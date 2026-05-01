import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useUI } from '@/lib/store'

const PERSIST_KEY = 'tally-ui-active-project'

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

describe('setActiveProject', () => {
  it('clears selectedFindingIds', () => {
    useUI.setState({ selectedFindingIds: new Set([1, 2]) })
    useUI.getState().setActiveProject(2)
    expect(useUI.getState().selectedFindingIds.size).toBe(0)
  })
})

describe('setFindingsSegment', () => {
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

describe('fresh-session reset', () => {
  const ORIGIN = window.location.origin

  function setLocation(href: string): void {
    window.history.replaceState({}, '', href)
  }

  function seedPersisted(state: Partial<{
    activeProjectId: number | null
    triageInjectionAcked: boolean
  }>): void {
    window.localStorage.setItem(
      PERSIST_KEY,
      JSON.stringify({ state, version: 0 })
    )
  }

  beforeEach(() => {
    window.localStorage.clear()
    setLocation(`${ORIGIN}/`)
  })

  afterEach(() => {
    window.localStorage.clear()
    setLocation(`${ORIGIN}/`)
    vi.resetModules()
  })

  it('clears persisted activeProjectId and strips the param when ?fresh=1 is set', async () => {
    seedPersisted({ activeProjectId: 7, triageInjectionAcked: true })
    setLocation(`${ORIGIN}/?fresh=1`)
    vi.resetModules()

    await import('@/lib/store')

    expect(window.localStorage.getItem(PERSIST_KEY)).toBeNull()
    expect(window.location.search).toBe('')
  })

  it('rehydrates persisted activeProjectId when ?fresh=1 is absent', async () => {
    seedPersisted({ activeProjectId: 7, triageInjectionAcked: false })
    setLocation(`${ORIGIN}/`)
    vi.resetModules()

    const mod = await import('@/lib/store')

    expect(mod.useUI.getState().activeProjectId).toBe(7)
  })

  it('preserves other query params when stripping ?fresh=1', async () => {
    setLocation(`${ORIGIN}/projects/1?fresh=1&tab=findings`)
    vi.resetModules()

    await import('@/lib/store')

    expect(window.location.search).toBe('?tab=findings')
    expect(window.location.pathname).toBe('/projects/1')
  })
})
