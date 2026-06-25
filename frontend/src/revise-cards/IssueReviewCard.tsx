import { JsonDiffView } from './JsonDiffView'
import { SignalText } from './SignalText'
import type { IssueDraft, ReviewFinding } from './types'
import { formatJson, hasActionablePolicyPatch, isPolicyFinding, resolvePolicyObject } from './jsonDiff'
import { indexSignals } from './signalUtils'
import { dimensionLabel, formatValue, severityClasses } from './utils'

type IssueReviewCardProps = {
  finding: ReviewFinding
  index: number
  total: number
  draft: IssueDraft
  disabled: boolean
  rawCard?: Record<string, unknown> | null
  patchSource?: 'claude' | 'triaging'
  onDraftChange: (draft: IssueDraft) => void
}

function normalizeSavedDecision(raw: string | undefined): IssueDraft['decision'] {
  if (raw === 'handled' || raw === 'accept') return 'handled'
  if (raw === 'not_handled' || raw === 'reject') return 'not_handled'
  return 'not_handled'
}

export function IssueReviewCard({
  finding,
  index,
  total,
  draft,
  disabled,
  rawCard,
  patchSource = 'claude',
  onDraftChange,
}: IssueReviewCardProps) {
  const isTriagePatch = patchSource === 'triaging'
  const suggestionLabel = isTriagePatch ? 'Triaging patch (reference only)' : 'Claude suggestion (reference only)'
  const styles = severityClasses(finding.severity)
  const suggested = finding.suggested_patch ?? null
  const policyIssue = isPolicyFinding(finding.field_path, finding.dimension)
  const currentPolicy = policyIssue
    ? resolvePolicyObject(finding.current_from_card ?? finding.current_value, rawCard)
    : null
  const suggestedPolicy = policyIssue ? resolvePolicyObject(suggested, rawCard) : null
  const policyPatchActionable = policyIssue && hasActionablePolicyPatch(suggested ?? undefined)
  const policyDiffIdentical =
    policyPatchActionable
    && JSON.stringify(formatJson(currentPolicy)) === JSON.stringify(formatJson(suggestedPolicy))
  const signalsById = Object.fromEntries(indexSignals(rawCard).map((signal) => [signal.signal_id, signal]))

  return (
    <section className={`rounded-lg border p-4 shadow-sm ${styles.panel}`}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-stone-600">
          Issue {index + 1} / {total}
        </span>
        <span className={`rounded border px-2 py-0.5 text-[11px] font-semibold uppercase ${styles.badge}`}>
          {styles.label}
        </span>
        <span className="rounded bg-white/70 px-2 py-0.5 text-[11px] font-medium text-stone-700">
          {isTriagePatch ? 'Triaging patch' : dimensionLabel(finding.dimension)}
        </span>
        {!isTriagePatch && finding.reviewer_confidence && (
          <span className="text-[11px] text-stone-600">confidence: {finding.reviewer_confidence}</span>
        )}
      </div>

      <h3 className="font-mono text-sm font-semibold text-stone-900">{finding.issue_id}</h3>
      {finding.explanation ? (
        <SignalText
          text={finding.explanation}
          signalsById={signalsById}
          as="p"
          className="mt-2 text-sm leading-relaxed text-stone-800"
        />
      ) : isTriagePatch ? (
        <p className="mt-2 text-sm text-stone-600">
          Field changed in triaging: <span className="font-mono">{finding.field_path}</span>
        </p>
      ) : null}

      {(finding.dict_key_issues?.length ?? 0) > 0 && (
        <div className="mt-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
          <div className="font-semibold">Dict key issue in expression</div>
          <ul className="mt-1 list-disc pl-5">
            {finding.dict_key_issues?.map((issue) => (
              <li key={`${issue.variable}-${issue.key_used}`}>{issue.message}</li>
            ))}
          </ul>
        </div>
      )}

      {policyIssue && currentPolicy ? (
        <div className="mt-4">
          {policyPatchActionable && !policyDiffIdentical ? (
            <>
              <div className="mb-2 text-xs text-stone-600">
                Policy diff — changed lines highlighted (current: amber/red, suggested: green)
              </div>
              <JsonDiffView
                left={currentPolicy}
                right={suggestedPolicy}
                leftLabel={`Current — ${finding.field_path || 'confirmation_policy'}`}
                rightLabel={suggestionLabel}
              />
            </>
          ) : (
            <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950">
              Claude did not return a machine-applicable <code>confirmation_policy</code> patch for this finding
              (often prose-only guidance). Use the direct card editor above to apply your own changes.
              {suggested && (
                <pre className="mt-3 max-h-48 overflow-auto rounded border border-amber-100 bg-white p-2 text-xs text-stone-800">
                  {formatValue(suggested)}
                </pre>
              )}
            </div>
          )}
          {finding.evidence_from_note && (
            <div className="mt-3">
              <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-600">
                Evidence from note
              </div>
              <p className="rounded-md border border-amber-200 bg-amber-50/80 p-2 text-xs leading-relaxed text-amber-950">
                {finding.evidence_from_note}
              </p>
            </div>
          )}
        </div>
      ) : (
        <div className="mt-4 grid gap-4 lg:grid-cols-2 lg:items-stretch">
          <div className="flex min-h-0 flex-col">
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-600">
              Current — {finding.field_path || 'value'}
            </div>
            <pre className="min-h-[12rem] flex-1 overflow-auto rounded-md border border-stone-300 bg-white p-3 text-xs">
              {formatValue(finding.current_value ?? finding.current_from_card)}
            </pre>
            {finding.evidence_from_note && (
              <div className="mt-3">
                <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-600">
                  Evidence from note
                </div>
                <p className="rounded-md border border-amber-200 bg-amber-50/80 p-2 text-xs leading-relaxed text-amber-950">
                  {finding.evidence_from_note}
                </p>
              </div>
            )}
          </div>

          <div className="flex min-h-0 flex-col">
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-600">
              {suggestionLabel}
            </div>
            {suggested ? (
              <pre className="min-h-[12rem] flex-1 overflow-auto rounded-md border border-stone-300 bg-white/80 p-3 text-xs">
                {formatValue(suggested)}
              </pre>
            ) : (
              <p className="min-h-[12rem] flex-1 rounded-md border border-dashed border-stone-300 bg-white/50 p-3 text-sm text-stone-600">
                No automated patch suggested.
              </p>
            )}
          </div>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={disabled}
          onClick={() => onDraftChange({ ...draft, decision: 'handled' })}
          className={`rounded-md px-3 py-1.5 text-sm font-medium ${
            draft.decision === 'handled'
              ? 'bg-emerald-700 text-white'
              : 'bg-white border border-stone-300 text-stone-800 hover:bg-stone-50'
          } disabled:opacity-50`}
        >
          Handled
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onDraftChange({ ...draft, decision: 'not_handled' })}
          className={`rounded-md px-3 py-1.5 text-sm font-medium ${
            draft.decision === 'not_handled'
              ? 'bg-stone-800 text-white'
              : 'bg-white border border-stone-300 text-stone-800 hover:bg-stone-50'
          } disabled:opacity-50`}
        >
          Not handled
        </button>
        {draft.decision === 'pending' && (
          <span className="text-xs text-stone-600">Mark each issue before finalizing this card.</span>
        )}
      </div>

      <div className="mt-3">
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-stone-600">
          Reviewer note (optional)
        </label>
        <input
          className="w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm disabled:bg-stone-100"
          disabled={disabled}
          value={draft.reviewer_note}
          onChange={(event) => onDraftChange({ ...draft, reviewer_note: event.target.value })}
          placeholder="How was this addressed?"
        />
      </div>
    </section>
  )
}

export function buildIssueDraft(finding: ReviewFinding): IssueDraft {
  const saved = finding.decision?.decision
  const hasSaved = saved === 'handled' || saved === 'not_handled' || saved === 'accept' || saved === 'reject'
  return {
    issue_id: finding.issue_id,
    field_path: finding.field_path,
    decision: hasSaved ? normalizeSavedDecision(saved) : 'not_handled',
    reviewer_note: finding.decision?.reviewer_note ?? '',
  }
}
