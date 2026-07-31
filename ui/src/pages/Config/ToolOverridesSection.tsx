import { useState, useEffect, useCallback } from 'react'
import { Wrench, ChevronDown, ChevronRight, FileText, Plus, Trash2, Save } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Panel } from '@/components/tty'
import { useToolArgProfileList, useSaveToolArgProfile, useDeleteToolArgProfile } from '@/lib/api'
import {
  mapProfilesToTemplates,
  mapTemplateToWriteInput,
  profileMatchesTemplate,
} from '@/lib/api/useToolArgProfiles'
import type { ToolArgProfile } from '@/lib/api'
import type {
  ArgsMode,
  ArgumentTemplate,
  ToolOverrideConfig,
  ToolCatalogEntry,
  ToolType,
  ToolLocationMode,
} from '@/lib/types'
import { SectionHeader } from './shared'
import { ArgumentTemplateEditor } from './ArgumentTemplateEditor'

function collectFreshFiles(template: ArgumentTemplate): Record<string, File> {
  const out: Record<string, File> = {}
  for (const arg of template.arguments) {
    if (arg.valueType === 'file' && arg.file) out[arg.flag] = arg.file
  }
  return out
}

// ─── Tool Overrides Section ───────────────────────────────────────────────────

export function ToolOverridesSection({
  catalog,
  overrides,
  projectId,
  onSave,
  onDelete,
  isSaving,
}: {
  catalog: ToolCatalogEntry[]
  overrides: ToolOverrideConfig[]
  projectId: number
  onSave: (override: ToolOverrideConfig, isNew: boolean) => Promise<void>
  onDelete: (toolId: string) => void
  isSaving: boolean
}) {
  const [selectedToolId, setSelectedToolId] = useState<string | null>(null)
  const [form, setForm] = useState<Partial<ToolOverrideConfig>>({})
  const [_isDirty, setIsDirty] = useState(false)

  const [argsMode, setArgsMode] = useState<ArgsMode>('stock')
  const [templates, setTemplates] = useState<ArgumentTemplate[]>([])
  const [serverProfiles, setServerProfiles] = useState<ToolArgProfile[]>([])
  const [templatesExpanded, setTemplatesExpanded] = useState(false)
  const [editingTemplateId, setEditingTemplateId] = useState<string | null>(null)

  const selectedTool = catalog.find(t => t.id === selectedToolId)
  const existingOverride = overrides.find(o => o.toolId === selectedToolId)
  const isNew = selectedToolId && !existingOverride

  const argProfileQuery = useToolArgProfileList(projectId)
  const saveProfile = useSaveToolArgProfile()
  const deleteProfile = useDeleteToolArgProfile()

  const availableForAdd = catalog.filter(t => !overrides.some(o => o.toolId === t.id))

  useEffect(() => {
    if (selectedToolId) {
      const existing = overrides.find(o => o.toolId === selectedToolId)
      if (existing) {
        setForm({ ...existing })
        setArgsMode(existing.argsMode ?? 'stock')
      } else {
        const tool = catalog.find(t => t.id === selectedToolId)
        setForm({
          toolId: selectedToolId,
          argsMode: 'stock',
          type: 'repo',
          location: tool?.supportsLocal ? 'local' : 'docker',
        })
        setArgsMode('stock')
      }
      setIsDirty(false)
      setTemplatesExpanded(false)
      setEditingTemplateId(null)
      setServerProfiles([])
      setTemplates([])
    }
  }, [selectedToolId, overrides, catalog])

  useEffect(() => {
    if (!selectedToolId || !argProfileQuery.data) return
    const loaded = argProfileQuery.data.items.filter(
      p => p.toolName === selectedToolId || p.toolName === selectedTool?.name
    )
    setTemplates(mapProfilesToTemplates(loaded))
    setServerProfiles(loaded)
  }, [selectedToolId, selectedTool, argProfileQuery.data])

  const updateField = <K extends keyof ToolOverrideConfig>(
    field: K,
    value: ToolOverrideConfig[K]
  ) => {
    setForm(f => ({ ...f, [field]: value }))
    setIsDirty(true)
  }

  const handleSave = async () => {
    if (!selectedToolId || !selectedTool) return
    await onSave({ ...form, argsMode } as ToolOverrideConfig, !!isNew)

    const serverIdSet = new Set(serverProfiles.map(p => String(p.id)))
    const currentServerIdSet = new Set(templates.filter(t => serverIdSet.has(t.id)).map(t => t.id))
    const mutations: Promise<ToolArgProfile | void>[] = []

    for (const t of templates) {
      const files = collectFreshFiles(t)
      const hasFreshFile = Object.keys(files).length > 0
      if (!serverIdSet.has(t.id)) {
        mutations.push(
          saveProfile.mutateAsync({
            projectId,
            profile: mapTemplateToWriteInput(selectedTool.id, t),
            files,
          })
        )
      } else {
        const sp = serverProfiles.find(p => String(p.id) === t.id)
        if (sp && (!profileMatchesTemplate(sp, t) || hasFreshFile)) {
          mutations.push(
            saveProfile.mutateAsync({
              projectId,
              profile: mapTemplateToWriteInput(selectedTool.id, t),
              files,
              existingId: sp.id,
            })
          )
        }
      }
    }

    for (const sp of serverProfiles) {
      if (!currentServerIdSet.has(String(sp.id))) {
        mutations.push(deleteProfile.mutateAsync({ projectId, profileId: sp.id }))
      }
    }

    if (mutations.length > 0) {
      await Promise.all(mutations).catch(() => {
        // errors surfaced per-mutation via onError
      })
    }

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

  const addTemplate = useCallback(() => {
    const newTemplate: ArgumentTemplate = {
      id: `tmpl-${Date.now()}`,
      name: '',
      arguments: [{ id: `arg-${Date.now()}`, flag: '', valueType: 'none' }],
    }
    setTemplates(prev => [...prev, newTemplate])
    setEditingTemplateId(newTemplate.id)
    setTemplatesExpanded(true)
    setIsDirty(true)
  }, [])

  const updateTemplate = useCallback((templateId: string, updates: Partial<ArgumentTemplate>) => {
    setTemplates(prev => prev.map(t => (t.id === templateId ? { ...t, ...updates } : t)))
    setIsDirty(true)
  }, [])

  const deleteTemplate = useCallback((templateId: string) => {
    setTemplates(prev => prev.filter(t => t.id !== templateId))
    setEditingTemplateId(prev => (prev === templateId ? null : prev))
    setIsDirty(true)
  }, [])

  const canSelectDocker = selectedTool?.supportsDocker ?? true

  return (
    <Panel bodyClassName="p-4">
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

          {/* Type / Location / Args row */}
          <div className="grid grid-cols-3 gap-4">
            {/* Type */}
            <div>
              <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
                Type
              </div>
              <div className="flex gap-1">
                {(['repo', 'api'] as ToolType[]).map(type => (
                  <button
                    key={type}
                    onClick={() => updateField('type', type)}
                    className={cn(
                      'flex-1 h-8 text-[10px] uppercase tracking-wider border transition-colors',
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
              <div className="flex gap-1">
                {(['local', 'docker'] as ToolLocationMode[]).map(loc => {
                  const disabled = loc === 'docker' && !canSelectDocker
                  return (
                    <button
                      key={loc}
                      onClick={() => updateField('location', loc)}
                      disabled={disabled}
                      className={cn(
                        'flex-1 h-8 text-[10px] uppercase tracking-wider border transition-colors',
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
            </div>

            {/* Args */}
            <div>
              <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
                Args
              </div>
              <div className="flex gap-1">
                {(['stock', 'custom'] as ArgsMode[]).map(mode => (
                  <button
                    key={mode}
                    onClick={() => {
                      setArgsMode(mode)
                      setIsDirty(true)
                      if (mode === 'custom' && templates.length === 0) {
                        setTemplatesExpanded(true)
                      }
                    }}
                    className={cn(
                      'flex-1 h-8 text-[10px] uppercase tracking-wider border transition-colors',
                      argsMode === mode
                        ? 'border-accent bg-accent/20 text-accent'
                        : 'border-border text-muted-foreground hover:border-muted-foreground'
                    )}
                  >
                    {mode}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {!canSelectDocker && (
            <div className="text-[9px] text-dim">
              {selectedTool.name} does not support Docker mode
            </div>
          )}

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

          {/* Argument Templates (only when argsMode = custom) */}
          {argsMode === 'custom' && (
            <div className="border border-border">
              <button
                onClick={() => setTemplatesExpanded(!templatesExpanded)}
                className="w-full flex items-center justify-between px-3 py-2 hover:bg-muted/30 transition-colors"
              >
                <div className="flex items-center gap-2">
                  {templatesExpanded ? (
                    <ChevronDown className="h-3 w-3 text-dim" />
                  ) : (
                    <ChevronRight className="h-3 w-3 text-dim" />
                  )}
                  <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                    Argument Templates
                  </span>
                </div>
                <span className="text-[10px] text-dim">
                  {templates.length === 0
                    ? 'No templates yet'
                    : `${templates.length} template${templates.length > 1 ? 's' : ''}`}
                </span>
              </button>

              {templatesExpanded && (
                <div className="border-t border-border p-3 space-y-3">
                  {templates.map(template => (
                    <div key={template.id} className="border border-border bg-muted/20">
                      {editingTemplateId === template.id ? (
                        <ArgumentTemplateEditor
                          template={template}
                          onUpdate={updates => updateTemplate(template.id, updates)}
                          onDelete={() => deleteTemplate(template.id)}
                          onClose={() => setEditingTemplateId(null)}
                        />
                      ) : (
                        <div className="flex items-center justify-between px-3 py-2">
                          <div className="flex items-center gap-3">
                            <FileText className="h-4 w-4 text-dim" />
                            <div>
                              <div className="text-xs font-bold text-foreground">
                                {template.name || '(unnamed)'}
                              </div>
                              <div className="text-[10px] text-dim">
                                {template.arguments.length} argument
                                {template.arguments.length !== 1 ? 's' : ''}
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => setEditingTemplateId(template.id)}
                              className="px-2 h-6 text-[9px] uppercase tracking-wider border border-border text-muted-foreground hover:bg-muted/30"
                            >
                              Edit
                            </button>
                            <button
                              onClick={() => deleteTemplate(template.id)}
                              aria-label="delete template"
                              className="px-2 h-6 text-[9px] uppercase tracking-wider border border-crit/50 text-crit hover:bg-crit/10"
                            >
                              <Trash2 className="h-3 w-3" />
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}

                  <button
                    onClick={addTemplate}
                    className="w-full flex items-center justify-center gap-2 px-3 py-2 border border-dashed border-border text-muted-foreground hover:border-accent hover:text-accent transition-colors"
                  >
                    <Plus className="h-3 w-3" />
                    <span className="text-[10px] uppercase tracking-wider">Add Template</span>
                  </button>
                </div>
              )}
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
                className="flex items-center gap-1 px-3 h-8 text-[10px] uppercase tracking-wider border border-border-strong text-muted-foreground hover:border-primary/50 hover:text-foreground transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={
                  isSaving ||
                  (argsMode !== 'custom' && form.location === 'local' && !form.path) ||
                  (argsMode !== 'custom' &&
                    form.location === 'docker' &&
                    (!form.container?.name || !form.container?.toolPath))
                }
                className={cn(
                  'flex items-center gap-1 px-4 h-8 text-[10px] uppercase tracking-wider transition-colors',
                  argsMode === 'custom' ||
                    (form.location === 'local' && form.path) ||
                    (form.location === 'docker' && form.container?.name && form.container?.toolPath)
                    ? 'bg-accent text-background hover:bg-accent/80 hover:shadow-[0_0_8px_rgba(57,255,20,0.15)]'
                    : 'bg-muted text-dim opacity-40 cursor-not-allowed'
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
