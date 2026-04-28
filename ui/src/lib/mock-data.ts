import type { Project, Scan, Segment } from './types'

export const projects: Project[] = [
  { id: 1, name: 'acme-platform', code: 'ACM' },
  { id: 2, name: 'atlas-api', code: 'ATL' },
  { id: 3, name: 'northwind-web', code: 'NWD' },
]

const tools: Record<Segment, string[]> = {
  sast: ['semgrep', 'codeql', 'bandit'],
  web: ['zap', 'nuclei', 'burp'],
  secrets: ['gitleaks', 'trufflehog'],
  sca: ['osv-scanner', 'trivy', 'grype'],
}

function seeded(seed: number) {
  let s = seed
  return () => {
    s = (s * 9301 + 49297) % 233280
    return s / 233280
  }
}
const rand = seeded(42)
const pick = <T>(a: T[]) => a[Math.floor(rand() * a.length)]

const segments: Segment[] = ['sast', 'web', 'secrets', 'sca']

// Scans: ACM has many scans (2 running with segment info), ATL has a few, NWD has none.
function buildScans(): Scan[] {
  const out: Scan[] = []
  const dist: { projectId: string; count: number }[] = [
    { projectId: '1', count: 9 },
    { projectId: '2', count: 3 },
    { projectId: '3', count: 0 },
  ]
  const runningSegments = [
    {
      currentSegment: 'cloning repositories',
      segmentLabel: '3 / 14 repos',
      progress: 22,
    },
    {
      currentSegment: 'enriching findings with CVE data',
      segmentLabel: '842 / 2,104 findings',
      progress: 40,
    },
  ]
  let idCounter = 2000
  let i = 0
  let runningIdx = 0
  for (const { projectId, count } of dist) {
    for (let j = 0; j < count; j++) {
      const segment = pick(segments)
      const isRunning = projectId === '1' && j < 2
      const startedAt = new Date(Date.now() - (i + 1) * 1000 * 60 * 37).toISOString()
      const seg = isRunning ? runningSegments[runningIdx++] : undefined
      out.push({
        id: `S-${idCounter++}`,
        projectId,
        segment,
        tool: pick(tools[segment]),
        status: isRunning ? 'running' : j === 2 ? 'failed' : 'done',
        startedAt,
        finishedAt: isRunning
          ? undefined
          : new Date(new Date(startedAt).getTime() + 8 * 60_000).toISOString(),
        findingsCount: isRunning ? undefined : Math.floor(rand() * 40),
        currentSegment: seg?.currentSegment,
        segmentLabel: seg?.segmentLabel,
        progress: seg?.progress,
      })
      i++
    }
  }
  return out
}

export const scans: Scan[] = buildScans()

// URL list entries previously generated here have been relocated to static
// JSON fixtures under `tests/fixtures/url-list-*.json` and are served via the
// MSW handler. See the Phase 11.6 session log for context.
