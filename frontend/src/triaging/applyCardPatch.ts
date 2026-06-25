import type { EvidenceCard } from '../api/triage'

/** Merge a revise-cards-style partial patch into a card for triaging display. */
export function applyCardPatch(card: EvidenceCard, patch: Record<string, unknown>): EvidenceCard {
  const next = structuredClone(card) as EvidenceCard & Record<string, unknown>
  if (typeof patch.overall_reasoning_note === 'string') {
    next.overall_reasoning_note = patch.overall_reasoning_note
  }
  if (patch.confirmation_policy && typeof patch.confirmation_policy === 'object') {
    next.confirmation_policy = structuredClone(patch.confirmation_policy) as Record<string, unknown>
  }
  if (Array.isArray(patch.diagnostic_signals) && Array.isArray(next.diagnostic_signals)) {
    const signals = [...next.diagnostic_signals]
    for (const partial of patch.diagnostic_signals) {
      if (!partial || typeof partial !== 'object') continue
      const signalId = String((partial as { signal_id?: string }).signal_id || '')
      const index = signals.findIndex((item) => item.signal_id === signalId)
      if (index < 0) continue
      const current = signals[index]
      const merged = { ...current, ...partial } as typeof current
      if (partial.condition && typeof partial.condition === 'object') {
        merged.condition = {
          ...(current.condition || {}),
          ...(partial.condition as Record<string, unknown>),
        }
      }
      signals[index] = merged
    }
    next.diagnostic_signals = signals
  }
  return next
}
