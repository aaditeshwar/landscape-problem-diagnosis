/** Short labels and tooltip text from scripts/reference/evaluation_rubric.json */

export type RubricHintEntry = {
  id: string
  name: string
  description: string
  weight?: number
  penalty?: number
}

export const RUBRIC_DIMENSIONS: Record<string, RubricHintEntry> = {
  D1: {
    id: 'D1',
    name: 'Query relevance',
    weight: 0.2,
    description:
      'Do confirmed/uncertain pathways, solutions, and follow-ups address what the user asked? Off-topic production systems or stresses score low.',
  },
  D2: {
    id: 'D2',
    name: 'Variable grounding',
    weight: 0.25,
    description:
      'Reasoning must cite available MWS variables with values, units, or trends — not vague claims without data dictionary variables.',
  },
  D3: {
    id: 'D3',
    name: 'Reasoning correctness',
    weight: 0.25,
    description:
      'Inference direction must be hydrologically/ecologically sound (e.g. negative delta_g → depletion). Wrong direction or contradictions score low.',
  },
  D4: {
    id: 'D4',
    name: 'Appropriate uncertainty',
    weight: 0.1,
    description:
      'Pathways needing missing variables belong in uncertain_pathways; confidence levels should match corroborating evidence.',
  },
  D5: {
    id: 'D5',
    name: 'Follow-up question',
    weight: 0.1,
    description:
      'Follow-up should resolve the top uncertainty in plain language for the persona, and must not ask for variables already in MWS data.',
  },
  D6: {
    id: 'D6',
    name: 'Solution relevance',
    weight: 0.1,
    description:
      'Solutions must match confirmed pathways and be actionable at MWS scale for aquifer/terrain context — not generic advice.',
  },
}

export const RUBRIC_ERROR_FLAGS: Record<string, RubricHintEntry> = {
  EF1: {
    id: 'EF1',
    name: 'Variable hallucination',
    penalty: -0.1,
    description: 'Reasoning cites a variable name not in data_dictionary_v2.json.',
  },
  EF2: {
    id: 'EF2',
    name: 'Not-available variable as fact',
    penalty: -0.1,
    description:
      'A confirmed pathway treats a not_available variable (e.g. borewell_density) as known without user input.',
  },
  EF3: {
    id: 'EF3',
    name: 'Wrong inference direction',
    penalty: -0.1,
    description:
      'Direction of change contradicts the variable (e.g. positive cumulative_g cited as depletion, forest increase as deforestation).',
  },
  EF4: {
    id: 'EF4',
    name: 'Unsupported confirmation',
    penalty: -0.1,
    description: 'Pathway is confirmed but reasoning cites no available variables.',
  },
  EF5: {
    id: 'EF5',
    name: 'Redundant follow-up',
    penalty: -0.05,
    description: 'Follow-up asks for information already present in available MWS data.',
  },
}

export const DIMENSION_IDS = ['D1', 'D2', 'D3', 'D4', 'D5', 'D6'] as const

export const ERROR_FLAG_IDS = ['EF1', 'EF2', 'EF3', 'EF4', 'EF5'] as const

/** Rubric dimensions are scored 0–3; weighted_total is 0–1. */
export const RUBRIC_DIMENSION_MAX = 3

export function dimensionScorePct(score: number): number {
  return Math.round((score / RUBRIC_DIMENSION_MAX) * 100)
}

export function formatDimensionScore(score: number): string {
  return `${dimensionScorePct(score)}%`
}

export function dimensionScoreTooltip(score: number, justification?: string): string {
  const parts = [`${score}/${RUBRIC_DIMENSION_MAX} (${formatDimensionScore(score)} of max)`]
  if (justification) parts.push(justification)
  return parts.join(' — ')
}

export function rubricTooltip(entry: RubricHintEntry): string {
  const parts = [entry.name, entry.description]
  if (entry.weight != null) parts.push(`Weight: ${Math.round(entry.weight * 100)}% of total.`)
  if (entry.penalty != null) parts.push(`Penalty when triggered: ${entry.penalty}.`)
  return parts.join(' ')
}
