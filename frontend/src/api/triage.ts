import { apiFetch as api } from './http'

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
  variables?: string[]
  condition?: { expression?: string; qualitative_description?: string }
  expression?: string
}

export type MissingVariableQuestion = {
  missing_variable: string
  question_to_user?: string
  how_answer_updates_diagnosis?: string
  response_type?: string
  choices?: Array<{
    id: string
    label: string
    normalized?: Record<string, unknown>
    effects?: { signals?: Array<{ signal_id: string; result: boolean }> }
  }>
}

export type EvidenceCard = {
  card_id: string
  causal_pathway?: string
  diagnostic_signals?: DiagnosticSignal[]
  confirmation_policy?: Record<string, unknown>
  missing_variable_questions?: MissingVariableQuestion[]
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

export type TriageChangedFields = {
  signals: Record<string, Array<'expression' | 'direction' | 'active'>>
  confirmation_policy?: boolean
}

export type TriageCatalogPatches = {
  schema_version: number
  catalog_filename: string
  batch_id: string
  updated_at?: string | null
  reviewer?: string | null
  cards: Record<
    string,
    {
      card_id: string
      patch: Record<string, unknown>
      changed_fields?: TriageChangedFields
      updated_at?: string
      reviewer?: string
      finalized?: boolean
      finalized_at?: string | null
      patch_stale?: boolean
      patch_discarded_reason?: string | null
      effective_changed_fields?: TriageChangedFields | null
    }
  >
}

export type DashboardChartDefaults = {
  remove_zeros?: boolean
  log_scale?: boolean
  trim_top?: boolean
  trim_bottom?: boolean
}

export type CdfRemovedBucket = {
  count: number
  mws_ids: string[]
}

export type CdfVariant = {
  trim_top: boolean
  trim_bottom: boolean
  remove_zeros: boolean
  log_scale: boolean
  cdf: [number, number][]
  sample_count: number
  x_max?: number | null
  removed: {
    zeros: CdfRemovedBucket
    top: CdfRemovedBucket
    bottom: CdfRemovedBucket
  }
}

export function cdfVariantKey(
  trimTop: boolean,
  trimBottom: boolean,
  removeZeros: boolean,
  logScale: boolean,
): string {
  return `${Number(trimTop)}${Number(trimBottom)}${Number(removeZeros)}${Number(logScale)}`
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
  cdf_variants?: Record<string, CdfVariant>
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

export function fetchTriageCard(cardId: string, catalogFilename?: string) {
  const query = catalogFilename ? `?catalog=${encodeURIComponent(catalogFilename)}` : ''
  return api<{
    card: EvidenceCard
    raw_card: EvidenceCard
    catalog_patch?: Record<string, unknown> | null
    changed_fields?: TriageChangedFields | null
    patch_stale?: boolean
    patch_discarded_reason?: string | null
    batch_id?: string | null
  }>(`/api/triage/card/${encodeURIComponent(cardId)}${query}`)
}

export function fetchTriageCatalogPatches(catalogFilename: string) {
  return api<TriageCatalogPatches>(`/api/triage/patches/${encodeURIComponent(catalogFilename)}`)
}

export function saveTriageCatalogPatches(
  catalogFilename: string,
  body: {
    reviewer: string
    cards: Array<{
      card_id: string
      diagnostic_signals: DiagnosticSignal[]
      confirmation_policy?: Record<string, unknown>
    }>
  },
) {
  return api<{
    catalog_filename: string
    batch_id: string
    saved_count: number
    card_count: number
    updated_at: string
    reviewer: string
  }>(`/api/triage/patches/${encodeURIComponent(catalogFilename)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
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
  follow_up_by_mws?: Record<string, Record<string, string>>
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

export type MwsVariableValueEntry = {
  name: string
  kind: 'scalar' | 'derived' | 'time_series' | 'static_dict' | 'list' | 'missing'
  formatted: string
  raw?: unknown
  series?: Array<{ year: number; value: unknown }>
  nested_series?: Array<{ year: string; series: string; value: unknown }>
  display_profile?: {
    type: string
    field?: string
  }
}

export type MwsVariableValuesPayload = {
  mws_id: string
  state?: string
  district?: string
  tehsil?: string
  variables: Record<string, MwsVariableValueEntry>
}

export function fetchMwsVariableValues(mwsId: string) {
  return api<MwsVariableValuesPayload>(`/api/triage/mws-variable-values/${encodeURIComponent(mwsId)}`)
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
