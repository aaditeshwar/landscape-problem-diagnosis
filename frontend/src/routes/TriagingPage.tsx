import { useEffect, useState } from 'react'
import { ExternalLink } from '../components/ExternalLink'
import { CommandFooter } from '../components/CommandFooter'
import {
  fetchTriageCatalog,
  fetchTriageCatalogPatches,
  fetchTriageCatalogs,
  fetchCardMap,
  type CardMapResponse,
  type CatalogBundle,
  type TriageCatalogPatches,
} from '../api/triage'
import { TriageSectionPanel } from '../triaging/TriageSectionPanel'
import {
  fetchReviewerAccess,
  isReviewerAllowed,
  loadStoredReviewerName,
  reviewerAccessHint,
  storeReviewerName,
  type ReviewerAccessConfig,
} from '../utils/reviewerAccess'

export function TriagingPage() {
  const [catalogs, setCatalogs] = useState<Array<{ filename: string }>>([])
  const [selectedCatalog, setSelectedCatalog] = useState('case_study_locations_v3.json')
  const [bundle, setBundle] = useState<CatalogBundle | null>(null)
  const [catalogPatches, setCatalogPatches] = useState<TriageCatalogPatches | null>(null)
  const [cardMapsByMws, setCardMapsByMws] = useState<Record<string, CardMapResponse>>({})
  const [cardMapsReady, setCardMapsReady] = useState(false)
  const [reviewer, setReviewer] = useState(loadStoredReviewerName)
  const [reviewerAccess, setReviewerAccess] = useState<ReviewerAccessConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchReviewerAccess().then(setReviewerAccess).catch(() => {
      setReviewerAccess({ allowed_reviewers_all: true, allowed_reviewers: [] })
    })
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
    Promise.all([fetchTriageCatalog(selectedCatalog), fetchTriageCatalogPatches(selectedCatalog)])
      .then(([catalogData, patchData]) => {
        if (cancelled) return
        setBundle(catalogData)
        setCatalogPatches(patchData)
        if (patchData.reviewer && !reviewer) {
          setReviewer(patchData.reviewer)
        }
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

  useEffect(() => {
    if (!bundle) {
      setCardMapsByMws({})
      setCardMapsReady(false)
      return
    }
    let cancelled = false
    setCardMapsReady(false)
    const mwsIds = [...new Set(bundle.sections.flatMap((section) => section.instances.map((inst) => inst.mws_id)))]
    Promise.all(mwsIds.map((mwsId) => fetchCardMap(mwsId).then((map) => [mwsId, map] as const)))
      .then((entries) => {
        if (cancelled) return
        setCardMapsByMws(Object.fromEntries(entries))
        setCardMapsReady(true)
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message || 'Failed to load MWS card maps')
      })
    return () => {
      cancelled = true
    }
  }, [bundle])

  const reviewerValid = reviewerAccess ? isReviewerAllowed(reviewer, reviewerAccess) : Boolean(reviewer.trim())

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
            <label className="flex items-center gap-2 text-sm text-stone-700">
              Reviewer
              <input
                className={`rounded border bg-white px-2 py-1 ${reviewerValid ? 'border-stone-300' : 'border-red-400'}`}
                placeholder="Your name"
                value={reviewer}
                onChange={(event) => {
                  setReviewer(event.target.value)
                  storeReviewerName(event.target.value)
                }}
              />
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
        {reviewerAccess && !reviewerValid ? (
          <p className="mx-auto mt-2 max-w-[1400px] text-xs text-red-700">{reviewerAccessHint(reviewerAccess)}</p>
        ) : null}
        {catalogPatches?.batch_id ? (
          <p className="mx-auto mt-2 max-w-[1400px] text-xs text-stone-500">
            Saved patches for this catalog → revise-cards batch{' '}
            <ExternalLink
              to={`/revise-cards?batch=${encodeURIComponent(catalogPatches.batch_id)}`}
              className="font-mono text-amber-800 hover:underline"
            >
              {catalogPatches.batch_id}
            </ExternalLink>
            {catalogPatches.updated_at ? ` · last saved ${catalogPatches.updated_at}` : null}
          </p>
        ) : null}
      </header>

      <main className="mx-auto max-w-[1400px] space-y-6 px-4 py-6">
        {error ? <p className="text-sm text-red-700">{error}</p> : null}
        {loading ? <p className="text-sm text-stone-500">Loading catalog…</p> : null}
        {!cardMapsReady && bundle ? <p className="text-sm text-stone-500">Loading MWS card maps…</p> : null}
        {bundle ? (
          <p className="text-sm text-stone-600">
            {bundle.instance_count} instances across {bundle.sections.length} sections
          </p>
        ) : null}
        {bundle?.sections.map((section) => (
          <TriageSectionPanel
            key={`${selectedCatalog}-${section.section_key}`}
            section={section}
            catalogFilename={selectedCatalog}
            reviewer={reviewer}
            reviewerValid={reviewerValid}
            catalogPatches={catalogPatches}
            cardMapsByMws={cardMapsByMws}
            cardMapsReady={cardMapsReady}
            onPatchesSaved={setCatalogPatches}
          />
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
