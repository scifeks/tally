import { Panel } from "@/components/tty"

export default function Placeholder({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="h-full p-4">
      <Panel title={title}>
        <div className="p-8 space-y-3 text-xs leading-relaxed max-w-2xl">
          <div className="text-dim">// route stub</div>
          <div className="text-foreground">
            <span className="text-primary tty-cursor">This page is intentionally empty for the prototype.</span>
          </div>
          {hint && (
            <div className="text-muted-foreground pt-2 border-t border-border">
              <span className="text-dim">notes:</span> {hint}
            </div>
          )}
          <div className="pt-4 text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
            status: <span className="text-med">pending implementation</span>
          </div>
        </div>
      </Panel>
    </div>
  )
}
