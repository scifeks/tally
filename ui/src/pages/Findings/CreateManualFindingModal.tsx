import { useState, useEffect } from 'react'
import { Modal, ModalButton } from '@/components/Modal'
import { useFieldSpecs, useRepositories, useProjectScanConfig, useCreateFinding } from '@/lib/api'
import { TagInput } from '@/pages/Config/shared'

interface FormState {
  title: string
  severity: string
  status: string
  confidence: string
  segment: string
  findingType: string
  repoId: string
  file: string
  url: string
  cwe: string[]
  vulnerabilityId: string
  description: string
  notes: string
}

interface CreateManualFindingModalProps {
  open: boolean
  onClose: () => void
  segment: string
  projectId: number
}

const labelCls = 'text-[10px] uppercase tracking-[0.15em] text-muted-foreground'
const inputCls =
  'w-full bg-background border border-border px-2 py-1.5 text-xs text-foreground placeholder:text-dim outline-none focus:border-accent'
const selectCls =
  'w-full bg-background border border-border px-2 py-1.5 text-xs text-foreground outline-none focus:border-accent'

function initialFormState(segment: string): FormState {
  return {
    title: '',
    severity: '',
    status: 'active',
    confidence: '',
    segment,
    findingType: '',
    repoId: '',
    file: '',
    url: '',
    cwe: [],
    vulnerabilityId: '',
    description: '',
    notes: '',
  }
}

export function CreateManualFindingModal({
  open,
  onClose,
  segment,
  projectId,
}: CreateManualFindingModalProps) {
  const [form, setForm] = useState<FormState>(() => initialFormState(segment))
  const { data: fieldSpecs } = useFieldSpecs()
  const { data: repositories = [] } = useRepositories(projectId)
  const { data: scanConfig } = useProjectScanConfig(projectId)
  const createMutation = useCreateFinding()

  useEffect(() => {
    if (open) {
      setForm(initialFormState(segment))
    }
  }, [open, segment])

  const updateField = (field: Exclude<keyof FormState, 'cwe'>, value: string) => {
    setForm(f => ({ ...f, [field]: value }))
  }

  const hasLocationData = form.repoId !== '' || form.file !== '' || form.url !== ''

  const isValid = form.title.trim() !== '' && form.severity !== '' && hasLocationData

  const handleSubmit = () => {
    if (!isValid) return

    const input = {
      title: form.title.trim(),
      severity: form.severity,
      segment: form.segment,
      ...(form.repoId && { repoId: parseInt(form.repoId, 10) }),
      ...(form.file && { file: form.file.trim() }),
      ...(form.url && { url: form.url.trim() }),
      ...(form.status && { status: form.status }),
      ...(form.confidence && { confidence: form.confidence }),
      ...(form.findingType && { findingType: [form.findingType] }),
      ...(form.cwe.length > 0 && { cwe: form.cwe }),
      ...(form.vulnerabilityId && { vulnerabilityId: form.vulnerabilityId.trim() }),
      ...(form.description && { description: form.description.trim() }),
      ...(form.notes && { notes: form.notes.trim() }),
    }

    createMutation.mutate(
      { projectId: String(projectId), input },
      {
        onSuccess: () => {
          setForm(initialFormState(segment))
          onClose()
        },
      }
    )
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="add manual finding"
      width="lg"
      footer={
        <>
          <ModalButton onClick={onClose}>cancel</ModalButton>
          <ModalButton
            variant="primary"
            onClick={handleSubmit}
            disabled={!isValid || createMutation.isPending}
          >
            &gt; create
          </ModalButton>
        </>
      }
    >
      <div className="space-y-5">
        <label className={labelCls}>
          TITLE <span className="text-crit">*</span>
          <input
            type="text"
            value={form.title}
            onChange={e => updateField('title', e.target.value)}
            className={inputCls}
            placeholder="finding title"
          />
        </label>

        <div className="grid grid-cols-3 gap-3">
          <label className={labelCls}>
            SEVERITY <span className="text-crit">*</span>
            <select
              value={form.severity}
              onChange={e => updateField('severity', e.target.value)}
              className={selectCls}
            >
              <option value="">select...</option>
              {fieldSpecs?.severities.map(sev => (
                <option key={sev} value={sev}>
                  {sev}
                </option>
              ))}
            </select>
          </label>

          <label className={labelCls}>
            STATUS
            <select
              value={form.status}
              onChange={e => updateField('status', e.target.value)}
              className={selectCls}
            >
              <option value="">select...</option>
              {fieldSpecs?.statuses.map(st => (
                <option key={st} value={st}>
                  {st}
                </option>
              ))}
            </select>
          </label>

          <label className={labelCls}>
            CONFIDENCE
            <select
              value={form.confidence}
              onChange={e => updateField('confidence', e.target.value)}
              className={selectCls}
            >
              <option value="">select...</option>
              {fieldSpecs?.confidenceLevels.map(conf => (
                <option key={conf} value={conf}>
                  {conf}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <label className={labelCls}>
            SEGMENT
            <select
              value={form.segment}
              onChange={e => updateField('segment', e.target.value)}
              className={selectCls}
            >
              {scanConfig?.segments.map(seg => (
                <option key={seg} value={seg}>
                  {seg}
                </option>
              ))}
            </select>
          </label>

          <label className={labelCls}>
            FINDING TYPE
            <select
              value={form.findingType}
              onChange={e => updateField('findingType', e.target.value)}
              className={selectCls}
            >
              <option value="">select...</option>
              {fieldSpecs?.findingTypes.map(ft => (
                <option key={ft} value={ft}>
                  {ft}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="border-t border-border/50 pt-3">
          <span className={labelCls}>
            LOCATION <span className="text-crit">*</span>
            <span className="text-dim text-[9px] tracking-normal normal-case ml-2">
              at least one required
            </span>
          </span>
          <div className="grid grid-cols-3 gap-3 mt-2">
            <label className={labelCls}>
              REPO
              <select
                value={form.repoId}
                onChange={e => updateField('repoId', e.target.value)}
                className={selectCls}
              >
                <option value="">select...</option>
                {repositories.map(repo => (
                  <option key={repo.id} value={String(repo.id)}>
                    {repo.name}
                  </option>
                ))}
              </select>
            </label>

            <label className={labelCls}>
              FILE
              <input
                type="text"
                value={form.file}
                onChange={e => updateField('file', e.target.value)}
                className={inputCls}
                placeholder="file path"
              />
            </label>

            <label className={labelCls}>
              URL
              <input
                type="text"
                value={form.url}
                onChange={e => updateField('url', e.target.value)}
                className={inputCls}
                placeholder="url"
              />
            </label>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <div className={labelCls}>CWE</div>
            <TagInput
              value={form.cwe}
              onChange={cwe => setForm(f => ({ ...f, cwe }))}
              placeholder="type and press Enter or comma"
            />
          </div>

          <label className={labelCls}>
            VULNERABILITY ID
            <input
              type="text"
              value={form.vulnerabilityId}
              onChange={e => updateField('vulnerabilityId', e.target.value)}
              className={`${inputCls} min-h-[36px]`}
              placeholder="CVE, etc."
            />
          </label>
        </div>

        <label className={labelCls}>
          DESCRIPTION
          <textarea
            value={form.description}
            onChange={e => updateField('description', e.target.value)}
            className={`${inputCls} resize-none`}
            placeholder="detailed description"
            rows={3}
          />
        </label>

        <label className={labelCls}>
          NOTES
          <textarea
            value={form.notes}
            onChange={e => updateField('notes', e.target.value)}
            className={`${inputCls} resize-none`}
            placeholder="internal notes"
            rows={3}
          />
        </label>
      </div>
    </Modal>
  )
}
