export type PathwayClassification = 'tp' | 'fp' | 'tn' | 'fn'

export const CLASSIFICATION_HEADER_STYLES: Record<PathwayClassification, string> = {
  tp: 'bg-emerald-100 text-emerald-900 border-emerald-200',
  fp: 'bg-amber-100 text-amber-900 border-amber-200',
  tn: 'bg-blue-100 text-blue-900 border-blue-200',
  fn: 'bg-red-100 text-red-900 border-red-200',
}

export const CLASSIFICATION_CHIP_STYLES: Record<PathwayClassification, string> = {
  tp: 'bg-emerald-100 text-emerald-900',
  fp: 'bg-amber-100 text-amber-900',
  tn: 'bg-blue-100 text-blue-900',
  fn: 'bg-red-100 text-red-900',
}

export const CLASSIFICATION_LABELS: Record<PathwayClassification, string> = {
  tp: 'true positive',
  fp: 'false positive',
  tn: 'true negative',
  fn: 'false negative',
}

export function classificationTitle(
  classification: PathwayClassification | undefined,
  mwsId: string,
  catalogLabel: string,
): string {
  const label = classification ? CLASSIFICATION_LABELS[classification] : 'unclassified'
  return `${mwsId} · catalog: ${catalogLabel} · ${label}`
}
