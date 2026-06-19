import type {
  EvidenceCardDocument,
  SignalEditorDraft,
  ConfirmationPolicy,
} from '../api/signals'
import type { EvidenceSuggestionsDocument, SignalSuggestion } from '../api/evidenceSuggestions'

export function draftFromCard(card: EvidenceCardDocument): SignalEditorDraft {
  const policy = card.confirmation_policy
  return {
    signals: (card.diagnostic_signals ?? []).map((signal) => ({
      signal_id: signal.signal_id,
      active: signal.active !== false,
      severity: signal.severity ?? 'moderate',
      direction: signal.direction ?? 'confirms',
      explanation: signal.explanation ?? '',
      qualitative_description:
        typeof signal.condition?.qualitative_description === 'string'
          ? signal.condition.qualitative_description
          : '',
      expression: typeof signal.condition?.expression === 'string' ? signal.condition.expression : '',
      condition_type: typeof signal.condition?.type === 'string' ? signal.condition.type : '',
      variables: signal.variables ?? [],
    })),
    confirmationPolicyJson: policy ? JSON.stringify(policy, null, 2) : '',
    overallReasoningNote: card.overall_reasoning_note ?? '',
    confounders: (card.confounders ?? []).map((item) =>
      typeof item === 'string'
        ? { confounder: item, how_to_distinguish: '' }
        : {
            confounder: String((item as { confounder?: string }).confounder ?? ''),
            how_to_distinguish: String((item as { how_to_distinguish?: string }).how_to_distinguish ?? ''),
          },
    ),
    followUpQuestions: (card.missing_variable_questions ?? []).map((question) => ({
      missing_variable: question.missing_variable ?? '',
      question_mode: question.question_mode ?? '',
      question_to_user: question.question_to_user ?? '',
      how_answer_updates_diagnosis: question.how_answer_updates_diagnosis ?? '',
      response_type: question.response_type ?? 'mcq',
      choices: (question.choices ?? []).map((choice) => ({
        id: choice.id ?? '',
        label: choice.label ?? '',
        normalizedJson: JSON.stringify(choice.normalized ?? {}, null, 2),
        effectsJson: JSON.stringify(choice.effects ?? { signals: [] }, null, 2),
      })),
    })),
  }
}

export function applySuggestionsToDraft(
  draft: SignalEditorDraft,
  saved: EvidenceSuggestionsDocument,
): SignalEditorDraft {
  const next = structuredClone(draft)
  const suggestions = saved.suggestions
  if (!suggestions) return next

  if (suggestions.overall_reasoning_note != null) {
    next.overallReasoningNote = suggestions.overall_reasoning_note
  }
  if (suggestions.confirmation_policy) {
    next.confirmationPolicyJson = JSON.stringify(suggestions.confirmation_policy, null, 2)
  }
  if (suggestions.confounders) {
    next.confounders = suggestions.confounders
  }

  for (const patch of suggestions.signals ?? []) {
    const target = next.signals.find((row) => row.signal_id === patch.signal_id)
    if (!target) continue
    if (patch.active != null) target.active = patch.active
    if (patch.severity) target.severity = patch.severity
    if (patch.direction) target.direction = patch.direction
    if (patch.explanation != null) target.explanation = patch.explanation
    if (patch.qualitative_description != null) target.qualitative_description = patch.qualitative_description
  }

  if (suggestions.follow_up_questions?.length) {
    next.followUpQuestions = suggestions.follow_up_questions.map((question) => ({
      missing_variable: question.missing_variable ?? '',
      question_mode: question.question_mode ?? '',
      question_to_user: question.question_to_user ?? '',
      how_answer_updates_diagnosis: question.how_answer_updates_diagnosis ?? '',
      response_type: question.response_type ?? 'mcq',
      choices: (question.choices ?? []).map((choice) => ({
        id: choice.id ?? '',
        label: choice.label ?? '',
        normalizedJson: JSON.stringify(choice.normalized ?? {}, null, 2),
        effectsJson: JSON.stringify(choice.effects ?? { signals: [] }, null, 2),
      })),
    }))
  }

  return next
}

function parseJsonObject(text: string, label: string): Record<string, unknown> | null {
  const trimmed = text.trim()
  if (!trimmed) return null
  try {
    const parsed = JSON.parse(trimmed) as unknown
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
    throw new Error(`${label} must be a JSON object`)
  } catch (error) {
    throw new Error(`${label}: ${error instanceof Error ? error.message : 'invalid JSON'}`)
  }
}

export function buildSuggestionsPayload(draft: SignalEditorDraft): {
  payload: {
    signals: SignalSuggestion[]
    confirmation_policy: ConfirmationPolicy | null
    overall_reasoning_note: string
    confounders: Array<{ confounder: string; how_to_distinguish: string }>
    follow_up_questions: NonNullable<EvidenceSuggestionsDocument['suggestions']>['follow_up_questions']
  }
  policyError: string | null
} {
  let confirmation_policy: ConfirmationPolicy | null = null
  let policyError: string | null = null
  if (draft.confirmationPolicyJson.trim()) {
    try {
      confirmation_policy = parseJsonObject(draft.confirmationPolicyJson, 'Confirmation policy') as ConfirmationPolicy
    } catch (error) {
      policyError = error instanceof Error ? error.message : 'Invalid confirmation policy JSON'
    }
  }

  const follow_up_questions = draft.followUpQuestions.map((question) => ({
    missing_variable: question.missing_variable,
    question_mode: question.question_mode || undefined,
    question_to_user: question.question_to_user || undefined,
    how_answer_updates_diagnosis: question.how_answer_updates_diagnosis || undefined,
    response_type: question.response_type || undefined,
    choices: question.choices.map((choice) => ({
      id: choice.id,
      label: choice.label || undefined,
      normalized: parseJsonObject(choice.normalizedJson, `Choice ${choice.id} normalized`) ?? {},
      effects: parseJsonObject(choice.effectsJson, `Choice ${choice.id} effects`) ?? undefined,
    })),
  }))

  return {
    payload: {
      signals: draft.signals.map((signal) => ({
        signal_id: signal.signal_id,
        active: signal.active,
        severity: signal.severity,
        direction: signal.direction,
        explanation: signal.explanation,
        qualitative_description: signal.qualitative_description || undefined,
      })),
      confirmation_policy,
      overall_reasoning_note: draft.overallReasoningNote,
      confounders: draft.confounders
        .filter((item) => item.confounder.trim())
        .map((item) => ({
          confounder: item.confounder,
          how_to_distinguish: item.how_to_distinguish ?? '',
        })),
      follow_up_questions,
    },
    policyError,
  }
}
