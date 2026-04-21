export function PrinterAnimation({
  active,
  progress,
  size = 220,
}: {
  active: boolean
  progress: number
  size?: number
}) {
  const pageCount = 6
  const pagesComplete = Math.floor((progress / 100) * pageCount)

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 220 220"
      className="shrink-0"
      aria-hidden
    >
      {/* Corner brackets */}
      <g stroke="var(--color-accent)" strokeWidth={2} fill="none">
        <path d="M 15 5 L 5 5 L 5 15" />
        <path d="M 205 5 L 215 5 L 215 15" />
        <path d="M 15 215 L 5 215 L 5 205" />
        <path d="M 205 215 L 215 215 L 215 205" />
      </g>

      {/* Outer frame */}
      <rect
        x="30"
        y="50"
        width="160"
        height="120"
        fill="none"
        stroke="var(--color-border)"
        strokeWidth="2"
        rx="4"
      />

      {/* Paper tray (input) */}
      <rect
        x="60"
        y="30"
        width="100"
        height="25"
        fill="var(--color-muted)"
        stroke="var(--color-border)"
        strokeWidth="1"
        rx="2"
      />

      {/* Document stack in tray */}
      {[0, 1, 2].map((i) => (
        <rect
          key={i}
          x={65 + i * 2}
          y={35 + i * 2}
          width={86 - i * 4}
          height={15}
          fill="var(--color-background)"
          stroke="var(--color-dim)"
          strokeWidth="0.5"
        />
      ))}

      {/* Printer body */}
      <rect
        x="40"
        y="60"
        width="140"
        height="70"
        fill="var(--color-muted)"
        stroke="var(--color-border)"
        strokeWidth="1"
        rx="2"
      />

      {/* Status lights */}
      <circle
        cx="60"
        cy="75"
        r="4"
        fill={active ? "var(--color-accent)" : "var(--color-dim)"}
        className={active ? "tty-glow" : ""}
      />
      <circle
        cx="75"
        cy="75"
        r="4"
        fill={active ? "var(--color-warn)" : "var(--color-dim)"}
        className={active ? "animate-pulse" : ""}
      />

      {/* LCD display area */}
      <rect
        x="90"
        y="68"
        width="80"
        height="16"
        fill="var(--color-background)"
        stroke="var(--color-border)"
        strokeWidth="1"
      />
      <text
        x="130"
        y="80"
        textAnchor="middle"
        fill="var(--color-accent)"
        fontSize="8"
        fontFamily="monospace"
        className={active ? "tty-glow" : ""}
      >
        {active ? `PRINTING ${progress}%` : "READY"}
      </text>

      {/* Paper output slot */}
      <rect
        x="60"
        y="125"
        width="100"
        height="8"
        fill="var(--color-background)"
        stroke="var(--color-border)"
        strokeWidth="1"
      />

      {/* Output tray */}
      <path
        d="M 55 170 L 60 135 L 160 135 L 165 170 Z"
        fill="var(--color-muted)"
        stroke="var(--color-border)"
        strokeWidth="1"
      />

      {/* Printed pages in output tray */}
      {Array.from({ length: pagesComplete }).map((_, i) => (
        <g key={i}>
          <rect
            x={65 + i * 1.5}
            y={140 + i * 3}
            width={90 - i * 3}
            height={25}
            fill="var(--color-background)"
            stroke="var(--color-accent)"
            strokeWidth="0.5"
            className="tty-glow"
          />
          {[0, 1, 2].map((line) => (
            <line
              key={line}
              x1={70 + i * 1.5}
              y1={148 + i * 3 + line * 5}
              x2={145 - i * 3}
              y2={148 + i * 3 + line * 5}
              stroke="var(--color-dim)"
              strokeWidth="0.5"
            />
          ))}
        </g>
      ))}

      {/* Currently printing page (animated) */}
      {active && pagesComplete < pageCount && (
        <g className="animate-pulse">
          <rect
            x="70"
            y="110"
            width="80"
            height="20"
            fill="var(--color-background)"
            stroke="var(--color-accent)"
            strokeWidth="1"
          />
        </g>
      )}
    </svg>
  )
}
