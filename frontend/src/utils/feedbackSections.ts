import type { FeedbackSectionDraft, RetrievedEvidenceCard } from '../types'

export type AgreementValue = 'agree' | 'partial' | 'disagree'

export const AGREEMENT_OPTIONS: Array<{ value: AgreementValue; label: string }> = [
  { value: 'agree', label: 'Agree' },
  { value: 'partial', label: 'Partially agree' },
  { value: 'disagree', label: 'Disagree' },
]

export function pathwaySectionKey(pathwayId: string): string {
  return `pathway:${pathwayId}`
}

export function feedbackSectionDomId(sectionKey: string): string {
  if (sectionKey === 'summary') return 'feedback-section-summary'
  if (sectionKey === 'solutions') return 'feedback-section-solutions'
  if (sectionKey.startsWith('pathway:')) {
    return `feedback-section-pathway-${sectionKey.slice('pathway:'.length).replace(/[^\w-]+/g, '-')}`
  }
  return `feedback-section-${sectionKey.replace(/[^\w-]+/g, '-')}`
}

export function focusParamToDomId(focus: string, pathwayId?: string | null): string | null {
  if (focus === 'pathway' && pathwayId) return feedbackSectionDomId(pathwaySectionKey(pathwayId))
  if (focus === 'summary') return feedbackSectionDomId('summary')
  if (focus === 'solutions') return feedbackSectionDomId('solutions')
  return null
}

export function cardForPathway(
  cards: RetrievedEvidenceCard[],
  pathwayId: string,
): RetrievedEvidenceCard | undefined {
  return cards.find(
    (card) =>
      card.pathway_id === pathwayId ||
      card.causal_pathway === pathwayId ||
      card.card_id.startsWith(`${pathwayId}__`),
  )
}

export function buildSignalEditorUrl(options: {
  clusterSuffix?: string | null
  pathway?: string | null
  cardId?: string | null
  snapshotId: string
  returnUrl: string
}): string | null {
  if (!options.clusterSuffix && !options.cardId) return null
  const params = new URLSearchParams({ snapshot_id: options.snapshotId })
  if (options.clusterSuffix) params.set('cluster', options.clusterSuffix)
  if (options.pathway) params.set('pathway', options.pathway)
  if (options.cardId) params.set('card_id', options.cardId)
  params.set('return', options.returnUrl)
  return `/signals?${params}`
}

export function mergeSectionDraft(
  sections: Record<string, FeedbackSectionDraft>,
  sectionKey: string,
  patch: Partial<FeedbackSectionDraft>,
): Record<string, FeedbackSectionDraft> {
  return {
    ...sections,
    [sectionKey]: {
      ...sections[sectionKey],
      ...patch,
    },
  }
}
