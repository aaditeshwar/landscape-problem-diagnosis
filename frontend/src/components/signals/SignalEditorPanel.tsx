import type { EvidenceCardDocument, EvidenceCardSummary, SignalEditorDraft } from '../../api/signals'
import { formatPathwayHierarchy } from '../../utils/pathwayLabels'
import { ConfirmationPolicySummary } from './ConfirmationPolicySummary'

interface Props {
  cards: EvidenceCardSummary[]
  selectedCardId: string | null
  card: EvidenceCardDocument | null
  draft: SignalEditorDraft | null
  loading: boolean
  error: string | null
  onSelectCardId: (cardId: string) => void
}

function ReadOnlyBlock({
  label,
  value,
  mono = false,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  const text = value.trim()
  if (!text) {
    return (
      <div className="mt-2">
        <div className="text-sm text-stone-600">{label}</div>
        <p className="mt-1 text-sm text-stone-400">—</p>
      </div>
    )
  }
  return (
    <div className="mt-2">
      <div className="text-sm text-stone-600">{label}</div>
      <div
        className={`mt-1 whitespace-pre-wrap break-words text-sm text-stone-800 ${
          mono ? 'font-mono text-xs leading-relaxed' : 'leading-relaxed'
        }`}
      >
        {text}
      </div>
    </div>
  )
}

function choiceEffectSummary(effectsJson: string): string | null {
  const trimmed = effectsJson.trim()
  if (!trimmed || trimmed === '{"signals":[]}' || trimmed === '{}') return null
  try {
    const parsed = JSON.parse(trimmed) as { signals?: Array<{ signal_id?: string; result?: boolean }> }
    const rows = parsed.signals ?? []
    if (!rows.length) return null
    return rows
      .map((row) => {
        const id = row.signal_id ?? '?'
        if (row.result === true) return `${id}→confirm`
        if (row.result === false) return `${id}→reject`
        return id
      })
      .join(', ')
  } catch {
    return null
  }
}

function FollowUpQuestionReadOnly({
  question,
}: {
  question: SignalEditorDraft['followUpQuestions'][number]
}) {
  return (
    <>
      <div className="mt-2">
        <div className="text-sm text-stone-600">Question to user</div>
        {question.question_to_user.trim() ? (
          <div className="mt-1 space-y-2">
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-stone-800">
              {question.question_to_user}
            </p>
            {question.choices.length > 0 ? (
              <ul className="space-y-1 border-l-2 border-amber-200 pl-3">
                {question.choices.map((choice) => {
                  const effect = choiceEffectSummary(choice.effectsJson)
                  return (
                    <li key={choice.id} className="text-sm text-stone-700">
                      <span className="font-medium text-stone-800">{choice.id}</span>
                      {choice.label ? `: ${choice.label}` : null}
                      {effect ? (
                        <span className="ml-1 text-xs text-stone-500">({effect})</span>
                      ) : null}
                    </li>
                  )
                })}
              </ul>
            ) : null}
          </div>
        ) : (
          <p className="mt-1 text-sm text-stone-400">—</p>
        )}
      </div>
      {question.how_answer_updates_diagnosis ? (
        <ReadOnlyBlock
          label="How answer updates diagnosis"
          value={question.how_answer_updates_diagnosis}
        />
      ) : null}
    </>
  )
}

export function SignalEditorPanel({
  cards,
  selectedCardId,
  card,
  draft,
  loading,
  error,
  onSelectCardId,
}: Props) {
  if (!draft) {
    return (
      <div className="space-y-4">
        <CardSelector cards={cards} selectedCardId={selectedCardId} onSelectCardId={onSelectCardId} />
        {loading ? <p className="text-sm text-stone-500">Loading card…</p> : null}
        {error ? <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <CardSelector cards={cards} selectedCardId={selectedCardId} onSelectCardId={onSelectCardId} />

      {loading ? <p className="text-sm text-stone-500">Loading card…</p> : null}
      {error ? <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null}

      {card ? (
        <>
          <section className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-stone-800">Card overview</h3>
            <dl className="mt-2 grid gap-2 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-stone-500">Production system</dt>
                <dd className="font-medium">{card.production_system ?? '—'}</dd>
              </div>
              <div>
                <dt className="text-stone-500">Observed stress</dt>
                <dd className="font-medium">{card.observed_stress ?? '—'}</dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-stone-500">Causal pathway</dt>
                <dd className="font-medium">{card.causal_pathway ?? '—'}</dd>
              </div>
            </dl>
          </section>

          <section className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-stone-800">Diagnostic signals</h3>
            <p className="mt-1 text-xs text-stone-500">Read-only view of card signal definitions.</p>
            <ul className="mt-3 space-y-4">
              {draft.signals.map((signal) => (
                <li key={signal.signal_id} className="rounded-lg border border-stone-100 bg-stone-50/70 p-3">
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                    <span className="font-medium text-stone-800">{signal.signal_id}</span>
                    <span className="text-stone-600">
                      Active: <span className="font-medium">{signal.active ? 'yes' : 'no'}</span>
                    </span>
                    <span className="text-stone-600">
                      Severity: <span className="font-medium">{signal.severity || '—'}</span>
                    </span>
                    <span className="text-stone-600">
                      Direction: <span className="font-medium">{signal.direction || '—'}</span>
                    </span>
                  </div>
                  {signal.variables.length ? (
                    <p className="mt-2 text-xs text-stone-500">Variables: {signal.variables.join(', ')}</p>
                  ) : null}
                  {signal.expression ? (
                    <ReadOnlyBlock label="Expression" value={signal.expression} mono />
                  ) : null}
                  <ReadOnlyBlock label="Qualitative description" value={signal.qualitative_description} />
                  <ReadOnlyBlock label="Explanation" value={signal.explanation} />
                </li>
              ))}
            </ul>
          </section>

          <section className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-stone-800">Confirmation policy</h3>
            <p className="mt-1 text-xs text-stone-500">Structured rules enforced by the server (v1 schema).</p>
            <ConfirmationPolicySummary policyJson={draft.confirmationPolicyJson} />
          </section>

          <section className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-stone-800">Overall reasoning note</h3>
            <p className="mt-1 text-xs text-stone-500">Human-readable prose for reviewers and LLM prompts.</p>
            <ReadOnlyBlock label="Note" value={draft.overallReasoningNote} />
          </section>

          <section className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-stone-800">Follow-up questions</h3>
            <p className="mt-1 text-xs text-stone-500">MCQ follow-up templates as stored on the card.</p>
            <ul className="mt-3 space-y-4">
              {draft.followUpQuestions.map((question, qIndex) => (
                <li key={question.missing_variable || qIndex} className="rounded-lg border border-stone-100 p-3">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="font-medium text-stone-800">{question.missing_variable}</span>
                    {question.question_mode ? (
                      <span className="text-stone-600">
                        Mode: <span className="font-medium">{question.question_mode}</span>
                      </span>
                    ) : null}
                  </div>
                  <FollowUpQuestionReadOnly question={question} />
                </li>
              ))}
            </ul>
          </section>

          <section className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-stone-800">Confounders</h3>
            {draft.confounders.length === 0 ? (
              <p className="mt-2 text-sm text-stone-400">None listed.</p>
            ) : (
              <ul className="mt-3 space-y-3">
                {draft.confounders.map((item, index) => (
                  <li key={index} className="rounded-lg border border-stone-100 p-3">
                    <ReadOnlyBlock label="Confounder" value={item.confounder} />
                    <ReadOnlyBlock label="How to distinguish" value={item.how_to_distinguish ?? ''} />
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      ) : null}
    </div>
  )
}

function CardSelector({
  cards,
  selectedCardId,
  onSelectCardId,
}: {
  cards: EvidenceCardSummary[]
  selectedCardId: string | null
  onSelectCardId: (cardId: string) => void
}) {
  return (
    <section className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-stone-800">Evidence card</h2>
      <label className="mt-3 flex flex-col gap-1 text-sm">
        <span className="font-medium text-stone-700">Pathway card</span>
        <select
          value={selectedCardId ?? ''}
          onChange={(e) => onSelectCardId(e.target.value)}
          className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-200"
        >
          <option value="">Select a card…</option>
          {cards.map((item) => (
            <option key={item.card_id} value={item.card_id}>
              {formatPathwayHierarchy({
                pathway_id: item.causal_pathway ?? item.pathway_id ?? item.card_id,
                production_system: item.production_system,
                observed_stress: item.observed_stress,
              })}
            </option>
          ))}
        </select>
      </label>
      {selectedCardId ? (
        <p className="mt-2 text-xs text-stone-500">
          Card ID: <code className="rounded bg-stone-100 px-1">{selectedCardId}</code>
        </p>
      ) : null}
    </section>
  )
}
