import { Fragment, useEffect, useMemo, useState } from 'react'
import type { DiagnosticSignal, EvaluateSectionResult, MissingVariableQuestion, TriageChangedFields, TriageSection } from '../api/triage'
import { diagnosisMwsUrl, pathwayLabel } from '../api/triage'
import { ExternalLink } from '../components/ExternalLink'
import {
  CLASSIFICATION_CHIP_STYLES,
  CLASSIFICATION_HEADER_STYLES,
  CLASSIFICATION_LABELS,
  type PathwayClassification,
  classificationTitle,
} from './pathwayClassification'
import {
  mcqQuestionForSignal,
  signalResultFromChoice,
  type MissingVariableQuestion as McqQuestion,
} from './mcqFollowUp'

const ALL_CLASSIFICATIONS: PathwayClassification[] = ['tp', 'fp', 'tn', 'fn']

function defaultClassificationFilter(): Set<PathwayClassification> {
  return new Set(ALL_CLASSIFICATIONS)
}

function filterMwsColumns(
  mwsColumns: MwsColumn[],
  selected: Set<PathwayClassification>,
): MwsColumn[] {
  if (!mwsColumns.length) return mwsColumns
  return mwsColumns.filter((mws) => !mws.classification || selected.has(mws.classification))
}

function toggleClassification(
  selected: Set<PathwayClassification>,
  key: PathwayClassification,
): Set<PathwayClassification> {
  const next = new Set(selected)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  return next
}

export type CardEditState = {
  card_id: string
  diagnostic_signals: DiagnosticSignal[]
  confirmation_policy: Record<string, unknown>
  missing_variable_questions?: MissingVariableQuestion[]
}

export type FollowUpChoicesByMws = Record<string, Record<string, string>>

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
  changedFields?: Record<string, TriageChangedFields>
  followUpChoices: FollowUpChoicesByMws
  onFollowUpChoiceChange: (mwsId: string, variable: string, choiceId: string) => void
  onEditChange: (cardId: string, edit: CardEditState) => void
}

function changedFieldClass(changed: boolean): string {
  return changed ? 'ring-2 ring-amber-400 ring-offset-1' : ''
}

function signalFieldChanged(
  changedFields: Record<string, TriageChangedFields> | undefined,
  cardId: string,
  signalId: string,
  field: 'expression' | 'direction' | 'active',
): boolean {
  const cardChanged = changedFields?.[cardId]
  if (!cardChanged) return false
  return (cardChanged.signals?.[signalId] || []).includes(field)
}

function policyChanged(changedFields: Record<string, TriageChangedFields> | undefined, cardId: string): boolean {
  return Boolean(changedFields?.[cardId]?.confirmation_policy)
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
  if (status === 'needs_llm' || status === 'no_expression' || status === 'name_error') return '?'
  if (status === 'user_provided' || status === 'user_provided_unresolved') return '?'
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

function McqDefinitionPanel({
  question,
  signalId,
  onQuestionChange,
}: {
  question: McqQuestion
  signalId: string
  onQuestionChange: (next: McqQuestion) => void
}) {
  return (
    <div className="space-y-2 rounded border border-amber-200 bg-amber-50/40 p-2">
      <div className="text-[9px] font-semibold uppercase tracking-wide text-amber-900">Follow-up MCQ</div>
      <textarea
        className="w-full rounded border border-stone-200 bg-white p-1 text-[10px] leading-tight"
        rows={3}
        value={question.question_to_user || ''}
        onChange={(event) => onQuestionChange({ ...question, question_to_user: event.target.value })}
      />
      <ul className="space-y-1">
        {(question.choices || []).map((choice, idx) => {
          const effect = (choice.effects?.signals || []).find((row) => row.signal_id === signalId)
          return (
            <li key={choice.id} className="rounded border border-stone-200 bg-white p-1">
              <input
                className="mb-1 w-full rounded border border-stone-100 p-0.5 font-mono text-[10px]"
                value={choice.label}
                onChange={(event) => {
                  const choices = [...(question.choices || [])]
                  choices[idx] = { ...choice, label: event.target.value }
                  onQuestionChange({ ...question, choices })
                }}
              />
              <div className="flex items-center justify-between gap-1 text-[9px] text-stone-500">
                <span className="font-mono">{choice.id}</span>
                <select
                  className="rounded border border-stone-200 p-0.5 text-[9px]"
                  value={effect?.result === false ? 'false' : effect?.result === true ? 'true' : ''}
                  onChange={(event) => {
                    const val = event.target.value
                    const choices = [...(question.choices || [])]
                    const signals = [...(choice.effects?.signals || [])].filter((row) => row.signal_id !== signalId)
                    if (val === 'true' || val === 'false') {
                      signals.push({ signal_id: signalId, result: val === 'true' })
                    }
                    choices[idx] = { ...choice, effects: { signals } }
                    onQuestionChange({ ...question, choices })
                  }}
                >
                  <option value="">— effect —</option>
                  <option value="true">T for signal</option>
                  <option value="false">F for signal</option>
                </select>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function PolicyTextarea({
  cardId,
  policy,
  onEditChange,
  edit,
  highlight = false,
}: {
  cardId: string
  policy: Record<string, unknown>
  edit: CardEditState
  onEditChange: (cardId: string, edit: CardEditState) => void
  highlight?: boolean
}) {
  const [draft, setDraft] = useState(() => JSON.stringify(policy || {}, null, 2))

  useEffect(() => {
    setDraft(JSON.stringify(policy || {}, null, 2))
  }, [cardId, policy])

  return (
    <textarea
      className={`w-full max-w-xl rounded border border-stone-200 p-1 font-mono text-[10px] ${changedFieldClass(highlight)}`}
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
  changedFields,
  followUpChoices,
  onFollowUpChoiceChange,
  onEditChange,
}: {
  group: PathwayGroup
  changedFields?: Record<string, TriageChangedFields>
  followUpChoices: FollowUpChoicesByMws
  onFollowUpChoiceChange: (mwsId: string, variable: string, choiceId: string) => void
  onEditChange: (cardId: string, edit: CardEditState) => void
}) {
  const [collapsed, setCollapsed] = useState(true)
  const [selectedClasses, setSelectedClasses] = useState(defaultClassificationFilter)
  const signalIds = mergedSignalIds(group.columns)
  const visibleColumns = useMemo(
    () =>
      group.columns.map((col) => ({
        ...col,
        mwsColumns: filterMwsColumns(col.mwsColumns, selectedClasses),
      })),
    [group.columns, selectedClasses],
  )
  const visibleMwsCount = visibleColumns.reduce((sum, col) => sum + col.mwsColumns.length, 0)

  return (
    <div className="overflow-auto overscroll-x-contain rounded-lg border border-stone-200 bg-white">
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
          <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-normal text-stone-600">
            <span className="text-stone-500">MWS:</span>
            {ALL_CLASSIFICATIONS.map((key) => {
              const active = selectedClasses.has(key)
              return (
                <label
                  key={key}
                  className={`inline-flex cursor-pointer items-center gap-1 rounded border px-1.5 py-0.5 ${
                    active ? CLASSIFICATION_CHIP_STYLES[key] : 'border-stone-200 bg-stone-50 text-stone-400'
                  }`}
                >
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={active}
                    onChange={() => setSelectedClasses((value) => toggleClassification(value, key))}
                  />
                  {key.toUpperCase()}
                  <span className="hidden sm:inline">({CLASSIFICATION_LABELS[key]})</span>
                </label>
              )
            })}
            {visibleMwsCount === 0 ? (
              <span className="text-amber-800">No MWS columns match the current filter.</span>
            ) : null}
          </div>
        ) : null}
      </div>
      {!collapsed ? (
      <table className="min-w-full border-collapse text-[11px]">
        <thead>
          <tr className="border-b border-stone-200 bg-amber-50/60">
            <th rowSpan={2} className="sticky left-0 z-20 min-w-[72px] border-r border-stone-200 bg-amber-50/60 px-2 py-1 text-left align-bottom">
              Signal
            </th>
            {visibleColumns.map((col) => (
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
            {visibleColumns.map((col) => (
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
                {visibleColumns.map((col) => {
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
                  const expr = signalExpression(signal)
                  const hasExpr = Boolean(expr.trim())
                  const mcqQuestion = mcqQuestionForSignal(
                    col.edit.missing_variable_questions,
                    signalId,
                    signal.variables || [],
                    hasExpr,
                  )
                  const isMcq = mcqQuestion !== null
                  return (
                    <Fragment key={`${col.cardId}-${signalId}`}>
                      <td rowSpan={2} className="border-l border-b border-stone-200 px-1 py-1 align-top">
                        {isMcq && mcqQuestion ? (
                          <McqDefinitionPanel
                            question={mcqQuestion}
                            signalId={signalId}
                            onQuestionChange={(next) => {
                              const questions = [...(col.edit.missing_variable_questions || [])]
                              const qIdx = questions.findIndex(
                                (item) => item.missing_variable === mcqQuestion.missing_variable,
                              )
                              if (qIdx >= 0) questions[qIdx] = next
                              else questions.push(next)
                              onEditChange(col.cardId, {
                                ...col.edit,
                                missing_variable_questions: questions,
                              })
                            }}
                          />
                        ) : (
                          <textarea
                            className={`w-full rounded border border-stone-200 p-1 font-mono text-[10px] leading-tight ${changedFieldClass(
                              signalFieldChanged(changedFields, col.cardId, signalId, 'expression'),
                            )}`}
                            rows={4}
                            value={expr}
                            title={
                              signalFieldChanged(changedFields, col.cardId, signalId, 'expression')
                                ? 'Saved patch changed this expression'
                                : undefined
                            }
                            onChange={(event) =>
                              updateSignal(col.edit, idx, { expression: event.target.value }, onEditChange)
                            }
                          />
                        )}
                      </td>
                      {col.mwsColumns.map((mws) => {
                        const evalSignal = mws.signals[signalId]
                        const choiceId =
                          isMcq && mcqQuestion
                            ? followUpChoices[mws.mws_id]?.[mcqQuestion.missing_variable]
                            : undefined
                        const preview =
                          isMcq && mcqQuestion
                            ? signalResultFromChoice(mcqQuestion, signalId, choiceId)
                            : null
                        const displayResult = evalSignal?.result ?? preview
                        const displayStatus = evalSignal?.status ?? (preview !== null ? 'user_provided' : undefined)
                        return (
                          <td
                            key={`${col.cardId}-${mws.mws_id}-${signalId}`}
                            className="border-l border-stone-100 px-1 py-1 align-top"
                          >
                            {isMcq && mcqQuestion ? (
                              <div className="space-y-1">
                                <select
                                  className="w-full max-w-[120px] rounded border border-stone-200 p-0.5 text-[9px]"
                                  value={choiceId || ''}
                                  onChange={(event) =>
                                    onFollowUpChoiceChange(
                                      mws.mws_id,
                                      mcqQuestion.missing_variable,
                                      event.target.value,
                                    )
                                  }
                                >
                                  <option value="">Select answer…</option>
                                  {(mcqQuestion.choices || []).map((choice) => (
                                    <option key={choice.id} value={choice.id}>
                                      {choice.label}
                                    </option>
                                  ))}
                                </select>
                                {displayResult !== null && displayResult !== undefined ? (
                                  <span
                                    className={`mx-auto block min-w-[1.25rem] rounded border px-1 py-0.5 text-center font-mono font-semibold ${resultTone(
                                      displayResult,
                                      displayStatus,
                                    )}`}
                                  >
                                    {resultChar(displayResult, displayStatus)}
                                  </span>
                                ) : (
                                  <span className="block text-center text-stone-300">—</span>
                                )}
                              </div>
                            ) : evalSignal ? (
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
                {visibleColumns.map((col) => {
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
                          className={`min-w-0 flex-1 max-w-[88px] rounded border border-stone-200 p-0.5 text-[9px] ${changedFieldClass(
                            signalFieldChanged(changedFields, col.cardId, signalId, 'direction'),
                          )}`}
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
                          className={`min-w-0 flex-1 max-w-[88px] rounded border border-stone-200 p-0.5 text-[9px] ${changedFieldClass(
                            signalFieldChanged(changedFields, col.cardId, signalId, 'active'),
                          )}`}
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
            {visibleColumns.map((col) => (
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
                  highlight={policyChanged(changedFields, col.cardId)}
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

export function SignalGrid({
  section,
  cardEdits,
  evalResult,
  changedFields,
  followUpChoices,
  onFollowUpChoiceChange,
  onEditChange,
}: Props) {
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
        <PathwaySignalTable
          key={group.pathwayId}
          group={group}
          changedFields={changedFields}
          followUpChoices={followUpChoices}
          onFollowUpChoiceChange={onFollowUpChoiceChange}
          onEditChange={onEditChange}
        />
      ))}
      {!evalResult ? (
        <p className="text-[11px] text-stone-500">Run Play to populate MWS signal cells.</p>
      ) : null}
    </div>
  )
}
