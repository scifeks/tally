import { ArrowRight, FolderOpen } from 'lucide-react'
import { useUI } from '@/lib/store'
import { useState } from 'react'
import { CreateProjectModal } from './CreateProjectModal'

export function NoProjectSelectedState({
  projects,
}: {
  projects: Array<{ id: number; code: string; name: string }>
}) {
  const setActiveProject = useUI(s => s.setActiveProject)
  const [createModalOpen, setCreateModalOpen] = useState(false)

  return (
    <div className="h-full flex items-center justify-center p-6">
      <div className="max-w-[600px] w-full">
        <div className="flex justify-center mb-8">
          <ProjectSelectGraphic />
        </div>

        <div className="text-center mb-8">
          <h2 className="text-lg font-bold uppercase tracking-[0.2em] text-foreground mb-2">
            No Project Selected
          </h2>
          <p className="text-sm text-muted-foreground leading-relaxed">
            Select a project from the dropdown above or choose one below to get started. All
            findings, scans, and configuration are scoped to the active project.
          </p>
        </div>

        {projects.length > 0 ? (
          <div className="border border-border bg-background">
            <div className="px-4 py-2 border-b border-border">
              <span className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
                <span className="text-accent">[</span> available projects{' '}
                <span className="text-accent">]</span>
              </span>
            </div>
            <div className="divide-y divide-border">
              {projects.map(p => (
                <button
                  key={p.id}
                  onClick={() => setActiveProject(p.id)}
                  className="w-full flex items-center gap-4 px-4 py-3 hover:bg-muted transition-colors text-left group"
                >
                  <FolderOpen className="h-5 w-5 text-muted-foreground group-hover:text-accent" />
                  <div className="flex-1">
                    <div className="flex items-baseline gap-2">
                      <span className="text-sm font-bold text-primary tty-glow">{p.code}</span>
                      <span className="text-sm text-foreground">{p.name}</span>
                    </div>
                  </div>
                  <ArrowRight className="h-4 w-4 text-dim group-hover:text-accent" />
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="border border-border bg-muted/30 p-6 text-center">
            <p className="text-sm text-muted-foreground mb-4">
              No projects found. Create one to get started.
            </p>
            <button
              onClick={() => setCreateModalOpen(true)}
              className="px-4 py-2 border border-accent text-accent text-xs uppercase tracking-[0.15em] font-bold hover:bg-[rgba(107,211,107,0.1)]"
            >
              + Create Project
            </button>
          </div>
        )}

        {projects.length > 0 && (
          <div className="mt-4 flex justify-center">
            <button
              onClick={() => setCreateModalOpen(true)}
              className="px-4 py-2 border border-accent text-accent text-xs uppercase tracking-[0.15em] font-bold hover:bg-[rgba(107,211,107,0.1)]"
            >
              + Create Project
            </button>
          </div>
        )}

        <div className="mt-6 text-center">
          <p className="text-[11px] text-dim">
            <span className="text-dim">{'// '}</span>
            use the project dropdown in the header to switch projects at any time
          </p>
        </div>

        <CreateProjectModal
          open={createModalOpen}
          onClose={() => setCreateModalOpen(false)}
          onCreated={id => setActiveProject(id)}
        />
      </div>
    </div>
  )
}

function ProjectSelectGraphic() {
  const size = 200

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className="shrink-0"
      aria-hidden
    >
      <g stroke="var(--color-accent)" strokeWidth={2} fill="none" opacity={0.5}>
        <path d="M 20 10 L 10 10 L 10 20" />
        <path d={`M ${size - 20} 10 L ${size - 10} 10 L ${size - 10} 20`} />
        <path d={`M 20 ${size - 10} L 10 ${size - 10} L 10 ${size - 20}`} />
        <path
          d={`M ${size - 20} ${size - 10} L ${size - 10} ${size - 10} L ${size - 10} ${size - 20}`}
        />
      </g>

      <g stroke="var(--color-border)" strokeWidth={0.5} opacity={0.2}>
        {[0.25, 0.5, 0.75].map(frac => (
          <line key={`h-${frac}`} x1={15} y1={size * frac} x2={size - 15} y2={size * frac} />
        ))}
        {[0.25, 0.5, 0.75].map(frac => (
          <line key={`v-${frac}`} x1={size * frac} y1={15} x2={size * frac} y2={size - 15} />
        ))}
      </g>

      <g fill="none" stroke="var(--color-accent)" strokeWidth={2}>
        <path
          d="M 50 70 L 50 140 L 150 140 L 150 70 L 100 70 L 90 55 L 50 55 L 50 70"
          opacity={0.7}
        />
        <path d="M 50 55 L 90 55 L 100 70" opacity={0.4} />
      </g>

      <g className="animate-pulse">
        <text
          x={100}
          y={115}
          textAnchor="middle"
          fontSize={36}
          fontFamily="monospace"
          fontWeight="bold"
          fill="var(--color-accent)"
          opacity={0.8}
        >
          ?
        </text>
      </g>

      <g fill="var(--color-muted-foreground)" opacity={0.4}>
        <circle cx={40} cy={100} r={4} />
        <circle cx={160} cy={100} r={4} />
        <circle cx={100} cy={160} r={4} />
      </g>

      <g stroke="var(--color-dim)" strokeWidth={1} strokeDasharray="4 3" opacity={0.3}>
        <line x1={44} y1={100} x2={50} y2={100} />
        <line x1={150} y1={100} x2={156} y2={100} />
        <line x1={100} y1={140} x2={100} y2={156} />
      </g>

      <line
        x1={50}
        y1={0}
        x2={50}
        y2={size}
        stroke="var(--color-accent)"
        strokeWidth={1}
        opacity={0.15}
      >
        <animate attributeName="x1" values="50;150;50" dur="3s" repeatCount="indefinite" />
        <animate attributeName="x2" values="50;150;50" dur="3s" repeatCount="indefinite" />
      </line>

      <text
        x={100}
        y={180}
        textAnchor="middle"
        fontSize={9}
        fontFamily="monospace"
        fill="var(--color-dim)"
        letterSpacing="0.15em"
      >
        AWAITING SELECTION
      </text>
    </svg>
  )
}
