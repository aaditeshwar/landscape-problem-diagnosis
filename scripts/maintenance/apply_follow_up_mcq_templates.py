#!/usr/bin/env python3
"""Apply shared MCQ templates to evidence card missing_variable_questions entries."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "runtime"))

from services.follow_up_mcq import MCQ_TEMPLATES  # noqa: E402

RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"


def apply_templates(*, dry_run: bool = False) -> dict[str, int]:
    stats = {"files_touched": 0, "entries_updated": 0}
    for path in sorted(RAW_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as fh:
            card = json.load(fh)
        changed = False
        for entry in card.get("missing_variable_questions") or []:
            if not isinstance(entry, dict):
                continue
            var = str(entry.get("missing_variable") or entry.get("variable") or "").strip()
            template = MCQ_TEMPLATES.get(var)
            if not template:
                continue
            template_choices = {
                str(choice.get("id") or "").strip(): choice
                for choice in template.get("choices") or []
                if isinstance(choice, dict) and choice.get("id")
            }
            if entry.get("response_type") == "mcq" and entry.get("choices"):
                for choice in entry.get("choices") or []:
                    if not isinstance(choice, dict):
                        continue
                    template_choice = template_choices.get(str(choice.get("id") or "").strip())
                    if not template_choice:
                        continue
                    if choice.get("label") != template_choice.get("label"):
                        choice["label"] = template_choice["label"]
                        changed = True
                    template_norm = template_choice.get("normalized")
                    if isinstance(template_norm, dict) and choice.get("normalized") != template_norm:
                        choice["normalized"] = json.loads(json.dumps(template_norm))
                        changed = True
                continue
            entry["response_type"] = template["response_type"]
            entry["choices"] = json.loads(json.dumps(template["choices"]))
            stats["entries_updated"] += 1
            changed = True
        if changed:
            stats["files_touched"] += 1
            if not dry_run:
                with path.open("w", encoding="utf-8") as fh:
                    json.dump(card, fh, ensure_ascii=False, indent=2)
                    fh.write("\n")
    return stats


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    stats = apply_templates(dry_run=dry_run)
    mode = "Would update" if dry_run else "Updated"
    print(
        f"{mode} {stats['entries_updated']} question entries "
        f"across {stats['files_touched']} card files."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
