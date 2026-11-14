import { describe, it, expect, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React, { type ReactNode } from 'react'
import { useBurpPollStatus, useStartBurpPoll, useCancelBurpPoll } from '../../../../src/lib/api/useBurpPoll'

vi.mock('../../../../src/lib/api/client', () => ({
  apiFetch: vi.fn(),
}))

import { apiFetch } from '../../../../src/lib/api/client'
const mockApiFetch = vi.mocked(apiFetch)

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return React.createElement(QueryClientProvider, { client: qc }, children)
}

describe('useBurpPollStatus', () => {
  it('maps snake_case response to camelCase', async () => {
    mockApiFetch.mockResolvedValueOnce({
      project_id: 1,
      configured: true,
      active: false,
    })

    const { result } = renderHook(
      () => useBurpPollStatus(1),
      { wrapper }
    )

    await waitFor(() =>
      expect(result.current.isSuccess).toBe(true)
    )
    expect(result.current.data).toEqual({
      projectId: 1,
      configured: true,
      active: false,
    })
  })
})

describe('useStartBurpPoll', () => {
  it('calls start endpoint with POST', async () => {
    mockApiFetch.mockResolvedValueOnce({
      project_id: 1,
      status: 'polling',
    })

    const { result } = renderHook(
      () => useStartBurpPoll(),
      { wrapper }
    )

    result.current.mutate({ projectId: 1 })

    await waitFor(() =>
      expect(result.current.isSuccess).toBe(true)
    )
    expect(mockApiFetch).toHaveBeenCalledWith(
      expect.stringContaining('/burp/poll'),
      { method: 'POST' }
    )
  })
})

describe('useCancelBurpPoll', () => {
  it('calls cancel endpoint with POST', async () => {
    mockApiFetch.mockResolvedValueOnce({
      project_id: 1,
      status: 'stopping',
    })

    const { result } = renderHook(
      () => useCancelBurpPoll(),
      { wrapper }
    )

    result.current.mutate({ projectId: 1 })

    await waitFor(() =>
      expect(result.current.isSuccess).toBe(true)
    )
    expect(mockApiFetch).toHaveBeenCalledWith(
      expect.stringContaining('/burp/poll/cancel'),
      { method: 'POST' }
    )
  })
})
