import { useMemo, useState } from 'react'
import type { FollowUpQuestionDraft, SignalEditDraft, UserCardEditDraft } from './types'
import { indexSignals } from './signalUtils'

function buildSignalDrafts(rawCard: Record<string, unknown> | null | undefined): Record<string, SignalEditDraft> {
  const drafts: Record<string, SignalEditDraft> = {}
  for (const signal of indexSignals(rawCard)) {
    drafts[signal.signal_id] = {
      signal_id: signal.signal_id,
      active: signal.active !== false,
      variables: (signal.variables ?? []).join(', '),
      expression: signal.expression ?? '',
      qualitative_description: signal.qualitative_description ?? '',
      explanation: signal.explanation ?? '',
      severity: signal.severity ?? '',
      direction: signal.direction ?? '',
    }
  }
  return drafts
}

function buildFollowUpDrafts(rawCard: Record<string, unknown> | null | undefined): FollowUpQuestionDraft[] {
  const questions = rawCard?.missing_variable_questions
  if (!Array.isArray(questions)) return []
  return questions
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'))
    .map((question) => ({
      missing_variable: String(question.missing_variable ?? ''),
      question_to_user: String(question.question_to_user ?? ''),
      how_answer_updates_diagnosis: String(question.how_answer_updates_diagnosis ?? ''),
      question_mode: String(question.question_mode ?? ''),
      choices_json: JSON.stringify(question.choices ?? [], null, 2),
    }))
}

export function buildUserCardEditDraft(
  rawCard: Record<string, unknown> | null | undefined,
  saved?: UserCardEditDraft | null,
  savedPatch?: Record<string, unknown> | null,
): UserCardEditDraft {
  if (saved) return saved
  const mergedCard = savedPatch ? applyUserPatchPreview(rawCard, savedPatch) : rawCard
  const policy = mergedCard?.confirmation_policy
  return {
    overall_reasoning_note: String(mergedCard?.overall_reasoning_note ?? ''),
    confirmation_policy_json:
      policy && typeof policy === 'object' ? JSON.stringify(policy, null, 2) : '{\n  "version": 1\n}',
    signals: buildSignalDrafts(mergedCard),
    follow_up_questions: buildFollowUpDrafts(mergedCard),
    dirty: Boolean(savedPatch && Object.keys(savedPatch).length),
  }
}

function mergeFollowUpQuestions(
  current: unknown,
  partialQuestions: unknown,
): unknown {
  if (!Array.isArray(partialQuestions)) return current
  if (!Array.isArray(current)) return partialQuestions
  const merged = [...current] as Array<Record<string, unknown>>
  for (const partial of partialQuestions) {
    if (!partial || typeof partial !== 'object') continue
    const key = String((partial as { missing_variable?: string }).missing_variable || '')
    const index = merged.findIndex((item) => String(item.missing_variable || '') === key)
    if (index < 0) {
      merged.push(partial as Record<string, unknown>)
      continue
    }
    merged[index] = { ...merged[index], ...(partial as Record<string, unknown>) }
  }
  return merged
}

function applyUserPatchPreview(
  rawCard: Record<string, unknown> | null | undefined,
  patch: Record<string, unknown>,
): Record<string, unknown> | null | undefined {
  if (!rawCard) return rawCard
  const next = JSON.parse(JSON.stringify(rawCard)) as Record<string, unknown>
  if (typeof patch.overall_reasoning_note === 'string') {
    next.overall_reasoning_note = patch.overall_reasoning_note
  }
  if (patch.confirmation_policy && typeof patch.confirmation_policy === 'object') {
    next.confirmation_policy = patch.confirmation_policy
  }
  if (Array.isArray(patch.diagnostic_signals) && Array.isArray(next.diagnostic_signals)) {
    const signals = [...(next.diagnostic_signals as Array<Record<string, unknown>>)]
    for (const partial of patch.diagnostic_signals) {
      if (!partial || typeof partial !== 'object') continue
      const signalId = String((partial as { signal_id?: string }).signal_id || '')
      const index = signals.findIndex((item) => item.signal_id === signalId)
      if (index < 0) continue
      const current = signals[index]
      const merged = { ...current, ...partial }
      if (partial.condition && typeof partial.condition === 'object') {
        merged.condition = {
          ...((current.condition as Record<string, unknown>) || {}),
          ...(partial.condition as Record<string, unknown>),
        }
      }
      signals[index] = merged
    }
    next.diagnostic_signals = signals
  }
  if (patch.missing_variable_questions) {
    next.missing_variable_questions = mergeFollowUpQuestions(
      next.missing_variable_questions,
      patch.missing_variable_questions,
    )
  }
  return next
}

function parseFollowUpDraft(draft: FollowUpQuestionDraft): Record<string, unknown> | null {
  try {
    const choices = JSON.parse(draft.choices_json)
    if (!Array.isArray(choices)) return null
    return {
      missing_variable: draft.missing_variable,
      question_to_user: draft.question_to_user,
      how_answer_updates_diagnosis: draft.how_answer_updates_diagnosis,
      question_mode: draft.question_mode,
      response_type: 'mcq',
      choices,
    }
  } catch {
    return null
  }
}

export function userCardEditToPatch(
  draft: UserCardEditDraft,
  rawCard: Record<string, unknown> | null | undefined,
): Record<string, unknown> {
  const patch: Record<string, unknown> = {}
  const originalNote = String(rawCard?.overall_reasoning_note ?? '')
  if (draft.overall_reasoning_note !== originalNote) {
    patch.overall_reasoning_note = draft.overall_reasoning_note
  }

  try {
    const parsedPolicy = JSON.parse(draft.confirmation_policy_json) as unknown
    const originalPolicy = rawCard?.confirmation_policy
    if (JSON.stringify(parsedPolicy) !== JSON.stringify(originalPolicy ?? null)) {
      patch.confirmation_policy = parsedPolicy
    }
  } catch {
    /* invalid JSON — caller should block finalize */
  }

  const signalPatches: Array<Record<string, unknown>> = []
  const originalSignals = indexSignals(rawCard)
  for (const original of originalSignals) {
    const edited = draft.signals[original.signal_id]
    if (!edited) continue
    const nextVariables = edited.variables
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
    const originalActive = original.active !== false
    const activeChanged = edited.active !== originalActive
    const fieldsChanged =
      edited.expression !== (original.expression ?? '')
      || edited.qualitative_description !== (original.qualitative_description ?? '')
      || edited.explanation !== (original.explanation ?? '')
      || edited.severity !== (original.severity ?? '')
      || edited.direction !== (original.direction ?? '')
      || JSON.stringify(nextVariables) !== JSON.stringify(original.variables ?? [])
    if (!activeChanged && !fieldsChanged) continue
    const signalPatch: Record<string, unknown> = {
      signal_id: original.signal_id,
    }
    if (activeChanged) {
      signalPatch.active = edited.active
    }
    if (fieldsChanged) {
      signalPatch.variables = nextVariables
      signalPatch.severity = edited.severity
      signalPatch.direction = edited.direction
      signalPatch.condition = {
        expression: edited.expression,
        qualitative_description: edited.qualitative_description,
      }
      if (edited.explanation !== (original.explanation ?? '')) {
        signalPatch.explanation = edited.explanation
      }
    }
    signalPatches.push(signalPatch)
  }
  if (signalPatches.length) {
    patch.diagnostic_signals = signalPatches
  }

  const originalQuestions = buildFollowUpDrafts(rawCard)
  const questionPatches: Array<Record<string, unknown>> = []
  for (let index = 0; index < draft.follow_up_questions.length; index += 1) {
    const edited = draft.follow_up_questions[index]
    const original = originalQuestions[index]
    const parsed = parseFollowUpDraft(edited)
    if (!parsed) continue
    const unchanged =
      original
      && edited.missing_variable === original.missing_variable
      && edited.question_to_user === original.question_to_user
      && edited.how_answer_updates_diagnosis === original.how_answer_updates_diagnosis
      && edited.question_mode === original.question_mode
      && edited.choices_json === original.choices_json
    if (unchanged) continue
    questionPatches.push(parsed)
  }
  if (questionPatches.length) {
    patch.missing_variable_questions = questionPatches
  }

  return patch
}

type CardContentEditorProps = {
  draft: UserCardEditDraft
  disabled?: boolean
  onChange: (draft: UserCardEditDraft) => void
}

export function CardContentEditor({ draft, disabled, onChange }: CardContentEditorProps) {
  const [openSignals, setOpenSignals] = useState<Record<string, boolean>>({})
  const [openFollowUps, setOpenFollowUps] = useState<Record<string, boolean>>({})
  const signalIds = useMemo(() => Object.keys(draft.signals).sort(), [draft.signals])
  const inputClass =
    'w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm text-stone-900 shadow-sm disabled:bg-stone-100'
  const labelClass = 'mb-1 block text-xs font-semibold uppercase tracking-wide text-stone-600'

  let policyError: string | null = null
  try {
    JSON.parse(draft.confirmation_policy_json)
  } catch {
    policyError = 'Confirmation policy must be valid JSON before finalize.'
  }

  const followUpErrors = draft.follow_up_questions
    .map((question, index) => {
      try {
        const parsed = JSON.parse(question.choices_json)
        if (!Array.isArray(parsed)) return `Question ${index + 1}: choices must be a JSON array.`
        return null
      } catch {
        return `Question ${index + 1}: choices JSON is invalid.`
      }
    })
    .filter(Boolean)

  return (
    <div className="space-y-4 rounded-lg border border-sky-200 bg-sky-50/40 p-4">
      <div>
        <h3 className="text-sm font-semibold text-stone-900">Your direct card edits</h3>
        <p className="mt-1 text-xs text-stone-600">
          Edit note, signals, confirmation policy, and follow-up MCQs here. Saved separately on finalize; apply with{' '}
          <code className="rounded bg-white px-1">apply_user_card_edits.py</code> after Claude patch processing.
        </p>
      </div>

      <div>
        <label className={labelClass}>Overall reasoning note</label>
        <textarea
          className={`${inputClass} min-h-32 font-serif leading-relaxed`}
          disabled={disabled}
          value={draft.overall_reasoning_note}
          onChange={(event) =>
            onChange({ ...draft, overall_reasoning_note: event.target.value, dirty: true })
          }
        />
      </div>

      <div>
        <label className={labelClass}>Confirmation policy (JSON)</label>
        <textarea
          className={`${inputClass} min-h-48 font-mono text-xs`}
          disabled={disabled}
          value={draft.confirmation_policy_json}
          onChange={(event) =>
            onChange({ ...draft, confirmation_policy_json: event.target.value, dirty: true })
          }
        />
        {policyError && <p className="mt-1 text-xs text-red-700">{policyError}</p>}
      </div>

      <div>
        <div className={labelClass}>Diagnostic signals</div>
        <div className="space-y-2">
          {signalIds.map((signalId) => {
            const signal = draft.signals[signalId]
            const expanded = openSignals[signalId]
            return (
              <div key={signalId} className="rounded-md border border-stone-200 bg-white">
                <button
                  type="button"
                  disabled={disabled}
                  className="flex w-full items-center justify-between px-3 py-2 text-left text-sm font-mono font-semibold text-stone-800"
                  onClick={() => setOpenSignals((prev) => ({ ...prev, [signalId]: !expanded }))}
                >
                  <span className="flex items-center gap-2">
                    <span>{signalId}</span>
                    <select
                      className={`rounded border px-1.5 py-0.5 text-[10px] font-normal uppercase ${
                        signal.active
                          ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                          : 'border-stone-200 bg-stone-100 text-stone-500'
                      }`}
                      disabled={disabled}
                      value={signal.active ? 'active' : 'inactive'}
                      onClick={(event) => event.stopPropagation()}
                      onChange={(event) =>
                        onChange({
                          ...draft,
                          dirty: true,
                          signals: {
                            ...draft.signals,
                            [signalId]: { ...signal, active: event.target.value === 'active' },
                          },
                        })
                      }
                    >
                      <option value="active">active</option>
                      <option value="inactive">inactive</option>
                    </select>
                  </span>
                  <span className="text-xs font-normal text-stone-500">{expanded ? 'Hide' : 'Edit'}</span>
                </button>
                {expanded && (
                  <div className="space-y-3 border-t border-stone-100 p-3">
                    <div>
                      <label className={labelClass}>Status</label>
                      <select
                        className={inputClass}
                        disabled={disabled}
                        value={signal.active ? 'active' : 'inactive'}
                        onChange={(event) =>
                          onChange({
                            ...draft,
                            dirty: true,
                            signals: {
                              ...draft.signals,
                              [signalId]: { ...signal, active: event.target.value === 'active' },
                            },
                          })
                        }
                      >
                        <option value="active">Active — evaluated at diagnosis time</option>
                        <option value="inactive">Inactive — skipped during evaluation</option>
                      </select>
                    </div>
                    <div className="grid gap-3 md:grid-cols-2">
                      <div>
                        <label className={labelClass}>Severity</label>
                        <input
                          className={inputClass}
                          disabled={disabled}
                          value={signal.severity}
                          onChange={(event) =>
                            onChange({
                              ...draft,
                              dirty: true,
                              signals: {
                                ...draft.signals,
                                [signalId]: { ...signal, severity: event.target.value },
                              },
                            })
                          }
                        />
                      </div>
                      <div>
                        <label className={labelClass}>Direction</label>
                        <input
                          className={inputClass}
                          disabled={disabled}
                          value={signal.direction}
                          onChange={(event) =>
                            onChange({
                              ...draft,
                              dirty: true,
                              signals: {
                                ...draft.signals,
                                [signalId]: { ...signal, direction: event.target.value },
                              },
                            })
                          }
                        />
                      </div>
                    </div>
                    <div>
                      <label className={labelClass}>Variables (comma-separated)</label>
                      <input
                        className={inputClass}
                        disabled={disabled}
                        value={signal.variables}
                        onChange={(event) =>
                          onChange({
                            ...draft,
                            dirty: true,
                            signals: {
                              ...draft.signals,
                              [signalId]: { ...signal, variables: event.target.value },
                            },
                          })
                        }
                      />
                    </div>
                    <div>
                      <label className={labelClass}>Expression</label>
                      <textarea
                        className={`${inputClass} min-h-20 font-mono text-xs`}
                        disabled={disabled}
                        value={signal.expression}
                        onChange={(event) =>
                          onChange({
                            ...draft,
                            dirty: true,
                            signals: {
                              ...draft.signals,
                              [signalId]: { ...signal, expression: event.target.value },
                            },
                          })
                        }
                      />
                    </div>
                    <div>
                      <label className={labelClass}>Qualitative description</label>
                      <textarea
                        className={`${inputClass} min-h-24`}
                        disabled={disabled}
                        value={signal.qualitative_description}
                        onChange={(event) =>
                          onChange({
                            ...draft,
                            dirty: true,
                            signals: {
                              ...draft.signals,
                              [signalId]: { ...signal, qualitative_description: event.target.value },
                            },
                          })
                        }
                      />
                    </div>
                    <div>
                      <label className={labelClass}>Explanation</label>
                      <textarea
                        className={`${inputClass} min-h-32 font-serif leading-relaxed`}
                        disabled={disabled}
                        value={signal.explanation}
                        onChange={(event) =>
                          onChange({
                            ...draft,
                            dirty: true,
                            signals: {
                              ...draft.signals,
                              [signalId]: { ...signal, explanation: event.target.value },
                            },
                          })
                        }
                      />
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {draft.follow_up_questions.length > 0 && (
        <div>
          <div className={labelClass}>Missing variable follow-up questions</div>
          <div className="space-y-2">
            {draft.follow_up_questions.map((question, index) => {
              const key = question.missing_variable || `question_${index}`
              const expanded = openFollowUps[key]
              return (
                <div key={key} className="rounded-md border border-stone-200 bg-white">
                  <button
                    type="button"
                    disabled={disabled}
                    className="flex w-full items-center justify-between px-3 py-2 text-left text-sm font-semibold text-stone-800"
                    onClick={() => setOpenFollowUps((prev) => ({ ...prev, [key]: !expanded }))}
                  >
                    <span className="font-mono">{question.missing_variable || `question_${index + 1}`}</span>
                    <span className="text-xs font-normal text-stone-500">{expanded ? 'Hide' : 'Edit'}</span>
                  </button>
                  {expanded && (
                    <div className="space-y-3 border-t border-stone-100 p-3">
                      <div>
                        <label className={labelClass}>Question to user</label>
                        <textarea
                          className={`${inputClass} min-h-20`}
                          disabled={disabled}
                          value={question.question_to_user}
                          onChange={(event) => {
                            const next = [...draft.follow_up_questions]
                            next[index] = { ...question, question_to_user: event.target.value }
                            onChange({ ...draft, follow_up_questions: next, dirty: true })
                          }}
                        />
                      </div>
                      <div>
                        <label className={labelClass}>How answer updates diagnosis</label>
                        <textarea
                          className={`${inputClass} min-h-20`}
                          disabled={disabled}
                          value={question.how_answer_updates_diagnosis}
                          onChange={(event) => {
                            const next = [...draft.follow_up_questions]
                            next[index] = { ...question, how_answer_updates_diagnosis: event.target.value }
                            onChange({ ...draft, follow_up_questions: next, dirty: true })
                          }}
                        />
                      </div>
                      <div>
                        <label className={labelClass}>Question mode</label>
                        <input
                          className={inputClass}
                          disabled={disabled}
                          value={question.question_mode}
                          onChange={(event) => {
                            const next = [...draft.follow_up_questions]
                            next[index] = { ...question, question_mode: event.target.value }
                            onChange({ ...draft, follow_up_questions: next, dirty: true })
                          }}
                        />
                      </div>
                      <div>
                        <label className={labelClass}>Choices (JSON array)</label>
                        <textarea
                          className={`${inputClass} min-h-40 font-mono text-xs`}
                          disabled={disabled}
                          value={question.choices_json}
                          onChange={(event) => {
                            const next = [...draft.follow_up_questions]
                            next[index] = { ...question, choices_json: event.target.value }
                            onChange({ ...draft, follow_up_questions: next, dirty: true })
                          }}
                        />
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          {followUpErrors.map((message) => (
            <p key={message} className="mt-1 text-xs text-red-700">
              {message}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}
