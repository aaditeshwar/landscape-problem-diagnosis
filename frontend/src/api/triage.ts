async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    let detail = await res.text()
    try {
      const parsed = JSON.parse(detail) as { detail?: string }
      if (typeof parsed.detail === 'string') detail = parsed.detail
    } catch {
      /* keep raw */
    }
    throw new Error(detail || `${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

export type CaseStudyCatalog = { filename: string; path: string }

export type CaseStudyInstance = {
  case_study_id: number
  mws_id: string
  lat?: number
  lng?: number
  production_system: string
  observed_stress: string
  expected_pathway: string | null
  stress_only: boolean
  state?: string
  district?: string
  tehsil?: string
}

export type TriageSection = {
  section_key: string
  production_system: string
  observed_stress: string
  actual_pathways: string[]
  matrix_pathways?: string[]
  matrix_columns?: string[]
  predicted_pathways: string[]
  instances: CaseStudyInstance[]
}

export type CatalogBundle = {
  filename: string
  instance_count: number
  sections: TriageSection[]
}

export type DiagnosticSignal = {
  signal_id: string
  direction?: string
  active?: boolean
  condition?: { expression?: string }
  expression?: string
}

export type EvidenceCard = {
  card_id: string
  causal_pathway?: string
  diagnostic_signals?: DiagnosticSignal[]
  confirmation_policy?: Record<string, unknown>
}

export type CardMapResponse = {
  mws_id: string
  found: boolean
  cards_by_pathway: Record<string, { card_id?: string }>
  cards_full: Record<string, EvidenceCard>
}

export type EvaluateSectionResult = {
  production_system: string
  observed_stress: string
  instances: Array<{
    case_study_id: number
    mws_id: string
    actual_pathway: string
    predicted_pathway: string
    predicted_status: string
    confirmed_pathways?: string[]
    match: boolean
    card_id?: string
    signals: Array<Record<string, unknown>>
  }>
  matrix: {
    row_pathways?: string[]
    cells: Array<{
      matrix_row_pathway?: string
      actual_pathway: string
      predicted_pathway: string
      classification?: 'tp' | 'fp' | 'tn' | 'fn'
      instance: {
        case_study_id: number
        mws_id: string
        tehsil?: string
        match: boolean
        predicted_status: string
        catalog_pathway?: string
      }
    }>
  }
  variable_table: {
    access_keys: string[]
    columns: Array<{ case_study_id: number; mws_id: string; card_id?: string }>
    rows: Array<{
      access: string
      values: Array<{ case_study_id: number; mws_id?: string; formatted: string }>
    }>
  }
  signal_grid?: {
    pathways: Array<{
      pathway_id: string
      cards: Array<{
        card_id: string
        mws_columns: Array<{
          mws_id: string
          case_study_id: number
          state?: string
          district?: string
          tehsil?: string
          actual_pathway?: string
          actual_matches_pathway?: boolean
          pathway_confirmed?: boolean
          classification?: 'tp' | 'fp' | 'tn' | 'fn'
          production_gated?: boolean
          signals: Record<string, { result?: unknown; status?: unknown; variable_values?: Array<{ access: string; formatted: string }> }>
        }>
      }>
    }>
  }
}

export type DashboardChartDefaults = {
  remove_zeros?: boolean
  log_scale?: boolean
  trim_top?: boolean
  trim_bottom?: boolean
}

export type DashboardChartDefaultsManifest = {
  version: number
  variables: Record<string, DashboardChartDefaults>
}

export type DashboardVariable = {
  access: string
  chart_type: 'cdf' | 'categorical'
  unit?: string
  sample_count?: number
  cdf?: [number, number][]
  x_max?: number | null
  samples?: Array<{ mws_id: string; value: number }>
  distribution?: Array<{ label: string; count: number; percent: number }>
}

export type DashboardVariableGroup = {
  category: string
  variables: DashboardVariable[]
}

export type DashboardSection = {
  section_key: string
  production_system: string
  observed_stress: string
  mws_count: number
  variable_groups?: DashboardVariableGroup[]
  variables: Record<string, DashboardVariable>
}

export function fetchTriageCatalogs() {
  return api<{ catalogs: CaseStudyCatalog[] }>('/api/triage/catalogs')
}

export function fetchTriageCatalog(filename: string) {
  return api<CatalogBundle>(`/api/triage/catalog/${encodeURIComponent(filename)}`)
}

export function fetchCardMap(mwsId: string) {
  return api<CardMapResponse>(`/api/triage/card-map?mws_id=${encodeURIComponent(mwsId)}`)
}

export function fetchTriageCard(cardId: string) {
  return api<{ card: EvidenceCard; draft: Record<string, unknown> | null }>(
    `/api/triage/card/${encodeURIComponent(cardId)}`,
  )
}

export function evaluateTriageSection(body: {
  production_system: string
  observed_stress: string
  instances: CaseStudyInstance[]
  card_edits: Array<{
    card_id: string
    diagnostic_signals?: DiagnosticSignal[]
    confirmation_policy?: Record<string, unknown>
  }>
}) {
  return api<EvaluateSectionResult>('/api/triage/evaluate-section', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function saveTriageDraft(
  cardId: string,
  body: {
    diagnostic_signals: DiagnosticSignal[]
    confirmation_policy?: Record<string, unknown>
    section?: { production_system: string; observed_stress: string }
  },
) {
  return api(`/api/triage/drafts/${encodeURIComponent(cardId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function fetchDashboardManifest() {
  return api<{ sections: Array<{ section_key: string; filename: string }> }>('/api/triage/dashboard/manifest')
}

export function fetchDashboardChartDefaults() {
  return api<DashboardChartDefaultsManifest>('/api/triage/dashboard/chart-defaults')
}

export function fetchDashboardSection(sectionKey: string) {
  return api<DashboardSection>(`/api/triage/dashboard/${encodeURIComponent(sectionKey)}`)
}

export type VariableCatalogEntry = {
  name: string
  display_type?: string
  type?: string
  shape?: string
  unit?: string
  availability?: string
  source?: string
  description?: string
  computation?: string
  source_sheet?: string
  signal_usages: Array<{
    card_id: string
    signal_id: string
    access: string
    expression: string
  }>
}

export type VariableCatalogSection = {
  category: string
  variables: VariableCatalogEntry[]
}

export function fetchVariableCatalog() {
  return api<{
    dictionary_version?: string
    variable_count: number
    sections: VariableCatalogSection[]
  }>('/api/triage/variable-catalog')
}

export const NONE_OF_THESE = '__none_of_these__'
export const STRESS_ONLY = '__stress_only__'

export function pathwayLabel(pathway: string): string {
  if (pathway === NONE_OF_THESE) return 'None of these'
  if (pathway === STRESS_ONLY) return 'Stress only'
  return pathway.replace(/_/g, ' ')
}

export function diagnosisMwsUrl(instance: Pick<CaseStudyInstance, 'mws_id' | 'state' | 'district' | 'tehsil'>): string {
  const params = new URLSearchParams({ mws: instance.mws_id })
  if (instance.state) params.set('state', instance.state)
  if (instance.district) params.set('district', instance.district)
  if (instance.tehsil) params.set('tehsil', instance.tehsil)
  return `/?${params.toString()}`
}

export function dashboardSectionUrl(productionSystem: string, observedStress: string, sectionKey: string): string {
  const params = new URLSearchParams({
    production_system: productionSystem,
    observed_stress: observedStress,
  })
  return `/dashboard?${params.toString()}#${sectionKey}`
}
