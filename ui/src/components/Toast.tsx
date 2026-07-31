import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { X, Check, AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUI } from '@/lib/store'

const AUTO_DISMISS_MS = 3000

export function Toast() {
  const toast = useUI(s => s.toast)
  const dismiss = useUI(s => s.dismissToast)

  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(dismiss, AUTO_DISMISS_MS)
    return () => clearTimeout(timer)
  }, [toast, dismiss])

  if (!toast) return null

  const isError = toast.tone === 'error'

  return createPortal(
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'fixed top-4 right-4 z-[110] flex items-center gap-3 border bg-background px-4 py-3 shadow-lg max-w-sm',
        isError ? 'border-crit' : 'border-primary'
      )}
    >
      {isError ? (
        <AlertCircle className="h-4 w-4 text-crit shrink-0" />
      ) : (
        <Check className="h-4 w-4 text-primary shrink-0" />
      )}
      <span className={cn('text-xs', isError ? 'text-crit' : 'text-foreground')}>
        {toast.message}
      </span>
      <button
        onClick={dismiss}
        className="ml-auto text-muted-foreground hover:text-foreground shrink-0"
        aria-label="Dismiss"
      >
        <X className="h-3 w-3" />
      </button>
    </div>,
    document.body
  )
}
