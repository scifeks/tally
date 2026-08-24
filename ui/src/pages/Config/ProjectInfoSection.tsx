import { useState, useEffect } from 'react'
import { Settings, RotateCcw, Save, Loader2 } from 'lucide-react'
import { cn, formatDate } from '@/lib/utils'
import { Panel } from '@/components/tty'
import type { ProjectInfo, ProjectInfoUpdate } from '@/lib/types'
import { SectionHeader } from './shared'

// ─── Project Info Section ─────────────────────────────────────────────────────

interface FormState {
  companyName: string
  departmentName: string
  abbreviation: string
}

function initialForm(info: ProjectInfo | null): FormState {
  return {
    companyName: info?.companyName ?? '',
    departmentName: info?.departmentName ?? '',
    abbreviation: info?.abbreviation ?? '',
  }
}

function diff(form: FormState, info: ProjectInfo | null): ProjectInfoUpdate {
  const out: ProjectInfoUpdate = {}
  if (!info) return out
  if (form.companyName !== info.companyName) out.companyName = form.companyName
  if (form.departmentName !== info.departmentName) out.departmentName = form.departmentName
  if (form.abbreviation !== info.abbreviation) out.abbreviation = form.abbreviation
  return out
}

export function ProjectInfoSection({
  projectInfo,
  onSave,
  isSaving,
}: {
  projectInfo: ProjectInfo | null
  onSave: (updates: ProjectInfoUpdate) => void
  isSaving: boolean
}) {
  const [form, setForm] = useState<FormState>(() => initialForm(projectInfo))
  const [isDirty, setIsDirty] = useState(false)

  useEffect(() => {
    setForm(initialForm(projectInfo))
    setIsDirty(false)
  }, [projectInfo])

  const updateField = (field: keyof FormState, value: string) => {
    setForm(f => ({ ...f, [field]: value }))
    setIsDirty(true)
  }

  const handleSave = () => {
    const updates = diff(form, projectInfo)
    if (Object.keys(updates).length === 0) {
      setIsDirty(false)
      return
    }
    onSave(updates)
  }

  const handleReset = () => {
    setForm(initialForm(projectInfo))
    setIsDirty(false)
  }

  if (!projectInfo) {
    return (
      <Panel>
        <SectionHeader icon={Settings} title="PROJECT INFO" />
        <div className="text-sm text-dim">Loading project info...</div>
      </Panel>
    )
  }

  return (
    <Panel bodyClassName="p-4">
      <SectionHeader icon={Settings} title="PROJECT INFO">
        <div className="flex items-center gap-2">
          <button
            onClick={handleReset}
            disabled={!isDirty || isSaving}
            className={cn(
              'flex items-center gap-1 px-3 h-7 text-[10px] uppercase tracking-wider border transition-colors',
              isDirty && !isSaving
                ? 'border-border-strong text-muted-foreground hover:border-primary/50 hover:text-foreground'
                : 'border-border/50 text-dim opacity-40 cursor-not-allowed'
            )}
          >
            <RotateCcw className="h-3 w-3" />
            Reset
          </button>
          <button
            onClick={handleSave}
            disabled={!isDirty || isSaving}
            className={cn(
              'flex items-center gap-1 px-3 h-7 text-[10px] uppercase tracking-wider transition-colors',
              isDirty && !isSaving
                ? 'bg-accent text-background hover:bg-accent/70'
                : 'bg-muted text-dim opacity-40 cursor-not-allowed'
            )}
          >
            {isSaving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
            {isSaving ? 'Saving...' : 'Update'}
          </button>
        </div>
      </SectionHeader>

      <div className="grid grid-cols-2 gap-4">
        {/* Editable fields */}
        <div className="space-y-3">
          <div>
            <label
              htmlFor="proj-company-name"
              className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
            >
              Company Name
            </label>
            <input
              id="proj-company-name"
              type="text"
              value={form.companyName}
              onChange={e => updateField('companyName', e.target.value)}
              className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none"
            />
          </div>
          <div>
            <label
              htmlFor="proj-department-name"
              className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
            >
              Department Name
            </label>
            <input
              id="proj-department-name"
              type="text"
              value={form.departmentName}
              onChange={e => updateField('departmentName', e.target.value)}
              className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none"
            />
          </div>
          <div>
            <label
              htmlFor="proj-abbreviation"
              className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
            >
              Abbreviation <span className="text-dim">(max 3)</span>
            </label>
            <input
              id="proj-abbreviation"
              type="text"
              value={form.abbreviation}
              onChange={e => updateField('abbreviation', e.target.value.toUpperCase())}
              maxLength={3}
              className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none"
            />
          </div>
        </div>

        {/* Read-only info */}
        <div className="space-y-3">
          <div>
            <div className="block text-[10px] uppercase tracking-wider text-dim mb-1">
              Project Name (read-only)
            </div>
            <div className="h-8 px-2 flex items-center bg-muted/30 border border-border/50 text-xs text-dim">
              {projectInfo.name}
            </div>
          </div>
          <div>
            <div className="block text-[10px] uppercase tracking-wider text-dim mb-1">
              Path (read-only)
            </div>
            <div className="h-8 px-2 flex items-center bg-muted/30 border border-border/50 text-xs text-dim font-mono">
              {projectInfo.path}
            </div>
          </div>
          <div>
            <div className="block text-[10px] uppercase tracking-wider text-dim mb-1">Created</div>
            <div className="h-8 px-2 flex items-center bg-muted/30 border border-border/50 text-xs text-dim">
              {formatDate(projectInfo.createdAt)}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="block text-[10px] uppercase tracking-wider text-dim mb-1">
                Repositories
              </div>
              <div className="h-8 px-2 flex items-center bg-muted/30 border border-border/50 text-xs text-dim tabular-nums">
                {projectInfo.repoCount}
              </div>
            </div>
            <div>
              <div className="block text-[10px] uppercase tracking-wider text-dim mb-1">
                Findings
              </div>
              <div className="h-8 px-2 flex items-center bg-muted/30 border border-border/50 text-xs text-dim tabular-nums">
                {projectInfo.findingCount}
              </div>
            </div>
          </div>
        </div>
      </div>
    </Panel>
  )
}
