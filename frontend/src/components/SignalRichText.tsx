import { useMemo } from 'react'
import type { SignalEvaluation } from '../types'
import {
  buildSignalIndex,
  formatSignalTooltip,
  resolveSignal,
} from '../utils/signalLookup'

const SIGNAL_PATTERN = /\bsig_\d+\b/gi

interface SignalRichTextProps {
  text: string
  pathwayId?: string
  signalEvaluation?: SignalEvaluation | null
  className?: string
}

export function SignalRichText({
  text,
  pathwayId,
  signalEvaluation,
  className,
}: SignalRichTextProps) {
  const index = useMemo(
    () => buildSignalIndex(signalEvaluation),
    [signalEvaluation],
  )

  const parts = useMemo(() => {
    if (!text) return [{ kind: 'text' as const, value: '' }]

    const segments: Array<
      { kind: 'text'; value: string } | { kind: 'signal'; value: string }
    > = []
    let lastIndex = 0
    const matches = [...text.matchAll(SIGNAL_PATTERN)]

    for (const match of matches) {
      const start = match.index ?? 0
      if (start > lastIndex) {
        segments.push({ kind: 'text', value: text.slice(lastIndex, start) })
      }
      segments.push({ kind: 'signal', value: match[0] })
      lastIndex = start + match[0].length
    }

    if (lastIndex < text.length) {
      segments.push({ kind: 'text', value: text.slice(lastIndex) })
    }

    return segments.length ? segments : [{ kind: 'text' as const, value: text }]
  }, [text])

  return (
    <span className={className}>
      {parts.map((part, idx) => {
        if (part.kind === 'text') {
          return <span key={idx}>{part.value}</span>
        }

        const signalId = part.value.toLowerCase()
        const signal = resolveSignal(signalId, pathwayId, index)

        if (!signal) {
          return (
            <span key={idx} className="font-medium text-stone-700">
              {part.value}
            </span>
          )
        }

        const tooltip = formatSignalTooltip(signal)

        return (
          <span key={idx} className="group relative inline-block align-baseline">
            <span
              className="cursor-help border-b border-dotted border-amber-600/60 font-medium text-amber-900"
              aria-label={tooltip}
            >
              {part.value}
            </span>
            <span
              role="tooltip"
              className="pointer-events-none absolute bottom-full left-0 z-30 mb-1 hidden w-max max-w-xs rounded-md border border-stone-700 bg-stone-900 px-2.5 py-2 text-left text-xs leading-relaxed whitespace-pre-wrap text-stone-100 shadow-lg group-hover:block"
            >
              {tooltip}
            </span>
          </span>
        )
      })}
    </span>
  )
}
