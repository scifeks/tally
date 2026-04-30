import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RepositorySection } from '@/pages/Config/RepositorySection'
import type { RepositoryConfig } from '@/lib/types'

const repos: RepositoryConfig[] = [
  {
    id: 101,
    projectId: 1,
    name: 'dvwa',
    types: ['api', 'ui'],
    locationMode: 'local',
    localPath: '/opt/repos/dvwa',
    languages: ['php'],
    testDirectories: ['tests'],
    ignoreDirectories: ['vendor'],
    baseUrls: ['http://localhost:8080'],
    alsoRunCrawlers: true,
    katana: { headless: false, crawlDepth: 10 },
  },
  {
    id: 102,
    projectId: 1,
    name: 'dvpwa',
    types: ['api'],
    locationMode: 'docker',
    localPath: '/opt/repos/dvpwa',
    docker: { containerName: 'dvpwa-container', mountPoint: '/app' },
    languages: ['python'],
    testDirectories: ['tests'],
    ignoreDirectories: [],
    baseUrls: [],
    alsoRunCrawlers: true,
    katana: { headless: false, crawlDepth: 8 },
  },
]

function renderSection(overrides: Partial<React.ComponentProps<typeof RepositorySection>> = {}) {
  const props = {
    repositories: repos,
    projectId: 1,
    onSave: vi.fn(),
    onDelete: vi.fn(),
    onUpdateAuth: vi.fn(),
    isSaving: false,
    isSavingAuth: false,
    authSavedAt: null,
    ...overrides,
  }
  return { ...render(<RepositorySection {...props} />), props }
}

describe('RepositorySection', () => {
  it('shows the empty placeholder when no repository is selected', () => {
    renderSection()
    expect(
      screen.getByText(/select a repository to edit or create a new one/i)
    ).toBeInTheDocument()
  })

  it('populates form fields when an existing repository is selected', () => {
    renderSection()
    const select = screen.getByRole('combobox')
    fireEvent.change(select, { target: { value: '101' } })
    expect(screen.getByLabelText(/^name/i)).toHaveValue('dvwa')
    expect(screen.getByLabelText(/local path/i)).toHaveValue('/opt/repos/dvwa')
  })

  it('hides the auth section when creating a new repository', () => {
    renderSection()
    fireEvent.click(screen.getByRole('button', { name: /new/i }))
    expect(screen.queryByLabelText(/login url/i)).not.toBeInTheDocument()
  })

  it('shows the auth section when editing an existing repository', () => {
    renderSection()
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '101' } })
    expect(screen.getByLabelText(/login url/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
  })

  it('calls onUpdateAuth with the auth payload when Save Auth is clicked', () => {
    const onUpdateAuth = vi.fn()
    renderSection({ onUpdateAuth })
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '101' } })
    fireEvent.change(screen.getByLabelText(/login url/i), {
      target: { value: 'https://x.test/login' },
    })
    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'alice' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'secret' } })
    fireEvent.click(screen.getByRole('button', { name: /save auth/i }))
    expect(onUpdateAuth).toHaveBeenCalledTimes(1)
    expect(onUpdateAuth).toHaveBeenCalledWith(101, {
      loginUrl: 'https://x.test/login',
      username: 'alice',
      password: 'secret',
    })
  })

  it('disables the Save Auth button until a login URL is entered', () => {
    renderSection()
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '101' } })
    expect(screen.getByRole('button', { name: /save auth/i })).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/login url/i), {
      target: { value: 'https://x.test/login' },
    })
    expect(screen.getByRole('button', { name: /save auth/i })).toBeEnabled()
  })

  describe('authSavedAt', () => {
    beforeEach(() => {
      vi.useFakeTimers()
      vi.setSystemTime(new Date('2026-04-29T12:00:00Z'))
    })
    afterEach(() => vi.useRealTimers())

    it('flashes a "Saved" affordance when authSavedAt is fresh', () => {
      const now = Date.now()
      renderSection({ authSavedAt: now - 100 })
      fireEvent.change(screen.getByRole('combobox'), { target: { value: '101' } })
      expect(screen.getByText(/saved/i)).toBeInTheDocument()
    })

    it('does not show the affordance for stale timestamps', () => {
      const now = Date.now()
      renderSection({ authSavedAt: now - 5_000 })
      fireEvent.change(screen.getByRole('combobox'), { target: { value: '101' } })
      expect(screen.queryByText(/^saved$/i)).not.toBeInTheDocument()
    })
  })

  it('confirms before deleting and calls onDelete with the selected id', async () => {
    const onDelete = vi.fn()
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderSection({ onDelete })
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '101' } })
    await userEvent.click(screen.getByRole('button', { name: /delete/i }))
    expect(confirmSpy).toHaveBeenCalled()
    expect(onDelete).toHaveBeenCalledWith(101)
    confirmSpy.mockRestore()
  })

  it('does not delete when confirm is dismissed', async () => {
    const onDelete = vi.fn()
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderSection({ onDelete })
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '101' } })
    await userEvent.click(screen.getByRole('button', { name: /delete/i }))
    expect(onDelete).not.toHaveBeenCalled()
    confirmSpy.mockRestore()
  })

  it('passes the selected file to onSave when present', async () => {
    const onSave = vi.fn()
    renderSection({ onSave })
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '101' } })
    const file = new File(['{"swagger":"2.0"}'], 'spec.json', { type: 'application/json' })
    const fileInput = screen.getByLabelText(/endpoint file/i) as HTMLInputElement
    await userEvent.upload(fileInput, file)
    const saveBtn = within(
      screen.getByRole('button', { name: /^save$/i }).parentElement as HTMLElement
    ).getByRole('button', { name: /^save$/i })
    fireEvent.click(saveBtn)
    expect(onSave).toHaveBeenCalledTimes(1)
    const [, isNew, endpointFile] = onSave.mock.calls[0]
    expect(isNew).toBe(false)
    expect(endpointFile).toBe(file)
  })

  it('calls onSave with isNew=true when creating a new repository', () => {
    const onSave = vi.fn()
    renderSection({ onSave })
    fireEvent.click(screen.getByRole('button', { name: /new/i }))
    fireEvent.change(screen.getByLabelText(/^name/i), { target: { value: 'newrepo' } })
    // Toggle a type
    fireEvent.click(screen.getByRole('button', { name: /^api$/i }))
    fireEvent.change(screen.getByLabelText(/local path/i), {
      target: { value: '/opt/repos/newrepo' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^create$/i }))
    expect(onSave).toHaveBeenCalledTimes(1)
    const [repo, isNew] = onSave.mock.calls[0]
    expect(isNew).toBe(true)
    expect(repo.name).toBe('newrepo')
    expect(repo.localPath).toBe('/opt/repos/newrepo')
    expect(repo.types).toContain('api')
  })
})
