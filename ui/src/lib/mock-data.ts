import type { HttpMethod, Project, Scan, Segment, UrlEntry, UrlProtocol } from './types'

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

// ─── URL Lists ──────────────────────────────────────────────────────────────
// ACM has 180 entries, ATL has 42, NWD has 0 (exercises the empty state).

const methods: HttpMethod[] = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']
const methodWeights: Record<HttpMethod, number> = {
  GET: 6,
  POST: 3,
  PUT: 1,
  PATCH: 1,
  DELETE: 1,
  HEAD: 0.5,
  OPTIONS: 0.5,
}
function pickMethod(): HttpMethod {
  const total = methods.reduce((s, m) => s + methodWeights[m], 0)
  let r = rand() * total
  for (const m of methods) {
    r -= methodWeights[m]
    if (r <= 0) return m
  }
  return 'GET'
}

// Intentionally scattered (not pre-sorted) so the page's sort feature has
// something to actually do.
const pathPool = [
  '/',
  '/login',
  '/logout',
  '/health',
  '/metrics',
  '/robots.txt',
  '/api/v1/users',
  '/api/v1/users/{id}',
  '/api/v1/users/{id}/avatar',
  '/api/v1/users/{id}/sessions',
  '/api/v1/users/search',
  '/api/v1/orders',
  '/api/v1/orders/{id}',
  '/api/v1/orders/{id}/refund',
  '/api/v1/orders/{id}/items',
  '/api/v1/orders/export',
  '/api/v1/payments',
  '/api/v1/payments/{id}',
  '/api/v1/payments/{id}/capture',
  '/api/v1/products',
  '/api/v1/products/{id}',
  '/api/v1/products/{id}/reviews',
  '/api/v2/users',
  '/api/v2/users/{id}',
  '/api/v2/orders',
  '/api/v2/orders/{id}',
  '/admin',
  '/admin/users',
  '/admin/users/{id}',
  '/admin/settings',
  '/admin/audit',
  '/admin/reports',
  '/admin/reports/{id}',
  '/auth/token',
  '/auth/refresh',
  '/auth/revoke',
  '/auth/.well-known/jwks',
  '/webhooks/stripe',
  '/webhooks/github',
  '/webhooks/slack',
  '/assets/app.js',
  '/assets/app.css',
  '/assets/logo.svg',
  '/docs',
  '/docs/openapi.json',
  '/docs/changelog',
  '/graphql',
  '/graphql/subscriptions',
  '/ws/notifications',
  '/ws/chat',
]

const hostByProject: Record<string, string> = {
  '1': 'api.acme-platform.com',
  '2': 'api.atlas.dev',
}

const countByProject: Record<string, number> = {
  '1': 180,
  '2': 42,
  '3': 0,
}

function portFor(proto: UrlProtocol): number {
  if (proto === 'ws') return 80
  if (proto === 'wss') return 443
  if (proto === 'http') return 80
  return 443
}

function buildUrls(): UrlEntry[] {
  const out: UrlEntry[] = []
  let idCounter = 5000
  for (const project of projects) {
    const host = hostByProject[String(project.id)] ?? `api.${project.name}.example.com`
    const count = countByProject[String(project.id)] ?? 0
    for (let i = 0; i < count; i++) {
      const path = pick(pathPool)
      let protocol: UrlProtocol = 'https'
      if (path.startsWith('/ws/')) protocol = rand() < 0.5 ? 'wss' : 'ws'
      const port = portFor(protocol)
      out.push({
        id: `U-${idCounter++}`,
        projectId: String(project.id),
        method: pickMethod(),
        protocol,
        host,
        port,
        path,
      })
    }
  }
  return out
}

export const urls: UrlEntry[] = buildUrls()
