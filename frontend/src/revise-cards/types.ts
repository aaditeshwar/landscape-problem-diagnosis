export type DimensionScore = {
  score: 'pass' | 'warn' | 'fail'
  note?: string
}

export type ReviewFinding = {
  issue_id: string
  dimension: string
  severity: 'info' | 'warn' | 'error'
  field_path: string
  current_value: unknown
  current_from_card?: unknown
  evidence_from_note?: string
  explanation: string
  reviewer_confidence?: 'high' | 'medium' | 'low'
  suggested_patch?: Record<string, unknown>
  composite_key: string
  dict_key_issues?: Array<{
    variable: string
    key_used: string
    issue: string
    canonical_key?: string
    message: string
  }>
  decision?: {
    decision: 'handled' | 'not_handled'
    reviewer_note?: string
    decided_at?: string
  } | null
  edited_patch?: Record<string, unknown> | null
}

export type ReviewBatch = {
  batch_id: string
  generated_at?: string
  pathway_filter?: string
  model?: string
  card_count: number
  finalized_card_count: number
}

export type ReviewCardSummary = {
  card_id: string
  overall_score: string
  dimensions: Record<string, DimensionScore>
  finding_count: number
  handled_count: number
  not_handled_count: number
  decided_count: number
  pending_count: number
  finalized: boolean
  finalized_at?: string | null
  has_edits?: boolean
}

export type ReviewCardBundle = {
  batch_id: string
  card_id: string
  overall_score?: string
  dimensions: Record<string, DimensionScore>
  summary?: string
  overall_reasoning_note?: string | null
  findings: ReviewFinding[]
  raw_card?: Record<string, unknown> | null
  user_card_edit?: Record<string, unknown> | null
  user_card_edit_status?: {
    has_saved_edit: boolean
    propagated_at?: string | null
    in_sync_with_raw_card: boolean
    last_saved_at?: string | null
  }
  finalized: boolean
  finalized_at?: string | null
}

export type SignalEditDraft = {
  signal_id: string
  variables: string
  expression: string
  qualitative_description: string
  severity: string
  direction: string
}

export type FollowUpQuestionDraft = {
  missing_variable: string
  question_to_user: string
  how_answer_updates_diagnosis: string
  question_mode: string
  choices_json: string
}

export type UserCardEditDraft = {
  overall_reasoning_note: string
  confirmation_policy_json: string
  signals: Record<string, SignalEditDraft>
  follow_up_questions: FollowUpQuestionDraft[]
  dirty: boolean
}

export type IssueDraft = {
  issue_id: string
  field_path: string
  decision: 'pending' | 'handled' | 'not_handled'
  reviewer_note: string
}

export type FinalizeCardResponse = {
  card_id: string
  finalized_at: string
  handled_count: number
  not_handled_count: number
  user_edit_saved: boolean
  user_edit_status_changed?: boolean
  decisions_path: string
  edited_patches_path: string
  user_card_edits_path: string
}
