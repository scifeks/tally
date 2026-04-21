import { Panel } from "@/components/tty"
import { EditableText, EditableSelect } from "@/components/Editable"
import { cn, formatRelative } from "@/lib/utils"
import type { Finding, Severity, Status } from "@/lib/types"
import {
  SEV_ORDER,
  SEV_LABEL,
  SEV_COLOR,
  STATUS_ORDER,
  STATUS_LABEL,
  STATUS_COLOR,
} from "./constants"

// ─── Field ────────────────────────────────────────────────────────────────────

function Field({
  label,
  value,
  mono,
  accent,
}: {
  label: string
  value: string
  mono?: boolean
  accent?: boolean
}) {
  return (
    <div className="flex items-baseline gap-3">
      <div className="w-20 shrink-0 text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
        {label}
      </div>
      <div
        className={cn(
          "flex-1",
          mono && "font-mono",
          accent ? "text-primary" : "text-foreground",
        )}
      >
        {value}
      </div>
    </div>
  )
}

// ─── FindingDetailPanel ───────────────────────────────────────────────────────

export function FindingDetailPanel({
  finding,
  onUpdate,
}: {
  finding: Finding | null
  onUpdate: (patch: Partial<Finding>) => void
}) {
  if (!finding) {
    return (
      <Panel title="detail" className="h-full">
        <div className="p-6 text-xs text-muted-foreground leading-relaxed">
          <div className="text-dim mb-2">// no finding selected</div>
          click a row to inspect it.
        </div>
      </Panel>
    )
  }
  return (
    <Panel
      title={`detail :: ${finding.id}`}
      className="h-full"
      bodyClassName="overflow-auto"
    >
      <div className="p-4 space-y-4 text-xs">
        {/* Header row: editable severity + status, read-only timestamp */}
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
              severity
            </span>
            <EditableSelect<Severity>
              value={finding.severity}
              options={SEV_ORDER.map((s) => ({
                value: s,
                label: SEV_LABEL[s],
                color: SEV_COLOR[s],
              }))}
              onChange={(next) => onUpdate({ severity: next })}
              ariaLabel="Edit severity"
              renderValue={(v) => (
                <span
                  className="uppercase tracking-wider font-bold"
                  style={{ color: SEV_COLOR[v] }}
                >
                  {SEV_LABEL[v]}
                </span>
              )}
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
              status
            </span>
            <EditableSelect<Status>
              value={finding.status}
              options={STATUS_ORDER.map((s) => ({
                value: s,
                label: STATUS_LABEL[s],
                color: STATUS_COLOR[s],
              }))}
              onChange={(next) => onUpdate({ status: next })}
              ariaLabel="Edit status"
              renderValue={(v) => (
                <span
                  className="uppercase tracking-wider"
                  style={{ color: STATUS_COLOR[v] }}
                >
                  {STATUS_LABEL[v]}
                </span>
              )}
            />
          </div>
          <span className="ml-auto text-muted-foreground">
            {formatRelative(finding.discoveredAt)}
          </span>
        </div>

        {/* Editable title */}
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-1 flex items-center gap-2">
            <span>title</span>
            <span className="text-dim normal-case tracking-normal">
              // click to edit
            </span>
          </div>
          <EditableText
            value={finding.title}
            onChange={(next) => onUpdate({ title: next })}
            ariaLabel="Edit finding title"
            valueClassName="text-sm text-primary tty-glow leading-relaxed"
            inputClassName="text-sm"
          />
        </div>

        <Field label="domain" value={finding.domain.toUpperCase()} />
        <Field label="tool" value={finding.tool} />
        <Field label="target" value={finding.target} mono />
        {finding.file && (
          <Field label="file" value={`${finding.file}:${finding.line ?? ""}`} mono />
        )}
        {finding.commitHash && (
          <Field label="commit" value={finding.commitHash} mono accent />
        )}
        {finding.cwe && <Field label="cwe" value={finding.cwe} />}

        {/* Editable notes */}
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-1 flex items-center gap-2">
            <span>notes</span>
            <span className="text-dim normal-case tracking-normal">
              // click to edit
            </span>
          </div>
          <EditableText
            value={finding.notes ?? ""}
            onChange={(next) => onUpdate({ notes: next })}
            multiline
            placeholder="// add triage notes..."
            ariaLabel="Edit notes"
          />
        </div>

        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-2">
            description
          </div>
          <div className="border border-border p-3 text-foreground leading-relaxed bg-muted/30">
            <span className="text-dim">$</span> cat finding/{finding.id}.md
            <br />
            Placeholder description rendered by the FastAPI backend. This field
            will carry full remediation guidance, CVSS vector, references, and
            code context when the real API is wired in.
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 pt-2">
          <button
            onClick={() => onUpdate({ status: "triaged" })}
            className="text-[11px] uppercase tracking-wider py-1.5 border border-accent text-accent hover:bg-muted"
          >
            &gt; triage
          </button>
          <button
            onClick={() => onUpdate({ status: "fixed" })}
            className="text-[11px] uppercase tracking-wider py-1.5 border border-border-strong text-foreground hover:bg-muted"
          >
            mark fixed
          </button>
          <button
            onClick={() => onUpdate({ status: "false_positive" })}
            className="text-[11px] uppercase tracking-wider py-1.5 border border-border text-muted-foreground hover:bg-muted"
          >
            false-pos
          </button>
          <button
            onClick={() => onUpdate({ status: "wontfix" })}
            className="text-[11px] uppercase tracking-wider py-1.5 border border-border text-muted-foreground hover:bg-muted"
          >
            wontfix
          </button>
        </div>
      </div>
    </Panel>
  )
}
