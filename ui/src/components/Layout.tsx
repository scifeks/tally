import { Outlet, useLocation } from "react-router-dom"
import { TopBar } from "./TopBar"

export function Layout() {
  const loc = useLocation()
  const path = loc.pathname === "/" ? "/dashboard" : loc.pathname
  const now = new Date()
  const stamp = now.toLocaleString("en-US", { hour12: false })

  return (
    <div className="h-screen flex flex-col bg-background text-foreground">
      <TopBar />
      <main className="flex-1 min-h-0 overflow-hidden">
        <Outlet />
      </main>
      <footer className="border-t border-border bg-background shrink-0">
        <div className="flex items-center justify-between h-6 px-4 text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
          <div className="flex items-center gap-4">
            <span className="text-dim">tally@console</span>
            <span>{path}</span>
          </div>
          <div className="flex items-center gap-4">
            <span className="hidden md:inline">tty/1</span>
            <span>status: <span className="text-low">ok</span></span>
            <span className="tabular-nums">{stamp}</span>
          </div>
        </div>
      </footer>
    </div>
  )
}
