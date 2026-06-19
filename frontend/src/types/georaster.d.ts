declare module 'georaster' {
  type GeoRaster = {
    getValuesAtPoint: (x: number, y: number) => number[]
  }
  export default function parseGeoraster(input: ArrayBuffer): Promise<GeoRaster>
}

declare module 'georaster-layer-for-leaflet' {
  import type { GridLayer } from 'leaflet'

  interface GeoRasterLayerOptions {
    georaster: unknown
    opacity?: number
    resolution?: number
    pixelValuesToColorFn?: (values: number[]) => string
  }

  export default class GeoRasterLayer extends GridLayer {
    constructor(options: GeoRasterLayerOptions)
    getBounds(): L.LatLngBounds
  }
}
