import { useState, useEffect, useMemo } from 'react'
import { cn } from '@/lib/utils'

export function NeuralGrid({
  active,
  progress,
  size = 200,
}: {
  active: boolean
  progress: number // 0-100
  size?: number
}) {
  const cols = 6
  const rows = 6
  const totalNodes = cols * rows
  const nodeRadius = 6
  const spacing = size / (cols + 1)

  // Calculate how many nodes should be "processed" based on progress
  const processedCount = Math.floor((progress / 100) * totalNodes)

  // Generate node positions
  const nodes = useMemo(() => {
    const result: { x: number; y: number; id: number }[] = []
    for (let row = 0; row < rows; row++) {
      for (let col = 0; col < cols; col++) {
        result.push({
          id: row * cols + col,
          x: spacing * (col + 1),
          y: spacing * (row + 1),
        })
      }
    }
    return result
  }, [spacing])

  // Generate connecting lines (horizontal and vertical neighbors)
  const lines = useMemo(() => {
    const result: { x1: number; y1: number; x2: number; y2: number; id: string }[] = []
    for (let row = 0; row < rows; row++) {
      for (let col = 0; col < cols; col++) {
        const idx = row * cols + col
        // Right neighbor
        if (col < cols - 1) {
          result.push({
            id: `h-${idx}`,
            x1: nodes[idx].x,
            y1: nodes[idx].y,
            x2: nodes[idx + 1].x,
            y2: nodes[idx + 1].y,
          })
        }
        // Bottom neighbor
        if (row < rows - 1) {
          result.push({
            id: `v-${idx}`,
            x1: nodes[idx].x,
            y1: nodes[idx].y,
            x2: nodes[idx + cols].x,
            y2: nodes[idx + cols].y,
          })
        }
      }
    }
    return result
  }, [nodes])

  // Active pulse node (cycles through unprocessed nodes when running)
  const [pulseIdx, setPulseIdx] = useState(0)
  useEffect(() => {
    if (!active) return
    const interval = setInterval(() => {
      setPulseIdx(i => (i + 1) % totalNodes)
    }, 150)
    return () => clearInterval(interval)
  }, [active, totalNodes])

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className="shrink-0"
      aria-hidden
    >
      {/* Background frame */}
      <rect
        x={4}
        y={4}
        width={size - 8}
        height={size - 8}
        fill="none"
        stroke="var(--color-border)"
        strokeWidth={1}
      />
      {/* Corner brackets */}
      <g stroke="var(--color-accent)" strokeWidth={2} fill="none">
        <path d={`M 12 4 L 4 4 L 4 12`} />
        <path d={`M ${size - 12} 4 L ${size - 4} 4 L ${size - 4} 12`} />
        <path d={`M 12 ${size - 4} L 4 ${size - 4} L 4 ${size - 12}`} />
        <path
          d={`M ${size - 12} ${size - 4} L ${size - 4} ${size - 4} L ${size - 4} ${size - 12}`}
        />
      </g>

      {/* Connecting lines */}
      {lines.map(line => {
        // Line is "active" if both endpoints are processed
        const startIdx = nodes.findIndex(n => n.x === line.x1 && n.y === line.y1)
        const endIdx = nodes.findIndex(n => n.x === line.x2 && n.y === line.y2)
        const lineActive = startIdx < processedCount && endIdx < processedCount
        return (
          <line
            key={line.id}
            x1={line.x1}
            y1={line.y1}
            x2={line.x2}
            y2={line.y2}
            stroke={lineActive ? 'var(--color-accent)' : 'var(--color-border)'}
            strokeWidth={lineActive ? 1.5 : 0.5}
            opacity={lineActive ? 0.8 : 0.3}
            className={lineActive ? 'transition-all duration-300' : ''}
          />
        )
      })}

      {/* Nodes */}
      {nodes.map(node => {
        const isProcessed = node.id < processedCount
        const isPulse = active && node.id === pulseIdx && !isProcessed
        return (
          <g key={node.id}>
            {/* Glow effect for pulse */}
            {isPulse && (
              <circle
                cx={node.x}
                cy={node.y}
                r={nodeRadius + 4}
                fill="var(--color-accent)"
                opacity={0.3}
                className="animate-pulse"
              />
            )}
            {/* Node circle */}
            <circle
              cx={node.x}
              cy={node.y}
              r={nodeRadius}
              fill={isProcessed ? 'var(--color-accent)' : 'var(--color-background)'}
              stroke={isProcessed || isPulse ? 'var(--color-accent)' : 'var(--color-border)'}
              strokeWidth={isPulse ? 2 : 1}
              className={cn('transition-all duration-200', isProcessed && 'tty-glow')}
            />
            {/* Checkmark for processed */}
            {isProcessed && (
              <text
                x={node.x}
                y={node.y + 1}
                textAnchor="middle"
                dominantBaseline="middle"
                fontSize={8}
                fill="var(--color-background)"
                fontWeight="bold"
              >
                ✓
              </text>
            )}
          </g>
        )
      })}

      {/* Center brain icon area when idle */}
      {!active && progress === 0 && (
        <g opacity={0.4}>
          <circle cx={size / 2} cy={size / 2} r={30} fill="var(--color-muted)" />
          <text
            x={size / 2}
            y={size / 2 + 2}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize={24}
            fill="var(--color-dim)"
          >
            AI
          </text>
        </g>
      )}
    </svg>
  )
}
