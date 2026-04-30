import { useState, useEffect } from 'react'
import { Wrench, ChevronDown, Trash2, Save } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Panel } from '@/components/tty'
import type { ToolOverrideConfig, ToolCatalogEntry, ToolType, ToolLocationMode } from '@/lib/types'
import { SectionHeader } from './shared'

// ─── Tool Overrides Section ───────────────────────────────────────────────────

export function ToolOverridesSection({
  catalog,
  overrides,
  onSave,
  onDelete,
  isSaving,
}: {
  catalog: ToolCatalogEntry[]
  overrides: ToolOverrideConfig[]
  onSave: (override: ToolOverrideConfig, isNew: boolean) => void
  onDelete: (toolId: string) => void
  isSaving: boolean
}) {
  const [selectedToolId, setSelectedToolId] = useState<string | null>(null)
  const [form, setForm] = useState<Partial<ToolOverrideConfig>>({})
  const [_isDirty, setIsDirty] = useState(false)

  const selectedTool = catalog.find(t => t.id === selectedToolId)
  const existingOverride = overrides.find(o => o.toolId === selectedToolId)
  const isNew = selectedToolId && !existingOverride

  const availableForAdd = catalog.filter(t => !overrides.some(o => o.toolId === t.id))

  useEffect(() => {
    if (selectedToolId) {
      const existing = overrides.find(o => o.toolId === selectedToolId)
      if (existing) {
        setForm({ ...existing })
      } else {
        const tool = catalog.find(t => t.id === selectedToolId)
        setForm({
          toolId: selectedToolId,
          type: 'repo',
          location: tool?.supportsLocal ? 'local' : 'docker',
        })
      }
      setIsDirty(false)
    }
  }, [selectedToolId, overrides, catalog])

  const updateField = <K extends keyof ToolOverrideConfig>(
    field: K,
    value: ToolOverrideConfig[K]
  ) => {
    setForm(f => ({ ...f, [field]: value }))
    setIsDirty(true)
  }

  const handleSave = () => {
    if (!selectedToolId) return
    onSave(form as ToolOverrideConfig, !!isNew)
    setIsDirty(false)
  }

  const handleDelete = () => {
    if (selectedToolId && !isNew) {
      if (confirm('Remove this override? The tool will revert to global configuration.')) {
        onDelete(selectedToolId)
        setSelectedToolId(null)
      }
    }
  }

  const canSelectDocker = selectedTool?.supportsDocker ?? true

  return (
    <Panel>
      <SectionHeader icon={Wrench} title="TOOL OVERRIDES">
        <div className="flex items-center gap-2">
          {overrides.length > 0 && (
            <div className="relative">
              <select
                value={selectedToolId ?? ''}
                onChange={e => setSelectedToolId(e.target.value || null)}
                className="h-7 pl-2 pr-6 bg-background border border-border text-xs text-foreground appearance-none cursor-pointer focus:border-accent focus:outline-none"
              >
                <option value="">Select override...</option>
                {overrides.map(o => {
                  const tool = catalog.find(t => t.id === o.toolId)
                  return (
                    <option key={o.toolId} value={o.toolId}>
                      {tool?.name ?? o.toolId}
                    </option>
                  )
                })}
              </select>
              <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 h-3 w-3 text-dim pointer-events-none" />
            </div>
          )}

          {availableForAdd.length > 0 && (
            <div className="relative">
              <select
                value=""
                onChange={e => {
                  if (e.target.value) setSelectedToolId(e.target.value)
                }}
                className="h-7 pl-2 pr-6 bg-background border border-accent/50 text-xs text-accent appearance-none cursor-pointer focus:border-accent focus:outline-none"
              >
                <option value="">+ Add Override</option>
                {availableForAdd.map(t => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 h-3 w-3 text-accent pointer-events-none" />
            </div>
          )}
        </div>
      </SectionHeader>

      {!selectedToolId && (
        <div className="text-sm text-dim py-8 text-center">
          {overrides.length === 0
            ? 'No tool overrides configured. Add one to customize tool paths for this project.'
            : 'Select a tool override to edit or add a new one.'}
        </div>
      )}

      {selectedToolId && selectedTool && (
        <div className="space-y-4">
          {/* Tool info */}
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <div className="text-sm text-foreground font-bold">{selectedTool.name}</div>
              <div className="text-[10px] text-dim uppercase tracking-wider">
                {isNew ? 'New override' : 'Overrides global default'}
              </div>
            </div>
            {!isNew && (
              <span className="px-2 h-5 flex items-center text-[9px] uppercase tracking-wider bg-high/20 text-high">
                Override Active
              </span>
            )}
          </div>

          {/* Type */}
          <div>
            <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
              Type
            </div>
            <div className="flex gap-2">
              {(['repo', 'api'] as ToolType[]).map(type => (
                <button
                  key={type}
                  onClick={() => updateField('type', type)}
                  className={cn(
                    'px-4 h-8 text-[10px] uppercase tracking-wider border transition-colors',
                    form.type === type
                      ? 'border-accent bg-accent/20 text-accent'
                      : 'border-border text-muted-foreground hover:border-muted-foreground'
                  )}
                >
                  {type}
                </button>
              ))}
            </div>
          </div>

          {/* Location */}
          <div>
            <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
              Location
            </div>
            <div className="flex gap-2">
              {(['local', 'docker'] as ToolLocationMode[]).map(loc => {
                const disabled = loc === 'docker' && !canSelectDocker
                return (
                  <button
                    key={loc}
                    onClick={() => updateField('location', loc)}
                    disabled={disabled}
                    className={cn(
                      'px-4 h-8 text-[10px] uppercase tracking-wider border transition-colors',
                      form.location === loc
                        ? 'border-accent bg-accent/20 text-accent'
                        : disabled
                          ? 'border-border/50 text-dim cursor-not-allowed'
                          : 'border-border text-muted-foreground hover:border-muted-foreground'
                    )}
                  >
                    {loc}
                  </button>
                )
              })}
            </div>
            {!canSelectDocker && (
              <div className="text-[9px] text-dim mt-1">
                {selectedTool.name} does not support Docker mode
              </div>
            )}
          </div>

          {/* Path fields */}
          {form.location === 'local' ? (
            <div>
              <label
                htmlFor="tool-path"
                className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
              >
                Path <span className="text-crit">*</span>
              </label>
              <input
                id="tool-path"
                type="text"
                value={form.path ?? ''}
                onChange={e => updateField('path', e.target.value)}
                placeholder="/path/to/tool"
                className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground font-mono focus:border-accent focus:outline-none"
              />
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label
                  htmlFor="tool-container-name"
                  className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
                >
                  Container Name <span className="text-crit">*</span>
                </label>
                <input
                  id="tool-container-name"
                  type="text"
                  value={form.container?.name ?? ''}
                  onChange={e =>
                    updateField('container', {
                      name: e.target.value,
                      toolPath: form.container?.toolPath ?? '',
                    })
                  }
                  className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none"
                />
              </div>
              <div>
                <label
                  htmlFor="tool-container-path"
                  className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
                >
                  Tool Path in Container <span className="text-crit">*</span>
                </label>
                <input
                  id="tool-container-path"
                  type="text"
                  value={form.container?.toolPath ?? ''}
                  onChange={e =>
                    updateField('container', {
                      name: form.container?.name ?? '',
                      toolPath: e.target.value,
                    })
                  }
                  placeholder="/usr/local/bin/tool"
                  className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground font-mono focus:border-accent focus:outline-none"
                />
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="border-t border-border pt-4 flex items-center justify-between">
            <div>
              {!isNew && (
                <button
                  onClick={handleDelete}
                  className="flex items-center gap-1 px-3 h-8 text-[10px] uppercase tracking-wider border border-crit text-crit hover:bg-crit/10 transition-colors"
                >
                  <Trash2 className="h-3 w-3" />
                  Remove Override
                </button>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setSelectedToolId(null)}
                className="flex items-center gap-1 px-3 h-8 text-[10px] uppercase tracking-wider border border-border text-muted-foreground hover:bg-muted/30 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={
                  isSaving ||
                  (form.location === 'local' && !form.path) ||
                  (form.location === 'docker' &&
                    (!form.container?.name || !form.container?.toolPath))
                }
                className={cn(
                  'flex items-center gap-1 px-4 h-8 text-[10px] uppercase tracking-wider transition-colors',
                  (form.location === 'local' && form.path) ||
                    (form.location === 'docker' && form.container?.name && form.container?.toolPath)
                    ? 'bg-accent text-background hover:bg-accent/80'
                    : 'bg-muted text-dim cursor-not-allowed'
                )}
              >
                <Save className="h-3 w-3" />
                {isSaving ? 'Saving...' : isNew ? 'Create' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </Panel>
  )
}
