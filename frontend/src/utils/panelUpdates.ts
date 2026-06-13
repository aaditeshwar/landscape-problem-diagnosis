const ACTION_LABELS: Record<string, string> = {
  'cropping_intensity + annual_delta_g_mm dual_axis': 'Cropping intensity vs groundwater recharge (ΔG)',
  'annual_well_depth_m trend': 'Well depth trend',
  'annual_precipitation_mm + annual_delta_g_mm dual_axis': 'Rainfall vs groundwater recharge (ΔG)',
  'drought_weeks stacked_bar': 'Kharif drought-week breakdown',
  'annual_et_mm + annual_runoff_mm + annual_precipitation_mm stacked_area':
    'Water balance (ET, runoff, precipitation)',
  'lulc_stacked_area': 'Land-use class trends',
  'cd_total_degradation_ha sparkline': 'Cumulative cropping-area degradation',
  'nrega_land_restoration_count bar': 'NREGA land-restoration works',
  'lulc_tree_forest_ha trend': 'Tree/forest cover trend',
  'cd_total_deforestation_ha + cd_total_afforestation_ha paired_bar': 'Deforestation vs afforestation',
  'drought_weeks_* stacked_bar': 'Kharif drought-week breakdown',
  'dry_spell_weeks bar': 'Dry-spell weeks',
  'monsoon_onset_date scatter': 'Monsoon onset dates',
  'cropping_intensity trend': 'Cropping intensity trend',
  'dist_*_km horizontal_bars': 'Nearest facility distances',
  'nrega_*_count stacked_bar_cumulative': 'MGNREGA works by category',
}

export function panelUpdateActionLabel(key: string): string {
  return ACTION_LABELS[key] ?? key.replace(/_/g, ' ')
}

export function formatPanelUpdateActions(updates: string[]): string {
  if (updates.length === 0) {
    return 'Updated pathway ranking; no additional charts were highlighted.'
  }
  return updates.map((key) => panelUpdateActionLabel(key)).join('; ')
}

export function formatPanelUpdateActionList(updates: string[]): string[] {
  return updates.map((key) => panelUpdateActionLabel(key))
}
