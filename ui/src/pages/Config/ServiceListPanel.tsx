import { Plus, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ServiceConfig } from '@/lib/types'

export function ServiceListPanel({
  services,
  selectedIndex,
  onSelect,
  onAdd,
  onDelete,
}: {
  services: ServiceConfig[]
  selectedIndex: number
  onSelect: (index: number) => void
  onAdd: () => void
  onDelete: (index: number) => void
}) {
  return (
    <div className="border border-border bg-background">
      <div className="px-3 py-2 border-b border-border">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Services</span>
      </div>

      <div className="divide-y divide-border">
        {services.map((svc, i) => (
          <div
            key={i}
            role="button"
            tabIndex={0}
            onClick={() => onSelect(i)}
            onKeyDown={e => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                onSelect(i)
              }
            }}
            className={cn(
              'group flex items-center justify-between px-3 py-2 cursor-pointer transition-colors',
              i === selectedIndex
                ? 'border-l-2 border-l-accent bg-accent/5'
                : 'border-l-2 border-l-transparent hover:bg-muted/20'
            )}
          >
            <div className="min-w-0">
              <div className="text-xs text-foreground truncate">{svc.name || '(unnamed)'}</div>
              {svc.type.length > 0 && (
                <div className="flex gap-1 mt-0.5">
                  {svc.type.map(t => (
                    <span key={t} className="text-[9px] text-dim uppercase">
                      {t}
                    </span>
                  ))}
                </div>
              )}
            </div>
            {services.length > 1 && (
              <button
                onClick={e => {
                  e.stopPropagation()
                  onDelete(i)
                }}
                className="opacity-0 group-hover:opacity-100 p-1 text-dim hover:text-crit transition-all"
                title="Remove service"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            )}
          </div>
        ))}
      </div>

      <div className="border-t border-border p-2">
        <button
          onClick={onAdd}
          className="flex items-center gap-1 w-full justify-center px-2 py-1.5 text-[10px] uppercase tracking-wider border border-dashed border-border text-muted-foreground hover:border-accent hover:text-accent transition-colors"
        >
          <Plus className="h-3 w-3" />
          Add Service
        </button>
      </div>
    </div>
  )
}
