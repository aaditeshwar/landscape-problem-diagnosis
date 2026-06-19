# Policy fixes for your review

Applied **46 card updates** via `metadata/policy_corrections.json`.
Old fingerprints changed; search the updated `review_unique_policies.csv` by **example card**.

## Summary by your issue list

| Issue | Fix applied |
|-------|-------------|
| 1 (missing min_from_set) | All listed rows now have `min_from_set` when primary set has 2+ signals |
| 2 (draft note incomplete) | `draft_reasoning_note_from_policy` now lists all signals in min_from_set |
| 3 (6b4cc36f, 7203d24bf55d2cc9) | GW Indo-Gangetic: sig_01/02/05; NE small holding: sig_01 + sig_05 |
| 4 (539b4853797aafb1) | rainfed_risk__007: min 3 changed to min 2 |
| 5 (891d2f836d063a2a) | rainfed_risk__002: primary sig_01/02/03 (same as rainfed cluster default) |

## `758bb14fc8d6bbf1` (new `17f901bcdc0bbbd4`)

- **Example card:** `agriculture__water_scarcity__drought__005`
- **Issue addressed:** Issue 1: added min_from_set (2-of-4 drought signals)
- **Primary:** sig_01, sig_02, sig_03, sig_04
- **min_from_set:** `{"signals": ["sig_01", "sig_02", "sig_03", "sig_04"], "min": 2}`

**Draft note:**

> Pathway drought confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (drought_weeks_severe, drought_weeks_moderate), sig_02 (dry_spell_weeks), sig_03 (drought_causality), sig_04 (seasonal_precipitation_mm, precipitation_mm). Amplifying signals (do not alone confirm): sig_05 (monsoon_onset_date).

---

## `514cea203f3ea5b0` (new `c146e866fe7a931b`)

- **Example card:** `agriculture__water_scarcity__drought__002`
- **Issue addressed:** Issues 1+2: primary sig_01/02/03 (not lone sig_04); min_from_set added
- **Primary:** sig_01, sig_02, sig_03
- **min_from_set:** `{"signals": ["sig_01", "sig_02", "sig_03"], "min": 2}`

**Draft note:**

> Pathway drought confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (drought_weeks_severe, drought_weeks_moderate), sig_02 (dry_spell_weeks), sig_03 (drought_causality). Amplifying signals (do not alone confirm): sig_05 (monsoon_onset_date).

---

## `6b4cc36f5057475d` (new `6f210623937510c1`)

- **Example card:** `agriculture__water_scarcity__groundwater_stress__003`
- **Issue addressed:** Issue 3: expanded from lone sig_03 to sig_01+02+05
- **Primary:** sig_01, sig_02, sig_05
- **min_from_set:** `{"signals": ["sig_01", "sig_02", "sig_05"], "min": 2}`

**Draft note:**

> Pathway groundwater_stress confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (soge_dev_percent, soge_class_name), sig_02 (trend_annual_delta_g_mm, delta_g_mm), sig_05 (annual_well_depth_m). Amplifying signals (do not alone confirm): sig_04 (nrega_swc_count). Follow-up variables for field evidence: annual_well_depth_m, borewell_density, groundwater_salinity.

---

## `e8dc01684602bd98` (new `c146e866fe7a931b`)

- **Example card:** `ntfp_forest_biodiversity__ntfp_decline__forest_degradation__003`
- **Issue addressed:** Issue 1: RS primary sig_01/02/03 min 2 (was lone sig_05)
- **Primary:** sig_01, sig_02, sig_03
- **min_from_set:** `{"signals": ["sig_01", "sig_02", "sig_03"], "min": 2}`

**Draft note:**

> Pathway forest_degradation confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (lulc_tree_forest_ha), sig_02 (cd_total_deforestation_ha, cd_afforestation_ha), sig_03 (cd_total_deforestation_ha). Amplifying signals (do not alone confirm): sig_04 (organization_domains), sig_06 (forest_patch_connectivity). Follow-up variables for field evidence: ntfp_species_presence, forest_patch_connectivity.

---

## `539b4853797aafb1` (new `af4e696010ff91bd`)

- **Example card:** `agriculture__water_scarcity__rainfed_risk__007`
- **Issue addressed:** Issue 4: min confirms 3 to 2 on sig_01/02/04
- **Primary:** sig_01, sig_02, sig_04
- **min_from_set:** `{"signals": ["sig_01", "sig_02", "sig_04"], "min": 2}`

**Draft note:**

> Pathway rainfed_risk confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (lulc_single_kharif_ha, lulc_double_crop_ha), sig_02 (cropping_intensity), sig_04 (canal_name, nrega_irrigation_count). Amplifying signals (do not alone confirm): sig_03 (runoff_mm, terrain_cluster_id). Follow-up variables for field evidence: irrigated_area_ha.

---

## `891d2f836d063a2a` (new `c146e866fe7a931b`)

- **Example card:** `agriculture__water_scarcity__rainfed_risk__002`
- **Issue addressed:** Issue 5: added primary sig_01/02/03 with min_from_set
- **Primary:** sig_01, sig_02, sig_03
- **min_from_set:** `{"signals": ["sig_01", "sig_02", "sig_03"], "min": 2}`

**Draft note:**

> Pathway rainfed_risk confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (lulc_single_kharif_ha, lulc_double_crop_ha), sig_02 (cropping_intensity), sig_03 (canal_name, nrega_irrigation_count). Amplifying signals (do not alone confirm): sig_04 (runoff_mm, terrain_cluster_id). Follow-up variables for field evidence: irrigated_area_ha.

---

## `7203d24bf55d2cc9` (new `f27db9ca8faf9f79`)

- **Example card:** `socio_economic__low_income__small_landholding__012`
- **Issue addressed:** Issue 3: sig_01 required plus sig_05 (sig_02/03 are amplifiers on this card)
- **Primary:** sig_01, sig_05
- **min_from_set:** `{"signals": ["sig_01", "sig_05"], "min": 2}`

**Draft note:**

> Pathway small_landholding confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (lulc_cropland_ha, village_total_population), sig_05 (landholding_size_distribution). Required: sig_01 (lulc_cropland_ha, village_total_population) must be TRUE. Amplifying signals (do not alone confirm): sig_02 (cropping_intensity), sig_03 (dist_apmc_km), sig_04 (organization_domains, nrega_community_assets_count), sig_07 (market_price_crop). Follow-up variables for field evidence: landholding_size_distribution, household_income_inr, market_price_crop.

---

## `5e7b2cca017d1bdb` (new `4463c439a16ec684`)

- **Example card:** `agriculture__water_scarcity__rainfed_risk__008`
- **Issue addressed:** Issues 1+2: min_from_set plus full primary list
- **Primary:** sig_01, sig_02, sig_04, sig_05
- **min_from_set:** `{"signals": ["sig_01", "sig_02", "sig_04", "sig_05"], "min": 2}`

**Draft note:**

> Pathway rainfed_risk confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (lulc_single_kharif_ha, lulc_double_crop_ha), sig_02 (cropping_intensity), sig_04 (canal_name, nrega_irrigation_count), sig_05 (swb_rabi_area_ha). Amplifying signals (do not alone confirm): sig_03 (runoff_mm, terrain_cluster_id). Follow-up variables for field evidence: irrigated_area_ha.

---

## `6803055bd44bd95e` (new `78ccdb1aa0eb37b9`)

- **Example card:** `agriculture__water_scarcity__rainfed_risk__011`
- **Issue addressed:** Issues 1+2: min_from_set plus full primary list
- **Primary:** sig_01, sig_02, sig_03, sig_05
- **min_from_set:** `{"signals": ["sig_01", "sig_02", "sig_03", "sig_05"], "min": 2}`

**Draft note:**

> Pathway rainfed_risk confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (lulc_single_kharif_ha, lulc_double_crop_ha), sig_02 (cropping_intensity), sig_03 (canal_name, nrega_irrigation_count), sig_05 (swb_rabi_area_ha). Amplifying signals (do not alone confirm): sig_04 (runoff_mm, terrain_cluster_id). Follow-up variables for field evidence: irrigated_area_ha.

---

## `6078765eee9d5c67` (new `4463c439a16ec684`)

- **Example card:** `agriculture__water_scarcity__rainfed_risk__012`
- **Issue addressed:** Issues 1+2: min_from_set plus full primary list
- **Primary:** sig_01, sig_02, sig_04, sig_05
- **min_from_set:** `{"signals": ["sig_01", "sig_02", "sig_04", "sig_05"], "min": 2}`

**Draft note:**

> Pathway rainfed_risk confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (lulc_single_kharif_ha, lulc_double_crop_ha), sig_02 (cropping_intensity), sig_04 (nrega_irrigation_count, canal_name), sig_05 (irrigated_area_ha). Amplifying signals (do not alone confirm): sig_03 (runoff_mm, terrain_cluster_id). Follow-up variables for field evidence: irrigated_area_ha.

---

## `cdd74db78c08c69f` (new `78ccdb1aa0eb37b9`)

- **Example card:** `agriculture__water_scarcity__rainfed_risk__005`
- **Issue addressed:** Issues 1+2: min_from_set plus full primary list
- **Primary:** sig_01, sig_02, sig_03, sig_05
- **min_from_set:** `{"signals": ["sig_01", "sig_02", "sig_03", "sig_05"], "min": 2}`

**Draft note:**

> Pathway rainfed_risk confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (lulc_single_kharif_ha, lulc_double_crop_ha), sig_02 (cropping_intensity), sig_03 (canal_name, nrega_irrigation_count), sig_05 (irrigated_area_ha). Amplifying signals (do not alone confirm): sig_04 (runoff_mm, terrain_cluster_id). Follow-up variables for field evidence: irrigated_area_ha.

---

## `f6ed3f98aa2dd75e` (new `fcbd4fef4a61d6b5`)

- **Example card:** `agriculture__water_scarcity__irrigation_challenges__004`
- **Issue addressed:** Issues 1+2: min_from_set plus full primary list
- **Primary:** sig_01, sig_02
- **min_from_set:** `{"signals": ["sig_01", "sig_02"], "min": 2}`

**Draft note:**

> Pathway irrigation_challenges confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (swb_total_area_ha, swb_count), sig_02 (swb_kharif_area_ha). Amplifying signals (do not alone confirm): sig_03 (nrega_swc_count), sig_04 (dist_cooperative_km, river_name), sig_05 (annual_well_depth_m). Follow-up variables for field evidence: annual_well_depth_m.

---

## `045266b712bf5319` (new `6f210623937510c1`)

- **Example card:** `agriculture__water_scarcity__irrigation_challenges__012`
- **Issue addressed:** Issues 1+2: min_from_set plus full primary list
- **Primary:** sig_01, sig_02, sig_05
- **min_from_set:** `{"signals": ["sig_01", "sig_02", "sig_05"], "min": 2}`

**Draft note:**

> Pathway irrigation_challenges confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (swb_total_area_ha, swb_count), sig_02 (swb_kharif_area_ha), sig_05 (annual_well_depth_m). Amplifying signals (do not alone confirm): sig_03 (nrega_swc_count), sig_04 (river_name, dist_cooperative_km). Follow-up variables for field evidence: annual_well_depth_m.

---

## `9cae31a0b8d701ad` (new `bb9ce3ccd9457ea0`)

- **Example card:** `agriculture__water_scarcity__irrigation_challenges__005`
- **Issue addressed:** Issues 1+2: min_from_set plus full primary list
- **Primary:** sig_01, sig_02, sig_06
- **min_from_set:** `{"signals": ["sig_01", "sig_02", "sig_06"], "min": 2}`

**Draft note:**

> Pathway irrigation_challenges confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (swb_total_area_ha, swb_count), sig_02 (swb_kharif_area_ha), sig_06 (annual_well_depth_m). Amplifying signals (do not alone confirm): sig_03 (nrega_swc_count), sig_04 (river_name), sig_05 (dist_cooperative_km). Follow-up variables for field evidence: annual_well_depth_m.

---

## `7058dec595e400a6` (new `15fc2a3d3a2cd24d`)

- **Example card:** `agriculture__water_scarcity__irrigation_challenges__014`
- **Issue addressed:** Issues 1+2: min_from_set plus full primary list
- **Primary:** sig_01, sig_02, sig_05, sig_06
- **min_from_set:** `{"signals": ["sig_01", "sig_02", "sig_05", "sig_06"], "min": 2}`

**Draft note:**

> Pathway irrigation_challenges confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (swb_total_area_ha, swb_count), sig_02 (swb_kharif_area_ha), sig_05 (annual_well_depth_m), sig_06 (tank_siltation_status). Amplifying signals (do not alone confirm): sig_03 (nrega_swc_count), sig_04 (dist_cooperative_km). Follow-up variables for field evidence: annual_well_depth_m, tank_siltation_status.

---

## `1893d4cba2de282a` (new `af4e696010ff91bd`)

- **Example card:** `ntfp_forest_biodiversity__ntfp_decline__encroachment__004`
- **Issue addressed:** Issues 1+2: min_from_set plus full primary list
- **Primary:** sig_01, sig_02, sig_04
- **min_from_set:** `{"signals": ["sig_01", "sig_02", "sig_04"], "min": 2}`

**Draft note:**

> Pathway encroachment confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (cd_forest_to_farm_ha), sig_02 (cd_urbanization_ha), sig_04 (cd_forest_to_farm_ha, cd_urbanization_ha). Amplifying signals (do not alone confirm): sig_03 (village_st_percent). Follow-up variables for field evidence: fra_claims_filed_count, ntfp_collection_trend_qualitative.

---

## `b3a16ce03ca2017f` (new `17360cefb9c81426`)

- **Example card:** `ntfp_forest_biodiversity__ntfp_decline__encroachment__001`
- **Issue addressed:** Issue 1: sig_01 required plus one of sig_03/sig_04 (min 2)
- **Primary:** sig_01, sig_03, sig_04
- **min_from_set:** `{"signals": ["sig_01", "sig_03", "sig_04"], "min": 2}`

**Draft note:**

> Pathway encroachment confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (cd_forest_to_farm_ha), sig_03 (village_st_percent), sig_04 (cd_forest_to_farm_ha, village_st_percent). Required: sig_01 (cd_forest_to_farm_ha) must be TRUE. Additionally require at least one group: sig_03 (village_st_percent); OR sig_04 (cd_forest_to_farm_ha, village_st_percent). Amplifying signals (do not alone confirm): sig_02 (cd_urbanization_ha). Follow-up variables for field evidence: fra_claims_filed_count, forest_patch_connectivity.

---

## `9f3ae20f0f54b7c8` (new `6f210623937510c1`)

- **Example card:** `ntfp_forest_biodiversity__ntfp_decline__encroachment__003`
- **Issue addressed:** Issues 1+2: min_from_set plus full primary list
- **Primary:** sig_01, sig_02, sig_05
- **min_from_set:** `{"signals": ["sig_01", "sig_02", "sig_05"], "min": 2}`

**Draft note:**

> Pathway encroachment confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (cd_forest_to_farm_ha), sig_02 (cd_forest_to_farm_ha), sig_05 (cd_forest_to_farm_ha, village_st_percent). Amplifying signals (do not alone confirm): sig_03 (cd_urbanization_ha), sig_04 (village_st_percent). Follow-up variables for field evidence: ntfp_collection_trend_qualitative, fra_claims_filed_count.

---

## `9b0276448d48e4a4` (new `fc67fc268897daf1`)

- **Example card:** `ntfp_forest_biodiversity__ntfp_decline__encroachment__010`
- **Issue addressed:** Issue 2: kept sig_01 OR sig_04 rule; added min_from_set for draft clarity
- **Primary:** sig_01, sig_04
- **min_from_set:** `null`

**Draft note:**

> Pathway encroachment confirmation policy (auto-generated summary). Confirm when at least one of the primary signals is TRUE: sig_01 (cd_forest_to_farm_ha), sig_04 (cd_forest_to_farm_ha, village_st_percent). Additionally require at least one group: sig_01 (cd_forest_to_farm_ha); OR sig_04 (cd_forest_to_farm_ha, village_st_percent). Amplifying signals (do not alone confirm): sig_03 (village_st_percent). Follow-up variables for field evidence: fra_claims_filed_count, forest_boundary_demarcation_status.

---

## `1105430c8b5be6df` (new `bbb534422d76f1f3`)

- **Example card:** `ntfp_forest_biodiversity__ntfp_decline__encroachment__014`
- **Issue addressed:** Issues 1+2: min_from_set plus full primary list
- **Primary:** sig_01, sig_03, sig_05, sig_06
- **min_from_set:** `{"signals": ["sig_01", "sig_03", "sig_05", "sig_06"], "min": 2}`

**Draft note:**

> Pathway encroachment confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (cd_forest_to_farm_ha), sig_03 (village_st_percent), sig_05 (fra_claims_filed_count), sig_06 (ntfp_collection_trend_qualitative). Amplifying signals (do not alone confirm): sig_02 (cd_urbanization_ha), sig_04 (village_st_percent). Follow-up variables for field evidence: fra_claims_filed_count, ntfp_collection_trend_qualitative.

---

## `f8775f4def3a75aa` (new `55a053da44bd463f`)

- **Example card:** `ntfp_forest_biodiversity__ntfp_decline__encroachment__015`
- **Issue addressed:** Issues 1+2: min_from_set plus full primary list
- **Primary:** sig_01, sig_02, sig_04, sig_05, sig_06, sig_07
- **min_from_set:** `{"signals": ["sig_01", "sig_02", "sig_04", "sig_05", "sig_06", "sig_07"], "min": 2}`

**Draft note:**

> Pathway encroachment confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (cd_forest_to_farm_ha), sig_02 (cd_forest_to_farm_ha), sig_04 (village_st_percent), sig_05 (cd_forest_to_farm_ha, cd_urbanization_ha), sig_06 (fra_claims_filed_count), sig_07 (ntfp_collection_trend_qualitative). Amplifying signals (do not alone confirm): sig_03 (cd_urbanization_ha). Follow-up variables for field evidence: fra_claims_filed_count, ntfp_collection_trend_qualitative.

---

## `bcf9ecea2b9f1039` (new `e37509dd23c1582a`)

- **Example card:** `socio_economic__economic_hardship__multi_sector_vulnerability__011`
- **Issue addressed:** Issues 1+2: min_from_set plus full primary list
- **Primary:** sig_01, sig_03, sig_04, sig_05, sig_06
- **min_from_set:** `{"signals": ["sig_01", "sig_03", "sig_04", "sig_05", "sig_06"], "min": 2}`

**Draft note:**

> Pathway multi_sector_vulnerability confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (village_sc_percent, village_st_percent), sig_03 (dist_bank_km), sig_04 (drought_weeks_severe, nrega_swc_count), sig_05 (migrant_household_percent), sig_06 (household_income_inr). Amplifying signals (do not alone confirm): sig_02 (village_literacy_rate). Follow-up variables for field evidence: migrant_household_percent, household_income_inr.

---

## `2dbc650b1490ddc7` (new `5d3fe22f2d4e4543`)

- **Example card:** `socio_economic__economic_hardship__multi_sector_vulnerability__015`
- **Issue addressed:** Issues 1+2: min_from_set plus full primary list
- **Primary:** sig_01, sig_03, sig_05, sig_06, sig_07
- **min_from_set:** `{"signals": ["sig_01", "sig_03", "sig_05", "sig_06", "sig_07"], "min": 2}`

**Draft note:**

> Pathway multi_sector_vulnerability confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (village_sc_percent, village_st_percent), sig_03 (dist_bank_km), sig_05 (drought_weeks_severe), sig_06 (migrant_household_percent), sig_07 (household_income_inr). Amplifying signals (do not alone confirm): sig_02 (village_literacy_rate), sig_04 (nrega_swc_count). Follow-up variables for field evidence: migrant_household_percent, household_income_inr.

---

## `165dde27b2d7007e` (new `64dcf71a7b8b4f0f`)

- **Example card:** `socio_economic__low_income__small_landholding__007`
- **Issue addressed:** Issues 1+2: min_from_set plus full primary list
- **Primary:** sig_01, sig_02, sig_05, sig_07
- **min_from_set:** `{"signals": ["sig_01", "sig_02", "sig_05", "sig_07"], "min": 2}`

**Draft note:**

> Pathway small_landholding confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (lulc_cropland_ha, village_total_population), sig_02 (mean_cropping_intensity, cropping_intensity), sig_05 (household_income_inr), sig_07 (landholding_size_distribution). Amplifying signals (do not alone confirm): sig_03 (dist_apmc_km, dist_dairy_km), sig_04 (organization_domains, nrega_community_assets_count), sig_06 (market_price_crop). Follow-up variables for field evidence: landholding_size_distribution, household_income_inr, market_price_crop.

---

## `579f0295a41c238a` (new `fb20692f59040e84`)

- **Example card:** `socio_economic__low_income__small_landholding__015`
- **Issue addressed:** Issues 1+2: min_from_set plus full primary list
- **Primary:** sig_01, sig_06, sig_08
- **min_from_set:** `{"signals": ["sig_01", "sig_06", "sig_08"], "min": 2}`

**Draft note:**

> Pathway small_landholding confirmation policy (auto-generated summary). Confirm when at least 2 of the primary signals co-occur: sig_01 (lulc_cropland_ha, village_total_population), sig_06 (household_income_inr), sig_08 (landholding_size_distribution). Amplifying signals (do not alone confirm): sig_02 (cropping_intensity), sig_03 (dist_apmc_km), sig_04 (nrega_community_assets_count, organization_domains), sig_05 (dist_dairy_km), sig_07 (market_price_crop). Follow-up variables for field evidence: landholding_size_distribution, household_income_inr, market_price_crop.

---
