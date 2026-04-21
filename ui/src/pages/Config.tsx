import { useState, useMemo, useEffect } from "react"
import { Settings, Database, Wrench, ChevronDown, Plus, Trash2, Save, RotateCcw, Check, AlertCircle } from "lucide-react"
import { cn } from "@/lib/utils"
import { Panel } from "@/components/tty"
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
import type {
  ProjectInfo,
  RepositoryConfig,
  ToolOverrideConfig,
  ToolCatalogEntry,
  RepoType,
  RepoLocationMode,
  ToolType,
  ToolLocationMode,
} from "@/lib/types"

// ─── Animated Graphic ─────────────────────────────────────────────────────────
// Circuit board / settings panel animation for config page
// Same dimensions (180px) and positioning pattern as Scans/Triage/Reports

function ConfigPanel({ active, size = 180 }: { active?: boolean; size?: number }) {
  // Multiple interconnected gears to represent configuration
  const gearConfigs = [
    { cx: size * 0.35, cy: size * 0.35, r: size * 0.18, teeth: 10, speed: 8 },
    { cx: size * 0.65, cy: size * 0.55, r: size * 0.14, teeth: 8, speed: -6 },
    { cx: size * 0.35, cy: size * 0.7, r: size * 0.10, teeth: 6, speed: 10 },
  ]

  // Build gear path
  const buildGearPath = (cx: number, cy: number, r: number, teeth: number) => {
    const toothH = r * 0.25
    const pts: string[] = []
    for (let i = 0; i < teeth; i++) {
      const a1 = (i / teeth) * Math.PI * 2
      const a2 = ((i + 0.3) / teeth) * Math.PI * 2
      const a3 = ((i + 0.5) / teeth) * Math.PI * 2
      const a4 = ((i + 0.8) / teeth) * Math.PI * 2

      pts.push(`${cx + Math.cos(a1) * r},${cy + Math.sin(a1) * r}`)
      pts.push(`${cx + Math.cos(a2) * (r + toothH)},${cy + Math.sin(a2) * (r + toothH)}`)
      pts.push(`${cx + Math.cos(a3) * (r + toothH)},${cy + Math.sin(a3) * (r + toothH)}`)
      pts.push(`${cx + Math.cos(a4) * r},${cy + Math.sin(a4) * r}`)
    }
    return `M ${pts.join(" L ")} Z`
  }

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className="shrink-0"
      aria-hidden
    >
      {/* Corner brackets - matching other pages */}
      <g stroke="var(--color-accent)" strokeWidth={2} fill="none">
        <path d={`M 15 5 L 5 5 L 5 15`} />
        <path d={`M ${size - 15} 5 L ${size - 5} 5 L ${size - 5} 15`} />
        <path d={`M 15 ${size - 5} L 5 ${size - 5} L 5 ${size - 15}`} />
        <path d={`M ${size - 15} ${size - 5} L ${size - 5} ${size - 5} L ${size - 5} ${size - 15}`} />
      </g>

      {/* Background grid */}
      <g stroke="var(--color-border)" strokeWidth={0.5} opacity={0.3}>
        {[0.25, 0.5, 0.75].map((frac) => (
          <line key={`h-${frac}`} x1={10} y1={size * frac} x2={size - 10} y2={size * frac} />
        ))}
        {[0.25, 0.5, 0.75].map((frac) => (
          <line key={`v-${frac}`} x1={size * frac} y1={10} x2={size * frac} y2={size - 10} />
        ))}
      </g>

      {/* Connecting lines between gears */}
      <g stroke="var(--color-dim)" strokeWidth={1} strokeDasharray="4 2" opacity={0.4}>
        <line x1={gearConfigs[0].cx} y1={gearConfigs[0].cy} x2={gearConfigs[1].cx} y2={gearConfigs[1].cy} />
        <line x1={gearConfigs[0].cx} y1={gearConfigs[0].cy} x2={gearConfigs[2].cx} y2={gearConfigs[2].cy} />
        <line x1={gearConfigs[1].cx} y1={gearConfigs[1].cy} x2={gearConfigs[2].cx} y2={gearConfigs[2].cy} />
      </g>

      {/* Gears */}
      {gearConfigs.map((gear, idx) => (
        <g
          key={idx}
          style={{
            transformOrigin: `${gear.cx}px ${gear.cy}px`,
            animation: active ? `spin ${Math.abs(gear.speed)}s linear infinite ${gear.speed < 0 ? 'reverse' : 'normal'}` : undefined,
          }}
        >
          {/* Gear outline */}
          <path
            d={buildGearPath(gear.cx, gear.cy, gear.r, gear.teeth)}
            fill="none"
            stroke="var(--color-accent)"
            strokeWidth={1.5}
            opacity={0.7}
          />
          {/* Inner circle */}
          <circle
            cx={gear.cx}
            cy={gear.cy}
            r={gear.r * 0.4}
            fill="none"
            stroke="var(--color-accent)"
            strokeWidth={1}
            opacity={0.5}
          />
          {/* Center dot */}
          <circle
            cx={gear.cx}
            cy={gear.cy}
            r={3}
            fill="var(--color-accent)"
            className={active ? "tty-glow" : ""}
          />
        </g>
      ))}

      {/* Data flow indicators */}
      {active && (
        <g>
          {[0, 1, 2].map((i) => (
            <circle
              key={i}
              r={2}
              fill="var(--color-accent)"
              opacity={0.8}
              className="tty-glow"
            >
              <animateMotion
                dur={`${2 + i * 0.5}s`}
                repeatCount="indefinite"
                path={`M ${gearConfigs[0].cx} ${gearConfigs[0].cy} L ${gearConfigs[(i + 1) % 3].cx} ${gearConfigs[(i + 1) % 3].cy}`}
              />
            </circle>
          ))}
        </g>
      )}

      {/* Status indicator box */}
      <rect
        x={size * 0.7}
        y={size * 0.12}
        width={size * 0.22}
        height={size * 0.18}
        fill="none"
        stroke="var(--color-border)"
        strokeWidth={1}
      />
      <text
        x={size * 0.81}
        y={size * 0.18}
        textAnchor="middle"
        fontSize={8}
        fill="var(--color-dim)"
        fontFamily="monospace"
      >
        CONFIG
      </text>
      <circle
        cx={size * 0.81}
        cy={size * 0.25}
        r={4}
        fill={active ? "var(--color-low)" : "var(--color-dim)"}
        className={active ? "tty-glow" : ""}
      />
    </svg>
  )
}

// ─── Section Header ───────────────────────────────────────────────────────────

function SectionHeader({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>
  title: string
  children?: React.ReactNode
}) {
  return (
    <div className="flex items-center justify-between mb-4">
      <div className="flex items-center gap-3">
        <Icon className="h-4 w-4 text-accent" />
        <span className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
          <span className="text-accent">[</span> {title} <span className="text-accent">]</span>
        </span>
      </div>
      {children}
    </div>
  )
}

// ─── Tag Input ────────────────────────────────────────────────────────────────

function TagInput({
  value,
  onChange,
  placeholder,
  disabled,
}: {
  value: string[]
  onChange: (tags: string[]) => void
  placeholder?: string
  disabled?: boolean
}) {
  const [input, setInput] = useState("")

  const addTag = () => {
    const tag = input.trim()
    if (tag && !value.includes(tag)) {
      onChange([...value, tag])
    }
    setInput("")
  }

  const removeTag = (tag: string) => {
    onChange(value.filter((t) => t !== tag))
  }

  return (
    <div className={cn("border border-border bg-background", disabled && "opacity-50")}>
      <div className="flex flex-wrap gap-1 p-2 min-h-[36px]">
        {value.map((tag) => (
          <span
            key={tag}
            className="flex items-center gap-1 px-2 h-6 bg-muted text-xs text-foreground"
          >
            {tag}
            {!disabled && (
              <button
                type="button"
                onClick={() => removeTag(tag)}
                className="text-dim hover:text-foreground"
              >
                &times;
              </button>
            )}
          </span>
        ))}
        {!disabled && (
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === ",") {
                e.preventDefault()
                addTag()
              }
            }}
            onBlur={addTag}
            placeholder={value.length === 0 ? placeholder : ""}
            className="flex-1 min-w-[100px] bg-transparent text-xs text-foreground outline-none placeholder:text-dim"
          />
        )}
      </div>
    </div>
  )
}

// ─── Project Info Section ─────────────────────────────────────────────────────

function ProjectInfoSection({
  projectInfo,
  onSave,
  isSaving,
}: {
  projectInfo: ProjectInfo | null
  onSave: (updates: Partial<ProjectInfo>) => void
  isSaving: boolean
}) {
  const [form, setForm] = useState<Partial<ProjectInfo>>({})
  const [isDirty, setIsDirty] = useState(false)

  useEffect(() => {
    if (projectInfo) {
      setForm({
        name: projectInfo.name,
        code: projectInfo.code,
        company: projectInfo.company ?? "",
        department: projectInfo.department ?? "",
        abbreviation: projectInfo.abbreviation ?? "",
      })
      setIsDirty(false)
    }
  }, [projectInfo])

  const updateField = (field: keyof ProjectInfo, value: string) => {
    setForm((f) => ({ ...f, [field]: value }))
    setIsDirty(true)
  }

  const handleSave = () => {
    onSave(form)
    setIsDirty(false)
  }

  const handleReset = () => {
    if (projectInfo) {
      setForm({
        name: projectInfo.name,
        code: projectInfo.code,
        company: projectInfo.company ?? "",
        department: projectInfo.department ?? "",
        abbreviation: projectInfo.abbreviation ?? "",
      })
      setIsDirty(false)
    }
  }

  if (!projectInfo) {
    return (
      <Panel>
        <SectionHeader icon={Settings} title="PROJECT INFO" />
        <div className="text-sm text-dim">Loading project info...</div>
      </Panel>
    )
  }

  return (
    <Panel>
      <SectionHeader icon={Settings} title="PROJECT INFO">
        <div className="flex items-center gap-2">
          <button
            onClick={handleReset}
            disabled={!isDirty}
            className={cn(
              "flex items-center gap-1 px-3 h-7 text-[10px] uppercase tracking-wider border transition-colors",
              isDirty
                ? "border-border text-muted-foreground hover:bg-muted/30"
                : "border-border/50 text-dim cursor-not-allowed",
            )}
          >
            <RotateCcw className="h-3 w-3" />
            Reset
          </button>
          <button
            onClick={handleSave}
            disabled={!isDirty || isSaving}
            className={cn(
              "flex items-center gap-1 px-3 h-7 text-[10px] uppercase tracking-wider transition-colors",
              isDirty
                ? "bg-accent text-background hover:bg-accent/80"
                : "bg-muted text-dim cursor-not-allowed",
            )}
          >
            <Save className="h-3 w-3" />
            {isSaving ? "Saving..." : "Save"}
          </button>
        </div>
      </SectionHeader>

      <div className="grid grid-cols-2 gap-4">
        {/* Editable fields */}
        <div className="space-y-3">
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
              Project Name
            </label>
            <input
              type="text"
              value={form.name ?? ""}
              onChange={(e) => updateField("name", e.target.value)}
              className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
              Code
            </label>
            <input
              type="text"
              value={form.code ?? ""}
              onChange={(e) => updateField("code", e.target.value.toUpperCase())}
              maxLength={4}
              className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
              Company
            </label>
            <input
              type="text"
              value={form.company ?? ""}
              onChange={(e) => updateField("company", e.target.value)}
              className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
              Department
            </label>
            <input
              type="text"
              value={form.department ?? ""}
              onChange={(e) => updateField("department", e.target.value)}
              className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none"
            />
          </div>
        </div>

        {/* Read-only info */}
        <div className="space-y-3">
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-dim mb-1">
              Path (read-only)
            </label>
            <div className="h-8 px-2 flex items-center bg-muted/30 border border-border/50 text-xs text-dim font-mono">
              {projectInfo.path}
            </div>
          </div>
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-dim mb-1">
              Created
            </label>
            <div className="h-8 px-2 flex items-center bg-muted/30 border border-border/50 text-xs text-dim">
              {new Date(projectInfo.createdAt).toLocaleDateString()}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-dim mb-1">
                Repositories
              </label>
              <div className="h-8 px-2 flex items-center bg-muted/30 border border-border/50 text-xs text-dim tabular-nums">
                {projectInfo.repoCount}
              </div>
            </div>
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-dim mb-1">
                Findings
              </label>
              <div className="h-8 px-2 flex items-center bg-muted/30 border border-border/50 text-xs text-dim tabular-nums">
                {projectInfo.findingCount}
              </div>
            </div>
          </div>
        </div>
      </div>
    </Panel>
  )
}

// ─── Repository Section ───────────────────────────────────────────────────────

function RepositorySection({
  repositories,
  projectId,
  onSave,
  onDelete,
  isSaving,
}: {
  repositories: RepositoryConfig[]
  projectId: string
  onSave: (repo: RepositoryConfig, isNew: boolean) => void
  onDelete: (repoId: string) => void
  isSaving: boolean
}) {
  const [selectedId, setSelectedId] = useState<string | "new" | null>(null)
  const [form, setForm] = useState<Partial<RepositoryConfig>>({})
  const [isDirty, setIsDirty] = useState(false)

  // Initialize form when selection changes
  useEffect(() => {
    if (selectedId === "new") {
      setForm({
        projectId,
        name: "",
        types: [],
        locationMode: "local",
        localPath: "",
        languages: [],
        testDirectories: [],
        ignoreDirectories: [],
        baseUrls: [],
        alsoRunCrawlers: true,
        katana: { headless: false, crawlDepth: 10 },
      })
      setIsDirty(false)
    } else if (selectedId) {
      const repo = repositories.find((r) => r.id === selectedId)
      if (repo) {
        setForm({ ...repo })
        setIsDirty(false)
      }
    }
  }, [selectedId, repositories, projectId])

  const updateField = <K extends keyof RepositoryConfig>(field: K, value: RepositoryConfig[K]) => {
    setForm((f) => ({ ...f, [field]: value }))
    setIsDirty(true)
  }

  const handleSave = () => {
    if (!form.name) return
    onSave(form as RepositoryConfig, selectedId === "new")
    if (selectedId === "new") setSelectedId(null)
    setIsDirty(false)
  }

  const handleReset = () => {
    if (selectedId === "new") {
      setSelectedId(null)
    } else if (selectedId) {
      const repo = repositories.find((r) => r.id === selectedId)
      if (repo) setForm({ ...repo })
    }
    setIsDirty(false)
  }

  const handleDelete = () => {
    if (selectedId && selectedId !== "new") {
      if (confirm("Delete this repository? This cannot be undone.")) {
        onDelete(selectedId)
        setSelectedId(null)
      }
    }
  }

  // Type selection logic: library is mutually exclusive
  const toggleType = (type: RepoType) => {
    const current = form.types ?? []
    if (type === "library") {
      updateField("types", current.includes("library") ? [] : ["library"])
    } else {
      if (current.includes("library")) return // Can't add api/ui when library selected
      if (current.includes(type)) {
        updateField("types", current.filter((t) => t !== type))
      } else {
        updateField("types", [...current, type])
      }
    }
  }

  const isLibrary = form.types?.includes("library") ?? false
  const hasBaseUrls = (form.baseUrls?.length ?? 0) > 0
  const hasEndpointFile = Boolean(form.endpointFile)
  const showCrawlerQuestion = hasBaseUrls && hasEndpointFile
  const showKatanaFields = hasBaseUrls && (!hasEndpointFile || form.alsoRunCrawlers)

  return (
    <Panel>
      <SectionHeader icon={Database} title="REPOSITORIES">
        <div className="flex items-center gap-2">
          {/* Repo selector */}
          <div className="relative">
            <select
              value={selectedId ?? ""}
              onChange={(e) => setSelectedId(e.target.value || null)}
              className="h-7 pl-2 pr-6 bg-background border border-border text-xs text-foreground appearance-none cursor-pointer focus:border-accent focus:outline-none"
            >
              <option value="">Select repository...</option>
              {repositories.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 h-3 w-3 text-dim pointer-events-none" />
          </div>
          <button
            onClick={() => setSelectedId("new")}
            className="flex items-center gap-1 px-2 h-7 text-[10px] uppercase tracking-wider border border-border text-muted-foreground hover:bg-muted/30 transition-colors"
          >
            <Plus className="h-3 w-3" />
            New
          </button>
        </div>
      </SectionHeader>

      {!selectedId && (
        <div className="text-sm text-dim py-8 text-center">
          Select a repository to edit or create a new one
        </div>
      )}

      {selectedId && (
        <div className="space-y-4">
          {/* Identity */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                Name <span className="text-crit">*</span>
              </label>
              <input
                type="text"
                value={form.name ?? ""}
                onChange={(e) => updateField("name", e.target.value)}
                className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                Type <span className="text-crit">*</span>
              </label>
              <div className="flex gap-2">
                {(["library", "api", "ui"] as RepoType[]).map((type) => {
                  const selected = form.types?.includes(type)
                  const disabled = type !== "library" && isLibrary
                  return (
                    <button
                      key={type}
                      onClick={() => toggleType(type)}
                      disabled={disabled}
                      className={cn(
                        "px-3 h-8 text-[10px] uppercase tracking-wider border transition-colors",
                        selected
                          ? "border-accent bg-accent/20 text-accent"
                          : disabled
                            ? "border-border/50 text-dim cursor-not-allowed"
                            : "border-border text-muted-foreground hover:border-muted-foreground",
                      )}
                    >
                      {type}
                    </button>
                  )
                })}
              </div>
              <div className="text-[9px] text-dim mt-1">
                library cannot be combined with api or ui
              </div>
            </div>
          </div>

          {/* Location */}
          <div className="border-t border-border pt-4">
            <label className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
              Location Mode
            </label>
            <div className="flex gap-2 mb-3">
              {(["local", "docker"] as RepoLocationMode[]).map((mode) => (
                <button
                  key={mode}
                  onClick={() => updateField("locationMode", mode)}
                  className={cn(
                    "px-4 h-8 text-[10px] uppercase tracking-wider border transition-colors",
                    form.locationMode === mode
                      ? "border-accent bg-accent/20 text-accent"
                      : "border-border text-muted-foreground hover:border-muted-foreground",
                  )}
                >
                  {mode}
                </button>
              ))}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                  Local Path <span className="text-crit">*</span>
                </label>
                <input
                  type="text"
                  value={form.localPath ?? ""}
                  onChange={(e) => updateField("localPath", e.target.value)}
                  placeholder="/path/to/repo"
                  className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground font-mono focus:border-accent focus:outline-none"
                />
                {form.locationMode === "docker" && (
                  <div className="text-[9px] text-dim mt-1">
                    Required for language detection and local tool execution
                  </div>
                )}
              </div>

              {form.locationMode === "docker" && (
                <>
                  <div>
                    <label className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                      Container Name <span className="text-crit">*</span>
                    </label>
                    <input
                      type="text"
                      value={form.docker?.containerName ?? ""}
                      onChange={(e) =>
                        updateField("docker", { ...form.docker, containerName: e.target.value, mountPoint: form.docker?.mountPoint ?? "" })
                      }
                      className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                      Mount Point <span className="text-crit">*</span>
                    </label>
                    <input
                      type="text"
                      value={form.docker?.mountPoint ?? ""}
                      onChange={(e) =>
                        updateField("docker", { ...form.docker, containerName: form.docker?.containerName ?? "", mountPoint: e.target.value })
                      }
                      placeholder="/app"
                      className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground font-mono focus:border-accent focus:outline-none"
                    />
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Code Context */}
          <div className="border-t border-border pt-4 grid grid-cols-3 gap-4">
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                Languages <span className="text-crit">*</span>
              </label>
              <TagInput
                value={form.languages ?? []}
                onChange={(tags) => updateField("languages", tags)}
                placeholder="python, javascript..."
              />
            </div>
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                Test Directories
              </label>
              <TagInput
                value={form.testDirectories ?? []}
                onChange={(tags) => updateField("testDirectories", tags)}
                placeholder="tests, spec..."
              />
            </div>
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                Ignore Directories
              </label>
              <TagInput
                value={form.ignoreDirectories ?? []}
                onChange={(tags) => updateField("ignoreDirectories", tags)}
                placeholder="vendor, node_modules..."
              />
            </div>
          </div>

          {/* API Targets */}
          <div className="border-t border-border pt-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                  Base URLs
                </label>
                <TagInput
                  value={form.baseUrls ?? []}
                  onChange={(tags) => updateField("baseUrls", tags)}
                  placeholder="https://api.example.com"
                />
                <div className="text-[9px] text-dim mt-1">
                  First URL is used as canonical scope for scans
                </div>
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                  Endpoint File
                </label>
                <input
                  type="text"
                  value={form.endpointFile ?? ""}
                  onChange={(e) => updateField("endpointFile", e.target.value)}
                  placeholder="/path/to/openapi.yaml"
                  className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground font-mono focus:border-accent focus:outline-none"
                />
                <div className="text-[9px] text-dim mt-1">
                  OpenAPI, Swagger, Postman, HAR, or Katana JSONL
                </div>
              </div>
            </div>

            {showCrawlerQuestion && (
              <div className="mt-3 p-3 border border-border bg-muted/20">
                <label className="flex items-center gap-2 cursor-pointer">
                  <button
                    onClick={() => updateField("alsoRunCrawlers", !form.alsoRunCrawlers)}
                    className={cn(
                      "w-4 h-4 border flex items-center justify-center transition-colors",
                      form.alsoRunCrawlers
                        ? "border-accent bg-accent text-background"
                        : "border-border hover:border-muted-foreground",
                    )}
                  >
                    {form.alsoRunCrawlers && <Check className="h-3 w-3" />}
                  </button>
                  <span className="text-xs text-foreground">Also run live crawlers to supplement the endpoint file?</span>
                </label>
                {!form.alsoRunCrawlers && (
                  <div className="mt-2 flex items-start gap-2 text-[10px] text-high">
                    <AlertCircle className="h-3 w-3 mt-0.5 shrink-0" />
                    <span>ZAP will rely entirely on the endpoint file. Results are only as good as the file.</span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Katana Settings */}
          {showKatanaFields && (
            <div className="border-t border-border pt-4">
              <label className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
                Crawler Settings
              </label>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <button
                      onClick={() => {
                        const newHeadless = !form.katana?.headless
                        updateField("katana", {
                          headless: newHeadless,
                          crawlDepth: newHeadless ? Math.min(form.katana?.crawlDepth ?? 10, 5) : (form.katana?.crawlDepth ?? 10),
                        })
                      }}
                      className={cn(
                        "w-4 h-4 border flex items-center justify-center transition-colors",
                        form.katana?.headless
                          ? "border-accent bg-accent text-background"
                          : "border-border hover:border-muted-foreground",
                      )}
                    >
                      {form.katana?.headless && <Check className="h-3 w-3" />}
                    </button>
                    <span className="text-xs text-foreground">Katana headless mode</span>
                  </label>
                  <div className="text-[9px] text-dim mt-1 ml-6">
                    Uses Chrome to render JavaScript routes. Slower, required for SPAs.
                  </div>
                  {form.detected?.isSpa && (
                    <div className="mt-1 ml-6 flex items-center gap-1 text-[9px] text-high">
                      <AlertCircle className="h-3 w-3" />
                      SPA detected — headless recommended
                    </div>
                  )}
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                    Crawl Depth {form.katana?.headless && <span className="text-high">(max 5 in headless)</span>}
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={form.katana?.headless ? 5 : 20}
                    value={form.katana?.crawlDepth ?? 10}
                    onChange={(e) =>
                      updateField("katana", { ...form.katana!, crawlDepth: parseInt(e.target.value) || 10 })
                    }
                    className="w-24 h-8 px-2 bg-background border border-border text-xs text-foreground tabular-nums focus:border-accent focus:outline-none"
                  />
                </div>
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="border-t border-border pt-4 flex items-center justify-between">
            <div>
              {selectedId !== "new" && (
                <button
                  onClick={handleDelete}
                  className="flex items-center gap-1 px-3 h-8 text-[10px] uppercase tracking-wider border border-crit text-crit hover:bg-crit/10 transition-colors"
                >
                  <Trash2 className="h-3 w-3" />
                  Delete
                </button>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleReset}
                className="flex items-center gap-1 px-3 h-8 text-[10px] uppercase tracking-wider border border-border text-muted-foreground hover:bg-muted/30 transition-colors"
              >
                <RotateCcw className="h-3 w-3" />
                Reset
              </button>
              <button
                onClick={handleSave}
                disabled={!form.name || !form.localPath || (form.types?.length ?? 0) === 0 || isSaving}
                className={cn(
                  "flex items-center gap-1 px-4 h-8 text-[10px] uppercase tracking-wider transition-colors",
                  form.name && form.localPath && (form.types?.length ?? 0) > 0
                    ? "bg-accent text-background hover:bg-accent/80"
                    : "bg-muted text-dim cursor-not-allowed",
                )}
              >
                <Save className="h-3 w-3" />
                {isSaving ? "Saving..." : selectedId === "new" ? "Create" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}
    </Panel>
  )
}

// ─── Tool Overrides Section ───────────────────────────────────────────────────

function ToolOverridesSection({
  catalog,
  overrides,
  projectId,
  onSave,
  onDelete,
  isSaving,
}: {
  catalog: ToolCatalogEntry[]
  overrides: ToolOverrideConfig[]
  projectId: string
  onSave: (override: ToolOverrideConfig, isNew: boolean) => void
  onDelete: (toolId: string) => void
  isSaving: boolean
}) {
  const [selectedToolId, setSelectedToolId] = useState<string | null>(null)
  const [form, setForm] = useState<Partial<ToolOverrideConfig>>({})
  const [isDirty, setIsDirty] = useState(false)

  const selectedTool = catalog.find((t) => t.id === selectedToolId)
  const existingOverride = overrides.find((o) => o.toolId === selectedToolId)
  const isNew = selectedToolId && !existingOverride

  // Available tools for adding (not already overridden)
  const availableForAdd = catalog.filter((t) => !overrides.some((o) => o.toolId === t.id))

  useEffect(() => {
    if (selectedToolId) {
      const existing = overrides.find((o) => o.toolId === selectedToolId)
      if (existing) {
        setForm({ ...existing })
      } else {
        const tool = catalog.find((t) => t.id === selectedToolId)
        setForm({
          toolId: selectedToolId,
          type: "repo",
          location: tool?.supportsLocal ? "local" : "docker",
        })
      }
      setIsDirty(false)
    }
  }, [selectedToolId, overrides, catalog])

  const updateField = <K extends keyof ToolOverrideConfig>(field: K, value: ToolOverrideConfig[K]) => {
    setForm((f) => ({ ...f, [field]: value }))
    setIsDirty(true)
  }

  const handleSave = () => {
    if (!selectedToolId) return
    onSave(form as ToolOverrideConfig, !!isNew)
    setIsDirty(false)
  }

  const handleDelete = () => {
    if (selectedToolId && !isNew) {
      if (confirm("Remove this override? The tool will revert to global configuration.")) {
        onDelete(selectedToolId)
        setSelectedToolId(null)
      }
    }
  }

  const canSelectDocker = selectedTool?.supportsDocker ?? true

  return (
    <Panel>
      <SectionHeader icon={Wrench} title="TOOL OVERRIDES">
        <div className="flex items-center gap-2">
          {/* Existing overrides selector */}
          {overrides.length > 0 && (
            <div className="relative">
              <select
                value={selectedToolId ?? ""}
                onChange={(e) => setSelectedToolId(e.target.value || null)}
                className="h-7 pl-2 pr-6 bg-background border border-border text-xs text-foreground appearance-none cursor-pointer focus:border-accent focus:outline-none"
              >
                <option value="">Select override...</option>
                {overrides.map((o) => {
                  const tool = catalog.find((t) => t.id === o.toolId)
                  return (
                    <option key={o.toolId} value={o.toolId}>
                      {tool?.name ?? o.toolId}
                    </option>
                  )
                })}
              </select>
              <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 h-3 w-3 text-dim pointer-events-none" />
            </div>
          )}

          {/* Add new override */}
          {availableForAdd.length > 0 && (
            <div className="relative">
              <select
                value=""
                onChange={(e) => {
                  if (e.target.value) setSelectedToolId(e.target.value)
                }}
                className="h-7 pl-2 pr-6 bg-background border border-accent/50 text-xs text-accent appearance-none cursor-pointer focus:border-accent focus:outline-none"
              >
                <option value="">+ Add Override</option>
                {availableForAdd.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 h-3 w-3 text-accent pointer-events-none" />
            </div>
          )}
        </div>
      </SectionHeader>

      {!selectedToolId && (
        <div className="text-sm text-dim py-8 text-center">
          {overrides.length === 0
            ? "No tool overrides configured. Add one to customize tool paths for this project."
            : "Select a tool override to edit or add a new one."}
        </div>
      )}

      {selectedToolId && selectedTool && (
        <div className="space-y-4">
          {/* Tool info */}
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <div className="text-sm text-foreground font-bold">{selectedTool.name}</div>
              <div className="text-[10px] text-dim uppercase tracking-wider">
                {isNew ? "New override" : "Overrides global default"}
              </div>
            </div>
            {!isNew && (
              <span className="px-2 h-5 flex items-center text-[9px] uppercase tracking-wider bg-high/20 text-high">
                Override Active
              </span>
            )}
          </div>

          {/* Type */}
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
              Type
            </label>
            <div className="flex gap-2">
              {(["repo", "api"] as ToolType[]).map((type) => (
                <button
                  key={type}
                  onClick={() => updateField("type", type)}
                  className={cn(
                    "px-4 h-8 text-[10px] uppercase tracking-wider border transition-colors",
                    form.type === type
                      ? "border-accent bg-accent/20 text-accent"
                      : "border-border text-muted-foreground hover:border-muted-foreground",
                  )}
                >
                  {type}
                </button>
              ))}
            </div>
          </div>

          {/* Location */}
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
              Location
            </label>
            <div className="flex gap-2">
              {(["local", "docker"] as ToolLocationMode[]).map((loc) => {
                const disabled = loc === "docker" && !canSelectDocker
                return (
                  <button
                    key={loc}
                    onClick={() => updateField("location", loc)}
                    disabled={disabled}
                    className={cn(
                      "px-4 h-8 text-[10px] uppercase tracking-wider border transition-colors",
                      form.location === loc
                        ? "border-accent bg-accent/20 text-accent"
                        : disabled
                          ? "border-border/50 text-dim cursor-not-allowed"
                          : "border-border text-muted-foreground hover:border-muted-foreground",
                    )}
                  >
                    {loc}
                  </button>
                )
              })}
            </div>
            {!canSelectDocker && (
              <div className="text-[9px] text-dim mt-1">
                {selectedTool.name} does not support Docker mode
              </div>
            )}
          </div>

          {/* Path fields */}
          {form.location === "local" ? (
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                Path <span className="text-crit">*</span>
              </label>
              <input
                type="text"
                value={form.path ?? ""}
                onChange={(e) => updateField("path", e.target.value)}
                placeholder="/path/to/tool"
                className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground font-mono focus:border-accent focus:outline-none"
              />
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                  Container Name <span className="text-crit">*</span>
                </label>
                <input
                  type="text"
                  value={form.container?.name ?? ""}
                  onChange={(e) =>
                    updateField("container", { name: e.target.value, toolPath: form.container?.toolPath ?? "" })
                  }
                  className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                  Tool Path in Container <span className="text-crit">*</span>
                </label>
                <input
                  type="text"
                  value={form.container?.toolPath ?? ""}
                  onChange={(e) =>
                    updateField("container", { name: form.container?.name ?? "", toolPath: e.target.value })
                  }
                  placeholder="/usr/local/bin/tool"
                  className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground font-mono focus:border-accent focus:outline-none"
                />
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="border-t border-border pt-4 flex items-center justify-between">
            <div>
              {!isNew && (
                <button
                  onClick={handleDelete}
                  className="flex items-center gap-1 px-3 h-8 text-[10px] uppercase tracking-wider border border-crit text-crit hover:bg-crit/10 transition-colors"
                >
                  <Trash2 className="h-3 w-3" />
                  Remove Override
                </button>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setSelectedToolId(null)}
                className="flex items-center gap-1 px-3 h-8 text-[10px] uppercase tracking-wider border border-border text-muted-foreground hover:bg-muted/30 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={
                  isSaving ||
                  (form.location === "local" && !form.path) ||
                  (form.location === "docker" && (!form.container?.name || !form.container?.toolPath))
                }
                className={cn(
                  "flex items-center gap-1 px-4 h-8 text-[10px] uppercase tracking-wider transition-colors",
                  (form.location === "local" && form.path) ||
                  (form.location === "docker" && form.container?.name && form.container?.toolPath)
                    ? "bg-accent text-background hover:bg-accent/80"
                    : "bg-muted text-dim cursor-not-allowed",
                )}
              >
                <Save className="h-3 w-3" />
                {isSaving ? "Saving..." : isNew ? "Create" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}
    </Panel>
  )
}

// ─── Main Config Page ─────────────────────────────────────────────────────────

export default function Config() {
  const activeProjectId = useUI((s) => s.activeProjectId)

  // TODO [BACKEND]: These hooks return mock data. Replace with real API calls.
  const { data: projects = [] } = useProjects()
  const { data: projectInfo } = useProjectInfo(activeProjectId)
  const { data: repositories = [] } = useRepositories(activeProjectId)
  const { data: toolCatalog = [] } = useToolCatalog()
  const { data: toolOverrides = [] } = useToolOverrides(activeProjectId)

  // Mutations
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
          {/* Repositories - left column */}
          <RepositorySection
            repositories={repositories}
            projectId={activeProjectId}
            onSave={(repo, isNew) => saveRepository.mutate({ repo, isNew })}
            onDelete={(repoId) => deleteRepository.mutate({ repoId, projectId: activeProjectId })}
            isSaving={saveRepository.isPending}
          />

          {/* Tool Overrides - right column */}
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
