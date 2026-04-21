// ─── Animated Graphic ─────────────────────────────────────────────────────────
// Circuit board / settings panel animation for config page
// Same dimensions (180px) and positioning pattern as Scans/Triage/Reports

export function ConfigPanel({ active, size = 180 }: { active?: boolean; size?: number }) {
  const gearConfigs = [
    { cx: size * 0.35, cy: size * 0.35, r: size * 0.18, teeth: 10, speed: 8 },
    { cx: size * 0.65, cy: size * 0.55, r: size * 0.14, teeth: 8, speed: -6 },
    { cx: size * 0.35, cy: size * 0.7, r: size * 0.10, teeth: 6, speed: 10 },
  ]

  const buildGearPath = (cx: number, cy: number, r: number, teeth: number) => {
    const toothH = r * 0.25
    const pts: string[] = []
    for (let i = 0; i < teeth; i++) {
      const a1 = (i / teeth) * Math.PI * 2
      const a2 = ((i + 0.3) / teeth) * Math.PI * 2
      const a3 = ((i + 0.5) / teeth) * Math.PI * 2
      const a4 = ((i + 0.8) / teeth) * Math.PI * 2

      pts.push(`${cx + Math.cos(a1) * r},${cy + Math.sin(a1) * r}`)
      pts.push(`${cx + Math.cos(a2) * (r + toothH)},${cy + Math.sin(a2) * (r + toothH)}`)
      pts.push(`${cx + Math.cos(a3) * (r + toothH)},${cy + Math.sin(a3) * (r + toothH)}`)
      pts.push(`${cx + Math.cos(a4) * r},${cy + Math.sin(a4) * r}`)
    }
    return `M ${pts.join(" L ")} Z`
  }

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className="shrink-0"
      aria-hidden
    >
      <g stroke="var(--color-accent)" strokeWidth={2} fill="none">
        <path d={`M 15 5 L 5 5 L 5 15`} />
        <path d={`M ${size - 15} 5 L ${size - 5} 5 L ${size - 5} 15`} />
        <path d={`M 15 ${size - 5} L 5 ${size - 5} L 5 ${size - 15}`} />
        <path d={`M ${size - 15} ${size - 5} L ${size - 5} ${size - 5} L ${size - 5} ${size - 15}`} />
      </g>

      <g stroke="var(--color-border)" strokeWidth={0.5} opacity={0.3}>
        {[0.25, 0.5, 0.75].map((frac) => (
          <line key={`h-${frac}`} x1={10} y1={size * frac} x2={size - 10} y2={size * frac} />
        ))}
        {[0.25, 0.5, 0.75].map((frac) => (
          <line key={`v-${frac}`} x1={size * frac} y1={10} x2={size * frac} y2={size - 10} />
        ))}
      </g>

      <g stroke="var(--color-dim)" strokeWidth={1} strokeDasharray="4 2" opacity={0.4}>
        <line x1={gearConfigs[0].cx} y1={gearConfigs[0].cy} x2={gearConfigs[1].cx} y2={gearConfigs[1].cy} />
        <line x1={gearConfigs[0].cx} y1={gearConfigs[0].cy} x2={gearConfigs[2].cx} y2={gearConfigs[2].cy} />
        <line x1={gearConfigs[1].cx} y1={gearConfigs[1].cy} x2={gearConfigs[2].cx} y2={gearConfigs[2].cy} />
      </g>

      {gearConfigs.map((gear, idx) => (
        <g
          key={idx}
          style={{
            transformOrigin: `${gear.cx}px ${gear.cy}px`,
            animation: active ? `spin ${Math.abs(gear.speed)}s linear infinite ${gear.speed < 0 ? 'reverse' : 'normal'}` : undefined,
          }}
        >
          <path
            d={buildGearPath(gear.cx, gear.cy, gear.r, gear.teeth)}
            fill="none"
            stroke="var(--color-accent)"
            strokeWidth={1.5}
            opacity={0.7}
          />
          <circle
            cx={gear.cx}
            cy={gear.cy}
            r={gear.r * 0.4}
            fill="none"
            stroke="var(--color-accent)"
            strokeWidth={1}
            opacity={0.5}
          />
          <circle
            cx={gear.cx}
            cy={gear.cy}
            r={3}
            fill="var(--color-accent)"
            className={active ? "tty-glow" : ""}
          />
        </g>
      ))}

      {active && (
        <g>
          {[0, 1, 2].map((i) => (
            <circle
              key={i}
              r={2}
              fill="var(--color-accent)"
              opacity={0.8}
              className="tty-glow"
            >
              <animateMotion
                dur={`${2 + i * 0.5}s`}
                repeatCount="indefinite"
                path={`M ${gearConfigs[0].cx} ${gearConfigs[0].cy} L ${gearConfigs[(i + 1) % 3].cx} ${gearConfigs[(i + 1) % 3].cy}`}
              />
            </circle>
          ))}
        </g>
      )}

      <rect
        x={size * 0.7}
        y={size * 0.12}
        width={size * 0.22}
        height={size * 0.18}
        fill="none"
        stroke="var(--color-border)"
        strokeWidth={1}
      />
      <text
        x={size * 0.81}
        y={size * 0.18}
        textAnchor="middle"
        fontSize={8}
        fill="var(--color-dim)"
        fontFamily="monospace"
      >
        CONFIG
      </text>
      <circle
        cx={size * 0.81}
        cy={size * 0.25}
        r={4}
        fill={active ? "var(--color-low)" : "var(--color-dim)"}
        className={active ? "tty-glow" : ""}
      />
    </svg>
  )
}
