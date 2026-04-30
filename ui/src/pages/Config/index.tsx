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
import { ConfigPanel } from './ConfigPanel'
import { ProjectInfoSection } from './ProjectInfoSection'
import { RepositorySection } from './RepositorySection'
import { ToolOverridesSection } from './ToolOverridesSection'
import { NoProjectSelectedState } from '@/components/NoProjectSelectedState'
import { ConfigMutationErrorModal } from '@/components/ConfigMutationErrorModal'

// ─── Main Config Page ─────────────────────────────────────────────────────────

export default function Config() {
  const activeProjectId = useUI(s => s.activeProjectId)
  const projectId = activeProjectId ?? 0

  const { data: projects = [] } = useProjects()
  const { data: projectInfo } = useProjectInfo(projectId)
  const { data: repositories = [] } = useRepositories(projectId)
  const { data: toolCatalog = [] } = useToolCatalog()
  const { data: toolOverrides = [] } = useToolOverrides(projectId)

  const updateProjectInfo = useUpdateProjectInfo()
  const saveRepository = useSaveRepository()
  const deleteRepository = useDeleteRepository()
  const updateRepoAuth = useUpdateRepoAuth()
  const saveToolOverride = useSaveToolOverride()
  const deleteToolOverride = useDeleteToolOverride()

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
          onSave={updates => updateProjectInfo.mutate({ projectId, updates })}
          isSaving={updateProjectInfo.isPending}
        />

        <div className="grid grid-cols-2 gap-4">
          <RepositorySection
            repositories={repositories}
            projectId={projectId}
            onSave={(repo, isNew, endpointFile) =>
              saveRepository.mutate({ projectId, repo, isNew, endpointFile })
            }
            onDelete={repoId => deleteRepository.mutate({ projectId, repoId })}
            onUpdateAuth={(repoId, auth) => updateRepoAuth.mutate({ projectId, repoId, auth })}
            isSaving={saveRepository.isPending}
            isSavingAuth={updateRepoAuth.isPending}
            authSavedAt={updateRepoAuth.isSuccess ? Date.now() : null}
          />

          <ToolOverridesSection
            catalog={toolCatalog}
            overrides={toolOverrides}
            onSave={(override, isNew) => saveToolOverride.mutate({ projectId, override, isNew })}
            onDelete={toolId => deleteToolOverride.mutate({ projectId, toolId })}
            isSaving={saveToolOverride.isPending}
          />
        </div>
      </div>

      <ConfigMutationErrorModal />
    </div>
  )
}
