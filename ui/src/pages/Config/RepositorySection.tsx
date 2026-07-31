import { useState, useEffect, useRef } from 'react'
import {
  Database,
  ChevronDown,
  Plus,
  Trash2,
  Save,
  RotateCcw,
  Check,
  AlertCircle,
  Lock,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Panel } from '@/components/tty'
import type {
  AuthHeaderEntry,
  ConfigMode,
  RepositoryAuthUpdate,
  RepositoryConfig,
  ServiceConfig,
} from '@/lib/types'
import { deriveConfigMode, emptyService } from '@/lib/types'
import { SectionHeader } from './shared'
import { ServiceDetailForm } from './ServiceDetailForm'
import { ServiceListPanel } from './ServiceListPanel'

const NEW_REPO_ID = -1 as const

interface AuthFormState {
  authType: 'form' | 'header'
  loginUrl: string
  username: string
  password: string
  authHeaders: AuthHeaderEntry[]
}

const EMPTY_AUTH: AuthFormState = {
  authType: 'form',
  loginUrl: '',
  username: '',
  password: '',
  authHeaders: [],
}

export function RepositorySection({
  repositories,
  projectId,
  onSave,
  onDelete,
  onUpdateAuth,
  isSaving,
  isSavingAuth,
  authSavedAt,
  saveCompletedAt,
}: {
  repositories: RepositoryConfig[]
  projectId: number
  onSave: (
    repo: RepositoryConfig,
    isNew: boolean,
    endpointFile?: File | null,
    garakConfigFile?: File | null
  ) => void
  onDelete: (repoId: number) => void
  onUpdateAuth: (repoId: number, auth: RepositoryAuthUpdate) => void
  isSaving: boolean
  isSavingAuth: boolean
  authSavedAt: number | null
  saveCompletedAt: number | null
}) {
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [repoName, setRepoName] = useState('')
  const [localPath, setLocalPath] = useState('')
  const [formServices, setFormServices] = useState<ServiceConfig[]>([])
  const [selectedServiceIdx, setSelectedServiceIdx] = useState(0)
  const [mode, setMode] = useState<ConfigMode>('basic')
  const [katana, setKatana] = useState({
    headless: false,
    crawlDepth: 10,
  })
  const [endpointFileUpload, setEndpointFileUpload] = useState<File | null>(null)
  const [garakConfigUpload, setGarakConfigUpload] = useState<File | null>(null)
  const [existingEndpointFile, setExistingEndpointFile] = useState<string | undefined>(undefined)
  const [existingGarakFile, setExistingGarakFile] = useState<string | undefined>(undefined)
  const [_isDirty, setIsDirty] = useState(false)
  const [auth, setAuth] = useState<AuthFormState>(EMPTY_AUTH)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const garakFileInputRef = useRef<HTMLInputElement | null>(null)
  const pendingNewRepoRef = useRef(false)

  const isNewRepo = selectedId === NEW_REPO_ID

  useEffect(() => {
    if (isNewRepo) {
      setRepoName('')
      setLocalPath('')
      setFormServices([emptyService()])
      setSelectedServiceIdx(0)
      setMode('basic')
      setKatana({ headless: false, crawlDepth: 10 })
      setEndpointFileUpload(null)
      setGarakConfigUpload(null)
      setExistingEndpointFile(undefined)
      setExistingGarakFile(undefined)
      setAuth(EMPTY_AUTH)
      setIsDirty(false)
    } else if (selectedId !== null) {
      const repo = repositories.find(r => r.id === selectedId)
      if (repo) {
        setRepoName(repo.name)
        setLocalPath(repo.localPath)
        setFormServices([...repo.services])
        setSelectedServiceIdx(0)
        setMode(deriveConfigMode(repo.services))
        setKatana({ ...repo.katana })
        setEndpointFileUpload(null)
        setGarakConfigUpload(null)
        setExistingEndpointFile(repo.endpointFile)
        setExistingGarakFile(repo.garakConfigFile)
        if (repo.authType === 'header' && repo.authHeadersMeta?.length) {
          setAuth({
            authType: 'header',
            loginUrl: '',
            username: '',
            password: '',
            authHeaders: repo.authHeadersMeta,
          })
        } else if (repo.authConfigured && repo.authLoginUrl) {
          setAuth({
            authType: 'form',
            loginUrl: repo.authLoginUrl,
            username: '',
            password: '',
            authHeaders: [],
          })
        } else {
          setAuth(EMPTY_AUTH)
        }
        setIsDirty(false)
      }
    }
  }, [selectedId, repositories, isNewRepo])

  const updateService = <K extends keyof ServiceConfig>(field: K, value: ServiceConfig[K]) => {
    setFormServices(svcs => {
      const updated = [...svcs]
      updated[selectedServiceIdx] = {
        ...updated[selectedServiceIdx],
        [field]: value,
      }
      return updated
    })
    setIsDirty(true)
  }

  const handleAddService = () => {
    const newName = `service-${formServices.length + 1}`
    setFormServices(svcs => [...svcs, emptyService(newName)])
    setSelectedServiceIdx(formServices.length)
    setMode('advanced')
    setIsDirty(true)
  }

  const handleDeleteService = (index: number) => {
    if (formServices.length <= 1) return
    setFormServices(svcs => svcs.filter((_, i) => i !== index))
    if (selectedServiceIdx >= index && selectedServiceIdx > 0) {
      setSelectedServiceIdx(selectedServiceIdx - 1)
    }
    setIsDirty(true)
  }

  const handleToggleMode = (newMode: ConfigMode) => {
    if (newMode === 'advanced' && mode === 'basic') {
      setMode('advanced')
    }
  }

  const canSwitchToBasic = formServices.length <= 1

  const handleSave = () => {
    if (!repoName || !localPath) return
    const activeService = formServices[0]
    if (!activeService || activeService.type.length === 0) {
      return
    }
    const repo: RepositoryConfig = {
      id: isNewRepo ? 0 : (selectedId ?? 0),
      projectId,
      name: repoName,
      localPath,
      services: formServices,
      alsoRunCrawlers: formServices[selectedServiceIdx]?.crawlEnabled ?? true,
      katana,
    }
    if (isNewRepo && auth.loginUrl) {
      repo.auth = {
        loginUrl: auth.loginUrl,
        usernameFieldName: 'username',
        passwordFieldName: 'password',
        inlineUsername: auth.username,
        inlinePassword: auth.password,
      }
    }
    if (isNewRepo) pendingNewRepoRef.current = true
    onSave(repo, isNewRepo, endpointFileUpload, garakConfigUpload)
  }

  useEffect(() => {
    if (saveCompletedAt === null) return
    setEndpointFileUpload(null)
    setGarakConfigUpload(null)
    setIsDirty(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
    if (garakFileInputRef.current) {
      garakFileInputRef.current.value = ''
    }
    if (pendingNewRepoRef.current) {
      setSelectedId(null)
      pendingNewRepoRef.current = false
    }
  }, [saveCompletedAt])

  const handleReset = () => {
    if (isNewRepo) {
      setSelectedId(null)
    } else if (selectedId !== null) {
      const repo = repositories.find(r => r.id === selectedId)
      if (repo) {
        setRepoName(repo.name)
        setLocalPath(repo.localPath)
        setFormServices([...repo.services])
        setSelectedServiceIdx(0)
        setMode(deriveConfigMode(repo.services))
        setKatana({ ...repo.katana })
      }
    }
    setEndpointFileUpload(null)
    setGarakConfigUpload(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
    if (garakFileInputRef.current) {
      garakFileInputRef.current.value = ''
    }
    setIsDirty(false)
  }

  const handleDelete = () => {
    if (selectedId !== null && !isNewRepo) {
      if (confirm('Delete this repository? This cannot be undone.')) {
        onDelete(selectedId)
        setSelectedId(null)
      }
    }
  }

  const handleSaveAuth = () => {
    if (selectedId === null || isNewRepo) return
    if (auth.authType === 'form') {
      if (!auth.loginUrl) return
      const payload: RepositoryAuthUpdate = {
        authType: 'form',
        loginUrl: auth.loginUrl,
      }
      if (auth.username) payload.username = auth.username
      if (auth.password) payload.password = auth.password
      onUpdateAuth(selectedId, payload)
    } else {
      const validHeaders = auth.authHeaders.filter(h => h.header)
      if (validHeaders.length === 0) return
      const payload: RepositoryAuthUpdate = {
        authType: 'header',
        authHeaders: validHeaders.map(h => ({
          header: h.header,
          value: h.value,
          value_env: h.valueEnv,
        })),
      }
      onUpdateAuth(selectedId, payload)
    }
  }

  const selectedRepo = repositories.find(r => r.id === selectedId)
  const currentService = formServices[selectedServiceIdx]
  const hasBaseUrls = (currentService?.baseUrls.length ?? 0) > 0
  const hasEndpointFile = Boolean(endpointFileUpload)
  const showCrawlerQuestion = hasBaseUrls && hasEndpointFile
  const showKatanaFields =
    hasBaseUrls && (!hasEndpointFile || (currentService?.crawlEnabled ?? true))

  const authJustSaved = authSavedAt !== null && Date.now() - authSavedAt < 3000

  const saveDisabled =
    !repoName || !localPath || (formServices[0]?.type.length ?? 0) === 0 || isSaving

  return (
    <Panel bodyClassName="p-4">
      <SectionHeader icon={Database} title="REPOSITORIES">
        <div className="flex items-center gap-2">
          <div className="relative">
            <select
              value={selectedId === null ? '' : String(selectedId)}
              onChange={e => setSelectedId(e.target.value === '' ? null : Number(e.target.value))}
              className="h-7 pl-2 pr-6 bg-background border border-border text-xs text-foreground appearance-none cursor-pointer focus:border-accent focus:outline-none"
            >
              <option value="">Select repository...</option>
              {repositories.map(r => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 h-3 w-3 text-dim pointer-events-none" />
          </div>
          <button
            onClick={() => setSelectedId(NEW_REPO_ID)}
            className="flex items-center gap-1 px-2 h-7 text-[10px] uppercase tracking-wider border border-border text-muted-foreground hover:bg-muted/30 transition-colors"
          >
            <Plus className="h-3 w-3" />
            New
          </button>
        </div>
      </SectionHeader>

      {selectedId === null && (
        <div className="text-sm text-dim py-8 text-center">
          Select a repository to edit or create a new one
        </div>
      )}

      {selectedId !== null && (
        <div className="space-y-4">
          {/* Mode toggle */}
          <div className="flex items-center gap-4">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                Mode
              </div>
              <div className="flex gap-2">
                {(['basic', 'advanced'] as ConfigMode[]).map(m => {
                  const disabled = m === 'basic' && !canSwitchToBasic
                  return (
                    <button
                      key={m}
                      onClick={() => handleToggleMode(m)}
                      disabled={disabled}
                      className={cn(
                        'px-3 h-7 text-[10px] uppercase tracking-wider border transition-colors',
                        mode === m
                          ? 'border-accent bg-accent/20 text-accent'
                          : disabled
                            ? 'border-border/50 text-dim cursor-not-allowed'
                            : 'border-border text-muted-foreground hover:border-muted-foreground'
                      )}
                    >
                      {m}
                      {disabled && <Lock className="inline ml-1 h-2.5 w-2.5" />}
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Repo name */}
            <div className="flex-1">
              <label
                htmlFor="repo-name"
                className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
              >
                Name <span className="text-crit">*</span>
              </label>
              <input
                id="repo-name"
                type="text"
                value={repoName}
                onChange={e => {
                  setRepoName(e.target.value)
                  setIsDirty(true)
                }}
                className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none"
              />
            </div>

            {/* Local path */}
            <div className="flex-1">
              <label
                htmlFor="repo-local-path"
                className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
              >
                Local Path <span className="text-crit">*</span>
              </label>
              <input
                id="repo-local-path"
                type="text"
                value={localPath}
                onChange={e => {
                  setLocalPath(e.target.value)
                  setIsDirty(true)
                }}
                placeholder="/path/to/repo"
                className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground font-mono focus:border-accent focus:outline-none"
              />
            </div>
          </div>

          {/* Service editing area */}
          <div className="border-t border-border pt-4">
            <div className="flex gap-4">
              {mode === 'advanced' && (
                <div className="w-48 flex-shrink-0">
                  <ServiceListPanel
                    services={formServices}
                    selectedIndex={selectedServiceIdx}
                    onSelect={setSelectedServiceIdx}
                    onAdd={handleAddService}
                    onDelete={handleDeleteService}
                  />
                </div>
              )}

              {currentService && (
                <div className="flex-1 min-w-0">
                  <ServiceDetailForm
                    service={currentService}
                    onChange={updateService}
                    mode={mode}
                    isDisabled={isSaving}
                    katanaDefaults={katana}
                  />
                </div>
              )}
            </div>
          </div>

          {/* Endpoint file + crawler question */}
          <div className="border-t border-border pt-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label
                  htmlFor="repo-endpoint-file"
                  className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
                >
                  Endpoint File
                </label>
                <input
                  ref={fileInputRef}
                  id="repo-endpoint-file"
                  type="file"
                  onChange={e => {
                    const file = e.target.files?.[0] ?? null
                    setEndpointFileUpload(file)
                    setIsDirty(true)
                  }}
                  className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground font-mono focus:border-accent focus:outline-none file:mr-2 file:py-1 file:px-2 file:bg-muted file:border-0 file:text-[10px] file:uppercase file:text-muted-foreground"
                />
                {existingEndpointFile && !endpointFileUpload && (
                  <div className="text-[9px] text-accent mt-1">
                    Current: {existingEndpointFile}. Uploading a new file will replace it.
                  </div>
                )}
                <div className="text-[9px] text-dim mt-1">
                  OpenAPI, Swagger, Postman, HAR, or Katana JSONL
                </div>
              </div>
              <div>
                <label
                  htmlFor="repo-garak-config"
                  className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
                >
                  Garak Config
                </label>
                <input
                  ref={garakFileInputRef}
                  id="repo-garak-config"
                  type="file"
                  accept=".yaml,.yml"
                  onChange={e => {
                    const file = e.target.files?.[0] ?? null
                    setGarakConfigUpload(file)
                    setIsDirty(true)
                  }}
                  className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground font-mono focus:border-accent focus:outline-none file:mr-2 file:py-1 file:px-2 file:bg-muted file:border-0 file:text-[10px] file:uppercase file:text-muted-foreground"
                />
                {existingGarakFile && !garakConfigUpload && (
                  <div className="text-[9px] text-accent mt-1">
                    Current: {existingGarakFile}. Uploading a new file will replace it.
                  </div>
                )}
                <div className="text-[9px] text-dim mt-1">
                  YAML config file required to run Garak
                </div>
              </div>
            </div>

            {showCrawlerQuestion && (
              <div className="mt-3 p-3 border border-border bg-muted/20">
                <div className="flex items-center gap-2 cursor-pointer">
                  <button
                    onClick={() => updateService('crawlEnabled', !currentService?.crawlEnabled)}
                    className={cn(
                      'w-4 h-4 border flex items-center justify-center transition-colors',
                      currentService?.crawlEnabled
                        ? 'border-accent bg-accent text-background'
                        : 'border-border hover:border-muted-foreground'
                    )}
                  >
                    {currentService?.crawlEnabled && <Check className="h-3 w-3" />}
                  </button>
                  <span className="text-xs text-foreground">
                    Also run live crawlers to supplement the endpoint file?
                  </span>
                </div>
                {!currentService?.crawlEnabled && (
                  <div className="mt-2 flex items-start gap-2 text-[10px] text-high">
                    <AlertCircle className="h-3 w-3 mt-0.5 shrink-0" />
                    <span>
                      ZAP will rely entirely on the endpoint file. Results are only as good as the
                      file.
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Katana settings (basic mode only; advanced mode shows per-service) */}
          {mode === 'basic' && showKatanaFields && (
            <div className="border-t border-border pt-4">
              <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
                Crawler Settings
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="flex items-center gap-2 cursor-pointer">
                    <button
                      onClick={() => {
                        const newHeadless = !katana.headless
                        setKatana({
                          headless: newHeadless,
                          crawlDepth: newHeadless
                            ? Math.min(katana.crawlDepth, 5)
                            : katana.crawlDepth,
                        })
                        setIsDirty(true)
                      }}
                      className={cn(
                        'w-4 h-4 border flex items-center justify-center transition-colors',
                        katana.headless
                          ? 'border-accent bg-accent text-background'
                          : 'border-border hover:border-muted-foreground'
                      )}
                    >
                      {katana.headless && <Check className="h-3 w-3" />}
                    </button>
                    <span className="text-xs text-foreground">Katana headless mode</span>
                  </div>
                  <div className="text-[9px] text-dim mt-1 ml-6">
                    Uses Chrome to render JavaScript routes. Slower, required for SPAs.
                  </div>
                </div>
                <div>
                  <label
                    htmlFor="repo-crawl-depth"
                    className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
                  >
                    Crawl Depth{' '}
                    {katana.headless && <span className="text-high">(max 5 in headless)</span>}
                  </label>
                  <input
                    id="repo-crawl-depth"
                    type="number"
                    min={1}
                    max={katana.headless ? 5 : 20}
                    value={katana.crawlDepth}
                    onChange={e => {
                      setKatana(k => ({
                        ...k,
                        crawlDepth: parseInt(e.target.value) || 10,
                      }))
                      setIsDirty(true)
                    }}
                    className="w-24 h-8 px-2 bg-background border border-border text-xs text-foreground tabular-nums focus:border-accent focus:outline-none"
                  />
                </div>
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="border-t border-border pt-4 flex items-center justify-between">
            <div>
              {!isNewRepo && (
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
                className="flex items-center gap-1 px-3 h-8 text-[10px] uppercase tracking-wider border border-border-strong text-muted-foreground hover:border-primary/50 hover:text-foreground transition-colors"
              >
                <RotateCcw className="h-3 w-3" />
                Reset
              </button>
              <button
                onClick={handleSave}
                disabled={saveDisabled}
                className={cn(
                  'flex items-center gap-1 px-4 h-8 text-[10px] uppercase tracking-wider transition-colors',
                  !saveDisabled
                    ? 'bg-accent text-background hover:bg-accent/80 hover:shadow-[0_0_8px_rgba(57,255,20,0.15)]'
                    : 'bg-muted text-dim opacity-40 cursor-not-allowed'
                )}
              >
                <Save className="h-3 w-3" />
                {isSaving ? 'Saving...' : isNewRepo ? 'Create' : 'Save'}
              </button>
            </div>
          </div>

          {/* Auth credentials */}
          <div className="border-t border-border pt-4">
            <div className="flex items-center gap-2 mb-2">
              <Lock className="h-3 w-3 text-muted-foreground" />
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Auth Credentials
              </span>
            </div>
            <div className="text-[9px] text-dim mb-3">
              Optional login credentials for crawlers.
              {!isNewRepo && ' Values are never echoed back from the server.'}
            </div>

            {/* Auth Type Selector */}
            <div className="mb-4">
              <label
                htmlFor="repo-auth-type"
                className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-2"
              >
                Authentication Type
              </label>
              <select
                id="repo-auth-type"
                value={auth.authType}
                onChange={e =>
                  setAuth(prev => ({
                    ...prev,
                    authType: e.target.value as 'form' | 'header',
                  }))
                }
                className="w-48 h-8 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none"
              >
                <option value="form">Form Login</option>
                <option value="header">Header-Based</option>
              </select>
            </div>

            {/* Form-based auth fields */}
            {auth.authType === 'form' && (
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label
                    htmlFor="repo-auth-login-url"
                    className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
                  >
                    Login URL
                  </label>
                  <input
                    id="repo-auth-login-url"
                    type="text"
                    value={auth.loginUrl}
                    onChange={e =>
                      setAuth(a => ({
                        ...a,
                        loginUrl: e.target.value,
                      }))
                    }
                    placeholder={
                      !isNewRepo && selectedRepo?.authConfigured
                        ? 'Stored — enter new value to override'
                        : 'https://example.com/login'
                    }
                    className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground font-mono focus:border-accent focus:outline-none"
                  />
                </div>
                <div>
                  <label
                    htmlFor="repo-auth-username"
                    className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
                  >
                    Username
                  </label>
                  <input
                    id="repo-auth-username"
                    type="text"
                    autoComplete="off"
                    value={auth.username}
                    onChange={e =>
                      setAuth(a => ({
                        ...a,
                        username: e.target.value,
                      }))
                    }
                    placeholder={
                      !isNewRepo && selectedRepo?.authConfigured
                        ? 'Stored — enter new value to override'
                        : undefined
                    }
                    className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none"
                  />
                </div>
                <div>
                  <label
                    htmlFor="repo-auth-password"
                    className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
                  >
                    Password
                  </label>
                  <input
                    id="repo-auth-password"
                    type="password"
                    autoComplete="new-password"
                    value={auth.password}
                    onChange={e =>
                      setAuth(a => ({
                        ...a,
                        password: e.target.value,
                      }))
                    }
                    placeholder={
                      !isNewRepo && selectedRepo?.authConfigured
                        ? 'Stored — enter new value to override'
                        : undefined
                    }
                    className="w-full h-8 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none"
                  />
                </div>
              </div>
            )}

            {/* Header-based auth fields */}
            {auth.authType === 'header' && (
              <div>
                {auth.authHeaders.map((entry, idx) => (
                  <div key={idx} className="flex gap-2 mb-2">
                    <input
                      placeholder="Header name (e.g., Authorization)"
                      value={entry.header}
                      onChange={e => {
                        const updated = [...auth.authHeaders]
                        updated[idx] = { ...entry, header: e.target.value }
                        setAuth(prev => ({ ...prev, authHeaders: updated }))
                      }}
                      className="flex-1 h-8 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none"
                    />
                    <input
                      placeholder="Value"
                      type="text"
                      value={entry.value}
                      onChange={e => {
                        const updated = [...auth.authHeaders]
                        updated[idx] = { ...entry, value: e.target.value }
                        setAuth(prev => ({ ...prev, authHeaders: updated }))
                      }}
                      className="flex-1 h-8 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none"
                    />
                    <input
                      placeholder="Env var (optional)"
                      type="text"
                      value={entry.valueEnv}
                      onChange={e => {
                        const updated = [...auth.authHeaders]
                        updated[idx] = { ...entry, valueEnv: e.target.value }
                        setAuth(prev => ({ ...prev, authHeaders: updated }))
                      }}
                      className="w-36 h-8 px-2 bg-background border border-border text-xs text-foreground focus:border-accent focus:outline-none"
                    />
                    <button
                      onClick={() => {
                        const updated = auth.authHeaders.filter((_, i) => i !== idx)
                        setAuth(prev => ({ ...prev, authHeaders: updated }))
                      }}
                      className="px-2 h-8 border border-crit text-crit hover:bg-crit/10 text-[10px] uppercase tracking-wider transition-colors"
                    >
                      Remove
                    </button>
                  </div>
                ))}
                <button
                  onClick={() => {
                    setAuth(prev => ({
                      ...prev,
                      authHeaders: [...prev.authHeaders, { header: '', value: '', valueEnv: '' }],
                    }))
                  }}
                  className="flex items-center gap-1 px-3 h-8 text-[10px] uppercase tracking-wider border border-border text-muted-foreground hover:bg-muted/30 transition-colors"
                >
                  <Plus className="h-3 w-3" />
                  Add Header
                </button>
              </div>
            )}

            {!isNewRepo && (
              <div className="flex items-center justify-end gap-2 mt-4">
                {authJustSaved && (
                  <span className="text-[10px] text-accent flex items-center gap-1">
                    <Check className="h-3 w-3" />
                    Saved
                  </span>
                )}
                <button
                  onClick={handleSaveAuth}
                  disabled={
                    isSavingAuth ||
                    (auth.authType === 'form' && !auth.loginUrl) ||
                    (auth.authType === 'header' &&
                      auth.authHeaders.filter(h => h.header).length === 0)
                  }
                  className={cn(
                    'flex items-center gap-1 px-3 h-8 text-[10px] uppercase tracking-wider transition-colors',
                    (auth.authType === 'form' && auth.loginUrl) ||
                      (auth.authType === 'header' &&
                        auth.authHeaders.filter(h => h.header).length > 0)
                      ? 'bg-accent text-background hover:bg-accent/80 hover:shadow-[0_0_8px_rgba(57,255,20,0.15)]'
                      : 'bg-muted text-dim opacity-40 cursor-not-allowed'
                  )}
                >
                  <Save className="h-3 w-3" />
                  {isSavingAuth ? 'Saving...' : 'Save Auth'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </Panel>
  )
}
