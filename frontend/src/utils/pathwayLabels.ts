import type { PathwayResult } from '../types'

const PRODUCTION_SYSTEM_LABELS: Record<string, string> = {
  Agriculture: 'Agriculture',
  Livestock: 'Livestock',
  NTFP_Forest_Biodiversity: 'Forestry, biodiversity, NTFP',
  Fishery: 'Fishery',
  Socio_Economic: 'Socio-economic',
}

const OBSERVED_STRESS_LABELS: Record<string, string> = {
  water_scarcity: 'Water scarcity',
  crop_failure: 'Crop failure',
  market_access_gap: 'Market access gap',
  livestock_decline: 'Livestock decline',
  ntfp_decline: 'NTFP decline',
  biodiversity_loss: 'Biodiversity loss',
  wildlife_conflict: 'Wildlife conflict',
  low_fish_productivity: 'Low fish productivity',
  economic_hardship: 'Economic hardship',
  low_income: 'Low income',
}

function titleCaseWords(value: string): string {
  return value
    .split('_')
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

function productionLabel(value: string | undefined): string | null {
  if (!value) return null
  return PRODUCTION_SYSTEM_LABELS[value] ?? titleCaseWords(value)
}

function stressLabel(value: string | undefined): string | null {
  if (!value) return null
  return OBSERVED_STRESS_LABELS[value] ?? titleCaseWords(value)
}

function pathwayLabel(value: string): string {
  return titleCaseWords(value)
}

export function formatPathwayHierarchy(pathway: Pick<PathwayResult, 'pathway_id' | 'production_system' | 'observed_stress'>): string {
  const parts = [
    productionLabel(pathway.production_system),
    stressLabel(pathway.observed_stress),
    pathwayLabel(pathway.pathway_id),
  ].filter(Boolean)
  return parts.join(' -> ')
}

function formatAerTagList(tags: string[] | undefined): string {
  if (!tags?.length) return '—'
  return tags.join(', ')
}

export type AerAlignment = 'exact' | 'neighbor' | 'mismatch' | 'unknown'

export function classifyPathwayAerAlignment(
  pathway: Pick<PathwayResult, 'aer_tags'>,
  mwsAerCode?: string | null,
  retrievalAerTags?: string[] | null,
): AerAlignment {
  const tags = pathway.aer_tags?.filter(Boolean) ?? []
  if (!mwsAerCode || tags.length === 0) return 'unknown'
  if (tags.includes(mwsAerCode)) return 'exact'
  const retrieval = new Set((retrievalAerTags ?? []).filter(Boolean))
  if ([...retrieval].some((tag) => tags.includes(tag))) return 'neighbor'
  return 'mismatch'
}

function overlappingRetrievalTags(
  cardTags: string[] | undefined,
  retrievalAerTags: string[] | undefined,
): string[] {
  const retrieval = new Set((retrievalAerTags ?? []).filter(Boolean))
  return (cardTags ?? []).filter((tag) => retrieval.has(tag))
}

export function formatPathwayAerContext(
  pathway: Pick<PathwayResult, 'aer_tags'>,
  mwsAerCode?: string | null,
  retrievalAerTags?: string[] | null,
): { text: string; alignment: AerAlignment; note: string | null } {
  const alignment = classifyPathwayAerAlignment(pathway, mwsAerCode, retrievalAerTags)
  const evidenceAer = formatAerTagList(pathway.aer_tags)
  const parts = [`Evidence AER: ${evidenceAer}`]
  if (mwsAerCode) parts.push(`MWS AER: ${mwsAerCode}`)

  let note: string | null = null
  if (alignment === 'neighbor') {
    const overlap = overlappingRetrievalTags(pathway.aer_tags, retrievalAerTags ?? undefined)
    note =
      overlap.length > 0
        ? `Neighbor proxy via ${overlap.join(', ')}`
        : 'Neighbor proxy (expanded retrieval set)'
  } else if (alignment === 'mismatch') {
    note = 'Card AER tags do not overlap the retrieval neighbor set'
  }

  return { text: parts.join(' · '), alignment, note }
}
