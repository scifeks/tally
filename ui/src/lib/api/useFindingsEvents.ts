/**
 * useFindingsEvents - subscribe to the project-scoped `finding_updated`
 * SSE stream and patch the TanStack Query cache directly.
 *
 * Per `decisions.md` B13 the SPA does not refetch the list when an event
 * arrives - the event payload is the full serialized finding row, so we
 * locate it across every cached page of `['findings', projectId, *]`
 * and replace it in place. When the event reports a different
 * `severity` or `status` than the previously cached row,
 * `['findingsCounts', projectId]` is invalidated so dashboard tiles
 * refresh.
 *
 * The hook is a no-op when `projectId` is empty (no project selected).
 */

import { useEffect } from 'react'
import { useQueryClient, type QueryKey } from '@tanstack/react-query'
import { apiEventSource } from './sse'
import { SSE_ENDPOINTS } from './config'
import { mapFinding } from './useFindings'
import type { Finding } from '../types'

interface FindingsPageShape {
  items: Finding[]
  total: number
  offset: number
  limit: number
}

interface InfiniteFindingsCache {
  pages: FindingsPageShape[]
  pageParams: unknown[]
}

type FindingApiPayload = Parameters<typeof mapFinding>[0]

export function useFindingsEvents(projectId: string): void {
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!projectId) return
    const handle = apiEventSource(SSE_ENDPOINTS.findingsEvents(projectId), {
      eventTypes: ['finding_updated'],
      onEvent: (_type, raw) => {
        if (!raw || typeof raw !== 'object') return
        const updated = mapFinding(raw as FindingApiPayload)
        const entries = queryClient.getQueriesData<InfiniteFindingsCache>({
          queryKey: ['findings', projectId],
        })
        let counted = false
        let prevSeverity: string | undefined
        let prevStatus: string | undefined
        for (const [key, cache] of entries as Array<
          [QueryKey, InfiniteFindingsCache | undefined]
        >) {
          if (!cache) continue
          let touched = false
          const nextPages = cache.pages.map(page => {
            const nextItems = page.items.map(item => {
              if (item.id !== updated.id) return item
              if (!counted) {
                prevSeverity = item.severity
                prevStatus = item.status
                counted = true
              }
              touched = true
              return updated
            })
            return touched ? { ...page, items: nextItems } : page
          })
          if (touched) {
            queryClient.setQueryData<InfiniteFindingsCache>(key, { ...cache, pages: nextPages })
          }
        }
        if (counted && (prevSeverity !== updated.severity || prevStatus !== updated.status)) {
          queryClient.invalidateQueries({ queryKey: ['findingsCounts', projectId] })
        }
      },
    })
    return () => handle.close()
  }, [projectId, queryClient])
}
