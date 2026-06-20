function clonePatch(patch: Record<string, unknown>): Record<string, unknown> {
  return JSON.parse(JSON.stringify(patch)) as Record<string, unknown>
}

function updateDiagnosticSignal(
  patch: Record<string, unknown>,
  signalId: string,
  field: 'expression' | 'qualitative_description',
  value: string,
): Record<string, unknown> {
  const next = clonePatch(patch)
  const signals = Array.isArray(next.diagnostic_signals) ? [...next.diagnostic_signals] : []
  const index = signals.findIndex(
    (sig) => typeof sig === 'object' && sig && (sig as { signal_id?: string }).signal_id === signalId,
  )
  if (index < 0) return next
  const signal = { ...(signals[index] as Record<string, unknown>) }
  const condition = { ...((signal.condition as Record<string, unknown>) || {}) }
  condition[field] = value
  signal.condition = condition
  signals[index] = signal
  next.diagnostic_signals = signals
  return next
}

function updateOverallNote(patch: Record<string, unknown>, value: string): Record<string, unknown> {
  return { ...clonePatch(patch), overall_reasoning_note: value }
}


function updateMcqChoice(
  patch: Record<string, unknown>,
  questionIndex: number,
  choiceIndex: number,
  updates: { label?: string; band?: string; present?: boolean },
): Record<string, unknown> {
  const next = clonePatch(patch)
  const questions = Array.isArray(next.missing_variable_questions)
    ? [...next.missing_variable_questions]
    : []
  const question = { ...(questions[questionIndex] as Record<string, unknown>) }
  const choices = Array.isArray(question.choices) ? [...question.choices] : []
  const choice = { ...(choices[choiceIndex] as Record<string, unknown>) }
  if (updates.label !== undefined) choice.label = updates.label
  const normalized = { ...((choice.normalized as Record<string, unknown>) || {}) }
  if (updates.band !== undefined) normalized.band = updates.band
  if (updates.present !== undefined) normalized.present = updates.present
  choice.normalized = normalized
  choices[choiceIndex] = choice
  question.choices = choices
  questions[questionIndex] = question
  next.missing_variable_questions = questions
  return next
}

function updateQuestionText(patch: Record<string, unknown>, questionIndex: number, value: string): Record<string, unknown> {
  const next = clonePatch(patch)
  const questions = Array.isArray(next.missing_variable_questions)
    ? [...next.missing_variable_questions]
    : []
  const question = { ...(questions[questionIndex] as Record<string, unknown>) }
  question.question_to_user = value
  questions[questionIndex] = question
  next.missing_variable_questions = questions
  return next
}

export type PatchFieldEditorProps = {
  patch: Record<string, unknown>
  disabled?: boolean
  onChange: (patch: Record<string, unknown>) => void
}

export function PatchFieldEditor({ patch, disabled, onChange }: PatchFieldEditorProps) {
  const inputClass =
    'w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm text-stone-900 shadow-sm disabled:bg-stone-100'
  const labelClass = 'mb-1 block text-xs font-semibold uppercase tracking-wide text-stone-600'

  if (typeof patch.overall_reasoning_note === 'string') {
    return (
      <div>
        <label className={labelClass}>Overall reasoning note</label>
        <textarea
          className={`${inputClass} min-h-40 font-serif leading-relaxed`}
          disabled={disabled}
          value={patch.overall_reasoning_note}
          onChange={(event) => onChange(updateOverallNote(patch, event.target.value))}
        />
      </div>
    )
  }

  if (Array.isArray(patch.diagnostic_signals)) {
    return (
      <div className="space-y-4">
        {patch.diagnostic_signals.map((raw, index) => {
          const signal = raw as {
            signal_id?: string
            condition?: { expression?: string; qualitative_description?: string }
          }
          const signalId = signal.signal_id || `signal_${index + 1}`
          return (
            <div key={signalId} className="rounded-md border border-stone-200 bg-white p-3">
              <div className="mb-2 text-sm font-semibold text-stone-800">{signalId}</div>
              <label className={labelClass}>Expression</label>
              <textarea
                className={`${inputClass} min-h-20 font-mono text-xs`}
                disabled={disabled}
                value={signal.condition?.expression ?? ''}
                onChange={(event) =>
                  onChange(updateDiagnosticSignal(patch, signalId, 'expression', event.target.value))
                }
              />
              <label className={`${labelClass} mt-3`}>Qualitative description</label>
              <textarea
                className={`${inputClass} min-h-24`}
                disabled={disabled}
                value={signal.condition?.qualitative_description ?? ''}
                onChange={(event) =>
                  onChange(
                    updateDiagnosticSignal(patch, signalId, 'qualitative_description', event.target.value),
                  )
                }
              />
            </div>
          )
        })}
      </div>
    )
  }

  if (patch.metadata && typeof patch.metadata === 'object') {
    const metadata = patch.metadata as Record<string, unknown>
    if (typeof metadata.evaluator_extension_requested === 'string') {
      return (
        <div>
          <label className={labelClass}>Evaluator extension requested</label>
          <textarea
            className={`${inputClass} min-h-24 font-mono text-xs`}
            disabled={disabled}
            value={metadata.evaluator_extension_requested}
            onChange={(event) => {
            const next = clonePatch(patch)
            const meta = { ...((next.metadata as Record<string, unknown>) || {}) }
            meta.evaluator_extension_requested = event.target.value
            next.metadata = meta
            onChange(next)
          }}
          />
        </div>
      )
    }
  }

  if (Array.isArray(patch.missing_variable_questions)) {
    return (
      <div className="space-y-4">
        {patch.missing_variable_questions.map((raw, qIndex) => {
          const question = raw as {
            missing_variable?: string
            question_to_user?: string
            choices?: Array<{
              id?: string
              label?: string
              normalized?: { band?: string; present?: boolean }
            }>
          }
          return (
            <div key={qIndex} className="rounded-md border border-stone-200 bg-white p-3">
              <div className="mb-2 text-sm font-semibold text-stone-800">
                {question.missing_variable || `question_${qIndex}`}
              </div>
              {typeof question.question_to_user === 'string' && (
                <>
                  <label className={labelClass}>Question to user</label>
                  <textarea
                    className={`${inputClass} min-h-20`}
                    disabled={disabled}
                    value={question.question_to_user}
                    onChange={(event) => onChange(updateQuestionText(patch, qIndex, event.target.value))}
                  />
                </>
              )}
              {(question.choices ?? []).map((choice, cIndex) => (
                <div key={choice.id || cIndex} className="mt-3 rounded border border-stone-100 p-2">
                  <div className="mb-2 text-xs font-medium text-stone-700">Choice: {choice.id || cIndex}</div>
                  <label className={labelClass}>Label</label>
                  <input
                    className={inputClass}
                    disabled={disabled}
                    value={choice.label ?? ''}
                    onChange={(event) =>
                      onChange(updateMcqChoice(patch, qIndex, cIndex, { label: event.target.value }))
                    }
                  />
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    <div>
                      <label className={labelClass}>Band</label>
                      <input
                        className={inputClass}
                        disabled={disabled}
                        value={choice.normalized?.band ?? ''}
                        onChange={(event) =>
                          onChange(updateMcqChoice(patch, qIndex, cIndex, { band: event.target.value }))
                        }
                      />
                    </div>
                    <div>
                      <label className={labelClass}>Present</label>
                      <select
                        className={inputClass}
                        disabled={disabled}
                        value={String(choice.normalized?.present ?? '')}
                        onChange={(event) =>
                          onChange(
                            updateMcqChoice(patch, qIndex, cIndex, {
                              present: event.target.value === 'true',
                            }),
                          )
                        }
                      >
                        <option value="true">true</option>
                        <option value="false">false</option>
                      </select>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )
        })}
      </div>
    )
  }

  if (patch.confirmation_policy && typeof patch.confirmation_policy === 'object') {
    const policy = patch.confirmation_policy as Record<string, unknown>
    const primary = Array.isArray(policy.primary_confirm_signals)
      ? (policy.primary_confirm_signals as string[]).join(', ')
      : ''
    return (
      <div className="space-y-3">
        <p className="text-sm text-stone-600">
          Confirmation policy patch — edit primary signal list below; nested rules remain in the saved patch.
        </p>
        <label className={labelClass}>Primary confirm signals (comma-separated)</label>
        <input
          className={inputClass}
          disabled={disabled}
          value={primary}
          onChange={(event) => {
            const next = clonePatch(patch)
            const nextPolicy = { ...(next.confirmation_policy as Record<string, unknown>) }
            nextPolicy.primary_confirm_signals = event.target.value
              .split(',')
              .map((item) => item.trim())
              .filter(Boolean)
            next.confirmation_policy = nextPolicy
            onChange(next)
          }}
        />
        <label className={labelClass}>Full policy JSON (read-only reference)</label>
        <pre className="max-h-48 overflow-auto rounded-md border border-stone-200 bg-stone-50 p-2 text-xs">
          {JSON.stringify(policy, null, 2)}
        </pre>
      </div>
    )
  }

  const flatKey = Object.keys(patch).find((key) => key.includes('['))
  if (flatKey) {
    return (
      <div>
        <p className="mb-2 text-sm text-amber-800">
          This patch uses a nested path key. Showing JSON for manual review.
        </p>
        <pre className="rounded-md border border-stone-200 bg-stone-50 p-2 text-xs">
          {JSON.stringify(patch, null, 2)}
        </pre>
      </div>
    )
  }

  return (
    <pre className="rounded-md border border-stone-200 bg-stone-50 p-2 text-xs">
      {JSON.stringify(patch, null, 2)}
    </pre>
  )
}

export function initialPatchDraft(
  suggested: Record<string, unknown> | null | undefined,
  edited: Record<string, unknown> | null | undefined,
): Record<string, unknown> | null {
  const base = edited ?? suggested
  if (!base || Object.keys(base).length === 0) return null
  return JSON.parse(JSON.stringify(base)) as Record<string, unknown>
}
