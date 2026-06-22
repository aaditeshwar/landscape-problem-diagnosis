import { useEffect, useState } from 'react'
import { ExternalLink } from '../components/ExternalLink'
import { CommandFooter } from '../components/CommandFooter'
import { fetchTriageCatalog, fetchTriageCatalogs, type CatalogBundle } from '../api/triage'
import { TriageSectionPanel } from '../triaging/TriageSectionPanel'

export function TriagingPage() {
  const [catalogs, setCatalogs] = useState<Array<{ filename: string }>>([])
  const [selectedCatalog, setSelectedCatalog] = useState('case_study_locations_v3.json')
  const [bundle, setBundle] = useState<CatalogBundle | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchTriageCatalogs()
      .then(({ catalogs: rows }) => {
        const sorted = [...rows].sort((a, b) => b.filename.localeCompare(a.filename))
        setCatalogs(sorted)
        const preferred = sorted.find((row) => row.filename === 'case_study_locations_v3.json')
        if (preferred) {
          setSelectedCatalog(preferred.filename)
        } else if (sorted.length) {
          setSelectedCatalog(sorted[0].filename)
        }
      })
      .catch((err: Error) => setError(err.message))
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchTriageCatalog(selectedCatalog)
      .then((data) => {
        if (!cancelled) setBundle(data)
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message || 'Failed to load catalog')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [selectedCatalog])

  return (
    <div className="min-h-screen bg-stone-100">
      <header className="border-b border-stone-200 bg-white px-4 py-3">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-stone-900">Case study triaging</h1>
            <p className="text-sm text-stone-500">Tune signals and confirmation policy per production system / stress</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-stone-700">
              Catalog
              <select
                className="rounded border border-stone-300 bg-white px-2 py-1"
                value={selectedCatalog}
                onChange={(event) => setSelectedCatalog(event.target.value)}
              >
                {catalogs.map((row) => (
                  <option key={row.filename} value={row.filename}>
                    {row.filename}
                  </option>
                ))}
              </select>
            </label>
            <ExternalLink to="/dashboard" className="text-sm text-amber-800 hover:underline">
              Variable dashboard
            </ExternalLink>
            <ExternalLink to="/variables" className="text-sm text-amber-800 hover:underline">
              Variable catalog
            </ExternalLink>
            <ExternalLink to="/" className="text-sm text-amber-800 hover:underline">
              Diagnosis app
            </ExternalLink>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1400px] space-y-6 px-4 py-6">
        {error ? <p className="text-sm text-red-700">{error}</p> : null}
        {loading ? <p className="text-sm text-stone-500">Loading catalog…</p> : null}
        {bundle ? (
          <p className="text-sm text-stone-600">
            {bundle.instance_count} instances across {bundle.sections.length} sections
          </p>
        ) : null}
        {bundle?.sections.map((section) => (
          <TriageSectionPanel key={section.section_key} section={section} />
        ))}

        <CommandFooter
          title="Regenerate case-study MWS JSON exports"
          commands={[
            {
              label: 'All case-study MWS in catalog',
              command: '.\\.venv\\Scripts\\python.exe scripts\\export_case_study_mws_variables.py',
            },
            {
              label: 'Single MWS (example)',
              command: '.\\.venv\\Scripts\\python.exe scripts\\export_case_study_mws_variables.py --uid 4_102533',
            },
            {
              label: 'Current catalog file',
              command: `metadata/${selectedCatalog}`,
            },
          ]}
        />
      </main>
    </div>
  )
}
