import type { SignalSummary } from './signalUtils'
import { splitSignalReferences, signalTooltipText } from './signalUtils'

type SignalTextProps = {
  text: string
  signalsById: Record<string, SignalSummary>
  className?: string
  as?: 'p' | 'span'
}

export function SignalText({ text, signalsById, className = '', as = 'span' }: SignalTextProps) {
  const Tag = as
  const parts = splitSignalReferences(text)
  return (
    <Tag className={className}>
      {parts.map((part, index) => {
        if (part.kind === 'signal') {
          const signal = signalsById[part.value]
          const title = signal ? signalTooltipText(signal) : part.value
          return (
            <abbr
              key={`${part.value}-${index}`}
              title={title}
              className="cursor-help border-b border-dotted border-stone-500 font-mono text-[0.95em] text-stone-900 no-underline"
            >
              {part.value}
            </abbr>
          )
        }
        return <span key={index}>{part.value}</span>
      })}
    </Tag>
  )
}

export function SignalLegend({ signals }: { signals: SignalSummary[] }) {
  if (!signals.length) return null
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {signals.map((signal) => (
        <abbr
          key={signal.signal_id}
          title={signalTooltipText(signal)}
          className="cursor-help rounded border border-stone-300 bg-stone-50 px-2 py-0.5 font-mono text-[11px] text-stone-800 no-underline"
        >
          {signal.signal_id}
          {signal.direction ? ` · ${signal.direction}` : ''}
        </abbr>
      ))}
    </div>
  )
}
