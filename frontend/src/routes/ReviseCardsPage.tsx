import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { fetchReviewBatches, fetchReviewBatch, fetchReviewCard, finalizeReviewCard } from '../api/claudeReview'
import { buildUserCardEditDraft, CardContentEditor, userCardEditToPatch } from '../revise-cards/CardContentEditor'
import { CardSidebar } from '../revise-cards/CardSidebar'
import { buildIssueDraft, IssueReviewCard } from '../revise-cards/IssueReviewCard'
import { SignalLegend, SignalText } from '../revise-cards/SignalText'
import { indexSignals } from '../revise-cards/signalUtils'
import type { IssueDraft, ReviewBatch, ReviewCardBundle, ReviewCardSummary, UserCardEditDraft } from '../revise-cards/types'
import { dimensionLabel, severityClasses } from '../revise-cards/utils'
import { CommandFooter } from '../components/CommandFooter'
import {
  fetchReviewerAccess,
  isReviewerAllowed,
  loadStoredReviewerName,
  reviewerAccessHint,
  storeReviewerName,
  type ReviewerAccessConfig,
} from '../utils/reviewerAccess'

export function ReviseCardsPage() {
  const [params, setParams] = useSearchParams()
  const [batches, setBatches] = useState<ReviewBatch[]>([])
  const [batchId, setBatchId] = useState<string | null>(params.get('batch'))
  const [cards, setCards] = useState<ReviewCardSummary[]>([])
  const [selectedCardId, setSelectedCardId] = useState<string | null>(params.get('card_id'))
  const [bundle, setBundle] = useState<ReviewCardBundle | null>(null)
  const [drafts, setDrafts] = useState<Record<string, IssueDraft>>({})
  const [userCardEdit, setUserCardEdit] = useState<UserCardEditDraft | null>(null)
  const [showCardEditor, setShowCardEditor] = useState(true)
  const [reviewer, setReviewer] = useState(loadStoredReviewerName)
  const [reviewerAccess, setReviewerAccess] = useState<ReviewerAccessConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [cardLoading, setCardLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [cardLoadError, setCardLoadError] = useState<string | null>(null)
  const [finalizeError, setFinalizeError] = useState<string | null>(null)
  const [finalizeMessage, setFinalizeMessage] = useState<string | null>(null)
  const [finalizing, setFinalizing] = useState(false)
  const mainPanelRef = useRef<HTMLElement>(null)
  const mainScrollTopRef = useRef(0)
  const activeBatchRef = useRef<string | null>(batchId)

  useEffect(() => {
    activeBatchRef.current = batchId
  }, [batchId])

  const sortBatches = useCallback((rows: ReviewBatch[]) => {
    return [...rows].sort((a, b) => b.batch_id.localeCompare(a.batch_id))
  }, [])

  useEffect(() => {
    fetchReviewerAccess().then(setReviewerAccess).catch(() => {
      setReviewerAccess({ allowed_reviewers_all: true, allowed_reviewers: [] })
    })
    let cancelled = false
    setLoading(true)
    fetchReviewBatches()
      .then(({ batches: loaded }) => {
        if (cancelled) return
        const sorted = sortBatches(loaded)
        setBatches(sorted)
        const urlBatch = new URLSearchParams(window.location.search).get('batch')
        setBatchId((current) => {
          if (urlBatch && sorted.some((batch) => batch.batch_id === urlBatch)) return urlBatch
          if (current && sorted.some((batch) => batch.batch_id === current)) return current
          return sorted[0]?.batch_id ?? null
        })
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message || 'Failed to load review batches')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [sortBatches])

  useEffect(() => {
    const batchParam = params.get('batch')
    if (batchParam && batchParam !== batchId) {
      setBatchId(batchParam)
    }
    const cardParam = params.get('card_id')
    if (cardParam && cardParam !== selectedCardId) {
      setSelectedCardId(cardParam)
    }
  }, [params, batchId, selectedCardId])

  const refreshBatch = useCallback(async (id: string) => {
    const summary = await fetchReviewBatch(id)
    if (activeBatchRef.current !== id) return summary.cards
    setCards(summary.cards)
    return summary.cards
  }, [])

  const updateParams = useCallback(
    (cardId: string | null, batch: string | null) => {
      const next = new URLSearchParams()
      if (batch) next.set('batch', batch)
      if (cardId) next.set('card_id', cardId)
      setParams(next)
    },
    [setParams],
  )

  useEffect(() => {
    if (!batchId) return
    let cancelled = false
    setError(null)
    setCards([])
    refreshBatch(batchId)
      .then((loadedCards) => {
        if (cancelled || activeBatchRef.current !== batchId) return
        const paramCard = new URLSearchParams(window.location.search).get('card_id')
        const validParam =
          paramCard && loadedCards.some((card) => card.card_id === paramCard)
        if (validParam) {
          setSelectedCardId(paramCard)
        } else if (loadedCards[0]?.card_id) {
          const fallback = loadedCards[0].card_id
          setSelectedCardId(fallback)
          updateParams(fallback, batchId)
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message || 'Failed to load batch')
      })
    return () => {
      cancelled = true
    }
  }, [batchId, refreshBatch, updateParams])

  useEffect(() => {
    if (!batchId || !selectedCardId) {
      setBundle(null)
      setDrafts({})
      setUserCardEdit(null)
      setCardLoadError(null)
      return
    }
    let cancelled = false
    setCardLoading(true)
    setCardLoadError(null)
    setFinalizeError(null)
    setFinalizeMessage(null)
    fetchReviewCard(batchId, selectedCardId)
      .then((data) => {
        if (cancelled) return
        if (data.card_id !== selectedCardId) return
        setBundle(data)
        const nextDrafts: Record<string, IssueDraft> = {}
        for (const finding of data.findings) {
          nextDrafts[finding.issue_id] = buildIssueDraft(finding)
        }
        setDrafts(nextDrafts)
        setUserCardEdit(buildUserCardEditDraft(data.raw_card, null, data.user_card_edit ?? null))
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setCardLoadError(err.message || 'Failed to load card review')
          setBundle(null)
        }
      })
      .finally(() => {
        if (!cancelled) setCardLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [batchId, selectedCardId])

  const handleSelectCard = (cardId: string) => {
    if (mainPanelRef.current) {
      mainScrollTopRef.current = mainPanelRef.current.scrollTop
    }
    setSelectedCardId(cardId)
    updateParams(cardId, batchId)
  }

  useLayoutEffect(() => {
    const panel = mainPanelRef.current
    if (!panel) return
    panel.scrollTop = mainScrollTopRef.current
  }, [selectedCardId, cardLoading, bundle?.card_id])

  const pendingCount = useMemo(
    () => Object.values(drafts).filter((draft) => draft.decision === 'pending').length,
    [drafts],
  )

  const notHandledCount = useMemo(
    () => Object.values(drafts).filter((draft) => draft.decision === 'not_handled').length,
    [drafts],
  )

  const outstandingCount = pendingCount + notHandledCount
  const hasFindings = (bundle?.findings.length ?? 0) > 0
  const activeBatch = batches.find((batch) => batch.batch_id === batchId)
  const isTriageBatch = activeBatch?.source === 'triaging'
  const reviewerValid = reviewerAccess ? isReviewerAllowed(reviewer, reviewerAccess) : Boolean(reviewer.trim())

  const hasSaveableDirectEdits = useMemo(() => {
    if (!userCardEdit || !bundle?.raw_card) return false
    if (userCardEdit.dirty) return true
    try {
      return Object.keys(userCardEditToPatch(userCardEdit, bundle.raw_card)).length > 0
    } catch {
      return false
    }
  }, [userCardEdit, bundle?.raw_card])

  const canFinalize = Boolean(
    bundle &&
    !finalizing &&
    reviewerValid &&
    pendingCount === 0 &&
    (!bundle.finalized || hasSaveableDirectEdits || isTriageBatch),
  )

  const finalizeDisabledReason = useMemo(() => {
    if (!bundle) return 'Loading card…'
    if (finalizing) return 'Saving…'
    if (!reviewerValid) {
      return reviewerAccess ? reviewerAccessHint(reviewerAccess, reviewer) : 'Enter a reviewer name to save.'
    }
    if (pendingCount > 0) {
      return `Mark ${pendingCount} issue(s) as handled or not handled before saving.`
    }
    if (bundle.finalized && !hasSaveableDirectEdits && !isTriageBatch) {
      return 'Make a direct card edit to save updates on an already-finalized card.'
    }
    return null
  }, [
    bundle,
    finalizing,
    reviewerValid,
    reviewerAccess,
    pendingCount,
    hasSaveableDirectEdits,
    isTriageBatch,
  ])

  const handleFinalizeCard = async () => {
    if (!bundle || !batchId || !userCardEdit) return
    if (!reviewerValid) {
      setFinalizeError(reviewerAccess ? reviewerAccessHint(reviewerAccess, reviewer) : 'Reviewer name is required.')
      return
    }
    if (pendingCount > 0) {
      setFinalizeError('Mark every issue as handled or not handled before finalizing.')
      return
    }

    try {
      JSON.parse(userCardEdit.confirmation_policy_json)
    } catch {
      setFinalizeError('Fix confirmation policy JSON before finalizing.')
      return
    }
    for (const question of userCardEdit.follow_up_questions) {
      try {
        const parsed = JSON.parse(question.choices_json)
        if (!Array.isArray(parsed)) {
          setFinalizeError(`Follow-up "${question.missing_variable}": choices must be a JSON array.`)
          return
        }
      } catch {
        setFinalizeError(`Follow-up "${question.missing_variable}": invalid choices JSON.`)
        return
      }
    }

    setFinalizing(true)
    setFinalizeError(null)
    setFinalizeMessage(null)
    try {
      const userPatch = userCardEditToPatch(userCardEdit, bundle.raw_card)
      const patchToSave =
        Object.keys(userPatch).length > 0
          ? userPatch
          : bundle.user_card_edit && Object.keys(bundle.user_card_edit).length > 0
            ? bundle.user_card_edit
            : null
      if (isTriageBatch && !patchToSave) {
        setFinalizeError('No triaging patch to finalize for this card.')
        setFinalizing(false)
        return
      }
      const issues = bundle.findings.map((finding) => {
        const draft = drafts[finding.issue_id]
        return {
          issue_id: draft.issue_id,
          decision: draft.decision as 'handled' | 'not_handled',
          field_path: draft.field_path,
          reviewer_note: draft.reviewer_note,
        }
      })
      const result = await finalizeReviewCard(bundle.card_id, {
        batch_id: batchId,
        reviewer: reviewer.trim(),
        issues,
        user_card_edit: patchToSave,
      })
      setFinalizeMessage(
        (hasFindings
          ? `Saved ${result.handled_count} handled / ${result.not_handled_count} not handled.`
          : isTriageBatch
            ? 'Triaging patch finalized.'
            : 'Card finalized (no issues to triage).') +
          (result.user_edit_saved ? ` Your card edits → ${result.user_card_edits_path}.` : '') +
          ` Decisions → ${result.decisions_path}`,
      )
      const refreshed = await fetchReviewCard(batchId, bundle.card_id)
      setBundle(refreshed)
      await refreshBatch(batchId)
    } catch (err) {
      setFinalizeError(err instanceof Error ? err.message : 'Failed to finalize card')
    } finally {
      setFinalizing(false)
    }
  }

  const signalSummaries = useMemo(() => indexSignals(bundle?.raw_card), [bundle?.raw_card])
  const triageChangedSummary = useMemo(() => {
    const changed = bundle?.triage_changed_fields
    if (!changed) return []
    const labels: string[] = []
    for (const [signalId, fields] of Object.entries(changed.signals || {})) {
      const parts: string[] = []
      if (fields.expression) parts.push('expression')
      if (fields.direction) parts.push('direction')
      if (fields.active) parts.push('active')
      if (parts.length) labels.push(`${signalId}: ${parts.join(', ')}`)
    }
    if (changed.confirmation_policy) labels.push('confirmation policy')
    return labels
  }, [bundle?.triage_changed_fields])
  const signalsById = useMemo(
    () => Object.fromEntries(signalSummaries.map((signal) => [signal.signal_id, signal])),
    [signalSummaries],
  )

  if (loading) {
    return <div className="flex h-full items-center justify-center text-stone-600">Loading review batches…</div>
  }

  if (!batches.length) {
    return (
      <div className="mx-auto max-w-2xl p-8">
        <h1 className="text-2xl font-semibold text-stone-900">Revise Cards</h1>
        <p className="mt-3 text-stone-700">
          No review batches found. Run Claude review scripts, or save patches from the{' '}
          <Link to="/triaging" className="text-amber-800 underline-offset-2 hover:underline">
            triaging app
          </Link>
          .
        </p>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-screen flex-col bg-[#f5f1ea]">
      <header className="border-b border-stone-300 bg-white/90 px-4 py-3 backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-lg font-semibold text-stone-900">Revise Cards</h1>
              <Link to="/" className="text-sm text-stone-600 underline-offset-2 hover:underline">
                Home
              </Link>
              <Link to="/diagnose" className="text-sm text-stone-600 underline-offset-2 hover:underline">
                Diagnosis map
              </Link>
            </div>
            <p className="text-sm text-stone-600">
              {activeBatch?.pathway_filter || 'Review batch'} · {activeBatch?.card_count ?? 0} cards
              {isTriageBatch ? (
                <>
                  {' '}
                  ·{' '}
                  <Link to="/triaging" className="text-amber-800 underline-offset-2 hover:underline">
                    triaging app
                  </Link>
                </>
              ) : null}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs text-stone-600">Batch</label>
            <select
              className="rounded-md border border-stone-300 bg-white px-2 py-1 text-sm"
              value={batchId ?? ''}
              onChange={(event) => {
                const nextBatchId = event.target.value
                setBatchId(nextBatchId)
                setSelectedCardId(null)
                setBundle(null)
                updateParams(null, nextBatchId)
              }}
            >
              {batches.map((batch) => (
                <option key={batch.batch_id} value={batch.batch_id}>
                  {batch.source === 'triaging'
                    ? `Triaging: ${batch.catalog_filename || batch.batch_id}`
                    : `Claude: ${batch.batch_id}`}{' '}
                  ({batch.finalized_card_count}/{batch.card_count} finalized)
                </option>
              ))}
            </select>
            <input
              className="rounded-md border border-stone-300 bg-white px-2 py-1 text-sm"
              placeholder="Reviewer name"
              value={reviewer}
              onChange={(event) => {
                setReviewer(event.target.value)
                storeReviewerName(event.target.value)
              }}
            />
          </div>
        </div>
        {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
        {reviewerAccess && !reviewerValid && reviewerAccessHint(reviewerAccess, reviewer) ? (
          <p className="mt-2 text-xs text-red-700">{reviewerAccessHint(reviewerAccess, reviewer)}</p>
        ) : null}
      </header>

      <div className="flex min-h-0 flex-1">
        <CardSidebar cards={cards} selectedCardId={selectedCardId} onSelect={handleSelectCard} />

        <main ref={mainPanelRef} className="relative min-w-0 flex-1 overflow-y-auto p-4">
          {cardLoadError ? (
            <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900">
              <p className="font-semibold">Could not load {selectedCardId}</p>
              <p className="mt-2">{cardLoadError}</p>
            </div>
          ) : bundle && (bundle.card_id === selectedCardId || cardLoading) ? (
            <>
              {cardLoading && bundle.card_id !== selectedCardId && (
                <div className="sticky top-0 z-10 mb-3 rounded-md border border-stone-300 bg-white/95 px-3 py-2 text-sm text-stone-600 shadow-sm backdrop-blur">
                  Loading card review…
                </div>
              )}
              <div className={cardLoading && bundle.card_id !== selectedCardId ? 'pointer-events-none opacity-40' : ''}>
              <div className="mb-4 rounded-lg border border-stone-300 bg-white p-4 shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <h2 className="font-mono text-sm font-semibold text-stone-900">{bundle.card_id}</h2>
                    {bundle.summary && <p className="mt-2 text-sm text-stone-700">{bundle.summary}</p>}
                    {isTriageBatch ? (
                      <div className="mt-3 flex flex-wrap gap-2">
                        <span className="rounded border border-amber-300 bg-amber-50 px-2 py-0.5 text-xs font-semibold uppercase text-amber-900">
                          Triaging patch
                        </span>
                        {activeBatch?.catalog_filename ? (
                          <span className="rounded border border-stone-200 bg-stone-50 px-2 py-0.5 font-mono text-[11px] text-stone-700">
                            {activeBatch.catalog_filename}
                          </span>
                        ) : null}
                      </div>
                    ) : (
                      <div className="mt-3 flex flex-wrap gap-2">
                        <span
                          className={`rounded border px-2 py-0.5 text-xs font-semibold uppercase ${severityClasses('', bundle.overall_score).badge}`}
                        >
                          {bundle.overall_score}
                        </span>
                        {Object.entries(bundle.dimensions).map(([key, dim]) => {
                          const dimStyles = severityClasses('', dim.score)
                          return (
                            <span
                              key={key}
                              className={`rounded border px-2 py-0.5 text-[11px] font-medium ${dimStyles.badge}`}
                            >
                              {dimensionLabel(key)}: {dim.score}
                            </span>
                          )
                        })}
                      </div>
                    )}
                    {isTriageBatch && triageChangedSummary.length > 0 ? (
                      <p className="mt-2 text-xs text-amber-900">
                        Changed in triaging: {triageChangedSummary.join(' · ')}
                      </p>
                    ) : null}
                    {isTriageBatch && bundle.patch_stale ? (
                      <p className="mt-2 text-xs text-red-800">
                        Saved triaging patch was discarded because the raw card changed after the patch was saved.
                        Edit from current card content; saving will write a new patch.
                      </p>
                    ) : null}
                  </div>
                  <div className="text-right">
                    {bundle.finalized && (
                      <div className="mb-2 rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
                        Finalized {bundle.finalized_at ? `at ${bundle.finalized_at}` : ''}
                      </div>
                    )}
                    <button
                      type="button"
                      disabled={!canFinalize}
                      onClick={() => void handleFinalizeCard()}
                      className="rounded-md bg-stone-900 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-stone-400"
                      title={finalizeDisabledReason ?? undefined}
                    >
                      {finalizing
                        ? 'Saving…'
                        : bundle.finalized
                          ? 'Save updates'
                          : isTriageBatch
                            ? 'Finalize patch'
                            : 'Finalize card'}
                    </button>
                    {!canFinalize && finalizeDisabledReason ? (
                      <p className="mt-2 text-xs text-amber-800">{finalizeDisabledReason}</p>
                    ) : null}
                    {outstandingCount > 0 && (
                      <p className="mt-2 text-xs text-amber-800">
                        {pendingCount > 0 && `${pendingCount} issue(s) still need a handled/not handled mark`}
                        {pendingCount > 0 && notHandledCount > 0 && ' · '}
                        {notHandledCount > 0 && `${notHandledCount} issue(s) not handled`}
                      </p>
                    )}
                  </div>
                </div>

                {bundle.overall_reasoning_note && (
                  <div className="mt-4 border-t border-stone-200 pt-4">
                    <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-600">
                      Overall reasoning note
                    </div>
                    <SignalText
                      text={bundle.overall_reasoning_note}
                      signalsById={signalsById}
                      as="p"
                      className="text-sm leading-relaxed text-stone-800"
                    />
                    <SignalLegend signals={signalSummaries} />
                  </div>
                )}

                {userCardEdit && (
                  <div className="mt-4 border-t border-stone-200 pt-4">
                    <button
                      type="button"
                      className="text-sm font-medium text-sky-800 underline-offset-2 hover:underline"
                      onClick={() => setShowCardEditor((open) => !open)}
                    >
                      {showCardEditor ? 'Hide direct card editor' : 'Edit note, signals, and confirmation policy'}
                    </button>
                    {showCardEditor && (
                      <div className="mt-3">
                        <CardContentEditor
                          draft={userCardEdit}
                          disabled={finalizing}
                          onChange={setUserCardEdit}
                        />
                      </div>
                    )}
                  </div>
                )}

                {finalizeError && <p className="mt-3 text-sm text-red-700">{finalizeError}</p>}
                {finalizeMessage && <p className="mt-3 text-sm text-emerald-800">{finalizeMessage}</p>}
                {bundle.finalized && (
                  <p className="mt-3 text-xs text-stone-600">
                    After direct edits, propagate to raw cards:{' '}
                    <code className="rounded bg-stone-100 px-1">
                      python scripts/review/apply_user_card_edits.py
                    </code>
                    {' '}then{' '}
                    <code className="rounded bg-stone-100 px-1">
                      python scripts/reload_evidence_cards.py --prefix …
                    </code>
                  </p>
                )}
                {bundle.user_card_edit_status?.has_saved_edit && (
                  <p className="mt-2 text-xs text-stone-600">
                    Direct edit status:{' '}
                    {bundle.user_card_edit_status.propagated_at
                      ? bundle.user_card_edit_status.in_sync_with_raw_card
                        ? `propagated (${bundle.user_card_edit_status.propagated_at})`
                        : `propagated previously (${bundle.user_card_edit_status.propagated_at}) but raw card changed since then`
                      : 'saved but not yet propagated to raw card'}
                  </p>
                )}
                {!bundle.finalized && (
                  <p className="mt-3 text-xs text-stone-600">
                    {isTriageBatch
                      ? 'Triaging patch items are reference only. The direct card editor shows the raw card; finalize promotes your edits.'
                      : hasFindings
                        ? 'Claude suggestions are reference only. Use the direct card editor for changes, then mark issues handled.'
                        : 'No issues flagged on this card. Use the direct card editor to make changes, then finalize when ready.'}
                  </p>
                )}
              </div>

              <div className="space-y-4">
                {bundle.findings.length === 0 ? (
                  <div className="rounded-lg border border-stone-200 bg-stone-50 p-4 text-sm text-stone-700">
                    <p className="font-medium">No patch items for this card</p>
                    <p className="mt-1">
                      {isTriageBatch
                        ? 'This triaging batch has no saved signal or confirmation-policy changes for this card.'
                        : 'Claude rated this card as pass with no actionable findings. Use the direct card editor if you still need changes.'}
                    </p>
                  </div>
                ) : (
                  bundle.findings.map((finding, index) => (
                    <IssueReviewCard
                      key={finding.issue_id}
                      finding={finding}
                      index={index}
                      total={bundle.findings.length}
                      draft={drafts[finding.issue_id] ?? buildIssueDraft(finding)}
                      disabled={finalizing}
                      rawCard={bundle.raw_card}
                      patchSource={isTriageBatch ? 'triaging' : 'claude'}
                      onDraftChange={(draft) =>
                        setDrafts((prev) => ({ ...prev, [finding.issue_id]: draft }))
                      }
                    />
                  ))
                )}
              </div>
              </div>
            </>
          ) : cardLoading ? (
            <div className="text-stone-600">Loading card review…</div>
          ) : (
            <div className="text-stone-600">No review data for this card.</div>
          )}
          <CommandFooter
            title="Push finalized edits to raw cards and MongoDB"
            commands={[
              {
                label: 'Apply Claude / edited patches to raw JSON',
                command: '.\\.venv\\Scripts\\python.exe scripts\\review\\apply_claude_review_patches.py --apply',
              },
              {
                label: 'Apply direct editor saves from this app',
                command: '.\\.venv\\Scripts\\python.exe scripts\\review\\apply_user_card_edits.py',
              },
              {
                label: 'Reload one card prefix into Mongo (example)',
                command:
                  '.\\.venv\\Scripts\\python.exe scripts\\reload_evidence_cards.py --prefix agriculture__water_scarcity__drought',
              },
              {
                label: 'Reload full raw corpus',
                command: '.\\.venv\\Scripts\\python.exe scripts\\reload_evidence_cards.py',
              },
            ]}
          />
        </main>
      </div>
    </div>
  )
}
