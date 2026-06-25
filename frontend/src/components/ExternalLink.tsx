import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { appPath } from '../appBase'

type Props = {
  to: string
  children: ReactNode
  className?: string
}

function internalRouterPath(to: string): string | null {
  if (/^https?:\/\//i.test(to)) {
    try {
      const url = new URL(to, window.location.origin)
      if (url.origin !== window.location.origin) return null
      return appPath(`${url.pathname}${url.search}${url.hash}`)
    } catch {
      return null
    }
  }
  return appPath(to)
}

/** Internal route or absolute URL — always opens in a new tab. */
export function ExternalLink({ to, children, className }: Props) {
  const internalTo = internalRouterPath(to)
  if (internalTo) {
    return (
      <Link to={internalTo} target="_blank" rel="noopener noreferrer" className={className}>
        {children}
      </Link>
    )
  }
  return (
    <a href={to} target="_blank" rel="noopener noreferrer" className={className}>
      {children}
    </a>
  )
}
