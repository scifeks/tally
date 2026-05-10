import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { ToolOverridesSection } from '@/pages/Config/ToolOverridesSection'
import type { ToolCatalogEntry, ToolOverrideConfig } from '@/lib/types'
import { server } from '../../../handlers'
import { clearAllCookies, setCookie } from '../../../helpers/cookies'

const PROJECT_ID = 2

const catalog: ToolCatalogEntry[] = [
  { id: 'gitleaks', name: 'gitleaks', supportsLocal: true, supportsDocker: true },
  { id: 'semgrep', name: 'semgrep', supportsLocal: true, supportsDocker: true },
]

const gitleaksOverride: ToolOverrideConfig = {
  toolId: 'gitleaks',
  type: 'repo',
  location: 'docker',
  container: { name: 'gitleaks-runner', toolPath: '/usr/local/bin/gitleaks' },
}

function makeQC() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
}

function renderSection(opts?: {
  overrides?: ToolOverrideConfig[]
  onSave?: (override: ToolOverrideConfig, isNew: boolean) => void
  onDelete?: (toolId: string) => void
}) {
  const onSave = opts?.onSave ?? vi.fn()
  const onDelete = opts?.onDelete ?? vi.fn()
  const overrides = opts?.overrides ?? [gitleaksOverride]
  const utils = render(
    <QueryClientProvider client={makeQC()}>
      <ToolOverridesSection
        catalog={catalog}
        overrides={overrides}
        projectId={PROJECT_ID}
        onSave={onSave}
        onDelete={onDelete}
        isSaving={false}
      />
    </QueryClientProvider>
  )
  return { ...utils, onSave, onDelete }
}

async function selectGitleaksOverride() {
  const user = userEvent.setup()
  const overrideSelect = screen.getAllByRole('combobox')[0] as HTMLSelectElement
  await user.selectOptions(overrideSelect, 'gitleaks')
  return user
}

async function flipToCustomArgs(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: /^custom$/i }))
}

async function expandTemplatesPanel(user: ReturnType<typeof userEvent.setup>) {
  const header = screen.getByRole('button', { name: /argument templates/i })
  if (!header.querySelector('svg.lucide-chevron-down')) {
    await user.click(header)
  }
}

async function waitForExistingTemplate(
  user: ReturnType<typeof userEvent.setup>,
  name: string
) {
  await expandTemplatesPanel(user)
  await waitFor(() => {
    expect(screen.getByText(name)).toBeInTheDocument()
  })
}

beforeEach(() => {
  clearAllCookies()
  setCookie('tally_csrf', 'test-csrf-token')
})

afterEach(() => server.resetHandlers())

describe('ArgumentTemplateEditor (integration)', () => {
  it('reveals the templates panel when args-mode flips from stock to custom', async () => {
    renderSection()
    const user = await selectGitleaksOverride()

    expect(screen.queryByText(/argument templates/i)).not.toBeInTheDocument()
    await flipToCustomArgs(user)
    expect(screen.getByText(/argument templates/i)).toBeInTheDocument()
  })

  it('rehydrates fileName from the server payload so existing file args show the chip', async () => {
    renderSection()
    const user = await selectGitleaksOverride()
    await flipToCustomArgs(user)
    await waitForExistingTemplate(user, 'with-config')

    await user.click(screen.getAllByRole('button', { name: /^edit$/i })[1])
    expect(screen.getByText('--config')).toBeInTheDocument()
  })

  it('Add Template appends an empty template and opens it inline', async () => {
    renderSection()
    const user = await selectGitleaksOverride()
    await flipToCustomArgs(user)
    await waitForExistingTemplate(user, 'verbose-only')

    await user.click(screen.getByRole('button', { name: /add template/i }))
    expect(screen.getByLabelText(/template name/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/argument flag/i)).toHaveValue('')
  })

  it('saves a new template via POST with the mapped JSON payload', async () => {
    server.use(
      http.get(`/api/v1/projects/${PROJECT_ID}/arg-profiles`, () =>
        HttpResponse.json({ items: [], total: 0, offset: 0, limit: 50 })
      )
    )
    let capturedPayload: unknown = null
    server.use(
      http.post(`/api/v1/projects/${PROJECT_ID}/arg-profiles`, async ({ request }) => {
        const form = await request.formData()
        const raw = form.get('payload') as string
        capturedPayload = JSON.parse(raw)
        return HttpResponse.json(
          {
            id: 99,
            toolName: 'gitleaks',
            name: 'fresh',
            args: [{ name: '--verbose', type: 'flag' }],
            createdAt: '2026-05-05T00:00:00+00:00',
            updatedAt: '2026-05-05T00:00:00+00:00',
          },
          { status: 201 }
        )
      })
    )

    renderSection()
    const user = await selectGitleaksOverride()
    await flipToCustomArgs(user)

    await user.click(screen.getByRole('button', { name: /add template/i }))

    const nameInput = screen.getByLabelText(/template name/i)
    await user.clear(nameInput)
    await user.type(nameInput, 'fresh')
    const flagInput = screen.getByLabelText(/argument flag/i)
    await user.type(flagInput, '--verbose')

    await user.click(screen.getByRole('button', { name: /^done$/i }))
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => {
      expect(capturedPayload).toEqual({
        toolName: 'gitleaks',
        name: 'fresh',
        args: [{ name: '--verbose', type: 'flag' }],
      })
    })
  })

  it('uploads a fresh File as a multipart sibling field keyed by the arg name', async () => {
    server.use(
      http.get(`/api/v1/projects/${PROJECT_ID}/arg-profiles`, () =>
        HttpResponse.json({ items: [], total: 0, offset: 0, limit: 50 })
      )
    )
    let capturedContentType: string | null = null
    let capturedBody: string | null = null
    server.use(
      http.post(`/api/v1/projects/${PROJECT_ID}/arg-profiles`, async ({ request }) => {
        capturedContentType = request.headers.get('Content-Type')
        capturedBody = await request.text()
        return HttpResponse.json(
          {
            id: 100,
            toolName: 'gitleaks',
            name: 'with-rules',
            args: [{ name: '--rules', type: 'file', path: 'arg_files/100/--rules' }],
            createdAt: '2026-05-05T00:00:00+00:00',
            updatedAt: '2026-05-05T00:00:00+00:00',
          },
          { status: 201 }
        )
      })
    )

    const { container } = renderSection()
    const user = await selectGitleaksOverride()
    await flipToCustomArgs(user)

    await user.click(screen.getByRole('button', { name: /add template/i }))

    await user.clear(screen.getByLabelText(/template name/i))
    await user.type(screen.getByLabelText(/template name/i), 'with-rules')
    await user.type(screen.getByLabelText(/argument flag/i), '--rules')
    await user.selectOptions(screen.getByLabelText(/value type/i), 'file')

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    const picked = new File(['rule-bytes'], 'rules.yml', { type: 'text/yaml' })
    await user.upload(fileInput, picked)

    await user.click(screen.getByRole('button', { name: /^done$/i }))
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => expect(capturedBody).not.toBeNull())
    expect(capturedContentType).toMatch(/multipart\/form-data/)
    expect(capturedBody).toContain('name="--rules"; filename=')
    const payloadMatch = capturedBody!.match(
      /name="payload"\r?\n\r?\n([\s\S]*?)\r?\n--/
    )
    expect(payloadMatch).not.toBeNull()
    const payload = JSON.parse(payloadMatch![1])
    expect(payload.toolName).toBe('gitleaks')
    expect(payload.name).toBe('with-rules')
    expect(payload.args).toEqual([{ name: '--rules', type: 'file', path: '', operator: '' }])
  })

  it('issues DELETE for a server-backed template the user removed before saving', async () => {
    let deletedId: string | null = null
    server.use(
      http.delete(
        `/api/v1/projects/${PROJECT_ID}/arg-profiles/:profileId`,
        ({ params }) => {
          deletedId = params.profileId as string
          return new HttpResponse(null, { status: 204 })
        }
      )
    )

    renderSection()
    const user = await selectGitleaksOverride()
    await flipToCustomArgs(user)
    await waitForExistingTemplate(user, 'verbose-only')

    const verboseRow = screen.getByText('verbose-only').closest('div[class*="border"]')
    await user.click(within(verboseRow as HTMLElement).getByLabelText(/delete template/i))

    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => expect(deletedId).toBe('1'))
  })

  it('issues PUT when an existing templates flag changes (profileMatchesTemplate=false)', async () => {
    let putBody: { args?: Array<{ name: string }> } | null = null
    let putId: string | null = null
    server.use(
      http.put(
        `/api/v1/projects/${PROJECT_ID}/arg-profiles/:profileId`,
        async ({ params, request }) => {
          const form = await request.formData()
          putBody = JSON.parse(form.get('payload') as string)
          putId = params.profileId as string
          return HttpResponse.json({
            id: Number(params.profileId),
            toolName: 'gitleaks',
            name: 'verbose-only',
            args: [{ name: '--debug', type: 'flag' }],
            createdAt: '2026-05-05T00:00:00+00:00',
            updatedAt: '2026-05-05T00:00:00+00:00',
          })
        }
      )
    )

    renderSection()
    const user = await selectGitleaksOverride()
    await flipToCustomArgs(user)
    await waitForExistingTemplate(user, 'verbose-only')

    const verboseRow = screen.getByText('verbose-only').closest('div[class*="border"]')
    await user.click(within(verboseRow as HTMLElement).getByRole('button', { name: /^edit$/i }))

    const flagInput = screen.getByLabelText(/argument flag/i)
    await user.clear(flagInput)
    await user.type(flagInput, '--debug')

    await user.click(screen.getByRole('button', { name: /^done$/i }))
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => expect(putId).toBe('1'))
    expect(putBody?.args?.[0].name).toBe('--debug')
  })

  it('issues PUT when only a fresh File is picked on an otherwise unchanged template', async () => {
    let putId: string | null = null
    let putBody: string | null = null
    server.use(
      http.put(
        `/api/v1/projects/${PROJECT_ID}/arg-profiles/:profileId`,
        async ({ params, request }) => {
          putId = params.profileId as string
          putBody = await request.text()
          return HttpResponse.json({
            id: Number(params.profileId),
            toolName: 'gitleaks',
            name: 'with-config',
            args: [
              { name: '--config', type: 'file', path: `arg_files/${params.profileId}/--config` },
            ],
            createdAt: '2026-05-05T00:00:00+00:00',
            updatedAt: '2026-05-05T00:00:00+00:00',
          })
        }
      )
    )

    const { container } = renderSection()
    const user = await selectGitleaksOverride()
    await flipToCustomArgs(user)
    await waitForExistingTemplate(user, 'with-config')

    const configRow = screen.getByText('with-config').closest('div[class*="border"]')
    await user.click(within(configRow as HTMLElement).getByRole('button', { name: /^edit$/i }))

    await user.click(screen.getByLabelText(/remove file/i))

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    const picked = new File(['fresh-bytes'], '--config', { type: 'application/octet-stream' })
    await user.upload(fileInput, picked)

    await user.click(screen.getByRole('button', { name: /^done$/i }))
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => expect(putId).toBe('3'))
    expect(putBody).toContain('name="--config"; filename=')
  })
})
