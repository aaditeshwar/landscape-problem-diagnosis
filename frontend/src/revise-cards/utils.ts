export function severityClasses(severity: string, overall?: string): {
  panel: string
  badge: string
  label: string
} {
  const level = severity === 'error' || overall === 'fail'
    ? 'error'
    : severity === 'warn' || overall === 'warn'
      ? 'warn'
      : severity === 'info'
        ? 'info'
        : overall === 'pass'
          ? 'pass'
          : 'pending'

  switch (level) {
    case 'error':
      return {
        panel: 'bg-red-50 border-red-300',
        badge: 'bg-red-100 text-red-900 border-red-200',
        label: 'Error',
      }
    case 'warn':
      return {
        panel: 'bg-amber-50 border-amber-300',
        badge: 'bg-amber-100 text-amber-900 border-amber-200',
        label: 'Warning',
      }
    case 'info':
      return {
        panel: 'bg-sky-50 border-sky-200',
        badge: 'bg-sky-100 text-sky-900 border-sky-200',
        label: 'Info',
      }
    case 'pass':
      return {
        panel: 'bg-emerald-50 border-emerald-300',
        badge: 'bg-emerald-100 text-emerald-900 border-emerald-200',
        label: 'Pass',
      }
    default:
      return {
        panel: 'bg-stone-50 border-stone-300',
        badge: 'bg-stone-100 text-stone-800 border-stone-200',
        label: 'Pending',
      }
  }
}

/** Sidebar row background when selected — deeper hue by overall score. */
export function sidebarActiveClasses(overallScore: string): string {
  switch (overallScore) {
    case 'pass':
      return 'border-l-emerald-700 bg-emerald-200/90 shadow-sm ring-1 ring-inset ring-emerald-400/50'
    case 'warn':
      return 'border-l-amber-700 bg-amber-200/90 shadow-sm ring-1 ring-inset ring-amber-500/40'
    case 'fail':
      return 'border-l-red-700 bg-red-200/90 shadow-sm ring-1 ring-inset ring-red-400/50'
    default:
      return 'border-l-stone-700 bg-stone-200 shadow-sm ring-1 ring-inset ring-stone-400/50'
  }
}

export function dimensionLabel(dimension: string): string {
  return dimension.replace(/^D\d_/, '').replace(/_/g, ' ')
}

export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}

export function patchesEqual(a: Record<string, unknown> | null, b: Record<string, unknown> | null): boolean {
  return JSON.stringify(a ?? {}) === JSON.stringify(b ?? {})
}
