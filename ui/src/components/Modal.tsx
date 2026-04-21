import { useEffect, type ReactNode } from "react"
import { createPortal } from "react-dom"
import { X } from "lucide-react"
import { cn } from "@/lib/utils"

/**
 * TTY-styled modal. Renders via portal so it escapes any overflow/stacking
 * issues in the main layout. Closes on backdrop click and Escape.
 */
export function Modal({
  open,
  title,
  onClose,
  children,
  footer,
  width = "md",
  tone = "default",
}: {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  width?: "sm" | "md" | "lg"
  tone?: "default" | "warn" | "error"
}) {
  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [open, onClose])

  if (!open) return null

  const widthCls =
    width === "sm" ? "max-w-md" : width === "lg" ? "max-w-3xl" : "max-w-xl"
  const toneBorder =
    tone === "error"
      ? "border-crit"
      : tone === "warn"
        ? "border-high"
        : "border-border-strong"
  const toneTitle =
    tone === "error" ? "text-crit" : tone === "warn" ? "text-high" : "text-primary"

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className="fixed inset-0 z-[100] flex items-center justify-center p-6"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-background/85 backdrop-blur-[1px]"
        onClick={onClose}
      />
      {/* Panel */}
      <div
        className={cn(
          "relative w-full border-2 bg-background shadow-[0_0_0_1px_var(--color-background),0_0_48px_rgba(107,211,107,0.15)]",
          widthCls,
          toneBorder,
        )}
      >
        <header className="flex items-center justify-between h-9 px-3 border-b border-border-strong">
          <div
            className={cn(
              "flex items-center gap-2 text-xs uppercase tracking-[0.22em] font-bold",
              toneTitle,
            )}
          >
            <span className="text-dim">[</span>
            <span>{title}</span>
            <span className="text-dim">]</span>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </header>
        <div className="p-4 text-xs max-h-[70vh] overflow-auto">{children}</div>
        {footer && (
          <footer className="flex items-center justify-end gap-2 px-3 h-11 border-t border-border-strong">
            {footer}
          </footer>
        )}
      </div>
    </div>,
    document.body,
  )
}

export function ModalButton({
  variant = "default",
  onClick,
  children,
  disabled,
}: {
  variant?: "default" | "primary" | "danger"
  onClick: () => void
  children: ReactNode
  disabled?: boolean
}) {
  const cls =
    variant === "primary"
      ? "border-accent text-accent hover:bg-muted"
      : variant === "danger"
        ? "border-crit text-crit hover:bg-[rgba(255,77,77,0.1)]"
        : "border-border-strong text-foreground hover:bg-muted"
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "px-3 h-7 border text-[11px] uppercase tracking-[0.18em] font-bold transition-colors",
        cls,
        disabled && "opacity-40 cursor-not-allowed hover:bg-transparent",
      )}
    >
      {children}
    </button>
  )
}
