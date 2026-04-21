import { useUI } from "@/lib/store"
import {
  useProjects,
  useProjectInfo,
  useUpdateProjectInfo,
  useRepositories,
  useSaveRepository,
  useDeleteRepository,
  useToolCatalog,
  useToolOverrides,
  useSaveToolOverride,
  useDeleteToolOverride,
} from "@/lib/api"
import { ConfigPanel } from "./ConfigPanel"
import { ProjectInfoSection } from "./ProjectInfoSection"
import { RepositorySection } from "./RepositorySection"
import { ToolOverridesSection } from "./ToolOverridesSection"

// ─── Main Config Page ─────────────────────────────────────────────────────────

export default function Config() {
  const activeProjectId = useUI((s) => s.activeProjectId)

  // TODO [BACKEND]: These hooks return mock data. Replace with real API calls.
  const { data: projects = [] } = useProjects()
  const { data: projectInfo } = useProjectInfo(activeProjectId)
  const { data: repositories = [] } = useRepositories(activeProjectId)
  const { data: toolCatalog = [] } = useToolCatalog()
  const { data: toolOverrides = [] } = useToolOverrides(activeProjectId)

  const updateProjectInfo = useUpdateProjectInfo()
  const saveRepository = useSaveRepository()
  const deleteRepository = useDeleteRepository()
  const saveToolOverride = useSaveToolOverride()
  const deleteToolOverride = useDeleteToolOverride()

  const project = projects.find((p) => p.id === activeProjectId)

  return (
    <div className="h-full flex flex-col min-h-0 p-4 gap-4">
      {/* Header */}
      <div className="flex items-start gap-6 shrink-0">
        <ConfigPanel active size={180} />

        <div className="flex-1 flex flex-col gap-2">
          <div className="flex items-center gap-4">
            <span className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
              <span className="text-accent">[</span> PROJECT <span className="text-accent">]</span>
            </span>
            <span className="text-sm text-primary font-bold">{project?.code} / {project?.name}</span>
          </div>
          <div className="text-xs text-dim max-w-xl">
            Configure project settings, manage repositories, and set up tool overrides.
            Changes to repositories and tools apply to future scans only.
          </div>
        </div>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 min-h-0 overflow-y-auto space-y-4">
        {/* Project Info - full width row */}
        <ProjectInfoSection
          projectInfo={projectInfo ?? null}
          onSave={(updates) => updateProjectInfo.mutate({ projectId: activeProjectId, updates })}
          isSaving={updateProjectInfo.isPending}
        />

        {/* Repositories + Tool Overrides - 2 column layout */}
        <div className="grid grid-cols-2 gap-4">
          <RepositorySection
            repositories={repositories}
            projectId={activeProjectId}
            onSave={(repo, isNew) => saveRepository.mutate({ repo, isNew })}
            onDelete={(repoId) => deleteRepository.mutate({ repoId, projectId: activeProjectId })}
            isSaving={saveRepository.isPending}
          />

          <ToolOverridesSection
            catalog={toolCatalog}
            overrides={toolOverrides}
            projectId={activeProjectId}
            onSave={(override, isNew) => saveToolOverride.mutate({ projectId: activeProjectId, override, isNew })}
            onDelete={(toolId) => deleteToolOverride.mutate({ projectId: activeProjectId, toolId })}
            isSaving={saveToolOverride.isPending}
          />
        </div>
      </div>
    </div>
  )
}
