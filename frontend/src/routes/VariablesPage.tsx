import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ExternalLink } from '../components/ExternalLink'
import { CommandFooter } from '../components/CommandFooter'
import { MwsLocationPicker, type MwsLocationSelection } from '../components/MwsLocationPicker'
import { VariableValueCell } from '../components/VariableValueCell'
import {
  fetchMwsVariableValues,
  fetchVariableCatalog,
  type MwsVariableValuesPayload,
  type VariableCatalogEntry,
  type VariableCatalogSection,
} from '../api/triage'

function typeLabel(variable: VariableCatalogEntry): string {
  return variable.display_type || variable.shape?.replace(/_/g, ' ') || variable.type || '—'
}

function matchesQuery(variable: VariableCatalogEntry, query: string): boolean {
  if (!query) return true
  const q = query.toLowerCase()
  return (
    variable.name.toLowerCase().includes(q) ||
    (variable.description || '').toLowerCase().includes(q) ||
    (variable.source || '').toLowerCase().includes(q) ||
    variable.signal_usages.some(
      (u) =>
        u.card_id.toLowerCase().includes(q) ||
        u.signal_id.toLowerCase().includes(q) ||
        u.access.toLowerCase().includes(q),
    )
  )
}

function selectionFromParams(params: URLSearchParams): MwsLocationSelection | null {
  const mws_id = params.get('mws') || ''
  const state = params.get('state') || ''
  const district = params.get('district') || ''
  const tehsil = params.get('tehsil') || ''
  if (!mws_id && !state) return null
  return { state, district, tehsil, mws_id }
}

export function VariablesPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [sections, setSections] = useState<VariableCatalogSection[]>([])
  const [variableCount, setVariableCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [location, setLocation] = useState<MwsLocationSelection | null>(() => selectionFromParams(searchParams))
  const [mwsValues, setMwsValues] = useState<MwsVariableValuesPayload | null>(null)
  const [valuesLoading, setValuesLoading] = useState(false)
  const [valuesError, setValuesError] = useState<string | null>(null)

  useEffect(() => {
    fetchVariableCatalog()
      .then((data) => {
        setSections(data.sections)
        setVariableCount(data.variable_count)
      })
      .catch((err: Error) => setError(err.message || 'Failed to load variable catalog'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!location?.mws_id) {
      setMwsValues(null)
      setValuesError(null)
      return
    }
    let cancelled = false
    setValuesLoading(true)
    setValuesError(null)
    fetchMwsVariableValues(location.mws_id)
      .then((data) => {
        if (!cancelled) setMwsValues(data)
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setMwsValues(null)
          setValuesError(err.message || 'Failed to load MWS values')
        }
      })
      .finally(() => {
        if (!cancelled) setValuesLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [location?.mws_id])

  const handleLocationChange = (next: MwsLocationSelection | null) => {
    setLocation(next)
    const params = new URLSearchParams(searchParams)
    if (!next?.mws_id && !next?.state) {
      params.delete('mws')
      params.delete('state')
      params.delete('district')
      params.delete('tehsil')
    } else {
      if (next.state) params.set('state', next.state)
      else params.delete('state')
      if (next.district) params.set('district', next.district)
      else params.delete('district')
      if (next.tehsil) params.set('tehsil', next.tehsil)
      else params.delete('tehsil')
      if (next.mws_id) params.set('mws', next.mws_id)
      else params.delete('mws')
    }
    setSearchParams(params, { replace: true })
  }

  const filteredSections = useMemo(
    () =>
      sections
        .map((section) => ({
          ...section,
          variables: section.variables.filter((v) => matchesQuery(v, search)),
        }))
        .filter((section) => section.variables.length > 0),
    [sections, search],
  )

  const visibleCount = filteredSections.reduce((n, s) => n + s.variables.length, 0)
  const showMwsColumn = Boolean(location?.mws_id)
  const valueColumnLabel = showMwsColumn ? `MWS ${location!.mws_id}` : 'MWS value'

  return (
    <div className="min-h-screen bg-stone-100">
      <header className="border-b border-stone-200 bg-white px-4 py-3">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-stone-900">Variable catalog</h1>
            <p className="text-sm text-stone-500">
              Data dictionary, types, signal-expression references, and per-MWS resolved values
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search variables…"
              className="rounded-md border border-stone-300 px-3 py-1.5 text-sm"
              aria-label="Search variables"
            />
            <ExternalLink to="/dashboard" className="text-sm text-amber-800 hover:underline">
              Dashboard
            </ExternalLink>
            <ExternalLink to="/triaging" className="text-sm text-amber-800 hover:underline">
              Triaging
            </ExternalLink>
          </div>
        </div>
        <div className="mx-auto mt-3 max-w-[1400px]">
          <MwsLocationPicker value={location} onChange={handleLocationChange} />
          {valuesLoading ? <p className="mt-2 text-xs text-stone-500">Loading MWS variable values…</p> : null}
          {valuesError ? <p className="mt-2 text-xs text-red-700">{valuesError}</p> : null}
          {mwsValues ? (
            <p className="mt-2 text-xs text-stone-500">
              Showing values for {mwsValues.mws_id}
              {mwsValues.tehsil ? ` · ${mwsValues.state}/${mwsValues.district}/${mwsValues.tehsil}` : null}
            </p>
          ) : null}
        </div>
      </header>

      <main className="mx-auto max-w-[1400px] space-y-6 px-4 py-6">
        {error ? <p className="text-sm text-red-700">{error}</p> : null}
        {loading ? <p className="text-sm text-stone-500">Loading catalog…</p> : null}
        {!loading ? (
          <p className="text-sm text-stone-600">
            {search ? `${visibleCount} of ${variableCount}` : variableCount} variables in{' '}
            {search ? filteredSections.length : sections.length} categories
          </p>
        ) : null}

        {filteredSections.map((section) => (
          <section key={section.category} id={section.category.replace(/\W+/g, '_')} className="space-y-2">
            <h2 className="border-b border-stone-200 pb-1 text-base font-semibold text-stone-900">
              {section.category}
              <span className="ml-2 text-sm font-normal text-stone-500">({section.variables.length})</span>
            </h2>
            <div className="overflow-auto rounded-lg border border-stone-200 bg-white">
              <table className="min-w-full border-collapse text-[11px]">
                <thead>
                  <tr className="border-b border-stone-200 bg-stone-50 text-left text-stone-600">
                    <th className="whitespace-nowrap px-2 py-1.5 font-medium">Variable</th>
                    <th className="whitespace-nowrap px-2 py-1.5 font-medium">Type</th>
                    <th className="whitespace-nowrap px-2 py-1.5 font-medium">Units</th>
                    <th className="whitespace-nowrap px-2 py-1.5 font-medium">Source</th>
                    <th className="min-w-[180px] px-2 py-1.5 font-medium">Signal usage (≤3)</th>
                    {showMwsColumn ? (
                      <th className="min-w-[160px] px-2 py-1.5 font-medium">{valueColumnLabel}</th>
                    ) : null}
                    <th className="min-w-[280px] px-2 py-1.5 font-medium">Explanation</th>
                  </tr>
                </thead>
                <tbody>
                  {section.variables.map((variable) => (
                    <tr key={variable.name} className="border-b border-stone-100 align-top hover:bg-stone-50/50">
                      <td className="whitespace-nowrap px-2 py-1.5 font-mono font-medium text-stone-900">
                        {variable.name}
                      </td>
                      <td className="whitespace-nowrap px-2 py-1.5 text-stone-700">{typeLabel(variable)}</td>
                      <td className="whitespace-nowrap px-2 py-1.5 text-stone-600">{variable.unit || '—'}</td>
                      <td className="max-w-[200px] px-2 py-1.5 text-stone-600">
                        <span className="line-clamp-2" title={variable.source}>
                          {variable.source || variable.availability || '—'}
                        </span>
                      </td>
                      <td className="px-2 py-1.5 text-stone-600">
                        {variable.signal_usages.length ? (
                          <ul className="space-y-0.5">
                            {variable.signal_usages.slice(0, 3).map((usage) => (
                              <li key={`${usage.card_id}-${usage.signal_id}-${usage.access}`}>
                                <ExternalLink
                                  to={`/revise-cards?card_id=${encodeURIComponent(usage.card_id)}`}
                                  className="text-amber-800 hover:underline"
                                >
                                  {usage.card_id.split('__').slice(-2).join('__')}
                                </ExternalLink>
                                <span className="text-stone-500">
                                  {' '}
                                  · {usage.signal_id} · <code>{usage.access}</code>
                                </span>
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <span className="text-stone-400">not in cards</span>
                        )}
                      </td>
                      {showMwsColumn ? (
                        <td className="px-2 py-1.5">
                          <VariableValueCell entry={mwsValues?.variables[variable.name]} />
                        </td>
                      ) : null}
                      <td className="px-2 py-1.5 text-stone-700">{variable.description || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ))}

        {!loading && search && !filteredSections.length ? (
          <p className="text-sm text-stone-500">No variables match “{search}”.</p>
        ) : null}

        <CommandFooter
          title="Add a variable to the triage dashboard"
          commands={[
            {
              label: 'Rebuild all dashboard sections',
              command: '.\\.venv\\Scripts\\python.exe scripts\\triage\\build_variable_dashboard.py',
            },
            {
              label: 'Add one variable to a section',
              command:
                '.\\.venv\\Scripts\\python.exe scripts\\triage\\build_variable_dashboard.py --add-variable borewell_density --section Agriculture/water_scarcity',
            },
          ]}
        />
      </main>
    </div>
  )
}
