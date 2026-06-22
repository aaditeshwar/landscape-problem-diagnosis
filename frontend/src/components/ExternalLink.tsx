import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

type Props = {
  to: string
  children: ReactNode
  className?: string
}

/** Internal route or absolute URL — always opens in a new tab. */
export function ExternalLink({ to, children, className }: Props) {
  const isExternal = /^https?:\/\//i.test(to)
  if (isExternal) {
    return (
      <a href={to} target="_blank" rel="noopener noreferrer" className={className}>
        {children}
      </a>
    )
  }
  return (
    <Link to={to} target="_blank" rel="noopener noreferrer" className={className}>
      {children}
    </Link>
  )
}
