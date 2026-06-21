export interface TehsilProperties {
  state: string
  district: string
  tehsil: string
  mws_count?: number
}

export interface GeoFeature<P = Record<string, unknown>> {
  type: 'Feature'
  properties: P
  geometry: GeoJSON.Geometry
}

export interface FeatureCollection<P = Record<string, unknown>> {
  type: 'FeatureCollection'
  features: GeoFeature<P>[]
}

export type TehsilFeatureCollection = FeatureCollection<TehsilProperties>

export type MwsFeatureCollection = FeatureCollection<{
  uid: string
  state: string
  district: string
  tehsil: string
}>

export interface TehsilRef {
  state: string
  district: string
  tehsil: string
}

export interface IngestedTehsil {
  id: string
  mws_count?: number
  village_count?: number
}

export interface LocateResult {
  lon: number
  lat: number
  found: boolean
  mws_uid?: string
  village_id?: number
  state?: string
  district?: string
  tehsil?: string
}

export interface PathwayResult {
  pathway_id: string
  confidence: string
  reasoning?: string
  production_system?: string
  observed_stress?: string
  card_id?: string
  aer_tags?: string[]
  card_rainfall_regime?: string
  missing_variable_questions?: Array<{ variable: string; question: string }>
}

export interface PathwayChange {
  pathway_id: string
  from: string
  to: string
  reason: string
  interpretation?: string
}

export interface FollowUpSignalUpdate {
  pathway_id: string
  signal_id?: string
  variable?: string
  direction?: string
  result?: boolean | null
  inference?: 'evaluated' | 'unable_to_evaluate' | string
  inference_note?: string
  user_answer?: string
  update_interpretation?: string
  update_rule?: string
}

export interface PathwayInterpretation {
  pathway_id: string
  status: 'confirmed' | 'uncertain' | string
  reasoning: string
}

export interface PathwaySignalSummary {
  pathway_id?: string
  signal_id?: string
  direction?: string
  result?: boolean | null
  status?: string
  expression?: string
  qualitative_hint?: string
  user_answer?: string
  update_interpretation?: string
  update_rule?: string
  answered_variable?: string
  inference?: string
  inference_note?: string
}

export interface SignalEvaluationPathway {
  pathway_id: string
  summary?: Record<string, unknown>
  evidence_note?: string | null
  signals: PathwaySignalSummary[]
}

export interface SignalEvaluation {
  pathways: SignalEvaluationPathway[]
}

export interface DiagnosisRevision {
  improved: boolean
  summary: string | null
  pathway_changes: PathwayChange[]
  pathway_interpretations?: PathwayInterpretation[]
}

export interface FollowUpMcqChoice {
  id: string
  label: string
}

export interface FollowUpMcq {
  variable: string
  question: string
  choices: FollowUpMcqChoice[]
}

export interface ReviewerSignalNote {
  signal_id: string
  server_result?: boolean | null
  comment?: string
}

export interface ReviewerPathwayComment {
  pathway_id: string
  agreement: string
  signal_notes?: ReviewerSignalNote[]
  pathway_comment?: string
}

export interface ChangeReview {
  summary?: string
  agrees_with_revision?: boolean
}

export interface SkippedProductionSystem {
  production_system: string
  rule_id?: string
  message?: string
  expression?: string
  tree_cover_percent_mws?: number
  [key: string]: unknown
}

export interface DiagnosisResponse {
  session_id: string
  diagnosis_snapshot_id?: string
  follow_up_count?: number
  turn_no?: number
  log_index?: number | null
  mws_aer_code?: string | null
  retrieval_aer_tags?: string[]
  confirmed_pathways: PathwayResult[]
  uncertain_pathways: PathwayResult[]
  solutions: string[]
  panel_updates: string[]
  panel_update_explanation?: string | null
  follow_up_question?: string | null
  follow_up_variable?: string | null
  follow_up_mcq?: FollowUpMcq | null
  diagnosis_revision?: DiagnosisRevision | null
  follow_up_signal_updates?: FollowUpSignalUpdate[]
  pathway_retrieval_ranks?: Record<string, number>
  signal_evaluation?: SignalEvaluation | null
  want_llm_opinion?: boolean
  llm_skipped?: boolean
  skipped_production_systems?: SkippedProductionSystem[]
  reviewer_commentary?: ReviewerPathwayComment[]
  change_review?: ChangeReview | null
  solutions_review_notes?: string | null
}

export interface FollowUpExchange {
  question: string
  answer: string
  variable?: string
  mcq?: FollowUpMcq | null
  /** @deprecated retained for diagnosis panel only */
  actions?: string[]
  explanation?: string | null
  revision?: DiagnosisRevision | null
  signalUpdates?: FollowUpSignalUpdate[]
  signalEvaluation?: SignalEvaluation | null
}

export interface MwsDocument {
  uid: string
  state: string
  district: string
  tehsil: string
  tehsils?: TehsilRef[]
  area_ha?: number
  nbss_lup_aer_code?: string
  nbss_lup_aer_name?: string
  agro_ecological_zone?: string
  rainfall_regime?: string
  rainfall_mm_band?: string
  aquifer?: {
    raw_class?: string
    acwadam_class?: string
    lithology_percent?: Record<string, number>
  }
  terrain?: {
    cluster_id?: number
    description?: string
    plain_percent?: number
    slopy_percent?: number
  }
  soge?: {
    dev_percent?: number
    class_name?: string
  }
  river_name?: string | null
  canal?: { canal_name?: string; project_name?: string } | null
  hydrological_annual?: Record<
    string,
    {
      precipitation_mm?: number
      delta_g_mm?: number
      well_depth_m?: number
      et_mm?: number
      runoff_mm?: number
    }
  >
  cropping_intensity?: Record<
    string,
    | number
    | {
        cropping_intensity?: number
        single_crop_ha?: number
        double_crop_ha?: number
        triple_crop_ha?: number
      }
  >
  drought_kharif?: Record<
    string,
    {
      no_drought_weeks?: number
      mild_weeks?: number
      moderate_weeks?: number
      severe_weeks?: number
      dry_spell_weeks?: number
    }
  >
  swb_annual?: Record<
    string,
    { total_ha?: number; kharif_ha?: number; rabi_ha?: number; zaid_ha?: number }
  >
  swb_count?: number
  swb_intersect?: Array<{ swb_uid?: string; name?: string; lat?: number; lon?: number }>
  lulc_ha?: Record<string, Record<string, number>>
  change_detection?: Record<string, Record<string, number>>
  intersect_villages?: {
    village_ids?: number[]
    details?: Record<string, { area_intersect?: number; percentage_of_area?: number }>
  }
  intersect_village_names?: Array<{
    village_id: number
    name?: string
    population?: number
    sc_percent?: number
    st_percent?: number
    literacy_rate_percent?: number
    area_intersect_ha?: number
    percent_of_mws?: number
  }>
  village_aggregates?: Record<string, number>
  facility_distances?: {
    dist_apmc_km?: number
    dist_bank_km?: number
    dist_dairy_km?: number
    dist_phc_km?: number
    dist_chc_km?: number
    dist_sub_centre_km?: number
    dist_district_hospital_km?: number
    dist_school_primary_km?: number
    dist_school_secondary_km?: number
    dist_college_km?: number
    dist_csc_km?: number
    dist_pds_km?: number
    dist_cooperative_km?: number
    dist_markets_trading_km?: number
    dist_storage_warehousing_km?: number
    dist_agri_processing_km?: number
  }
  facility_distance_table?: Array<{ facility: string; distance_km: number }>
  nrega_mws?: Record<string, Record<string, number>>
}

export interface FeedbackSectionDraft {
  server_agreement?: string | null
  llm_agreement?: string | null
  free_text?: string | null
  linked_card_id?: string | null
  linked_cluster_suffix?: string | null
}

export interface FeedbackDocument {
  diagnosis_snapshot_id: string
  session_id: string
  follow_up_count: number
  turn_no?: number | null
  log_index?: number | null
  reviewer: { name: string; email: string }
  mws_uid: string
  updated_at: string
  sections: Record<string, FeedbackSectionDraft>
}

export interface CardDiagnosticSignal {
  signal_id: string
  active?: boolean
  direction?: string
}

export interface RetrievedEvidenceCard {
  card_id: string
  pathway_id: string
  cluster_suffix?: string | null
  production_system?: string
  observed_stress?: string
  causal_pathway?: string
  diagnostic_signals?: CardDiagnosticSignal[]
}

export interface FeedbackContext {
  session_id: string
  diagnosis_snapshot_id: string
  follow_up_count: number
  turn_no?: number | null
  log_index?: number | null
  mws_uid: string
  mws_doc: MwsDocument
  want_llm_opinion: boolean
  llm_skipped: boolean
  follow_up_history: FollowUpExchange[]
  server_diagnosis: {
    confirmed_pathways: PathwayResult[]
    uncertain_pathways: PathwayResult[]
    summary?: string | null
    solutions: string[]
    signal_evaluation?: SignalEvaluation | null
    pathway_notes: Record<string, string>
    panel_updates: string[]
    panel_update_explanation?: string | null
  }
  llm_diagnosis?: {
    reviewer_commentary?: ReviewerPathwayComment[]
    change_review?: ChangeReview | null
    solutions_review_notes?: string | null
  } | null
  retrieved_cards: RetrievedEvidenceCard[]
  context_clusters: Record<string, unknown>
  skipped_production_systems?: SkippedProductionSystem[]
}
