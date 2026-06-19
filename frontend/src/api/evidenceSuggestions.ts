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

export interface EvidenceSuggestionsDocument {
  card_id: string
  cluster_suffix?: string
  pathway_id?: string
  reviewer: { name: string; email: string }
  updated_at: string
  suggestions?: {
    signals?: SignalSuggestion[]
    confirmation_policy?: ConfirmationPolicy | null
    overall_reasoning_note?: string | null
    confounders?: Array<{ confounder: string; how_to_distinguish: string }>
    follow_up_questions?: FollowUpQuestionSuggestion[]
  }
  provenance?: Record<string, unknown>
}

export interface SignalSuggestion {
  signal_id: string
  active?: boolean
  severity?: string
  direction?: string
  explanation?: string
  qualitative_description?: string
}

export interface ConfirmationPolicy {
  version?: number
  primary_confirm_signals?: string[]
  confirm_when?: Record<string, unknown>
  confidence_when?: Array<Record<string, unknown>>
}

export interface FollowUpQuestionSuggestion {
  missing_variable?: string
  question_mode?: string
  question_to_user?: string
  how_answer_updates_diagnosis?: string
  response_type?: string
  choices?: Array<{
    id?: string
    label?: string
    normalized?: Record<string, unknown>
    effects?: Record<string, unknown>
  }>
}

export function fetchEvidenceSuggestions(cardId: string, email: string): Promise<EvidenceSuggestionsDocument> {
  const params = new URLSearchParams({ email: email.trim() })
  return api(`/api/evidence-suggestions/${encodeURIComponent(cardId)}?${params}`)
}

export function saveEvidenceSuggestions(
  cardId: string,
  body: {
    reviewer: { name: string; email: string }
    suggestions: EvidenceSuggestionsDocument['suggestions']
    cluster_suffix?: string | null
    pathway_id?: string | null
    provenance?: Record<string, unknown>
  },
): Promise<EvidenceSuggestionsDocument> {
  return api(`/api/evidence-suggestions/${encodeURIComponent(cardId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
