import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
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
    saveCompletedAt: null,
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

  it('populates form fields when an existing repository is selected', async () => {
    const user = userEvent.setup()
    renderSection()
    await user.selectOptions(screen.getByRole('combobox'), '101')
    expect(screen.getByLabelText(/^name/i)).toHaveValue('dvwa')
    expect(screen.getByLabelText(/local path/i)).toHaveValue('/opt/repos/dvwa')
  })

  it('hides the auth section when creating a new repository', async () => {
    const user = userEvent.setup()
    renderSection()
    await user.click(screen.getByRole('button', { name: /new/i }))
    expect(screen.queryByLabelText(/login url/i)).not.toBeInTheDocument()
  })

  it('shows the auth section when editing an existing repository', async () => {
    const user = userEvent.setup()
    renderSection()
    await user.selectOptions(screen.getByRole('combobox'), '101')
    expect(screen.getByLabelText(/login url/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
  })

  it('calls onUpdateAuth with the auth payload when Save Auth is clicked', async () => {
    const user = userEvent.setup()
    const onUpdateAuth = vi.fn()
    renderSection({ onUpdateAuth })
    await user.selectOptions(screen.getByRole('combobox'), '101')
    await user.type(screen.getByLabelText(/login url/i), 'https://x.test/login')
    await user.type(screen.getByLabelText(/username/i), 'alice')
    await user.type(screen.getByLabelText(/password/i), 'secret')
    await user.click(screen.getByRole('button', { name: /save auth/i }))
    expect(onUpdateAuth).toHaveBeenCalledTimes(1)
    expect(onUpdateAuth).toHaveBeenCalledWith(101, {
      loginUrl: 'https://x.test/login',
      username: 'alice',
      password: 'secret',
    })
  })

  it('disables the Save Auth button until a login URL is entered', async () => {
    const user = userEvent.setup()
    renderSection()
    await user.selectOptions(screen.getByRole('combobox'), '101')
    expect(screen.getByRole('button', { name: /save auth/i })).toBeDisabled()
    await user.type(screen.getByLabelText(/login url/i), 'https://x.test/login')
    expect(screen.getByRole('button', { name: /save auth/i })).toBeEnabled()
  })

  describe('authSavedAt', () => {
    const PINNED_NOW = new Date('2026-04-29T12:00:00Z').getTime()
    let nowSpy: ReturnType<typeof vi.spyOn>

    beforeEach(() => {
      nowSpy = vi.spyOn(Date, 'now').mockReturnValue(PINNED_NOW)
    })
    afterEach(() => nowSpy.mockRestore())

    it('flashes a "Saved" affordance when authSavedAt is fresh', async () => {
      const user = userEvent.setup()
      renderSection({ authSavedAt: PINNED_NOW - 100 })
      await user.selectOptions(screen.getByRole('combobox'), '101')
      expect(screen.getByText(/saved/i)).toBeInTheDocument()
    })

    it('does not show the affordance for stale timestamps', async () => {
      const user = userEvent.setup()
      renderSection({ authSavedAt: PINNED_NOW - 5_000 })
      await user.selectOptions(screen.getByRole('combobox'), '101')
      expect(screen.queryByText(/^saved$/i)).not.toBeInTheDocument()
    })
  })

  it('confirms before deleting and calls onDelete with the selected id', async () => {
    const user = userEvent.setup()
    const onDelete = vi.fn()
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderSection({ onDelete })
    await user.selectOptions(screen.getByRole('combobox'), '101')
    await user.click(screen.getByRole('button', { name: /delete/i }))
    expect(confirmSpy).toHaveBeenCalled()
    expect(onDelete).toHaveBeenCalledWith(101)
    confirmSpy.mockRestore()
  })

  it('does not delete when confirm is dismissed', async () => {
    const user = userEvent.setup()
    const onDelete = vi.fn()
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderSection({ onDelete })
    await user.selectOptions(screen.getByRole('combobox'), '101')
    await user.click(screen.getByRole('button', { name: /delete/i }))
    expect(onDelete).not.toHaveBeenCalled()
    confirmSpy.mockRestore()
  })

  it('passes the selected file to onSave when present', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    renderSection({ onSave })
    await user.selectOptions(screen.getByRole('combobox'), '101')
    const file = new File(['{"swagger":"2.0"}'], 'spec.json', { type: 'application/json' })
    const fileInput = screen.getByLabelText(/endpoint file/i) as HTMLInputElement
    await user.upload(fileInput, file)
    const saveBtn = within(
      screen.getByRole('button', { name: /^save$/i }).parentElement as HTMLElement
    ).getByRole('button', { name: /^save$/i })
    await user.click(saveBtn)
    expect(onSave).toHaveBeenCalledTimes(1)
    const [, isNew, endpointFile] = onSave.mock.calls[0]
    expect(isNew).toBe(false)
    expect(endpointFile).toBe(file)
    // Regression for an empty-multipart bug. Clearing the file input
    // synchronously detaches the underlying blob in Chrome before the async
    // mutation reads it, so the section keeps the file ref until the parent
    // fires saveCompletedAt.
    expect(fileInput.files?.length).toBe(1)
    expect(fileInput.files?.[0]).toBe(file)
  })

  it('clears the staged file once saveCompletedAt fires', async () => {
    const user = userEvent.setup()
    const repoFile = new File(['{"swagger":"2.0"}'], 'spec.json', {
      type: 'application/json',
    })
    const { rerender, props } = renderSection({ saveCompletedAt: null })
    await user.selectOptions(screen.getByRole('combobox'), '101')
    const fileInput = screen.getByLabelText(/endpoint file/i) as HTMLInputElement
    await user.upload(fileInput, repoFile)
    expect(fileInput.files?.length).toBe(1)
    rerender(<RepositorySection {...props} saveCompletedAt={Date.now()} />)
    expect(fileInput.files?.length).toBe(0)
  })

  it('shows the existing seed file affordance when set and no fresh upload is staged', async () => {
    const user = userEvent.setup()
    const reposWithSeed: RepositoryConfig[] = [
      { ...repos[0], endpointFile: 'existing.json' },
    ]
    renderSection({ repositories: reposWithSeed })
    await user.selectOptions(screen.getByRole('combobox'), '101')
    expect(
      screen.getByText(/current: existing\.json\. uploading a new file will replace it\./i)
    ).toBeInTheDocument()
  })

  it('hides the existing seed file affordance once a fresh file is staged', async () => {
    const user = userEvent.setup()
    const reposWithSeed: RepositoryConfig[] = [
      { ...repos[0], endpointFile: 'existing.json' },
    ]
    renderSection({ repositories: reposWithSeed })
    await user.selectOptions(screen.getByRole('combobox'), '101')
    const fresh = new File(['{}'], 'fresh.json', { type: 'application/json' })
    const fileInput = screen.getByLabelText(/endpoint file/i) as HTMLInputElement
    await user.upload(fileInput, fresh)
    expect(
      screen.queryByText(/current: existing\.json\./i)
    ).not.toBeInTheDocument()
  })

  it('calls onSave with isNew=true when creating a new repository', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    renderSection({ onSave })
    await user.click(screen.getByRole('button', { name: /new/i }))
    await user.type(screen.getByLabelText(/^name/i), 'newrepo')
    await user.click(screen.getByRole('button', { name: /^api$/i }))
    await user.type(screen.getByLabelText(/local path/i), '/opt/repos/newrepo')
    await user.click(screen.getByRole('button', { name: /^create$/i }))
    expect(onSave).toHaveBeenCalledTimes(1)
    const [repo, isNew] = onSave.mock.calls[0]
    expect(isNew).toBe(true)
    expect(repo.name).toBe('newrepo')
    expect(repo.localPath).toBe('/opt/repos/newrepo')
    expect(repo.types).toContain('api')
  })
})
