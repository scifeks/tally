import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { HistoryTable } from '@/pages/Reports/HistoryTable'
import type { ReportHistoryEntry } from '@/lib/types'
import { server } from '../../../handlers'
import { clearAllCookies, setCookie } from '../../../helpers/cookies'

beforeEach(() => {
  clearAllCookies()
  setCookie('tally_csrf', 'test-csrf-token')
})

afterEach(() => server.resetHandlers())

describe('Reports HistoryTable', () => {
  it('renders the empty-state copy when entries is empty', () => {
    render(<HistoryTable projectId={1} entries={[]} />)
    expect(screen.getByText(/no reports generated yet/i)).toBeInTheDocument()
  })

  it('routes each row download click to /reports/:reportId/download for the matching entry', async () => {
    const calledUrls: string[] = []
    server.use(
      http.get('/api/v1/projects/1/reports/:reportId/download', ({ request }) => {
        calledUrls.push(new URL(request.url).pathname)
        return new HttpResponse(new Uint8Array([0x25, 0x50, 0x44, 0x46]), {
          status: 200,
          headers: { 'Content-Type': 'application/pdf' },
        })
      })
    )

    const entries: ReportHistoryEntry[] = [
      {
        id: 4001,
        projectId: 1,
        filename: 'acme-pentest.pdf',
        format: 'pdf',
        generatedAt: '2026-04-29T10:00:00Z',
        sizeBytes: 245_000,
        downloadUrl: '/api/v1/projects/1/reports/4001/download',
      },
      {
        id: 4002,
        projectId: 1,
        filename: 'acme-pentest.html',
        format: 'html',
        generatedAt: '2026-04-30T14:00:00Z',
        sizeBytes: 80_000,
        downloadUrl: '/api/v1/projects/1/reports/4002/download',
      },
    ]
    render(<HistoryTable projectId={1} entries={entries} />)

    const user = userEvent.setup()
    await user.click(screen.getByTestId('report-history-download-4002'))
    await user.click(screen.getByTestId('report-history-download-4001'))

    expect(calledUrls).toEqual([
      '/api/v1/projects/1/reports/4002/download',
      '/api/v1/projects/1/reports/4001/download',
    ])
  })
})
