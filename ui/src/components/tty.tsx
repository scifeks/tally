import type { ReactNode, HTMLAttributes } from "react"
import { cn } from "@/lib/utils"
import type { Severity, Status } from "@/lib/types"

/** Box-drawing framed panel, e.g. ┌── TITLE ──┐ with body inside. */
export function Panel({
  title,
  right,
  children,
  className,
  bodyClassName,
}: {
  title?: string
  right?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}) {
  return (
    <section
      className={cn(
        "border border-border bg-background flex flex-col min-h-0",
        className,
      )}
    >
      {title && (
        <header className="flex items-center justify-between border-b border-border px-3 h-8 shrink-0">
          <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-primary">
            <span className="text-dim">[</span>
            <span>{title}</span>
            <span className="text-dim">]</span>
          </div>
          {right && <div className="text-xs text-muted-foreground">{right}</div>}
        </header>
      )}
      <div className={cn("flex-1 min-h-0", bodyClassName)}>{children}</div>
    </section>
  )
}

export function SeverityChip({ severity }: { severity: Severity }) {
  const map: Record<Severity, { label: string; cls: string }> = {
    critical: { label: "CRIT", cls: "text-crit border-crit" },
    high: { label: "HIGH", cls: "text-high border-high" },
    medium: { label: "MED", cls: "text-med border-med" },
    low: { label: "LOW", cls: "text-low border-low" },
    info: { label: "INFO", cls: "text-info border-info" },
  }
  const s = map[severity]
  return (
    <span
      className={cn(
        "inline-flex items-center justify-center px-1.5 h-5 text-[10px] font-bold uppercase tracking-wider border",
        s.cls,
      )}
      style={{ borderColor: "currentColor" }}
    >
      {s.label}
    </span>
  )
}

export function StatusChip({ status }: { status: Status }) {
  const map: Record<Status, { label: string; cls: string }> = {
    open: { label: "open", cls: "text-high" },
    triaged: { label: "triaged", cls: "text-info" },
    fixed: { label: "fixed", cls: "text-low" },
    wontfix: { label: "wontfix", cls: "text-muted-foreground" },
    false_positive: { label: "false-pos", cls: "text-muted-foreground" },
  }
  const s = map[status]
  return <span className={cn("text-[11px] uppercase tracking-wider", s.cls)}>{s.label}</span>
}

/** Big terminal-looking key → value metric tile. */
export function Metric({
  label,
  value,
  hint,
  accent,
}: {
  label: string
  value: string | number
  hint?: string
  accent?: "crit" | "high" | "med" | "low" | "primary"
}) {
  const accentCls = {
    crit: "text-crit",
    high: "text-high",
    med: "text-med",
    low: "text-low",
    primary: "text-primary",
  }[accent ?? "primary"]
  return (
    <div className="border border-border bg-background p-3 flex flex-col gap-1">
      <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">{label}</div>
      <div className={cn("text-3xl leading-none font-bold tabular-nums", accentCls)}>{value}</div>
      {hint && <div className="text-[11px] text-muted-foreground">{hint}</div>}
    </div>
  )
}

export function Bar({ value, max, className }: { value: number; max: number; className?: string }) {
  const pct = max === 0 ? 0 : Math.min(100, (value / max) * 100)
  return (
    <div className={cn("h-1.5 w-full bg-muted border border-border", className)}>
      <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
    </div>
  )
}

export function Row(props: HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={cn("flex items-center gap-2", props.className)} />
}
