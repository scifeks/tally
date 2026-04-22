import { useMemo } from 'react'
import { cn } from '@/lib/utils'
import { useScanHistory } from '@/lib/api'

export function HistoryTable({ projectId }: { projectId: string }) {
  // TODO [BACKEND]: This hook returns mock data. Replace with real API call.
  // GET /api/v1/projects/:id/scans
  const { data: scans = [] } = useScanHistory(projectId)

  const history = useMemo(
    () =>
      scans
        .filter(s => s.projectId === projectId && s.status !== 'running')
        .sort((a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime()),
    [scans, projectId]
  )

  if (history.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center p-8 text-muted-foreground text-sm">
        No scan history for this project yet.
      </div>
    )
  }

  return (
    <div className="overflow-auto flex-1">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-muted text-muted-foreground uppercase tracking-wider">
          <tr>
            <th className="text-left px-3 py-2 font-medium">ID</th>
            <th className="text-left px-3 py-2 font-medium">Segment</th>
            <th className="text-left px-3 py-2 font-medium">Tool</th>
            <th className="text-left px-3 py-2 font-medium">Status</th>
            <th className="text-right px-3 py-2 font-medium">Findings</th>
            <th className="text-left px-3 py-2 font-medium">Started</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {history.map(scan => (
            <tr key={scan.id} className="hover:bg-muted/30">
              <td className="px-3 py-2 font-mono text-accent">{scan.id}</td>
              <td className="px-3 py-2 uppercase">{scan.segment}</td>
              <td className="px-3 py-2">{scan.tool}</td>
              <td className="px-3 py-2">
                <span
                  className={cn(
                    'uppercase',
                    scan.status === 'done' && 'text-low',
                    scan.status === 'failed' && 'text-crit'
                  )}
                >
                  {scan.status}
                </span>
              </td>
              <td className="px-3 py-2 text-right tabular-nums">{scan.findingsCount ?? '-'}</td>
              <td className="px-3 py-2 text-muted-foreground">
                {new Date(scan.startedAt).toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
