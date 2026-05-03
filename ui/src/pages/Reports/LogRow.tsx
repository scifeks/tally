import { cn, formatTime } from '@/lib/utils'
import type { ReportLogEvent } from '@/lib/types'

const TYPE_COLORS: Record<string, string> = {
  generation_started: 'text-accent',
  step_started: 'text-muted-foreground',
  step_completed: 'text-good',
  step_failed: 'text-crit',
  generation_completed: 'text-good',
  generation_failed: 'text-crit',
  draft_started: 'text-warn',
  draft_completed: 'text-good',
  draft_failed: 'text-crit',
}

export function LogRow({ event }: { event: ReportLogEvent }) {
  const time = formatTime(event.timestamp)

  return (
    <div className="flex items-start gap-3 px-3 py-1.5 font-mono text-[11px] hover:bg-muted/20">
      <span className="text-dim shrink-0">{time}</span>
      <span className={cn('uppercase shrink-0 w-24', TYPE_COLORS[event.type] ?? 'text-foreground')}>
        {event.type.replace(/_/g, ' ')}
      </span>
      <span className="text-foreground flex-1">{event.message}</span>
    </div>
  )
}
