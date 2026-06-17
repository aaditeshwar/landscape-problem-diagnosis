import type { DiagnosisResponse, FollowUpExchange, PathwayResult, TehsilRef } from '../types'
import type { FollowUpTarget } from '../utils/followUp'
import { followUpPromptLabel } from '../utils/followUp'
import { formatPathwayAerContext, formatPathwayHierarchy } from '../utils/pathwayLabels'
import { formatPanelUpdateActionList } from '../utils/panelUpdates'
import { SignalRichText } from './SignalRichText'

interface Props {
  selectedMwsUid: string | null
  analysisMwsUid?: string | null
  displayMwsUid?: string | null
  villageNames: string[]
  problem: string
  onProblemChange: (value: string) => void
  wantLlmOpinion: boolean
  onWantLlmOpinionChange: (value: boolean) => void
  onSubmit: () => void
  loading: boolean
  error: string | null
  diagnosis: DiagnosisResponse | null
  followUpHistory: FollowUpExchange[]
  followUpAnswer: string
  onFollowUpAnswerChange: (value: string) => void
  followUpTarget: FollowUpTarget | null
  canContinueConversation: boolean
  onSubmitFollowUp: () => void
  disabled: boolean
  mwsAerCode?: string | null
  retrievalAerTags?: string[] | null
  freezeContext?: boolean
  lockedTehsil?: TehsilRef | null
  mapTehsil?: TehsilRef | null
  displayLocation?: TehsilRef | null
}

export function DiagnosisPanel({
  selectedMwsUid,
  analysisMwsUid,
  displayMwsUid,
  villageNames,
  problem,
  onProblemChange,
  wantLlmOpinion,
  onWantLlmOpinionChange,
  onSubmit,
  loading,
  error,
  diagnosis,
  followUpHistory,
  followUpAnswer,
  onFollowUpAnswerChange,
  followUpTarget,
  canContinueConversation,
  onSubmitFollowUp,
  disabled,
  mwsAerCode,
  retrievalAerTags,
  freezeContext = false,
  lockedTehsil,
  mapTehsil,
  displayLocation,
}: Props) {
  const sectionTitle = followUpPromptLabel(followUpTarget, followUpHistory.length > 0)
  const resolvedMwsAer = mwsAerCode ?? diagnosis?.mws_aer_code ?? null
  const resolvedRetrievalAer = retrievalAerTags ?? diagnosis?.retrieval_aer_tags ?? null
  const panelMwsUid = displayMwsUid ?? analysisMwsUid ?? selectedMwsUid
  const reportMwsUid = analysisMwsUid ?? panelMwsUid
  const browsingDifferentTehsil =
    freezeContext &&
    !!lockedTehsil &&
    !!mapTehsil &&
    (lockedTehsil.state !== mapTehsil.state ||
      lockedTehsil.district !== mapTehsil.district ||
      lockedTehsil.tehsil !== mapTehsil.tehsil)
  const browsingDifferentMws =
    !!reportMwsUid && !!selectedMwsUid && selectedMwsUid !== reportMwsUid
  const browsingDuringRun = (loading || freezeContext) && (browsingDifferentTehsil || browsingDifferentMws)
  const browsingWhileFrozen = freezeContext && !loading && (browsingDifferentTehsil || browsingDifferentMws)
  const mapBrowseLabel = browsingDifferentTehsil
    ? `${mapTehsil?.tehsil}, ${mapTehsil?.district}`
    : selectedMwsUid
  const runEnabled = wantLlmOpinion ? Boolean(problem.trim()) : true
  const summaryHeading =
    diagnosis?.llm_skipped === false && (diagnosis?.want_llm_opinion ?? wantLlmOpinion) ? 'Answer' : 'Summary'

  function pathwayAerLine(pathway: PathwayResult) {
    const aer = formatPathwayAerContext(pathway, resolvedMwsAer, resolvedRetrievalAer)
    const tone =
      aer.alignment === 'exact'
        ? 'text-stone-500'
        : aer.alignment === 'neighbor'
          ? 'text-amber-800'
          : aer.alignment === 'mismatch'
            ? 'font-medium text-red-800'
            : 'text-stone-500'
    return (
      <div className={`mt-1 text-xs ${tone}`}>
        {aer.text}
        {aer.note ? ` · ${aer.note}` : ''}
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      <div>
        <h2 className="text-lg font-semibold text-stone-800">Problem diagnosis</h2>
        {panelMwsUid ? (
          <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50/70 px-3 py-2 text-sm text-stone-700">
            <div>
              <span className="font-medium">MWS:</span> {panelMwsUid}
            </div>
            {displayLocation ? (
              <div className="mt-1">
                <span className="font-medium">Tehsil:</span> {displayLocation.tehsil}
                <span className="mx-1 text-stone-400">·</span>
                <span className="font-medium">District:</span> {displayLocation.district}
                <span className="mx-1 text-stone-400">·</span>
                <span className="font-medium">State:</span> {displayLocation.state}
              </div>
            ) : null}
            {browsingDuringRun ? (
              <div className="mt-1 text-xs text-amber-800">
                Diagnosis running for MWS {reportMwsUid}. Map is viewing {mapBrowseLabel}; only the info panel follows map selection.
              </div>
            ) : browsingWhileFrozen ? (
              <div className="mt-1 text-xs text-amber-800">
                Diagnosis session is for MWS {reportMwsUid}. Map is viewing {mapBrowseLabel}; only the info panel follows map selection.
              </div>
            ) : null}
            {villageNames.length > 0 ? (
              <div className="mt-1">
                <span className="font-medium">Villages:</span> {villageNames.join(', ')}
              </div>
            ) : (
              <div className="mt-1 text-stone-500">No intersecting village names on record.</div>
            )}
          </div>
        ) : (
          <p className="mt-1 text-sm text-stone-500">Select an MWS on the map to run landscape diagnosis.</p>
        )}
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={wantLlmOpinion}
          onChange={(e) => onWantLlmOpinionChange(e.target.checked)}
          disabled={disabled || loading}
          className="rounded border-stone-400"
        />
        <span className="font-medium text-stone-700">Include LLM opinion</span>
      </label>

      {wantLlmOpinion ? (
        <label className="flex flex-col gap-2 text-sm">
          <span className="font-medium text-stone-700">Problem description</span>
          <textarea
            className="min-h-28 rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-200 disabled:bg-stone-100"
            value={problem}
            onChange={(e) => onProblemChange(e.target.value)}
            placeholder="e.g. Our wells are drying up and cotton yields are falling"
            disabled={disabled || loading}
          />
        </label>
      ) : (
        <p className="text-sm text-stone-600">
          Server-only diagnosis uses landscape data and evidence cards without a user question.
        </p>
      )}

      <button
        type="button"
        onClick={onSubmit}
        disabled={disabled || loading || !runEnabled}
        className="rounded-lg bg-amber-700 px-4 py-2 text-sm font-semibold text-white shadow hover:bg-amber-800 disabled:cursor-not-allowed disabled:bg-stone-300"
      >
        {loading ? 'Analyzing…' : 'Run diagnosis'}
      </button>

      {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

      {diagnosis && (
        <div className="space-y-4 border-t border-stone-200 pt-4">
          <p className="text-xs text-stone-500">
            Analysis for MWS {reportMwsUid}
            {browsingDuringRun || browsingWhileFrozen
              ? ` · map viewing ${mapBrowseLabel}`
              : ''}
            {!(browsingDuringRun || browsingWhileFrozen) && villageNames.length > 0
              ? ` · Villages: ${villageNames.join(', ')}`
              : ''}
          </p>
          {diagnosis.panel_update_explanation?.trim() ? (
            <section className="rounded-lg border border-sky-200 bg-sky-50/60 px-3 py-2">
              <h3 className="text-sm font-semibold text-sky-900">{summaryHeading}</h3>
              <p className="mt-1 text-sm text-stone-800">
                <SignalRichText
                  text={diagnosis.panel_update_explanation}
                  signalEvaluation={diagnosis.signal_evaluation}
                />
              </p>
            </section>
          ) : null}
          <section>
            <h3 className="text-sm font-semibold text-emerald-800">Confirmed pathways</h3>
            {diagnosis.confirmed_pathways.length === 0 ? (
              <p className="mt-1 text-sm text-stone-500">None yet.</p>
            ) : (
              <ul className="mt-2 space-y-2">
                {diagnosis.confirmed_pathways.map((p: PathwayResult) => (
                  <li key={p.pathway_id} className="rounded-lg bg-emerald-50 px-3 py-2 text-sm">
                    <div className="font-medium">{formatPathwayHierarchy(p)}</div>
                    {pathwayAerLine(p)}
                    <div className="text-xs uppercase text-emerald-700">{p.confidence} confidence</div>
                    {p.reasoning && (
                      <p className="mt-1 text-stone-700">
                        <SignalRichText
                          text={p.reasoning}
                          pathwayId={p.pathway_id}
                          signalEvaluation={diagnosis.signal_evaluation}
                        />
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {diagnosis.uncertain_pathways.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-amber-800">Uncertain pathways</h3>
              <p className="mt-1 text-xs text-amber-900/80">
                Not yet confirmed — follow-up questions may move these to confirmed.
              </p>
              <ul className="mt-2 space-y-2">
                {diagnosis.uncertain_pathways.map((p: PathwayResult) => (
                  <li key={p.pathway_id} className="rounded-lg bg-amber-50 px-3 py-2 text-sm">
                    <div className="font-medium">{formatPathwayHierarchy(p)}</div>
                    {pathwayAerLine(p)}
                    <div className="text-xs uppercase text-amber-700">{p.confidence} confidence</div>
                    {p.reasoning && (
                      <p className="mt-1 text-stone-700">
                        <SignalRichText
                          text={p.reasoning}
                          pathwayId={p.pathway_id}
                          signalEvaluation={diagnosis.signal_evaluation}
                        />
                      </p>
                    )}
                    {p.missing_variable_questions && p.missing_variable_questions.length > 0 ? (
                      <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-stone-600">
                        {p.missing_variable_questions.map((q) => (
                          <li key={`${p.pathway_id}-${q.variable}`}>{q.question}</li>
                        ))}
                      </ul>
                    ) : null}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {diagnosis.solutions.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-stone-800">Suggested solutions</h3>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-stone-700">
                {diagnosis.solutions.map((s: string) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </section>
          )}

          {followUpHistory.length > 0 && (
            <section className="space-y-3">
              <h3 className="text-sm font-semibold text-stone-800">Follow-up conversation</h3>
              {followUpHistory.map((entry, index) => (
                <div
                  key={`${index}-${entry.question.slice(0, 24)}`}
                  className="rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm"
                >
                  <div className="text-xs font-medium uppercase tracking-wide text-stone-500">
                    Question {index + 1}
                  </div>
                  <p className="mt-1 text-stone-800">{entry.question}</p>
                  <div className="mt-2 text-xs font-medium uppercase tracking-wide text-stone-500">Your answer</div>
                  <p className="mt-1 text-stone-700">{entry.answer}</p>
                  {entry.revision ? (
                    <div className="mt-2 rounded-md border border-violet-100 bg-violet-50/60 px-2 py-2">
                      <div className="text-xs font-medium uppercase tracking-wide text-violet-800">
                        Diagnosis update
                      </div>
                      {entry.revision.summary ? (
                        <p className="mt-1 text-sm text-stone-800">
                          <SignalRichText
                            text={entry.revision.summary}
                            signalEvaluation={entry.signalEvaluation ?? diagnosis.signal_evaluation}
                          />
                        </p>
                      ) : null}
                      {entry.revision.pathway_changes.length > 0 ? (
                        <ul className="mt-2 space-y-1 text-sm text-stone-700">
                          {entry.revision.pathway_changes.map((change) => (
                            <li key={`${change.pathway_id}-${change.from}-${change.to}`}>
                              <span className="font-medium">
                                {formatPathwayHierarchy({ pathway_id: change.pathway_id })}
                              </span>
                              : {change.from} → {change.to}
                              {change.reason ? (
                                <p className="mt-1 text-xs text-stone-600">
                                  <SignalRichText
                                    text={change.reason}
                                    pathwayId={change.pathway_id}
                                    signalEvaluation={entry.signalEvaluation ?? diagnosis.signal_evaluation}
                                  />
                                </p>
                              ) : null}
                            </li>
                          ))}
                        </ul>
                      ) : entry.revision.improved ? (
                        <p className="mt-1 text-sm text-stone-700">Solutions or confidence were updated.</p>
                      ) : null}
                      {(entry.revision.pathway_interpretations?.length ?? 0) > 0 ? (
                        <div className="mt-2 space-y-2">
                          <div className="text-xs font-medium uppercase tracking-wide text-amber-900">
                            Evidence interpretation
                          </div>
                          {entry.revision.pathway_interpretations?.map((item) => (
                            <div
                              key={`${item.pathway_id}-${item.status}`}
                              className="rounded border border-amber-100 bg-amber-50/80 px-2 py-2 text-xs text-stone-700"
                            >
                              <div className="font-medium text-amber-900">
                                {formatPathwayHierarchy({ pathway_id: item.pathway_id })}
                                {item.status === 'ruled_out'
                                  ? ' · ruled out'
                                  : item.status
                                    ? ` · ${item.status}`
                                    : ''}
                              </div>
                              <p className="mt-1">
                                <SignalRichText
                                  text={item.reasoning}
                                  pathwayId={item.pathway_id}
                                  signalEvaluation={entry.signalEvaluation ?? diagnosis.signal_evaluation}
                                />
                              </p>
                            </div>
                          ))}
                        </div>
                      ) : !entry.revision.improved && !entry.revision.pathway_changes.length ? (
                        <p className="mt-1 text-sm text-stone-600">No material change to pathway ranking.</p>
                      ) : null}
                    </div>
                  ) : null}
                  <div className="mt-2 text-xs font-medium uppercase tracking-wide text-sky-700">Action taken</div>
                  {entry.actions.length > 0 ? (
                    <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-sky-900">
                      {formatPanelUpdateActionList(entry.actions).map((label) => (
                        <li key={label}>{label}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-1 text-sm text-stone-500">No additional charts were highlighted.</p>
                  )}
                  {entry.explanation?.trim() ? (
                    <>
                      <div className="mt-2 text-xs font-medium uppercase tracking-wide text-stone-500">Why</div>
                      <p className="mt-1 text-sm text-stone-800">
                        <SignalRichText
                          text={entry.explanation}
                          signalEvaluation={entry.signalEvaluation ?? diagnosis.signal_evaluation}
                        />
                      </p>
                    </>
                  ) : null}
                </div>
              ))}
            </section>
          )}

          {canContinueConversation && followUpTarget && (
            <section className="rounded-lg border border-amber-200 bg-amber-50/60 p-3">
              <h3 className="text-sm font-semibold text-amber-900">{sectionTitle}</h3>
              {(followUpTarget.question || diagnosis.follow_up_mcq?.question) ? (
                <p className="mt-1 text-sm text-stone-700">
                  {diagnosis.follow_up_mcq?.question ?? followUpTarget.question}
                </p>
              ) : (
                <p className="mt-1 text-sm text-stone-600">
                  No further structured questions from the diagnosis model. You can still add observations,
                  corrections, or clarifications below and the analysis will be updated.
                </p>
              )}
              {diagnosis.follow_up_mcq &&
              diagnosis.follow_up_mcq.variable === followUpTarget.variable ? (
                <div className="mt-2 space-y-2">
                  {diagnosis.follow_up_mcq.choices.map((choice) => (
                    <label
                      key={choice.id}
                      className="flex cursor-pointer items-start gap-2 rounded-md border border-stone-200 bg-white px-3 py-2 text-sm"
                    >
                      <input
                        type="radio"
                        name="follow-up-mcq"
                        value={choice.id}
                        checked={followUpAnswer === choice.id}
                        onChange={() => onFollowUpAnswerChange(choice.id)}
                        disabled={loading}
                        className="mt-0.5"
                      />
                      <span className="text-stone-800">{choice.label}</span>
                    </label>
                  ))}
                </div>
              ) : (
                <textarea
                  className="mt-2 min-h-20 w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm"
                  value={followUpAnswer}
                  onChange={(e) => onFollowUpAnswerChange(e.target.value)}
                  placeholder={
                    followUpTarget.question
                      ? 'Type your answer…'
                      : 'e.g. We also noticed siltation in the farm pond after last monsoon…'
                  }
                  disabled={loading}
                />
              )}
              <button
                type="button"
                onClick={onSubmitFollowUp}
                disabled={loading || !followUpAnswer.trim()}
                className="mt-2 rounded-lg bg-stone-800 px-3 py-2 text-sm font-medium text-white hover:bg-stone-900 disabled:bg-stone-300"
              >
                Submit answer
              </button>
            </section>
          )}
        </div>
      )}
    </div>
  )
}
