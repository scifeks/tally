import { useEffect } from 'react'
import { useUI } from '@/lib/store'
import { useProjects } from '@/lib/api'

/**
 * Side-effect component: once the project list resolves, clears the
 * persisted `activeProjectId` if it points at a project that no longer
 * exists (deleted / archived between sessions). Renders nothing.
 */
export function ActiveProjectGuard(): null {
  const { data: projects, isSuccess } = useProjects()
  const activeProjectId = useUI(s => s.activeProjectId)
  const setActiveProject = useUI(s => s.setActiveProject)

  useEffect(() => {
    if (!isSuccess || !projects) return
    if (activeProjectId === null) return
    if (!projects.some(p => p.id === activeProjectId)) {
      setActiveProject(null)
    }
  }, [isSuccess, projects, activeProjectId, setActiveProject])

  return null
}
