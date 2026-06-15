import type { TehsilRef } from '../types'

export function tehsilKey(ref: TehsilRef): string {
  return `${ref.state}__${ref.district}__${ref.tehsil}`
}

export function normalizeTehsils(mws: {
  tehsils?: TehsilRef[]
  state?: string
  district?: string
  tehsil?: string
} | null): TehsilRef[] {
  if (!mws) return []
  if (mws.tehsils?.length) return mws.tehsils
  if (mws.state && mws.district && mws.tehsil) {
    return [{ state: mws.state, district: mws.district, tehsil: mws.tehsil }]
  }
  return []
}

export function formatMwsTehsilLabel(
  mws: {
    tehsils?: TehsilRef[]
    state?: string
    district?: string
    tehsil?: string
  } | null,
  activeRef?: TehsilRef | null,
): string {
  const refs = normalizeTehsils(mws)
  if (!refs.length) return '—'
  const active =
    activeRef ??
    (mws?.state && mws?.district && mws?.tehsil
      ? { state: mws.state, district: mws.district, tehsil: mws.tehsil }
      : refs[0])
  const label = `${active.tehsil}, ${active.district}, ${active.state}`
  if (refs.length === 1) return label
  const others = refs.filter((ref) => tehsilKey(ref) !== tehsilKey(active)).map((ref) => ref.tehsil)
  if (!others.length) return label
  return `${label} (also in ${others.join(', ')})`
}
