import type {
  DiagnosisResponse,
  FeedbackContext,
  FeedbackDocument,
  FollowUpExchange,
  MwsDocument,
} from '../types'
import { apiFetch as api } from './http'

export function fetchFeedbackContext(snapshotId: string, logIndex?: number | null): Promise<FeedbackContext> {
  const q = new URLSearchParams({ snapshot_id: snapshotId })
  if (typeof logIndex === 'number' && logIndex >= 0) {
    q.set('log_index', String(logIndex))
  }
  return api(`/api/feedback/context?${q}`)
}

export function buildFeedbackPageUrl(options: {
  snapshotId: string
  logIndex?: number | null
  focus?: 'pathway' | 'summary' | 'solutions'
  pathwayId?: string
}): string {
  const params = new URLSearchParams({ snapshot_id: options.snapshotId })
  if (typeof options.logIndex === 'number' && options.logIndex >= 0) {
    params.set('log_index', String(options.logIndex))
  }
  if (options.focus) params.set('focus', options.focus)
  if (options.pathwayId) params.set('pathway_id', options.pathwayId)
  return `/feedback?${params}`
}

export function fetchSavedFeedback(snapshotId: string, email: string): Promise<FeedbackDocument> {
  const q = new URLSearchParams({ email })
  return api(`/api/feedback/saved/${encodeURIComponent(snapshotId)}?${q}`)
}

export function saveFeedback(
  snapshotId: string,
  payload: {
    reviewer: { name: string; email: string }
    sections: Record<string, unknown>
    session_id: string
    follow_up_count: number
    turn_no?: number | null
    log_index?: number | null
    mws_uid: string
  },
): Promise<FeedbackDocument> {
  return api(`/api/feedback/saved/${encodeURIComponent(snapshotId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export type { DiagnosisResponse, FollowUpExchange, MwsDocument }
