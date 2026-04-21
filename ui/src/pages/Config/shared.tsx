import { useState } from "react"
import type { ComponentType, ReactNode } from "react"
import { cn } from "@/lib/utils"

// ─── Section Header ───────────────────────────────────────────────────────────

export function SectionHeader({
  icon: Icon,
  title,
  children,
}: {
  icon: ComponentType<{ className?: string }>
  title: string
  children?: ReactNode
}) {
  return (
    <div className="flex items-center justify-between mb-4">
      <div className="flex items-center gap-3">
        <Icon className="h-4 w-4 text-accent" />
        <span className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
          <span className="text-accent">[</span> {title} <span className="text-accent">]</span>
        </span>
      </div>
      {children}
    </div>
  )
}

// ─── Tag Input ────────────────────────────────────────────────────────────────

export function TagInput({
  value,
  onChange,
  placeholder,
  disabled,
}: {
  value: string[]
  onChange: (tags: string[]) => void
  placeholder?: string
  disabled?: boolean
}) {
  const [input, setInput] = useState("")

  const addTag = () => {
    const tag = input.trim()
    if (tag && !value.includes(tag)) {
      onChange([...value, tag])
    }
    setInput("")
  }

  const removeTag = (tag: string) => {
    onChange(value.filter((t) => t !== tag))
  }

  return (
    <div className={cn("border border-border bg-background", disabled && "opacity-50")}>
      <div className="flex flex-wrap gap-1 p-2 min-h-[36px]">
        {value.map((tag) => (
          <span
            key={tag}
            className="flex items-center gap-1 px-2 h-6 bg-muted text-xs text-foreground"
          >
            {tag}
            {!disabled && (
              <button
                type="button"
                onClick={() => removeTag(tag)}
                className="text-dim hover:text-foreground"
              >
                &times;
              </button>
            )}
          </span>
        ))}
        {!disabled && (
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === ",") {
                e.preventDefault()
                addTag()
              }
            }}
            onBlur={addTag}
            placeholder={value.length === 0 ? placeholder : ""}
            className="flex-1 min-w-[100px] bg-transparent text-xs text-foreground outline-none placeholder:text-dim"
          />
        )}
      </div>
    </div>
  )
}
