export interface PanelHighlightFlags {
  dualAxis: boolean
  forestTrend: boolean
  deforestationPair: boolean
  lulcStacked: boolean
  croppingTrend: boolean
  droughtWeeks: boolean
  nregaBar: boolean
  distBars: boolean
  degradationSummary: boolean
}

export function panelHighlightFlags(updates: string[]): PanelHighlightFlags {
  const text = updates.join(' ').toLowerCase()
  return {
    dualAxis: text.includes('cropping_intensity') && text.includes('annual_delta_g_mm'),
    forestTrend: text.includes('lulc_tree_forest_ha'),
    deforestationPair: text.includes('cd_total_deforestation') || text.includes('cd_total_afforestation'),
    lulcStacked: text.includes('lulc_stacked'),
    croppingTrend: text.includes('cropping_intensity') && !text.includes('annual_delta_g_mm'),
    droughtWeeks: text.includes('drought_weeks'),
    nregaBar: text.includes('nrega'),
    distBars: text.includes('dist_'),
    degradationSummary: text.includes('cd_total_degradation'),
  }
}

export function hasPanelHighlights(flags: PanelHighlightFlags): boolean {
  return Object.values(flags).some(Boolean)
}
