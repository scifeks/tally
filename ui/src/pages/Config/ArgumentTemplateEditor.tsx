import { ChevronDown, FileText, Plus, Upload, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ArgumentTemplate, ArgValueType, ToolArgument } from '@/lib/types'

export function ArgumentTemplateEditor({
  template,
  onUpdate,
  onDelete: _onDelete,
  onClose,
}: {
  template: ArgumentTemplate
  onUpdate: (updates: Partial<ArgumentTemplate>) => void
  onDelete: () => void
  onClose: () => void
}) {
  const updateArgument = (argId: string, updates: Partial<ToolArgument>) => {
    onUpdate({
      arguments: template.arguments.map(a => (a.id === argId ? { ...a, ...updates } : a)),
    })
  }

  const addArgument = () => {
    onUpdate({
      arguments: [...template.arguments, { id: `arg-${Date.now()}`, flag: '', valueType: 'none' }],
    })
  }

  const removeArgument = (argId: string) => {
    onUpdate({
      arguments: template.arguments.filter(a => a.id !== argId),
    })
  }

  return (
    <div className="p-3 space-y-3">
      <div>
        <label
          htmlFor={`tmpl-name-${template.id}`}
          className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
        >
          Template Name <span className="text-crit">*</span>
        </label>
        <input
          id={`tmpl-name-${template.id}`}
          type="text"
          value={template.name}
          onChange={e => onUpdate({ name: e.target.value })}
          placeholder="e.g., full-scan-with-wordlist"
          className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none"
        />
      </div>

      <div className="space-y-2">
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-muted-foreground">
          <div className="w-32">Argument</div>
          <div className="w-20">Operator</div>
          <div className="w-24">Type</div>
          <div className="flex-1">Value</div>
        </div>
        {template.arguments.map(arg => (
          <div key={arg.id} className="flex items-start gap-2">
            <div className="w-32">
              <input
                type="text"
                value={arg.flag}
                onChange={e => updateArgument(arg.id, { flag: e.target.value })}
                placeholder="--flag"
                aria-label="argument flag"
                className="w-full h-7 px-2 bg-background border border-border text-xs text-foreground font-mono focus:border-accent focus:outline-none"
              />
            </div>

            <div className="relative w-20">
              <select
                value={arg.operator ?? ''}
                onChange={e => updateArgument(arg.id, { operator: e.target.value })}
                disabled={arg.valueType === 'none'}
                aria-label="operator"
                className="w-full h-7 pl-2 pr-6 bg-background border border-border text-xs text-foreground appearance-none cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed focus:border-accent focus:outline-none"
              >
                <option value="">None</option>
                <option value="=">=</option>
              </select>
              <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 h-3 w-3 text-dim pointer-events-none" />
            </div>

            <div className="relative w-24">
              <select
                value={arg.valueType}
                onChange={e =>
                  updateArgument(arg.id, {
                    valueType: e.target.value as ArgValueType,
                    operator: e.target.value === 'none' ? '' : arg.operator,
                    value: undefined,
                    fileName: undefined,
                    file: undefined,
                  })
                }
                aria-label="value type"
                className="w-full h-7 pl-2 pr-6 bg-background border border-border text-xs text-foreground appearance-none cursor-pointer focus:border-accent focus:outline-none"
              >
                <option value="none">None</option>
                <option value="string">String</option>
                <option value="file">File</option>
              </select>
              <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 h-3 w-3 text-dim pointer-events-none" />
            </div>

            <div className="flex-1">
              {arg.valueType === 'string' && (
                <input
                  type="text"
                  value={arg.value ?? ''}
                  onChange={e => updateArgument(arg.id, { value: e.target.value })}
                  placeholder="value"
                  aria-label="argument value"
                  className="w-full h-7 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none"
                />
              )}
              {arg.valueType === 'file' && (
                <div className="flex items-center gap-2">
                  {arg.fileName ? (
                    <div className="flex items-center gap-2 px-2 h-7 bg-muted/30 border border-border text-xs text-foreground flex-1">
                      <FileText className="h-3 w-3 text-dim" />
                      <span className="truncate">{arg.fileName}</span>
                      <button
                        onClick={() =>
                          updateArgument(arg.id, {
                            value: undefined,
                            fileName: undefined,
                            file: undefined,
                          })
                        }
                        className="text-muted-foreground hover:text-crit"
                        aria-label="remove file"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                  ) : (
                    <label className="flex items-center gap-2 px-2 h-7 border border-dashed border-border text-xs text-muted-foreground hover:border-accent hover:text-accent cursor-pointer flex-1">
                      <Upload className="h-3 w-3" />
                      <span>Browse...</span>
                      <input
                        type="file"
                        className="hidden"
                        onChange={e => {
                          const file = e.target.files?.[0]
                          if (file) {
                            updateArgument(arg.id, {
                              fileName: file.name,
                              value: '',
                              file,
                            })
                          }
                        }}
                      />
                    </label>
                  )}
                </div>
              )}
              {arg.valueType === 'none' && (
                <div className="h-7 flex items-center text-[10px] text-dim italic">
                  (boolean flag)
                </div>
              )}
            </div>

            <button
              onClick={() => removeArgument(arg.id)}
              disabled={template.arguments.length === 1}
              aria-label="remove argument"
              className={cn(
                'h-7 w-7 flex items-center justify-center border transition-colors',
                template.arguments.length === 1
                  ? 'border-border/50 text-dim cursor-not-allowed'
                  : 'border-border text-muted-foreground hover:border-crit hover:text-crit'
              )}
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        ))}

        <button
          onClick={addArgument}
          className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-accent"
        >
          <Plus className="h-3 w-3" />
          Add argument
        </button>
      </div>

      <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
        <button
          onClick={onClose}
          className="px-3 h-7 text-[10px] uppercase tracking-wider border border-border text-muted-foreground hover:bg-muted/30"
        >
          Done
        </button>
      </div>
    </div>
  )
}
