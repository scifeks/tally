import { useState, useEffect } from 'react'
import { Folder, FileText, ChevronRight, ArrowUp } from 'lucide-react'
import { Modal } from './Modal'
import { useBrowseFilesystem } from '@/lib/api'
import type { FileSystemEntry } from '@/lib/types'

interface PathPickerModalProps {
  open: boolean
  onClose: () => void
  onSelect: (path: string) => void
  initialPath?: string
  title?: string
}

export function PathPickerModal({
  open,
  onClose,
  onSelect,
  initialPath = '/',
  title = 'Select File',
}: PathPickerModalProps) {
  const [currentPath, setCurrentPath] = useState(initialPath)
  const [manualPath, setManualPath] = useState('')

  const { data, isLoading, error } = useBrowseFilesystem(open ? currentPath : '')

  useEffect(() => {
    if (open) {
      setCurrentPath(initialPath)
      setManualPath('')
    }
  }, [open, initialPath])

  const navigateUp = () => {
    const parent = currentPath.split('/').slice(0, -1).join('/')
    setCurrentPath(parent || '/')
  }

  const handleEntryClick = (entry: FileSystemEntry) => {
    if (entry.isDir) {
      setCurrentPath(entry.path)
    } else {
      onSelect(entry.path)
      onClose()
    }
  }

  const handleManualSelect = () => {
    if (manualPath.trim()) {
      onSelect(manualPath.trim())
      onClose()
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={title} width="lg">
      <div className="flex flex-col -m-4">
        {/* Current path + up button */}
        <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
          <button
            onClick={navigateUp}
            disabled={currentPath === '/'}
            className="p-1 hover:bg-muted/30 disabled:opacity-30"
          >
            <ArrowUp className="h-4 w-4" />
          </button>
          <div className="flex-1 text-xs font-mono text-dim truncate">
            {data?.currentPath ?? currentPath}
          </div>
        </div>

        {/* Directory listing */}
        <div className="overflow-y-auto min-h-[300px] max-h-[400px]">
          {isLoading && <div className="p-4 text-xs text-dim text-center">Loading...</div>}
          {error && (
            <div className="p-4 text-xs text-crit text-center">Failed to browse directory</div>
          )}
          {data?.entries.map(entry => (
            <button
              key={entry.path}
              onClick={() => handleEntryClick(entry)}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-muted/30 transition-colors"
            >
              {entry.isDir ? (
                <Folder className="h-4 w-4 text-accent shrink-0" />
              ) : (
                <FileText className="h-4 w-4 text-dim shrink-0" />
              )}
              <span className="text-xs text-foreground truncate flex-1">{entry.name}</span>
              {entry.isDir && <ChevronRight className="h-3 w-3 text-dim shrink-0" />}
              {!entry.isDir && entry.sizeBytes != null && (
                <span className="text-[10px] text-dim shrink-0">
                  {formatBytes(entry.sizeBytes)}
                </span>
              )}
            </button>
          ))}
          {data && data.entries.length === 0 && (
            <div className="p-4 text-xs text-dim text-center">Empty directory</div>
          )}
        </div>

        {/* Manual path input */}
        <div className="border-t border-border px-3 py-2">
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={manualPath}
              onChange={e => setManualPath(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') handleManualSelect()
              }}
              placeholder="Or type a path manually..."
              className="flex-1 h-7 px-2 bg-background border border-border text-xs text-foreground font-mono focus:border-accent focus:outline-none"
            />
            <button
              onClick={handleManualSelect}
              disabled={!manualPath.trim()}
              className="px-3 h-7 text-[10px] uppercase tracking-wider bg-accent text-background hover:bg-accent/70 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Select
            </button>
          </div>
        </div>
      </div>
    </Modal>
  )
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
