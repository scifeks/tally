import type {
  Finding,
  HttpMethod,
  Project,
  Scan,
  Severity,
  Status,
  Segment,
  UrlEntry,
  UrlProtocol,
} from './types'

export const projects: Project[] = [
  { id: '1', name: 'acme-platform', code: 'ACM' },
  { id: '2', name: 'atlas-api', code: 'ATL' },
  { id: '3', name: 'northwind-web', code: 'NWD' },
]

const sastTitles = [
  'SQL injection via unparameterized query',
  'Command injection in subprocess call',
  'Path traversal in file read',
  'Hardcoded cryptographic key',
  'Insecure deserialization (pickle)',
  'XXE in XML parser',
  'Use of weak hash algorithm (MD5)',
  'SSRF via user-controlled URL',
  'Missing authorization check on endpoint',
  'Race condition in file handler',
]

const webTitles = [
  'Reflected XSS in search param',
  'Missing Content-Security-Policy header',
  'Cookie without Secure flag',
  'Open redirect on /logout',
  'Clickjacking: missing X-Frame-Options',
  'Directory listing enabled',
  'Stored XSS in profile bio',
  'CSRF on state-changing POST',
  'Verbose error exposes stack trace',
  'TLS 1.0 supported',
]

const secretsTitles = [
  'AWS access key in repo history',
  'Stripe live key in .env.example',
  'Private SSH key committed',
  'GitHub personal access token',
  'Slack webhook URL leaked',
  'JWT signing secret in source',
  'Database password in config.yaml',
  'Google API key in frontend bundle',
]

const scaTitles = [
  'lodash < 4.17.21: prototype pollution',
  'axios < 1.6.0: SSRF via follow-redirects',
  'log4j 2.14: RCE (Log4Shell)',
  'jackson-databind: deserialization RCE',
  'jinja2 < 3.1.3: sandbox escape',
  'openssl 1.1.1: buffer overread',
  'urllib3 < 2.2.2: cert validation bypass',
  'pillow < 10.2.0: arbitrary file read',
]

const tools: Record<Segment, string[]> = {
  sast: ['semgrep', 'codeql', 'bandit'],
  web: ['zap', 'nuclei', 'burp'],
  secrets: ['gitleaks', 'trufflehog'],
  sca: ['osv-scanner', 'trivy', 'grype'],
}

const severities: Severity[] = ['critical', 'high', 'medium', 'low', 'informational']
const statusPool: Status[] = ['active', 'active', 'active', 'fixed', 'wont_fix', 'false_positive']

function seeded(seed: number) {
  let s = seed
  return () => {
    s = (s * 9301 + 49297) % 233280
    return s / 233280
  }
}
const rand = seeded(42)
const pick = <T>(a: T[]) => a[Math.floor(rand() * a.length)]

const titleMap: Record<Segment, string[]> = {
  sast: sastTitles,
  web: webTitles,
  secrets: secretsTitles,
  sca: scaTitles,
}

const files = [
  'src/api/users.py',
  'src/auth/middleware.ts',
  'internal/db/query.go',
  'app/controllers/payment.rb',
  'lib/http/client.java',
  'services/upload/handler.py',
  'frontend/src/pages/profile.tsx',
  'backend/routes/admin.js',
]

const segments: Segment[] = ['sast', 'web', 'secrets', 'sca']

// 7-char git short hash (lowercase hex).
function commitHash(): string {
  const hex = '0123456789abcdef'
  let s = ''
  for (let i = 0; i < 7; i++) s += hex[Math.floor(rand() * 16)]
  return s
}

// Findings distribution:
//   ACM (p-01) — 220 findings, fully scanned
//   ATL (p-02) — 35 findings, partial scans
//   NWD (p-03) — 0 findings, no scans yet (exercises empty states)
function buildFindings(): Finding[] {
  const out: Finding[] = []
  const counts: Record<string, number> = { '1': 220, '2': 35, '3': 0 }
  let idCounter = 1000
  const triageActors: Array<'claude-code' | 'analyst_web'> = ['claude-code', 'analyst_web']
  for (const project of projects) {
    const n = counts[project.id]
    for (let i = 0; i < n; i++) {
      const segment = pick(segments)
      const severity = pick(severities)
      const status = pick(statusPool)
      const tool = pick(tools[segment])
      const title = pick(titleMap[segment])
      const discovered = new Date(Date.now() - Math.floor(rand() * 1000 * 60 * 60 * 24 * 30))
      // Web findings don't typically have a commit — they're runtime targets.
      const hasCommit = segment !== 'web'
      const isTriaged = rand() < 0.3
      out.push({
        id: `F-${idCounter++}`,
        segment,
        severity,
        status,
        title,
        tool,
        target: segment === 'web' ? `https://${project.name}.example.com` : project.name,
        file: segment === 'sast' || segment === 'secrets' ? pick(files) : undefined,
        line:
          segment === 'sast' || segment === 'secrets' ? Math.floor(rand() * 500) + 1 : undefined,
        cwe: segment === 'sast' ? `CWE-${Math.floor(rand() * 900) + 20}` : undefined,
        commitHash: hasCommit ? commitHash() : undefined,
        projectId: project.id,
        discoveredAt: discovered.toISOString(),
        notes: undefined,
        triagedAt: isTriaged
          ? new Date(discovered.getTime() + Math.floor(rand() * 1000 * 60 * 60 * 24)).toISOString()
          : undefined,
        triagedBy: isTriaged ? pick(triageActors) : undefined,
      })
    }
  }
  return out
}

export const findings: Finding[] = buildFindings()

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

// Per-project repository/target counts for the dashboard quick-start panel.
// urlLists is the count of URL entries in the project's URL list.
export const projectMeta: Record<
  string,
  { repositories: number; urlLists: number; enabledTools: number }
> = {
  '1': { repositories: 14, urlLists: 180, enabledTools: 9 },
  '2': { repositories: 4, urlLists: 42, enabledTools: 5 },
  '3': { repositories: 0, urlLists: 0, enabledTools: 0 },
}

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
    const host = hostByProject[project.id] ?? `api.${project.name}.example.com`
    const count = countByProject[project.id] ?? 0
    for (let i = 0; i < count; i++) {
      const path = pick(pathPool)
      let protocol: UrlProtocol = 'https'
      if (path.startsWith('/ws/')) protocol = rand() < 0.5 ? 'wss' : 'ws'
      const port = portFor(protocol)
      out.push({
        id: `U-${idCounter++}`,
        projectId: project.id,
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
