import { useCallback, useEffect, useState } from 'react'
import {
  dashboardSectionUrl,
  evaluateTriageSection,
  fetchCardMap,
  fetchTriageCard,
  saveTriageDraft,
  type CardMapResponse,
  type EvaluateSectionResult,
  type TriageSection,
} from '../api/triage'
import { ExternalLink } from '../components/ExternalLink'
import { SignalGrid, type CardEditState } from './SignalGrid'
import { ConfusionMatrix, VariableTable } from './TriageMatrixPanels'

type Props = {
  section: TriageSection
}

async function loadCardEditsForSection(
  section: TriageSection,
  cardMaps: Record<string, CardMapResponse>,
): Promise<Record<string, CardEditState>> {
  const edits: Record<string, CardEditState> = {}
  const builtPathways = [...section.predicted_pathways].sort()
  const uniqueMws = [...new Set(section.instances.map((inst) => inst.mws_id))]

  for (const mwsId of uniqueMws) {
    const map = cardMaps[mwsId]
    if (!map) continue
    for (const pathway of builtPathways) {
      const cardId = map.cards_by_pathway[pathway]?.card_id
      if (!cardId || edits[cardId]) continue
      const { card } = await fetchTriageCard(cardId)
      edits[cardId] = {
        card_id: cardId,
        diagnostic_signals: structuredClone(card.diagnostic_signals || []),
        confirmation_policy: structuredClone(card.confirmation_policy || {}),
      }
    }
  }
  return edits
}

export function TriageSectionPanel({ section }: Props) {
  const [cardEdits, setCardEdits] = useState<Record<string, CardEditState>>({})
  const [evalResult, setEvalResult] = useState<EvaluateSectionResult | null>(null)
  const [loadingCards, setLoadingCards] = useState(true)
  const [playing, setPlaying] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const matrixColumns = section.matrix_columns ?? section.predicted_pathways

  useEffect(() => {
    let cancelled = false
    setLoadingCards(true)
    setError(null)
    setEvalResult(null)

    const uniqueMws = [...new Set(section.instances.map((inst) => inst.mws_id))]
    Promise.all(uniqueMws.map((mwsId) => fetchCardMap(mwsId).then((map) => [mwsId, map] as const)))
      .then(async (entries) => {
        if (cancelled) return
        const maps = Object.fromEntries(entries)
        const edits = await loadCardEditsForSection(section, maps)
        if (!cancelled) setCardEdits(edits)
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message || 'Failed to load cards')
      })
      .finally(() => {
        if (!cancelled) setLoadingCards(false)
      })

    return () => {
      cancelled = true
    }
  }, [section])

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
        })),
      })
      setEvalResult(result)
      setMessage('Evaluation complete.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Play failed')
    } finally {
      setPlaying(false)
    }
  }

  const handleSaveDrafts = async () => {
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const cardIds = Object.keys(cardEdits)
      await Promise.all(
        cardIds.map((cardId) =>
          saveTriageDraft(cardId, {
            diagnostic_signals: cardEdits[cardId].diagnostic_signals,
            confirmation_policy: cardEdits[cardId].confirmation_policy,
            section: {
              production_system: section.production_system,
              observed_stress: section.observed_stress,
            },
          }),
        ),
      )
      setMessage(`Saved ${cardIds.length} draft(s).`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section id={section.section_key} className="space-y-4 rounded-xl border border-stone-200 bg-stone-50/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-stone-900">
            {section.production_system} · {section.observed_stress.replace(/_/g, ' ')}
          </h2>
          <p className="text-xs text-stone-500">{section.instances.length} case-study instances</p>
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
            onClick={handleSaveDrafts}
            disabled={saving || loadingCards || !Object.keys(cardEdits).length}
            className="rounded-md border border-stone-300 bg-white px-3 py-1.5 text-sm hover:bg-stone-100 disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Save drafts'}
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
      {message ? <p className="text-sm text-emerald-700">{message}</p> : null}
      {loadingCards ? <p className="text-sm text-stone-500">Loading evidence cards…</p> : null}

      <div className="grid gap-4 lg:grid-cols-5">
        <div className="lg:col-span-2">
          <ConfusionMatrix
            matrixColumns={matrixColumns}
            evalResult={evalResult}
          />
        </div>
        <div className="lg:col-span-3">
          <VariableTable evalResult={evalResult} instances={section.instances} />
        </div>
      </div>

      <SignalGrid
        section={section}
        cardEdits={cardEdits}
        evalResult={evalResult}
        onEditChange={onEditChange}
      />
    </section>
  )
}
