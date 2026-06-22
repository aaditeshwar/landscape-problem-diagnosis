type Props = {
  title: string
  distribution: Array<{ label: string; percent: number }>
  sampleCount?: number
  unit?: string
}

export function CategoryBarChart({ title, distribution, sampleCount, unit }: Props) {
  const width = 320
  const height = 160
  const pad = { top: 10, right: 8, bottom: 48, left: 8 }
  const innerW = width - pad.left - pad.right
  const innerH = height - pad.top - pad.bottom

  if (!distribution.length) {
    return (
      <div className="rounded border border-stone-200 bg-white p-2 text-[11px] text-stone-500">
        {title}: no data
      </div>
    )
  }

  const maxPct = Math.max(...distribution.map((d) => d.percent), 1)
  const barGap = 4
  const barW = Math.max(12, (innerW - barGap * (distribution.length - 1)) / distribution.length)

  return (
    <div className="rounded border border-stone-200 bg-white p-2">
      <div className="mb-1 truncate text-[11px] font-medium text-stone-800" title={title}>
        {title}
        {unit ? <span className="ml-1 font-normal text-stone-400">({unit})</span> : null}
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="img" aria-label={`Distribution of ${title}`}>
        <line x1={pad.left} y1={pad.top + innerH} x2={pad.left + innerW} y2={pad.top + innerH} stroke="#d6d3d1" />
        {[0, 25, 50, 75, 100].map((pct) => {
          const y = pad.top + innerH - (pct / 100) * innerH
          return (
            <g key={pct}>
              <line x1={pad.left} x2={pad.left + innerW} y1={y} y2={y} stroke="#f5f5f4" />
              <text x={pad.left + innerW + 2} y={y + 3} fontSize="7" fill="#d6d3d1">
                {pct}%
              </text>
            </g>
          )
        })}
        {distribution.map((item, idx) => {
          const barH = (item.percent / maxPct) * innerH
          const x = pad.left + idx * (barW + barGap)
          const y = pad.top + innerH - barH
          const label =
            item.label.length > 10 ? `${item.label.slice(0, 9)}…` : item.label
          return (
            <g key={item.label}>
              <rect x={x} y={y} width={barW} height={barH} fill="#b45309" opacity={0.85} rx={1} />
              <text x={x + barW / 2} y={y - 2} textAnchor="middle" fontSize="7" fill="#78716c">
                {item.percent.toFixed(0)}%
              </text>
              <text
                x={x + barW / 2}
                y={pad.top + innerH + 10}
                textAnchor="end"
                fontSize="7"
                fill="#57534e"
                transform={`rotate(-35 ${x + barW / 2} ${pad.top + innerH + 10})`}
              >
                {label}
              </text>
            </g>
          )
        })}
      </svg>
      {sampleCount != null ? (
        <div className="mt-1 text-[10px] text-stone-600">Samples: {sampleCount}</div>
      ) : null}
    </div>
  )
}
