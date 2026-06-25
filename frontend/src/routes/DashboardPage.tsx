import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  fetchDashboardChartDefaults,
  fetchDashboardManifest,
  fetchDashboardSection,
  type DashboardChartDefaults,
  type DashboardSection,
  type DashboardVariable,
} from '../api/triage'
import { CdfChart } from '../dashboard/CdfChart'
import { CategoryBarChart } from '../dashboard/CategoryBarChart'
import { CommandFooter } from '../components/CommandFooter'
import { ExternalLink } from '../components/ExternalLink'

function variableGroups(section: DashboardSection) {
  if (section.variable_groups?.length) return section.variable_groups
  const byCat: Record<string, DashboardVariable[]> = {}
  for (const variable of Object.values(section.variables)) {
    const cat = 'Variables'
    byCat[cat] = byCat[cat] || []
    byCat[cat].push(variable)
  }
  return Object.entries(byCat).map(([category, variables]) => ({ category, variables }))
}

function matchesQuery(variable: DashboardVariable, query: string): boolean {
  if (!query) return true
  const q = query.toLowerCase()
  return variable.access.toLowerCase().includes(q) || (variable.unit || '').toLowerCase().includes(q)
}

function hasChartData(variable: DashboardVariable): boolean {
  if (variable.chart_type === 'categorical') return (variable.distribution?.length ?? 0) > 0
  if (variable.cdf_variants && Object.values(variable.cdf_variants).some((variant) => variant.cdf?.length)) {
    return true
  }
  return (variable.cdf?.length ?? 0) > 0
}

function DashboardSectionPanel({
  sectionKey,
  section,
  groups,
  chartDefaults,
}: {
  sectionKey: string
  section: DashboardSection
  groups: Array<{ category: string; variables: DashboardVariable[] }>
  chartDefaults: Record<string, DashboardChartDefaults>
}) {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <section key={sectionKey} id={sectionKey} className="space-y-4 rounded-xl border border-stone-200 bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-stone-900">
            {section.production_system} · {section.observed_stress.replace(/_/g, ' ')}
          </h2>
          <p className="text-xs text-stone-500">{section.mws_count} MWS in global pool</p>
        </div>
        <button
          type="button"
          onClick={() => setCollapsed((value) => !value)}
          className="shrink-0 rounded border border-stone-300 px-2 py-1 text-xs text-stone-700 hover:bg-stone-50"
          aria-expanded={!collapsed}
        >
          {collapsed ? 'Expand' : 'Collapse'}
        </button>
      </div>
      {!collapsed
        ? groups.map((group) => (
            <div key={group.category} className="space-y-2">
              <h3 className="text-sm font-semibold text-stone-700">{group.category}</h3>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {group.variables.map((variable) => {
                  const isCategorical =
                    variable.chart_type === 'categorical' ||
                    (!variable.chart_type &&
                      (variable.distribution?.length ?? 0) > 0 &&
                      !variable.cdf?.length &&
                      !variable.cdf_variants)
                  return isCategorical ? (
                    <CategoryBarChart
                      key={variable.access}
                      title={variable.access}
                      unit={variable.unit}
                      sampleCount={variable.sample_count}
                      distribution={variable.distribution || []}
                    />
                  ) : (
                    <CdfChart
                      key={variable.access}
                      title={variable.access}
                      unit={variable.unit}
                      cdfVariants={variable.cdf_variants}
                      cdf={variable.cdf}
                      samples={variable.samples}
                      sampleCount={variable.sample_count}
                      xMax={variable.x_max}
                      defaults={chartDefaults[variable.access]}
                    />
                  )
                })}
              </div>
            </div>
          ))
        : null}
    </section>
  )
}

export function DashboardPage() {
  const [params] = useSearchParams()
  const [manifest, setManifest] = useState<Array<{ section_key: string }>>([])
  const [sections, setSections] = useState<Record<string, DashboardSection>>({})
  const [chartDefaults, setChartDefaults] = useState<Record<string, DashboardChartDefaults>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  const focusKey = useMemo(() => {
    const production = params.get('production_system')
    const stress = params.get('observed_stress')
    if (!production || !stress) return null
    const ps = production.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')
    return `${ps}__${stress}`
  }, [params])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchDashboardManifest()
      .then(async ({ sections: rows }) => {
        if (cancelled) return
        setManifest(rows)
        const defaultsPayload = await fetchDashboardChartDefaults()
        if (!cancelled) setChartDefaults(defaultsPayload.variables || {})
        const loaded: Record<string, DashboardSection> = {}
        for (const row of rows) {
          loaded[row.section_key] = await fetchDashboardSection(row.section_key)
        }
        if (!cancelled) setSections(loaded)
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message || 'Failed to load dashboard')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!focusKey || loading) return
    const el = document.getElementById(focusKey)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [focusKey, loading, sections])

  return (
    <div className="min-h-screen bg-stone-100">
      <header className="border-b border-stone-200 bg-white px-4 py-3">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-stone-900">Variable dashboard</h1>
            <p className="text-sm text-stone-500">Global variable distributions by triage section</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter variables…"
              className="rounded-md border border-stone-300 px-3 py-1.5 text-sm"
              aria-label="Filter variables"
            />
            <ExternalLink to="/variables" className="text-sm text-amber-800 hover:underline">
              Variable catalog
            </ExternalLink>
            <ExternalLink to="/triaging" className="text-sm text-amber-800 hover:underline">
              ← Triaging
            </ExternalLink>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1400px] space-y-8 px-4 py-6">
        {error ? <p className="text-sm text-red-700">{error}</p> : null}
        {loading ? <p className="text-sm text-stone-500">Loading dashboard…</p> : null}
        {!loading && !manifest.length ? (
          <p className="text-sm text-stone-600">
            No precomputed dashboard found. Run{' '}
            <code className="rounded bg-stone-200 px-1">scripts/triage/build_variable_dashboard.py</code>.
          </p>
        ) : null}

        {manifest.map((row) => {
          const section = sections[row.section_key]
          if (!section) return null
          const groups = variableGroups(section)
            .map((group) => ({
              ...group,
              variables: group.variables.filter((v) => matchesQuery(v, search) && hasChartData(v)),
            }))
            .filter((group) => group.variables.length > 0)

          if (!groups.length && search) return null

          return (
            <DashboardSectionPanel
              key={row.section_key}
              sectionKey={row.section_key}
              section={section}
              groups={groups}
              chartDefaults={chartDefaults}
            />
          )
        })}

        <CommandFooter
          title="Add a variable to the dashboard"
          commands={[
            {
              label: 'Rebuild all sections',
              command: '.\\.venv\\Scripts\\python.exe scripts\\triage\\build_variable_dashboard.py',
            },
            {
              label: 'Add variable to one section',
              command:
                '.\\.venv\\Scripts\\python.exe scripts\\triage\\build_variable_dashboard.py --add-variable dry_spell_weeks[-1] --section Agriculture/water_scarcity',
            },
          ]}
        />
      </main>
    </div>
  )
}
