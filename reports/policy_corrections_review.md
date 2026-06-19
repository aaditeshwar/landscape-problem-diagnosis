# Policy corrections review

Applied corrections to **4** card(s) across **4** fingerprint(s).

## `card:agriculture__water_scarcity__rainfed_risk__011`

- **Primary signals:** sig_01, sig_02, sig_03, sig_05
- **min_confirms_true:** 2
- **min_from_set:** `{"signals": ["sig_01", "sig_02", "sig_03", "sig_05"], "min": 2}`

**Draft note:**

> Pathway rainfed_risk confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (lulc_single_kharif_ha, lulc_double_crop_ha), sig_02 (cropping_intensity), sig_03 (canal_name, nrega_irrigation_count), sig_05 (swb_rabi_area_ha). Amplifying signals (do not alone confirm): sig_04 (runoff_mm, terrain_cluster_id). Follow-up variables for field evidence: irrigated_area_ha.

**Cards updated:**

- `agriculture__water_scarcity__rainfed_risk__011`

## `card:agriculture__water_scarcity__rainfed_risk__014`

- **Primary signals:** sig_01, sig_02, sig_03, sig_05
- **min_confirms_true:** 2
- **min_from_set:** `{"signals": ["sig_01", "sig_02", "sig_03", "sig_05"], "min": 2}`

**Draft note:**

> Pathway rainfed_risk confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (lulc_single_kharif_ha, lulc_double_crop_ha), sig_02 (cropping_intensity), sig_03 (canal_name, nrega_irrigation_count), sig_05 (swb_rabi_area_ha). Amplifying signals (do not alone confirm): sig_04 (runoff_mm, terrain_cluster_id). Follow-up variables for field evidence: irrigated_area_ha.

**Cards updated:**

- `agriculture__water_scarcity__rainfed_risk__014`

## `card:agriculture__water_scarcity__rainfed_risk__017`

- **Primary signals:** sig_01, sig_02, sig_03, sig_05
- **min_confirms_true:** 2
- **min_from_set:** `{"signals": ["sig_01", "sig_02", "sig_03", "sig_05"], "min": 2}`

**Draft note:**

> Pathway rainfed_risk confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (lulc_single_kharif_ha, lulc_double_crop_ha), sig_02 (cropping_intensity), sig_03 (canal_name, nrega_irrigation_count), sig_05 (swb_rabi_area_ha). Amplifying signals (do not alone confirm): sig_04 (runoff_mm, terrain_cluster_id). Follow-up variables for field evidence: irrigated_area_ha.

**Cards updated:**

- `agriculture__water_scarcity__rainfed_risk__017`

## `card:socio_economic__low_income__small_landholding__012`

- **Primary signals:** sig_01, sig_05
- **min_confirms_true:** 2
- **min_from_set:** `{"signals": ["sig_01", "sig_05"], "min": 2}`

**Draft note:**

> Pathway small_landholding confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (lulc_cropland_ha, village_total_population), sig_05 (landholding_size_distribution). Required: sig_01 (lulc_cropland_ha, village_total_population) must be TRUE. Amplifying signals (do not alone confirm): sig_02 (cropping_intensity), sig_03 (dist_apmc_km), sig_04 (organization_domains, nrega_community_assets_count), sig_07 (market_price_crop). Follow-up variables for field evidence: landholding_size_distribution, household_income_inr, market_price_crop.

**Cards updated:**

- `socio_economic__low_income__small_landholding__012`
