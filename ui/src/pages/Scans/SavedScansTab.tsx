import { useState, useEffect, useMemo } from 'react'
import { Bookmark, Check, Play, Save, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ConfiguredRepo, ConfiguredTool, SavedScanListItem, Segment } from '@/lib/types'
import type { SavedScanWriteInput } from '@/lib/api/useSavedScans'
import { useRunSavedScan } from '@/lib/api'
import { StaleSavedScanModal } from '@/components/StaleSavedScanModal'
import type { StaleSavedScanItem } from '@/components/StaleSavedScanModal'
import type { ToolArgProfile } from '@/lib/api/useToolArgProfiles'

const SEGMENT_LABEL: Record<Segment, string> = {
  sast: 'SAST',
  sca: 'SCA',
  web: 'WEB',
  secrets: 'SECRETS',
}

interface FormState {
  id?: number
  name: string
  repoIds: number[]
  toolIds: string[]
  skipToolIds: string[]
  segments: Segment[]
  skipEnrichment: boolean
}

interface SavedScansTabProps {
  projectId: number
  savedScans: SavedScanListItem[]
  configuredRepos: ConfiguredRepo[]
  configuredTools: ConfiguredTool[]
  toolArgProfiles: ToolArgProfile[]
  configuredSegments: Segment[]
  onSave: (payload: SavedScanWriteInput, existingId?: number) => void
  onDelete: (savedScanId: number) => void
  onSelect: (savedScanId: number) => void
  isSaving: boolean
}

export function SavedScansTab({
  projectId,
  savedScans,
  configuredRepos,
  configuredTools,
  toolArgProfiles,
  configuredSegments,
  onSave,
  onDelete,
  onSelect,
  isSaving,
}: SavedScansTabProps) {
  const [selectedScanId, setSelectedScanId] = useState<number | null>(null)
  const [isCreatingNew, setIsCreatingNew] = useState(false)
  const [form, setForm] = useState<Partial<FormState>>({})
  const [staleItems, setStaleItems] = useState<StaleSavedScanItem[] | null>(null)

  const runScan = useRunSavedScan()

  const selectedScan = savedScans.find(s => s.id === selectedScanId)

  const allToolOptions = useMemo(() => {
    const options: Array<{
      id: string
      name: string
      segment: Segment
      isTemplate?: boolean
    }> = []

    configuredTools.forEach(t => {
      options.push({ id: t.id, name: t.name, segment: t.segment })
    })

    toolArgProfiles.forEach(profile => {
      const baseTool = configuredTools.find(t => t.id === profile.toolName)
      if (!baseTool) return
      options.push({
        id: `${profile.toolName}:${profile.id}`,
        name: `${baseTool.name} [${profile.name}]`,
        segment: baseTool.segment,
        isTemplate: true,
      })
    })

    return options
  }, [configuredTools, toolArgProfiles])

  useEffect(() => {
    if (selectedScanId && selectedScan) {
      // The form's Tools list merges tool names and `toolName:profileId` template
      // strings into one id space; reconstruct that from the server's split arrays.
      const toolIds: string[] = [
        ...selectedScan.toolNames,
        ...selectedScan.argProfileIds.map(pid => {
          const opt = allToolOptions.find(
            o => o.id === `${toolArgProfiles.find(p => p.id === pid)?.toolName}:${pid}`
          )
          return opt?.id ?? String(pid)
        }),
      ]
      setForm({
        id: selectedScan.id,
        name: selectedScan.name,
        repoIds: selectedScan.repoIds,
        toolIds,
        skipToolIds: selectedScan.skipToolIds,
        segments: selectedScan.segments,
        skipEnrichment: selectedScan.skipEnrichment,
      })
      setIsCreatingNew(false)
    } else if (isCreatingNew) {
      setForm({
        name: '',
        repoIds: [],
        toolIds: [],
        skipToolIds: [],
        segments: [],
        skipEnrichment: false,
      })
    }
  }, [selectedScanId, selectedScan, isCreatingNew, projectId, allToolOptions, toolArgProfiles])

  const handleCreateNew = () => {
    setSelectedScanId(null)
    setIsCreatingNew(true)
  }

  const handleSave = () => {
    if (!form.name?.trim()) return
    const toolNames: string[] = []
    const argProfileIds: number[] = []
    for (const id of form.toolIds ?? []) {
      const colonIdx = id.lastIndexOf(':')
      if (colonIdx !== -1) {
        const profileId = Number(id.slice(colonIdx + 1))
        if (!isNaN(profileId)) {
          argProfileIds.push(profileId)
          continue
        }
      }
      toolNames.push(id)
    }
    const payload: SavedScanWriteInput = {
      name: form.name.trim(),
      skipEnrichment: form.skipEnrichment ?? false,
      repoIds: form.repoIds ?? [],
      toolNames,
      skipToolIds: form.skipToolIds ?? [],
      segments: form.segments ?? [],
      argProfileIds,
    }
    onSave(payload, form.id)
    if (isCreatingNew) {
      setIsCreatingNew(false)
    }
  }

  const handleDelete = () => {
    if (selectedScanId && confirm('Delete this saved scan configuration?')) {
      onDelete(selectedScanId)
      setSelectedScanId(null)
    }
  }

  const updateForm = <K extends keyof FormState>(field: K, value: FormState[K]) => {
    setForm(f => ({ ...f, [field]: value }))
  }

  const toggleInList = <T,>(current: T[], item: T): T[] =>
    current.includes(item) ? current.filter(x => x !== item) : [...current, item]

  const isEditing = Boolean(selectedScanId) || isCreatingNew

  return (
    <>
      <div className="flex-1 min-h-0 flex border border-border bg-background">
        {/* Left: Saved scans list */}
        <div className="w-64 border-r border-border flex flex-col">
          <div className="p-3 border-b border-border flex items-center justify-between">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Saved Scans
            </span>
            <button
              onClick={handleCreateNew}
              className="flex items-center gap-1 px-2 h-6 text-[10px] uppercase tracking-wider border border-accent/50 text-accent hover:bg-accent/10"
            >
              <Bookmark className="h-3 w-3" />
              New
            </button>
          </div>
          <div className="flex-1 overflow-auto">
            {savedScans.length === 0 && !isCreatingNew ? (
              <div className="p-4 text-center text-sm text-dim">No saved scans yet</div>
            ) : (
              <div className="divide-y divide-border">
                {savedScans.map(scan => (
                  <button
                    key={scan.id}
                    onClick={() => {
                      setSelectedScanId(scan.id)
                      setIsCreatingNew(false)
                    }}
                    className={cn(
                      'w-full text-left px-3 py-2 transition-colors',
                      selectedScanId === scan.id ? 'bg-accent/20 text-accent' : 'hover:bg-muted/30'
                    )}
                  >
                    <div className="text-xs font-bold">{scan.name}</div>
                    <div className="text-[10px] text-dim">
                      {scan.toolNames.length + scan.argProfileIds.length} tools &middot;{' '}
                      {scan.repoIds.length === 0 ? 'all repos' : `${scan.repoIds.length} repos`}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right: Editor */}
        <div className="flex-1 flex flex-col min-h-0">
          {!isEditing ? (
            <div className="flex-1 flex items-center justify-center text-muted-foreground">
              <div className="text-center">
                <Bookmark className="h-12 w-12 mx-auto mb-4 text-dim" />
                <div className="text-sm">Select a saved scan to edit or create a new one</div>
              </div>
            </div>
          ) : (
            <div className="flex-1 overflow-auto p-4 space-y-4">
              {/* Name */}
              <div>
                <label
                  htmlFor="saved-scan-name"
                  className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
                >
                  Scan Name <span className="text-crit">*</span>
                </label>
                <input
                  id="saved-scan-name"
                  type="text"
                  value={form.name ?? ''}
                  onChange={e => updateForm('name', e.target.value)}
                  placeholder="e.g., full-sast-scan"
                  className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none"
                />
              </div>

              {/* Repositories */}
              <div>
                <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
                  Repositories
                  {(form.repoIds?.length ?? 0) > 0 ? ` (${form.repoIds?.length} selected)` : null}
                </div>
                <div className="max-h-32 overflow-y-auto border border-border bg-background p-2 space-y-1">
                  {configuredRepos.length === 0 ? (
                    <div className="text-[10px] text-dim">No repositories configured</div>
                  ) : (
                    configuredRepos.map(r => {
                      const isSelected = form.repoIds?.includes(r.id) ?? false
                      return (
                        <button
                          key={r.id}
                          onClick={() =>
                            updateForm('repoIds', toggleInList(form.repoIds ?? [], r.id))
                          }
                          className={cn(
                            'w-full flex items-center justify-between px-2 h-6 text-[10px] transition-colors',
                            isSelected
                              ? 'bg-accent/20 text-accent'
                              : 'hover:bg-muted/30 text-muted-foreground'
                          )}
                        >
                          <span>{r.name}</span>
                          <span className="uppercase text-[9px] text-dim">{r.source}</span>
                        </button>
                      )
                    })
                  )}
                </div>
                <div className="text-[10px] text-dim mt-1">
                  Leave empty to scan all repositories
                </div>
              </div>

              {/* Tools (including templates) */}
              <div>
                <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
                  Tools
                  {(form.toolIds?.length ?? 0) > 0 ? ` (${form.toolIds?.length} selected)` : null}
                </div>
                <div className="max-h-40 overflow-y-auto border border-border bg-background p-2 space-y-1">
                  {allToolOptions.length === 0 ? (
                    <div className="text-[10px] text-dim">No tools configured</div>
                  ) : (
                    allToolOptions.map(t => {
                      const isSelected = form.toolIds?.includes(t.id) ?? false
                      return (
                        <button
                          key={t.id}
                          onClick={() =>
                            updateForm('toolIds', toggleInList(form.toolIds ?? [], t.id))
                          }
                          className={cn(
                            'w-full flex items-center justify-between px-2 h-6 text-[10px] transition-colors',
                            isSelected
                              ? 'bg-accent/20 text-accent'
                              : 'hover:bg-muted/30 text-muted-foreground'
                          )}
                        >
                          <span className="flex items-center gap-2">
                            {t.name}
                            {t.isTemplate && (
                              <span className="px-1 py-0.5 text-[8px] uppercase bg-high/20 text-high">
                                template
                              </span>
                            )}
                          </span>
                          <span className="uppercase text-[9px] text-dim">{t.segment}</span>
                        </button>
                      )
                    })
                  )}
                </div>
                <div className="text-[10px] text-dim mt-1">
                  Leave empty to run all tools. Templates from Config &gt; Tool Overrides appear
                  here.
                </div>
              </div>

              {/* Skip Tools */}
              <div>
                <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
                  Skip Tools
                  {(form.skipToolIds?.length ?? 0) > 0
                    ? ` (${form.skipToolIds?.length} selected)`
                    : null}
                </div>
                <div className="max-h-32 overflow-y-auto border border-border bg-background p-2 space-y-1">
                  {configuredTools.map(t => {
                    const isSelected = form.skipToolIds?.includes(t.id) ?? false
                    return (
                      <button
                        key={t.id}
                        onClick={() =>
                          updateForm('skipToolIds', toggleInList(form.skipToolIds ?? [], t.id))
                        }
                        className={cn(
                          'w-full flex items-center justify-between px-2 h-6 text-[10px] transition-colors',
                          isSelected
                            ? 'bg-crit/20 text-crit'
                            : 'hover:bg-muted/30 text-muted-foreground'
                        )}
                      >
                        <span>{t.name}</span>
                        <span className="uppercase text-[9px] text-dim">{t.segment}</span>
                      </button>
                    )
                  })}
                </div>
              </div>

              {/* Domains (Segment[]) */}
              <div>
                <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
                  Domains
                  {(form.segments?.length ?? 0) > 0 ? ` (${form.segments?.length} selected)` : null}
                </div>
                <div className="flex gap-2 flex-wrap">
                  {configuredSegments.map(d => {
                    const isSelected = form.segments?.includes(d) ?? false
                    return (
                      <button
                        key={d}
                        onClick={() => updateForm('segments', toggleInList(form.segments ?? [], d))}
                        className={cn(
                          'px-3 h-7 text-[10px] uppercase tracking-wider border transition-colors',
                          isSelected
                            ? 'border-accent bg-accent/20 text-accent'
                            : 'border-border text-muted-foreground hover:border-muted-foreground'
                        )}
                      >
                        {SEGMENT_LABEL[d]}
                      </button>
                    )
                  })}
                </div>
                <div className="text-[10px] text-dim mt-1">Leave empty to run all domains</div>
              </div>

              {/* Skip Enrichment */}
              <div>
                <button
                  onClick={() => updateForm('skipEnrichment', !form.skipEnrichment)}
                  className="flex items-center gap-2"
                >
                  <span
                    className={cn(
                      'w-4 h-4 border flex items-center justify-center',
                      form.skipEnrichment ? 'border-accent bg-accent' : 'border-border'
                    )}
                  >
                    {form.skipEnrichment && <Check className="h-3 w-3 text-background" />}
                  </span>
                  <span className="text-xs text-foreground">Skip enrichment step</span>
                </button>
              </div>

              {/* Actions */}
              <div className="border-t border-border pt-4 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {!isCreatingNew && selectedScanId && (
                    <>
                      <button
                        onClick={handleDelete}
                        className="flex items-center gap-1 px-3 h-8 text-[10px] uppercase tracking-wider border border-crit text-crit hover:bg-crit/10 transition-colors"
                      >
                        <Trash2 className="h-3 w-3" />
                        Delete
                      </button>
                      <button
                        disabled={runScan.isPending}
                        onClick={() =>
                          runScan.mutate(
                            { projectId, savedScanId: selectedScanId },
                            {
                              onSuccess: () => onSelect(selectedScanId),
                              onError: err => {
                                if (err.code === 'STALE_SAVED_SCAN') {
                                  const details = err.details as {
                                    staleItems?: StaleSavedScanItem[]
                                  }
                                  setStaleItems(details.staleItems ?? [])
                                }
                              },
                            }
                          )
                        }
                        className="flex items-center gap-1 px-3 h-8 text-[10px] uppercase tracking-wider border border-accent text-accent hover:bg-accent/10 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <Play className="h-3 w-3" />
                        Run This
                      </button>
                    </>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => {
                      setSelectedScanId(null)
                      setIsCreatingNew(false)
                    }}
                    className="px-3 h-8 text-[10px] uppercase tracking-wider border border-border text-muted-foreground hover:bg-muted/30 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleSave}
                    disabled={isSaving || !form.name?.trim()}
                    className={cn(
                      'flex items-center gap-1 px-4 h-8 text-[10px] uppercase tracking-wider transition-colors',
                      form.name?.trim()
                        ? 'bg-accent text-background hover:bg-accent/80'
                        : 'bg-muted text-dim cursor-not-allowed'
                    )}
                  >
                    <Save className="h-3 w-3" />
                    {isSaving ? 'Saving...' : isCreatingNew ? 'Create' : 'Save'}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
      <StaleSavedScanModal
        open={staleItems !== null}
        staleItems={staleItems ?? []}
        onDismiss={() => setStaleItems(null)}
      />
    </>
  )
}
