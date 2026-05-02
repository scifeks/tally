import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { DraftCard } from '@/pages/Reports/DraftCard'
import type { ReportDraft, ReportDraftStatus } from '@/lib/types'
import { server } from '../../../handlers'
import { clearAllCookies, setCookie } from '../../../helpers/cookies'

function makeDraft(status: ReportDraftStatus, extras: Partial<ReportDraft> = {}): ReportDraft {
  return {
    section: 'executive-summary',
    status,
    ...extras,
  }
}

interface RenderProps {
  draft: ReportDraft
  onGenerate?: (force: boolean) => void
  onUpload?: (file: File) => void
  onDelete?: () => void
  isGenerating?: boolean
  skipTriage?: boolean
}

function renderCard(props: RenderProps) {
  return render(
    <DraftCard
      projectId={1}
      draft={props.draft}
      onGenerate={props.onGenerate ?? (() => undefined)}
      onUpload={props.onUpload ?? (() => undefined)}
      onDelete={props.onDelete ?? (() => undefined)}
      isGenerating={props.isGenerating ?? false}
      skipTriage={props.skipTriage ?? false}
    />
  )
}

beforeEach(() => {
  clearAllCookies()
  setCookie('tally_csrf', 'test-csrf-token')
})

afterEach(() => server.resetHandlers())

describe('DraftCard - generate vs regenerate affordance', () => {
  it('renders Generate (not Regenerate) when status is not_generated and forwards force=false', async () => {
    const onGenerate = vi.fn()
    const user = userEvent.setup()
    renderCard({ draft: makeDraft('not_generated'), onGenerate })

    expect(screen.getByText(/not generated/i)).toBeInTheDocument()
    expect(screen.queryByTestId('report-draft-executive-summary-regenerate')).toBeNull()

    await user.click(screen.getByTestId('report-draft-executive-summary-generate'))
    expect(onGenerate).toHaveBeenCalledTimes(1)
    expect(onGenerate).toHaveBeenCalledWith(false)
  })

  it('renders the Regenerate icon button when status is draft and forwards force=true', async () => {
    const onGenerate = vi.fn()
    const user = userEvent.setup()
    renderCard({ draft: makeDraft('draft'), onGenerate })

    expect(screen.getByText(/draft ready/i)).toBeInTheDocument()
    expect(screen.queryByTestId('report-draft-executive-summary-generate')).toBeNull()

    await user.click(screen.getByTestId('report-draft-executive-summary-regenerate'))
    expect(onGenerate).toHaveBeenCalledTimes(1)
    expect(onGenerate).toHaveBeenCalledWith(true)
  })
})

describe('DraftCard - status badge copy per status', () => {
  it.each([
    ['reviewed', /reviewed/i],
    ['generating', /generating/i],
    ['failed', /failed/i],
  ] as const)('%s status renders the matching badge copy', (status, badgeRegex) => {
    renderCard({ draft: makeDraft(status) })
    expect(screen.getByText(badgeRegex)).toBeInTheDocument()
  })
})

describe('DraftCard - delete with window.confirm gate', () => {
  it('confirms then calls onDelete, and is a no-op when confirm returns false', async () => {
    const onDelete = vi.fn()
    const confirmSpy = vi.spyOn(window, 'confirm')
    const user = userEvent.setup()
    renderCard({ draft: makeDraft('draft'), onDelete })

    confirmSpy.mockReturnValueOnce(true)
    await user.click(screen.getByTestId('report-draft-executive-summary-delete'))
    expect(onDelete).toHaveBeenCalledTimes(1)

    confirmSpy.mockReturnValueOnce(false)
    await user.click(screen.getByTestId('report-draft-executive-summary-delete'))
    expect(onDelete).toHaveBeenCalledTimes(1)

    confirmSpy.mockRestore()
  })
})
