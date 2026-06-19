import type { ReactNode } from 'react'
import type { ConfirmationPolicy } from '../../api/signals'

function SignalChips({ ids }: { ids: string[] }) {
  if (!ids.length) return <span className="text-stone-400">—</span>
  return (
    <span className="inline-flex flex-wrap gap-1">
      {ids.map((id) => (
        <span
          key={id}
          className="inline-flex rounded bg-amber-100 px-1.5 py-0.5 font-mono text-[11px] font-medium text-amber-950"
        >
          {id}
        </span>
      ))}
    </span>
  )
}

function signalIdsFrom(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => String(item)).filter(Boolean)
}

function PolicyRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
      <span className="shrink-0 text-stone-500">{label}</span>
      <span className="min-w-0 flex-1">{children}</span>
    </div>
  )
}

export function ConfirmationPolicySummary({ policyJson }: { policyJson: string }) {
  const trimmed = policyJson.trim()
  if (!trimmed) {
    return <p className="mt-2 text-sm text-stone-400">No confirmation policy on this card.</p>
  }

  let policy: ConfirmationPolicy | null = null
  try {
    policy = JSON.parse(trimmed) as ConfirmationPolicy
  } catch {
    return <p className="mt-2 text-sm text-red-700">Invalid policy JSON — cannot display summary.</p>
  }

  const primary = policy.primary_confirm_signals ?? []
  const confirmWhen = (policy.confirm_when ?? {}) as Record<string, unknown>
  const minFromSet = confirmWhen.min_from_set as { signals?: string[]; min?: number } | undefined
  const minFromSignals = minFromSet?.signals ?? []
  const requiredAll = signalIdsFrom(confirmWhen.required_all)
  const requiredAny = Array.isArray(confirmWhen.required_any)
    ? (confirmWhen.required_any as unknown[][]).map((group) => signalIdsFrom(group))
    : []

  return (
    <div className="mt-2 space-y-2 rounded-lg border border-stone-100 bg-stone-50/80 p-3">
      <PolicyRow label="Version">
        <span className="font-medium text-stone-800">{policy.version ?? 1}</span>
      </PolicyRow>

      <PolicyRow label="Primary confirms">
        <SignalChips ids={primary} />
      </PolicyRow>

      {minFromSignals.length > 0 ? (
        <PolicyRow label={`Confirm when ≥${minFromSet?.min ?? '?'} of`}>
          <SignalChips ids={minFromSignals} />
        </PolicyRow>
      ) : null}

      {confirmWhen.min_confirms_true != null ? (
        <PolicyRow label="Min confirms TRUE">
          <span className="font-medium text-stone-800">{String(confirmWhen.min_confirms_true)}</span>
        </PolicyRow>
      ) : null}

      {requiredAll.length > 0 ? (
        <PolicyRow label="Required all">
          <SignalChips ids={requiredAll} />
        </PolicyRow>
      ) : null}

      {requiredAny.map((group, index) =>
        group.length > 0 ? (
          <PolicyRow key={index} label={`Required any group ${index + 1}`}>
            <SignalChips ids={group} />
          </PolicyRow>
        ) : null,
      )}

      {(policy.confidence_when ?? []).length > 0 ? (
        <div className="border-t border-stone-200 pt-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-stone-500">Confidence when</div>
          <ul className="mt-1 space-y-1.5">
            {(policy.confidence_when ?? []).map((rule, index) => {
              const row = rule as Record<string, unknown>
              const level = String(row.level ?? 'medium')
              const mfs = row.min_from_set as { signals?: string[]; min?: number } | undefined
              const mfsSignals = mfs?.signals ?? []
              const parts: ReactNode[] = []

              if (row.default) {
                parts.push(<span key="default">default</span>)
              }
              if (row.min_confirms_true != null) {
                parts.push(
                  <span key="min">
                    min confirms <strong>{String(row.min_confirms_true)}</strong>
                  </span>,
                )
              }
              if (mfsSignals.length > 0) {
                parts.push(
                  <span key="mfs" className="inline-flex flex-wrap items-center gap-1">
                    ≥{mfs?.min ?? '?'} of <SignalChips ids={mfsSignals} />
                  </span>,
                )
              }
              if (row.min_high_severity_confirms != null) {
                parts.push(
                  <span key="high">high-severity ≥{String(row.min_high_severity_confirms)}</span>,
                )
              }

              return (
                <li key={index} className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
                  <span className="rounded bg-stone-200 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-stone-700">
                    {level}
                  </span>
                  {parts.length ? (
                    <span className="inline-flex flex-wrap items-center gap-x-1 gap-y-1">{parts}</span>
                  ) : (
                    <span className="text-stone-400">—</span>
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
