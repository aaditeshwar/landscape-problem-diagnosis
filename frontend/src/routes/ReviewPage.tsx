import { useEffect, useState } from 'react'

import { ExternalLink } from '../components/ExternalLink'

import { RubricHint } from '../components/RubricHint'

import { CommandFooter } from '../components/CommandFooter'

import { DIMENSION_IDS, RUBRIC_DIMENSIONS, RUBRIC_ERROR_FLAGS, dimensionScorePct, dimensionScoreTooltip, formatDimensionScore, rubricTooltip } from '../eval/evalRubricHelp'

import { appHref } from '../appBase'

import {

  fetchQueryEvalBatch,

  fetchQueryEvalBatches,

  type AgreementPair,

  type AgreementSummary,

  type CaseStudyEval,

  type QueryEvalBatch,

  type QueryEvalBatchSummary,

  type QueryRun,

} from '../api/review'



const MODE_LABELS: Record<string, string> = {

  server: 'Server',

  llm_ollama: 'Ollama',

  server_plus_llm_ollama: 'Srv+Ollama',

  llm_claude: 'Claude',

}



const OUTDATED_EVAL_MODES = new Set(['llm_ollama', 'server_plus_llm_ollama'])



function evalModeLabel(mode: string, markOutdated = false): string {

  const base = MODE_LABELS[mode] ?? mode

  if (markOutdated && OUTDATED_EVAL_MODES.has(mode)) {

    return `${base} (outdated)`

  }

  return base

}



const EVAL_MODES = ['server', 'llm_ollama', 'server_plus_llm_ollama', 'llm_claude'] as const



function scorePct(evaluation: { weighted_total?: number; error?: string } | undefined): string | null {

  if (!evaluation || evaluation.error) return null

  if (typeof evaluation.weighted_total !== 'number') return null

  return `${Math.round(evaluation.weighted_total * 100)}%`

}



function scoreCell(evaluation: { weighted_total?: number; error?: string } | undefined) {

  const pct = scorePct(evaluation)

  if (!evaluation) return <span className="text-stone-400">—</span>

  if (evaluation.error) {

    return (

      <span className="text-red-600" title={evaluation.error}>

        err

      </span>

    )

  }

  if (!pct) return <span className="text-stone-400">—</span>

  const tone =

    (evaluation.weighted_total ?? 0) >= 0.7

      ? 'text-emerald-700'

      : (evaluation.weighted_total ?? 0) >= 0.45

        ? 'text-amber-700'

        : 'text-red-700'

  return <span className={`font-mono text-xs ${tone}`}>{pct}</span>

}



function kappaLabel(pair: AgreementPair) {

  const value = pair.kappa

  if (value == null || Number.isNaN(value)) return '—'

  const tone = value >= 0.6 ? 'text-emerald-700' : value >= 0.2 ? 'text-amber-700' : 'text-red-700'

  const exact = pair.exact_agreements

  const total = pair.pathway_count

  const suffix = exact != null && total ? ` (${exact}/${total})` : ''

  const title = [

    pair.observed_agreement != null ? `observed agreement: ${(pair.observed_agreement * 100).toFixed(1)}%` : null,

    pair.expected_agreement != null ? `chance agreement: ${(pair.expected_agreement * 100).toFixed(1)}%` : null,

    'κ = (observed − chance) / (1 − chance)',

  ]

    .filter(Boolean)

    .join(' · ')

  return (

    <span className={`font-mono text-xs ${tone}`} title={title}>

      κ={value.toFixed(2)}

      {suffix}

    </span>

  )

}



function AgreementStrip({ agreement }: { agreement?: AgreementSummary }) {

  if (!agreement) return null

  return (

    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-stone-500">

      {agreement.server_vs_ollama_independent ? (

        <span title="Server vs Ollama independent assessment">

          S↔Oll {kappaLabel(agreement.server_vs_ollama_independent)}

        </span>

      ) : null}

      {agreement.server_vs_claude_independent ? (

        <span title="Server vs Claude independent assessment">

          S↔Cla {kappaLabel(agreement.server_vs_claude_independent)}

        </span>

      ) : null}

      {agreement.ollama_vs_claude_independent ? (

        <span title="Ollama vs Claude independent assessment">

          O↔C {kappaLabel(agreement.ollama_vs_claude_independent)}

        </span>

      ) : null}

    </div>

  )

}



function SessionLinks({

  sessions,

  includeServer = false,

}: {

  sessions: Record<string, { feedback_url?: string; error?: string }>

  includeServer?: boolean

}) {

  const modes = includeServer

    ? (['server', 'llm_ollama', 'llm_claude'] as const)

    : (['llm_ollama', 'llm_claude'] as const)

  return (

    <div className="flex flex-wrap gap-2">

      {modes.map((mode) => {

        const ref = sessions[mode]

        if (!ref) return null

        if (ref.error) {

          return (

            <span key={mode} className="text-xs text-red-600" title={ref.error}>

              {MODE_LABELS[mode] ?? mode}: failed

            </span>

          )

        }

        if (!ref.feedback_url) return null

        return (

          <ExternalLink

            key={mode}

            to={ref.feedback_url}

            className="rounded bg-stone-200 px-2 py-0.5 text-xs text-stone-800 hover:bg-stone-300"

          >

            {MODE_LABELS[mode] ?? mode}

          </ExternalLink>

        )

      })}

    </div>

  )

}



function RubricLegend() {
  return (
    <div className="rounded border border-stone-200 bg-stone-50 px-3 py-2 text-xs text-stone-600">
      <p className="font-medium text-stone-700">Evaluation rubric</p>
      <p className="mt-1 text-xs text-stone-500">
        Dimensions scored 0–3 (shown as % of max). Weighted total is 0–100%.
      </p>
      <p className="mt-1">
        <span className="mr-2 font-medium text-stone-500">Dimensions:</span>
        {DIMENSION_IDS.map((id, index) => (
          <span key={id}>
            {index > 0 ? ' · ' : null}
            <RubricHint id={id} />
          </span>
        ))}
      </p>
      <p className="mt-1">
        <span className="mr-2 font-medium text-stone-500">Error flags:</span>
        {Object.keys(RUBRIC_ERROR_FLAGS).map((id, index) => (
          <span key={id}>
            {index > 0 ? ' · ' : null}
            <RubricHint id={id} />
          </span>
        ))}
      </p>
    </div>
  )
}

function CollapsedScores({ run, markOutdatedModes = false }: { run: QueryRun; markOutdatedModes?: boolean }) {

  return (

    <div className="flex flex-wrap items-center gap-2">

      {EVAL_MODES.map((mode) => (

        <span key={mode} className="inline-flex items-center gap-1 rounded bg-stone-50 px-1.5 py-0.5">

          <span className="text-[10px] uppercase tracking-wide text-stone-500">

            {evalModeLabel(mode, markOutdatedModes)}

          </span>

          {scoreCell(run.evaluations[mode])}

        </span>

      ))}

    </div>

  )

}



function QueryRunRow({ run, serverSession }: { run: QueryRun; serverSession?: { feedback_url?: string } }) {

  const [open, setOpen] = useState(false)

  const markOutdatedModes = isDiagnosticsEngineRun(run)

  const sessionsWithServer = {

    ...(serverSession ? { server: serverSession } : {}),

    ...run.sessions,

  }



  return (

    <div className="border-t border-stone-100 py-2">

      <button

        type="button"

        className="flex w-full flex-col gap-2 text-left sm:flex-row sm:items-start sm:justify-between"

        onClick={() => setOpen((v) => !v)}

      >

        <div className="min-w-0 flex-1">

          <div className="flex flex-wrap items-baseline gap-2">

            <span className="font-mono text-sm font-medium text-stone-800">{run.query_id}</span>

            <span className="text-xs text-stone-500">{run.persona}</span>

            <span className="text-stone-400">{open ? '▾' : '▸'}</span>

          </div>

          {!open ? <CollapsedScores run={run} markOutdatedModes={markOutdatedModes} /> : null}

          {!open ? <AgreementStrip agreement={run.agreement} /> : null}

        </div>

      </button>

      {open ? (

        <div className="mt-2 space-y-2 pl-2">

          <p className="text-xs text-stone-600">{run.query}</p>

          <SessionLinks sessions={sessionsWithServer} includeServer />

          <AgreementStrip agreement={run.agreement} />

          <table className="w-full text-xs">

            <thead>

              <tr className="text-stone-500">

                <th className="py-1 text-left font-medium">Mode</th>

                <th className="py-1 text-left font-medium">Score</th>

                {DIMENSION_IDS.map((id) => (

                  <th key={id} className="py-1 px-1 text-left font-medium">

                    <RubricHint id={id} />

                  </th>

                ))}

                <th className="py-1 text-left font-medium">Flags</th>

                <th className="py-1 text-left font-medium">Summary</th>

              </tr>

            </thead>

            <tbody>

              {EVAL_MODES.map((mode) => {

                const ev = run.evaluations[mode]

                return (

                  <tr key={mode} className="align-top">

                    <td className="py-1 pr-3 text-stone-700">{evalModeLabel(mode, markOutdatedModes)}</td>

                    <td className="py-1 pr-3">{scoreCell(ev)}</td>

                    {DIMENSION_IDS.map((id) => {

                      const dim = ev?.dimension_scores?.[id]

                      const dimScore = dim?.score

                      return (

                        <td

                          key={id}

                          className="py-1 px-1 font-mono text-stone-700"

                          title={typeof dimScore === 'number' ? dimensionScoreTooltip(dimScore, dim?.justification) : dim?.justification}

                        >

                          {typeof dimScore === 'number' ? formatDimensionScore(dimScore) : '—'}

                        </td>

                      )

                    })}

                    <td className="py-1 pr-3">

                      {ev?.error_flags_triggered?.length ? (

                        <div className="flex flex-wrap gap-1">

                          {ev.error_flags_triggered.map((flag, index) => {

                            const flagId = flag.flag_id || `EF?${index}`

                            return (

                              <span

                                key={`${flagId}-${index}`}

                                className="rounded bg-red-50 px-1 font-mono text-[10px] text-red-700"

                                title={

                                  flag.detail

                                    ? `${rubricTooltip(RUBRIC_ERROR_FLAGS[flagId] ?? { id: flagId, name: flagId, description: flag.detail })} — ${flag.detail}`

                                    : rubricTooltip(

                                        RUBRIC_ERROR_FLAGS[flagId] ?? {

                                          id: flagId,

                                          name: flagId,

                                          description: 'Rubric error flag',

                                        },

                                      )

                                }

                              >

                                <RubricHint id={flagId} className="border-none" />

                              </span>

                            )

                          })}

                        </div>

                      ) : (

                        <span className="text-stone-400">—</span>

                      )}

                    </td>

                    <td className="py-1 text-stone-600">

                      {ev?.error ? (

                        <span className="text-red-600">{ev.error}</span>

                      ) : (

                        <>

                          {ev?.summary || '—'}

                          {ev?.server_query_alignment ? (

                            <p className="mt-1 text-stone-500">

                              <span className="font-medium">Server alignment:</span> {ev.server_query_alignment}

                            </p>

                          ) : null}

                        </>

                      )}

                    </td>

                  </tr>

                )

              })}

            </tbody>

          </table>

        </div>

      ) : null}

    </div>

  )

}



function meanStd(scores: number[]): { mean: number; std: number } | null {

  if (!scores.length) return null

  const mean = scores.reduce((sum, value) => sum + value, 0) / scores.length

  const variance = scores.reduce((sum, value) => sum + (value - mean) ** 2, 0) / scores.length

  return { mean, std: Math.sqrt(variance) }

}



function formatMeanStd(mean: number, std: number): string {

  return `${Math.round(mean * 100)}% ± ${Math.round(std * 100)}%`

}



type ScoreBucket = {

  modes: Record<string, number[]>

  queryCount: number

  caseStudyIds: Set<number>

  errorFlagsByMode: Record<string, Record<string, number>>

  runtimeErrorsByMode: Record<string, number>

  dimensionScoresByMode: Record<string, Record<string, number[]>>

}



type ScoreTableRow = {

  key: string

  label: string

  bucket: ScoreBucket

  indent?: boolean

}



function emptyScoreBucket(): ScoreBucket {

  return {

    modes: {},

    queryCount: 0,

    caseStudyIds: new Set(),

    errorFlagsByMode: {},

    runtimeErrorsByMode: {},

    dimensionScoresByMode: {},

  }

}



function addQueryRunToBucket(bucket: ScoreBucket, caseStudyId: number, run: QueryRun) {

  bucket.queryCount += 1

  bucket.caseStudyIds.add(caseStudyId)

  for (const mode of EVAL_MODES) {

    const ev = run.evaluations?.[mode]

    if (!ev) continue

    if (ev.error) {

      bucket.runtimeErrorsByMode[mode] = (bucket.runtimeErrorsByMode[mode] ?? 0) + 1

      continue

    }

    const score = ev.weighted_total

    if (typeof score === 'number') {

      const rows = bucket.modes[mode] ?? []

      rows.push(score)

      bucket.modes[mode] = rows

    }

    for (const flag of ev.error_flags_triggered ?? []) {

      const flagId = flag.flag_id

      if (!flagId) continue

      const byFlag = bucket.errorFlagsByMode[mode] ?? {}

      byFlag[flagId] = (byFlag[flagId] ?? 0) + 1

      bucket.errorFlagsByMode[mode] = byFlag

    }

    for (const dimId of DIMENSION_IDS) {

      const dimScore = ev.dimension_scores?.[dimId]?.score

      if (typeof dimScore !== 'number') continue

      const byDim = bucket.dimensionScoresByMode[mode] ?? {}

      const rows = byDim[dimId] ?? []

      rows.push(dimScore)

      byDim[dimId] = rows

      bucket.dimensionScoresByMode[mode] = byDim

    }

  }

}



function ErrorCountStrip({ mode, bucket }: { mode: string; bucket: ScoreBucket }) {

  const flags = bucket.errorFlagsByMode[mode] ?? {}

  const flagEntries = Object.entries(flags).sort(([a], [b]) => a.localeCompare(b))

  const runtimeCount = bucket.runtimeErrorsByMode[mode] ?? 0

  if (!flagEntries.length && !runtimeCount) return null

  return (

    <div className="mt-1 flex flex-wrap gap-1">

      {flagEntries.map(([id, count]) => {

        const entry = RUBRIC_ERROR_FLAGS[id]

        return (

          <span

            key={id}

            className="cursor-help rounded bg-red-50 px-1 font-mono text-[10px] text-red-700"

            title={entry ? rubricTooltip(entry) : id}

          >

            {id}:{count}

          </span>

        )

      })}

      {runtimeCount > 0 ? (

        <span

          className="cursor-help rounded bg-stone-100 px-1 font-mono text-[10px] text-stone-600"

          title="Evaluation failed (runtime or API error), not a rubric error flag"

        >

          err:{runtimeCount}

        </span>

      ) : null}

    </div>

  )

}



function DimensionScoreStrip({ mode, bucket }: { mode: string; bucket: ScoreBucket }) {

  const dims = bucket.dimensionScoresByMode[mode] ?? {}

  const entries: Array<{ id: (typeof DIMENSION_IDS)[number]; meanPct: number }> = []

  for (const id of DIMENSION_IDS) {

    const stats = meanStd(dims[id] ?? [])

    if (stats) entries.push({ id, meanPct: dimensionScorePct(stats.mean) })

  }

  if (!entries.length) return null

  return (

    <div className="mt-1 flex flex-wrap gap-1">

      {entries.map(({ id, meanPct }) => {

        const entry = RUBRIC_DIMENSIONS[id]

        return (

          <span

            key={id}

            className="cursor-help rounded bg-sky-50 px-1 font-mono text-[10px] text-sky-800"

            title={entry ? `${rubricTooltip(entry)} Mean ${meanPct}% across queries.` : `${id} mean ${meanPct}%`}

          >

            {id}:{meanPct}

          </span>

        )

      })}

    </div>

  )

}



function ScoreSummaryTable({

  title,

  description,

  labelHeader,

  rows,

  showErrorCounts = false,

  showDimensionScores = false,

  markOutdatedModes = false,

}: {

  title: string

  description: string

  labelHeader: string

  rows: ScoreTableRow[]

  showErrorCounts?: boolean

  showDimensionScores?: boolean

  markOutdatedModes?: boolean

}) {

  if (!rows.length) return null

  return (

    <section className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm">

      <h2 className="text-sm font-semibold text-stone-900">{title}</h2>

      <p className="mt-1 text-xs text-stone-500">{description}</p>

      <div className="mt-3 overflow-x-auto">

        <table className="w-full min-w-[36rem] text-sm">

          <thead>

            <tr className="border-b border-stone-200 text-left text-xs text-stone-500">

              <th className="py-2 pr-4 font-medium">{labelHeader}</th>

              {EVAL_MODES.map((mode) => (

                <th key={mode} className="py-2 pr-4 font-medium">

                  {evalModeLabel(mode, markOutdatedModes)}

                </th>

              ))}

              <th className="py-2 pr-4 font-medium">Queries</th>

              <th className="py-2 font-medium">Case studies</th>

            </tr>

          </thead>

          <tbody>

            {rows.map(({ key, label, bucket, indent }) => (

              <tr key={key} className="border-b border-stone-100 align-top">

                <td

                  className={`py-2 pr-4 font-medium text-stone-800 ${indent ? 'pl-6 font-normal' : ''}`}

                >

                  {label}

                </td>

                {EVAL_MODES.map((mode) => {

                  const stats = meanStd(bucket.modes[mode] ?? [])

                  return (

                    <td key={mode} className="py-2 pr-4 font-mono text-xs text-stone-700">

                      {stats ? formatMeanStd(stats.mean, stats.std) : '—'}

                      {showDimensionScores ? <DimensionScoreStrip mode={mode} bucket={bucket} /> : null}

                      {showErrorCounts ? <ErrorCountStrip mode={mode} bucket={bucket} /> : null}

                    </td>

                  )

                })}

                <td className="py-2 pr-4 font-mono text-xs text-stone-600">

                  {bucket.queryCount || '—'}

                </td>

                <td className="py-2 font-mono text-xs text-stone-600">

                  {bucket.caseStudyIds.size || '—'}

                </td>

              </tr>

            ))}

          </tbody>

        </table>

      </div>

    </section>

  )

}



function personaLabel(persona: string): string {

  return persona.replace(/_/g, ' ')

}



function productionSystemLabel(productionSystem: string): string {

  return productionSystem.replace(/_/g, ' ')

}



function normalizeDiagnosticsUrl(url: string): string {

  try {

    const parsed = new URL(url, window.location.origin)

    const uid = parsed.searchParams.get('uid') || parsed.searchParams.get('mws')

    const path = parsed.pathname.replace(/\/$/, '') || '/'

    if (uid && (path === '/' || path.endsWith('/core-insights'))) {

      return appHref(`/diagnose?uid=${encodeURIComponent(uid)}`)

    }

    return url

  } catch {

    return url

  }

}



function PersonaSummaryTable({ batch }: { batch: QueryEvalBatch }) {

  const byPersona = new Map<string, ScoreBucket>()

  for (const cs of batch.case_studies ?? []) {

    for (const run of cs.query_runs ?? []) {

      if (isDiagnosticsEngineRun(run)) continue

      const persona = run.persona || 'unknown'

      const entry = byPersona.get(persona) ?? emptyScoreBucket()

      addQueryRunToBucket(entry, cs.case_study_id, run)

      byPersona.set(persona, entry)

    }

  }

  const rows: ScoreTableRow[] = [...byPersona.keys()].sort((a, b) => a.localeCompare(b)).map((persona) => ({

    key: persona,

    label: personaLabel(persona),

    bucket: byPersona.get(persona) ?? emptyScoreBucket(),

  }))

  return (

    <ScoreSummaryTable

      title="Score summary by persona"

      description="Mean ± std dev of weighted rubric scores across queries in this batch."

      labelHeader="Persona"

      rows={rows}

    />

  )

}



function aggregateScoresByProductionSystem(
  batch: QueryEvalBatch,
  includeRun: (run: QueryRun) => boolean,
): Map<string, ScoreBucket> {
  const byProductionSystem = new Map<string, ScoreBucket>()

  for (const cs of batch.case_studies ?? []) {
    for (const run of cs.query_runs ?? []) {
      if (!includeRun(run)) continue

      const productionSystem = run.production_system || cs.production_system || 'unknown'
      const entry = byProductionSystem.get(productionSystem) ?? emptyScoreBucket()
      addQueryRunToBucket(entry, cs.case_study_id, run)
      byProductionSystem.set(productionSystem, entry)
    }
  }

  return byProductionSystem
}

function productionSystemRows(byProductionSystem: Map<string, ScoreBucket>): ScoreTableRow[] {
  return [...byProductionSystem.keys()].sort((a, b) => a.localeCompare(b)).map((productionSystem) => ({
    key: productionSystem,
    label: productionSystemLabel(productionSystem),
    bucket: byProductionSystem.get(productionSystem) ?? emptyScoreBucket(),
  }))
}

function isDiagnosticsEngineRun(run: QueryRun): boolean {
  return run.query_id === 'Q000' || run.persona === 'diagnostics_engine'
}

function diagnosticsEngineScoreRows(batch: QueryEvalBatch): ScoreTableRow[] {
  const overall = emptyScoreBucket()
  const byCaseStudyProductionSystem = new Map<string, ScoreBucket>()

  for (const cs of batch.case_studies ?? []) {
    const caseStudyProductionSystem = cs.production_system || 'unknown'

    for (const run of cs.query_runs ?? []) {
      if (!isDiagnosticsEngineRun(run)) continue

      addQueryRunToBucket(overall, cs.case_study_id, run)

      const entry = byCaseStudyProductionSystem.get(caseStudyProductionSystem) ?? emptyScoreBucket()
      addQueryRunToBucket(entry, cs.case_study_id, run)
      byCaseStudyProductionSystem.set(caseStudyProductionSystem, entry)
    }
  }

  if (overall.queryCount === 0) return []

  const rows: ScoreTableRow[] = [
    {
      key: 'multi-system',
      label: productionSystemLabel('Multi-system'),
      bucket: overall,
    },
  ]

  for (const productionSystem of [...byCaseStudyProductionSystem.keys()].sort((a, b) => a.localeCompare(b))) {
    rows.push({
      key: `case-study-ps-${productionSystem}`,
      label: productionSystemLabel(productionSystem),
      bucket: byCaseStudyProductionSystem.get(productionSystem) ?? emptyScoreBucket(),
      indent: true,
    })
  }

  return rows
}

function ProductionSystemSummaryTable({ batch }: { batch: QueryEvalBatch }) {
  const diagnosticsRows = diagnosticsEngineScoreRows(batch)
  const personaRows = productionSystemRows(
    aggregateScoresByProductionSystem(batch, (run) => !isDiagnosticsEngineRun(run)),
  )

  if (!diagnosticsRows.length && !personaRows.length) return null

  return (
    <div className="space-y-4">
      <ScoreSummaryTable
        title="Score summary by production system — diagnostics engine (Q000)"
        description="Overall multi-system Q000 scores, with breakdown by case-study production system. D1–D6 show mean dimension score (% of 3); EF1–EF5 show error-flag counts. Hover for definitions. Ollama and Srv+Ollama columns predate current server card set."
        labelHeader="Production system"
        rows={diagnosticsRows}
        showDimensionScores
        showErrorCounts
        markOutdatedModes
      />
      <ScoreSummaryTable
        title="Score summary by production system — persona queries"
        description="Mean ± std dev across bank queries (excluding Q000), grouped by production system."
        labelHeader="Production system"
        rows={personaRows}
      />
    </div>
  )
}



function CaseStudyCard({ row }: { row: CaseStudyEval }) {

  const location = [row.tehsil, row.district, row.state].filter(Boolean).join(', ')

  return (

    <section className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm">

      <div className="flex flex-wrap items-start justify-between gap-3">

        <div>

          <h2 className="text-lg font-semibold text-stone-900">

            Case study {row.case_study_id}

            <span className="ml-2 font-mono text-base font-normal text-stone-600">{row.mws_id}</span>

          </h2>

          <p className="text-sm text-stone-500">{location || '—'}</p>

          <p className="mt-1 text-sm text-stone-600">

            {row.production_system} / {row.observed_stress}

            {row.expected_pathway ? (

              <span className="ml-2 font-mono text-xs text-amber-800">→ {row.expected_pathway}</span>

            ) : row.stress_only ? (

              <span className="ml-2 text-xs text-stone-500">(stress only)</span>

            ) : null}

          </p>

        </div>

        <div className="flex flex-col items-end gap-2">

          {row.diagnostics_url ? (

            <ExternalLink

              to={normalizeDiagnosticsUrl(row.diagnostics_url)}

              className="rounded bg-amber-100 px-3 py-1 text-sm font-medium text-amber-900 hover:bg-amber-200"

            >

              Open MWS diagnostics

            </ExternalLink>

          ) : null}

          {row.sessions?.server?.feedback_url ? (

            <div className="text-right">

              <p className="text-xs text-stone-500">Server session (shared)</p>

              <SessionLinks sessions={{ server: row.sessions.server }} includeServer />

            </div>

          ) : null}

        </div>

      </div>

      <div className="mt-4">

        <h3 className="text-sm font-semibold text-stone-800">

          Queries ({row.query_runs?.length ?? row.query_ids?.length ?? 0})

        </h3>

        {(row.query_runs ?? []).map((run) => (

          <QueryRunRow key={run.query_id} run={run} serverSession={row.sessions?.server} />

        ))}

      </div>

    </section>

  )

}



export function ReviewPage() {

  const [batches, setBatches] = useState<QueryEvalBatchSummary[]>([])

  const [selectedBatchId, setSelectedBatchId] = useState('')

  const [batch, setBatch] = useState<QueryEvalBatch | null>(null)

  const [loading, setLoading] = useState(true)

  const [error, setError] = useState<string | null>(null)



  useEffect(() => {

    fetchQueryEvalBatches()

      .then(({ batches: rows }) => {

        const sorted = [...rows].sort((a, b) =>

          (b.generated_at || b.batch_id).localeCompare(a.generated_at || a.batch_id),

        )

        setBatches(sorted)

        const preferred = sorted.find((row) => row.batch_id.includes('pilot_v3')) ?? sorted[0]

        if (preferred) setSelectedBatchId(preferred.batch_id)

      })

      .catch((err: Error) => setError(err.message))

  }, [])



  useEffect(() => {

    if (!selectedBatchId) {

      setBatch(null)

      setLoading(false)

      return

    }

    let cancelled = false

    setLoading(true)

    setError(null)

    fetchQueryEvalBatch(selectedBatchId)

      .then((data) => {

        if (!cancelled) setBatch(data)

      })

      .catch((err: Error) => {

        if (!cancelled) setError(err.message || 'Failed to load batch')

      })

      .finally(() => {

        if (!cancelled) setLoading(false)

      })

    return () => {

      cancelled = true

    }

  }, [selectedBatchId])



  return (

    <div className="min-h-screen bg-stone-100">

      <header className="border-b border-stone-200 bg-white px-4 py-3">

        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-3">

          <div>

            <h1 className="text-xl font-semibold text-stone-900">Query evaluation review</h1>

            <p className="text-sm text-stone-500">

              Scores: Server · Ollama independent · Server+Ollama review · Claude independent

            </p>

          </div>

          <div className="flex flex-wrap items-center gap-3">

            <label className="flex items-center gap-2 text-sm text-stone-700">

              Batch

              <select

                className="max-w-xs rounded border border-stone-300 bg-white px-2 py-1"

                value={selectedBatchId}

                onChange={(e) => setSelectedBatchId(e.target.value)}

              >

                {batches.length === 0 ? <option value="">No batches</option> : null}

                {batches.map((row) => (

                  <option key={row.batch_id} value={row.batch_id}>

                    {row.batch_id}

                  </option>

                ))}

              </select>

            </label>

            <ExternalLink to="/triaging" className="text-sm text-amber-800 hover:underline">

              Triaging

            </ExternalLink>

            <ExternalLink to="/" className="text-sm text-amber-800 hover:underline">

              Home

            </ExternalLink>

            <ExternalLink to="/diagnose" className="text-sm text-amber-800 hover:underline">

              Diagnosis map

            </ExternalLink>

          </div>

        </div>

      </header>



      <main className="mx-auto max-w-[1400px] space-y-6 px-4 py-6">

        {error ? <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p> : null}

        {loading ? <p className="text-sm text-stone-500">Loading batch…</p> : null}

        {!loading && batch ? (

          <>

            <p className="text-sm text-stone-600">

              {batch.case_studies?.length ?? 0} case studies · generated {batch.generated_at ?? '—'}

            </p>

            <RubricLegend />

            <ProductionSystemSummaryTable batch={batch} />

            <PersonaSummaryTable batch={batch} />

            {(batch.case_studies ?? []).map((row) => (

              <CaseStudyCard key={`${row.case_study_id}-${row.mws_id}`} row={row} />

            ))}

          </>

        ) : null}

        {!loading && !batch && !error ? (

          <p className="text-sm text-stone-500">No evaluation batches yet.</p>

        ) : null}

      </main>



      <div className="mx-auto max-w-[1400px] px-4 pb-8">

        <CommandFooter

          title="Run / augment query evaluation"

          commands={[

            {

              label: 'Augment pilot v3 batch (repair links + re-eval)',

              command:

                '.\\.venv\\Scripts\\python.exe scripts/eval/augment_query_eval_batch.py --batch-id query_eval__pilot_v3_20260626T184910Z --force-re-eval',

            },

            {

              label: 'Append agriculture case study to pilot v3',

              command:

                '.\\.venv\\Scripts\\python.exe scripts/eval/run_query_eval.py --append --case-study-id 5 --query-id Q000 --query-id Q001 --query-id Q003 --query-id Q020 --batch-label pilot_v3',

            },

          ]}

        />

      </div>

    </div>

  )

}


