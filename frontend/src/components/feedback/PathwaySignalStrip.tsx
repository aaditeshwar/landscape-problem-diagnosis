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

function directionBorder(direction?: string): string {
  if (direction === 'confirms') return 'border-emerald-400'
  if (direction === 'amplifies') return 'border-sky-400'
  if (direction === 'rules_out') return 'border-rose-400'
  return 'border-stone-200'
}

function resultCell(chip: PathwaySignalChip): { label: string; className: string } {
  if (!chip.active) {
    return { label: '—', className: 'bg-stone-100 text-stone-400' }
  }
  if (chip.result === true) {
    return { label: 'T', className: 'bg-emerald-100 text-emerald-800' }
  }
  if (chip.result === false) {
    return { label: 'F', className: 'bg-stone-200 text-stone-700' }
  }
  return { label: '?', className: 'bg-amber-100 text-amber-800' }
}

function chipTooltip(chip: PathwaySignalChip): string {
  if (chip.evalSignal) {
    return formatSignalTooltip(chip.evalSignal)
  }
  const lines = [
    chip.signal_id,
    `Active: ${chip.active ? 'yes' : 'no'}`,
    `Direction: ${chip.direction ?? '—'}`,
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
      <div className="inline-flex flex-wrap gap-1">
        {chips.map((chip) => {
          const cell = resultCell(chip)
          const tooltip = chipTooltip(chip)
          return (
            <div key={chip.signal_id} className="group relative flex flex-col items-center">
              <span className="mb-0.5 font-mono text-[8px] leading-none text-stone-400">
                {chip.signal_id.replace(/^sig_/, '')}
              </span>
              <div
                className={`flex h-5 w-5 items-center justify-center rounded border text-[10px] font-bold ${directionBorder(chip.direction)} ${cell.className}`}
              >
                {cell.label}
              </div>
              <span
                role="tooltip"
                className="pointer-events-none absolute left-0 top-full z-30 mt-1 hidden w-max max-w-[min(18rem,calc(100vw-2rem))] rounded-md border border-stone-700 bg-stone-900 px-2.5 py-2 text-left text-xs leading-relaxed break-words whitespace-pre-wrap text-stone-100 shadow-lg group-hover:block"
              >
                {tooltip}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
