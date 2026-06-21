import type { MwsDocument, TehsilRef } from '../types'
import { formatMwsTehsilLabel } from '../utils/tehsilRefs'
import {
  facilityDistanceTable,
  formatAgroEcologicalZone,
  hasNregaData,
  intersectVillageRows,
  landChangeTotals,
  degradationBreakdown,
  afforestationBreakdown,
  deforestationBreakdown,
  urbanizationBreakdown,
  mwsRainfallBand,
} from '../utils/mwsData'
import { hasPanelHighlights, panelHighlightFlags } from '../utils/panelHighlight'
import {
  ChangeDetectionStackedBar,
  CroppingChart,
  DeltaGChart,
  DeforestationPairChart,
  DroughtChart,
  DrySpellChart,
  DualAxisCroppingDeltaG,
  FacilityDistanceChart,
  ForestTrendChart,
  LulcStackedChart,
  NregaChart,
  PrecipitationChart,
  SogeGauge,
  SwbChart,
} from './charts/MwsCharts'

interface Props {
  mws: MwsDocument | null
  loading: boolean
  panelUpdates: string[]
  activeTehsil?: TehsilRef | null
}

function IdentityRow({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="flex justify-between gap-3 border-b border-stone-100 py-1.5 text-sm">
      <span className="text-stone-500">{label}</span>
      <span className="text-right font-medium text-stone-800">{value ?? '—'}</span>
    </div>
  )
}

function LandChangeRow({
  label,
  value,
  tone,
  breakdown,
}: {
  label: string
  value: number
  tone: 'red' | 'emerald' | 'amber' | 'stone'
  breakdown?: Array<{ key: string; label: string; ha: number; color: string }>
}) {
  const toneClass =
    tone === 'red'
      ? 'text-red-700'
      : tone === 'emerald'
        ? 'text-emerald-700'
        : tone === 'amber'
          ? 'text-amber-700'
          : 'text-stone-800'
  return (
    <div className="border-b border-stone-100 py-2 last:border-b-0">
      <div className="flex justify-between text-sm">
        <span className="text-stone-600">{label}</span>
        <span className={`font-medium ${toneClass}`}>{value.toFixed(1)} ha</span>
      </div>
      {breakdown && breakdown.length > 0 && <ChangeDetectionStackedBar segments={breakdown} />}
    </div>
  )
}

function formatPercent(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value.toFixed(1)}%`
}

export function InfoPanel({ mws, loading, panelUpdates, activeTehsil }: Props) {
  if (loading) {
    return <div className="p-6 text-sm text-stone-500">Loading MWS data…</div>
  }

  if (!mws) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-stone-500">
        Click a micro-watershed polygon to view its profile and charts.
      </div>
    )
  }

  const landChange = landChangeTotals(mws)
  const landBreakdowns = {
    degradation: degradationBreakdown(mws),
    afforestation: afforestationBreakdown(mws),
    deforestation: deforestationBreakdown(mws),
    urbanization: urbanizationBreakdown(mws),
  }
  const villages = intersectVillageRows(mws)
  const facilities = facilityDistanceTable(mws)
  const highlights = panelHighlightFlags(panelUpdates)
  const showHighlights = hasPanelHighlights(highlights)
  const showLivelihoods = villages.length > 0 || facilities.length > 0 || hasNregaData(mws)

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="border-b border-stone-200 bg-stone-50 px-4 py-3">
        <h2 className="text-lg font-semibold text-stone-800">MWS {mws.uid}</h2>
        <p className="text-sm text-stone-500">{formatMwsTehsilLabel(mws, activeTehsil)}</p>
      </div>

      <div className="space-y-4 p-4">
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-500">Identity</h3>
          <div className="rounded-lg border border-stone-200 bg-white px-3 py-1">
            <IdentityRow label="Area" value={mws.area_ha != null ? `${mws.area_ha.toFixed(1)} ha` : null} />
            <IdentityRow label="Agro-ecological zone" value={formatAgroEcologicalZone(mws)} />
            <IdentityRow label="Rainfall band" value={mwsRainfallBand(mws)} />
            <IdentityRow label="Terrain" value={mws.terrain?.description ?? mws.terrain?.cluster_id} />
            <IdentityRow label="Aquifer" value={mws.aquifer?.raw_class ?? mws.aquifer?.acwadam_class} />
            <IdentityRow label="River" value={mws.river_name} />
            <IdentityRow label="Canal" value={mws.canal?.canal_name ?? mws.canal?.project_name} />
            <IdentityRow
              label="Villages"
              value={
                (mws.intersect_village_names ?? [])
                  .map((v) => v.name)
                  .filter(Boolean)
                  .join(', ') || null
              }
            />
          </div>
        </section>

        {showHighlights && (
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-amber-700">Diagnosis highlight</h3>
            <div className="grid gap-3">
              {highlights.dualAxis && <DualAxisCroppingDeltaG mws={mws} />}
              {highlights.forestTrend && <ForestTrendChart mws={mws} />}
              {highlights.deforestationPair && <DeforestationPairChart mws={mws} />}
              {highlights.lulcStacked && <LulcStackedChart mws={mws} />}
              {highlights.croppingTrend && <CroppingChart mws={mws} />}
              {highlights.droughtWeeks && <DroughtChart mws={mws} />}
              {highlights.nregaBar && hasNregaData(mws) && <NregaChart mws={mws} />}
              {highlights.distBars && <FacilityDistanceChart mws={mws} />}
              {highlights.degradationSummary && (
                <div className="rounded-lg border border-stone-200 bg-white p-3 text-sm">
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-500">Land change (2017–25)</h4>
                  <LandChangeRow
                    label="Cropping area degradation"
                    value={landChange.croppingDegradation}
                    tone="red"
                    breakdown={landBreakdowns.degradation}
                  />
                </div>
              )}
            </div>
          </section>
        )}

        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-500">Water</h3>
          <div className="grid gap-3">
            <SogeGauge mws={mws} />
            <DeltaGChart mws={mws} />
            <SwbChart mws={mws} />
          </div>
        </section>

        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-500">Land use</h3>
          <div className="grid gap-3">
            <CroppingChart mws={mws} />
            <div className="rounded-lg border border-stone-200 bg-white p-3 text-sm">
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-500">Land change (2017–25)</h4>
              <LandChangeRow
                label="Cropping area degradation"
                value={landChange.croppingDegradation}
                tone="red"
                breakdown={landBreakdowns.degradation}
              />
              <LandChangeRow
                label="Tree cover increase"
                value={landChange.afforestation}
                tone="emerald"
                breakdown={landBreakdowns.afforestation}
              />
              <LandChangeRow
                label="Tree cover decrease"
                value={landChange.deforestation}
                tone="red"
                breakdown={landBreakdowns.deforestation}
              />
              <LandChangeRow
                label="Urbanization"
                value={landChange.urbanization}
                tone="amber"
                breakdown={landBreakdowns.urbanization}
              />
            </div>
          </div>
        </section>

        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-500">Tree cover</h3>
          <ForestTrendChart mws={mws} />
        </section>

        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-500">Climate & drought</h3>
          <div className="grid gap-3">
            <PrecipitationChart mws={mws} />
            <DroughtChart mws={mws} />
            <DrySpellChart mws={mws} />
          </div>
        </section>

        {showLivelihoods && (
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-500">Livelihoods</h3>
            <div className="grid gap-3">
              {villages.length > 0 && (
                <div className="overflow-hidden rounded-lg border border-stone-200 bg-white">
                  <div className="border-b border-stone-200 bg-stone-50 px-3 py-2">
                    <h4 className="text-xs font-semibold uppercase tracking-wide text-stone-500">Intersecting villages</h4>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-left text-sm">
                      <thead>
                        <tr className="border-b border-stone-200 text-xs uppercase tracking-wide text-stone-500">
                          <th className="px-3 py-2 font-medium">Village</th>
                          <th className="px-3 py-2 font-medium">Population</th>
                          <th className="px-3 py-2 font-medium">SC %</th>
                          <th className="px-3 py-2 font-medium">ST %</th>
                          <th className="px-3 py-2 font-medium">Literacy</th>
                        </tr>
                      </thead>
                      <tbody>
                        {villages.map((v) => (
                          <tr key={v.village_id} className="border-b border-stone-100 last:border-b-0">
                            <td className="px-3 py-2 font-medium text-stone-800">{v.name}</td>
                            <td className="px-3 py-2 text-stone-700">{v.population?.toLocaleString() ?? '—'}</td>
                            <td className="px-3 py-2 text-stone-700">{formatPercent(v.sc_percent)}</td>
                            <td className="px-3 py-2 text-stone-700">{formatPercent(v.st_percent)}</td>
                            <td className="px-3 py-2 text-stone-700">{formatPercent(v.literacy_rate_percent)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {facilities.length > 0 && (
                <div className="overflow-hidden rounded-lg border border-stone-200 bg-white">
                  <div className="border-b border-stone-200 bg-stone-50 px-3 py-2">
                    <h4 className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                      Nearest facility distances (min across villages)
                    </h4>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-left text-sm">
                      <thead>
                        <tr className="border-b border-stone-200 text-xs uppercase tracking-wide text-stone-500">
                          <th className="px-3 py-2 font-medium">Facility</th>
                          <th className="px-3 py-2 font-medium">Distance (km)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {facilities.map((row) => (
                          <tr key={row.facility} className="border-b border-stone-100 last:border-b-0">
                            <td className="px-3 py-2 text-stone-700">{row.facility}</td>
                            <td className="px-3 py-2 font-medium text-stone-800">{row.distance_km.toFixed(1)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {hasNregaData(mws) && <NregaChart mws={mws} />}
            </div>
          </section>
        )}
      </div>
    </div>
  )
}
