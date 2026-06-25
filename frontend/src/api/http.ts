import { appUrl } from '../appBase'

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(appUrl(path), init)
  if (!res.ok) {
    let detail = await res.text()
    try {
      const parsed = JSON.parse(detail) as {
        detail?: string | Array<{ msg?: string }>
      }
      if (typeof parsed.detail === 'string') detail = parsed.detail
      else if (Array.isArray(parsed.detail)) {
        detail = parsed.detail.map((d) => d.msg).filter(Boolean).join('; ')
      }
    } catch {
      /* keep raw text */
    }
    throw new Error(detail || `${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}
