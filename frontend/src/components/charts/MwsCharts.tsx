import type { ReactNode } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { MwsDocument } from '../../types'
import {
  croppingSeries,
  deforestationPair,
  droughtSeries,
  drySpellSeries,
  dualAxisSeries,
  facilityDistanceRows,
  hydroSeries,
  lulcForestSeries,
  lulcStackedSeries,
  nregaTotals,
  swbSeries,
  type YearPoint,
} from '../../utils/mwsData'

function ChartCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-stone-200 bg-white p-3 shadow-sm">
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-500">{title}</h4>
      <div className="h-44">{children}</div>
    </div>
  )
}

export function SogeGauge({ mws }: { mws: MwsDocument }) {
  const pct = mws.soge?.dev_percent
  const cls = mws.soge?.class_name ?? 'Unknown'
  const color =
    pct == null ? 'bg-stone-200' : pct >= 100 ? 'bg-red-600' : pct >= 90 ? 'bg-orange-500' : pct >= 70 ? 'bg-amber-500' : 'bg-emerald-500'

  return (
    <ChartCard title="Groundwater extraction (SOGE)">
      <div className="flex h-full flex-col items-center justify-center gap-2">
        <div className={`rounded-full px-4 py-2 text-lg font-bold text-white ${color}`}>
          {pct != null ? `${pct.toFixed(1)}%` : 'N/A'}
        </div>
        <p className="text-sm text-stone-600">{cls}</p>
      </div>
    </ChartCard>
  )
}

export function DeltaGChart({ mws }: { mws: MwsDocument }) {
  const data = hydroSeries(mws, 'delta_g_mm')
  return (
    <ChartCard title="Annual groundwater balance (ΔG)">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
          <XAxis dataKey="year" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Bar dataKey="value" name="ΔG (mm)">
            {data.map((entry: YearPoint) => (
              <Cell key={entry.year} fill={entry.value < 0 ? '#dc2626' : '#2563eb'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

export function CroppingChart({ mws }: { mws: MwsDocument }) {
  const data = croppingSeries(mws)
  if (data.length === 0) {
    return (
      <ChartCard title="Cropping intensity">
        <div className="flex h-full items-center justify-center text-sm text-stone-400">No cropping intensity data</div>
      </ChartCard>
    )
  }
  return (
    <ChartCard title="Cropping intensity">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
          <XAxis dataKey="year" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Line type="monotone" dataKey="value" stroke="#15803d" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

export function PrecipitationChart({ mws }: { mws: MwsDocument }) {
  const data = hydroSeries(mws, 'precipitation_mm')
  const mean = data.length ? data.reduce((s: number, d: YearPoint) => s + d.value, 0) / data.length : 0
  return (
    <ChartCard title="Annual precipitation">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
          <XAxis dataKey="year" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Bar dataKey="value" fill="#0ea5e9" name="Rainfall (mm)" />
          <Line type="monotone" dataKey={() => mean} stroke="#78716c" strokeDasharray="4 4" dot={false} name="Mean" />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

export function DroughtChart({ mws }: { mws: MwsDocument }) {
  const data = droughtSeries(mws)
  return (
    <ChartCard title="Kharif drought weeks">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
          <XAxis dataKey="year" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Bar dataKey="no" stackId="a" fill="#86efac" name="None" />
          <Bar dataKey="mild" stackId="a" fill="#fde047" name="Mild" />
          <Bar dataKey="moderate" stackId="a" fill="#fb923c" name="Moderate" />
          <Bar dataKey="severe" stackId="a" fill="#ef4444" name="Severe" />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

export function DrySpellChart({ mws }: { mws: MwsDocument }) {
  const data = drySpellSeries(mws)
  return (
    <ChartCard title="Dry spell weeks">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
          <XAxis dataKey="year" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Bar dataKey="value" fill="#a16207" name="Weeks" />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

export function SwbChart({ mws }: { mws: MwsDocument }) {
  const data = swbSeries(mws)
  if (data.length === 0) {
    return (
      <ChartCard title="Surface water bodies">
        <div className="flex h-full flex-col items-center justify-center gap-1 px-4 text-center text-sm text-stone-400">
          <span>No surface water body time series for this MWS.</span>
          <span className="text-xs">It may be absent from the CoRE Stack SWB export sheets.</span>
        </div>
      </ChartCard>
    )
  }
  return (
    <ChartCard title="Surface water bodies">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
          <XAxis dataKey="year" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Line type="monotone" dataKey="total" stroke="#0284c7" dot={false} name="Total ha" />
          <Line type="monotone" dataKey="kharif" stroke="#16a34a" dot={false} name="Kharif ha" />
          <Line type="monotone" dataKey="rabi" stroke="#ca8a04" dot={false} name="Rabi ha" />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

export function NregaChart({ mws }: { mws: MwsDocument }) {
  const data = nregaTotals(mws).slice(0, 6)
  return (
    <ChartCard title="MGNREGA works (cumulative)">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical">
          <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
          <XAxis type="number" tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="category" width={90} tick={{ fontSize: 10 }} />
          <Tooltip />
          <Bar dataKey="total" fill="#7c3aed" name="Count" />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

export function DualAxisCroppingDeltaG({ mws }: { mws: MwsDocument }) {
  const data = dualAxisSeries(mws)
  return (
    <ChartCard title="Cropping intensity vs ΔG (diagnosis highlight)">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
          <XAxis dataKey="year" tick={{ fontSize: 11 }} />
          <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
          <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Bar yAxisId="right" dataKey="deltaG" fill="#dc2626" name="ΔG (mm)" />
          <Line yAxisId="left" type="monotone" dataKey="cropping" stroke="#15803d" strokeWidth={2} dot={false} name="Cropping intensity" />
        </ComposedChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

export function panelUpdateNeedsDualAxis(updates: string[]): boolean {
  return updates.some((u) => u.includes('cropping_intensity') && u.includes('annual_delta_g_mm'))
}

export function ForestTrendChart({ mws }: { mws: MwsDocument }) {
  const data = lulcForestSeries(mws)
  if (data.length === 0) {
    return (
      <ChartCard title="Forest cover trend">
        <div className="flex h-full items-center justify-center text-sm text-stone-400">No forest LULC data</div>
      </ChartCard>
    )
  }
  return (
    <ChartCard title="Forest cover trend">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
          <XAxis dataKey="year" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Line type="monotone" dataKey="value" stroke="#166534" strokeWidth={2} dot={false} name="Tree/forest (ha)" />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

export function LulcStackedChart({ mws }: { mws: MwsDocument }) {
  const data = lulcStackedSeries(mws)
  if (data.length === 0) {
    return (
      <ChartCard title="Land use change">
        <div className="flex h-full items-center justify-center text-sm text-stone-400">No LULC time series</div>
      </ChartCard>
    )
  }
  return (
    <ChartCard title="Land use change">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
          <XAxis dataKey="year" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Area type="monotone" dataKey="cropland" stackId="lulc" fill="#ca8a04" stroke="#ca8a04" name="Cropland" />
          <Area type="monotone" dataKey="tree_forest" stackId="lulc" fill="#15803d" stroke="#15803d" name="Forest" />
          <Area type="monotone" dataKey="shrub_scrub" stackId="lulc" fill="#a3a3a3" stroke="#a3a3a3" name="Shrub/scrub" />
          <Area type="monotone" dataKey="barrenland" stackId="lulc" fill="#78716c" stroke="#78716c" name="Barren" />
          <Area type="monotone" dataKey="krz_water" stackId="lulc" fill="#0284c7" stroke="#0284c7" name="Water" />
        </AreaChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

export function DeforestationPairChart({ mws }: { mws: MwsDocument }) {
  const pair = deforestationPair(mws)
  const data = [
    { label: 'Deforestation', ha: pair.deforestation },
    { label: 'Afforestation', ha: pair.afforestation },
  ]
  return (
    <ChartCard title="Forest cover change (2017–25)">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Bar dataKey="ha" name="Area (ha)">
            <Cell fill="#dc2626" />
            <Cell fill="#16a34a" />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

export function FacilityDistanceChart({ mws }: { mws: MwsDocument }) {
  const data = facilityDistanceRows(mws)
  if (data.length === 0) {
    return (
      <ChartCard title="Facility distances">
        <div className="flex h-full items-center justify-center text-sm text-stone-400">No facility proximity data</div>
      </ChartCard>
    )
  }
  return (
    <ChartCard title="Nearest facility distances">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical">
          <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
          <XAxis type="number" tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="label" width={148} tick={{ fontSize: 11 }} />
          <Tooltip />
          <Bar dataKey="km" fill="#0369a1" name="Distance (km)" />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

export function ChangeDetectionStackedBar({
  segments,
}: {
  segments: Array<{ key: string; label: string; ha: number; color: string }>
}) {
  const total = segments.reduce((sum, segment) => sum + segment.ha, 0)
  if (total <= 0) {
    return <p className="mt-1 text-[10px] italic text-stone-400">No transition detail</p>
  }

  return (
    <div className="mt-1.5">
      <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-stone-100">
        {segments.map((segment) => (
          <div
            key={segment.key}
            className="h-full min-w-[2px] transition-[width] duration-300"
            style={{
              width: `${(segment.ha / total) * 100}%`,
              backgroundColor: segment.color,
            }}
            title={`${segment.label}: ${segment.ha.toFixed(1)} ha`}
          />
        ))}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1">
        {segments.map((segment) => (
          <span key={segment.key} className="inline-flex items-center gap-1 text-[10px] text-stone-600">
            <span
              className="inline-block h-2 w-2 shrink-0 rounded-sm"
              style={{ backgroundColor: segment.color }}
            />
            <span>
              {segment.label}{' '}
              <span className="font-medium text-stone-800">{segment.ha.toFixed(1)} ha</span>
            </span>
          </span>
        ))}
      </div>
    </div>
  )
}
