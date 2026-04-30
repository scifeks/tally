import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { NoProjectSelectedState } from '@/components/NoProjectSelectedState'
import { useUI } from '@/lib/store'

const SAMPLE_PROJECTS = [
  { id: 1, code: 'ACM', name: 'acme-platform' },
  { id: 2, code: 'ATL', name: 'atlas-api' },
]

beforeEach(() => {
  window.localStorage.clear()
  useUI.setState({
    activeProjectId: null,
    findingsSegment: 'sast',
    selectedFindingIds: new Set<number>(),
    findingMutationError: null,
    triageRunStatus: 'idle',
  })
})

describe('NoProjectSelectedState', () => {
  it('renders the headline and instructions', () => {
    render(<NoProjectSelectedState projects={SAMPLE_PROJECTS} />)
    expect(screen.getByText('No Project Selected')).toBeInTheDocument()
    expect(screen.getByText(/Select a project from the dropdown/i)).toBeInTheDocument()
  })

  it('renders a button per project when projects are available', () => {
    render(<NoProjectSelectedState projects={SAMPLE_PROJECTS} />)
    expect(screen.getByText('ACM')).toBeInTheDocument()
    expect(screen.getByText('acme-platform')).toBeInTheDocument()
    expect(screen.getByText('ATL')).toBeInTheDocument()
    expect(screen.getByText('atlas-api')).toBeInTheDocument()
  })

  it('clicking a project sets activeProjectId via the store', async () => {
    const user = userEvent.setup()
    render(<NoProjectSelectedState projects={SAMPLE_PROJECTS} />)

    await user.click(screen.getByText('ATL'))

    expect(useUI.getState().activeProjectId).toBe(2)
  })

  it('shows the CLI hint when the project list is empty', () => {
    render(<NoProjectSelectedState projects={[]} />)
    expect(screen.getByText(/No projects found/i)).toBeInTheDocument()
    expect(screen.getByText('$ tally project add')).toBeInTheDocument()
  })
})
