async function api<T>(path: string): Promise<T> {
  const res = await fetch(path)
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

export interface PublicConfig {
  cluster_cog_url?: string | null
  cluster_cog_viewer_url?: string | null
  remote_cluster_cog_url?: string | null
}

export interface ClusterPaletteEntry {
  value: number
  suffix?: string | null
  label: string
  color: string
  alpha?: number
  cluster?: ContextCluster | null
}

export interface ContextCluster {
  suffix: string
  label: string
  aquifer_types?: string[]
  aer_tags?: string[]
  rainfall_regime?: string
  agro_climatic_zones?: string[]
  terrain_types?: string[]
  geographic_examples?: string[]
}

export interface EvidenceCardSummary {
  card_id: string
  production_system?: string
  observed_stress?: string
  causal_pathway?: string
  pathway_id?: string
  cluster_suffix?: string
  pathway_tags?: string[]
}

export interface DiagnosticSignal {
  signal_id: string
  variables?: string[]
  condition?: Record<string, unknown>
  severity?: string
  direction?: string
  explanation?: string
  active?: boolean
}

export interface ConfounderEntry {
  confounder: string
  how_to_distinguish?: string
}

export interface FollowUpChoice {
  id?: string
  label?: string
  normalized?: Record<string, unknown>
  effects?: { signals?: Array<{ signal_id?: string; result?: boolean }> }
}

export interface MissingVariableQuestion {
  missing_variable?: string
  question_to_user?: string
  how_answer_updates_diagnosis?: string
  response_type?: string
  question_mode?: string
  choices?: FollowUpChoice[]
}

export interface ConfirmationPolicy {
  version?: number
  primary_confirm_signals?: string[]
  confirm_when?: Record<string, unknown>
  confidence_when?: Array<Record<string, unknown>>
}

export interface EvidenceCardDocument extends EvidenceCardSummary {
  context?: Record<string, unknown>
  diagnostic_signals?: DiagnosticSignal[]
  confirmation_policy?: ConfirmationPolicy
  overall_reasoning_note?: string
  confounders?: ConfounderEntry[]
  missing_variable_questions?: MissingVariableQuestion[]
}

export interface EditableSignalRow {
  signal_id: string
  active: boolean
  severity: string
  direction: string
  explanation: string
  qualitative_description: string
  expression: string
  condition_type: string
  variables: string[]
}

export interface EditableFollowUpChoice {
  id: string
  label: string
  normalizedJson: string
  effectsJson: string
}

export interface EditableFollowUpQuestion {
  missing_variable: string
  question_mode: string
  question_to_user: string
  how_answer_updates_diagnosis: string
  response_type: string
  choices: EditableFollowUpChoice[]
}

export interface SignalEditorDraft {
  signals: EditableSignalRow[]
  confirmationPolicyJson: string
  overallReasoningNote: string
  confounders: ConfounderEntry[]
  followUpQuestions: EditableFollowUpQuestion[]
}

export function fetchPublicConfig(): Promise<PublicConfig> {
  return api('/api/config/public')
}

export interface ClusterRasterQueryResult {
  lat: number
  lon: number
  raster_value: number
  cluster_suffix: string | null
  cluster_label?: string | null
  cluster?: ContextCluster | null
}

export function fetchClusterRasterQuery(lat: number, lon: number): Promise<ClusterRasterQueryResult> {
  const params = new URLSearchParams({
    lat: String(lat),
    lon: String(lon),
  })
  return api(`/api/clusters/raster-query?${params.toString()}`)
}

export function fetchClusterPalette(): Promise<{ palette: ClusterPaletteEntry[] }> {
  return api('/api/clusters/palette')
}

export function fetchCardsByCluster(suffix: string): Promise<{ suffix: string; cards: EvidenceCardSummary[] }> {
  return api(`/api/evidence-cards/by-cluster/${encodeURIComponent(suffix)}`)
}

export function fetchEvidenceCard(cardId: string): Promise<EvidenceCardDocument> {
  return api(`/api/evidence-cards/card/${encodeURIComponent(cardId)}`)
}

export function suffixFromRasterValue(value: number): string | null {
  if (!Number.isFinite(value) || value <= 0) return null
  return String(Math.round(value)).padStart(3, '0')
}

export function clusterSuffixFromCardId(cardId: string): string | null {
  const match = cardId.match(/__(\d{3})$/)
  return match?.[1] ?? null
}
