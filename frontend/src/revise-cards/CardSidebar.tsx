import type { ReviewCardSummary } from './types'
import { severityClasses } from './utils'

type CardSidebarProps = {
  cards: ReviewCardSummary[]
  selectedCardId: string | null
  onSelect: (cardId: string) => void
}

export function CardSidebar({ cards, selectedCardId, onSelect }: CardSidebarProps) {
  const finalizedCount = cards.filter((card) => card.finalized).length

  return (
    <aside className="flex h-full w-96 shrink-0 flex-col border-r border-stone-300 bg-stone-100/80">
      <div className="border-b border-stone-300 px-4 py-3">
        <h2 className="text-sm font-semibold text-stone-800">Cards</h2>
        <p className="mt-1 text-xs text-stone-600">
          {finalizedCount} / {cards.length} finalized
        </p>
      </div>
      <div className="flex-1 overflow-y-auto">
        {cards.map((card) => {
          const styles = severityClasses('', card.overall_score)
          const active = card.card_id === selectedCardId
          return (
            <button
              key={card.card_id}
              type="button"
              onClick={() => onSelect(card.card_id)}
              title={card.card_id}
              className={`block w-full border-b border-stone-200 px-4 py-3 text-left transition ${
                active ? 'bg-white shadow-inner' : 'hover:bg-white/70'
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <span className="min-w-0 break-all font-mono text-[11px] leading-snug text-stone-900">
                  {card.card_id}
                </span>
                <span
                  className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase ${styles.badge}`}
                >
                  {card.overall_score}
                </span>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-stone-600">
                <span>{card.finding_count} issues</span>
                {card.finalized && (
                  <span className="font-medium text-emerald-700">Finalized</span>
                )}
                {(card.pending_count ?? 0) > 0 && (
                  <span className="font-medium text-amber-800">{card.pending_count} pending</span>
                )}
                {(card.not_handled_count ?? 0) > 0 && (
                  <span className="font-medium text-amber-800">
                    {card.not_handled_count} not handled
                  </span>
                )}
                {!card.finalized
                  && (card.pending_count ?? 0) === 0
                  && (card.not_handled_count ?? 0) === 0 && (
                  <span className="text-stone-500">ready to finalize</span>
                )}
              </div>
            </button>
          )
        })}
      </div>
    </aside>
  )
}
