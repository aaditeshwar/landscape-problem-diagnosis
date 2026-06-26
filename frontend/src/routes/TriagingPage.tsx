import { useEffect, useRef, useState } from 'react'
import { ExternalLink } from '../components/ExternalLink'
import { CommandFooter } from '../components/CommandFooter'
import {
  fetchTriageCatalog,
  fetchTriageCatalogPatches,
  fetchTriageCatalogs,
  fetchCardMap,
  triageCatalogExampleUrl,
  uploadTriageCatalog,
  type CardMapResponse,
  type CaseStudyCatalog,
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
  const [catalogs, setCatalogs] = useState<CaseStudyCatalog[]>([])
  const [selectedCatalog, setSelectedCatalog] = useState('case_study_locations_v3.json')
  const [bundle, setBundle] = useState<CatalogBundle | null>(null)
  const [catalogPatches, setCatalogPatches] = useState<TriageCatalogPatches | null>(null)
  const [cardMapsByMws, setCardMapsByMws] = useState<Record<string, CardMapResponse>>({})
  const [cardMapsReady, setCardMapsReady] = useState(false)
  const [reviewer, setReviewer] = useState(loadStoredReviewerName)
  const [reviewerAccess, setReviewerAccess] = useState<ReviewerAccessConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [uploadFilename, setUploadFilename] = useState('')
  const [uploadBusy, setUploadBusy] = useState(false)
  const [uploadMessage, setUploadMessage] = useState<string | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadPanelOpen, setUploadPanelOpen] = useState(false)
  const uploadInputRef = useRef<HTMLInputElement>(null)

  const reloadCatalogs = async (selectFilename?: string) => {
    const { catalogs: rows } = await fetchTriageCatalogs()
    const sorted = [...rows].sort((a, b) => {
      const sourceRank = (row: CaseStudyCatalog) => (row.source === 'user' ? 1 : 0)
      const bySource = sourceRank(a) - sourceRank(b)
      if (bySource !== 0) return bySource
      return b.filename.localeCompare(a.filename)
    })
    setCatalogs(sorted)
    if (selectFilename) {
      setSelectedCatalog(selectFilename)
      return
    }
    const preferred = sorted.find((row) => row.filename === 'case_study_locations_v3.json')
    if (preferred) {
      setSelectedCatalog(preferred.filename)
    } else if (sorted.length) {
      setSelectedCatalog(sorted[0].filename)
    }
  }

  const catalogLabel = (row: CaseStudyCatalog) =>
    row.source === 'user' ? `${row.filename} (your upload)` : row.filename

  useEffect(() => {
    fetchReviewerAccess().then(setReviewerAccess).catch(() => {
      setReviewerAccess({ allowed_reviewers_all: true, allowed_reviewers: [] })
    })
    reloadCatalogs().catch((err: Error) => setError(err.message))
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

  const handleCatalogUpload = async (file: File | undefined) => {
    if (!file) return
    setUploadBusy(true)
    setUploadError(null)
    setUploadMessage(null)
    try {
      const result = await uploadTriageCatalog(file, uploadFilename.trim() || undefined)
      setUploadMessage(
        `Uploaded ${result.catalog_filename} (${result.instance_count} case studies). Select it from the catalog dropdown to triage.`,
      )
      setUploadFilename('')
      if (uploadInputRef.current) uploadInputRef.current.value = ''
      await reloadCatalogs(result.catalog_filename)
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploadBusy(false)
    }
  }

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
                    {catalogLabel(row)}
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
            <ExternalLink to="/review" className="text-sm text-amber-800 hover:underline">
              Query eval review
            </ExternalLink>
            <ExternalLink to="/dashboard" className="text-sm text-amber-800 hover:underline">
              Variable dashboard
            </ExternalLink>
            <ExternalLink to="/variables" className="text-sm text-amber-800 hover:underline">
              Variable catalog
            </ExternalLink>
            <ExternalLink to="/" className="text-sm text-amber-800 hover:underline">
              Home
            </ExternalLink>
            <ExternalLink to="/diagnose" className="text-sm text-amber-800 hover:underline">
              Diagnosis map
            </ExternalLink>
          </div>
        </div>
        {reviewerAccess && !reviewerValid && reviewerAccessHint(reviewerAccess, reviewer) ? (
          <p className="mx-auto mt-2 max-w-[1400px] text-xs text-red-700">{reviewerAccessHint(reviewerAccess, reviewer)}</p>
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

      <section className="border-b border-stone-200 bg-stone-50/80 px-4 py-3">
        <div className="mx-auto max-w-[1400px]">
          <button
            type="button"
            className="flex w-full items-center justify-between gap-3 text-left"
            aria-expanded={uploadPanelOpen}
            onClick={() => setUploadPanelOpen((open) => !open)}
          >
            <span className="text-sm font-semibold text-stone-800">Upload your case study catalog</span>
            <span className="text-xs text-stone-500">{uploadPanelOpen ? 'Hide' : 'Show'}</span>
          </button>
          {uploadPanelOpen ? (
            <div className="mt-3 space-y-3 border-t border-stone-200 pt-3">
              <p className="max-w-3xl text-xs leading-relaxed text-stone-600">
                JSON must include a <code className="rounded bg-white px-1">diagnosis_framework</code> with{' '}
                <code className="rounded bg-white px-1">production_systems → observed_stresses → causal_pathways → case_studies</code>.
                Malformed or non-compliant files are rejected. Accepted uploads appear in the catalog dropdown above.
              </p>
              <div className="flex flex-wrap items-end gap-3">
                <a
                  href={triageCatalogExampleUrl()}
                  download="case_study_catalog_example.json"
                  className="rounded border border-stone-300 bg-white px-3 py-1.5 text-sm text-stone-800 hover:border-amber-700 hover:text-amber-900"
                >
                  Download example JSON
                </a>
                <label className="flex flex-col gap-1 text-xs text-stone-600">
                  Optional filename
                  <input
                    className="rounded border border-stone-300 bg-white px-2 py-1 text-sm text-stone-800"
                    placeholder="my_case_studies.json"
                    value={uploadFilename}
                    onChange={(event) => setUploadFilename(event.target.value)}
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs text-stone-600">
                  Catalog file
                  <input
                    ref={uploadInputRef}
                    type="file"
                    accept="application/json,.json"
                    className="max-w-xs text-sm text-stone-700 file:mr-2 file:rounded file:border-0 file:bg-amber-800 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-amber-50 hover:file:bg-amber-900"
                    disabled={uploadBusy}
                    onChange={(event) => {
                      const file = event.target.files?.[0]
                      void handleCatalogUpload(file)
                    }}
                  />
                </label>
                {uploadBusy ? <p className="text-sm text-stone-500">Validating and saving…</p> : null}
              </div>
              {uploadMessage ? <p className="text-sm text-emerald-800">{uploadMessage}</p> : null}
              {uploadError ? <p className="text-sm text-red-700">{uploadError}</p> : null}
            </div>
          ) : null}
        </div>
      </section>

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
