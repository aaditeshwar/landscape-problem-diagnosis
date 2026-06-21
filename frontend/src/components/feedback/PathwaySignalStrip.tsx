import { useMemo } from 'react'
import type {
  CardDiagnosticSignal,
  PathwaySignalSummary,
  RetrievedEvidenceCard,
  SignalEvaluation,
} from '../../types'
import { formatSignalTooltip } from '../../utils/signalLookup'

export interface PathwaySignalChip {
  signal_id: string
  active: boolean
  direction?: string
  result?: boolean | null
  evalSignal?: PathwaySignalSummary
}

function sigSortKey(signalId: string): number {
  const match = signalId.match(/(\d+)/)
  return match ? Number.parseInt(match[1], 10) : 0
}

export function mergePathwaySignals(
  card: RetrievedEvidenceCard | undefined,
  pathwayId: string,
  signalEvaluation?: SignalEvaluation | null,
): PathwaySignalChip[] {
  const evalPathway = signalEvaluation?.pathways?.find((item) => item.pathway_id === pathwayId)
  const evalMap = new Map(
    (evalPathway?.signals ?? [])
      .filter((signal) => signal.signal_id)
      .map((signal) => [signal.signal_id as string, signal]),
  )

  const cardSignals: CardDiagnosticSignal[] = card?.diagnostic_signals ?? []
  if (cardSignals.length) {
    return [...cardSignals]
      .sort((a, b) => sigSortKey(a.signal_id) - sigSortKey(b.signal_id))
      .map((def) => {
        const active = def.active !== false
        const evalSignal = evalMap.get(def.signal_id)
        return {
          signal_id: def.signal_id,
          active,
          direction: def.direction ?? evalSignal?.direction,
          result: active ? evalSignal?.result : null,
          evalSignal,
        }
      })
  }

  return [...(evalPathway?.signals ?? [])]
    .filter((signal) => signal.signal_id)
    .sort((a, b) => sigSortKey(a.signal_id!) - sigSortKey(b.signal_id!))
    .map((signal) => ({
      signal_id: signal.signal_id as string,
      active: true,
      direction: signal.direction,
      result: signal.result,
      evalSignal: signal,
    }))
}

function directionLabel(direction?: string): string {
  if (direction === 'confirms') return 'confirm'
  if (direction === 'amplifies') return 'amplify'
  if (direction === 'rules_out') return 'rule out'
  return direction ?? '—'
}

function resultLabel(active: boolean, result?: boolean | null): string {
  if (!active) return '—'
  if (result === true) return 'true'
  if (result === false) return 'false'
  return '?'
}

function chipTooltip(chip: PathwaySignalChip): string {
  if (chip.evalSignal) {
    return formatSignalTooltip(chip.evalSignal)
  }
  const lines = [
    chip.signal_id,
    `Active: ${chip.active ? 'yes' : 'no'}`,
    `Direction: ${directionLabel(chip.direction)}`,
  ]
  if (!chip.active) {
    lines.push('Not evaluated (inactive)')
  }
  return lines.join('\n')
}

interface Props {
  pathwayId: string
  card?: RetrievedEvidenceCard
  signalEvaluation?: SignalEvaluation | null
}

export function PathwaySignalStrip({ pathwayId, card, signalEvaluation }: Props) {
  const chips = useMemo(
    () => mergePathwaySignals(card, pathwayId, signalEvaluation),
    [card, pathwayId, signalEvaluation],
  )

  if (!chips.length) return null

  return (
    <div className="mt-3 border-t border-stone-200/80 pt-3">
      <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-stone-500">
        Signal evaluation
      </div>
      <div className="flex flex-wrap gap-1.5">
        {chips.map((chip) => {
          const result = resultLabel(chip.active, chip.result)
          const resultTone =
            !chip.active
              ? 'text-stone-400'
              : chip.result === true
                ? 'text-emerald-700'
                : chip.result === false
                  ? 'text-stone-600'
                  : 'text-amber-700'

          return (
            <div
              key={chip.signal_id}
              className={`group relative rounded-md border px-2 py-1 text-[10px] leading-tight ${
                chip.active
                  ? 'border-stone-200 bg-white text-stone-800'
                  : 'border-stone-100 bg-stone-50/80 text-stone-500'
              }`}
            >
              <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
                <span className="cursor-help font-mono font-semibold text-amber-900">{chip.signal_id}</span>
                <span className="text-stone-400">·</span>
                <span className={chip.active ? 'text-emerald-700' : 'text-stone-400'}>
                  {chip.active ? 'active' : 'inactive'}
                </span>
                <span className="text-stone-400">·</span>
                <span className="text-stone-600">{directionLabel(chip.direction)}</span>
                <span className="text-stone-400">·</span>
                <span className={`font-medium ${resultTone}`}>{result}</span>
              </div>
              <span
                role="tooltip"
                className="pointer-events-none absolute bottom-full left-0 z-30 mb-1 hidden w-max max-w-xs rounded-md border border-stone-700 bg-stone-900 px-2.5 py-2 text-left text-xs leading-relaxed whitespace-pre-wrap text-stone-100 shadow-lg group-hover:block"
              >
                {chipTooltip(chip)}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
