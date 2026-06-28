# -*- coding: utf-8 -*-
"""Build metadata/groundtruth/groundtruth_collection_form.json from framework + cards."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "runtime") not in sys.path:
    sys.path.insert(0, str(ROOT / "runtime"))

from services.built_pathways import built_pathway_tuples  # noqa: E402
from services.follow_up_mcq import MCQ_TEMPLATES  # noqa: E402

FRAMEWORK_PATH = ROOT / "metadata" / "diagnosis_framework.json"
RAW_CARDS_DIR = ROOT / "data" / "evidence_cards" / "raw"
OUT_DIR = ROOT / "metadata" / "groundtruth"
FORM_PATH = OUT_DIR / "groundtruth_collection_form.json"
RESPONSE_TEMPLATE_PATH = OUT_DIR / "groundtruth_response_template.json"

PRODUCTION_LABELS = {
    "Agriculture": "Agriculture",
    "Livestock": "Livestock",
    "NTFP_Forest_Biodiversity": "NTFP / forest biodiversity",
    "Fishery": "Fishery",
    "Socio_Economic": "Socio-economic livelihoods",
}

STRESS_LABELS = {
    "water_scarcity": "Water scarcity",
    "low_yield": "Low crop yield",
    "crop_failure": "Crop failure",
    "market_access_gap": "Market access gap",
    "livestock_decline": "Livestock decline",
    "ntfp_decline": "NTFP decline",
    "wildlife_conflict": "Wildlife conflict",
    "biodiversity_loss": "Biodiversity loss",
    "low_fish_productivity": "Low fish productivity",
    "economic_hardship": "Economic hardship",
    "low_income": "Low income",
}

PATHWAY_LABELS = {
    "groundwater_stress": "Groundwater stress",
    "drought": "Drought",
    "rainfed_risk": "Rainfed agriculture risk",
    "irrigation_challenges": "Irrigation challenges",
    "forest_degradation": "Forest degradation",
    "encroachment": "Forest encroachment / grazing pressure",
    "multi_sector_vulnerability": "Multi-sector vulnerability",
    "small_landholding": "Small landholding pressure",
}


def _label(key: str, mapping: dict[str, str]) -> str:
    if key in mapping:
        return mapping[key]
    return key.replace("_", " ").strip().title()


def _load_followups_by_pathway() -> dict[tuple[str, str, str], dict[str, dict]]:
    """(production, stress, pathway) -> variable -> question entry (first card wins)."""
    out: dict[tuple[str, str, str], dict[str, dict]] = {}
    if not RAW_CARDS_DIR.is_dir():
        return out
    for path in sorted(RAW_CARDS_DIR.glob("*.json")):
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(card, dict):
            continue
        production = str(card.get("production_system") or "").strip()
        stress = str(card.get("observed_stress") or "").strip()
        pathway = str(card.get("causal_pathway") or "").strip()
        if not production or not stress or not pathway:
            continue
        key = (production, stress, pathway)
        bucket = out.setdefault(key, {})
        for q in card.get("missing_variable_questions") or []:
            if not isinstance(q, dict):
                continue
            var = str(q.get("missing_variable") or q.get("variable") or "").strip()
            if var and var not in bucket:
                bucket[var] = q
    return out


def _mcq_choices(variable: str, card_entry: dict) -> list[dict[str, str]]:
    template = MCQ_TEMPLATES.get(variable) or {}
    template_choices = {
        str(c.get("id") or "").strip(): str(c.get("label") or "").strip()
        for c in template.get("choices") or []
        if isinstance(c, dict)
    }
    choices: list[dict[str, str]] = []
    seen: set[str] = set()
    for choice in card_entry.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        cid = str(choice.get("id") or "").strip()
        label = str(choice.get("label") or template_choices.get(cid) or "").strip()
        if not cid or not label or cid in seen:
            continue
        seen.add(cid)
        choices.append({"id": cid, "label": label})
    if choices:
        return choices
    for cid, label in template_choices.items():
        if cid and label:
            choices.append({"id": cid, "label": label})
    return choices


def _follow_up_mcqs(
    key: tuple[str, str, str],
    followups: dict[tuple[str, str, str], dict[str, dict]],
) -> list[dict]:
    items: list[dict] = []
    for variable, entry in sorted(followups.get(key, {}).items()):
        response_type = str(entry.get("response_type") or "mcq").lower()
        question = str(
            entry.get("question_to_user") or entry.get("question") or ""
        ).strip()
        if not question:
            continue
        mcq: dict = {
            "variable": variable,
            "field_type": response_type,
            "label": _label(variable, {}),
            "question": question,
            "required_when_pathway_yes": True,
            "show_when": {"pathway_confirmed": "yes"},
        }
        if response_type == "mcq":
            choices = _mcq_choices(variable, entry)
            if choices:
                mcq["choices"] = choices
                mcq["allow_unknown"] = {
                    "id": "unknown",
                    "label": "Don't know / not applicable in our area",
                }
        items.append(mcq)
    return items


def build_form() -> dict:
    framework = json.loads(FRAMEWORK_PATH.read_text(encoding="utf-8"))["diagnosis_framework"]
    production_systems_fw = framework["production_systems"]
    built_tuples = built_pathway_tuples()
    followups = _load_followups_by_pathway()

    production_systems: list[dict] = []
    for ps_id, ps_data in production_systems_fw.items():
        stresses_out: list[dict] = []
        for stress_id, stress_data in (ps_data.get("observed_stresses") or {}).items():
            pathways_out: list[dict] = []
            for pathway_id, pathway_data in (stress_data.get("causal_pathways") or {}).items():
                key = (ps_id, stress_id, pathway_id)
                has_cards = key in built_tuples
                pathways_out.append(
                    {
                        "id": pathway_id,
                        "label": _label(pathway_id, PATHWAY_LABELS),
                        "field_type": "yes_no",
                        "prompt": (
                            f"Is \"{_label(pathway_id, PATHWAY_LABELS)}\" a plausible "
                            "causal explanation for this stress in your area?"
                        ),
                        "description": str(pathway_data.get("description") or "").strip(),
                        "has_evidence_cards": has_cards,
                        "show_when": {"observed_stress": stress_id, "value": "yes"},
                        "follow_up_mcqs": _follow_up_mcqs(key, followups)
                        if has_cards
                        else [],
                    }
                )
            pathways_out.sort(key=lambda p: (not p["has_evidence_cards"], p["label"]))
            stresses_out.append(
                {
                    "id": stress_id,
                    "label": _label(stress_id, STRESS_LABELS),
                    "field_type": "yes_no",
                    "prompt": (
                        f"Do people in your area report \"{_label(stress_id, STRESS_LABELS)}\"?"
                    ),
                    "description": str(stress_data.get("description") or "").strip(),
                    "show_when": {"production_system": ps_id, "value": "yes"},
                    "causal_pathways": pathways_out,
                }
            )
        production_systems.append(
            {
                "id": ps_id,
                "label": PRODUCTION_LABELS.get(ps_id, ps_id),
                "field_type": "yes_no",
                "prompt": (
                    f"Is \"{PRODUCTION_LABELS.get(ps_id, ps_id)}\" an important production "
                    "system in your micro-watershed?"
                ),
                "show_when": None,
                "observed_stresses": stresses_out,
            }
        )

    return {
        "meta": {
            "form_id": "landscape_groundtruth_v1",
            "version": 1,
            "title": "Landscape pathway ground truth - field collection form",
            "description": (
                "Structured yes/no hierarchy for stewards and field enablers: production system "
                "-> observed stress -> causal pathway -> follow-up MCQs. Use alongside CoRE Stack MWS "
                "data for signal tuning and query evaluation."
            ),
            "sources": [
                "metadata/diagnosis_framework.json",
                "data/evidence_cards/raw/*.json",
                "runtime/services/follow_up_mcq.py",
            ],
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "field_types": {
                "yes_no": {
                    "response_options": [
                        {"id": "yes", "label": "Yes"},
                        {"id": "no", "label": "No"},
                        {"id": "unknown", "label": "Don't know"},
                    ]
                },
                "mcq": {"response_type": "single_select"},
            },
            "collection_notes": [
                "Complete location fields first, then walk production systems top to bottom.",
                "Only answer pathway yes/no when the parent stress is yes.",
                "Answer follow-up MCQs only for pathways marked yes.",
                "Prefer the MWS UID from Commons Connect or the CoRE insights map.",
            ],
        },
        "respondent_fields": [
            {
                "id": "mws_uid",
                "field_type": "text",
                "label": "Micro-watershed UID",
                "required": True,
                "placeholder": "e.g. 4_100672",
            },
            {
                "id": "village_names",
                "field_type": "text",
                "label": "Village(s) covered",
                "required": False,
                "placeholder": "Comma-separated village names",
            },
            {
                "id": "state",
                "field_type": "text",
                "label": "State",
                "required": False,
            },
            {
                "id": "district",
                "field_type": "text",
                "label": "District",
                "required": False,
            },
            {
                "id": "tehsil",
                "field_type": "text",
                "label": "Tehsil / block",
                "required": False,
            },
            {
                "id": "collector_name",
                "field_type": "text",
                "label": "Collector name",
                "required": False,
            },
            {
                "id": "organisation",
                "field_type": "text",
                "label": "Organisation (CSO / department)",
                "required": False,
            },
            {
                "id": "collection_date",
                "field_type": "date",
                "label": "Date of visit / interview",
                "required": True,
            },
            {
                "id": "notes",
                "field_type": "textarea",
                "label": "Additional context",
                "required": False,
                "placeholder": "Season, respondent group, uncertainties, local terms used",
            },
        ],
        "production_systems": production_systems,
    }


def build_response_template(form: dict) -> dict:
    """Empty response skeleton mirroring the form hierarchy."""
    location = {f["id"]: None for f in form.get("respondent_fields") or []}
    responses: list[dict] = []
    for ps in form.get("production_systems") or []:
        ps_entry: dict = {
            "production_system": ps["id"],
            "present": None,
            "observed_stresses": [],
        }
        for stress in ps.get("observed_stresses") or []:
            stress_entry: dict = {
                "observed_stress": stress["id"],
                "present": None,
                "causal_pathways": [],
            }
            for pathway in stress.get("causal_pathways") or []:
                pathway_entry: dict = {
                    "causal_pathway": pathway["id"],
                    "present": None,
                    "follow_up_answers": [],
                }
                for mcq in pathway.get("follow_up_mcqs") or []:
                    pathway_entry["follow_up_answers"].append(
                        {
                            "variable": mcq["variable"],
                            "choice_id": None,
                        }
                    )
                stress_entry["causal_pathways"].append(pathway_entry)
            ps_entry["observed_stresses"].append(stress_entry)
        responses.append(ps_entry)
    return {
        "meta": {
            "form_id": form["meta"]["form_id"],
            "form_version": form["meta"]["version"],
            "response_id": None,
            "submitted_at": None,
        },
        "location": location,
        "responses": responses,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    form = build_form()
    FORM_PATH.write_text(json.dumps(form, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    template = build_response_template(form)
    RESPONSE_TEMPLATE_PATH.write_text(
        json.dumps(template, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    built_count = sum(
        1
        for ps in form["production_systems"]
        for st in ps["observed_stresses"]
        for pw in st["causal_pathways"]
        if pw["has_evidence_cards"]
    )
    mcq_count = sum(
        len(pw.get("follow_up_mcqs") or [])
        for ps in form["production_systems"]
        for st in ps["observed_stresses"]
        for pw in st["causal_pathways"]
    )
    print(f"Wrote {FORM_PATH.relative_to(ROOT)}")
    print(f"Wrote {RESPONSE_TEMPLATE_PATH.relative_to(ROOT)}")
    print(f"Production systems: {len(form['production_systems'])}")
    print(f"Built pathways with cards: {built_count}")
    print(f"Follow-up MCQs: {mcq_count}")


if __name__ == "__main__":
    main()
