#!/usr/bin/env python3
"""Generate low-effort human review catalogs (unique signals, follow-ups, policies)."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"
REPORT_DIR = ROOT / "reports"

import sys

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "runtime"))
from lib.card_policy_utils import (  # noqa: E402
    draft_reasoning_note_from_policy,
    expression_fingerprint,
    policy_fingerprint,
)
from lib.follow_up_utils import (  # noqa: E402
    choice_summary,
    choice_summary_from_map,
    merge_choice_summary,
    none_choice_ids_from_summary,
    parse_choice_summary,
)
from services.follow_up_mcq import MCQ_TEMPLATES  # noqa: E402

# Prose-informed suggestions for template-neutral (None) MCQ bands.
# Synced with review_unique_follow_ups.csv (2026-06-20); None = keep neutral.
SUGGESTED_NONE_RESULTS: dict[tuple[str, str], bool | None] = {
    ("irrigated_area_ha", "moderate"): True,
    ("migrant_household_percent", "low"): False,
    ("migrant_household_percent", "moderate"): False,
    ("household_income_inr", "50k_to_100k"): True,
    ("ntfp_species_presence", "reduced"): True,
    ("community_forest_governance_status", "inactive"): True,
}

SUGGESTED_NONE_RATIONALE: dict[tuple[str, str], str] = {
    ("irrigated_area_ha", "moderate"): "Prose: 10–30% irrigated = pathway partially confirmed.",
    ("migrant_household_percent", "low"): "Prose only strongly confirms high (>30%); low band rules out distress migration.",
    ("migrant_household_percent", "moderate"): "Prose only strongly confirms high (>30%); middle band rules out distress migration.",
    ("household_income_inr", "50k_to_100k"): "Middle income band treated as confirming hardship (user review 2026-06-20).",
    ("ntfp_species_presence", "reduced"): "Reduced species availability confirms degradation pathway (user review 2026-06-20).",
    ("community_forest_governance_status", "inactive"): "Inactive governance confirms degradation (user review 2026-06-20).",
}


def template_none_choice_ids(variable: str) -> list[str]:
    template = MCQ_TEMPLATES.get(variable) or {}
    out: list[str] = []
    for choice in template.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        if choice.get("confirms_result") is None and "confirms_result" in choice:
            out.append(str(choice.get("id") or ""))
    return [cid for cid in out if cid]


def suggested_summary_for_question(variable: str, question: dict) -> tuple[str, str]:
    base_map = parse_choice_summary(choice_summary(question))
    overrides: dict[str, bool | None] = {}
    rationale_parts: list[str] = []
    for choice_id in none_choice_ids_from_summary(base_map):
        key = (variable, choice_id)
        if key in SUGGESTED_NONE_RESULTS:
            overrides[choice_id] = SUGGESTED_NONE_RESULTS[key]
            note = SUGGESTED_NONE_RATIONALE.get(key, "")
            if note:
                rationale_parts.append(f"{choice_id}: {note}")
    merged = merge_choice_summary(base_map, overrides)
    return choice_summary_from_map(merged), " | ".join(rationale_parts)


def choice_fingerprint(choices: list) -> str:
    rows = []
    for choice in choices or []:
        if not isinstance(choice, dict):
            continue
        normalized = choice.get("normalized") or {}
        effects = choice.get("effects") or {}
        effect_rows = effects.get("signals") if isinstance(effects, dict) else []
        rows.append(
            {
                "id": choice.get("id"),
                "normalized": normalized,
                "effects": effect_rows,
            }
        )
    return json.dumps(rows, sort_keys=True, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    args = parser.parse_args()

    signal_groups: dict[str, list[str]] = defaultdict(list)
    follow_up_groups: dict[str, list[str]] = defaultdict(list)
    policy_groups: dict[str, list[str]] = defaultdict(list)
    policy_samples: dict[str, dict] = {}

    for path in sorted(RAW_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as handle:
            card = json.load(handle)
        card_id = str(card.get("card_id") or path.stem)

        for signal in card.get("diagnostic_signals") or []:
            if not isinstance(signal, dict):
                continue
            fp = expression_fingerprint(signal)
            signal_groups[fp].append(card_id)

        for question in card.get("missing_variable_questions") or []:
            if not isinstance(question, dict) or question.get("response_type") != "mcq":
                continue
            variable = str(question.get("missing_variable") or "")
            fp = f"{variable}::{question.get('question_mode')}::{choice_fingerprint(question.get('choices') or [])}"
            follow_up_groups[fp].append(card_id)

        policy = card.get("confirmation_policy") or {}
        pfp = policy_fingerprint(policy)
        policy_groups[pfp].append(card_id)
        if pfp not in policy_samples:
            policy_samples[pfp] = {
                "card_id": card_id,
                "policy": policy,
                "note_excerpt": str(card.get("overall_reasoning_note") or "")[:300],
                "draft_note": draft_reasoning_note_from_policy(card, policy),
            }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    with (REPORT_DIR / "review_unique_signals.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "fingerprint",
                "card_count",
                "example_card_id",
                "signal_id",
                "direction",
                "variables",
                "expression",
                "qualitative_excerpt",
            ],
        )
        writer.writeheader()
        seen_fp: set[str] = set()
        for path in sorted(RAW_DIR.glob("*.json")):
            with path.open(encoding="utf-8") as handle:
                card = json.load(handle)
            for signal in card.get("diagnostic_signals") or []:
                if not isinstance(signal, dict):
                    continue
                fp = expression_fingerprint(signal)
                if fp in seen_fp:
                    continue
                seen_fp.add(fp)
                condition = signal.get("condition") or {}
                qual = str(condition.get("qualitative_description") or "")[:180]
                writer.writerow(
                    {
                        "fingerprint": fp,
                        "card_count": len(signal_groups[fp]),
                        "example_card_id": signal_groups[fp][0],
                        "signal_id": signal.get("signal_id"),
                        "direction": signal.get("direction"),
                        "variables": ", ".join(signal.get("variables") or []),
                        "expression": condition.get("expression") or "",
                        "qualitative_excerpt": qual,
                    }
                )

    with (REPORT_DIR / "review_unique_follow_ups.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "fingerprint",
                "card_count",
                "example_card_id",
                "variable",
                "question_mode",
                "choice_summary",
                "none_choice_ids",
                "template_none_ids",
                "prose_excerpt",
                "suggested_choice_summary",
                "suggestion_rationale",
                "review_decision",
                "review_notes",
            ],
        )
        writer.writeheader()
        seen_fu: set[str] = set()
        for path in sorted(RAW_DIR.glob("*.json")):
            with path.open(encoding="utf-8") as handle:
                card = json.load(handle)
            for question in card.get("missing_variable_questions") or []:
                if not isinstance(question, dict) or question.get("response_type") != "mcq":
                    continue
                variable = str(question.get("missing_variable") or "")
                fp = f"{variable}::{question.get('question_mode')}::{choice_fingerprint(question.get('choices') or [])}"
                if fp in seen_fu:
                    continue
                seen_fu.add(fp)
                summary = choice_summary(question)
                summary_map = parse_choice_summary(summary)
                none_ids = none_choice_ids_from_summary(summary_map)
                suggested_summary, rationale = suggested_summary_for_question(variable, question)
                prose = str(question.get("how_answer_updates_diagnosis") or "")[:320].replace("\n", " ")
                writer.writerow(
                    {
                        "fingerprint": hashlib_hex(fp),
                        "card_count": len(follow_up_groups[fp]),
                        "example_card_id": follow_up_groups[fp][0],
                        "variable": variable,
                        "question_mode": question.get("question_mode"),
                        "choice_summary": summary,
                        "none_choice_ids": ",".join(none_ids),
                        "template_none_ids": ",".join(template_none_choice_ids(variable)),
                        "prose_excerpt": prose,
                        "suggested_choice_summary": suggested_summary,
                        "suggestion_rationale": rationale,
                        "review_decision": "needs_review" if none_ids else "ok",
                        "review_notes": "",
                    }
                )

    with (REPORT_DIR / "review_unique_policies.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "fingerprint",
                "card_count",
                "example_card_id",
                "primary_signals",
                "min_confirms_true",
                "note_excerpt",
                "draft_note",
                "policy_json",
            ],
        )
        writer.writeheader()
        for pfp, card_ids in sorted(policy_groups.items(), key=lambda item: -len(item[1])):
            sample = policy_samples[pfp]
            policy = sample["policy"]
            writer.writerow(
                {
                    "fingerprint": pfp,
                    "card_count": len(card_ids),
                    "example_card_id": sample["card_id"],
                    "primary_signals": ",".join(policy.get("primary_confirm_signals") or []),
                    "min_confirms_true": (policy.get("confirm_when") or {}).get("min_confirms_true", ""),
                    "note_excerpt": sample["note_excerpt"],
                    "draft_note": sample["draft_note"],
                    "policy_json": json.dumps(policy, ensure_ascii=False),
                }
            )

    workflow = REPORT_DIR / "REVIEW_WORKFLOW.md"
    workflow.write_text(
        r"""# Evidence card review workflow (low effort)

Review **unique rows** in these CSVs once; changes propagate to all cards sharing the same fingerprint.

## 1. Unique signals — `review_unique_signals.csv`

Each row is a distinct signal **expression + qualitative description + variables + direction** pattern across clusters.

- Sort by `card_count` descending — fix high-impact rows first.
- Edit one `example_card_id` in the signal editor (or raw JSON), then run maintenance scripts to mirror if needed.
- Rows with empty `expression` are qualitative-only follow-up signals — review `qualitative_excerpt`.

## 2. Unique follow-ups — `review_unique_follow_ups.csv`

Each row is a distinct MCQ template: variable + question_mode + choice normalized/effects fingerprint.

- **`choice_summary`**: choice id → effect result (`True`/`False`/`None`). `None` = no explicit `effects.signals` on the card.
- **`none_choice_ids`**: choices currently missing effects (audit errors).
- **`template_none_ids`**: choices with `confirms_result: None` in `follow_up_mcq.py` (intentionally neutral in runtime template).
- **`suggested_choice_summary`**: proposed summary after applying prose-informed defaults (see `suggestion_rationale`).
- **`review_decision`**: fill before propagation:
  - `ok` — no None bands; no action
  - `needs_review` — has None band(s); decide below
  - `keep_none` — neutral bands stay without effects (legitimate non-confirm/non-deny)
  - `apply_suggested` — propagate `suggested_choice_summary` to all cards in group
  - `propagate` — propagate your edited `choice_summary` column

Align `how_answer_updates_diagnosis` prose on the example card with chosen effects (prose is display-only; effects are enforced).

### 2b. Propagate reviewed follow-ups

After setting `review_decision` on each row:

```powershell
.\.venv\Scripts\python.exe scripts/maintenance/propagate_follow_up_templates.py --dry-run
.\.venv\Scripts\python.exe scripts/maintenance/propagate_follow_up_templates.py
.\.venv\Scripts\python.exe scripts/verify/audit_follow_up_effects.py --write-report
.\.venv\Scripts\python.exe scripts/verify/audit_mcq_normalized.py
.\.venv\Scripts\python.exe scripts/reload_evidence_cards.py
```

| Target | What gets updated |
|--------|-------------------|
| `data/evidence_cards/raw/*.json` | All cards sharing each template fingerprint |
| `metadata/reviewed_follow_up_by_fingerprint.json` | 30 canonical MCQ templates |
| Mongo `evidence_cards` | Via reload script |

## 3. Unique policies — `review_unique_policies.csv`

Each row is a distinct `confirmation_policy` JSON shape.

- Compare `note_excerpt` (LLM prose) vs `draft_note` (auto-generated from policy + signals).
- Auto prose lists primary confirms, amplifiers, and follow-up variables — it **does not** capture rich hydrogeological context, confounders, or intervention framing in the LLM note.
- After approving a policy row, update `overall_reasoning_note` manually or keep LLM note as supplemental context and add a one-line “Executable policy: …” prefix.

### 3b. Propagate reviewed policies

After editing `metadata/policy_corrections.json` or approving rows in the policy CSV:

```powershell
.\.venv\Scripts\python.exe scripts/maintenance/apply_policy_corrections.py
.\.venv\Scripts\python.exe scripts/verify/audit_confirmation_policy.py --write-report
.\.venv\Scripts\python.exe scripts/reload_evidence_cards.py
```

| Target | What gets updated |
|--------|-------------------|
| `data/evidence_cards/raw/*.json` | Cards matching fingerprint or `by_card_id` overrides |
| `metadata/reviewed_policy_by_fingerprint.json` | Canonical policy templates per fingerprint |
| Mongo `evidence_cards` | Via reload script |

## 4. Audits (run after edits)

```powershell
.\.venv\Scripts\python.exe scripts/verify/audit_confirmation_policy.py --write-report
.\.venv\Scripts\python.exe scripts/verify/audit_follow_up_effects.py --write-report
.\.venv\Scripts\python.exe scripts/verify/audit_mcq_normalized.py
```

`policy_audit.csv` — one row per warning/error with note/policy context columns for manual review.  
`policy_audit_summary.csv` — all 136 cards with issue counts (even clean cards).

## 5. Reload Mongo

```powershell
.\.venv\Scripts\python.exe scripts/reload_evidence_cards.py
```

## Prose: auto-generate vs keep LLM note

| Keep in LLM `overall_reasoning_note` | Safe to auto-generate |
|--------------------------------------|------------------------|
| Agro-climatic / AER context | Primary signal list |
| Confounders and alternatives | Min confirms count |
| Intervention framing | Amplifier list |
| Nuanced “when not to confirm” | Linked follow-up variable names |

Recommendation: treat **policy + effects** as source of truth; use `draft_note` as a **checklist** and retain LLM prose for context below a short policy summary.
""",
        encoding="utf-8",
    )

    print(f"Wrote {REPORT_DIR}/review_unique_signals.csv ({len(seen_fp)} unique signals)")
    print(f"Wrote {REPORT_DIR}/review_unique_follow_ups.csv ({len(seen_fu)} unique follow-up templates)")
    print(f"Wrote {REPORT_DIR}/review_unique_policies.csv ({len(policy_groups)} unique policies)")
    print(f"Wrote {workflow}")
    return 0


def hashlib_hex(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


if __name__ == "__main__":
    raise SystemExit(main())
