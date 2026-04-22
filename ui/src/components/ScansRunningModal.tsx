import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Modal, ModalButton } from './Modal'
import { useProjects, useScanHistory } from '@/lib/api'
import { useUI } from '@/lib/store'
import type { Scan } from '@/lib/types'
import { cn, formatRelative } from '@/lib/utils'
import { ArrowRight } from 'lucide-react'

/**
 * TODO [BACKEND]: Replace this simulation with real SSE subscription.
 * Mocks the "live" streaming feel by ticking progress forward on an interval.
 * The real app will replace this with an SSE subscription via useScanEvents().
 */
function useSimulatedProgress(running: Scan[]) {
  const [tick, setTick] = useState(0)
  useEffect(() => {
    if (running.length === 0) return
    const h = window.setInterval(() => setTick(t => t + 1), 1500)
    return () => window.clearInterval(h)
  }, [running.length])
  return tick
}

export function ScansRunningModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const activeProjectId = useUI(s => s.activeProjectId)

  // TODO [BACKEND]: These hooks return mock data. Replace with real API calls.
  const { data: projects = [] } = useProjects()
  const { data: scans = [] } = useScanHistory(activeProjectId)

  const running = scans.filter(s => s.status === 'running')
  const tick = useSimulatedProgress(running)

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`scans running :: ${running.length}`}
      width="lg"
      footer={
        <>
          <ModalButton onClick={onClose}>close</ModalButton>
          <Link
            to="/scans"
            onClick={onClose}
            className="inline-flex items-center gap-1 px-3 h-7 border border-accent text-accent hover:bg-muted text-[11px] uppercase tracking-[0.18em] font-bold"
          >
            open scans <ArrowRight className="h-3 w-3" />
          </Link>
        </>
      }
    >
      {running.length === 0 ? (
        <div className="text-muted-foreground py-6 text-center">
          <div className="text-dim mb-1">{'// no scans are currently running'}</div>
          <div>system idle.</div>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="text-[11px] text-muted-foreground leading-relaxed">
            <span className="text-dim">{'//'}</span> streaming segment progress via websocket.
            long-running ingestion + enrichment phases are normal.
          </div>
          {running.map(s => {
            const project = projects.find(p => p.id === s.projectId)
            // Simulate forward progress until 95% — real data will come from WS.
            const base = s.progress ?? 0
            const simulated = Math.min(95, base + ((tick * 2) % 20))
            return (
              <div key={s.id} className="border border-border bg-background">
                <div className="flex items-center gap-3 px-3 h-8 border-b border-border">
                  <span className="text-dim tabular-nums text-[11px]">{s.id}</span>
                  <span className="text-[11px] text-primary font-bold tty-glow">
                    {project?.code ?? '—'}
                  </span>
                  <span className="text-[11px] text-foreground truncate">{project?.name}</span>
                  <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                    {s.segment} · {s.tool}
                  </span>
                  <span className="ml-auto text-[10px] text-dim tabular-nums">
                    started {formatRelative(s.startedAt)}
                  </span>
                </div>
                <div className="p-3 space-y-2">
                  <div className="flex items-baseline justify-between">
                    <div className="text-xs text-accent tty-glow">
                      <span className="tty-cursor-inline">&gt;</span>{' '}
                      {s.currentSegment ?? 'working'}
                    </div>
                    <div className="text-[11px] text-muted-foreground tabular-nums">
                      {s.segmentLabel}
                    </div>
                  </div>
                  <ProgressBar value={simulated} />
                  <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-muted-foreground">
                    <span>
                      progress{' '}
                      <span className="text-accent tabular-nums">{simulated.toFixed(0)}%</span>
                    </span>
                    <span className="text-dim">ws://tally/scans/{s.id}</span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </Modal>
  )
}

function ProgressBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, value))
  return (
    <div className="relative h-2 w-full border border-border bg-muted overflow-hidden">
      <div
        className={cn('h-full bg-accent transition-[width] duration-500 ease-linear')}
        style={{ width: `${pct}%` }}
      />
      {/* Scanline sweep to reinforce the live feel */}
      <div
        className="absolute inset-y-0 w-6 bg-gradient-to-r from-transparent via-[rgba(57,255,20,0.35)] to-transparent animate-[scan-sweep_1.4s_linear_infinite]"
        style={{ left: `${pct}%`, transform: 'translateX(-100%)' }}
        aria-hidden
      />
      <style>{`@keyframes scan-sweep {
        0% { transform: translateX(-120%); }
        100% { transform: translateX(20%); }
      }`}</style>
    </div>
  )
}
