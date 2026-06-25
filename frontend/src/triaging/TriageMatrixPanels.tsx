import {
  NONE_OF_THESE,
  diagnosisMwsUrl,
  type EvaluateSectionResult,
  pathwayLabel,
} from '../api/triage'
import { ExternalLink } from '../components/ExternalLink'
import {
  CLASSIFICATION_CHIP_STYLES,
  type PathwayClassification,
  classificationTitle,
} from './pathwayClassification'

type Props = {
  matrixColumns: string[]
  evalResult: EvaluateSectionResult | null
}

function cellInstances(
  evalResult: EvaluateSectionResult | null,
  rowPathway: string,
  predicted: string,
) {
  if (!evalResult) return []
  return evalResult.matrix.cells.filter((cell) => {
    const row = cell.matrix_row_pathway ?? cell.actual_pathway
    return row === rowPathway && cell.predicted_pathway === predicted
  })
}

function mwsShort(mwsId: string) {
  const parts = mwsId.split('_')
  return parts[parts.length - 1] || mwsId
}

function chipStyle(classification: PathwayClassification | undefined) {
  if (!classification) return 'bg-stone-100 text-stone-700'
  return CLASSIFICATION_CHIP_STYLES[classification]
}

export function ConfusionMatrix({ matrixColumns, evalResult }: Props) {
  const rowPathways = evalResult?.matrix.row_pathways ?? matrixColumns
  const predictedCols = [...matrixColumns, NONE_OF_THESE]

  return (
    <div className="overflow-auto overscroll-x-contain rounded-lg border border-stone-200 bg-white">
      <div className="border-b border-stone-100 px-2 py-1 text-[10px] text-stone-600">
        Each row is a one-vs-rest classifier for that pathway (all section MWS). Green=TP, yellow=FP,
        blue=TN, red=FN.
      </div>
      <table className="w-full text-[11px]">
        <thead>
          <tr className="border-b border-stone-200 bg-stone-50">
            <th className="px-1.5 py-1.5 text-left font-medium text-stone-600">Pathway ↓ / Pred →</th>
            {predictedCols.map((col) => (
              <th key={col} className="px-1.5 py-1.5 text-left font-medium text-stone-700">
                {pathwayLabel(col)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rowPathways.map((row) => (
            <tr key={row} className="border-b border-stone-100">
              <td className="px-1.5 py-1.5 font-medium text-stone-700">{pathwayLabel(row)}</td>
              {predictedCols.map((col) => {
                const isActiveCol = col === row || col === NONE_OF_THESE
                const items = isActiveCol ? cellInstances(evalResult, row, col) : []
                return (
                  <td
                    key={col}
                    className={`align-top px-1.5 py-1.5 ${isActiveCol ? '' : 'bg-stone-50/40'}`}
                  >
                    <div className="flex flex-wrap gap-0.5">
                      {items.map((item) => {
                        const inst = item.instance
                        const classification = item.classification as PathwayClassification | undefined
                        const chipKey = `${inst.case_study_id}-${inst.mws_id}-${row}-${col}`
                        return (
                          <span
                            key={chipKey}
                            className={`inline-flex rounded px-1 py-0.5 text-[10px] ${chipStyle(classification)}`}
                            title={classificationTitle(
                              classification,
                              inst.mws_id,
                              inst.catalog_pathway || '—',
                            )}
                          >
                            #{inst.case_study_id}·{mwsShort(inst.mws_id)}
                          </span>
                        )
                      })}
                    </div>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {!evalResult ? (
        <p className="border-t border-stone-100 px-2 py-1.5 text-[11px] text-stone-500">Run Play to populate matrix.</p>
      ) : null}
    </div>
  )
}

export function VariableTable({
  evalResult,
  instances,
}: {
  evalResult: EvaluateSectionResult | null
  instances: Array<{ case_study_id: number; mws_id: string; state?: string; district?: string; tehsil?: string }>
}) {
  const table = evalResult?.variable_table
  if (!table) {
    return (
      <div className="rounded-lg border border-stone-200 bg-white p-3 text-xs text-stone-500">
        Variable values appear after Play.
      </div>
    )
  }

  const columnByMws = new Map(table.columns.map((col) => [col.mws_id, col]))

  return (
    <div className="overflow-auto overscroll-x-contain rounded-lg border border-stone-200 bg-white">
      <table className="min-w-full text-xs">
        <thead>
          <tr className="border-b border-stone-200 bg-stone-50">
            <th className="sticky left-0 z-20 min-w-[140px] border-r border-stone-200 bg-stone-50 px-2 py-2 text-left">
              Variable
            </th>
            {instances.map((inst) => (
              <th key={inst.mws_id} className="px-2 py-2 text-left">
                <div>#{inst.case_study_id}</div>
                <ExternalLink to={diagnosisMwsUrl(inst)} className="text-amber-800 hover:underline">
                  {inst.mws_id}
                </ExternalLink>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr className="border-b border-stone-100">
            <td className="sticky left-0 z-10 border-r border-stone-100 bg-white px-2 py-1 font-medium text-stone-600">
              Card
            </td>
            {instances.map((inst) => {
              const col = columnByMws.get(inst.mws_id)
              return (
                <td key={`card-${inst.mws_id}`} className="px-2 py-1">
                  {col?.card_id ? (
                    <ExternalLink
                      to={`/revise-cards?card_id=${encodeURIComponent(col.card_id)}`}
                      className="text-amber-800 hover:underline"
                    >
                      {col.card_id.split('__').slice(-2).join('__')}
                    </ExternalLink>
                  ) : (
                    '—'
                  )}
                </td>
              )
            })}
          </tr>
          {table.rows.map((row) => (
            <tr key={row.access} className="border-b border-stone-100">
              <td className="sticky left-0 z-10 border-r border-stone-100 bg-white px-2 py-1 font-mono text-[11px] text-stone-700">
                {row.access}
              </td>
              {instances.map((inst) => {
                const val =
                  row.values.find((item) => item.mws_id === inst.mws_id) ||
                  row.values.find((item) => item.case_study_id === inst.case_study_id)
                return (
                  <td key={`${row.access}-${inst.mws_id}`} className="px-2 py-1 font-mono text-[11px]">
                    {val?.formatted ?? '—'}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
