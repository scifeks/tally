import { useState } from 'react'
import { Wrench } from 'lucide-react'
import { useUI } from '@/lib/store'
import {
  useProjects,
  useProjectInfo,
  useUpdateProjectInfo,
  useRepositories,
  useSaveRepository,
  useDeleteRepository,
  useUpdateRepoAuth,
  useToolCatalog,
  useToolOverrides,
  useSaveToolOverride,
  useDeleteToolOverride,
} from '@/lib/api'
import { Panel } from '@/components/tty'
import { ConfigPanel } from './ConfigPanel'
import { ProjectInfoSection } from './ProjectInfoSection'
import { RepositorySection } from './RepositorySection'
import { ToolOverridesSection } from './ToolOverridesSection'
import { DocumentsSection } from './DocumentsSection'
import { SectionHeader } from './shared'
import { NoProjectSelectedState } from '@/components/NoProjectSelectedState'
import { ConfigMutationErrorModal } from '@/components/ConfigMutationErrorModal'

// ─── Main Config Page ─────────────────────────────────────────────────────────

export default function Config() {
  const activeProjectId = useUI(s => s.activeProjectId)
  const showToast = useUI(s => s.showToast)
  const projectId = activeProjectId ?? 0

  const { data: projects = [] } = useProjects()
  const { data: projectInfo } = useProjectInfo(projectId)
  const { data: repositories = [] } = useRepositories(projectId)
  const toolCatalogQuery = useToolCatalog()
  const toolOverridesQuery = useToolOverrides(projectId)
  const toolCatalog = toolCatalogQuery.data ?? []
  const toolOverrides = toolOverridesQuery.data ?? []

  const updateProjectInfo = useUpdateProjectInfo()
  const saveRepository = useSaveRepository()
  const deleteRepository = useDeleteRepository()
  const updateRepoAuth = useUpdateRepoAuth()
  const saveToolOverride = useSaveToolOverride()
  const deleteToolOverride = useDeleteToolOverride()

  // Bumped after a successful repo save so RepositorySection knows when
  // it's safe to clear the file input ref (blob-detach race fix).
  const [repoSaveCompletedAt, setRepoSaveCompletedAt] = useState<number | null>(null)

  const project = projects.find(p => p.id === activeProjectId)

  if (activeProjectId === null) {
    return <NoProjectSelectedState projects={projects} />
  }

  return (
    <div className="h-full flex flex-col min-h-0 p-4 gap-4">
      <div className="flex items-start gap-6 shrink-0">
        <ConfigPanel active size={180} />

        <div className="flex-1 flex flex-col gap-2">
          <div className="flex items-center gap-4">
            <span className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
              <span className="text-accent">[</span> PROJECT <span className="text-accent">]</span>
            </span>
            <span className="text-sm text-primary font-bold">
              {project?.code} / {project?.name}
            </span>
          </div>
          <div className="text-xs text-dim max-w-xl">
            Configure project settings, manage repositories, and set up tool overrides. Changes to
            repositories and tools apply to future scans only.
          </div>
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto space-y-4">
        <ProjectInfoSection
          projectInfo={projectInfo ?? null}
          onSave={updates =>
            updateProjectInfo.mutate(
              { projectId, updates },
              { onSuccess: () => showToast('Project info updated') }
            )
          }
          isSaving={updateProjectInfo.isPending}
        />

        <div className="grid grid-cols-2 gap-4">
          <RepositorySection
            repositories={repositories}
            projectId={projectId}
            onSave={(repo, isNew, endpointFile, garakConfigFile) =>
              saveRepository.mutate(
                { projectId, repo, isNew, endpointFile, garakConfigFile },
                {
                  onSuccess: () => {
                    setRepoSaveCompletedAt(Date.now())
                    showToast(isNew ? 'Repository created' : 'Repository saved')
                  },
                }
              )
            }
            onDelete={repoId =>
              deleteRepository.mutate(
                { projectId, repoId },
                { onSuccess: () => showToast('Repository deleted') }
              )
            }
            onUpdateAuth={(repoId, auth) =>
              updateRepoAuth.mutate(
                { projectId, repoId, auth },
                { onSuccess: () => showToast('Auth credentials saved') }
              )
            }
            isSaving={saveRepository.isPending}
            isSavingAuth={updateRepoAuth.isPending}
            authSavedAt={updateRepoAuth.isSuccess ? Date.now() : null}
            saveCompletedAt={repoSaveCompletedAt}
          />

          {toolCatalogQuery.data && toolOverridesQuery.data ? (
            <ToolOverridesSection
              catalog={toolCatalog}
              overrides={toolOverrides}
              projectId={projectId}
              onSave={async (override, isNew) => {
                await saveToolOverride.mutateAsync({
                  projectId,
                  override,
                  isNew,
                })
                showToast(isNew ? 'Tool override created' : 'Tool override saved')
              }}
              onDelete={toolId =>
                deleteToolOverride.mutate(
                  { projectId, toolId },
                  { onSuccess: () => showToast('Tool override removed') }
                )
              }
              isSaving={saveToolOverride.isPending}
            />
          ) : (
            <Panel>
              <SectionHeader icon={Wrench} title="TOOL OVERRIDES" />
              <div className="text-sm text-dim py-8 text-center">Loading tool configuration…</div>
            </Panel>
          )}
        </div>

        <DocumentsSection projectId={projectId} />
      </div>

      <ConfigMutationErrorModal />
    </div>
  )
}
