import { Fragment, useEffect, useMemo, useState } from 'react'
import type { DiagnosticSignal, EvaluateSectionResult, TriageSection } from '../api/triage'
import { diagnosisMwsUrl, pathwayLabel } from '../api/triage'
import { ExternalLink } from '../components/ExternalLink'
import {
  CLASSIFICATION_HEADER_STYLES,
  type PathwayClassification,
  classificationTitle,
} from './pathwayClassification'

export type CardEditState = {
  card_id: string
  diagnostic_signals: DiagnosticSignal[]
  confirmation_policy: Record<string, unknown>
}

type MwsColumn = {
  mws_id: string
  case_study_id: number
  state?: string
  district?: string
  tehsil?: string
  actual_pathway?: string
  actual_matches_pathway?: boolean
  classification?: PathwayClassification
  production_gated?: boolean
  signals: Record<
    string,
    {
      result?: unknown
      status?: unknown
      variable_values?: Array<{ access: string; formatted: string }>
    }
  >
}

type CardColumn = {
  pathwayId: string
  cardId: string
  clusterSuffix: string
  edit: CardEditState
  mwsColumns: MwsColumn[]
}

type PathwayGroup = {
  pathwayId: string
  columns: CardColumn[]
}

type Props = {
  section: TriageSection
  cardEdits: Record<string, CardEditState>
  evalResult: EvaluateSectionResult | null
  onEditChange: (cardId: string, edit: CardEditState) => void
}

function signalExpression(signal: DiagnosticSignal): string {
  return String(signal.condition?.expression || signal.expression || '')
}

function clusterSuffixFromCardId(cardId: string): string {
  const match = cardId.match(/__(\d{3})$/)
  return match?.[1] ?? '—'
}

function signalIdSort(a: string, b: string): number {
  const numA = Number.parseInt(a.replace(/\D/g, ''), 10)
  const numB = Number.parseInt(b.replace(/\D/g, ''), 10)
  if (!Number.isNaN(numA) && !Number.isNaN(numB) && numA !== numB) return numA - numB
  return a.localeCompare(b)
}

function resultChar(result: unknown, status?: unknown): string {
  if (result === true) return 'T'
  if (result === false) return 'F'
  if (status === 'needs_llm') return '?'
  return '—'
}

function resultTone(result: unknown, status?: unknown): string {
  if (result === true) return 'bg-emerald-100 text-emerald-900 border-emerald-200'
  if (result === false) return 'bg-red-100 text-red-900 border-red-200'
  if (status === 'needs_llm') return 'bg-amber-50 text-amber-900 border-amber-200'
  return 'bg-stone-50 text-stone-500 border-stone-200'
}

function signalHoverTitle(evalSignal: { variable_values?: Array<{ access: string; formatted: string }> } | undefined): string {
  const rows = evalSignal?.variable_values || []
  if (!rows.length) return ''
  return rows.map((row) => `${row.access}: ${row.formatted}`).join('\n')
}

function findSignal(edit: CardEditState, signalId: string): { signal: DiagnosticSignal; idx: number } | null {
  const idx = edit.diagnostic_signals.findIndex((item) => item.signal_id === signalId)
  if (idx < 0) return null
  return { signal: edit.diagnostic_signals[idx], idx }
}

function buildCardColumns(
  section: TriageSection,
  cardEdits: Record<string, CardEditState>,
  evalResult: EvaluateSectionResult | null,
): CardColumn[] {
  const grid = evalResult?.signal_grid
  if (grid?.pathways?.length) {
    const out: CardColumn[] = []
    for (const pathway of grid.pathways) {
      for (const card of pathway.cards) {
        const edit = cardEdits[card.card_id]
        if (!edit) continue
        out.push({
          pathwayId: pathway.pathway_id,
          cardId: card.card_id,
          clusterSuffix: clusterSuffixFromCardId(card.card_id),
          edit,
          mwsColumns: card.mws_columns,
        })
      }
    }
    return out
  }

  const out: CardColumn[] = []
  for (const pathway of section.predicted_pathways) {
    for (const cardId of Object.keys(cardEdits).sort()) {
      const edit = cardEdits[cardId]
      if (!edit || !cardId.includes(pathway)) continue
      out.push({
        pathwayId: pathway,
        cardId,
        clusterSuffix: clusterSuffixFromCardId(cardId),
        edit,
        mwsColumns: [],
      })
    }
  }
  return out
}

function groupByPathway(columns: CardColumn[]): PathwayGroup[] {
  const groups: PathwayGroup[] = []
  for (const col of columns) {
    const last = groups[groups.length - 1]
    if (last && last.pathwayId === col.pathwayId) {
      last.columns.push(col)
    } else {
      groups.push({ pathwayId: col.pathwayId, columns: [col] })
    }
  }
  return groups
}

function mergedSignalIds(columns: CardColumn[]): string[] {
  const ids = new Set<string>()
  for (const col of columns) {
    for (const signal of col.edit.diagnostic_signals) {
      if (signal.signal_id) ids.add(signal.signal_id)
    }
  }
  return [...ids].sort(signalIdSort)
}

function updateSignal(
  edit: CardEditState,
  signalIdx: number,
  patch: Partial<DiagnosticSignal> & { expression?: string },
  onEditChange: (cardId: string, edit: CardEditState) => void,
) {
  const nextSignals = edit.diagnostic_signals.map((item, i) => {
    if (i !== signalIdx) return item
    const next = { ...item, ...patch }
    if (patch.expression !== undefined) {
      next.condition = { ...(item.condition || {}), expression: patch.expression }
      delete (next as { expression?: string }).expression
    }
    return next
  })
  onEditChange(edit.card_id, { ...edit, diagnostic_signals: nextSignals })
}

function mwsHeaderTone(mws: MwsColumn): string {
  const classification = mws.classification
  if (classification) {
    return CLASSIFICATION_HEADER_STYLES[classification]
  }
  return 'bg-stone-100 text-stone-700 border-stone-200'
}

function PolicyTextarea({
  cardId,
  policy,
  onEditChange,
  edit,
}: {
  cardId: string
  policy: Record<string, unknown>
  edit: CardEditState
  onEditChange: (cardId: string, edit: CardEditState) => void
}) {
  const [draft, setDraft] = useState(() => JSON.stringify(policy || {}, null, 2))

  useEffect(() => {
    setDraft(JSON.stringify(policy || {}, null, 2))
  }, [cardId, policy])

  return (
    <textarea
      className="w-full max-w-xl rounded border border-stone-200 p-1 font-mono text-[10px]"
      rows={14}
      value={draft}
      onChange={(event) => {
        const next = event.target.value
        setDraft(next)
        try {
          const parsed = JSON.parse(next) as Record<string, unknown>
          onEditChange(cardId, { ...edit, confirmation_policy: parsed })
        } catch {
          /* allow invalid JSON while typing */
        }
      }}
    />
  )
}

function PathwaySignalTable({
  group,
  onEditChange,
}: {
  group: PathwayGroup
  onEditChange: (cardId: string, edit: CardEditState) => void
}) {
  const [collapsed, setCollapsed] = useState(false)
  const signalIds = mergedSignalIds(group.columns)

  return (
    <div className="overflow-auto rounded-lg border border-stone-200 bg-white">
      <div className="flex flex-wrap items-center gap-2 border-b border-stone-200 bg-stone-100 px-3 py-2">
        <button
          type="button"
          onClick={() => setCollapsed((value) => !value)}
          className="text-xs font-medium text-amber-900 hover:underline"
          aria-expanded={!collapsed}
        >
          {collapsed ? '▶' : '▼'}
        </button>
        <div className="text-sm font-semibold text-stone-800">{pathwayLabel(group.pathwayId)}</div>
        {!collapsed ? (
          <span className="text-[10px] font-normal text-stone-500">
            <span className="mr-1 inline-block rounded bg-emerald-100 px-1 text-emerald-900">green</span>
            TP
            <span className="mx-1 inline-block rounded bg-amber-100 px-1 text-amber-900">yellow</span>
            FP
            <span className="mx-1 inline-block rounded bg-blue-100 px-1 text-blue-900">blue</span>
            TN
            <span className="mx-1 inline-block rounded bg-red-100 px-1 text-red-900">red</span>
            FN
          </span>
        ) : null}
      </div>
      {!collapsed ? (
      <table className="min-w-full border-collapse text-[11px]">
        <thead>
          <tr className="border-b border-stone-200 bg-amber-50/60">
            <th rowSpan={2} className="sticky left-0 z-20 min-w-[72px] border-r border-stone-200 bg-amber-50/60 px-2 py-1 text-left align-bottom">
              Signal
            </th>
            {group.columns.map((col) => (
              <th
                key={`card-${col.cardId}`}
                colSpan={1 + col.mwsColumns.length}
                className="border-l border-stone-200 px-2 py-1 text-left"
              >
                <ExternalLink
                  to={`/revise-cards?card_id=${encodeURIComponent(col.cardId)}`}
                  className="font-mono text-[10px] text-amber-900 hover:underline"
                >
                  {col.cardId.split('__').slice(-2).join('__')}
                </ExternalLink>
                <span className="ml-1 text-stone-500">· {col.clusterSuffix}</span>
              </th>
            ))}
          </tr>
          <tr className="border-b border-stone-300 bg-stone-50">
            {group.columns.map((col) => (
              <Fragment key={`hdr-${col.cardId}`}>
                <th className="min-w-[220px] border-l border-stone-200 px-1 py-1 text-left font-normal text-stone-600">
                  Definition
                </th>
                {col.mwsColumns.map((mws) => (
                  <th
                    key={`${col.cardId}-${mws.mws_id}`}
                    className={`min-w-[52px] border border-stone-200 px-1 py-1 text-center font-normal ${mwsHeaderTone(mws)}`}
                    title={classificationTitle(
                      mws.classification,
                      mws.mws_id,
                      mws.actual_pathway || 'stress only',
                    )}
                  >
                    <div>#{mws.case_study_id}</div>
                    <ExternalLink
                      to={diagnosisMwsUrl(mws)}
                      className="text-[9px] hover:underline"
                    >
                      {mws.mws_id.slice(-6)}
                    </ExternalLink>
                    {mws.production_gated ? (
                      <div className="text-[8px] font-normal opacity-80" title="NTFP gate off in live diagnosis">
                        gated
                      </div>
                    ) : null}
                  </th>
                ))}
              </Fragment>
            ))}
          </tr>
        </thead>
        <tbody>
          {signalIds.map((signalId) => (
            <Fragment key={signalId}>
              <tr className="border-b border-stone-100 align-top">
                <td
                  rowSpan={2}
                  className="sticky left-0 z-10 border-r border-b border-stone-100 bg-white px-2 py-1 font-mono align-top"
                >
                  {signalId}
                </td>
                {group.columns.map((col) => {
                  const found = findSignal(col.edit, signalId)
                  if (!found) {
                    return (
                      <td
                        key={`${col.cardId}-${signalId}-empty`}
                        rowSpan={2}
                        colSpan={1 + col.mwsColumns.length}
                        className="border-l border-b border-stone-100 bg-stone-50/50"
                      />
                    )
                  }
                  const { signal, idx } = found
                  return (
                    <Fragment key={`${col.cardId}-${signalId}`}>
                      <td rowSpan={2} className="border-l border-b border-stone-200 px-1 py-1 align-top">
                        <textarea
                          className="w-full rounded border border-stone-200 p-1 font-mono text-[10px] leading-tight"
                          rows={4}
                          value={signalExpression(signal)}
                          onChange={(event) =>
                            updateSignal(col.edit, idx, { expression: event.target.value }, onEditChange)
                          }
                        />
                      </td>
                      {col.mwsColumns.map((mws) => {
                        const evalSignal = mws.signals[signalId]
                        return (
                          <td
                            key={`${col.cardId}-${mws.mws_id}-${signalId}`}
                            className="border-l border-stone-100 px-1 py-1 align-top"
                          >
                            {evalSignal ? (
                              <span
                                className={`mx-auto block min-w-[1.25rem] rounded border px-1 py-0.5 text-center font-mono font-semibold ${resultTone(
                                  evalSignal.result,
                                  evalSignal.status,
                                )}`}
                                title={signalHoverTitle(evalSignal)}
                              >
                                {resultChar(evalSignal.result, evalSignal.status)}
                              </span>
                            ) : (
                              <span className="block text-center text-stone-300">—</span>
                            )}
                          </td>
                        )
                      })}
                    </Fragment>
                  )
                })}
              </tr>
              <tr className="border-b border-stone-200 align-top">
                {group.columns.map((col) => {
                  const found = findSignal(col.edit, signalId)
                  if (!found) return null
                  const { signal, idx } = found
                  const span = Math.max(col.mwsColumns.length, 1)
                  return (
                    <td
                      key={`${col.cardId}-${signalId}-controls`}
                      colSpan={span}
                      className="border-l border-stone-100 px-1 py-1"
                    >
                      <div className="flex justify-center gap-1">
                        <select
                          className="min-w-0 flex-1 max-w-[88px] rounded border border-stone-200 p-0.5 text-[9px]"
                          value={signal.direction || 'confirms'}
                          onChange={(event) =>
                            updateSignal(col.edit, idx, { direction: event.target.value }, onEditChange)
                          }
                        >
                          <option value="confirms">confirms</option>
                          <option value="amplifies">amplifies</option>
                          <option value="rules_out">rules_out</option>
                        </select>
                        <select
                          className="min-w-0 flex-1 max-w-[88px] rounded border border-stone-200 p-0.5 text-[9px]"
                          value={signal.active !== false ? 'active' : 'inactive'}
                          onChange={(event) =>
                            updateSignal(
                              col.edit,
                              idx,
                              { active: event.target.value === 'active' },
                              onEditChange,
                            )
                          }
                        >
                          <option value="active">active</option>
                          <option value="inactive">inactive</option>
                        </select>
                      </div>
                    </td>
                  )
                })}
              </tr>
            </Fragment>
          ))}
          <tr className="border-b border-stone-200 align-top">
            <td className="sticky left-0 z-10 border-r border-stone-100 bg-white px-2 py-1 font-medium">
              policy
            </td>
            {group.columns.map((col) => (
              <td
                key={`policy-${col.cardId}`}
                colSpan={1 + col.mwsColumns.length}
                className="border-l border-stone-200 px-1 py-1"
              >
                <div className="mb-1 text-[9px] text-stone-400">{col.clusterSuffix}</div>
                <PolicyTextarea
                  cardId={col.cardId}
                  policy={col.edit.confirmation_policy || {}}
                  edit={col.edit}
                  onEditChange={onEditChange}
                />
              </td>
            ))}
          </tr>
        </tbody>
      </table>
      ) : null}
    </div>
  )
}

export function SignalGrid({ section, cardEdits, evalResult, onEditChange }: Props) {
  const cardColumns = useMemo(
    () => buildCardColumns(section, cardEdits, evalResult),
    [section, cardEdits, evalResult],
  )

  const pathwayGroups = useMemo(() => groupByPathway(cardColumns), [cardColumns])

  if (!pathwayGroups.length) {
    return <p className="text-sm text-stone-500">No signal columns for this section yet.</p>
  }

  return (
    <div className="space-y-4">
      {pathwayGroups.map((group) => (
        <PathwaySignalTable key={group.pathwayId} group={group} onEditChange={onEditChange} />
      ))}
      {!evalResult ? (
        <p className="text-[11px] text-stone-500">Run Play to populate MWS signal cells.</p>
      ) : null}
    </div>
  )
}
