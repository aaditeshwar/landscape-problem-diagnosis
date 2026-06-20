import { diffJsonLines, formatJson, type JsonDiffRow } from './jsonDiff'

type JsonDiffViewProps = {
  left: unknown
  right: unknown | null | undefined
  leftLabel?: string
  rightLabel?: string
  className?: string
}

function rowClass(kind: JsonDiffRow['kind'], side: 'left' | 'right'): string {
  if (kind === 'same') return ''
  if (kind === 'remove' && side === 'left') return 'bg-red-100 text-red-950'
  if (kind === 'add' && side === 'right') return 'bg-emerald-100 text-emerald-950'
  if (kind === 'change') {
    return side === 'left' ? 'bg-amber-100 text-amber-950' : 'bg-emerald-100 text-emerald-950'
  }
  return ''
}

function DiffColumn({
  side,
  rows,
  label,
}: {
  side: 'left' | 'right'
  rows: JsonDiffRow[]
  label: string
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-600">{label}</div>
      <pre className="min-h-[12rem] flex-1 overflow-auto rounded-md border border-stone-300 bg-white p-3 text-xs leading-relaxed">
        {rows.map((row, index) => {
          const text = side === 'left' ? row.left : row.right
          if (!text) {
            return <div key={index} className="text-stone-300">&nbsp;</div>
          }
          return (
            <div key={index} className={rowClass(row.kind, side)}>
              {text}
            </div>
          )
        })}
      </pre>
    </div>
  )
}

export function JsonDiffView({
  left,
  right,
  leftLabel = 'Current',
  rightLabel = 'Suggested',
  className = '',
}: JsonDiffViewProps) {
  const leftText = formatJson(left)
  const rightText = right == null ? '—' : formatJson(right)
  const rows = diffJsonLines(leftText, rightText)

  return (
    <div className={`grid gap-4 lg:grid-cols-2 lg:items-stretch ${className}`}>
      <DiffColumn side="left" rows={rows} label={leftLabel} />
      <DiffColumn side="right" rows={rows} label={rightLabel} />
    </div>
  )
}
