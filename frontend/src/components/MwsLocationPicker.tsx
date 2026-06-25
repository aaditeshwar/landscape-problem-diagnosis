import { useEffect, useMemo, useState } from 'react'
import { fetchMwsBoundaries, fetchTehsils } from '../api/client'
import type { MwsFeatureCollection, TehsilFeatureCollection, TehsilRef } from '../types'

export type MwsLocationSelection = {
  state: string
  district: string
  tehsil: string
  mws_id: string
}

type Props = {
  value: MwsLocationSelection | null
  onChange: (next: MwsLocationSelection | null) => void
}

function tehsilKey(ref: TehsilRef): string {
  return `${ref.state}__${ref.district}__${ref.tehsil}`
}

export function MwsLocationPicker({ value, onChange }: Props) {
  const [tehsils, setTehsils] = useState<TehsilFeatureCollection | null>(null)
  const [mwsBoundaries, setMwsBoundaries] = useState<MwsFeatureCollection | null>(null)
  const [loadingMws, setLoadingMws] = useState(false)

  useEffect(() => {
    fetchTehsils().then(setTehsils).catch(() => setTehsils(null))
  }, [])

  const tehsilRefs = useMemo(() => {
    if (!tehsils?.features?.length) return []
    const seen = new Map<string, TehsilRef>()
    for (const feature of tehsils.features) {
      const props = feature.properties || {}
      const state = String(props.state || '')
      const district = String(props.district || '')
      const tehsil = String(props.tehsil || '')
      if (!state || !district || !tehsil) continue
      seen.set(tehsilKey({ state, district, tehsil }), { state, district, tehsil })
    }
    return [...seen.values()].sort((a, b) =>
      `${a.state}/${a.district}/${a.tehsil}`.localeCompare(`${b.state}/${b.district}/${b.tehsil}`),
    )
  }, [tehsils])

  const states = useMemo(
    () => [...new Set(tehsilRefs.map((ref) => ref.state))].sort(),
    [tehsilRefs],
  )
  const districts = useMemo(() => {
    if (!value?.state) return []
    return [...new Set(tehsilRefs.filter((ref) => ref.state === value.state).map((ref) => ref.district))].sort()
  }, [tehsilRefs, value?.state])
  const tehsilNames = useMemo(() => {
    if (!value?.state || !value?.district) return []
    return tehsilRefs
      .filter((ref) => ref.state === value.state && ref.district === value.district)
      .map((ref) => ref.tehsil)
      .sort()
  }, [tehsilRefs, value?.district, value?.state])

  useEffect(() => {
    if (!value?.state || !value?.district || !value?.tehsil) {
      setMwsBoundaries(null)
      return
    }
    let cancelled = false
    setLoadingMws(true)
    fetchMwsBoundaries({ state: value.state, district: value.district, tehsil: value.tehsil })
      .then((data) => {
        if (!cancelled) setMwsBoundaries(data)
      })
      .catch(() => {
        if (!cancelled) setMwsBoundaries(null)
      })
      .finally(() => {
        if (!cancelled) setLoadingMws(false)
      })
    return () => {
      cancelled = true
    }
  }, [value?.district, value?.state, value?.tehsil])

  const mwsIds = useMemo(() => {
    const ids = (mwsBoundaries?.features || [])
      .map((feature) => String(feature.properties?.uid || ''))
      .filter(Boolean)
    return [...new Set(ids)].sort()
  }, [mwsBoundaries])

  return (
    <div className="flex flex-wrap items-end gap-2">
      <label className="flex flex-col gap-0.5 text-xs text-stone-600">
        State
        <select
          className="min-w-[120px] rounded border border-stone-300 bg-white px-2 py-1 text-sm"
          value={value?.state || ''}
          onChange={(event) => {
            const state = event.target.value
            onChange(state ? { state, district: '', tehsil: '', mws_id: '' } : null)
          }}
        >
          <option value="">—</option>
          {states.map((state) => (
            <option key={state} value={state}>
              {state}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-0.5 text-xs text-stone-600">
        District
        <select
          className="min-w-[120px] rounded border border-stone-300 bg-white px-2 py-1 text-sm"
          value={value?.district || ''}
          disabled={!value?.state}
          onChange={(event) => {
            if (!value?.state) return
            onChange({ ...value, district: event.target.value, tehsil: '', mws_id: '' })
          }}
        >
          <option value="">—</option>
          {districts.map((district) => (
            <option key={district} value={district}>
              {district}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-0.5 text-xs text-stone-600">
        Tehsil
        <select
          className="min-w-[120px] rounded border border-stone-300 bg-white px-2 py-1 text-sm"
          value={value?.tehsil || ''}
          disabled={!value?.district}
          onChange={(event) => {
            if (!value?.state || !value?.district) return
            onChange({ ...value, tehsil: event.target.value, mws_id: '' })
          }}
        >
          <option value="">—</option>
          {tehsilNames.map((tehsil) => (
            <option key={tehsil} value={tehsil}>
              {tehsil}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-0.5 text-xs text-stone-600">
        MWS
        <select
          className="min-w-[120px] rounded border border-stone-300 bg-white px-2 py-1 font-mono text-sm"
          value={value?.mws_id || ''}
          disabled={!value?.tehsil || loadingMws}
          onChange={(event) => {
            if (!value) return
            onChange({ ...value, mws_id: event.target.value })
          }}
        >
          <option value="">{loadingMws ? 'Loading…' : '—'}</option>
          {mwsIds.map((mwsId) => (
            <option key={mwsId} value={mwsId}>
              {mwsId}
            </option>
          ))}
        </select>
      </label>
    </div>
  )
}
