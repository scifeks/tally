import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useUI } from '@/lib/store'
import {
  useProjects,
  useProjectMeta,
  useFindings,
  useFindingsCounts,
  useScanHistory,
  useRunningScansCount,
} from '@/lib/api'
import { Panel, SeverityChip } from '@/components/tty'
import { cn, formatRelative } from '@/lib/utils'
import { Play, GitBranch, Wrench, Link2, ScrollText, ArrowRight, FolderOpen } from 'lucide-react'
import type { ReactNode } from 'react'

export default function Dashboard() {
  const activeProjectId = useUI(s => s.activeProjectId)

  const projectIdParam = activeProjectId !== null ? String(activeProjectId) : ''

  // GET /api/v1/projects (real)
  const { data: projects = [] } = useProjects()
  // GET /api/v1/projects/:id/meta (real)
  const { data: meta } = useProjectMeta(projectIdParam)
  // GET /api/v1/projects/:id/findings/counts (real)
  const { data: counts } = useFindingsCounts(projectIdParam)
  // SSE /api/v1/projects/:id/scans/events (real, snapshot+delta-driven)
  const runningScansCount = useRunningScansCount(activeProjectId)
  // GET /api/v1/projects/:id/findings — TODO [BACKEND]: still mock; Phase 11.5
  const { data: findings = [] } = useFindings({ projectId: projectIdParam })
  // GET /api/v1/projects/:id/scans — TODO [BACKEND]: still mock; Phase 11.7
  const { data: scans = [] } = useScanHistory(projectIdParam)

  // useMemo must run before the early return below to keep hook order stable
  // across renders where activeProjectId toggles between null and a value.
  const projectFindings = useMemo(
    () => findings.filter(f => f.projectId === projectIdParam),
    [findings, projectIdParam]
  )
  const projectScans = useMemo(
    () => scans.filter(s => s.projectId === projectIdParam),
    [scans, projectIdParam]
  )

  // Initial app load: no project picked yet — show selection state.
  if (!activeProjectId) {
    return <NoProjectSelectedState projects={projects} />
  }
  const project = projects.find(p => p.id === activeProjectId)
  if (!project) {
    return <NoProjectSelectedState projects={projects} />
  }
  const reposCount = counts?.reposCount ?? 0
  const urlsCount = counts?.urlsCount ?? 0
  const enabledToolsCount = meta?.enabledTools?.length ?? 0
  const totalFindings = counts?.total ?? 0
  const openCrit = counts?.bySeverityStatus.critical?.active ?? 0
  const openHigh = counts?.bySeverityStatus.high?.active ?? 0

  const hasScans = projectScans.length > 0
  const hasFindings = projectFindings.length > 0

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 space-y-6 max-w-[1400px] mx-auto">
        {/* Project summary header */}
        <section className="border border-border bg-background">
          <div className="flex items-stretch">
            <div className="flex flex-col justify-center px-6 py-4 border-r border-border min-w-[200px]">
              <div className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
                active project
              </div>
              <div className="flex items-baseline gap-3 mt-1">
                <span className="text-2xl font-bold text-primary tty-glow tabular-nums">
                  {project.code}
                </span>
                <span className="text-sm text-foreground">{project.name}</span>
              </div>
            </div>
            <div className="flex-1 grid grid-cols-4 divide-x divide-border">
              <SummaryStat label="repositories" value={reposCount} href="/config/repositories" />
              <SummaryStat label="urls" value={urlsCount} href="/urls" />
              <SummaryStat label="tools enabled" value={enabledToolsCount} href="/config/tools" />
              <SummaryStat
                label="scans"
                value={projectScans.length}
                href="/scans"
                accent={runningScansCount > 0 ? 'accent' : undefined}
                hint={runningScansCount > 0 ? `${runningScansCount} running` : undefined}
              />
            </div>
          </div>
        </section>

        {!hasScans ? (
          <EmptyProjectState project={project} hasMeta={reposCount > 0} />
        ) : (
          <>
            {/* Quick actions */}
            <section>
              <SectionTitle>quick actions</SectionTitle>
              <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3">
                <ActionTile
                  icon={<Play className="h-4 w-4" />}
                  label="new scan"
                  desc="start a scan across selected tools"
                  to="/scans"
                  primary
                />
                <ActionTile
                  icon={<GitBranch className="h-4 w-4" />}
                  label="repositories"
                  desc="add or edit source repos"
                  to="/config"
                />
                <ActionTile
                  icon={<Link2 className="h-4 w-4" />}
                  label="url lists"
                  desc="targets for web scanning"
                  to="/urls"
                />
                <ActionTile
                  icon={<Wrench className="h-4 w-4" />}
                  label="tool config"
                  desc="enable/disable scanners"
                  to="/config"
                />
                <ActionTile
                  icon={<ScrollText className="h-4 w-4" />}
                  label="findings"
                  desc="review findings"
                  to="/findings"
                />
              </div>
            </section>

            {/* Two-column: recent scans + quick stats */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <Panel title="recent scans" className="lg:col-span-2" bodyClassName="overflow-auto">
                <div className="text-xs">
                  <div className="grid grid-cols-[90px_70px_90px_1fr_80px_110px] text-[10px] uppercase tracking-[0.18em] text-muted-foreground px-3 h-7 items-center border-b border-border">
                    <div>id</div>
                    <div>domain</div>
                    <div>tool</div>
                    <div>status</div>
                    <div className="text-right">findings</div>
                    <div className="text-right">when</div>
                  </div>
                  {projectScans.slice(0, 8).map(s => (
                    <div
                      key={s.id}
                      className="grid grid-cols-[90px_70px_90px_1fr_80px_110px] items-center px-3 h-8 border-b border-border last:border-b-0 hover:bg-muted/50"
                    >
                      <div className="text-dim tabular-nums">{s.id}</div>
                      <div className="uppercase text-muted-foreground text-[11px]">{s.segment}</div>
                      <div className="text-foreground">{s.tool}</div>
                      <div>
                        <ScanStatus status={s.status} />
                      </div>
                      <div className="text-right tabular-nums text-muted-foreground">
                        {s.findingsCount ?? '—'}
                      </div>
                      <div className="text-right text-muted-foreground tabular-nums">
                        {formatRelative(s.startedAt)}
                      </div>
                    </div>
                  ))}
                </div>
                <div className="flex justify-end border-t border-border p-2">
                  <Link
                    to="/scans"
                    className="text-[11px] uppercase tracking-wider text-muted-foreground hover:text-accent flex items-center gap-1"
                  >
                    all scans <ArrowRight className="h-3 w-3" />
                  </Link>
                </div>
              </Panel>

              <Panel title="at a glance">
                <div className="divide-y divide-border text-xs">
                  <GlanceRow
                    label="last scan"
                    value={counts?.lastScanAt ? formatRelative(counts.lastScanAt) : 'never'}
                  />
                  <GlanceRow label="total findings" value={totalFindings.toString()} />
                  <GlanceRow
                    label="open critical"
                    value={openCrit.toString()}
                    highlight={openCrit > 0 ? 'crit' : undefined}
                  />
                  <GlanceRow
                    label="open high"
                    value={openHigh.toString()}
                    highlight={openHigh > 0 ? 'high' : undefined}
                  />
                  <GlanceRow
                    label="scans running"
                    value={runningScansCount.toString()}
                    highlight={runningScansCount > 0 ? 'accent' : undefined}
                  />
                </div>
                {hasFindings && (
                  <div className="border-t border-border p-2 flex justify-end">
                    <Link
                      to="/findings"
                      className="text-[11px] uppercase tracking-wider text-muted-foreground hover:text-accent flex items-center gap-1"
                    >
                      view findings <ArrowRight className="h-3 w-3" />
                    </Link>
                  </div>
                )}
              </Panel>
            </div>

            {/* Most recent critical/high findings */}
            {hasFindings && (
              <Panel title="recent high-severity findings">
                <div className="text-xs">
                  <div className="grid grid-cols-[80px_70px_1fr_110px_90px] text-[10px] uppercase tracking-[0.18em] text-muted-foreground px-3 h-7 items-center border-b border-border">
                    <div>id</div>
                    <div>sev</div>
                    <div>title</div>
                    <div>tool</div>
                    <div className="text-right">when</div>
                  </div>
                  {projectFindings
                    .filter(
                      f =>
                        f.status === 'active' &&
                        (f.severity === 'critical' || f.severity === 'high')
                    )
                    .slice(0, 8)
                    .map(f => (
                      <Link
                        to="/findings"
                        key={f.id}
                        className="grid grid-cols-[80px_70px_1fr_110px_90px] items-center px-3 h-8 border-b border-border last:border-b-0 hover:bg-muted/50"
                      >
                        <div className="text-dim tabular-nums">{f.id}</div>
                        <div>
                          <SeverityChip severity={f.severity} />
                        </div>
                        <div className="text-foreground truncate pr-3">{f.title}</div>
                        <div className="text-muted-foreground">{f.tool}</div>
                        <div className="text-right text-muted-foreground tabular-nums">
                          {formatRelative(f.discoveredAt)}
                        </div>
                      </Link>
                    ))}
                </div>
              </Panel>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-center gap-2 mb-3 text-[11px] uppercase tracking-[0.25em] text-muted-foreground">
      <span className="text-dim">[</span>
      <span>{children}</span>
      <span className="text-dim">]</span>
      <span className="flex-1 border-t border-border" />
    </div>
  )
}

function SummaryStat({
  label,
  value,
  href,
  hint,
  accent,
}: {
  label: string
  value: number
  href: string
  hint?: string
  accent?: 'accent'
}) {
  return (
    <Link
      to={href}
      className="flex flex-col justify-center px-5 py-4 hover:bg-muted/50 transition-colors group"
    >
      <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">{label}</div>
      <div className="flex items-baseline gap-2 mt-1">
        <span
          className={cn(
            'text-2xl font-bold tabular-nums',
            accent === 'accent' ? 'text-accent' : 'text-foreground'
          )}
        >
          {value}
        </span>
        {hint && <span className="text-[11px] text-accent">{hint}</span>}
      </div>
      <div className="flex items-center gap-1 mt-0.5 text-[10px] uppercase tracking-wider text-dim group-hover:text-accent">
        manage <ArrowRight className="h-3 w-3" />
      </div>
    </Link>
  )
}

function ActionTile({
  icon,
  label,
  desc,
  to,
  primary,
}: {
  icon: ReactNode
  label: string
  desc: string
  to: string
  primary?: boolean
}) {
  return (
    <Link
      to={to}
      className={cn(
        'group flex flex-col gap-2 border p-4 transition-colors bg-background',
        primary
          ? 'border-accent hover:bg-muted'
          : 'border-border hover:border-border-strong hover:bg-muted/50'
      )}
    >
      <div className="flex items-center gap-2">
        <span className={primary ? 'text-accent' : 'text-muted-foreground'}>{icon}</span>
        <span
          className={cn(
            'text-xs uppercase tracking-[0.18em] font-bold',
            primary ? 'text-accent tty-glow' : 'text-foreground'
          )}
        >
          &gt; {label}
        </span>
      </div>
      <div className="text-[11px] text-muted-foreground leading-relaxed">{desc}</div>
    </Link>
  )
}

function GlanceRow({
  label,
  value,
  highlight,
}: {
  label: string
  value: string
  highlight?: 'crit' | 'high' | 'accent'
}) {
  const cls =
    highlight === 'crit'
      ? 'text-crit'
      : highlight === 'high'
        ? 'text-high'
        : highlight === 'accent'
          ? 'text-accent'
          : 'text-foreground'
  return (
    <div className="flex items-center justify-between px-3 h-9">
      <span className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</span>
      <span className={cn('tabular-nums font-bold', cls)}>{value}</span>
    </div>
  )
}

function ScanStatus({ status }: { status: string }) {
  const map: Record<string, string> = {
    running: 'text-accent',
    done: 'text-low',
    failed: 'text-crit',
    queued: 'text-muted-foreground',
  }
  return (
    <span
      className={cn('text-[11px] uppercase tracking-wider', map[status] ?? 'text-muted-foreground')}
    >
      {status === 'running' ? <span className="tty-cursor">running</span> : status}
    </span>
  )
}

function EmptyProjectState({
  project,
  hasMeta,
}: {
  project: { code: string; name: string }
  hasMeta: boolean
}) {
  const steps = [
    {
      done: hasMeta,
      label: 'add a repository or URL list',
      desc: 'define what to scan',
      to: '/config/repositories',
      icon: <GitBranch className="h-4 w-4" />,
    },
    {
      done: false,
      label: 'enable tools',
      desc: 'pick your SAST / WEB / SECRETS / SCA scanners',
      to: '/config/tools',
      icon: <Wrench className="h-4 w-4" />,
    },
    {
      done: false,
      label: 'start your first scan',
      desc: "ingestion + enrichment can take a while — that's normal",
      to: '/scans',
      icon: <Play className="h-4 w-4" />,
    },
  ]

  return (
    <Panel title={`welcome :: ${project.code}`}>
      <div className="p-6 space-y-6">
        <div className="text-sm text-foreground max-w-[640px] leading-relaxed">
          <span className="text-dim">$</span> no scans have been run against{' '}
          <span className="text-primary tty-glow">{project.name}</span>. once a scan completes, the
          dashboard will populate with findings, severity breakdowns, and triage state.
        </div>

        <div>
          <SectionTitle>getting started</SectionTitle>
          <ol className="space-y-2">
            {steps.map((s, i) => (
              <li key={i}>
                <Link
                  to={s.to}
                  className={cn(
                    'flex items-center gap-4 border px-4 py-3 transition-colors',
                    s.done
                      ? 'border-border text-muted-foreground'
                      : 'border-border hover:border-accent hover:bg-muted/50'
                  )}
                >
                  <span
                    className={cn('w-8 text-center font-bold', s.done ? 'text-low' : 'text-accent')}
                  >
                    {s.done ? '[x]' : `[${i + 1}]`}
                  </span>
                  <span className={s.done ? 'text-muted-foreground' : 'text-accent'}>{s.icon}</span>
                  <div className="flex-1">
                    <div
                      className={cn(
                        'text-xs uppercase tracking-[0.18em] font-bold',
                        s.done ? 'text-muted-foreground line-through' : 'text-foreground'
                      )}
                    >
                      {s.label}
                    </div>
                    <div className="text-[11px] text-muted-foreground mt-0.5">{s.desc}</div>
                  </div>
                  <ArrowRight className="h-4 w-4 text-muted-foreground" />
                </Link>
              </li>
            ))}
          </ol>
        </div>

        <div className="border border-border bg-muted/30 p-3 text-[11px] text-muted-foreground leading-relaxed">
          <span className="text-dim">{'// '}</span>
          scans can take significant time on first run — repositories are cloned, targets are
          crawled, and results are enriched before findings appear. you can leave this page; results
          stream in live.
        </div>
      </div>
    </Panel>
  )
}

// ─── No Project Selected State ────────────────────────────────────────────────
// Shown on initial app load before a project has been selected.

function NoProjectSelectedState({
  projects,
}: {
  projects: Array<{ id: number; code: string; name: string }>
}) {
  const setActiveProject = useUI(s => s.setActiveProject)

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
            <p className="text-sm text-muted-foreground">
              No projects found. Create a project using the CLI to get started.
            </p>
            <code className="block mt-3 text-xs text-accent font-mono">$ tally project add</code>
          </div>
        )}

        <div className="mt-6 text-center">
          <p className="text-[11px] text-dim">
            <span className="text-dim">{'// '}</span>
            use the project dropdown in the header to switch projects at any time
          </p>
        </div>
      </div>
    </div>
  )
}

// ─── Project Select Graphic ───────────────────────────────────────────────────
// Animated SVG showing a folder/project icon with connection nodes.

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
