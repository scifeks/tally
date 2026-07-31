import { useState, useCallback } from 'react'
import { Modal, ModalButton } from '@/components/Modal'
import { useCreateProject } from '@/lib/api'

const NAME_RE = /^[a-zA-Z0-9][a-zA-Z0-9 -]*$/

interface Props {
  open: boolean
  onClose: () => void
  onCreated: (projectId: number) => void
}

export function CreateProjectModal({ open, onClose, onCreated }: Props) {
  const [name, setName] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [departmentName, setDepartmentName] = useState('')
  const [abbreviation, setAbbreviation] = useState('')
  const [error, setError] = useState<string | null>(null)

  const createProject = useCreateProject()

  const trimmedName = name.trim()
  const nameValid = trimmedName.length > 0 && NAME_RE.test(trimmedName)
  const canSubmit = nameValid && !createProject.isPending

  const resetForm = useCallback(() => {
    setName('')
    setCompanyName('')
    setDepartmentName('')
    setAbbreviation('')
    setError(null)
    createProject.reset()
  }, [createProject])

  const handleClose = useCallback(() => {
    resetForm()
    onClose()
  }, [resetForm, onClose])

  const handleSubmit = useCallback(() => {
    if (!canSubmit) return
    setError(null)
    createProject.mutate(
      {
        name: trimmedName,
        companyName: companyName.trim() || undefined,
        departmentName: departmentName.trim() || undefined,
        abbreviation: abbreviation.trim() || undefined,
      },
      {
        onSuccess: project => {
          resetForm()
          onClose()
          onCreated(project.id)
        },
        onError: err => {
          setError(err.message)
        },
      }
    )
  }, [
    canSubmit,
    trimmedName,
    companyName,
    departmentName,
    abbreviation,
    createProject,
    resetForm,
    onClose,
    onCreated,
  ])

  const labelCls = 'block text-[10px] uppercase tracking-[0.15em] text-muted-foreground mb-1'
  const inputCls =
    'w-full bg-background border border-border px-2 py-1.5 text-xs text-foreground placeholder:text-dim outline-none focus:border-accent'

  return (
    <Modal
      open={open}
      title="Create Project"
      onClose={handleClose}
      width="sm"
      footer={
        <>
          <ModalButton onClick={handleClose}>Cancel</ModalButton>
          <ModalButton variant="primary" onClick={handleSubmit} disabled={!canSubmit}>
            {createProject.isPending ? 'Creating...' : 'Create'}
          </ModalButton>
        </>
      }
    >
      <div className="space-y-3">
        <div>
          <label htmlFor="project-name" className={labelCls}>
            Project Name <span className="text-crit">*</span>
          </label>
          <input
            id="project-name"
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="my-project"
            className={inputCls}
          />
          {trimmedName && !nameValid && (
            <p className="text-[10px] text-crit mt-1">
              Must start with a letter or digit. Letters, digits, spaces, and hyphens only.
            </p>
          )}
        </div>

        <div>
          <label htmlFor="company-name" className={labelCls}>
            Company Name
          </label>
          <input
            id="company-name"
            type="text"
            value={companyName}
            onChange={e => setCompanyName(e.target.value)}
            placeholder="Acme Corp"
            className={inputCls}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="department-name" className={labelCls}>
              Department
            </label>
            <input
              id="department-name"
              type="text"
              value={departmentName}
              onChange={e => setDepartmentName(e.target.value)}
              placeholder="Security"
              className={inputCls}
            />
          </div>
          <div>
            <label htmlFor="abbreviation" className={labelCls}>
              Abbreviation
            </label>
            <input
              id="abbreviation"
              type="text"
              value={abbreviation}
              onChange={e => setAbbreviation(e.target.value.slice(0, 3))}
              placeholder="ACM"
              maxLength={3}
              className={inputCls}
            />
          </div>
        </div>

        {error && (
          <p className="text-[10px] text-crit border border-crit/30 bg-crit/5 px-2 py-1.5">
            {error}
          </p>
        )}
      </div>
    </Modal>
  )
}
