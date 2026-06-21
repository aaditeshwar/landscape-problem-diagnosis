export type SignalSummary = {
  signal_id: string
  active?: boolean
  severity?: string
  direction?: string
  expression?: string
  qualitative_description?: string
  explanation?: string
  variables?: string[]
}

export function indexSignals(rawCard: Record<string, unknown> | null | undefined): SignalSummary[] {
  const signals = rawCard?.diagnostic_signals
  if (!Array.isArray(signals)) return []
  return signals
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'))
    .map((signal) => {
      const condition = (signal.condition as Record<string, unknown> | undefined) || {}
      const variables = Array.isArray(signal.variables)
        ? signal.variables.filter((v): v is string => typeof v === 'string')
        : []
      return {
        signal_id: String(signal.signal_id || ''),
        active: signal.active !== false,
        severity: typeof signal.severity === 'string' ? signal.severity : undefined,
        direction: typeof signal.direction === 'string' ? signal.direction : undefined,
        explanation: typeof signal.explanation === 'string' ? signal.explanation : undefined,
        expression: typeof condition.expression === 'string' ? condition.expression : undefined,
        qualitative_description:
          typeof condition.qualitative_description === 'string'
            ? condition.qualitative_description
            : undefined,
        variables,
      }
    })
    .filter((signal) => signal.signal_id)
}

export function signalTooltipText(signal: SignalSummary): string {
  const lines = [
    signal.severity ? `Severity: ${signal.severity}` : null,
    signal.direction ? `Direction: ${signal.direction}` : null,
    signal.variables?.length ? `Variables: ${signal.variables.join(', ')}` : null,
    signal.expression ? `Expression: ${signal.expression}` : null,
    signal.qualitative_description ? `Description: ${signal.qualitative_description}` : null,
  ].filter(Boolean)
  return lines.join('\n')
}

export function splitSignalReferences(text: string): Array<{ kind: 'text' | 'signal'; value: string }> {
  const parts = text.split(/(\bsig_\d+\b)/g)
  return parts
    .filter((part) => part.length > 0)
    .map((part) => (/\bsig_\d+\b/.test(part) ? { kind: 'signal' as const, value: part } : { kind: 'text' as const, value: part }))
}
