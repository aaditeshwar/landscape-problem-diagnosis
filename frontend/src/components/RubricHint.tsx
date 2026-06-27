import type { ReactNode } from 'react'
import { RUBRIC_DIMENSIONS, RUBRIC_ERROR_FLAGS, rubricTooltip } from '../eval/evalRubricHelp'

export function RubricHint({
  id,
  children,
  className = '',
}: {
  id: string
  children?: ReactNode
  className?: string
}) {
  const entry = RUBRIC_DIMENSIONS[id] ?? RUBRIC_ERROR_FLAGS[id]
  const label = children ?? id
  if (!entry) {
    return <span className={className}>{label}</span>
  }
  return (
    <span
      className={`cursor-help border-b border-dotted border-stone-400 ${className}`}
      title={rubricTooltip(entry)}
    >
      {label}
    </span>
  )
}
