import { useState, useEffect } from 'react'
import {
  Database,
  ChevronDown,
  Plus,
  Trash2,
  Save,
  RotateCcw,
  Check,
  AlertCircle,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Panel } from '@/components/tty'
import type { RepositoryConfig, RepoType, RepoLocationMode } from '@/lib/types'
import { SectionHeader, TagInput } from './shared'

// ─── Repository Section ───────────────────────────────────────────────────────

export function RepositorySection({
  repositories,
  projectId,
  onSave,
  onDelete,
  isSaving,
}: {
  repositories: RepositoryConfig[]
  projectId: string
  onSave: (repo: RepositoryConfig, isNew: boolean) => void
  onDelete: (repoId: string) => void
  isSaving: boolean
}) {
  const [selectedId, setSelectedId] = useState<string | 'new' | null>(null)
  const [form, setForm] = useState<Partial<RepositoryConfig>>({})
  const [_isDirty, setIsDirty] = useState(false)

  useEffect(() => {
    if (selectedId === 'new') {
      setForm({
        projectId,
        name: '',
        types: [],
        locationMode: 'local',
        localPath: '',
        languages: [],
        testDirectories: [],
        ignoreDirectories: [],
        baseUrls: [],
        alsoRunCrawlers: true,
        katana: { headless: false, crawlDepth: 10 },
      })
      setIsDirty(false)
    } else if (selectedId) {
      const repo = repositories.find(r => r.id === selectedId)
      if (repo) {
        setForm({ ...repo })
        setIsDirty(false)
      }
    }
  }, [selectedId, repositories, projectId])

  const updateField = <K extends keyof RepositoryConfig>(field: K, value: RepositoryConfig[K]) => {
    setForm(f => ({ ...f, [field]: value }))
    setIsDirty(true)
  }

  const handleSave = () => {
    if (!form.name) return
    onSave(form as RepositoryConfig, selectedId === 'new')
    if (selectedId === 'new') setSelectedId(null)
    setIsDirty(false)
  }

  const handleReset = () => {
    if (selectedId === 'new') {
      setSelectedId(null)
    } else if (selectedId) {
      const repo = repositories.find(r => r.id === selectedId)
      if (repo) setForm({ ...repo })
    }
    setIsDirty(false)
  }

  const handleDelete = () => {
    if (selectedId && selectedId !== 'new') {
      if (confirm('Delete this repository? This cannot be undone.')) {
        onDelete(selectedId)
        setSelectedId(null)
      }
    }
  }

  const toggleType = (type: RepoType) => {
    const current = form.types ?? []
    if (type === 'library') {
      updateField('types', current.includes('library') ? [] : ['library'])
    } else {
      if (current.includes('library')) return
      if (current.includes(type)) {
        updateField(
          'types',
          current.filter(t => t !== type)
        )
      } else {
        updateField('types', [...current, type])
      }
    }
  }

  const isLibrary = form.types?.includes('library') ?? false
  const hasBaseUrls = (form.baseUrls?.length ?? 0) > 0
  const hasEndpointFile = Boolean(form.endpointFile)
  const showCrawlerQuestion = hasBaseUrls && hasEndpointFile
  const showKatanaFields = hasBaseUrls && (!hasEndpointFile || form.alsoRunCrawlers)

  return (
    <Panel>
      <SectionHeader icon={Database} title="REPOSITORIES">
        <div className="flex items-center gap-2">
          <div className="relative">
            <select
              value={selectedId ?? ''}
              onChange={e => setSelectedId(e.target.value || null)}
              className="h-7 pl-2 pr-6 bg-background border border-border text-xs text-foreground appearance-none cursor-pointer focus:border-accent focus:outline-none"
            >
              <option value="">Select repository...</option>
              {repositories.map(r => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 h-3 w-3 text-dim pointer-events-none" />
          </div>
          <button
            onClick={() => setSelectedId('new')}
            className="flex items-center gap-1 px-2 h-7 text-[10px] uppercase tracking-wider border border-border text-muted-foreground hover:bg-muted/30 transition-colors"
          >
            <Plus className="h-3 w-3" />
            New
          </button>
        </div>
      </SectionHeader>

      {!selectedId && (
        <div className="text-sm text-dim py-8 text-center">
          Select a repository to edit or create a new one
        </div>
      )}

      {selectedId && (
        <div className="space-y-4">
          {/* Identity */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label
                htmlFor="repo-name"
                className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
              >
                Name <span className="text-crit">*</span>
              </label>
              <input
                id="repo-name"
                type="text"
                value={form.name ?? ''}
                onChange={e => updateField('name', e.target.value)}
                className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none"
              />
            </div>
            <div>
              <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                Type <span className="text-crit">*</span>
              </div>
              <div className="flex gap-2">
                {(['library', 'api', 'ui'] as RepoType[]).map(type => {
                  const selected = form.types?.includes(type)
                  const disabled = type !== 'library' && isLibrary
                  return (
                    <button
                      key={type}
                      onClick={() => toggleType(type)}
                      disabled={disabled}
                      className={cn(
                        'px-3 h-8 text-[10px] uppercase tracking-wider border transition-colors',
                        selected
                          ? 'border-accent bg-accent/20 text-accent'
                          : disabled
                            ? 'border-border/50 text-dim cursor-not-allowed'
                            : 'border-border text-muted-foreground hover:border-muted-foreground'
                      )}
                    >
                      {type}
                    </button>
                  )
                })}
              </div>
              <div className="text-[9px] text-dim mt-1">
                library cannot be combined with api or ui
              </div>
            </div>
          </div>

          {/* Location */}
          <div className="border-t border-border pt-4">
            <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
              Location Mode
            </div>
            <div className="flex gap-2 mb-3">
              {(['local', 'docker'] as RepoLocationMode[]).map(mode => (
                <button
                  key={mode}
                  onClick={() => updateField('locationMode', mode)}
                  className={cn(
                    'px-4 h-8 text-[10px] uppercase tracking-wider border transition-colors',
                    form.locationMode === mode
                      ? 'border-accent bg-accent/20 text-accent'
                      : 'border-border text-muted-foreground hover:border-muted-foreground'
                  )}
                >
                  {mode}
                </button>
              ))}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label
                  htmlFor="repo-local-path"
                  className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
                >
                  Local Path <span className="text-crit">*</span>
                </label>
                <input
                  id="repo-local-path"
                  type="text"
                  value={form.localPath ?? ''}
                  onChange={e => updateField('localPath', e.target.value)}
                  placeholder="/path/to/repo"
                  className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground font-mono focus:border-accent focus:outline-none"
                />
                {form.locationMode === 'docker' && (
                  <div className="text-[9px] text-dim mt-1">
                    Required for language detection and local tool execution
                  </div>
                )}
              </div>

              {form.locationMode === 'docker' && (
                <>
                  <div>
                    <label
                      htmlFor="repo-container-name"
                      className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
                    >
                      Container Name <span className="text-crit">*</span>
                    </label>
                    <input
                      id="repo-container-name"
                      type="text"
                      value={form.docker?.containerName ?? ''}
                      onChange={e =>
                        updateField('docker', {
                          ...form.docker,
                          containerName: e.target.value,
                          mountPoint: form.docker?.mountPoint ?? '',
                        })
                      }
                      className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none"
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="repo-mount-point"
                      className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
                    >
                      Mount Point <span className="text-crit">*</span>
                    </label>
                    <input
                      id="repo-mount-point"
                      type="text"
                      value={form.docker?.mountPoint ?? ''}
                      onChange={e =>
                        updateField('docker', {
                          ...form.docker,
                          containerName: form.docker?.containerName ?? '',
                          mountPoint: e.target.value,
                        })
                      }
                      placeholder="/app"
                      className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground font-mono focus:border-accent focus:outline-none"
                    />
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Code Context */}
          <div className="border-t border-border pt-4 grid grid-cols-3 gap-4">
            <div>
              <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                Languages <span className="text-crit">*</span>
              </div>
              <TagInput
                value={form.languages ?? []}
                onChange={tags => updateField('languages', tags)}
                placeholder="python, javascript..."
              />
            </div>
            <div>
              <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                Test Directories
              </div>
              <TagInput
                value={form.testDirectories ?? []}
                onChange={tags => updateField('testDirectories', tags)}
                placeholder="tests, spec..."
              />
            </div>
            <div>
              <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                Ignore Directories
              </div>
              <TagInput
                value={form.ignoreDirectories ?? []}
                onChange={tags => updateField('ignoreDirectories', tags)}
                placeholder="vendor, node_modules..."
              />
            </div>
          </div>

          {/* API Targets */}
          <div className="border-t border-border pt-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                  Base URLs
                </div>
                <TagInput
                  value={form.baseUrls ?? []}
                  onChange={tags => updateField('baseUrls', tags)}
                  placeholder="https://api.example.com"
                />
                <div className="text-[9px] text-dim mt-1">
                  First URL is used as canonical scope for scans
                </div>
              </div>
              <div>
                <label
                  htmlFor="repo-endpoint-file"
                  className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
                >
                  Endpoint File
                </label>
                <input
                  id="repo-endpoint-file"
                  type="text"
                  value={form.endpointFile ?? ''}
                  onChange={e => updateField('endpointFile', e.target.value)}
                  placeholder="/path/to/openapi.yaml"
                  className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground font-mono focus:border-accent focus:outline-none"
                />
                <div className="text-[9px] text-dim mt-1">
                  OpenAPI, Swagger, Postman, HAR, or Katana JSONL
                </div>
              </div>
            </div>

            {showCrawlerQuestion && (
              <div className="mt-3 p-3 border border-border bg-muted/20">
                <div className="flex items-center gap-2 cursor-pointer">
                  <button
                    onClick={() => updateField('alsoRunCrawlers', !form.alsoRunCrawlers)}
                    className={cn(
                      'w-4 h-4 border flex items-center justify-center transition-colors',
                      form.alsoRunCrawlers
                        ? 'border-accent bg-accent text-background'
                        : 'border-border hover:border-muted-foreground'
                    )}
                  >
                    {form.alsoRunCrawlers && <Check className="h-3 w-3" />}
                  </button>
                  <span className="text-xs text-foreground">
                    Also run live crawlers to supplement the endpoint file?
                  </span>
                </div>
                {!form.alsoRunCrawlers && (
                  <div className="mt-2 flex items-start gap-2 text-[10px] text-high">
                    <AlertCircle className="h-3 w-3 mt-0.5 shrink-0" />
                    <span>
                      ZAP will rely entirely on the endpoint file. Results are only as good as the
                      file.
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Katana Settings */}
          {showKatanaFields && (
            <div className="border-t border-border pt-4">
              <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
                Crawler Settings
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="flex items-center gap-2 cursor-pointer">
                    <button
                      onClick={() => {
                        const newHeadless = !form.katana?.headless
                        updateField('katana', {
                          headless: newHeadless,
                          crawlDepth: newHeadless
                            ? Math.min(form.katana?.crawlDepth ?? 10, 5)
                            : (form.katana?.crawlDepth ?? 10),
                        })
                      }}
                      className={cn(
                        'w-4 h-4 border flex items-center justify-center transition-colors',
                        form.katana?.headless
                          ? 'border-accent bg-accent text-background'
                          : 'border-border hover:border-muted-foreground'
                      )}
                    >
                      {form.katana?.headless && <Check className="h-3 w-3" />}
                    </button>
                    <span className="text-xs text-foreground">Katana headless mode</span>
                  </div>
                  <div className="text-[9px] text-dim mt-1 ml-6">
                    Uses Chrome to render JavaScript routes. Slower, required for SPAs.
                  </div>
                  {form.detected?.isSpa && (
                    <div className="mt-1 ml-6 flex items-center gap-1 text-[9px] text-high">
                      <AlertCircle className="h-3 w-3" />
                      SPA detected — headless recommended
                    </div>
                  )}
                </div>
                <div>
                  <label
                    htmlFor="repo-crawl-depth"
                    className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
                  >
                    Crawl Depth{' '}
                    {form.katana?.headless && (
                      <span className="text-high">(max 5 in headless)</span>
                    )}
                  </label>
                  <input
                    id="repo-crawl-depth"
                    type="number"
                    min={1}
                    max={form.katana?.headless ? 5 : 20}
                    value={form.katana?.crawlDepth ?? 10}
                    onChange={e =>
                      updateField('katana', {
                        headless: form.katana?.headless ?? false,
                        crawlDepth: parseInt(e.target.value) || 10,
                      })
                    }
                    className="w-24 h-8 px-2 bg-background border border-border text-xs text-foreground tabular-nums focus:border-accent focus:outline-none"
                  />
                </div>
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="border-t border-border pt-4 flex items-center justify-between">
            <div>
              {selectedId !== 'new' && (
                <button
                  onClick={handleDelete}
                  className="flex items-center gap-1 px-3 h-8 text-[10px] uppercase tracking-wider border border-crit text-crit hover:bg-crit/10 transition-colors"
                >
                  <Trash2 className="h-3 w-3" />
                  Delete
                </button>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleReset}
                className="flex items-center gap-1 px-3 h-8 text-[10px] uppercase tracking-wider border border-border text-muted-foreground hover:bg-muted/30 transition-colors"
              >
                <RotateCcw className="h-3 w-3" />
                Reset
              </button>
              <button
                onClick={handleSave}
                disabled={
                  !form.name || !form.localPath || (form.types?.length ?? 0) === 0 || isSaving
                }
                className={cn(
                  'flex items-center gap-1 px-4 h-8 text-[10px] uppercase tracking-wider transition-colors',
                  form.name && form.localPath && (form.types?.length ?? 0) > 0
                    ? 'bg-accent text-background hover:bg-accent/80'
                    : 'bg-muted text-dim cursor-not-allowed'
                )}
              >
                <Save className="h-3 w-3" />
                {isSaving ? 'Saving...' : selectedId === 'new' ? 'Create' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </Panel>
  )
}
