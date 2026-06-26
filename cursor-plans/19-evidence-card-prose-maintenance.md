# Evidence card prose maintenance (signals, policy, notes)

> **Status:** Track A largely done (categories 1–8); Track B P1+P2 complete (2026-06-26) — **0 policy audit warnings** corpus-wide  
> **Created:** 2026-06-26  
> **Related:** [00-tooling-registry.md](./00-tooling-registry.md), [13-confirmation-policy-and-schema.md](./13-confirmation-policy-and-schema.md), [15-claude-evidence-card-review.md](./15-claude-evidence-card-review.md), [16-revise-cards-review-app.md](./16-revise-cards-review-app.md)

---

## Purpose

Bulk-align human-readable prose on evidence cards with machine-evaluated rules, without regressions when `apply_user_card_edits.py` runs. Two tracks:

| Track | Fields | Status |
|-------|--------|--------|
| **A — Signal qual** | `diagnostic_signals[].condition.qualitative_description` vs `expression` | Categories 1–8 applied; rainfed sig_01, drought sig_04/05, etc. pending |
| **B — Policy vs note** | `overall_reasoning_note` vs `confirmation_policy` | **Done** — `align_overall_reasoning_notes.py` applied; audit 0 warnings (136 cards) |

---

## Golden rule: raw cards + patch file stay in sync

`metadata/claude_review_user_card_edits.json` stores **partial patches** per finalized card. `apply_user_card_edits.py` **merges** those patches onto raw JSON. Stale patch content **reverts** good raw edits (e.g. category 1B dry-spell qual).

**Patches are retained** after apply (not purged). Each entry gets `propagated_at` + `applied_card_digest`. Re-finalizing a card in Revise Cards **overwrites** that card's entry and clears propagation metadata.

---

## Maintenance sequence (after any raw-card bulk edit)

Run in order:

```powershell
# 1. Apply the maintenance change (examples)
py scripts/maintenance/align_qualitative_descriptions.py <category>   # signal qual templates
py scripts/maintenance/align_overall_reasoning_notes.py          # note opening from confirmation_policy (Track B)
py scripts/maintenance/normalize_evidence_card_expressions.py         # expression rewrites + variables[] sync into patches

# 2. Refresh user-edit patches from live raw (MANDATORY after raw maintenance)
py scripts/maintenance/sync_user_edit_patches_from_raw.py

# 3. Verify apply is a no-op (expect applied=0)
py scripts/review/apply_user_card_edits.py --dry-run

# 4. Audits (optional but recommended before Mongo)
py scripts/maintenance/audit_expression_prose.py
py scripts/verify/audit_confirmation_policy.py --write-report

# 5. Reload Mongo
py scripts/reload_evidence_cards.py
# Or scoped: py scripts/reload_evidence_cards.py --prefix agriculture__water_scarcity__drought
```

### Per-script patch sync behaviour

| Script | Updates raw JSON | Mirrors into `claude_review_user_card_edits.json` |
|--------|------------------|---------------------------------------------------|
| `align_qualitative_descriptions.py` | qual prose | qual fields only (`sync_user_edit_patches`) |
| `normalize_evidence_card_expressions.py` | expressions + `variables[]` | `variables[]` in patch signals |
| `sync_user_edit_patches_from_raw.py` | — | **All** patch-covered fields + `applied_card_digest` from raw |

### Authoring going forward

| Method | After saving |
|--------|----------------|
| **Revise Cards app** (preferred) | `py scripts/review/apply_user_card_edits.py` |
| **Maintenance scripts** on raw | Run full sequence above |

**Never** run bare `apply_user_card_edits.py` after raw maintenance without step 2 (`sync_user_edit_patches_from_raw.py`).

---

## Track A — Signal qual alignment (done categories)

Handler categories in `scripts/maintenance/align_qualitative_descriptions.py`:

| Cat | Handler key | Target |
|-----|-------------|--------|
| 1A | `drought_sig_01_return_period` | return-period expressions |
| 1B | `drought_mean_dry_spell` | `mean(dry_spell_weeks) >= 3` |
| 2A | `groundwater_mean_delta_g_only` | `mean_annual_delta_g_mm < 0` |
| 3A | `irrigation_sig_01_swb_trend` | SWB trend + count |
| 3B | `irrigation_sig_03_nrega_swc` | `nrega_swc_count <= 20` |
| 4 | `rainfed_nrega_irrigation_count` | NREGA irrigation count |
| 5 | `encroachment_sig01_forest_farm_ha` | forest-to-farm ha thresholds |
| 6 | `forest_degradation_deforestation_ha` | deforestation ha thresholds |
| 7 | `multi_sector_sig01_literacy` | SC/ST + literacy |
| 8 | `multi_sector_sig03_bank_or_nrega` | bank distance / NREGA |

**Workflow:** Review template wording in chat → apply category → verify `apply_user_card_edits.py --dry-run` (SKIP all affected).

**Prose rule:** expression threshold `> 29` → describe as **30 ha** in qual (round in prose, not expression).

---

## Track B — Policy vs `overall_reasoning_note` (done)

### Apply tool

```powershell
py scripts/maintenance/align_overall_reasoning_notes.py           # cards with drift flags
py scripts/maintenance/align_overall_reasoning_notes.py --all-cards  # full corpus refresh
```

Rebuilds the note **opening** from `confirmation_policy` (policy authoritative), preserves contextual **tail** (distinguish-from, interventions, etc.). Uses em-dash primary lists (`sig_01 (short label), sig_02 (…) — co-occur`).

**Note label tiers** (`scripts/lib/sig_note_labels.py`, `scripts/lib/note_label_templates.py`):
1. **Tier 2** — expression/pathway templates (short handles; expression in tooltip)
2. **Tier 1** — compress `qualitative_description` (strip rationale/parentheticals)
3. Fallback — variable names

Re-apply after template edits:

```powershell
py scripts/maintenance/align_overall_reasoning_notes.py --all-cards
py scripts/maintenance/scrub_note_signal_duplicates.py --all-cards
```

### Audit tool

```powershell
py scripts/verify/audit_confirmation_policy.py --write-report
```

Produces:
- `reports/policy_review/policy_audit.csv` — one row per issue
- `reports/policy_review/policy_audit_summary.csv` — all cards

Helpers: `scripts/lib/card_policy_utils.py` (`primary_signals_from_note`, `derive_policy`, `draft_reasoning_note_from_policy`).

### Baseline audit (2026-06-26)

| Issue code | Count | Meaning |
|------------|-------|---------|
| `policy_extra_primary` | 70 | Policy lists primaries not named as primaries in note prose |
| `stored_derive_drift` | 68 | `confirmation_policy` primary set ≠ re-derive from current note |
| `min_confirms_mismatch` | 15 | Note implies different `min_confirms_true` than policy |
| `amplifier_in_policy_primary` | 2 | **ERROR** — amplifier in primary set (`multi_sector_vulnerability__005/006` sig_05) |

**155 issue rows** across **~90 cards** (many cards have multiple flags). Pathways most affected: `multi_sector_vulnerability` (35), `encroachment` (30), `small_landholding` (29), `forest_degradation` (25).

**Recurring patterns (for template categories):**

1. **Policy includes sig_06 / sig_07 not in note** — common on small_landholding + multi_sector cards where Revise Cards updated `confirmation_policy` but note still describes an older primary set.
2. **Policy includes sig_05 (amplifier) as primary** — note says amplifies; policy lists sig_05 in `primary_confirm_signals` (2 hard errors on `multi_sector_vulnerability__005/006`).
3. **Drought sig_04 in policy, not note** — policy `sig_01, sig_02, sig_04`; note emphasizes `sig_01` + `sig_02` only (trend signal as contextual in prose).
4. **min_confirms 1 vs 2** — note reads single-signal confirm; policy `min_confirms_true: 2` (15 cards, heavy in irrigation + rainfed).

### Planned workflow (same as Track A)

1. Group issues into template categories; review proposed note **or** policy wording in chat.
2. Implement `align_overall_reasoning_notes.py` or `align_confirmation_policies.py` (TBD — likely note prose updates to match authoritative policy).
3. `sync_user_edit_patches_from_raw.py` after apply.
4. Dry-run `apply_user_card_edits.py`.
5. `reload_evidence_cards.py`.

**Open decision:** For each category, is **policy** or **note** authoritative? Revise Cards edits often touch `confirmation_policy` only — default: **align note to policy** unless user says otherwise.

---

## Mongo reload

After any raw card change batch:

```powershell
py scripts/reload_evidence_cards.py              # full corpus (~136 cards)
py scripts/reload_evidence_cards.py --prefix X   # pathway subset
```

---

## Checklist (copy per maintenance session)

- [ ] Maintenance script applied to `data/evidence_cards/raw/`
- [ ] `sync_user_edit_patches_from_raw.py` (0 skipped digest drift)
- [ ] `apply_user_card_edits.py --dry-run` → `applied=0`
- [ ] Audits clean or exceptions documented
- [ ] `reload_evidence_cards.py`
- [ ] Git commit + push
