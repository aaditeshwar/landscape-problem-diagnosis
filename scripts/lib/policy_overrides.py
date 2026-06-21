"""Load reviewed confirmation policy overrides (pilot cards + fingerprint templates)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = ROOT / "reports"
PILOT_POLICIES = ROOT / "metadata" / "pilot_confirmation_policies.json"
POLICY_CORRECTIONS = REPORTS_DIR / "policy_corrections.json"
REVIEWED_POLICY_BY_FP = REPORTS_DIR / "reviewed_policy_by_fingerprint.json"
REVIEWED_FOLLOW_UP_BY_FP = REPORTS_DIR / "reviewed_follow_up_by_fingerprint.json"
REVIEWED_BY_FP = REVIEWED_POLICY_BY_FP
RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def load_pilot_overrides() -> dict[str, dict]:
    return load_json(PILOT_POLICIES)


def load_policy_corrections() -> tuple[dict[str, dict], dict[str, dict]]:
    """Return (by_fingerprint, by_card_id) template bodies without version wrapper."""
    raw = load_json(POLICY_CORRECTIONS)
    raw.pop("_comment", None)
    by_card_id = raw.pop("by_card_id", {}) or {}
    return raw, by_card_id


def load_reviewed_by_fingerprint() -> dict[str, dict]:
    return load_json(REVIEWED_BY_FP)


def resolve_policy_for_card(
    card: dict,
    *,
    card_id: str | None = None,
    pilot: dict[str, dict] | None = None,
    by_fingerprint: dict[str, dict] | None = None,
    by_card_id: dict[str, dict] | None = None,
) -> dict | None:
    """Return a reviewed override policy for this card, or None to keep derive/existing."""
    from lib.card_policy_utils import policy_fingerprint

    card_id = str(card_id or card.get("card_id") or "").strip()
    pilot = pilot if pilot is not None else load_pilot_overrides()
    by_fingerprint = by_fingerprint if by_fingerprint is not None else load_reviewed_by_fingerprint()
    _, corrections_by_card = load_policy_corrections()
    by_card_id = by_card_id if by_card_id is not None else corrections_by_card

    if card_id and card_id in pilot:
        return pilot[card_id]
    if card_id and card_id in by_card_id:
        body = by_card_id[card_id]
        return {"version": 1, **body}
    fp = policy_fingerprint(card.get("confirmation_policy"))
    if fp and fp in by_fingerprint:
        return by_fingerprint[fp]
    return None


def export_reviewed_by_fingerprint(raw_dir: Path | None = None) -> dict[str, dict]:
    """Build fingerprint -> policy map from raw cards (canonical after review)."""
    from lib.card_policy_utils import policy_fingerprint

    raw_dir = raw_dir or RAW_DIR
    out: dict[str, dict] = {}
    for path in sorted(raw_dir.glob("*.json")):
        with path.open(encoding="utf-8") as handle:
            card = json.load(handle)
        policy = card.get("confirmation_policy")
        if not isinstance(policy, dict):
            continue
        fp = policy_fingerprint(policy)
        if fp:
            out[fp] = policy
    return out
