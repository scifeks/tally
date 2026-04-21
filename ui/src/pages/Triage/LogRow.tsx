import { cn } from "@/lib/utils"
import type { TriageLogEvent, TriageLogEventType } from "@/lib/types"

const TYPE_STYLE: Record<TriageLogEventType, { color: string; prefix: string }> = {
  run_started: { color: "text-accent", prefix: ">>>" },
  batch_created: { color: "text-muted-foreground", prefix: "[+]" },
  batch_started: { color: "text-high", prefix: "[*]" },
  batch_progress: { color: "text-muted-foreground", prefix: "   " },
  batch_completed: { color: "text-low", prefix: "[✓]" },
  batch_failed: { color: "text-crit", prefix: "[!]" },
  batch_retry: { color: "text-high", prefix: "[↻]" },
  run_completed: { color: "text-accent", prefix: ">>>" },
  run_cancelled: { color: "text-high", prefix: "XXX" },
}

export function LogRow({ event }: { event: TriageLogEvent }) {
  const time = new Date(event.timestamp).toLocaleTimeString("en-US", { hour12: false })
  const style = TYPE_STYLE[event.type]

  return (
    <div className="flex items-start gap-3 text-xs font-mono leading-relaxed py-0.5 px-3 hover:bg-muted/30">
      <span className="text-dim shrink-0 tabular-nums">{time}</span>
      <span className={cn("shrink-0 font-bold", style.color)}>{style.prefix}</span>
      <span className={cn("flex-1", style.color)}>{event.message}</span>
      {event.processedCount !== undefined && event.totalCount !== undefined && (
        <span className="text-accent tabular-nums">
          {event.processedCount}/{event.totalCount}
        </span>
      )}
    </div>
  )
}
