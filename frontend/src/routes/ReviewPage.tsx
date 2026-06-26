import { useEffect, useState } from 'react'

import { ExternalLink } from '../components/ExternalLink'

import { CommandFooter } from '../components/CommandFooter'

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



function CollapsedScores({ run }: { run: QueryRun }) {

  return (

    <div className="flex flex-wrap items-center gap-2">

      {EVAL_MODES.map((mode) => (

        <span key={mode} className="inline-flex items-center gap-1 rounded bg-stone-50 px-1.5 py-0.5">

          <span className="text-[10px] uppercase tracking-wide text-stone-500">{MODE_LABELS[mode]}</span>

          {scoreCell(run.evaluations[mode])}

        </span>

      ))}

    </div>

  )

}



function QueryRunRow({ run, serverSession }: { run: QueryRun; serverSession?: { feedback_url?: string } }) {

  const [open, setOpen] = useState(false)

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

          {!open ? <CollapsedScores run={run} /> : null}

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

                <th className="py-1 text-left font-medium">Summary</th>

              </tr>

            </thead>

            <tbody>

              {EVAL_MODES.map((mode) => {

                const ev = run.evaluations[mode]

                return (

                  <tr key={mode} className="align-top">

                    <td className="py-1 pr-3 text-stone-700">{MODE_LABELS[mode]}</td>

                    <td className="py-1 pr-3">{scoreCell(ev)}</td>

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



function personaLabel(persona: string): string {

  return persona.replace(/_/g, ' ')

}



function PersonaSummaryTable({ batch }: { batch: QueryEvalBatch }) {

  const byPersona = new Map<string, { modes: Record<string, number[]>; queryCount: number }>()

  for (const cs of batch.case_studies ?? []) {

    for (const run of cs.query_runs ?? []) {

      const persona = run.persona || 'unknown'

      const entry = byPersona.get(persona) ?? { modes: {}, queryCount: 0 }

      entry.queryCount += 1

      for (const mode of EVAL_MODES) {

        const score = run.evaluations?.[mode]?.weighted_total

        if (typeof score !== 'number' || run.evaluations?.[mode]?.error) continue

        const rows = entry.modes[mode] ?? []

        rows.push(score)

        entry.modes[mode] = rows

      }

      byPersona.set(persona, entry)

    }

  }

  const personas = [...byPersona.keys()].sort((a, b) => a.localeCompare(b))

  if (!personas.length) return null

  return (

    <section className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm">

      <h2 className="text-sm font-semibold text-stone-900">Score summary by persona</h2>

      <p className="mt-1 text-xs text-stone-500">Mean ± std dev of weighted rubric scores across queries in this batch.</p>

      <div className="mt-3 overflow-x-auto">

        <table className="w-full min-w-[32rem] text-sm">

          <thead>

            <tr className="border-b border-stone-200 text-left text-xs text-stone-500">

              <th className="py-2 pr-4 font-medium">Persona</th>

              {EVAL_MODES.map((mode) => (

                <th key={mode} className="py-2 pr-4 font-medium">

                  {MODE_LABELS[mode]}

                </th>

              ))}

              <th className="py-2 font-medium">Queries</th>

            </tr>

          </thead>

          <tbody>

            {personas.map((persona) => {

              const entry = byPersona.get(persona) ?? { modes: {}, queryCount: 0 }

              return (

                <tr key={persona} className="border-b border-stone-100 align-top">

                  <td className="py-2 pr-4 font-medium text-stone-800">{personaLabel(persona)}</td>

                  {EVAL_MODES.map((mode) => {

                    const stats = meanStd(entry.modes[mode] ?? [])

                    return (

                      <td key={mode} className="py-2 pr-4 font-mono text-xs text-stone-700">

                        {stats ? formatMeanStd(stats.mean, stats.std) : '—'}

                      </td>

                    )

                  })}

                  <td className="py-2 font-mono text-xs text-stone-600">{entry.queryCount || '—'}</td>

                </tr>

              )

            })}

          </tbody>

        </table>

      </div>

    </section>

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

              to={row.diagnostics_url}

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

        if (sorted.length) setSelectedBatchId(sorted[0].batch_id)

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

              label: 'Augment pilot batch (re-eval all modes)',

              command:

                '.\\.venv\\Scripts\\python.exe scripts/eval/augment_query_eval_batch.py --batch-id query_eval__pilot_v2_20260625T131416Z --force-re-eval',

            },

            {

              label: 'New pilot run',

              command:

                '.\\.venv\\Scripts\\python.exe scripts/eval/run_query_eval.py --case-study-id 5 --limit-queries 2 --batch-label pilot',

            },

          ]}

        />

      </div>

    </div>

  )

}


