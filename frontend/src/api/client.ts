import type {
  DiagnosisResponse,
  FeatureCollection,
  IngestedTehsil,
  LocateResult,
  MwsDocument,
  MwsFeatureCollection,
  TehsilFeatureCollection,
  TehsilRef,
} from '../types'

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    let detail = await res.text()
    try {
      const parsed = JSON.parse(detail) as { detail?: string | Array<{ msg?: string }> }
      if (typeof parsed.detail === 'string') detail = parsed.detail
      else if (Array.isArray(parsed.detail)) detail = parsed.detail.map((d) => d.msg).filter(Boolean).join('; ')
    } catch {
      /* keep raw text */
    }
    throw new Error(detail || `${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

export function fetchTehsils(): Promise<TehsilFeatureCollection> {
  return api('/api/map/tehsils')
}

export function fetchMwsBoundaries(ref: TehsilRef): Promise<MwsFeatureCollection> {
  const q = new URLSearchParams({ state: ref.state, district: ref.district, tehsil: ref.tehsil })
  return api(`/api/map/mws?${q}`)
}

export function fetchVillageBoundaries(ref: TehsilRef): Promise<FeatureCollection> {
  const q = new URLSearchParams({ state: ref.state, district: ref.district, tehsil: ref.tehsil })
  return api(`/api/map/villages?${q}`)
}

export function fetchMws(uid: string): Promise<MwsDocument> {
  return api(`/api/mws/${encodeURIComponent(uid)}`)
}

export function fetchIngestedTehsils(): Promise<{ tehsils: IngestedTehsil[]; count: number }> {
  return api('/api/ingested-tehsils')
}

export function locatePoint(lat: number, lon: number): Promise<LocateResult> {
  return api('/api/locate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lat, lon }),
  })
}

export function runDiagnosisQuery(
  uid: string,
  problemDescription: string,
  sessionId?: string | null,
): Promise<DiagnosisResponse> {
  return api('/api/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      uid,
      problem_description: problemDescription,
      session_id: sessionId ?? null,
    }),
  })
}

export function submitDiagnosisAnswer(
  sessionId: string,
  variable: string,
  answer: string,
): Promise<DiagnosisResponse> {
  return api('/api/answer', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, variable, answer }),
  })
}
