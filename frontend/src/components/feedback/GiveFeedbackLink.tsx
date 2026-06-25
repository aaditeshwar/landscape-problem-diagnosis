import { Link } from 'react-router-dom'
import { buildFeedbackPageUrl } from '../../api/feedback'

interface Props {
  snapshotId?: string | null
  focus?: 'pathway' | 'summary' | 'solutions'
  pathwayId?: string
  disabled?: boolean
  className?: string
}

export function GiveFeedbackLink({
  snapshotId,
  focus,
  pathwayId,
  disabled,
  className,
}: Props) {
  if (!snapshotId || disabled) return null
  const to = buildFeedbackPageUrl({ snapshotId, focus, pathwayId })
  return (
    <Link
      to={to}
      target="_blank"
      rel="noopener noreferrer"
      className={
        className ??
        'text-xs font-medium text-amber-800 underline decoration-amber-300 underline-offset-2 hover:text-amber-950'
      }
    >
      See details and give feedback
    </Link>
  )
}
