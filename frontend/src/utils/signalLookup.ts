import type { PathwaySignalSummary, SignalEvaluation } from '../types'

export interface SignalIndex {
  byPathway: Map<string, Map<string, PathwaySignalSummary>>
  byId: Map<string, PathwaySignalSummary[]>
}

export function buildSignalIndex(
  evaluation: SignalEvaluation | null | undefined,
): SignalIndex {
  const byPathway = new Map<string, Map<string, PathwaySignalSummary>>()
  const byId = new Map<string, PathwaySignalSummary[]>()

  for (const pathway of evaluation?.pathways ?? []) {
    const pathwayMap = new Map<string, PathwaySignalSummary>()
    for (const signal of pathway.signals ?? []) {
      if (!signal.signal_id) continue
      const entry: PathwaySignalSummary = {
        ...signal,
        pathway_id: pathway.pathway_id,
      }
      pathwayMap.set(signal.signal_id, entry)
      const existing = byId.get(signal.signal_id) ?? []
      existing.push(entry)
      byId.set(signal.signal_id, existing)
    }
    byPathway.set(pathway.pathway_id, pathwayMap)
  }

  return { byPathway, byId }
}

export function resolveSignal(
  signalId: string,
  pathwayId: string | undefined,
  index: SignalIndex,
): PathwaySignalSummary | null {
  if (pathwayId) {
    const scoped = index.byPathway.get(pathwayId)?.get(signalId)
    if (scoped) return scoped
  }

  const matches = index.byId.get(signalId) ?? []
  if (matches.length === 1) return matches[0]
  if (pathwayId && matches.length > 1) {
    const preferred = matches.find((m) => m.pathway_id === pathwayId)
    if (preferred) return preferred
  }
  return matches[0] ?? null
}

export function formatSignalResult(signal: PathwaySignalSummary): string {
  if (signal.result === true) return 'TRUE'
  if (signal.result === false) return 'FALSE'
  if (signal.result === null) return 'unknown'
  return 'not evaluated'
}

export function formatSignalTooltip(signal: PathwaySignalSummary): string {
  const lines = [
    `${signal.signal_id} (${signal.direction ?? 'unknown direction'})`,
    `Result: ${formatSignalResult(signal)}${signal.status ? ` (${signal.status})` : ''}`,
  ]
  if (signal.expression) {
    lines.push(`Expression: ${signal.expression}`)
  } else if (signal.qualitative_hint) {
    lines.push(`Hint: ${signal.qualitative_hint}`)
  }
  if (signal.variable_values?.length) {
    lines.push(
      'Variables:',
      ...signal.variable_values.map((row) => `  ${row.access} = ${row.formatted}`),
    )
  }
  if (signal.pathway_id) {
    lines.push(`Pathway: ${signal.pathway_id.replace(/_/g, ' ')}`)
  }
  return lines.join('\n')
}
