export type JsonDiffRow = {
  kind: 'same' | 'remove' | 'add' | 'change'
  left?: string
  right?: string
}

export function formatJson(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string') {
    try {
      return JSON.stringify(JSON.parse(value), null, 2)
    } catch {
      return value
    }
  }
  return JSON.stringify(value, null, 2)
}

function lcsTable(left: string[], right: string[]): number[][] {
  const rows = left.length + 1
  const cols = right.length + 1
  const table = Array.from({ length: rows }, () => Array<number>(cols).fill(0))
  for (let i = 1; i < rows; i += 1) {
    for (let j = 1; j < cols; j += 1) {
      if (left[i - 1] === right[j - 1]) {
        table[i][j] = table[i - 1][j - 1] + 1
      } else {
        table[i][j] = Math.max(table[i - 1][j], table[i][j - 1])
      }
    }
  }
  return table
}

export function diffJsonLines(leftText: string, rightText: string): JsonDiffRow[] {
  const leftLines = leftText.split('\n')
  const rightLines = rightText.split('\n')
  const table = lcsTable(leftLines, rightLines)
  const rows: JsonDiffRow[] = []
  let i = leftLines.length
  let j = rightLines.length

  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && leftLines[i - 1] === rightLines[j - 1]) {
      rows.unshift({ kind: 'same', left: leftLines[i - 1], right: rightLines[j - 1] })
      i -= 1
      j -= 1
    } else if (j > 0 && (i === 0 || table[i][j - 1] >= table[i - 1][j])) {
      rows.unshift({ kind: 'add', right: rightLines[j - 1] })
      j -= 1
    } else if (i > 0) {
      rows.unshift({ kind: 'remove', left: leftLines[i - 1] })
      i -= 1
    }
  }

  const merged: JsonDiffRow[] = []
  for (const row of rows) {
    const prev = merged[merged.length - 1]
    if (prev?.kind === 'remove' && row.kind === 'add') {
      merged[merged.length - 1] = { kind: 'change', left: prev.left, right: row.right }
      continue
    }
    merged.push(row)
  }
  return merged
}

export function resolvePolicyObject(
  value: unknown,
  rawCard: Record<string, unknown> | null | undefined,
): unknown {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const obj = value as Record<string, unknown>
    if (obj.confirmation_policy && typeof obj.confirmation_policy === 'object') {
      return obj.confirmation_policy
    }
    if (obj.confirmation_policy_alternative && typeof obj.confirmation_policy_alternative === 'object') {
      return obj.confirmation_policy_alternative
    }
    if ('version' in obj || 'confirm_when' in obj || 'primary_confirm_signals' in obj) {
      return obj
    }
  }
  if (rawCard?.confirmation_policy) return rawCard.confirmation_policy
  return value
}

export function hasActionablePolicyPatch(suggested: Record<string, unknown> | null | undefined): boolean {
  if (!suggested) return false
  if (suggested.confirmation_policy && typeof suggested.confirmation_policy === 'object') return true
  if (suggested.confirmation_policy_alternative && typeof suggested.confirmation_policy_alternative === 'object') {
    return true
  }
  return Boolean(
    suggested.overall_reasoning_note
    || suggested.overall_reasoning_note_edit
    || ('version' in suggested && 'confirm_when' in suggested),
  )
}

export function isPolicyFinding(fieldPath: string, dimension: string): boolean {
  return fieldPath.startsWith('confirmation_policy') || dimension.includes('confirmation_policy')
}
