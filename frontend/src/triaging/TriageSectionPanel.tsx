import { useCallback, useEffect, useState } from 'react'
import {
  dashboardSectionUrl,
  evaluateTriageSection,
  fetchTriageCatalogPatches,
  saveTriageCatalogPatches,
  type CardMapResponse,
  type EvaluateSectionResult,
  type TriageCatalogPatches,
  type TriageChangedFields,
  type TriageSection,
} from '../api/triage'
import { ExternalLink } from '../components/ExternalLink'
import { applyCardPatch } from './applyCardPatch'
import { SignalGrid, type CardEditState, type FollowUpChoicesByMws } from './SignalGrid'
import { ConfusionMatrix, VariableTable } from './TriageMatrixPanels'

type Props = {
  section: TriageSection
  catalogFilename: string
  reviewer: string
  reviewerValid: boolean
  catalogPatches: TriageCatalogPatches | null
  cardMapsByMws: Record<string, CardMapResponse>
  cardMapsReady: boolean
  onPatchesSaved: (patches: TriageCatalogPatches) => void
}

function loadCardEditsForSection(
  section: TriageSection,
  cardMaps: Record<string, CardMapResponse>,
  catalogPatches: TriageCatalogPatches | null,
): {
  edits: Record<string, CardEditState>
  changedFields: Record<string, TriageChangedFields>
  stalePatchCardIds: string[]
} {
  const edits: Record<string, CardEditState> = {}
  const changedFields: Record<string, TriageChangedFields> = {}
  const stalePatchCardIds: string[] = []
  const builtPathways = [...section.predicted_pathways].sort()
  const uniqueMws = [...new Set(section.instances.map((inst) => inst.mws_id))]

  for (const mwsId of uniqueMws) {
    const map = cardMaps[mwsId]
    if (!map?.cards_full) continue
    for (const pathway of builtPathways) {
      const base = map.cards_full[pathway]
      const cardId = base?.card_id
      if (!cardId || edits[cardId]) continue
      const patchEntry = catalogPatches?.cards?.[cardId]
      const displayCard =
        patchEntry?.patch && !patchEntry.patch_stale && typeof patchEntry.patch === 'object'
          ? applyCardPatch(base, patchEntry.patch as Record<string, unknown>)
          : base
      edits[cardId] = {
        card_id: cardId,
        diagnostic_signals: structuredClone(displayCard.diagnostic_signals || []),
        confirmation_policy: structuredClone(displayCard.confirmation_policy || {}),
        missing_variable_questions: structuredClone(displayCard.missing_variable_questions || []),
      }
      if (patchEntry?.patch_stale) {
        stalePatchCardIds.push(cardId)
      }
      const savedChanged = patchEntry?.effective_changed_fields ?? patchEntry?.changed_fields
      if (savedChanged && !patchEntry?.patch_stale) {
        changedFields[cardId] = savedChanged
      }
    }
  }
  return { edits, changedFields, stalePatchCardIds }
}

export function TriageSectionPanel({
  section,
  catalogFilename,
  reviewer,
  reviewerValid,
  catalogPatches,
  cardMapsByMws,
  cardMapsReady,
  onPatchesSaved,
}: Props) {
  const [followUpChoices, setFollowUpChoices] = useState<FollowUpChoicesByMws>({})
  const [cardEdits, setCardEdits] = useState<Record<string, CardEditState>>({})
  const [savedChangedFields, setSavedChangedFields] = useState<Record<string, TriageChangedFields>>({})
  const [stalePatchCardIds, setStalePatchCardIds] = useState<string[]>([])
  const [evalResult, setEvalResult] = useState<EvaluateSectionResult | null>(null)
  const [loadingCards, setLoadingCards] = useState(true)
  const [playing, setPlaying] = useState(false)
  const [saving, setSaving] = useState(false)
  const [variablesCollapsed, setVariablesCollapsed] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const matrixColumns = section.matrix_columns ?? section.predicted_pathways

  useEffect(() => {
    if (!cardMapsReady) {
      setLoadingCards(true)
      return
    }
    setError(null)
    setEvalResult(null)
    setFollowUpChoices({})
    const loaded = loadCardEditsForSection(section, cardMapsByMws, catalogPatches)
    setCardEdits(loaded.edits)
    setSavedChangedFields(loaded.changedFields)
    setStalePatchCardIds(loaded.stalePatchCardIds)
    setLoadingCards(false)
  }, [section, catalogPatches, cardMapsByMws, cardMapsReady])

  const onFollowUpChoiceChange = useCallback((mwsId: string, variable: string, choiceId: string) => {
    setFollowUpChoices((prev) => ({
      ...prev,
      [mwsId]: { ...(prev[mwsId] || {}), [variable]: choiceId },
    }))
  }, [])

  const onEditChange = useCallback((cardId: string, edit: CardEditState) => {
    setCardEdits((prev) => ({ ...prev, [cardId]: edit }))
  }, [])

  const handlePlay = async () => {
    setPlaying(true)
    setError(null)
    setMessage(null)
    try {
      const result = await evaluateTriageSection({
        production_system: section.production_system,
        observed_stress: section.observed_stress,
        instances: section.instances,
        card_edits: Object.values(cardEdits).map((edit) => ({
          card_id: edit.card_id,
          diagnostic_signals: edit.diagnostic_signals,
          confirmation_policy: edit.confirmation_policy,
          missing_variable_questions: edit.missing_variable_questions,
        })),
        follow_up_by_mws: followUpChoices,
      })
      setEvalResult(result)
      setMessage('Evaluation complete.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Play failed')
    } finally {
      setPlaying(false)
    }
  }

  const handleSavePatches = async () => {
    if (!reviewerValid) {
      setError('Enter an allowed reviewer name before saving patches.')
      return
    }
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const cardIds = Object.keys(cardEdits)
      const result = await saveTriageCatalogPatches(catalogFilename, {
        reviewer: reviewer.trim(),
        cards: cardIds.map((cardId) => ({
          card_id: cardId,
          diagnostic_signals: cardEdits[cardId].diagnostic_signals,
          confirmation_policy: cardEdits[cardId].confirmation_policy,
        })),
      })
      const refreshed = await fetchTriageCatalogPatches(catalogFilename)
      onPatchesSaved(refreshed)
      const nextChanged: Record<string, TriageChangedFields> = {}
      for (const cardId of cardIds) {
        const entry = refreshed.cards[cardId]
        const savedChanged = entry?.effective_changed_fields ?? entry?.changed_fields
        if (savedChanged && !entry?.patch_stale) nextChanged[cardId] = savedChanged
      }
      setSavedChangedFields(nextChanged)
      setStalePatchCardIds([])
      if (result.saved_count === 0) {
        setError(
          'No changes differ from the on-disk raw card — nothing was saved. Edit signals so they differ from the propagated card file, then save again.',
        )
        return
      }
      setMessage(
        `Saved ${result.saved_count} patch(es) for ${catalogFilename}. Open revise-cards batch ${result.batch_id}.`,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const patchCount = catalogPatches
    ? Object.keys(catalogPatches.cards || {}).filter((cardId) => {
        const entry = catalogPatches.cards[cardId]
        return Object.prototype.hasOwnProperty.call(cardEdits, cardId) && !entry?.patch_stale
      }).length
    : 0

  return (
    <section id={section.section_key} className="space-y-4 rounded-xl border border-stone-200 bg-stone-50/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-stone-900">
            {section.production_system} · {section.observed_stress.replace(/_/g, ' ')}
          </h2>
          <p className="text-xs text-stone-500">
            {section.instances.length} case-study instances
            {patchCount ? ` · ${patchCount} saved patch(es) in catalog` : null}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={handlePlay}
            disabled={playing || loadingCards}
            className="rounded-md bg-amber-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-amber-800 disabled:opacity-50"
          >
            {playing ? 'Playing…' : '▶ Play'}
          </button>
          <button
            type="button"
            onClick={handleSavePatches}
            disabled={saving || loadingCards || !Object.keys(cardEdits).length || !reviewerValid}
            className="rounded-md border border-stone-300 bg-white px-3 py-1.5 text-sm hover:bg-stone-100 disabled:opacity-50"
            title="Save diffs as catalog-tagged patches for revise-cards"
          >
            {saving ? 'Saving…' : 'Save patches'}
          </button>
          <ExternalLink
            to={dashboardSectionUrl(section.production_system, section.observed_stress, section.section_key)}
            className="rounded-md border border-stone-300 bg-white px-3 py-1.5 text-sm hover:bg-stone-100"
          >
            Dashboard →
          </ExternalLink>
        </div>
      </div>

      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      {stalePatchCardIds.length ? (
        <p className="text-sm text-red-800">
          Saved patch(es) for {stalePatchCardIds.join(', ')} were discarded because the raw card file changed
          after the patch was saved. Cards show current file content; save again to write a fresh patch.
        </p>
      ) : null}
      {message ? <p className="text-sm text-emerald-700">{message}</p> : null}
      {loadingCards ? <p className="text-sm text-stone-500">Loading evidence cards…</p> : null}

      <div className="flex items-stretch gap-2">
        <div className="min-w-0 flex-1">
          <ConfusionMatrix matrixColumns={matrixColumns} evalResult={evalResult} />
        </div>
        {variablesCollapsed ? (
          <button
            type="button"
            onClick={() => setVariablesCollapsed(false)}
            className="flex w-8 shrink-0 flex-col items-center justify-center rounded-lg border border-stone-200 bg-white px-1 text-[10px] font-medium text-stone-600 hover:bg-stone-50"
            title="Show variable table"
            aria-label="Show variable table"
          >
            <span className="[writing-mode:vertical-rl] rotate-180">Variables</span>
          </button>
        ) : (
          <div className="flex w-full max-w-[48%] shrink-0 flex-col gap-1 lg:max-w-[50%]">
            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => setVariablesCollapsed(true)}
                className="rounded border border-stone-200 bg-white px-2 py-0.5 text-[11px] text-stone-600 hover:bg-stone-50"
                title="Collapse variable table"
              >
                Hide variables →
              </button>
            </div>
            <VariableTable evalResult={evalResult} instances={section.instances} />
          </div>
        )}
      </div>

      <details className="rounded-lg border border-stone-200 bg-white">
        <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-stone-700 hover:bg-stone-50">
          Diagnostic signals
        </summary>
        <div className="border-t border-stone-200 p-3">
          <SignalGrid
            section={section}
            cardEdits={cardEdits}
            evalResult={evalResult}
            changedFields={savedChangedFields}
            followUpChoices={followUpChoices}
            onFollowUpChoiceChange={onFollowUpChoiceChange}
            onEditChange={onEditChange}
          />
        </div>
      </details>
    </section>
  )
}
