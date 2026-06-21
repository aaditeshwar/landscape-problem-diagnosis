import type { MwsDocument } from '../types'

export interface YearPoint {
  year: string
  value: number
}

export interface DroughtPoint {
  year: string
  no: number
  mild: number
  moderate: number
  severe: number
}

function sortedYears(obj: Record<string, unknown> | undefined): string[] {
  if (!obj) return []
  return Object.keys(obj).sort((a, b) => Number(a) - Number(b))
}

export function hydroSeries(mws: MwsDocument, field: keyof NonNullable<MwsDocument['hydrological_annual']>[string]): YearPoint[] {
  const hydro = mws.hydrological_annual ?? {}
  return sortedYears(hydro)
    .map((year) => ({
      year,
      value: Number(hydro[year]?.[field] ?? NaN),
    }))
    .filter((p) => Number.isFinite(p.value))
}

/** Mean annual precipitation (mm) from hydrological_annual time series. */
export function meanAnnualPrecipitationMm(mws: MwsDocument): number | null {
  const points = hydroSeries(mws, 'precipitation_mm')
  if (!points.length) return null
  const sum = points.reduce((acc, p) => acc + p.value, 0)
  return sum / points.length
}

/** Rainfall band from mean annual precipitation (mm). */
export function rainfallBandLabel(meanMm: number): string {
  if (meanMm < 740) return '< 740 mm'
  if (meanMm < 960) return '740–960 mm'
  if (meanMm < 1200) return '960–1200 mm'
  if (meanMm < 1620) return '1200–1620 mm'
  return '> 1620 mm'
}

export function mwsRainfallBand(mws: MwsDocument): string | null {
  const mean = meanAnnualPrecipitationMm(mws)
  if (mean == null || !Number.isFinite(mean)) return null
  return rainfallBandLabel(mean)
}

export function formatAgroEcologicalZone(mws: MwsDocument): string | null {
  const name = mws.agro_ecological_zone ?? mws.nbss_lup_aer_name
  const code = mws.nbss_lup_aer_code
  if (name && code) return `${name} (${code})`
  if (name) return name
  if (code) return code
  return null
}

export function croppingSeries(mws: MwsDocument): YearPoint[] {
  const data = mws.cropping_intensity ?? {}
  return sortedYears(data)
    .map((year) => {
      const row = data[year]
      const raw =
        row != null && typeof row === 'object'
          ? (row as { cropping_intensity?: number }).cropping_intensity
          : row
      return { year, value: Number(raw) }
    })
    .filter((p) => Number.isFinite(p.value))
}

export function droughtSeries(mws: MwsDocument): DroughtPoint[] {
  const data = mws.drought_kharif ?? {}
  return sortedYears(data).map((year) => {
    const row = data[year] ?? {}
    return {
      year,
      no: Number(row.no_drought_weeks ?? 0),
      mild: Number(row.mild_weeks ?? 0),
      moderate: Number(row.moderate_weeks ?? 0),
      severe: Number(row.severe_weeks ?? 0),
    }
  })
}

export function droughtHasChartData(mws: MwsDocument): boolean {
  return droughtSeries(mws).some((point) => point.moderate > 0 || point.severe > 0)
}

export function drySpellSeries(mws: MwsDocument): YearPoint[] {
  const data = mws.drought_kharif ?? {}
  return sortedYears(data)
    .map((year) => ({ year, value: Number(data[year]?.dry_spell_weeks ?? NaN) }))
    .filter((p) => Number.isFinite(p.value))
}

export function swbSeries(mws: MwsDocument): Array<{ year: string; total: number; kharif: number; rabi: number }> {
  const data = mws.swb_annual ?? {}
  return sortedYears(data).map((year) => ({
    year,
    total: Number(data[year]?.total_ha ?? 0),
    kharif: Number(data[year]?.kharif_ha ?? 0),
    rabi: Number(data[year]?.rabi_ha ?? 0),
  }))
}

export function nregaTotals(mws: MwsDocument): Array<{ category: string; total: number }> {
  const totals: Record<string, number> = {}
  for (const year of Object.values(mws.nrega_mws ?? {})) {
    for (const [cat, count] of Object.entries(year)) {
      totals[cat] = (totals[cat] ?? 0) + Number(count ?? 0)
    }
  }
  return Object.entries(totals)
    .map(([category, total]) => ({ category: category.replace(/_/g, ' '), total }))
    .sort((a, b) => b.total - a.total)
}

export function hasNregaData(mws: MwsDocument): boolean {
  return nregaTotals(mws).some((row) => row.total > 0)
}

export function degradationTotals(mws: MwsDocument): { degradation: number; afforestation: number } {
  const land = landChangeTotals(mws)
  return { degradation: land.croppingDegradation, afforestation: land.afforestation }
}

export interface LandChangeTotals {
  croppingDegradation: number
  afforestation: number
  deforestation: number
  urbanization: number
}

function changeDetectionHa(mws: MwsDocument, sheet: string, ...keys: string[]): number {
  const row = mws.change_detection?.[sheet] ?? {}
  for (const key of keys) {
    const val = row[key]
    if (val != null && Number.isFinite(Number(val))) {
      return Number(val)
    }
  }
  return 0
}

export interface ChangeDetectionSegment {
  key: string
  label: string
  ha: number
  color: string
}

interface ChangeSegmentSpec {
  key: string
  label: string
  color: string
}

const DEGRADATION_BREAKDOWN: ChangeSegmentSpec[] = [
  { key: 'farm_to_barren_ha', label: 'Farm → barren', color: '#78716c' },
  { key: 'farm_to_built_up_ha', label: 'Farm → built-up', color: '#d97706' },
  { key: 'farm_to_scrubland_ha', label: 'Farm → scrubland', color: '#a8a29e' },
]

const AFFORESTATION_BREAKDOWN: ChangeSegmentSpec[] = [
  { key: 'barren_to_forest_ha', label: 'Barren → trees', color: '#84cc16' },
  { key: 'built_up_to_forest_ha', label: 'Built-up → trees', color: '#65a30d' },
  { key: 'farm_to_forest_ha', label: 'Farm → trees', color: '#15803d' },
  { key: 'scrubland_to_forest_ha', label: 'Scrub → trees', color: '#166534' },
]

const DEFORESTATION_BREAKDOWN: ChangeSegmentSpec[] = [
  { key: 'forest_to_barren_ha', label: 'Trees → barren', color: '#78716c' },
  { key: 'forest_to_built_up_ha', label: 'Trees → built-up', color: '#d97706' },
  { key: 'forest_to_farm_ha', label: 'Trees → farm', color: '#ca8a04' },
  { key: 'forest_to_scrubland_ha', label: 'Trees → scrub', color: '#a8a29e' },
]

const URBANIZATION_BREAKDOWN: ChangeSegmentSpec[] = [
  { key: 'barren_shrub_to_built_up_ha', label: 'Barren/shrub → built-up', color: '#78716c' },
  { key: 'tree_farm_to_built_up_ha', label: 'Tree/farm → built-up', color: '#ca8a04' },
  { key: 'water_to_built_up_ha', label: 'Water → built-up', color: '#0284c7' },
]

function changeDetectionBreakdown(
  mws: MwsDocument,
  sheet: string,
  specs: ChangeSegmentSpec[],
): ChangeDetectionSegment[] {
  const row = mws.change_detection?.[sheet] ?? {}
  return specs
    .map((spec) => ({
      ...spec,
      ha: Math.max(0, Number(row[spec.key] ?? 0)),
    }))
    .filter((segment) => segment.ha > 0)
}

export function degradationBreakdown(mws: MwsDocument): ChangeDetectionSegment[] {
  return changeDetectionBreakdown(mws, 'degradation', DEGRADATION_BREAKDOWN)
}

export function afforestationBreakdown(mws: MwsDocument): ChangeDetectionSegment[] {
  return changeDetectionBreakdown(mws, 'afforestation', AFFORESTATION_BREAKDOWN)
}

export function deforestationBreakdown(mws: MwsDocument): ChangeDetectionSegment[] {
  return changeDetectionBreakdown(mws, 'deforestation', DEFORESTATION_BREAKDOWN)
}

export function urbanizationBreakdown(mws: MwsDocument): ChangeDetectionSegment[] {
  return changeDetectionBreakdown(mws, 'urbanization', URBANIZATION_BREAKDOWN)
}

export function landChangeTotals(mws: MwsDocument): LandChangeTotals {
  return {
    croppingDegradation: changeDetectionHa(mws, 'degradation', 'total_ha', 'total_degradation'),
    afforestation: changeDetectionHa(mws, 'afforestation', 'total_ha', 'total_afforestation'),
    deforestation: changeDetectionHa(mws, 'deforestation', 'total_ha', 'total_deforestation'),
    urbanization: changeDetectionHa(mws, 'urbanization', 'total_ha', 'total_urbanization'),
  }
}

export function dualAxisSeries(mws: MwsDocument): Array<{ year: string; cropping: number; deltaG: number }> {
  const cropping = croppingSeries(mws)
  const delta = hydroSeries(mws, 'delta_g_mm')
  const deltaMap = Object.fromEntries(delta.map((d) => [d.year, d.value]))
  return cropping
    .filter((c) => deltaMap[c.year] !== undefined)
    .map((c) => ({ year: c.year, cropping: c.value, deltaG: deltaMap[c.year] }))
}

export function lulcForestSeries(mws: MwsDocument): YearPoint[] {
  const data = mws.lulc_ha ?? {}
  return sortedYears(data)
    .map((year) => ({ year, value: Number(data[year]?.tree_forest ?? NaN) }))
    .filter((p) => Number.isFinite(p.value))
}

const LULC_CROPLAND_COMPONENTS = ['single_kharif', 'single_non_kharif', 'double_crop', 'triple_crop'] as const
const LULC_SURFACE_KEYS = ['cropland', 'built_up', 'tree_forest', 'shrub_scrub', 'barrenland'] as const
const LULC_WATER_KEYS = ['k_water', 'kr_water', 'krz_water'] as const

export function lulcStackedSeries(
  mws: MwsDocument,
  options?: { combineWater?: boolean },
): Array<Record<string, string | number>> {
  const combineWater = options?.combineWater ?? false
  const data = mws.lulc_ha ?? {}
  return sortedYears(data).map((year) => {
    const row = data[year] ?? {}
    const out: Record<string, string | number> = { year }
    out.cropland = LULC_CROPLAND_COMPONENTS.reduce((sum, key) => sum + Number(row[key] ?? 0), 0)
    for (const key of LULC_SURFACE_KEYS.slice(1)) {
      out[key] = Number(row[key] ?? 0)
    }
    if (combineWater) {
      out.water = LULC_WATER_KEYS.reduce((sum, key) => sum + Number(row[key] ?? 0), 0)
    } else {
      for (const key of LULC_WATER_KEYS) {
        out[key] = Number(row[key] ?? 0)
      }
    }
    return out
  })
}

const FACILITY_DISTANCE_SPECS: Array<{ key: keyof NonNullable<MwsDocument['facility_distances']>; label: string }> = [
  { key: 'dist_school_primary_km', label: 'Primary school' },
  { key: 'dist_school_secondary_km', label: 'Secondary school' },
  { key: 'dist_college_km', label: 'College' },
  { key: 'dist_chc_km', label: 'Community health centre' },
  { key: 'dist_phc_km', label: 'Primary health centre' },
  { key: 'dist_sub_centre_km', label: 'Health sub-centre' },
  { key: 'dist_district_hospital_km', label: 'District hospital' },
  { key: 'dist_cooperative_km', label: 'Agricultural cooperative society' },
  { key: 'dist_markets_trading_km', label: 'Agricultural market' },
  { key: 'dist_storage_warehousing_km', label: 'Cold storage / warehousing' },
  { key: 'dist_agri_processing_km', label: 'Agri processing' },
  { key: 'dist_apmc_km', label: 'APMC' },
  { key: 'dist_dairy_km', label: 'Dairy / animal husbandry' },
  { key: 'dist_bank_km', label: 'Bank (nearest)' },
  { key: 'dist_csc_km', label: 'Common service centre' },
  { key: 'dist_pds_km', label: 'PDS outlet' },
]

const FACILITY_LABEL_ORDER = FACILITY_DISTANCE_SPECS.map((spec) => spec.label)

function sortFacilityRows<T extends { facility?: string; label?: string }>(rows: T[]): T[] {
  const order = new Map(FACILITY_LABEL_ORDER.map((label, index) => [label, index]))
  return [...rows].sort((a, b) => {
    const aLabel = a.facility ?? a.label ?? ''
    const bLabel = b.facility ?? b.label ?? ''
    const aIndex = order.get(aLabel) ?? Number.MAX_SAFE_INTEGER
    const bIndex = order.get(bLabel) ?? Number.MAX_SAFE_INTEGER
    if (aIndex !== bIndex) return aIndex - bIndex
    return aLabel.localeCompare(bLabel)
  })
}

export function facilityDistanceRows(mws: MwsDocument): Array<{ label: string; km: number }> {
  const dist = mws.facility_distances ?? {}
  const rows = FACILITY_DISTANCE_SPECS.flatMap(({ key, label }) => {
    const km = dist[key]
    if (km == null || !Number.isFinite(km)) return []
    return [{ label, km }]
  })
  return rows
}

export function deforestationPair(mws: MwsDocument): { deforestation: number; afforestation: number } {
  const land = landChangeTotals(mws)
  return { deforestation: land.deforestation, afforestation: land.afforestation }
}

export function intersectVillageRows(mws: MwsDocument): Array<{
  village_id: number
  name: string
  population: number | null
  sc_percent: number | null
  st_percent: number | null
  literacy_rate_percent: number | null
}> {
  return (mws.intersect_village_names ?? []).map((v) => ({
    village_id: v.village_id,
    name: v.name?.trim() || `Village ${v.village_id}`,
    population: v.population != null ? Number(v.population) : null,
    sc_percent: v.sc_percent != null ? Number(v.sc_percent) : null,
    st_percent: v.st_percent != null ? Number(v.st_percent) : null,
    literacy_rate_percent: v.literacy_rate_percent != null ? Number(v.literacy_rate_percent) : null,
  }))
}

export function facilityDistanceTable(mws: MwsDocument): Array<{ facility: string; distance_km: number }> {
  if (mws.facility_distance_table?.length) {
    return sortFacilityRows(mws.facility_distance_table)
  }
  return facilityDistanceRows(mws).map((row) => ({
    facility: row.label,
    distance_km: row.km,
  }))
}
