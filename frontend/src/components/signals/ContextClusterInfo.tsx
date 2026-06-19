import type { ContextCluster } from '../../api/signals'

interface Props {
  cluster: ContextCluster | null
  suffix: string | null
}

function ChipList({ label, values }: { label: string; values?: string[] }) {
  if (!values?.length) return null
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-wide text-stone-500">{label}</div>
      <p className="mt-1 text-sm text-stone-700">{values.join(', ')}</p>
    </div>
  )
}

export function ContextClusterInfo({ cluster, suffix }: Props) {
  if (!suffix) {
    return (
      <section className="rounded-lg border border-dashed border-stone-300 bg-stone-50/80 p-4 text-sm text-stone-500">
        Select a context cluster to view its metadata.
      </section>
    )
  }

  if (!cluster) {
    return (
      <section className="rounded-lg border border-stone-200 bg-white p-4 text-sm text-stone-600">
        Cluster <span className="font-medium">{suffix}</span> metadata is not available.
      </section>
    )
  }

  return (
    <section className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-stone-800">
        Cluster {suffix} · {cluster.label}
      </h3>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <ChipList label="Aquifer types" values={cluster.aquifer_types} />
        <ChipList label="AER tags" values={cluster.aer_tags} />
        <ChipList label="Rainfall regime" values={cluster.rainfall_regime ? [cluster.rainfall_regime] : undefined} />
        <ChipList label="Terrain" values={cluster.terrain_types} />
        <ChipList label="Examples" values={cluster.geographic_examples} />
      </div>
    </section>
  )
}
