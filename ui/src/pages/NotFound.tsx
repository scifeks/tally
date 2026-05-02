import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Panel } from '@/components/tty'
import { Home } from 'lucide-react'

const GLITCH_CHARS = '!@#$%^&*()_+-=[]{}|;:,.<>?/~`'
const ERROR_LINES = [
  'FATAL: route not found in navigation matrix',
  'ERRNO: 0x194 (404)',
  'STACK: ./routes/resolver.ts:42',
  '       ./core/dispatch.ts:118',
  '       ./main.ts:7',
  '',
  '// The requested path does not exist.',
  '// Check the URL or return to a known route.',
]

function GlitchText({ text, isGlitching }: { text: string; isGlitching: boolean }) {
  const [display, setDisplay] = useState(text)

  useEffect(() => {
    if (!isGlitching) {
      setDisplay(text)
      return
    }

    const interval = setInterval(() => {
      setDisplay(
        text
          .split('')
          .map(char =>
            char === ' '
              ? ' '
              : Math.random() > 0.7
                ? GLITCH_CHARS[Math.floor(Math.random() * GLITCH_CHARS.length)]
                : char
          )
          .join('')
      )
    }, 50)

    return () => clearInterval(interval)
  }, [text, isGlitching])

  return <span>{display}</span>
}

export default function NotFound() {
  const [visibleLines, setVisibleLines] = useState<number>(0)
  const [isGlitching, setIsGlitching] = useState(true)
  const [showCursor, setShowCursor] = useState(true)

  useEffect(() => {
    if (visibleLines < ERROR_LINES.length) {
      const timeout = setTimeout(() => {
        setVisibleLines(v => v + 1)
      }, 120)
      return () => clearTimeout(timeout)
    } else {
      const timeout = setTimeout(() => setIsGlitching(false), 500)
      return () => clearTimeout(timeout)
    }
  }, [visibleLines])

  useEffect(() => {
    const interval = setInterval(() => setShowCursor(v => !v), 530)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="h-full p-4 flex items-center justify-center">
      <Panel title="system error" className="w-full max-w-2xl">
        <div className="p-6 space-y-6">
          <div className="text-crit font-bold text-center leading-none overflow-hidden">
            <pre className="inline-block text-[10px] sm:text-xs">
              {`
 ██╗  ██╗ ██████╗ ██╗  ██╗
 ██║  ██║██╔═══██╗██║  ██║
 ███████║██║   ██║███████║
 ╚════██║██║   ██║╚════██║
      ██║╚██████╔╝     ██║
      ╚═╝ ╚═════╝      ╚═╝
`}
            </pre>
          </div>

          <div className="border border-border bg-muted/30 p-4 font-mono text-xs space-y-1">
            {ERROR_LINES.slice(0, visibleLines).map((line, i) => (
              <div
                key={i}
                className={
                  line.startsWith('FATAL')
                    ? 'text-crit'
                    : line.startsWith('ERRNO')
                      ? 'text-high'
                      : line.startsWith('//')
                        ? 'text-dim'
                        : 'text-muted-foreground'
                }
              >
                <GlitchText text={line} isGlitching={isGlitching && i === visibleLines - 1} />
              </div>
            ))}
            {visibleLines < ERROR_LINES.length && (
              <span className={showCursor ? 'text-primary' : 'text-transparent'}>_</span>
            )}
          </div>

          <div className="relative h-1 bg-border overflow-hidden">
            <div className="absolute inset-y-0 w-24 bg-gradient-to-r from-transparent via-crit to-transparent animate-scan" />
          </div>

          <div className="flex items-center justify-center gap-4 pt-2">
            <Link
              to="/"
              className="flex items-center gap-2 px-4 h-9 border border-accent text-accent text-xs uppercase tracking-wider hover:bg-accent/10 transition-colors"
            >
              <Home className="h-4 w-4" />
              Return Home
            </Link>
          </div>

          <div className="text-center text-[10px] uppercase tracking-[0.2em] text-dim">
            <span className="text-muted-foreground">[</span>
            <span className="text-crit">status</span>
            <span className="text-muted-foreground">]</span> route resolution failed
          </div>
        </div>
      </Panel>
    </div>
  )
}
