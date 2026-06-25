import { apiFetch as api } from './http'

export type QueryEvalBatchSummary = {

  batch_id: string

  generated_at?: string

  updated_at?: string

  catalog?: string

  case_study_count?: number

  modes?: string[]

  dry_run?: boolean

}



export type SessionRef = {

  session_id?: string

  diagnosis_snapshot_id?: string

  log_index?: number | null

  feedback_url?: string

  elapsed_ms?: number

  llm_provider?: string

  error?: string

}



export type DimensionScore = {

  score?: number

  justification?: string

}



export type QueryEvaluation = {

  query_id?: string

  persona?: string

  eval_mode?: string

  weighted_total?: number

  summary?: string

  server_query_alignment?: string

  dimension_scores?: Record<string, DimensionScore>

  error_flags_triggered?: Array<{ flag_id?: string; detail?: string }>

  error?: string

}



export type AgreementPair = {

  kappa?: number | null

  pathway_count?: number

  exact_agreements?: number

  observed_agreement?: number

  expected_agreement?: number

  left_source?: string

  right_source?: string

}



export type AgreementSummary = {

  server_vs_ollama_independent?: AgreementPair

  server_vs_claude_independent?: AgreementPair

  ollama_vs_claude_independent?: AgreementPair

}



export type QueryRun = {

  query_id: string

  persona?: string

  query?: string

  sessions: Record<string, SessionRef>

  evaluations: Record<string, QueryEvaluation>

  agreement?: AgreementSummary

}



export type CaseStudyEval = {

  case_study_id: number

  mws_id: string

  state?: string

  district?: string

  tehsil?: string

  production_system?: string

  observed_stress?: string

  expected_pathway?: string

  stress_only?: boolean

  diagnostics_url?: string

  query_ids?: string[]

  sessions: Record<string, SessionRef>

  query_runs: QueryRun[]

}



export type QueryEvalBatch = {

  batch_id: string

  generated_at?: string

  updated_at?: string

  catalog?: string

  modes?: string[]

  case_studies: CaseStudyEval[]

}



export function fetchQueryEvalBatches() {

  return api<{ batches: QueryEvalBatchSummary[] }>('/api/query-eval/batches')

}



export function fetchQueryEvalBatch(batchId: string) {

  return api<QueryEvalBatch>(`/api/query-eval/batch/${encodeURIComponent(batchId)}`)

}


