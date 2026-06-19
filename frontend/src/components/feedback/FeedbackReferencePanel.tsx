import type { MwsDocument } from '../../types'
import { formatAgroEcologicalZone, mwsRainfallBand } from '../../utils/mwsData'
import { formatMwsTehsilLabel } from '../../utils/tehsilRefs'
import {
  CroppingChart,
  DeltaGChart,
  DroughtChart,
  LulcStackedChart,
  SogeGauge,
} from '../charts/MwsCharts'

function Chip({ label, value }: { label: string; value: string | number | null | undefined }) {
  if (value == null || value === '') return null
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-stone-200 bg-white px-2 py-0.5 text-xs text-stone-700">
      <span className="font-medium text-stone-500">{label}</span>
      {value}
    </span>
  )
}

export function FeedbackReferencePanel({ mws }: { mws: MwsDocument }) {
  const clusterId = mws.terrain?.cluster_id
  const aquifer =
    mws.aquifer?.acwadam_class ?? mws.aquifer?.raw_class ?? null
  const aer = mws.nbss_lup_aer_code
    ? `${mws.nbss_lup_aer_code}${mws.nbss_lup_aer_name ? ` · ${mws.nbss_lup_aer_name}` : ''}`
    : null

  return (
    <section className="rounded-lg border border-stone-200 bg-white shadow-sm">
      <details open>
        <summary className="cursor-pointer list-none px-4 py-3 marker:content-none">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-sm font-semibold text-stone-800">MWS reference</h2>
              <p className="text-xs text-stone-500">
                {mws.uid} · {formatMwsTehsilLabel(mws)}
              </p>
            </div>
            <span className="text-xs text-stone-400">Collapse / expand</span>
          </div>
        </summary>
        <div className="space-y-3 border-t border-stone-100 px-4 pb-4 pt-3">
          <div className="flex flex-wrap gap-2">
            <Chip label="AER" value={aer} />
            <Chip label="Rainfall" value={mwsRainfallBand(mws)} />
            <Chip label="Aquifer" value={aquifer} />
            <Chip label="Cluster" value={clusterId != null ? `#${clusterId}` : null} />
            <Chip label="AEZ" value={formatAgroEcologicalZone(mws)} />
            <Chip label="Area" value={mws.area_ha != null ? `${mws.area_ha.toFixed(0)} ha` : null} />
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3 [&_.h-44]:h-32">
            <SogeGauge mws={mws} />
            <DeltaGChart mws={mws} />
            <CroppingChart mws={mws} />
            <DroughtChart mws={mws} />
            <LulcStackedChart mws={mws} />
          </div>
        </div>
      </details>
    </section>
  )
}
