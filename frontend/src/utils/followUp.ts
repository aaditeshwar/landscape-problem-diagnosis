import type { DiagnosisResponse } from '../types'

export const USER_OBSERVATION_VARIABLE = 'user_observation'

export interface FollowUpTarget {
  variable: string
  question: string | null
  structured: boolean
}

export function askedVariablesFromHistory(history: Array<{ variable?: string }>): Set<string> {
  const asked = new Set<string>()
  for (const entry of history) {
    if (entry.variable) asked.add(entry.variable)
  }
  return asked
}

export function askedQuestionsFromHistory(history: Array<{ question?: string }>): Set<string> {
  const asked = new Set<string>()
  for (const entry of history) {
    const q = entry.question?.trim()
    if (q) asked.add(q)
  }
  return asked
}

export function resolveFollowUpTarget(
  diagnosis: DiagnosisResponse | null,
  askedVariables: Set<string>,
  askedQuestions: Set<string> = new Set(),
): FollowUpTarget | null {
  if (!diagnosis) return null

  const followUpQuestion = diagnosis.follow_up_question?.trim() || null
  const followUpVariable = diagnosis.follow_up_variable?.trim() || null

  if (
    followUpQuestion &&
    !askedQuestions.has(followUpQuestion) &&
    followUpVariable &&
    !askedVariables.has(followUpVariable)
  ) {
    return { variable: followUpVariable, question: followUpQuestion, structured: true }
  }

  return { variable: USER_OBSERVATION_VARIABLE, question: null, structured: false }
}

export function followUpPromptLabel(target: FollowUpTarget | null, hasHistory: boolean): string {
  if (!target) return 'Continue conversation'
  if (target.question && hasHistory) return 'Next follow-up question'
  if (target.question) return 'Follow-up question'
  return 'Continue conversation'
}
