import { useRef, useState } from 'react'
import { FileText, Upload, Trash2, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Panel } from '@/components/tty'
import { SectionHeader } from './shared'
import { useDocuments, useUploadDocument, useDeleteDocument } from '@/lib/api'
import type { DocumentSource } from '@/lib/types'

const ACCEPTED_EXTENSIONS = '.md,.txt'

export function DocumentsSection({ projectId }: { projectId: number }) {
  const { data: documents = [], isLoading } = useDocuments(projectId)
  const uploadDoc = useUploadDocument()
  const deleteDoc = useDeleteDocument()
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    uploadDoc.mutate(
      { projectId, file },
      {
        onSettled: () => {
          if (fileInputRef.current) fileInputRef.current.value = ''
        },
      }
    )
  }

  const handleDelete = (filename: string) => {
    deleteDoc.mutate(
      { projectId, filename },
      {
        onSettled: () => setConfirmDelete(null),
      }
    )
  }

  return (
    <Panel>
      <SectionHeader icon={FileText} title="DOCUMENTS">
        <label
          className={cn(
            'flex items-center gap-2 px-3 py-1 border text-[10px] uppercase tracking-wider font-bold cursor-pointer transition-colors',
            uploadDoc.isPending
              ? 'opacity-50 cursor-not-allowed border-muted text-muted-foreground'
              : 'border-accent text-accent hover:bg-accent/10'
          )}
        >
          {uploadDoc.isPending ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <Upload className="h-3 w-3" />
          )}
          Upload
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_EXTENSIONS}
            onChange={handleFileChange}
            disabled={uploadDoc.isPending}
            className="hidden"
          />
        </label>
      </SectionHeader>

      {isLoading ? (
        <div className="text-sm text-dim py-8 text-center">Loading documents...</div>
      ) : documents.length === 0 ? (
        <div className="text-[11px] text-dim py-6 text-center">
          No documents uploaded. Upload .md or .txt files to add RAG context for chat.
        </div>
      ) : (
        <div className="space-y-1">
          {documents.map((doc: DocumentSource) => (
            <div
              key={doc.name}
              className="flex items-center justify-between px-3 py-2 border-b border-border last:border-b-0"
            >
              <div className="flex items-center gap-2 min-w-0">
                <FileText className="h-3 w-3 text-muted-foreground shrink-0" />
                <span className="text-[11px] text-foreground truncate">{doc.name}</span>
                <span className="text-[9px] text-dim shrink-0">{doc.chunks} chunks</span>
              </div>
              {confirmDelete === doc.name ? (
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => handleDelete(doc.name)}
                    disabled={deleteDoc.isPending}
                    className="px-2 py-0.5 text-[9px] uppercase tracking-wider font-bold bg-crit/20 border border-crit text-crit hover:bg-crit/30 disabled:opacity-50"
                  >
                    Confirm
                  </button>
                  <button
                    onClick={() => setConfirmDelete(null)}
                    className="px-2 py-0.5 text-[9px] uppercase tracking-wider text-muted-foreground hover:text-foreground"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setConfirmDelete(doc.name)}
                  className="p-1 hover:bg-crit/20 hover:text-crit transition-all text-muted-foreground"
                  title="Remove document"
                  aria-label={`remove ${doc.name}`}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </Panel>
  )
}
