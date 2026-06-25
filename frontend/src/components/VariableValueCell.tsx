import { useMemo, type ReactNode } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { MwsVariableValueEntry } from '../api/triage'
import {
  categoryDictRows,
  cdBreakupBarData,
  categoryBarData,
  monsoonOffsetData,
  nregaYearData,
  seasonalLinesData,
  simpleLineData,
  stackedCroppingData,
  stackedDroughtData,
  stackedLulcData,
  stackedSwbData,
} from '../utils/variableValueCharts'

type Props = {
  entry?: MwsVariableValueEntry
}

const STACK_COLORS: Record<string, string> = {
  no_drought: '#86efac',
  mild: '#fde047',
  moderate: '#fb923c',
  severe: '#ef4444',
  single_kharif: '#15803d',
  single_non_kharif: '#4ade80',
  double: '#ca8a04',
  triple: '#a16207',
  kharif: '#16a34a',
  rabi: '#ca8a04',
  zaid: '#0284c7',
  built_up: '#d97706',
  water: '#0ea5e9',
  crop: '#eab308',
  trees: '#166534',
  shrubs: '#a3a3a3',
  barren: '#78716c',
}

function MiniChart({ children }: { children: ReactNode }) {
  return (
    <div className="min-w-[180px]">
      <div className="h-20 w-full">{children}</div>
    </div>
  )
}

function CategoryDictView({ entry }: { entry: MwsVariableValueEntry }) {
  const rows = categoryDictRows(entry)
  if (!rows.length) {
    return <span className="font-mono text-[10px] text-stone-600">{entry.formatted}</span>
  }
  return (
    <div className="max-w-[240px] space-y-0.5 font-mono text-[10px] text-stone-700">
      {rows.slice(0, 12).map(({ key, value }) => (
        <div key={key} className="flex justify-between gap-2">
          <span className="truncate text-stone-500" title={key}>
            {key}
          </span>
          <span>{value}</span>
        </div>
      ))}
      {rows.length > 12 ? <div className="text-stone-400">+{rows.length - 12} more</div> : null}
    </div>
  )
}

function LineOnlyChart({ entry }: { entry: MwsVariableValueEntry }) {
  const data = useMemo(() => simpleLineData(entry), [entry])
  if (data.length < 2) return <span className="font-mono text-[10px] text-stone-600">{entry.formatted}</span>
  return (
    <MiniChart>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
          <XAxis dataKey="label" hide />
          <YAxis hide domain={['auto', 'auto']} />
          <Tooltip labelFormatter={(label) => `Year ${label}`} />
          <Line type="monotone" dataKey="value" stroke="#b45309" strokeWidth={1.5} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </MiniChart>
  )
}

function SeasonalLinesChart({ entry, field }: { entry: MwsVariableValueEntry; field: string }) {
  const data = useMemo(() => seasonalLinesData(entry, field), [entry, field])
  if (!data.length) return <span className="text-stone-400">—</span>
  return (
    <MiniChart>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
          <XAxis dataKey="label" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
          <YAxis hide domain={['auto', 'auto']} />
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 9 }} />
          <Line type="monotone" dataKey="kharif" stroke="#16a34a" strokeWidth={1.5} dot={false} name="Kharif" />
          <Line type="monotone" dataKey="rabi" stroke="#ca8a04" strokeWidth={1.5} dot={false} name="Rabi" />
          <Line type="monotone" dataKey="zaid" stroke="#0284c7" strokeWidth={1.5} dot={false} name="Zaid" />
        </LineChart>
      </ResponsiveContainer>
    </MiniChart>
  )
}

function MonsoonOffsetChart({ entry }: { entry: MwsVariableValueEntry }) {
  const data = useMemo(() => monsoonOffsetData(entry), [entry])
  if (!data.length) return <span className="text-stone-400">—</span>
  return (
    <MiniChart>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }} barCategoryGap="20%">
          <XAxis dataKey="label" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
          <YAxis hide domain={['auto', 'auto']} />
          <Tooltip formatter={(v) => [`${v} days`, 'After earliest onset']} labelFormatter={(l) => `Year ${l}`} />
          <Bar dataKey="value" fill="#0ea5e9" maxBarSize={8} name="Days offset" />
        </BarChart>
      </ResponsiveContainer>
    </MiniChart>
  )
}

function StackedBarChart({
  entry,
  keys,
  buildData,
}: {
  entry: MwsVariableValueEntry
  keys: string[]
  buildData: (e: MwsVariableValueEntry) => Array<Record<string, string | number>>
}) {
  const data = useMemo(() => buildData(entry), [entry, buildData])
  if (!data.length) return <span className="text-stone-400">—</span>
  return (
    <MiniChart>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="2 2" stroke="#e7e5e4" />
          <XAxis dataKey="label" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
          <YAxis hide domain={['auto', 'auto']} />
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 8 }} />
          {keys.map((key) => (
            <Bar
              key={key}
              dataKey={key}
              stackId="stack"
              fill={STACK_COLORS[key] || '#78716c'}
              name={key.replace(/_/g, ' ')}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </MiniChart>
  )
}

function CategoryBarChart({ entry, tall }: { entry: MwsVariableValueEntry; tall?: boolean }) {
  const data = useMemo(() => categoryBarData(entry), [entry])
  if (!data.length) return <span className="text-stone-400">—</span>
  return (
    <div className={tall ? 'min-w-[200px]' : 'min-w-[180px]'}>
      <div className={tall ? 'h-28 w-full' : 'h-20 w-full'}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }} barCategoryGap="20%">
            <XAxis dataKey="label" tick={{ fontSize: 8 }} interval={0} angle={-35} textAnchor="end" height={36} />
            <YAxis hide domain={[0, 'auto']} />
            <Tooltip />
            <Bar dataKey="value" fill="#b45309" maxBarSize={10} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function CdBreakupChart({ entry }: { entry: MwsVariableValueEntry }) {
  const data = useMemo(() => cdBreakupBarData(entry), [entry])
  if (!data.length) return <span className="text-stone-400">—</span>
  return (
    <div className="min-w-[220px]">
      <div className="h-32 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart layout="vertical" data={data} margin={{ top: 4, right: 8, left: 4, bottom: 0 }}>
            <XAxis type="number" hide domain={[0, 'auto']} />
            <YAxis type="category" dataKey="label" width={88} tick={{ fontSize: 8 }} />
            <Tooltip formatter={(v) => [`${v} ha`, 'Area']} />
            <Bar dataKey="value" fill="#b45309" maxBarSize={10} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function DefaultTimeSeriesChart({ entry }: { entry: MwsVariableValueEntry }) {
  const data = useMemo(() => simpleLineData(entry), [entry])
  if (data.length >= 2) {
    return (
      <div className="min-w-[140px]">
        <div className="h-16 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
              <XAxis dataKey="label" hide />
              <YAxis hide domain={['auto', 'auto']} />
              <Tooltip formatter={(value) => [String(value), entry.name]} labelFormatter={(label) => `Year ${label}`} />
              <Line type="monotone" dataKey="value" stroke="#b45309" strokeWidth={1.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="font-mono text-[10px] text-stone-600">{entry.formatted}</div>
      </div>
    )
  }
  return <span className="font-mono text-[10px] text-stone-600">{entry.formatted}</span>
}

export function VariableValueCell({ entry }: Props) {
  if (!entry || entry.kind === 'missing') {
    return <span className="text-stone-400">—</span>
  }

  const profile = entry.display_profile

  if (profile?.type === 'line_only' || profile?.type === 'line_chart') {
    return <LineOnlyChart entry={entry} />
  }
  if (profile?.type === 'seasonal_lines' && profile.field) {
    return <SeasonalLinesChart entry={entry} field={String(profile.field)} />
  }
  if (profile?.type === 'monsoon_offset') {
    return <MonsoonOffsetChart entry={entry} />
  }
  if (profile?.type === 'stacked_drought') {
    return (
      <StackedBarChart
        entry={entry}
        keys={['no_drought', 'mild', 'moderate', 'severe']}
        buildData={stackedDroughtData}
      />
    )
  }
  if (profile?.type === 'stacked_cropping') {
    return (
      <StackedBarChart
        entry={entry}
        keys={['single_kharif', 'single_non_kharif', 'double', 'triple']}
        buildData={stackedCroppingData}
      />
    )
  }
  if (profile?.type === 'stacked_swb') {
    return <StackedBarChart entry={entry} keys={['kharif', 'rabi', 'zaid']} buildData={stackedSwbData} />
  }
  if (profile?.type === 'stacked_lulc') {
    return (
      <StackedBarChart
        entry={entry}
        keys={['built_up', 'water', 'crop', 'trees', 'shrubs', 'barren']}
        buildData={stackedLulcData}
      />
    )
  }
  if (profile?.type === 'nrega_years') {
    const data = nregaYearData(entry)
    const keys = data.length
      ? Object.keys(data[0]).filter((k) => k !== 'label')
      : []
    return <StackedBarChart entry={entry} keys={keys} buildData={nregaYearData} />
  }
  if (profile?.type === 'category_dict') {
    return <CategoryDictView entry={entry} />
  }
  if (profile?.type === 'category_bars') {
    return <CategoryBarChart entry={entry} tall={entry.name === 'stream_order_area_percent'} />
  }
  if (
    profile?.type === 'cd_degradation_breakup' ||
    profile?.type === 'cd_deforestation_breakup' ||
    profile?.type === 'cd_crop_intensity_breakup'
  ) {
    return <CdBreakupChart entry={entry} />
  }

  if (entry.kind === 'time_series') {
    return <DefaultTimeSeriesChart entry={entry} />
  }

  if (entry.kind === 'static_dict' && entry.raw && typeof entry.raw === 'object') {
    return <CategoryDictView entry={entry} />
  }

  if (entry.kind === 'list' && Array.isArray(entry.raw)) {
    return <span className="font-mono text-[10px] text-stone-700">{(entry.raw as unknown[]).join(', ')}</span>
  }

  return (
    <span className="font-mono text-[10px] text-stone-800" title={entry.kind === 'derived' ? 'derived' : undefined}>
      {entry.formatted}
    </span>
  )
}
