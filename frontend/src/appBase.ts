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

  let pathPart = path
  let hash = ''
  const hashIdx = path.indexOf('#')
  if (hashIdx >= 0) {
    pathPart = path.slice(0, hashIdx)
    hash = path.slice(hashIdx)
  }

  const normalized = pathPart.startsWith('/') ? pathPart : `/${pathPart}`
  const base = APP_BASE.endsWith('/') ? APP_BASE.slice(0, -1) : APP_BASE
  if (!base) return `${normalized}${hash}`
  return `${base}${normalized}${hash}`
}

/**
 * Router-relative path for `<Link to={...}>` / `navigate()` (basename applied by React Router).
 * Same as passing a root-absolute path when `base` is `/`.
 */
export function appPath(path: string): string {
  if (/^https?:\/\//i.test(path)) {
    try {
      const url = new URL(path)
      return `${url.pathname}${url.search}${url.hash}`
    } catch {
      return path
    }
  }
  return path.startsWith('/') ? path : `/${path}`
}

/** Absolute href for raw `<a href>` (includes Vite base). */
export function appHref(path: string): string {
  return appUrl(appPath(path))
}
