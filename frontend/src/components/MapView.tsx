import { useEffect, useMemo } from 'react'
import { GeoJSON, MapContainer, TileLayer, useMap } from 'react-leaflet'
import type { Layer, PathOptions } from 'leaflet'
import L from 'leaflet'
import type { FeatureCollection, MwsFeatureCollection, TehsilFeatureCollection, TehsilProperties, TehsilRef } from '../types'

interface Props {
  tehsils: TehsilFeatureCollection | null
  mwsBoundaries: MwsFeatureCollection | null
  villageBoundaries: FeatureCollection | null
  selectedTehsil: TehsilRef | null
  selectedMwsUid: string | null
  mwsHighlightEpoch?: number
  showVillages: boolean
  flyTarget: { lat: number; lon: number; zoom?: number; seq: number } | null
  onFlyComplete?: () => void
  onTehsilSelect: (ref: TehsilRef) => void
  onMwsSelect: (uid: string) => void
}

function tehsilLayerKey(ref: TehsilRef | null): string {
  if (!ref) return 'none'
  return `${ref.state}__${ref.district}__${ref.tehsil}`
}

function matchesTehsil(props: Record<string, unknown>, ref: TehsilRef): boolean {
  return props.state === ref.state && props.district === ref.district && props.tehsil === ref.tehsil
}

function FitBounds({ data, layerKey }: { data: GeoJSON.GeoJsonObject | null; layerKey: string }) {
  const map = useMap()
  useEffect(() => {
    if (!data) return
    const layer = L.geoJSON(data)
    const bounds = layer.getBounds()
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [24, 24] })
  }, [data, layerKey, map])
  return null
}

function FlyToTarget({
  target,
  onComplete,
}: {
  target: { lat: number; lon: number; zoom?: number; seq: number } | null
  onComplete?: () => void
}) {
  const map = useMap()
  useEffect(() => {
    if (!target) return
    map.flyTo([target.lat, target.lon], target.zoom ?? 11, { duration: 1.2 })
    const timer = window.setTimeout(() => onComplete?.(), 1300)
    return () => window.clearTimeout(timer)
  }, [target?.seq, map, onComplete, target])
  return null
}

export function MapView({
  tehsils,
  mwsBoundaries,
  villageBoundaries,
  selectedTehsil,
  selectedMwsUid,
  mwsHighlightEpoch = 0,
  showVillages,
  flyTarget,
  onFlyComplete,
  onTehsilSelect,
  onMwsSelect,
}: Props) {
  const activeTehsilKey = tehsilLayerKey(selectedTehsil)

  const visibleMws = useMemo((): MwsFeatureCollection | null => {
    if (!mwsBoundaries || !selectedTehsil) return null
    const features = mwsBoundaries.features.filter((feature) =>
      matchesTehsil(feature.properties as Record<string, unknown>, selectedTehsil),
    )
    if (features.length === 0) return null
    return { type: 'FeatureCollection', features }
  }, [mwsBoundaries, selectedTehsil])

  const visibleVillages = useMemo((): FeatureCollection | null => {
    if (!villageBoundaries || !selectedTehsil) return null
    const features = villageBoundaries.features.filter((feature) =>
      matchesTehsil(feature.properties as Record<string, unknown>, selectedTehsil),
    )
    if (features.length === 0) return null
    return { type: 'FeatureCollection', features }
  }, [villageBoundaries, selectedTehsil])

  const tehsilStyle = useMemo(
    () =>
      (feature?: GeoJSON.Feature): PathOptions => {
        const props = feature?.properties as TehsilProperties | undefined
        const active =
          selectedTehsil &&
          props?.state === selectedTehsil.state &&
          props?.district === selectedTehsil.district &&
          props?.tehsil === selectedTehsil.tehsil
        return active
          ? {
              color: '#ffffff',
              weight: 3,
              fillColor: '#d946ef',
              fillOpacity: 0.28,
            }
          : {
              color: '#f5f3ff',
              weight: 1.5,
              fillColor: '#7c3aed',
              fillOpacity: 0.14,
            }
      },
    [selectedTehsil],
  )

  const mwsStyle = useMemo(
    () =>
      (feature?: GeoJSON.Feature): PathOptions => {
        const uid = feature?.properties?.uid as string | undefined
        const selected = uid && uid === selectedMwsUid
        return selected
          ? {
              color: '#ffffff',
              weight: 2.5,
              fillColor: '#ec4899',
              fillOpacity: 0.45,
            }
          : {
              color: '#22d3ee',
              weight: 1.2,
              fillColor: '#0891b2',
              fillOpacity: 0.24,
            }
      },
    [selectedMwsUid],
  )

  function bindTehsilEvents(feature: GeoJSON.Feature, layer: Layer) {
    const props = feature.properties as TehsilProperties
    layer.bindTooltip(`${props.tehsil}, ${props.district}`, { sticky: true })
    layer.on('click', (e) => {
      L.DomEvent.stopPropagation(e)
      onTehsilSelect(props)
    })
  }

  function bindMwsEvents(feature: GeoJSON.Feature, layer: Layer) {
    const uid = feature.properties?.uid as string
    layer.bindTooltip(uid, { sticky: true })
    layer.on('click', (e) => {
      L.DomEvent.stopPropagation(e)
      onMwsSelect(uid)
    })
  }

  return (
    <MapContainer center={[20.5, 78.5]} zoom={6} className="h-full w-full" scrollWheelZoom>
      <TileLayer
        attribution='&copy; Google'
        url="https://mt{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"
        subdomains={['0', '1', '2', '3']}
        maxZoom={20}
      />
      {tehsils && (
        <GeoJSON
          key="tehsils"
          data={tehsils}
          style={tehsilStyle}
          onEachFeature={bindTehsilEvents}
        />
      )}
      {showVillages && visibleVillages && (
        <GeoJSON
          key={`villages-${activeTehsilKey}`}
          data={visibleVillages}
          style={{ color: '#fdf4ff', weight: 0.8, fillColor: '#a78bfa', fillOpacity: 0.12 }}
          interactive={false}
        />
      )}
      {visibleMws && (
        <GeoJSON
          key={`mws-${activeTehsilKey}-${selectedMwsUid ?? 'none'}-${mwsHighlightEpoch}`}
          data={visibleMws}
          style={mwsStyle}
          onEachFeature={bindMwsEvents}
        />
      )}
      {!flyTarget && <FitBounds data={visibleMws} layerKey={activeTehsilKey} />}
      <FlyToTarget target={flyTarget} onComplete={onFlyComplete} />
    </MapContainer>
  )
}
