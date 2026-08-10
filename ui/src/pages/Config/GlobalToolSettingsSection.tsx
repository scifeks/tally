import { useState, useEffect } from 'react'
import { Settings, Plus, Trash2, FolderOpen, Save } from 'lucide-react'
import { Panel } from '@/components/tty'
import { PathPickerModal } from '@/components/PathPickerModal'
import { useGlobalToolSettings, useUpdateGlobalToolSettings } from '@/lib/api'
import { SectionHeader } from './shared'

export function GlobalToolSettingsSection() {
  const { data: settings, isLoading } = useGlobalToolSettings()
  const updateSettings = useUpdateGlobalToolSettings()

  const [paths, setPaths] = useState<string[]>([])
  const [isDirty, setIsDirty] = useState(false)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [pickerInitialPath, setPickerInitialPath] = useState('/usr/share')

  useEffect(() => {
    if (settings) {
      setPaths(settings.ffufWordlistPaths)
      setIsDirty(false)
    }
  }, [settings])

  const addPath = (path: string) => {
    if (!paths.includes(path)) {
      setPaths(prev => [...prev, path])
      setIsDirty(true)
    }
  }

  const removePath = (index: number) => {
    setPaths(prev => prev.filter((_, i) => i !== index))
    setIsDirty(true)
  }

  const handleSave = () => {
    updateSettings.mutate({ ffufWordlistPaths: paths })
    setIsDirty(false)
  }

  const openPicker = () => {
    const lastPath = paths[paths.length - 1]
    if (lastPath) {
      const dir = lastPath.split('/').slice(0, -1).join('/')
      setPickerInitialPath(dir || '/')
    }
    setPickerOpen(true)
  }

  if (isLoading) {
    return (
      <Panel>
        <SectionHeader icon={Settings} title="GLOBAL TOOL SETTINGS" />
        <div className="text-sm text-dim py-4 text-center">Loading...</div>
      </Panel>
    )
  }

  return (
    <>
      <Panel bodyClassName="p-4">
        <SectionHeader icon={Settings} title="GLOBAL TOOL SETTINGS" />

        <div className="space-y-3">
          <div>
            <div className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
              ffuf Wordlists
            </div>
            <div className="text-[10px] text-dim mb-3">
              Wordlist files for directory and file discovery. Each wordlist runs as a separate ffuf
              pass against the target.
            </div>
          </div>

          {paths.length === 0 && (
            <div className="text-xs text-dim py-3 text-center border border-dashed border-border">
              No wordlists configured. ffuf will fall back to FFUF_WORDLIST env var or system
              defaults.
            </div>
          )}

          {paths.map((path, i) => (
            <div key={`${path}-${i}`} className="flex items-center gap-2">
              <input
                type="text"
                value={path}
                onChange={e => {
                  const updated = [...paths]
                  updated[i] = e.target.value
                  setPaths(updated)
                  setIsDirty(true)
                }}
                className="flex-1 h-8 px-2 bg-background border border-border text-xs text-foreground font-mono focus:border-accent focus:outline-none"
              />
              <button
                onClick={() => {
                  const dir = path.split('/').slice(0, -1).join('/')
                  setPickerInitialPath(dir || '/')
                  setPickerOpen(true)
                }}
                className="h-8 px-2 border border-border text-muted-foreground hover:border-accent hover:text-accent transition-colors"
                title="Browse"
              >
                <FolderOpen className="h-4 w-4" />
              </button>
              <button
                onClick={() => removePath(i)}
                className="h-8 px-2 border border-crit/50 text-crit hover:bg-crit/10 transition-colors"
                title="Remove"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}

          <button
            onClick={openPicker}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 border border-dashed border-border text-muted-foreground hover:border-accent hover:text-accent transition-colors"
          >
            <Plus className="h-3 w-3" />
            <span className="text-[10px] uppercase tracking-wider">Add Wordlist</span>
          </button>

          {isDirty && (
            <div className="flex justify-end pt-2">
              <button
                onClick={handleSave}
                disabled={updateSettings.isPending}
                className="flex items-center gap-1 px-4 h-8 text-[10px] uppercase tracking-wider bg-accent text-background hover:bg-accent/70"
              >
                <Save className="h-3 w-3" />
                {updateSettings.isPending ? 'Saving...' : 'Save'}
              </button>
            </div>
          )}
        </div>
      </Panel>

      <PathPickerModal
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onSelect={addPath}
        initialPath={pickerInitialPath}
        title="Select Wordlist File"
      />
    </>
  )
}
