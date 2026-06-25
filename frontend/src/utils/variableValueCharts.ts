import type { MwsVariableValueEntry } from '../api/triage'

export type ChartRow = Record<string, string | number>

export function simpleLineData(entry: MwsVariableValueEntry): ChartRow[] {
  if (entry.series?.length) {
    return entry.series
      .map((row) => ({ label: String(row.year), value: Number(row.value) }))
      .filter((row) => Number.isFinite(row.value))
  }
  return []
}

export function seasonalLinesData(entry: MwsVariableValueEntry, field: string): ChartRow[] {
  const raw = entry.raw as Record<string, Record<string, Record<string, unknown>>> | undefined
  if (!raw) return []
  return Object.keys(raw)
    .sort((a, b) => a.localeCompare(b))
    .map((year) => {
      const seasons = raw[year] || {}
      return {
        label: year,
        kharif: Number(seasons.kharif?.[field] ?? 0),
        rabi: Number(seasons.rabi?.[field] ?? 0),
        zaid: Number(seasons.zaid?.[field] ?? 0),
      }
    })
}

export function monsoonOffsetData(entry: MwsVariableValueEntry): ChartRow[] {
  const raw = entry.raw as Record<string, string> | undefined
  if (!raw) return []
  const parsed = Object.entries(raw)
    .map(([year, iso]) => ({ year, date: new Date(String(iso)) }))
    .filter((row) => !Number.isNaN(row.date.getTime()))
  if (!parsed.length) return []

  const earliest = parsed.reduce((best, row) => {
    const md = row.date.getMonth() * 100 + row.date.getDate()
    const bestMd = best.date.getMonth() * 100 + best.date.getDate()
    return md < bestMd ? row : best
  })
  const refMonth = earliest.date.getMonth()
  const refDay = earliest.date.getDate()

  return parsed
    .map(({ year, date }) => {
      const ref = new Date(date.getFullYear(), refMonth, refDay)
      const days = Math.round((date.getTime() - ref.getTime()) / 86_400_000)
      return { label: year, value: days }
    })
    .sort((a, b) => a.label.localeCompare(b.label))
}

export function stackedDroughtData(entry: MwsVariableValueEntry): ChartRow[] {
  const raw = entry.raw as Record<string, Record<string, unknown>> | undefined
  if (!raw) return []
  return Object.keys(raw)
    .sort((a, b) => a.localeCompare(b))
    .map((year) => {
      const row = raw[year] || {}
      return {
        label: year,
        no_drought: Number(row.no_drought ?? 0),
        mild: Number(row.mild ?? 0),
        moderate: Number(row.moderate ?? 0),
        severe: Number(row.severe ?? 0),
      }
    })
}

export function stackedCroppingData(entry: MwsVariableValueEntry): ChartRow[] {
  const raw = entry.raw as Record<string, Record<string, unknown>> | undefined
  if (!raw) return []
  return Object.keys(raw)
    .sort((a, b) => a.localeCompare(b))
    .map((year) => {
      const row = raw[year] || {}
      return {
        label: year,
        single_kharif: Number(row.single_kharif ?? 0),
        single_non_kharif: Number(row.single_non_kharif ?? 0),
        double: Number(row.double ?? 0),
        triple: Number(row.triple ?? 0),
      }
    })
}

export function stackedSwbData(entry: MwsVariableValueEntry): ChartRow[] {
  const raw = entry.raw as Record<string, Record<string, unknown>> | undefined
  if (!raw) return []
  return Object.keys(raw)
    .sort((a, b) => a.localeCompare(b))
    .map((year) => {
      const row = raw[year] || {}
      return {
        label: year,
        kharif: Number(row.kharif_ha ?? 0),
        rabi: Number(row.rabi_ha ?? 0),
        zaid: Number(row.zaid_ha ?? 0),
      }
    })
}

export function stackedLulcData(entry: MwsVariableValueEntry): ChartRow[] {
  const raw = entry.raw as Record<string, Record<string, unknown>> | undefined
  if (!raw) return []
  return Object.keys(raw)
    .sort((a, b) => a.localeCompare(b))
    .map((year) => {
      const row = raw[year] || {}
      const kWater = Number(row.k_water ?? 0)
      const krWater = Number(row.kr_water ?? 0)
      const krzWater = Number(row.krz_water ?? 0)
      const crop =
        Number(row.single_kharif ?? 0) +
        Number(row.single_non_kharif ?? 0) +
        Number(row.double_crop ?? 0) +
        Number(row.triple_crop ?? 0)
      return {
        label: year,
        built_up: Number(row.built_up_area ?? 0),
        water: kWater + krWater + krzWater,
        crop,
        trees: Number(row.tree_forest ?? 0),
        shrubs: Number(row.shrub_scrub ?? 0),
        barren: Number(row.barrenland ?? 0),
      }
    })
}

export function nregaYearData(entry: MwsVariableValueEntry): ChartRow[] {
  const raw = entry.raw as Record<string, Record<string, unknown>> | undefined
  if (!raw) return []
  const categories = new Set<string>()
  for (const row of Object.values(raw)) {
    if (row && typeof row === 'object') {
      for (const key of Object.keys(row)) categories.add(key)
    }
  }
  const keys = [...categories].sort()
  return Object.keys(raw)
    .sort((a, b) => a.localeCompare(b))
    .slice(-12)
    .map((year) => {
      const row = raw[year] || {}
      const out: ChartRow = { label: year }
      for (const key of keys) {
        out[key] = Number(row[key] ?? 0)
      }
      return out
    })
}

export function categoryDictRows(entry: MwsVariableValueEntry): Array<{ key: string; value: string }> {
  const raw = entry.raw
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return []
  return Object.entries(raw as Record<string, unknown>)
    .filter(([, val]) => val !== null && val !== undefined && val !== 0 && val !== '')
    .map(([key, val]) => ({ key, value: String(val) }))
    .sort((a, b) => {
      const aNum = Number(a.key)
      const bNum = Number(b.key)
      if (Number.isFinite(aNum) && Number.isFinite(bNum)) return aNum - bNum
      return a.key.localeCompare(b.key)
    })
}

export function categoryBarData(entry: MwsVariableValueEntry): ChartRow[] {
  return categoryDictRows(entry)
    .map(({ key, value }) => ({ label: key, value: Number(value) }))
    .filter((row) => Number.isFinite(row.value))
}

const CD_TOTAL_KEY_RE = /^total(_|$)/i

export function cdBreakupBarData(entry: MwsVariableValueEntry): ChartRow[] {
  const raw = entry.raw
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return []
  return Object.entries(raw as Record<string, unknown>)
    .filter(([key, val]) => {
      if (CD_TOTAL_KEY_RE.test(key)) return false
      const num = Number(val)
      return Number.isFinite(num) && num > 0
    })
    .map(([key, val]) => ({
      label: key.replace(/_ha$/, '').replace(/_/g, ' '),
      value: Number(val),
    }))
    .sort((a, b) => b.value - a.value)
}
