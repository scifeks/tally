import { useEffect, useRef, useState, type ReactNode } from "react"
import { Pencil } from "lucide-react"
import { cn } from "@/lib/utils"

/**
 * Text / textarea editable field. Affords editability via dotted underline +
 * pencil on hover; entering edit mode shows a blinking TTY cursor.
 */
export function EditableText({
  value,
  onChange,
  placeholder = "click to edit",
  multiline = false,
  className,
  valueClassName,
  inputClassName,
  ariaLabel,
}: {
  value: string
  onChange: (next: string) => void
  placeholder?: string
  multiline?: boolean
  className?: string
  /** Class applied to the displayed (read-mode) value span. */
  valueClassName?: string
  /** Class applied to the <input>/<textarea> in edit mode. */
  inputClassName?: string
  ariaLabel?: string
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null)

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus()
      if ("select" in inputRef.current) inputRef.current.select()
    }
  }, [editing])

  useEffect(() => {
    setDraft(value)
  }, [value])

  const commit = () => {
    setEditing(false)
    if (draft !== value) onChange(draft)
  }
  const cancel = () => {
    setEditing(false)
    setDraft(value)
  }

  if (editing) {
    const Tag = multiline ? "textarea" : "input"
    return (
      <div className={cn("editable-input flex items-start gap-1", className)}>
        <span className="text-accent mt-0.5 tty-cursor-inline" aria-hidden>
          &gt;
        </span>
        <Tag
          // @ts-expect-error ref typing covers both
          ref={inputRef}
          aria-label={ariaLabel}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault()
              cancel()
            }
            if (e.key === "Enter" && !multiline) {
              e.preventDefault()
              commit()
            }
            if (e.key === "Enter" && multiline && (e.metaKey || e.ctrlKey)) {
              e.preventDefault()
              commit()
            }
          }}
          rows={multiline ? 3 : undefined}
          className={cn(
            "flex-1 bg-transparent outline-none border border-accent px-2 py-1 text-foreground font-mono resize-none",
            multiline && "min-h-[72px]",
            inputClassName ?? "text-xs",
          )}
        />
      </div>
    )
  }

  const empty = !value
  return (
    <button
      type="button"
      onClick={() => setEditing(true)}
      aria-label={ariaLabel ?? "Edit"}
      className={cn(
        "group relative w-full text-left px-2 py-1 border border-transparent",
        "hover:border-dashed hover:border-accent/60 hover:bg-muted/40",
        "focus:outline-none focus:border-dashed focus:border-accent",
        className,
      )}
    >
      <span
        className={cn(
          "block whitespace-pre-wrap",
          empty ? "text-dim italic" : "text-foreground",
          valueClassName ?? "text-xs",
        )}
      >
        {empty ? placeholder : value}
      </span>
      <Pencil
        aria-hidden
        className="absolute right-1.5 top-1.5 h-3 w-3 text-dim opacity-0 group-hover:opacity-100 group-focus:opacity-100 transition-opacity"
      />
    </button>
  )
}

/**
 * Editable select/enum: shows current value; hover reveals dotted underline +
 * caret; click opens option list. Entering edit state shows tty cursor.
 */
export function EditableSelect<T extends string>({
  value,
  options,
  onChange,
  renderValue,
  ariaLabel,
  className,
}: {
  value: T
  options: { value: T; label: string; color?: string }[]
  onChange: (next: T) => void
  renderValue?: (v: T) => ReactNode
  ariaLabel?: string
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false)
    }
    document.addEventListener("mousedown", onDoc)
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("mousedown", onDoc)
      document.removeEventListener("keydown", onKey)
    }
  }, [open])

  return (
    <div ref={ref} className={cn("relative inline-block", className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={ariaLabel ?? "Edit"}
        className={cn(
          "group inline-flex items-center gap-1.5 px-2 py-1 border text-left",
          open
            ? "border-accent bg-muted"
            : "border-transparent hover:border-dashed hover:border-accent/60 hover:bg-muted/40",
        )}
      >
        {open && (
          <span className="text-accent tty-cursor-inline" aria-hidden>
            &gt;
          </span>
        )}
        <span className="text-xs">
          {renderValue ? renderValue(value) : value}
        </span>
        <Pencil
          aria-hidden
          className={cn(
            "h-3 w-3 text-dim transition-opacity",
            open ? "opacity-100" : "opacity-0 group-hover:opacity-100",
          )}
        />
      </button>
      {open && (
        <div className="absolute left-0 top-full mt-1 min-w-[160px] border border-border-strong bg-background z-40">
          {options.map((o) => {
            const active = o.value === value
            return (
              <button
                key={o.value}
                onClick={() => {
                  onChange(o.value)
                  setOpen(false)
                }}
                className={cn(
                  "w-full flex items-center gap-2 px-2 py-1.5 text-xs border-b border-border last:border-b-0 hover:bg-muted text-left",
                  active && "bg-muted",
                )}
              >
                <span className={cn("text-dim", active && "text-accent")}>
                  {active ? ">" : " "}
                </span>
                <span style={o.color ? { color: o.color } : undefined}>{o.label}</span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
