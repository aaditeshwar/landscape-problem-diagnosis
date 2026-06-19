import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import { MapContainer, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import { fetchClusterRasterQuery, type ClusterPaletteEntry } from '../../api/signals'

interface Props {
  cogUrl: string | null
  viewerUrl?: string | null
  palette: ClusterPaletteEntry[]
  selectedSuffix: string | null
  onSelectSuffix: (suffix: string) => void
}

type GeoRasterLike = unknown

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function buildPopupHtml(entry: ClusterPaletteEntry | undefined, suffix: string): string {
  const cluster = entry?.cluster
  const label = cluster?.label ?? entry?.label ?? suffix
  const lines = [`<strong>${escapeHtml(suffix)}</strong> · ${escapeHtml(label)}`]
  if (cluster?.rainfall_regime) {
    lines.push(`Rainfall: ${escapeHtml(cluster.rainfall_regime)}`)
  }
  if (cluster?.aquifer_types?.length) {
    lines.push(`Aquifer: ${escapeHtml(cluster.aquifer_types.join(', '))}`)
  }
  if (cluster?.terrain_types?.length) {
    lines.push(`Terrain: ${escapeHtml(cluster.terrain_types.join(', '))}`)
  }
  if (cluster?.geographic_examples?.length) {
    lines.push(`Examples: ${escapeHtml(cluster.geographic_examples.slice(0, 3).join(', '))}`)
  }
  return `<div style="font-size:13px;line-height:1.45">${lines.join('<br/>')}</div>`
}

function ClusterRasterLayer({
  cogUrl,
  palette,
  onRasterReady,
}: {
  cogUrl: string
  palette: ClusterPaletteEntry[]
  onRasterReady: (ready: boolean) => void
}) {
  const map = useMap()

  useEffect(() => {
    let cancelled = false
    let layer: L.Layer | null = null
    onRasterReady(false)

    async function load() {
      try {
        const [parseGeoraster, GeoRasterLayer] = await Promise.all([
          import('georaster').then((module) => module.default),
          import('georaster-layer-for-leaflet').then((module) => module.default),
        ])
        const response = await fetch(cogUrl)
        if (!response.ok) throw new Error(`COG fetch failed (${response.status})`)
        const georaster = (await parseGeoraster(await response.arrayBuffer())) as GeoRasterLike
        if (cancelled) return

        onRasterReady(true)

        const colorByValue = new Map(palette.map((entry) => [entry.value, entry.color]))
        layer = new GeoRasterLayer({
          georaster,
          opacity: 0.78,
          resolution: 256,
          pixelValuesToColorFn(values: number[]) {
            const value = values?.[0]
            if (value == null || value <= 0) return 'transparent'
            return colorByValue.get(value) ?? '#78716c'
          },
        })
        layer.addTo(map)

        const disablePointerEvents = () => {
          const container = (layer as L.GridLayer).getContainer?.()
          if (container) {
            container.style.pointerEvents = 'none'
          }
        }
        layer.on('load', disablePointerEvents)
        disablePointerEvents()
        window.setTimeout(disablePointerEvents, 250)

        const bounds = (layer as { getBounds?: () => L.LatLngBounds }).getBounds?.()
        if (bounds?.isValid()) {
          map.fitBounds(bounds, { padding: [12, 12] })
          map.setZoom(map.getZoom() - 1)
        }
      } catch (error) {
        console.error('Failed to load cluster COG', error)
        if (!cancelled) onRasterReady(false)
      }
    }

    void load()

    return () => {
      cancelled = true
      onRasterReady(false)
      if (layer) {
        map.removeLayer(layer)
        layer = null
      }
    }
  }, [cogUrl, map, onRasterReady, palette])

  return null
}

function ClusterMapClickHandler({
  palette,
  onSelectSuffix,
}: {
  palette: ClusterPaletteEntry[]
  onSelectSuffix: (suffix: string) => void
}) {
  const map = useMap()
  const paletteRef = useRef(palette)
  const onSelectRef = useRef(onSelectSuffix)
  paletteRef.current = palette
  onSelectRef.current = onSelectSuffix

  useMapEvents({
    click: (event) => {
      void (async () => {
        try {
          const result = await fetchClusterRasterQuery(event.latlng.lat, event.latlng.lng)
          const suffix = result.cluster_suffix
          if (!suffix) return

          onSelectRef.current(suffix)
          const entry = paletteRef.current.find((item) => item.suffix === suffix)
          L.popup({ maxWidth: 300, className: 'cluster-map-popup' })
            .setLatLng(event.latlng)
            .setContent(buildPopupHtml(entry, suffix))
            .openOn(map)
        } catch (error) {
          console.warn('Cluster lookup failed for map click', error)
        }
      })()
    },
  })

  return null
}

export function ClusterMap({ cogUrl, viewerUrl, palette, selectedSuffix, onSelectSuffix }: Props) {
  const [rasterReady, setRasterReady] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const legendRefs = useRef<Record<string, HTMLButtonElement | null>>({})
  const handleRasterReady = useCallback((ready: boolean) => {
    setRasterReady(ready)
  }, [])
  const selectablePalette = useMemo(
    () => palette.filter((entry) => entry.suffix && entry.value > 0),
    [palette],
  )

  useEffect(() => {
    if (!cogUrl) {
      setLoadError('Cluster map URL is not configured.')
      return
    }
    setLoadError(null)
  }, [cogUrl])

  useEffect(() => {
    if (!selectedSuffix) return
    legendRefs.current[selectedSuffix]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [selectedSuffix])

  return (
    <div className="flex flex-col rounded-lg border border-stone-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-stone-200 px-3 py-2">
        <div>
          <h2 className="text-sm font-semibold text-stone-800">Context clusters</h2>
          <p className="text-xs text-stone-500">Click the map or choose a cluster below.</p>
        </div>
        {viewerUrl ? (
          <a
            href={viewerUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs font-medium text-amber-800 underline"
          >
            Open COG viewer
          </a>
        ) : null}
      </div>

      <div className="cluster-map-interactive relative h-[340px] shrink-0">
        {cogUrl ? (
          <MapContainer center={[20.5, 78.5]} zoom={5} className="h-full w-full" scrollWheelZoom>
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            <ClusterRasterLayer cogUrl={cogUrl} palette={palette} onRasterReady={handleRasterReady} />
            <ClusterMapClickHandler palette={palette} onSelectSuffix={onSelectSuffix} />
          </MapContainer>
        ) : (
          <div className="flex h-full items-center justify-center p-4 text-sm text-stone-500">{loadError}</div>
        )}
        {!rasterReady && cogUrl ? (
          <div className="pointer-events-none absolute inset-x-0 bottom-2 flex justify-center">
            <span className="rounded bg-white/90 px-2 py-1 text-xs text-stone-600 shadow-sm">
              Loading cluster raster…
            </span>
          </div>
        ) : null}
      </div>

      <div className="max-h-44 shrink-0 overflow-y-auto border-t border-stone-200 px-3 py-2">
        <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
          {selectablePalette.map((entry) => {
            const selected = entry.suffix === selectedSuffix
            return (
              <button
                key={entry.suffix}
                ref={(node) => {
                  if (entry.suffix) legendRefs.current[entry.suffix] = node
                }}
                type="button"
                onClick={() => entry.suffix && onSelectSuffix(entry.suffix)}
                className={`flex items-start gap-2 rounded px-2 py-1.5 text-left text-xs transition-colors ${
                  selected
                    ? 'bg-amber-100 ring-2 ring-amber-500 ring-offset-1'
                    : 'hover:bg-stone-50'
                }`}
              >
                <span
                  className="mt-0.5 inline-block h-3 w-3 shrink-0 rounded-sm border border-stone-300"
                  style={{ backgroundColor: entry.color }}
                />
                <span>
                  <span className="font-semibold text-stone-800">{entry.suffix}</span>
                  <span className="text-stone-600"> · {entry.cluster?.label ?? entry.label}</span>
                </span>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
