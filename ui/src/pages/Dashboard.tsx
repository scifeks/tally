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
import { cn, findingTitle, formatRelative } from '@/lib/utils'
import { Play, GitBranch, Wrench, Link2, ScrollText, ArrowRight } from 'lucide-react'
import { NoProjectSelectedState } from '@/components/NoProjectSelectedState'
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
  // GET /api/v1/projects/:id/findings (real, server-filtered to top crit/high active)
  const { data: recentFindings } = useFindings({
    projectId: projectIdParam,
    filters: {
      severity: ['critical', 'high'],
      status: ['active'],
      sort: 'severity',
      order: 'desc',
      limit: 10,
    },
  })
  const { data: scans = [] } = useScanHistory(activeProjectId ?? 0)

  // useMemo must run before the early return below to keep hook order stable
  // across renders where activeProjectId toggles between null and a value.
  const projectScans = useMemo(
    () => scans.filter(s => s.projectId === activeProjectId),
    [scans, activeProjectId]
  )

  // Initial app load: no project picked yet - show selection state.
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
  const hasAnyFindings = totalFindings > 0
  const hasRecentHighSeverity = recentFindings.length > 0

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
              <SummaryStat label="repositories" value={reposCount} href="/config" />
              <SummaryStat label="urls" value={urlsCount} href="/urls" />
              <SummaryStat label="tools enabled" value={enabledToolsCount} href="/config" />
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
                  <div className="grid grid-cols-[90px_110px_1fr_1fr_80px_110px] text-[10px] uppercase tracking-[0.18em] text-muted-foreground px-3 h-7 items-center border-b border-border">
                    <div>id</div>
                    <div>domains</div>
                    <div>tools</div>
                    <div>status</div>
                    <div className="text-right">findings</div>
                    <div className="text-right">when</div>
                  </div>
                  {projectScans.slice(0, 8).map(s => (
                    <div
                      key={s.id}
                      className="grid grid-cols-[90px_110px_1fr_1fr_80px_110px] items-center px-3 h-8 border-b border-border last:border-b-0 hover:bg-muted/50"
                    >
                      <div className="text-dim tabular-nums">{s.id}</div>
                      <div className="uppercase text-muted-foreground text-[11px] truncate">
                        {s.domains.length > 0 ? s.domains.join(', ') : '-'}
                      </div>
                      <div className="text-foreground truncate">
                        {s.toolIds.length > 0 ? s.toolIds.join(', ') : '-'}
                      </div>
                      <div>
                        <ScanStatus status={s.status} />
                      </div>
                      <div className="text-right tabular-nums text-muted-foreground">
                        {s.findingsCount ?? '-'}
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
                  <GlanceRow label="last scan" value={formatRelative(counts?.lastScanAt)} />
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
                {hasAnyFindings && (
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
            {hasRecentHighSeverity && (
              <Panel title="recent high-severity findings">
                <div className="text-xs">
                  <div className="grid grid-cols-[80px_70px_1fr_110px_90px] text-[10px] uppercase tracking-[0.18em] text-muted-foreground px-3 h-7 items-center border-b border-border">
                    <div>id</div>
                    <div>sev</div>
                    <div>title</div>
                    <div>tool</div>
                    <div className="text-right">when</div>
                  </div>
                  {recentFindings.slice(0, 8).map(f => (
                    <Link
                      to="/findings"
                      key={f.id}
                      className="grid grid-cols-[80px_70px_1fr_110px_90px] items-center px-3 h-8 border-b border-border last:border-b-0 hover:bg-muted/50"
                    >
                      <div className="text-dim tabular-nums">{f.id}</div>
                      <div>
                        <SeverityChip severity={f.severity} />
                      </div>
                      <div className="text-foreground truncate pr-3">{findingTitle(f)}</div>
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
      to: '/config',
      icon: <GitBranch className="h-4 w-4" />,
    },
    {
      done: false,
      label: 'enable tools',
      desc: 'pick your SAST / WEB / SECRETS / SCA scanners',
      to: '/config',
      icon: <Wrench className="h-4 w-4" />,
    },
    {
      done: false,
      label: 'start your first scan',
      desc: "ingestion + enrichment can take a while - that's normal",
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
          scans can take significant time on first run - repositories are cloned, targets are
          crawled, and results are enriched before findings appear. you can leave this page; results
          stream in live.
        </div>
      </div>
    </Panel>
  )
}
