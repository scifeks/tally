import { Link } from 'react-router-dom'
import { Play, Wrench } from 'lucide-react'
import type { Segment } from '@/lib/types'
import { SEGMENTS } from './constants'

export function EmptyFindingsState({ segment }: { segment: Segment }) {
  const segmentLabel = SEGMENTS.find(s => s.key === segment)?.label ?? segment
  return (
    <div className="flex-1 min-h-0 overflow-auto flex items-start justify-center p-8">
      <div className="w-full max-w-xl border border-border bg-background">
        <div className="border-b border-border px-3 h-8 flex items-center text-xs uppercase tracking-[0.18em] text-primary">
          <span className="text-dim mr-1">[</span>no findings yet
          <span className="text-dim ml-1">]</span>
        </div>
        <div className="p-6 space-y-5 text-xs">
          <div className="text-sm text-foreground leading-relaxed">
            <span className="text-dim">$</span> no{' '}
            <span className="text-accent">{segmentLabel}</span> findings for the active project.
          </div>
          <div className="text-muted-foreground leading-relaxed">
            this can mean one of a few things:
          </div>
          <ul className="space-y-1.5 text-muted-foreground pl-3">
            <li>
              <span className="text-dim">•</span> no scans have been run yet
            </li>
            <li>
              <span className="text-dim">•</span> scans are still running (enrichment can take a
              while)
            </li>
            <li>
              <span className="text-dim">•</span> scans ran clean - nothing to report in this
              segment
            </li>
          </ul>
          <div className="grid grid-cols-2 gap-2 pt-2">
            <Link
              to="/scans"
              className="flex items-center gap-2 border border-accent text-accent px-3 py-2 hover:bg-muted"
            >
              <Play className="h-3.5 w-3.5" />
              <span className="text-[11px] uppercase tracking-[0.18em] font-bold">
                &gt; view scans
              </span>
            </Link>
            <Link
              to="/config/tools"
              className="flex items-center gap-2 border border-border text-foreground px-3 py-2 hover:bg-muted"
            >
              <Wrench className="h-3.5 w-3.5" />
              <span className="text-[11px] uppercase tracking-[0.18em] font-bold">
                configure tools
              </span>
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
