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
import { apiFetch as api } from './http'

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
  tehsilRef?: TehsilRef | null,
  wantLlmOpinion = false,
): Promise<DiagnosisResponse> {
  return api('/api/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      uid,
      problem_description: problemDescription,
      session_id: sessionId ?? null,
      state: tehsilRef?.state ?? null,
      district: tehsilRef?.district ?? null,
      tehsil: tehsilRef?.tehsil ?? null,
      want_llm_opinion: wantLlmOpinion,
    }),
  })
}

export function submitDiagnosisAnswer(
  sessionId: string,
  variable: string,
  answer: string,
  wantLlmOpinion?: boolean,
  choiceId?: string | null,
): Promise<DiagnosisResponse> {
  return api('/api/answer', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      variable,
      answer: choiceId ? '' : answer,
      choice_id: choiceId ?? null,
      want_llm_opinion: wantLlmOpinion ?? null,
    }),
  })
}
