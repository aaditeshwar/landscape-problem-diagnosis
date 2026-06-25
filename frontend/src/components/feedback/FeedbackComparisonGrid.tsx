import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type {
  FeedbackContext,
  FeedbackSectionDraft,
  IndependentPathwayReview,
  PathwayResult,
  ReviewerPathwayComment,
} from '../../types'
import {
  buildSignalEditorUrl,
  cardForPathway,
  feedbackSectionDomId,
  pathwaySectionKey,
  type AgreementValue,
} from '../../utils/feedbackSections'
import { formatPathwayHierarchy, productionLabel } from '../../utils/pathwayLabels'
import { AgreementControl } from './AgreementControl'
import { PathwaySignalStrip } from './PathwaySignalStrip'
import { SignalRichText } from '../SignalRichText'

type PathwayWithStatus = PathwayResult & { serverStatus: 'confirmed' | 'uncertain' }

interface Props {
  context: FeedbackContext
  snapshotId: string
  returnUrl: string
  sections: Record<string, FeedbackSectionDraft>
  onSectionChange: (sectionKey: string, patch: Partial<FeedbackSectionDraft>) => void
}

function ReadOnlyColumn({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-stone-200 bg-stone-50/80 p-3">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-500">{label}</div>
      <div className="text-sm text-stone-800">{children}</div>
    </div>
  )
}

function FeedbackColumn({
  sectionKey,
  draft,
  showLlm,
  signalEditorUrl,
  onSectionChange,
}: {
  sectionKey: string
  draft: FeedbackSectionDraft
  showLlm: boolean
  signalEditorUrl: string | null
  onSectionChange: (sectionKey: string, patch: Partial<FeedbackSectionDraft>) => void
}) {
  function setAgreement(field: 'server_agreement' | 'llm_agreement', value: AgreementValue | null) {
    onSectionChange(sectionKey, { [field]: value })
  }

  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50/40 p-3">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-amber-900">Your feedback</div>
      <div className="space-y-3">
        <AgreementControl
          label="Suggested reasoning"
          name={`${sectionKey}-server`}
          value={draft.server_agreement}
          onChange={(value) => setAgreement('server_agreement', value)}
        />
        {showLlm ? (
          <AgreementControl
            label="LLM opinion"
            name={`${sectionKey}-llm`}
            value={draft.llm_agreement}
            onChange={(value) => setAgreement('llm_agreement', value)}
          />
        ) : null}
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-xs font-medium text-stone-600">Free-text notes</span>
          <textarea
            value={draft.free_text ?? ''}
            onChange={(e) => onSectionChange(sectionKey, { free_text: e.target.value })}
            rows={4}
            className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-200"
            placeholder="What should change, and why?"
          />
        </label>
        {signalEditorUrl ? (
          <Link
            to={signalEditorUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex text-xs font-medium text-amber-900 underline decoration-amber-400 underline-offset-2 hover:text-amber-950"
          >
            See details and edit signals - advanced
          </Link>
        ) : null}
      </div>
    </div>
  )
}

function llmPathwayComment(
  commentary: ReviewerPathwayComment[] | undefined,
  pathwayId: string,
): ReviewerPathwayComment | undefined {
  return commentary?.find((item) => item.pathway_id === pathwayId)
}

function llmIndependentReview(
  reviews: IndependentPathwayReview[] | undefined,
  pathwayId: string,
): IndependentPathwayReview | undefined {
  return reviews?.find((item) => item.pathway_id === pathwayId)
}

function LlmPathwayOpinion({
  pathwayId,
  reviewerItem,
  independentItem,
  signalEvaluation,
}: {
  pathwayId: string
  reviewerItem?: ReviewerPathwayComment
  independentItem?: IndependentPathwayReview
  signalEvaluation: FeedbackContext['server_diagnosis']['signal_evaluation']
}) {
  const hasServerReview = Boolean(reviewerItem?.pathway_comment || reviewerItem?.agreement)
  const hasIndependent = Boolean(
    independentItem?.reasoning || independentItem?.pathway_present || independentItem?.key_datapoints?.length,
  )

  if (!hasServerReview && !hasIndependent) {
    return <span className="text-stone-500">No LLM commentary for this pathway.</span>
  }

  return (
    <div className="space-y-3">
      <div>
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-violet-800">
          Server evaluation review
        </div>
        {hasServerReview ? (
          <div>
            {reviewerItem?.agreement ? (
              <div className="mb-1 text-xs uppercase text-violet-800">{reviewerItem.agreement}</div>
            ) : null}
            {reviewerItem?.pathway_comment ? (
              <SignalRichText
                text={reviewerItem.pathway_comment}
                pathwayId={pathwayId}
                signalEvaluation={signalEvaluation}
              />
            ) : (
              <span className="text-stone-500">No server-evaluation commentary.</span>
            )}
          </div>
        ) : (
          <span className="text-stone-500">No server-evaluation commentary.</span>
        )}
      </div>
      <div className="border-t border-violet-200/80 pt-2">
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-violet-800">
          Independent assessment
        </div>
        {hasIndependent ? (
          <div>
            {independentItem?.pathway_present ? (
              <div className="mb-1 text-xs uppercase text-violet-800">
                {independentItem.pathway_present}
                {independentItem.confidence ? ` · ${independentItem.confidence}` : ''}
              </div>
            ) : null}
            {independentItem?.reasoning ? (
              <p className="text-sm text-stone-800">{independentItem.reasoning}</p>
            ) : null}
            {independentItem?.key_datapoints?.length ? (
              <p className="mt-1 text-xs text-stone-600">
                Datapoints: {independentItem.key_datapoints.join(' · ')}
              </p>
            ) : null}
          </div>
        ) : (
          <span className="text-stone-500">No independent assessment.</span>
        )}
      </div>
    </div>
  )
}

function PathwayStatusBadge({ status }: { status: 'confirmed' | 'uncertain' }) {
  return (
    <span
      className={`ml-2 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${
        status === 'confirmed'
          ? 'bg-emerald-100 text-emerald-800'
          : 'bg-amber-100 text-amber-900'
      }`}
    >
      {status === 'confirmed' ? 'Confirmed' : 'Uncertain'}
    </span>
  )
}

export function FeedbackComparisonGrid({
  context,
  snapshotId,
  returnUrl,
  sections,
  onSectionChange,
}: Props) {
  const showLlm = context.want_llm_opinion && !context.llm_skipped
  const skippedSystems = new Set(
    (context.skipped_production_systems ?? []).map((skip) => skip.production_system),
  )
  const pathways: PathwayWithStatus[] = [
    ...context.server_diagnosis.confirmed_pathways.map((pathway) => ({
      ...pathway,
      serverStatus: 'confirmed' as const,
    })),
    ...context.server_diagnosis.uncertain_pathways.map((pathway) => ({
      ...pathway,
      serverStatus: 'uncertain' as const,
    })),
  ].filter((pathway) => !pathway.production_system || !skippedSystems.has(pathway.production_system))
  const signalEvaluation = context.server_diagnosis.signal_evaluation
  const answerText =
    context.server_diagnosis.panel_update_explanation?.trim() ||
    context.server_diagnosis.summary?.trim() ||
    ''
  const llmSummaryText =
    context.llm_diagnosis?.change_review?.summary?.trim() || (showLlm ? answerText : '')

  function draftFor(sectionKey: string): FeedbackSectionDraft {
    return sections[sectionKey] ?? {}
  }

  function renderSectionGrid(options: {
    sectionKey: string
    title: ReactNode
    serverContent: ReactNode
    llmContent: ReactNode
    pathway?: PathwayResult
  }) {
    const { sectionKey, title, serverContent, llmContent, pathway } = options
    const card = pathway ? cardForPathway(context.retrieved_cards, pathway.pathway_id) : undefined
    const signalEditorUrl = buildSignalEditorUrl({
      clusterSuffix: card?.cluster_suffix ?? draftFor(sectionKey).linked_cluster_suffix,
      pathway: card?.causal_pathway ?? card?.pathway_id ?? pathway?.pathway_id,
      cardId: card?.card_id ?? draftFor(sectionKey).linked_card_id,
      snapshotId,
      returnUrl,
    })

    return (
      <section
        key={sectionKey}
        id={feedbackSectionDomId(sectionKey)}
        className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm"
      >
        <h3 className="mb-3 text-sm font-semibold text-stone-800">{title}</h3>
        <div className={`grid gap-3 ${showLlm ? 'lg:grid-cols-3' : 'lg:grid-cols-2'}`}>
          <ReadOnlyColumn label="Suggested reasoning">{serverContent}</ReadOnlyColumn>
          <FeedbackColumn
            sectionKey={sectionKey}
            draft={draftFor(sectionKey)}
            showLlm={showLlm}
            signalEditorUrl={signalEditorUrl}
            onSectionChange={onSectionChange}
          />
          {showLlm ? <ReadOnlyColumn label="LLM opinion">{llmContent}</ReadOnlyColumn> : null}
        </div>
      </section>
    )
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-sm font-semibold text-stone-800">Diagnosis feedback</h2>
        <p className="mt-1 text-xs text-stone-500">
          Compare server and LLM outputs, record agreement, and link to signal edits where evidence needs changing.
        </p>
      </div>

      {(context.skipped_production_systems?.length ?? 0) > 0 ? (
        <div className="rounded-lg border border-sky-200 bg-sky-50/80 px-3 py-2 text-sm text-sky-950">
          <div className="font-medium">Skipped at diagnosis time</div>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sky-900">
            {context.skipped_production_systems?.map((skip) => (
              <li key={`${skip.production_system}-${skip.rule_id ?? 'rule'}`}>
                <span className="font-medium">{productionLabel(skip.production_system)}</span>
                {skip.message ? `: ${skip.message}` : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {pathways.map((pathway) => {
        const sectionKey = pathwaySectionKey(pathway.pathway_id)
        const autoReasoning = pathway.reasoning ?? '—'
        const fullReasoningNote = context.server_diagnosis.pathway_notes[pathway.pathway_id]
        const llmItem = llmPathwayComment(context.llm_diagnosis?.reviewer_commentary, pathway.pathway_id)
        const independentItem = llmIndependentReview(
          context.llm_diagnosis?.independent_pathway_review,
          pathway.pathway_id,
        )
        const card = cardForPathway(context.retrieved_cards, pathway.pathway_id)

        return renderSectionGrid({
          sectionKey,
          title: (
            <span className="inline-flex flex-wrap items-center gap-1">
              <span>{formatPathwayHierarchy(pathway)}</span>
              <PathwayStatusBadge status={pathway.serverStatus} />
              <span className="text-xs font-normal uppercase text-stone-500">{pathway.confidence}</span>
            </span>
          ),
          pathway,
          serverContent: (
            <>
              <SignalRichText
                text={autoReasoning}
                pathwayId={pathway.pathway_id}
                signalEvaluation={signalEvaluation}
              />
              {fullReasoningNote ? (
                <p className="mt-2 text-sm text-stone-700">
                  <SignalRichText
                    text={fullReasoningNote}
                    pathwayId={pathway.pathway_id}
                    signalEvaluation={signalEvaluation}
                  />
                </p>
              ) : null}
              <PathwaySignalStrip
                pathwayId={pathway.pathway_id}
                card={card}
                signalEvaluation={signalEvaluation}
              />
            </>
          ),
          llmContent: (
            <LlmPathwayOpinion
              pathwayId={pathway.pathway_id}
              reviewerItem={llmItem}
              independentItem={independentItem}
              signalEvaluation={signalEvaluation}
            />
          ),
        })
      })}

      {renderSectionGrid({
        sectionKey: 'summary',
        title: showLlm ? 'Answer / summary' : 'Summary',
        serverContent:
          !showLlm && answerText ? (
            <SignalRichText text={answerText} signalEvaluation={signalEvaluation} />
          ) : showLlm ? (
            <span className="text-stone-500">Server does not provide a separate summary when LLM is enabled.</span>
          ) : (
            <span className="text-stone-500">No summary text.</span>
          ),
        llmContent: llmSummaryText ? (
          <SignalRichText text={llmSummaryText} signalEvaluation={signalEvaluation} />
        ) : (
          <span className="text-stone-500">No LLM summary.</span>
        ),
      })}

      {renderSectionGrid({
        sectionKey: 'solutions',
        title: 'Suggested solutions',
        serverContent:
          context.server_diagnosis.solutions.length > 0 ? (
            <ul className="list-disc space-y-1 pl-5">
              {context.server_diagnosis.solutions.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : (
            <span className="text-stone-500">None listed.</span>
          ),
        llmContent: context.llm_diagnosis?.solutions_review_notes?.trim() ? (
          context.llm_diagnosis.solutions_review_notes
        ) : (
          <span className="text-stone-500">No LLM solutions notes.</span>
        ),
      })}
    </div>
  )
}
