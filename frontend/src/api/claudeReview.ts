import type { ReviewBatch, ReviewCardBundle, ReviewCardSummary, FinalizeCardResponse } from '../revise-cards/types'
import { apiFetch as api } from './http'

export function fetchReviewBatches(): Promise<{ batches: ReviewBatch[] }> {
  return api('/api/claude-review/batches')
}

export function fetchReviewBatch(batchId: string): Promise<{
  batch_id: string
  cards: ReviewCardSummary[]
  totals: { cards: number; finalized_cards: number; findings: number }
}> {
  return api(`/api/claude-review/batch/${encodeURIComponent(batchId)}`)
}

export function fetchReviewCard(batchId: string, cardId: string): Promise<ReviewCardBundle> {
  return api(
    `/api/claude-review/batch/${encodeURIComponent(batchId)}/card/${encodeURIComponent(cardId)}`,
  )
}

export function finalizeReviewCard(
  cardId: string,
  body: {
    batch_id: string
    reviewer?: string
    issues: Array<{
      issue_id: string
      decision: 'handled' | 'not_handled'
      field_path?: string
      reviewer_note?: string
    }>
    user_card_edit?: Record<string, unknown> | null
  },
): Promise<FinalizeCardResponse> {
  return api(`/api/claude-review/card/${encodeURIComponent(cardId)}/finalize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
