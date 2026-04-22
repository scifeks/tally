import { ChevronDown, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Segment, TriageBatchStatus } from '@/lib/types'

const SEGMENT_LABEL: Record<Segment, string> = {
  sast: 'SAST',
  sca: 'SCA',
  web: 'WEB',
  secrets: 'SECRETS',
}

export interface BatchDisplay {
  id: string
  segment: Segment
  findingCount: number
  status: TriageBatchStatus
  attempt: number
  startedAt?: string
  finishedAt?: string
}

export function BatchRow({
  batch,
  expanded,
  onToggle,
}: {
  batch: BatchDisplay
  expanded: boolean
  onToggle: () => void
}) {
  const statusColor: Record<TriageBatchStatus, string> = {
    pending: 'text-dim',
    in_progress: 'text-high animate-pulse',
    completed: 'text-low',
    failed: 'text-crit',
  }

  return (
    <div className="border-b border-border last:border-b-0">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-3 py-2 text-xs hover:bg-muted/30 transition-colors"
      >
        {expanded ? (
          <ChevronDown className="h-3 w-3 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-3 w-3 text-muted-foreground" />
        )}
        <span className="text-accent font-mono w-20">{batch.id}</span>
        <span className="uppercase text-muted-foreground w-16">{SEGMENT_LABEL[batch.segment]}</span>
        <span className="tabular-nums w-20">{batch.findingCount} findings</span>
        <span className={cn('uppercase font-bold w-24', statusColor[batch.status])}>
          {batch.status.replace('_', ' ')}
        </span>
        {batch.attempt > 1 && (
          <span className="text-high text-[10px]">attempt #{batch.attempt}</span>
        )}
        <span className="flex-1" />
        {batch.finishedAt && (
          <span className="text-muted-foreground">
            {new Date(batch.finishedAt).toLocaleTimeString('en-US', { hour12: false })}
          </span>
        )}
      </button>
      {expanded && (
        <div className="px-6 py-2 bg-muted/20 text-[11px] text-muted-foreground border-t border-border">
          <div className="font-mono">
            {'// Claude analysis for '}
            {batch.findingCount}
            {' findings in '}
            {SEGMENT_LABEL[batch.segment]}
            <br />
            {
              '// Prompt: Analyze security findings, provide severity assessment, recommend actions...'
            }
          </div>
        </div>
      )}
    </div>
  )
}
