/** Vite `base` (e.g. `/` or `/core-insights/`). */
export const APP_BASE = import.meta.env.BASE_URL

/** BrowserRouter basename without trailing slash. */
export function routerBasename(): string | undefined {
  const trimmed = APP_BASE.replace(/\/$/, '')
  return trimmed || undefined
}

/** Prefix an app-root path (`/api/...`, `/feedback`) with the Vite base. */
export function appUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path
  const normalized = path.startsWith('/') ? path : `/${path}`
  const base = APP_BASE.endsWith('/') ? APP_BASE.slice(0, -1) : APP_BASE
  if (!base) return normalized
  return `${base}${normalized}`
}
