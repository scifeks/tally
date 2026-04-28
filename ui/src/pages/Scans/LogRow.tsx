import { cn } from '@/lib/utils'
import type { ScanLogEvent, ScanLogEventType } from '@/lib/types'

const TYPE_STYLE: Record<ScanLogEventType, { color: string; prefix: string }> = {
  run_started: { color: 'text-accent', prefix: '>>>' },
  segment_started: { color: 'text-accent', prefix: '===' },
  tool_started: { color: 'text-muted-foreground', prefix: '[*]' },
  tool_skipped: { color: 'text-dim', prefix: '[-]' },
  tool_completed: { color: 'text-low', prefix: '[+]' },
  tool_failed: { color: 'text-crit', prefix: '[!]' },
  enrichment_progress: { color: 'text-muted-foreground', prefix: '   ' },
  enrichment_complete: { color: 'text-low', prefix: '   ' },
  segment_completed: { color: 'text-accent', prefix: '===' },
  run_completed: { color: 'text-accent', prefix: '>>>' },
  run_cancelled: { color: 'text-high', prefix: 'XXX' },
  run_failed: { color: 'text-crit', prefix: '!!!' },
}

export function LogRow({ event }: { event: ScanLogEvent }) {
  const time = new Date(event.timestamp).toLocaleTimeString('en-US', { hour12: false })
  const style = TYPE_STYLE[event.type]

  return (
    <div className="flex items-start gap-3 text-xs font-mono leading-relaxed py-0.5 px-3 hover:bg-muted/30">
      <span className="text-dim shrink-0 tabular-nums">{time}</span>
      <span className={cn('shrink-0 font-bold', style.color)}>{style.prefix}</span>
      <span className={cn('flex-1', style.color)}>{event.message}</span>
      {event.findingsCount !== undefined && (
        <span className="text-accent tabular-nums">{event.findingsCount} findings</span>
      )}
      {event.duration !== undefined && (
        <span className="text-dim tabular-nums">{event.duration.toFixed(1)}s</span>
      )}
    </div>
  )
}
