import type {
  DiagnosisResponse,
  FeedbackContext,
  FeedbackDocument,
  FollowUpExchange,
  MwsDocument,
} from '../types'

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    let detail = await res.text()
    try {
      const parsed = JSON.parse(detail) as { detail?: string | Array<{ msg?: string }> }
      if (typeof parsed.detail === 'string') detail = parsed.detail
      else if (Array.isArray(parsed.detail)) detail = parsed.detail.map((d) => d.msg).filter(Boolean).join('; ')
    } catch {
      /* keep raw text */
    }
    throw new Error(detail || `${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

export function fetchFeedbackContext(snapshotId: string): Promise<FeedbackContext> {
  const q = new URLSearchParams({ snapshot_id: snapshotId })
  return api(`/api/feedback/context?${q}`)
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

export function buildFeedbackPageUrl(options: {
  snapshotId: string
  focus?: 'pathway' | 'summary' | 'solutions'
  pathwayId?: string
}): string {
  const params = new URLSearchParams({ snapshot_id: options.snapshotId })
  if (options.focus) params.set('focus', options.focus)
  if (options.pathwayId) params.set('pathway_id', options.pathwayId)
  return `/feedback?${params}`
}

export type { DiagnosisResponse, FollowUpExchange, MwsDocument }
