import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ConfigMode, RepoLocationMode, RepoType, ServiceConfig } from '@/lib/types'
import { TagInput } from './shared'

function PerServiceKatana({
  service,
  onChange,
  isDisabled,
  defaults,
}: {
  service: ServiceConfig
  onChange: <K extends keyof ServiceConfig>(field: K, value: ServiceConfig[K]) => void
  isDisabled: boolean
  defaults?: { headless: boolean; crawlDepth: number }
}) {
  const headless = service.katanaHeadless ?? defaults?.headless ?? false
  const depth = service.katanaCrawlDepth ?? defaults?.crawlDepth ?? 5
  const maxDepth = headless ? 5 : 20

  return (
    <div className="border-t border-border pt-4">
      <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
        Crawler Settings
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="flex items-center gap-2 cursor-pointer">
            <button
              onClick={() => {
                const newHeadless = !headless
                onChange('katanaHeadless', newHeadless)
                if (newHeadless && depth > 5) {
                  onChange('katanaCrawlDepth', 5)
                } else if (service.katanaCrawlDepth === null) {
                  onChange('katanaCrawlDepth', depth)
                }
              }}
              disabled={isDisabled}
              className={cn(
                'w-4 h-4 border flex items-center justify-center transition-colors',
                headless
                  ? 'border-accent bg-accent text-background'
                  : 'border-border hover:border-muted-foreground'
              )}
            >
              {headless && <Check className="h-3 w-3" />}
            </button>
            <span className="text-xs text-foreground">Katana headless mode</span>
          </div>
          <div className="text-[9px] text-dim mt-1 ml-6">
            Uses Chrome to render JavaScript routes. Required for SPAs.
          </div>
        </div>
        <div>
          <label className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
            Crawl Depth {headless && <span className="text-high">(max 5 in headless)</span>}
          </label>
          <input
            type="number"
            min={1}
            max={maxDepth}
            value={depth}
            onChange={e => {
              const val = parseInt(e.target.value) || 5
              onChange('katanaCrawlDepth', Math.min(val, maxDepth))
            }}
            disabled={isDisabled}
            className="w-24 h-8 px-2 bg-background border border-border text-xs text-foreground tabular-nums focus:border-accent focus:outline-none disabled:opacity-50"
          />
        </div>
      </div>
    </div>
  )
}

export function ServiceDetailForm({
  service,
  onChange,
  mode,
  isDisabled,
  katanaDefaults,
}: {
  service: ServiceConfig
  onChange: <K extends keyof ServiceConfig>(field: K, value: ServiceConfig[K]) => void
  mode: ConfigMode
  isDisabled: boolean
  katanaDefaults?: { headless: boolean; crawlDepth: number }
}) {
  const isLibrary = service.type.includes('library')
  const hasPython = service.languages.some(l => l.toLowerCase() === 'python')

  const toggleType = (type: RepoType) => {
    const current = service.type
    if (type === 'library') {
      onChange('type', current.includes('library') ? [] : ['library'])
    } else {
      if (current.includes('library')) return
      if (current.includes(type)) {
        onChange(
          'type',
          current.filter(t => t !== type)
        )
      } else {
        onChange('type', [...current, type])
      }
    }
  }

  return (
    <div className={cn('space-y-4', isDisabled && 'opacity-60')}>
      {mode === 'advanced' && (
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label
              htmlFor="svc-name"
              className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
            >
              Service Name <span className="text-crit">*</span>
            </label>
            <input
              id="svc-name"
              type="text"
              value={service.name}
              onChange={e => onChange('name', e.target.value)}
              disabled={isDisabled}
              placeholder="backend, frontend, api..."
              className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none disabled:opacity-50"
            />
          </div>
          <div>
            <label
              htmlFor="svc-relative-path"
              className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
            >
              Relative Path
            </label>
            <input
              id="svc-relative-path"
              type="text"
              value={service.relativePath}
              onChange={e => onChange('relativePath', e.target.value)}
              disabled={isDisabled}
              placeholder="packages/api, services/auth..."
              className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground font-mono focus:border-accent focus:outline-none disabled:opacity-50"
            />
            <div className="text-[9px] text-dim mt-1">Sub-path within the repository root</div>
          </div>
        </div>
      )}

      {/* Type */}
      <div>
        <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
          Type <span className="text-crit">*</span>
        </div>
        <div className="flex gap-2">
          {(['library', 'api', 'ui'] as RepoType[]).map(type => {
            const selected = service.type.includes(type)
            const disabled = isDisabled || (type !== 'library' && isLibrary)
            return (
              <button
                key={type}
                onClick={() => toggleType(type)}
                disabled={disabled}
                className={cn(
                  'px-3 h-8 text-[10px] uppercase tracking-wider border transition-colors',
                  selected
                    ? 'border-accent bg-accent/20 text-accent'
                    : disabled
                      ? 'border-border/50 text-dim cursor-not-allowed'
                      : 'border-border text-muted-foreground hover:border-muted-foreground'
                )}
              >
                {type}
              </button>
            )
          })}
        </div>
        <div className="text-[9px] text-dim mt-1">library cannot be combined with api or ui</div>
      </div>

      {/* Location mode */}
      <div className="border-t border-border pt-4">
        <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
          Location Mode
        </div>
        <div className="flex gap-2 mb-3">
          {(['local', 'docker'] as RepoLocationMode[]).map(lm => (
            <button
              key={lm}
              onClick={() => onChange('locationMode', lm)}
              disabled={isDisabled}
              className={cn(
                'px-4 h-8 text-[10px] uppercase tracking-wider border transition-colors',
                service.locationMode === lm
                  ? 'border-accent bg-accent/20 text-accent'
                  : 'border-border text-muted-foreground hover:border-muted-foreground'
              )}
            >
              {lm}
            </button>
          ))}
        </div>

        {service.locationMode === 'docker' && (
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label
                htmlFor="svc-container-name"
                className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
              >
                Container Name <span className="text-crit">*</span>
              </label>
              <input
                id="svc-container-name"
                type="text"
                value={service.docker?.containerName ?? ''}
                onChange={e =>
                  onChange('docker', {
                    containerName: e.target.value,
                    mountPoint: service.docker?.mountPoint ?? '',
                  })
                }
                disabled={isDisabled}
                className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none disabled:opacity-50"
              />
            </div>
            <div>
              <label
                htmlFor="svc-mount-point"
                className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
              >
                Mount Point <span className="text-crit">*</span>
              </label>
              <input
                id="svc-mount-point"
                type="text"
                value={service.docker?.mountPoint ?? ''}
                onChange={e =>
                  onChange('docker', {
                    containerName: service.docker?.containerName ?? '',
                    mountPoint: e.target.value,
                  })
                }
                disabled={isDisabled}
                placeholder="/app"
                className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground font-mono focus:border-accent focus:outline-none disabled:opacity-50"
              />
            </div>
          </div>
        )}
      </div>

      {/* Code context */}
      <div className="border-t border-border pt-4 grid grid-cols-3 gap-4">
        <div>
          <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
            Languages <span className="text-crit">*</span>
          </div>
          <TagInput
            value={service.languages}
            onChange={tags => onChange('languages', tags)}
            placeholder="python, javascript..."
            disabled={isDisabled}
          />
        </div>
        <div>
          <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
            Test Directories
          </div>
          <TagInput
            value={service.testDirectories}
            onChange={tags => onChange('testDirectories', tags)}
            placeholder="tests, spec..."
            disabled={isDisabled}
          />
        </div>
        <div>
          <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
            Ignore Directories
          </div>
          <TagInput
            value={service.ignoreDirectories}
            onChange={tags => onChange('ignoreDirectories', tags)}
            placeholder="vendor, node_modules..."
            disabled={isDisabled}
          />
        </div>
      </div>

      {/* API targets + dependencies */}
      <div className="border-t border-border pt-4">
        <div className={`grid gap-4 ${hasPython ? 'grid-cols-2' : 'grid-cols-1'}`}>
          <div>
            <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
              Base URLs
            </div>
            <TagInput
              value={service.baseUrls}
              onChange={tags => onChange('baseUrls', tags)}
              placeholder="https://api.example.com"
              disabled={isDisabled}
            />
            <div className="text-[9px] text-dim mt-1">
              First URL is used as canonical scope for scans
            </div>
          </div>
          {hasPython && (
            <div>
              <label
                htmlFor="svc-deps-file"
                className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
              >
                Python Dependencies File
              </label>
              <input
                id="svc-deps-file"
                type="text"
                value={service.dependenciesFile}
                onChange={e => onChange('dependenciesFile', e.target.value)}
                disabled={isDisabled}
                placeholder="requirements.txt"
                className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground font-mono focus:border-accent focus:outline-none disabled:opacity-50"
              />
              <div className="text-[9px] text-dim mt-1">
                Override for pip-audit (auto-detected when absent)
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Crawl enabled */}
      <div className="border-t border-border pt-4">
        <div className="flex items-center gap-2">
          <button
            onClick={() => onChange('crawlEnabled', !service.crawlEnabled)}
            disabled={isDisabled}
            className={cn(
              'w-4 h-4 border flex items-center justify-center transition-colors',
              service.crawlEnabled
                ? 'border-accent bg-accent text-background'
                : 'border-border hover:border-muted-foreground'
            )}
          >
            {service.crawlEnabled && <Check className="h-3 w-3" />}
          </button>
          <span className="text-xs text-foreground">Enable live crawling for this service</span>
        </div>
      </div>

      {/* Per-service katana settings (advanced mode only) */}
      {mode === 'advanced' && service.crawlEnabled && service.baseUrls.length > 0 && (
        <PerServiceKatana
          service={service}
          onChange={onChange}
          isDisabled={isDisabled}
          defaults={katanaDefaults}
        />
      )}
    </div>
  )
}
