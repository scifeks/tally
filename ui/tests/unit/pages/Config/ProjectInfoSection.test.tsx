import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ProjectInfoSection } from '@/pages/Config/ProjectInfoSection'
import type { ProjectInfo, ProjectInfoUpdate } from '@/lib/types'

const projectInfo: ProjectInfo = {
  id: 1,
  name: 'acme-platform',
  code: 'ACM',
  companyName: 'ACME Corporation',
  departmentName: 'Security',
  abbreviation: 'ACM',
  createdAt: '2024-01-15T10:30:00Z',
  path: '/opt/tally/projects/acme-platform',
  repoCount: 14,
  findingCount: 220,
}

describe('ProjectInfoSection', () => {
  it('renders editable fields with current values', () => {
    render(<ProjectInfoSection projectInfo={projectInfo} onSave={vi.fn()} isSaving={false} />)
    expect(screen.getByLabelText(/company name/i)).toHaveValue('ACME Corporation')
    expect(screen.getByLabelText(/department name/i)).toHaveValue('Security')
    expect(screen.getByLabelText(/abbreviation/i)).toHaveValue('ACM')
  })

  it('does not render an editable input for project name or path', () => {
    render(<ProjectInfoSection projectInfo={projectInfo} onSave={vi.fn()} isSaving={false} />)
    // No <input> with the project name's value - only the editable trio.
    expect(screen.queryByDisplayValue('acme-platform')).not.toBeInTheDocument()
    expect(
      screen.queryByDisplayValue('/opt/tally/projects/acme-platform')
    ).not.toBeInTheDocument()
    // But the values are still visible as text.
    expect(screen.getByText('acme-platform')).toBeInTheDocument()
    expect(screen.getByText('/opt/tally/projects/acme-platform')).toBeInTheDocument()
  })

  it('disables Update button when nothing has changed', () => {
    render(<ProjectInfoSection projectInfo={projectInfo} onSave={vi.fn()} isSaving={false} />)
    expect(screen.getByRole('button', { name: /update/i })).toBeDisabled()
  })

  it('sends only the changed fields when Update is clicked', () => {
    const onSave = vi.fn<(updates: ProjectInfoUpdate) => void>()
    render(<ProjectInfoSection projectInfo={projectInfo} onSave={onSave} isSaving={false} />)

    fireEvent.change(screen.getByLabelText(/company name/i), {
      target: { value: 'New Co' },
    })
    fireEvent.click(screen.getByRole('button', { name: /update/i }))

    expect(onSave).toHaveBeenCalledTimes(1)
    expect(onSave).toHaveBeenCalledWith({ companyName: 'New Co' })
  })

  it('uppercases the abbreviation and limits it to 3 characters', () => {
    render(<ProjectInfoSection projectInfo={projectInfo} onSave={vi.fn()} isSaving={false} />)
    const abbr = screen.getByLabelText(/abbreviation/i) as HTMLInputElement
    fireEvent.change(abbr, { target: { value: 'xy' } })
    expect(abbr.value).toBe('XY')
    expect(abbr.maxLength).toBe(3)
  })

  it('shows a loading state when projectInfo is null', () => {
    render(<ProjectInfoSection projectInfo={null} onSave={vi.fn()} isSaving={false} />)
    expect(screen.getByText(/loading project info/i)).toBeInTheDocument()
  })

  it('reflects saving state on the Update button', () => {
    render(<ProjectInfoSection projectInfo={projectInfo} onSave={vi.fn()} isSaving={true} />)
    fireEvent.change(screen.getByLabelText(/company name/i), { target: { value: 'X' } })
    expect(screen.getByRole('button', { name: /saving/i })).toBeDisabled()
  })
})
