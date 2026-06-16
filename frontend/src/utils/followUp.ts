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

export function normalizeFollowUpQuestion(value: DiagnosisResponse['follow_up_question']): string | null {
  if (value == null) return null
  if (typeof value === 'string') {
    const trimmed = value.trim()
    return trimmed || null
  }
  if (typeof value === 'object' && value !== null && 'question' in value) {
    const question = (value as { question?: unknown }).question
    if (typeof question === 'string') {
      const trimmed = question.trim()
      return trimmed || null
    }
  }
  return null
}

export function resolveFollowUpTarget(
  diagnosis: DiagnosisResponse | null,
  _askedVariables: Set<string>,
  askedQuestions: Set<string> = new Set(),
): FollowUpTarget | null {
  if (!diagnosis) return null

  const followUpQuestion = normalizeFollowUpQuestion(diagnosis.follow_up_question)
  const followUpVariable = diagnosis.follow_up_variable?.trim() || null

  if (followUpQuestion && followUpVariable && !askedQuestions.has(followUpQuestion)) {
    return { variable: followUpVariable, question: followUpQuestion, structured: true }
  }

  if (followUpQuestion && !askedQuestions.has(followUpQuestion)) {
    return {
      variable: followUpVariable || USER_OBSERVATION_VARIABLE,
      question: followUpQuestion,
      structured: Boolean(followUpVariable),
    }
  }

  return { variable: USER_OBSERVATION_VARIABLE, question: null, structured: false }
}

export function followUpPromptLabel(target: FollowUpTarget | null, hasHistory: boolean): string {
  if (!target) return 'Continue conversation'
  if (target.question && hasHistory) return 'Next follow-up question'
  if (target.question) return 'Follow-up question'
  return 'Continue conversation'
}
