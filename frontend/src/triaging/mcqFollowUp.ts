export type McqChoiceEffect = {
  signal_id: string
  result: boolean
}

export type McqChoice = {
  id: string
  label: string
  normalized?: Record<string, unknown>
  effects?: { signals?: McqChoiceEffect[] }
}

export type MissingVariableQuestion = {
  missing_variable: string
  question_to_user?: string
  how_answer_updates_diagnosis?: string
  response_type?: string
  choices?: McqChoice[]
}

export function signalResultFromChoice(
  question: MissingVariableQuestion | null | undefined,
  signalId: string,
  choiceId: string | undefined,
): boolean | null {
  if (!question || !choiceId) return null
  const choice = (question.choices || []).find((item) => item.id === choiceId)
  if (!choice) return null
  for (const row of choice.effects?.signals || []) {
    if (row.signal_id === signalId) {
      return row.result
    }
  }
  return null
}

export function mcqQuestionForSignal(
  questions: MissingVariableQuestion[] | undefined,
  signalId: string,
  signalVariables: string[] = [],
  hasExpression: boolean,
): MissingVariableQuestion | null {
  for (const question of questions || []) {
    for (const choice of question.choices || []) {
      for (const row of choice.effects?.signals || []) {
        if (row.signal_id === signalId) return question
      }
    }
    if (!hasExpression && signalVariables.includes(question.missing_variable)) {
      return question
    }
  }
  return null
}

export function isMcqFollowUpSignal(
  questions: MissingVariableQuestion[] | undefined,
  signalId: string,
  signalVariables: string[] = [],
  hasExpression: boolean,
): boolean {
  return mcqQuestionForSignal(questions, signalId, signalVariables, hasExpression) !== null
}
