export interface TehsilProperties {
  state: string
  district: string
  tehsil: string
  mws_count?: number
}

export interface GeoFeature<P = Record<string, unknown>> {
  type: 'Feature'
  properties: P
  geometry: GeoJSON.Geometry
}

export interface FeatureCollection<P = Record<string, unknown>> {
  type: 'FeatureCollection'
  features: GeoFeature<P>[]
}

export type TehsilFeatureCollection = FeatureCollection<TehsilProperties>

export type MwsFeatureCollection = FeatureCollection<{
  uid: string
  state: string
  district: string
  tehsil: string
}>

export interface TehsilRef {
  state: string
  district: string
  tehsil: string
}

export interface IngestedTehsil {
  id: string
  mws_count?: number
  village_count?: number
}

export interface LocateResult {
  lon: number
  lat: number
  found: boolean
  mws_uid?: string
  village_id?: number
  state?: string
  district?: string
  tehsil?: string
}

export interface PathwayResult {
  pathway_id: string
  confidence: string
  reasoning?: string
  missing_variable_questions?: Array<{ variable: string; question: string }>
}

export interface PathwayChange {
  pathway_id: string
  from: string
  to: string
  reason: string
}

export interface DiagnosisRevision {
  improved: boolean
  summary: string | null
  pathway_changes: PathwayChange[]
}

export interface DiagnosisResponse {
  session_id: string
  confirmed_pathways: PathwayResult[]
  uncertain_pathways: PathwayResult[]
  solutions: string[]
  panel_updates: string[]
  panel_update_explanation?: string | null
  follow_up_question?: string | null
  diagnosis_revision?: DiagnosisRevision | null
  pathway_retrieval_ranks?: Record<string, number>
}

export interface FollowUpExchange {
  question: string
  answer: string
  actions: string[]
  explanation?: string | null
  variable?: string
  revision?: DiagnosisRevision | null
}

export interface MwsDocument {
  uid: string
  state: string
  district: string
  tehsil: string
  area_ha?: number
  aquifer?: {
    raw_class?: string
    acwadam_class?: string
    lithology_percent?: Record<string, number>
  }
  terrain?: {
    cluster_id?: number
    description?: string
    plain_percent?: number
    slopy_percent?: number
  }
  soge?: {
    dev_percent?: number
    class_name?: string
  }
  river_name?: string | null
  canal?: { canal_name?: string; project_name?: string } | null
  hydrological_annual?: Record<
    string,
    {
      precipitation_mm?: number
      delta_g_mm?: number
      well_depth_m?: number
      et_mm?: number
      runoff_mm?: number
    }
  >
  cropping_intensity?: Record<
    string,
    | number
    | {
        cropping_intensity?: number
        single_crop_ha?: number
        double_crop_ha?: number
        triple_crop_ha?: number
      }
  >
  drought_kharif?: Record<
    string,
    {
      no_drought_weeks?: number
      mild_weeks?: number
      moderate_weeks?: number
      severe_weeks?: number
      dry_spell_weeks?: number
    }
  >
  swb_annual?: Record<
    string,
    { total_ha?: number; kharif_ha?: number; rabi_ha?: number; zaid_ha?: number }
  >
  lulc_ha?: Record<string, Record<string, number>>
  change_detection?: Record<string, Record<string, number>>
  intersect_villages?: {
    village_ids?: number[]
    details?: Record<string, { area_intersect?: number; percentage_of_area?: number }>
  }
  intersect_village_names?: Array<{
    village_id: number
    name?: string
    population?: number
    sc_percent?: number
    st_percent?: number
    literacy_rate_percent?: number
    area_intersect_ha?: number
    percent_of_mws?: number
  }>
  village_aggregates?: Record<string, number>
  facility_distances?: {
    dist_apmc_km?: number
    dist_bank_km?: number
    dist_dairy_km?: number
    dist_phc_km?: number
    dist_chc_km?: number
    dist_sub_centre_km?: number
    dist_district_hospital_km?: number
    dist_school_primary_km?: number
    dist_school_secondary_km?: number
    dist_college_km?: number
    dist_csc_km?: number
    dist_pds_km?: number
    dist_cooperative_km?: number
    dist_markets_trading_km?: number
    dist_storage_warehousing_km?: number
    dist_agri_processing_km?: number
  }
  facility_distance_table?: Array<{ facility: string; distance_km: number }>
  nrega_mws?: Record<string, Record<string, number>>
}
