import { appUrl } from '../appBase'

export type ReviewerAccessConfig = {
  allowed_reviewers_all: boolean
  allowed_reviewers: string[]
}

let cachedConfig: ReviewerAccessConfig | null = null

export async function fetchReviewerAccess(): Promise<ReviewerAccessConfig> {
  if (cachedConfig) return cachedConfig
  const res = await fetch(appUrl('/api/config/public'))
  if (!res.ok) {
    return { allowed_reviewers_all: true, allowed_reviewers: [] }
  }
  const data = (await res.json()) as Partial<ReviewerAccessConfig>
  cachedConfig = {
    allowed_reviewers_all: data.allowed_reviewers_all !== false,
    allowed_reviewers: Array.isArray(data.allowed_reviewers) ? data.allowed_reviewers : [],
  }
  return cachedConfig
}

export function isReviewerAllowed(name: string, config: ReviewerAccessConfig): boolean {
  const cleaned = name.trim()
  if (!cleaned) return false
  if (config.allowed_reviewers_all) return true
  return config.allowed_reviewers.includes(cleaned)
}

export function reviewerAccessHint(config: ReviewerAccessConfig): string {
  if (config.allowed_reviewers_all) return 'Any reviewer name is allowed.'
  if (!config.allowed_reviewers.length) return 'No reviewers configured.'
  return `Allowed reviewers: ${config.allowed_reviewers.join(', ')}`
}

const STORAGE_KEY = 'landscape_reviewer_name'

export function loadStoredReviewerName(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) || ''
  } catch {
    return ''
  }
}

export function storeReviewerName(name: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, name.trim())
  } catch {
    /* ignore */
  }
}
