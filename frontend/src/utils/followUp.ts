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

  if (followUpQuestion && askedQuestions.has(followUpQuestion)) {
    // Backend should prevent this; fall through to next structured question.
  } else if (followUpQuestion) {
    for (const item of diagnosis.uncertain_pathways) {
      for (const q of item.missing_variable_questions ?? []) {
        if (q.question === followUpQuestion && q.variable && !askedVariables.has(q.variable)) {
          return { variable: q.variable, question: followUpQuestion, structured: true }
        }
      }
    }
  }

  const uncertainWithRank: Array<{ item: DiagnosisResponse['uncertain_pathways'][number]; rank: number }> = []
  for (const item of diagnosis.uncertain_pathways) {
    const rank = diagnosis.pathway_retrieval_ranks?.[item.pathway_id] ?? Number.MAX_SAFE_INTEGER
    uncertainWithRank.push({ item, rank })
  }
  uncertainWithRank.sort((a, b) => a.rank - b.rank)

  for (const { item } of uncertainWithRank) {
    for (const q of item.missing_variable_questions ?? []) {
      if (q.variable && q.question && !askedVariables.has(q.variable) && !askedQuestions.has(q.question)) {
        return { variable: q.variable, question: q.question, structured: true }
      }
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
