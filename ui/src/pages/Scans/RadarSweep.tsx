export function RadarSweep({ active, size = 200 }: { active: boolean; size?: number }) {
  const r = size / 2 - 10
  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className="shrink-0"
      aria-hidden
    >
      {/* Background circles */}
      {[0.25, 0.5, 0.75, 1].map(frac => (
        <circle
          key={frac}
          cx={size / 2}
          cy={size / 2}
          r={r * frac}
          fill="none"
          stroke="var(--color-border)"
          strokeWidth={1}
        />
      ))}
      {/* Cross-hairs */}
      <line
        x1={size / 2}
        y1={10}
        x2={size / 2}
        y2={size - 10}
        stroke="var(--color-border)"
        strokeWidth={1}
      />
      <line
        x1={10}
        y1={size / 2}
        x2={size - 10}
        y2={size / 2}
        stroke="var(--color-border)"
        strokeWidth={1}
      />
      {/* Corner brackets */}
      <g stroke="var(--color-accent)" strokeWidth={2} fill="none">
        <path d={`M 15 5 L 5 5 L 5 15`} />
        <path d={`M ${size - 15} 5 L ${size - 5} 5 L ${size - 5} 15`} />
        <path d={`M 15 ${size - 5} L 5 ${size - 5} L 5 ${size - 15}`} />
        <path
          d={`M ${size - 15} ${size - 5} L ${size - 5} ${size - 5} L ${size - 5} ${size - 15}`}
        />
      </g>
      {/* Sweep arm + glow */}
      {active && (
        <g className="origin-center" style={{ transformOrigin: `${size / 2}px ${size / 2}px` }}>
          <defs>
            <linearGradient id="sweepGrad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="var(--color-accent)" stopOpacity="0" />
              <stop offset="100%" stopColor="var(--color-accent)" stopOpacity="0.7" />
            </linearGradient>
          </defs>
          <g className="animate-radar-sweep">
            {/* Sweep wedge */}
            <path
              d={`M ${size / 2} ${size / 2} L ${size / 2} ${10} A ${r} ${r} 0 0 1 ${size / 2 + r * Math.sin(Math.PI / 6)} ${size / 2 - r * Math.cos(Math.PI / 6)} Z`}
              fill="url(#sweepGrad)"
            />
            {/* Line */}
            <line
              x1={size / 2}
              y1={size / 2}
              x2={size / 2}
              y2={10}
              stroke="var(--color-accent)"
              strokeWidth={2}
              className="tty-glow"
            />
          </g>
        </g>
      )}
      {/* Center dot */}
      <circle
        cx={size / 2}
        cy={size / 2}
        r={3}
        fill="var(--color-accent)"
        className={active ? 'tty-glow' : ''}
      />
    </svg>
  )
}
