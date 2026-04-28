import { NavLink } from 'react-router-dom'
import { ChevronDown, Activity } from 'lucide-react'
import { useUI } from '@/lib/store'
import { useProjects, useRunningScansCount, useRuntimeDependencies } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useRef, useState, useEffect, useMemo } from 'react'
import { ScansRunningModal } from './ScansRunningModal'
import { ProjectSwitchModal } from './ProjectSwitchModal'

interface NavItem {
  to: string
  label: string
  end?: boolean
}

const baseNav: NavItem[] = [
  { to: '/', label: 'DASHBOARD', end: true },
  { to: '/findings', label: 'FINDINGS' },
  { to: '/urls', label: 'URL LISTS' },
  { to: '/scans', label: 'SCANS' },
  { to: '/triage', label: 'TRIAGE' },
  { to: '/reports', label: 'REPORTS' },
  { to: '/chat', label: 'CHAT' },
]

export function TopBar() {
  const activeProjectId = useUI(s => s.activeProjectId)
  const setActiveProject = useUI(s => s.setActiveProject)
  const triageRunStatus = useUI(s => s.triageRunStatus)

  const { data: projects = [] } = useProjects()
  const runningCount = useRunningScansCount(activeProjectId)
  const { data: runtimeDeps } = useRuntimeDependencies()

  const activeProject = activeProjectId
    ? (projects.find(p => p.id === activeProjectId) ?? null)
    : null

  const triageRunning = triageRunStatus === 'running'

  // Hide TRIAGE in chrome only when we know claude is missing. While the
  // probe is loading or reports installed, render the link.
  const primaryNav = useMemo<NavItem[]>(() => {
    const claudeDep = runtimeDeps?.dependencies.find(d => d.name === 'claude')
    const claudeMissing = claudeDep !== undefined && !claudeDep.installed
    return claudeMissing ? baseNav.filter(n => n.to !== '/triage') : baseNav
  }, [runtimeDeps])

  const [projectOpen, setProjectOpen] = useState(false)
  const [scansModalOpen, setScansModalOpen] = useState(false)
  const [pendingProjectId, setPendingProjectId] = useState<number | null>(null)

  const projectRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (projectRef.current && !projectRef.current.contains(e.target as Node))
        setProjectOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const pendingProject = projects.find(p => p.id === pendingProjectId) ?? null

  const requestSwitch = (id: number) => {
    setProjectOpen(false)
    if (id === activeProjectId) return
    // First-time selection (no project active yet) skips the confirm dialog.
    if (activeProjectId === null) {
      setActiveProject(id)
      return
    }
    setPendingProjectId(id)
  }

  const confirmSwitch = () => {
    if (pendingProjectId !== null) setActiveProject(pendingProjectId)
    setPendingProjectId(null)
  }

  return (
    <header className="border-b border-border-strong bg-background shrink-0">
      <div className="grid grid-cols-[auto_1fr] items-stretch">
        {/* Logo: spans both rows on the left */}
        <NavLink
          to="/"
          aria-label="Tally home"
          className="row-span-2 flex items-center justify-center px-6 border-r border-border-strong hover:bg-muted/40 transition-colors min-w-[220px]"
        >
          <img
            src="/tally-logo.png"
            alt="Tally"
            className="h-14 md:h-16 w-auto max-w-[240px] object-contain drop-shadow-[0_0_4px_rgba(107,211,107,0.25)]"
          />
        </NavLink>

        {/* Row 1: utility bar (scans indicator + project switcher) */}
        <div className="flex items-stretch h-11 border-b border-border">
          <div className="flex-1 flex items-center gap-4 px-4 text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
            <span className="text-dim">tally://console</span>
            <span className="hidden lg:inline text-dim">
              session: <span className="text-muted-foreground tabular-nums">0x7f3a</span>
            </span>
          </div>

          {/* Scans running — clickable, opens modal */}
          <button
            type="button"
            onClick={() => setScansModalOpen(true)}
            className={cn(
              'flex items-center gap-2 px-4 border-l border-border hover:bg-muted transition-colors',
              runningCount > 0 ? 'text-accent' : 'text-muted-foreground'
            )}
            aria-label="Open running scans"
          >
            <Activity
              className={cn(
                'h-3.5 w-3.5',
                runningCount > 0 ? 'text-accent animate-pulse' : 'text-dim'
              )}
            />
            <span className="text-[11px] uppercase tracking-wider">
              {runningCount > 0
                ? `${runningCount} scan${runningCount > 1 ? 's' : ''} running`
                : 'idle'}
            </span>
            {runningCount > 0 && <span className="text-[10px] text-dim">[ click to view ]</span>}
          </button>

          {/* Project switcher */}
          <div ref={projectRef} className="relative flex items-stretch border-l border-border">
            <button
              onClick={() => setProjectOpen(v => !v)}
              className={cn(
                'flex items-center gap-2 px-4 min-w-[260px] hover:bg-muted',
                !activeProject && 'bg-muted/40'
              )}
            >
              <span className="text-[10px] uppercase tracking-[0.2em] text-dim">project:</span>
              {activeProject ? (
                <>
                  <span className="text-xs text-primary font-bold tty-glow">
                    {activeProject.code}
                  </span>
                  <span className="text-xs text-foreground truncate">{activeProject.name}</span>
                </>
              ) : (
                <span className="text-xs text-muted-foreground italic">-- select project --</span>
              )}
              <ChevronDown className="h-3 w-3 text-muted-foreground ml-auto" />
            </button>
            {projectOpen && (
              <div className="absolute top-full right-0 mt-[-1px] w-[280px] border border-border-strong bg-background z-40">
                <div className="px-3 py-1.5 text-[10px] uppercase tracking-[0.2em] text-dim border-b border-border">
                  [ switch project ]
                </div>
                {projects.map(p => {
                  const active = p.id === activeProjectId
                  return (
                    <button
                      key={p.id}
                      onClick={() => requestSwitch(p.id)}
                      className={cn(
                        'w-full flex items-center gap-2 px-3 py-2 text-xs border-b border-border last:border-b-0 hover:bg-muted text-left',
                        active ? 'bg-muted text-accent' : 'text-foreground'
                      )}
                    >
                      <span className="text-dim">{active ? '>' : ' '}</span>
                      <span className="text-primary font-bold w-10">{p.code}</span>
                      <span>{p.name}</span>
                    </button>
                  )
                })}
                <div className="px-3 py-1.5 text-[10px] text-dim border-t border-border">
                  <span className="text-dim">{'//'}</span> switching clears selections
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Row 2: primary nav tabs.
            NOTE: no overflow-* here — an overflow ancestor clips
            absolutely-positioned descendants (e.g. the CONFIG dropdown panel),
            which was rendering the panel as a sliver peeking from the clipped
            edge. Dropdown content must be allowed to escape this row. */}
        <nav className="flex items-stretch">
          {primaryNav.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  'group relative flex items-center px-4 text-xs font-bold uppercase tracking-[0.2em] border-r border-border transition-colors h-11',
                  isActive
                    ? 'text-primary bg-muted tty-glow'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted/60'
                )
              }
            >
              {({ isActive }) => (
                <>
                  <span className={cn('mr-2', isActive ? 'text-accent' : 'text-dim')}>
                    {isActive ? '>' : ' '}
                  </span>
                  {item.label}
                  {isActive && (
                    <span className="absolute left-0 right-0 bottom-[-1px] h-[2px] bg-accent" />
                  )}
                </>
              )}
            </NavLink>
          ))}

          {/* CONFIG link */}
          <NavLink
            to="/config"
            className={({ isActive }) =>
              cn(
                'group relative flex items-center px-4 text-xs font-bold uppercase tracking-[0.2em] border-r border-border transition-colors h-11',
                isActive
                  ? 'text-primary bg-muted tty-glow'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted/60'
              )
            }
          >
            {({ isActive }) => (
              <>
                <span className={cn('mr-2', isActive ? 'text-accent' : 'text-dim')}>
                  {isActive ? '>' : ' '}
                </span>
                CONFIG
                {isActive && (
                  <span className="absolute left-0 right-0 bottom-[-1px] h-[2px] bg-accent" />
                )}
              </>
            )}
          </NavLink>
        </nav>
      </div>

      {/* Modals */}
      <ScansRunningModal open={scansModalOpen} onClose={() => setScansModalOpen(false)} />
      <ProjectSwitchModal
        open={pendingProjectId !== null}
        from={activeProject}
        to={pendingProject}
        // Block if scans or triage are running on the project we're leaving
        // (which is the active project, the only one we hold a count for).
        runningScansCount={runningCount}
        triageRunning={triageRunning}
        onConfirm={confirmSwitch}
        onCancel={() => setPendingProjectId(null)}
      />
    </header>
  )
}
