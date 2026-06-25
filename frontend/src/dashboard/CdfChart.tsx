import { useMemo, useState, type MouseEvent } from 'react'
import {
  cdfVariantKey,
  type DashboardChartDefaults,
  type CdfVariant,
} from '../api/triage'
import { ExternalLink } from '../components/ExternalLink'

export type CdfSample = { mws_id: string; value: number }

type Props = {
  title: string
  cdfVariants?: Record<string, CdfVariant>
  cdf?: [number, number][]
  samples?: CdfSample[]
  sampleCount?: number
  xMax?: number | null
  unit?: string
  defaults?: DashboardChartDefaults
}

const Y_TICKS = [0, 0.1, 0.2, 0.5, 0.8, 0.9, 0.95, 1]
const TRIM_FRACTION = 0.001
const CDF_CENTILES = 100

type HoverPoint = { x: number; p: number; svgX: number; svgY: number }

function buildCdfFromValues(values: number[], centiles = CDF_CENTILES): [number, number][] {
  if (!values.length) return []
  const ordered = [...values].sort((a, b) => a - b)
  const n = ordered.length
  const steps = Math.max(1, Math.min(centiles, n))
  const points: [number, number][] = []
  for (let i = 1; i <= steps; i += 1) {
    const percentile = Math.round((i / steps) * 1_000_000) / 1_000_000
    const idx = Math.min(n - 1, Math.max(0, Math.ceil(percentile * n) - 1))
    const value = ordered[idx]
    const last = points[points.length - 1]
    if (last && last[0] === value) {
      last[1] = percentile
    } else {
      points.push([value, percentile])
    }
  }
  return points
}

function trimSamples(samples: CdfSample[], trimTop: boolean, trimBottom: boolean) {
  const sorted = [...samples].sort((a, b) => a.value - b.value)
  const n = sorted.length
  const topCut = trimTop ? Math.ceil(n * TRIM_FRACTION) : 0
  const bottomCut = trimBottom ? Math.ceil(n * TRIM_FRACTION) : 0
  const kept = sorted.slice(bottomCut, Math.max(bottomCut, n - topCut))
  return {
    kept,
    removedTop: trimTop ? sorted.slice(n - topCut) : [],
    removedBottom: trimBottom ? sorted.slice(0, bottomCut) : [],
  }
}

function removeZeroSamples(samples: CdfSample[]) {
  const removedZeros = samples.filter((item) => item.value === 0)
  const kept = samples.filter((item) => item.value !== 0)
  return { kept, removedZeros }
}

function axisX(raw: number, logScale: boolean) {
  return logScale ? Math.log1p(raw) : raw
}

function rawFromAxis(axis: number, logScale: boolean) {
  return logScale ? Math.expm1(axis) : axis
}

function nearestCdfPoint(chartCdf: [number, number][], rawX: number): [number, number] {
  if (!chartCdf.length) return [0, 0]
  let best = chartCdf[0]
  let bestDist = Math.abs(best[0] - rawX)
  for (const point of chartCdf) {
    const dist = Math.abs(point[0] - rawX)
    if (dist < bestDist) {
      best = point
      bestDist = dist
    }
  }
  return best
}

function removalPct(count: number, total: number): string {
  if (!total) return '0%'
  return `${Math.round((count / total) * 1000) / 10}%`
}

const MAX_REMOVED_MWS_LINKS = 20

function limitedMwsLinks(items: CdfSample[] | string[], label: string) {
  const ids = items.map((item) => (typeof item === 'string' ? item : item.mws_id))
  const shown = ids.slice(0, MAX_REMOVED_MWS_LINKS)
  const extra = ids.length - shown.length
  return (
    <div>
      {label}:{' '}
      {shown.map((mwsId) => (
        <ExternalLink
          key={`${label}-${mwsId}`}
          to={`/?mws=${encodeURIComponent(mwsId)}`}
          className="mr-1 text-amber-800 hover:underline"
        >
          {mwsId}
        </ExternalLink>
      ))}
      {extra > 0 ? <span className="text-stone-500">…and {extra} more</span> : null}
    </div>
  )
}

function rawTicks(minRaw: number, maxRaw: number, logScale: boolean): number[] {
  if (minRaw === maxRaw) return [minRaw]
  if (logScale) {
    const minAxis = axisX(minRaw, true)
    const maxAxis = axisX(maxRaw, true)
    const midAxis = (minAxis + maxAxis) / 2
    return [minRaw, rawFromAxis(midAxis, true), maxRaw]
  }
  const mid = minRaw + (maxRaw - minRaw) / 2
  return [minRaw, mid, maxRaw]
}

export function CdfChart({
  title,
  cdfVariants,
  cdf = [],
  samples = [],
  sampleCount,
  xMax,
  unit,
  defaults,
}: Props) {
  const [trimTop, setTrimTop] = useState(defaults?.trim_top ?? false)
  const [trimBottom, setTrimBottom] = useState(defaults?.trim_bottom ?? false)
  const [removeZeros, setRemoveZeros] = useState(defaults?.remove_zeros ?? false)
  const [logScale, setLogScale] = useState(defaults?.log_scale ?? false)
  const [hover, setHover] = useState<HoverPoint | null>(null)

  const totalSamples = sampleCount ?? samples.length
  const hasPrecomputed = Boolean(cdfVariants && Object.keys(cdfVariants).length)

  const {
    chartCdf,
    chartMinAxis,
    chartMaxAxis,
    chartXMax,
    removedTop,
    removedBottom,
    removedZeros,
    displayedCount,
    removedTopCount,
    removedBottomCount,
    removedZerosCount,
  } = useMemo(() => {
    if (hasPrecomputed && cdfVariants) {
      const key = cdfVariantKey(trimTop, trimBottom, removeZeros, logScale)
      const variant = cdfVariants[key] ?? cdfVariants['0000']
      const rawCdf = variant?.cdf ?? []
      const rawXs = rawCdf.map(([x]) => x)
      const minRaw = rawXs.length ? Math.min(...rawXs) : 0
      const maxRaw = variant?.x_max ?? xMax ?? (rawXs.length ? Math.max(...rawXs) : 1)
      const removed = variant?.removed
      return {
        chartCdf: rawCdf,
        chartMinAxis: axisX(minRaw, logScale),
        chartMaxAxis: axisX(maxRaw, logScale),
        chartXMax: maxRaw,
        removedTop: removed?.top.mws_ids ?? [],
        removedBottom: removed?.bottom.mws_ids ?? [],
        removedZeros: removed?.zeros.mws_ids ?? [],
        removedTopCount: removed?.top.count ?? 0,
        removedBottomCount: removed?.bottom.count ?? 0,
        removedZerosCount: removed?.zeros.count ?? 0,
        displayedCount: variant?.sample_count ?? totalSamples,
      }
    }

    const needsSampleRebuild = trimTop || trimBottom || removeZeros
    let removedZeroSamples: CdfSample[] = []
    let removedTopSamples: CdfSample[] = []
    let removedBottomSamples: CdfSample[] = []
    let rawCdf: [number, number][] = []
    let shown = totalSamples

    if (needsSampleRebuild && samples.length) {
      let working = samples
      if (removeZeros) {
        const zeroFilter = removeZeroSamples(working)
        working = zeroFilter.kept
        removedZeroSamples = zeroFilter.removedZeros
      }
      const trimmed = trimSamples(working, trimTop, trimBottom)
      removedTopSamples = trimmed.removedTop
      removedBottomSamples = trimmed.removedBottom
      const values = trimmed.kept.map((item) => item.value)
      shown = values.length
      rawCdf = buildCdfFromValues(values)
    } else if (!needsSampleRebuild && cdf.length) {
      rawCdf = cdf
      shown = totalSamples
    } else if (samples.length) {
      const values = samples.map((item) => item.value)
      shown = values.length
      rawCdf = buildCdfFromValues(values)
    } else {
      rawCdf = cdf
      shown = totalSamples
    }

    const rawXs = rawCdf.map(([x]) => x)
    const minRaw = rawXs.length ? Math.min(...rawXs) : 0
    const maxRaw = needsSampleRebuild
      ? rawXs.length
        ? Math.max(...rawXs)
        : 1
      : (xMax ?? (rawXs.length ? Math.max(...rawXs) : 1))

    return {
      chartCdf: rawCdf,
      chartMinAxis: axisX(minRaw, logScale),
      chartMaxAxis: axisX(maxRaw, logScale),
      chartXMax: maxRaw,
      removedTop: removedTopSamples.map((item) => item.mws_id),
      removedBottom: removedBottomSamples.map((item) => item.mws_id),
      removedZeros: removedZeroSamples.map((item) => item.mws_id),
      removedTopCount: removedTopSamples.length,
      removedBottomCount: removedBottomSamples.length,
      removedZerosCount: removedZeroSamples.length,
      displayedCount: shown,
    }
  }, [
    cdf,
    cdfVariants,
    hasPrecomputed,
    logScale,
    removeZeros,
    samples,
    totalSamples,
    trimBottom,
    trimTop,
    xMax,
  ])

  const width = 320
  const height = 160
  const pad = { top: 10, right: 10, bottom: 32, left: 36 }
  const innerW = width - pad.left - pad.right
  const innerH = height - pad.top - pad.bottom

  if (!chartCdf.length) {
    return (
      <div className="rounded border border-stone-200 bg-white p-2 text-[11px] text-stone-500">
        {title}: no data
      </div>
    )
  }

  const span = chartMaxAxis - chartMinAxis || 1
  const toX = (rawValue: number) => pad.left + ((axisX(rawValue, logScale) - chartMinAxis) / span) * innerW
  const toY = (p: number) => pad.top + (1 - p) * innerH
  const fromX = (svgX: number) => {
    const axisVal = chartMinAxis + ((svgX - pad.left) / innerW) * span
    return rawFromAxis(axisVal, logScale)
  }

  const line = chartCdf.map(([x, p], idx) => `${idx === 0 ? 'M' : 'L'} ${toX(x)} ${toY(p)}`).join(' ')

  const formatX = (v: number) => {
    if (Math.abs(v) >= 1000 || (Math.abs(v) < 0.01 && v !== 0)) return v.toExponential(1)
    return Number.isInteger(v) ? String(v) : v.toFixed(2)
  }

  const formatP = (p: number) => `${Math.round(p * 10_000) / 100}%`

  const rawMin = chartCdf[0][0]
  const rawMax = chartCdf[chartCdf.length - 1][0]
  const xTicks = rawTicks(rawMin, chartXMax ?? rawMax, logScale)

  const onChartMouseMove = (event: MouseEvent<SVGRectElement>) => {
    const rect = event.currentTarget.getBoundingClientRect()
    const scaleX = width / rect.width
    const svgX = (event.clientX - rect.left) * scaleX
    if (svgX < pad.left || svgX > pad.left + innerW) {
      setHover(null)
      return
    }
    const [x, p] = nearestCdfPoint(chartCdf, fromX(svgX))
    setHover({ x, p, svgX: toX(x), svgY: toY(p) })
  }

  const hasRemovals = removedZerosCount > 0 || removedTopCount > 0 || removedBottomCount > 0
  const showAllToggles = hasPrecomputed || samples.length > 0

  return (
    <div className="rounded border border-stone-200 bg-white p-2">
      <div className="mb-1 truncate text-[11px] font-medium text-stone-800" title={title}>
        {title}
        {unit ? <span className="ml-1 font-normal text-stone-400">({unit})</span> : null}
      </div>
      {showAllToggles ? (
        <div className="mb-1 flex flex-wrap gap-x-2 gap-y-1 text-[10px] text-stone-600">
          <label className="inline-flex items-center gap-1">
            <input type="checkbox" checked={trimTop} onChange={(e) => setTrimTop(e.target.checked)} />
            Trim top 0.1%
          </label>
          <label className="inline-flex items-center gap-1">
            <input type="checkbox" checked={trimBottom} onChange={(e) => setTrimBottom(e.target.checked)} />
            Trim bottom 0.1%
          </label>
          <label className="inline-flex items-center gap-1">
            <input type="checkbox" checked={removeZeros} onChange={(e) => setRemoveZeros(e.target.checked)} />
            Remove zeros
          </label>
          <label className="inline-flex items-center gap-1">
            <input type="checkbox" checked={logScale} onChange={(e) => setLogScale(e.target.checked)} />
            Log x-axis (log(1 + value))
          </label>
        </div>
      ) : (
        <div className="mb-1 text-[10px] text-stone-600">
          <label className="inline-flex items-center gap-1">
            <input type="checkbox" checked={logScale} onChange={(e) => setLogScale(e.target.checked)} />
            Log x-axis (log(1 + value))
          </label>
        </div>
      )}
      <div className="relative">
        <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="img" aria-label={`CDF of ${title}`}>
          {Y_TICKS.map((p) => (
            <g key={p}>
              <line
                x1={pad.left}
                x2={pad.left + innerW}
                y1={toY(p)}
                y2={toY(p)}
                stroke={p === 0.5 ? '#d6d3d1' : '#f5f5f4'}
                strokeWidth={1}
              />
              <text x={pad.left - 4} y={toY(p) + 3} textAnchor="end" fontSize="8" fill="#a8a29e">
                {Math.round(p * 100)}%
              </text>
            </g>
          ))}
          <line x1={pad.left} y1={pad.top + innerH} x2={pad.left + innerW} y2={pad.top + innerH} stroke="#d6d3d1" />
          <line x1={pad.left} y1={pad.top} x2={pad.left} y2={pad.top + innerH} stroke="#d6d3d1" />
          <path d={line} fill="none" stroke="#b45309" strokeWidth="1.5" />
          {hover ? (
            <>
              <line
                x1={hover.svgX}
                x2={hover.svgX}
                y1={pad.top}
                y2={pad.top + innerH}
                stroke="#78716c"
                strokeWidth={1}
                strokeDasharray="2 2"
              />
              <circle cx={hover.svgX} cy={hover.svgY} r={3} fill="#b45309" stroke="#fff" strokeWidth={1} />
            </>
          ) : null}
          {xTicks.map((tick) => (
            <g key={tick}>
              <line
                x1={toX(tick)}
                x2={toX(tick)}
                y1={pad.top + innerH}
                y2={pad.top + innerH + 4}
                stroke="#d6d3d1"
              />
              <text x={toX(tick)} y={height - 6} textAnchor="middle" fontSize="8" fill="#a8a29e">
                {formatX(tick)}
              </text>
            </g>
          ))}
          <text
            x={8}
            y={pad.top + innerH / 2}
            textAnchor="middle"
            fontSize="8"
            fill="#78716c"
            transform={`rotate(-90 8 ${pad.top + innerH / 2})`}
          >
            CDF %
          </text>
          <rect
            x={pad.left}
            y={pad.top}
            width={innerW}
            height={innerH}
            fill="transparent"
            onMouseMove={onChartMouseMove}
            onMouseLeave={() => setHover(null)}
          />
        </svg>
        {hover ? (
          <div
            className="pointer-events-none absolute z-10 rounded border border-stone-200 bg-white px-1.5 py-1 text-[10px] text-stone-700 shadow-sm"
            style={{
              left: `${Math.min(Math.max((hover.svgX / width) * 100, 8), 72)}%`,
              top: 4,
            }}
          >
            <div>
              value: {formatX(hover.x)}
              {unit ? ` ${unit}` : ''}
            </div>
            {logScale ? <div>log(1 + value): {formatX(axisX(hover.x, true))}</div> : null}
            <div>CDF: {formatP(hover.p)}</div>
          </div>
        ) : null}
      </div>
      <div className="mt-1 space-y-0.5 text-[10px] text-stone-600">
        <div>
          Samples: {displayedCount}
          {hasRemovals && displayedCount !== totalSamples ? ` of ${totalSamples}` : null}
        </div>
        {removeZeros && removedZerosCount > 0 ? (
          <div>
            Removed zeros: {removedZerosCount} ({removalPct(removedZerosCount, totalSamples)} of {totalSamples})
          </div>
        ) : null}
        {trimBottom && removedBottomCount > 0 ? (
          <div>
            Removed bottom 0.1%: {removedBottomCount} ({removalPct(removedBottomCount, totalSamples)} of{' '}
            {totalSamples})
          </div>
        ) : null}
        {trimTop && removedTopCount > 0 ? (
          <div>
            Removed top 0.1%: {removedTopCount} ({removalPct(removedTopCount, totalSamples)} of {totalSamples})
          </div>
        ) : null}
      </div>
      {hasRemovals ? (
        <div className="mt-1 space-y-1 text-[10px] text-stone-600">
          {removeZeros && removedZerosCount > 0 ? limitedMwsLinks(removedZeros, 'Zero MWS') : null}
          {trimBottom && removedBottomCount > 0 ? limitedMwsLinks(removedBottom, 'Bottom trim MWS') : null}
          {trimTop && removedTopCount > 0 ? limitedMwsLinks(removedTop, 'Top trim MWS') : null}
        </div>
      ) : null}
    </div>
  )
}
