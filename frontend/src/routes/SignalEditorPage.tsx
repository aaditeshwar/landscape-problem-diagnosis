import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  clusterSuffixFromCardId,
  fetchCardsByCluster,
  fetchClusterPalette,
  fetchEvidenceCard,
  fetchPublicConfig,
  type ClusterPaletteEntry,
  type EvidenceCardDocument,
  type EvidenceCardSummary,
  type SignalEditorDraft,
} from '../api/signals'
import { ClusterMap } from '../components/signals/ClusterMap'
import { ContextClusterInfo } from '../components/signals/ContextClusterInfo'
import { SignalEditorPanel } from '../components/signals/SignalEditorPanel'
import { draftFromCard } from '../utils/signalEditorDraft'

function pickInitialCard(
  cards: EvidenceCardSummary[],
  cardId: string | null,
  pathway: string | null,
): string | null {
  if (cardId && cards.some((card) => card.card_id === cardId)) return cardId
  if (pathway) {
    const match = cards.find(
      (card) => card.causal_pathway === pathway || card.pathway_id === pathway || card.card_id.includes(pathway),
    )
    if (match) return match.card_id
  }
  return cards[0]?.card_id ?? null
}

export function SignalEditorPage() {
  const [params] = useSearchParams()
  const initialCluster = params.get('cluster')
  const initialPathway = params.get('pathway')
  const initialCardId = params.get('card_id')
  const snapshotId = params.get('snapshot_id')

  const [cogUrl, setCogUrl] = useState<string | null>(null)
  const [palette, setPalette] = useState<ClusterPaletteEntry[]>([])
  const [selectedSuffix, setSelectedSuffix] = useState<string | null>(initialCluster)
  const [cards, setCards] = useState<EvidenceCardSummary[]>([])
  const [selectedCardId, setSelectedCardId] = useState<string | null>(initialCardId)
  const [card, setCard] = useState<EvidenceCardDocument | null>(null)
  const [draft, setDraft] = useState<SignalEditorDraft | null>(null)
  const [cardsLoading, setCardsLoading] = useState(false)
  const [cardLoading, setCardLoading] = useState(false)
  const [cardsError, setCardsError] = useState<string | null>(null)
  const [cardError, setCardError] = useState<string | null>(null)
  const [bootError, setBootError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([fetchPublicConfig(), fetchClusterPalette()])
      .then(([config, paletteResponse]) => {
        if (cancelled) return
        setCogUrl(config.cluster_cog_url ?? null)
        setPalette(paletteResponse.palette)
        if (!initialCluster && initialCardId) {
          setSelectedSuffix(clusterSuffixFromCardId(initialCardId))
        }
      })
      .catch((error: Error) => {
        if (!cancelled) setBootError(error.message || 'Failed to load signal editor config')
      })
    return () => {
      cancelled = true
    }
  }, [initialCardId, initialCluster])

  useEffect(() => {
    if (!selectedSuffix) {
      setCards([])
      setSelectedCardId(null)
      setCard(null)
      setDraft(null)
      return
    }
    let cancelled = false
    setCardsLoading(true)
    setCardsError(null)
    fetchCardsByCluster(selectedSuffix)
      .then((response) => {
        if (cancelled) return
        setCards(response.cards)
        setSelectedCardId((current) => pickInitialCard(response.cards, current ?? initialCardId, initialPathway))
      })
      .catch((error: Error) => {
        if (!cancelled) setCardsError(error.message || 'Failed to load cards for cluster')
      })
      .finally(() => {
        if (!cancelled) setCardsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [initialCardId, initialPathway, selectedSuffix])

  useEffect(() => {
    if (!selectedCardId) {
      setCard(null)
      setDraft(null)
      return
    }
    let cancelled = false
    setCardLoading(true)
    setCardError(null)
    fetchEvidenceCard(selectedCardId)
      .then((doc) => {
        if (cancelled) return
        setCard(doc)
        setDraft(draftFromCard(doc))
      })
      .catch((error: Error) => {
        if (!cancelled) setCardError(error.message || 'Failed to load evidence card')
      })
      .finally(() => {
        if (!cancelled) setCardLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [selectedCardId])

  const selectedCluster = useMemo(() => {
    const entry = palette.find((item) => item.suffix === selectedSuffix)
    return entry?.cluster ?? null
  }, [palette, selectedSuffix])

  const showDeepLinkFields = Boolean(snapshotId || initialCardId || initialPathway)

  return (
    <div className="min-h-full bg-[#faf7f2] p-6 text-stone-800">
      <header className="mb-6 border-b border-stone-300 pb-4">
        <h1 className="text-xl font-semibold">Evidence signal editor (editing disabled)</h1>
        <p className="mt-1 text-sm text-stone-600">
          Read-only view of evidence-card signals, confirmation policy, and follow-up effects for review.
        </p>
      </header>

      {bootError ? <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{bootError}</p> : null}

      <div className="mb-4 grid gap-4 xl:grid-cols-[2fr_3fr] xl:items-start">
        <div className="rounded-lg border border-stone-200 bg-white px-4 py-3 text-sm shadow-sm">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-stone-500">Deep link context</h2>
          {showDeepLinkFields ? (
            <dl className="mt-2 space-y-1">
              {selectedSuffix ? (
                <div className="flex gap-2">
                  <dt className="w-24 shrink-0 text-stone-500">Cluster</dt>
                  <dd className="font-medium">{selectedSuffix}</dd>
                </div>
              ) : null}
              {initialPathway ? (
                <div className="flex gap-2">
                  <dt className="w-24 shrink-0 text-stone-500">Pathway</dt>
                  <dd className="font-medium">{initialPathway}</dd>
                </div>
              ) : null}
              {selectedCardId ? (
                <div className="flex gap-2">
                  <dt className="w-24 shrink-0 text-stone-500">Card</dt>
                  <dd className="break-all font-medium">{selectedCardId}</dd>
                </div>
              ) : null}
              {snapshotId ? (
                <div className="flex gap-2">
                  <dt className="w-24 shrink-0 text-stone-500">Snapshot</dt>
                  <dd className="break-all font-medium">{snapshotId}</dd>
                </div>
              ) : null}
            </dl>
          ) : (
            <p className="mt-2 text-stone-500">
              {selectedSuffix
                ? `Map-selected cluster ${selectedSuffix}. Open from diagnosis feedback for snapshot and pathway deep links.`
                : 'Select a context cluster on the map below.'}
            </p>
          )}
        </div>
        <ContextClusterInfo cluster={selectedCluster} suffix={selectedSuffix} />
      </div>

      <div className="grid gap-4 xl:grid-cols-[2fr_3fr] xl:items-start">
        <div className="self-start">
          <ClusterMap
            cogUrl={cogUrl}
            palette={palette}
            selectedSuffix={selectedSuffix}
            onSelectSuffix={setSelectedSuffix}
          />
        </div>
        <div className="space-y-4">
          {cardsLoading ? <p className="text-sm text-stone-500">Loading cards for cluster {selectedSuffix}…</p> : null}
          {cardsError ? <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{cardsError}</p> : null}
          <SignalEditorPanel
            cards={cards}
            selectedCardId={selectedCardId}
            card={card}
            draft={draft}
            loading={cardLoading}
            error={cardError}
            onSelectCardId={setSelectedCardId}
          />
        </div>
      </div>
    </div>
  )
}
