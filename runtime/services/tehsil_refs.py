"""Tehsil reference helpers for multi-tehsil MWS membership."""

from __future__ import annotations

from typing import Any, TypedDict


class TehsilRef(TypedDict):
    state: str
    district: str
    tehsil: str


def tehsil_key(ref: TehsilRef | dict[str, Any]) -> str:
    return f"{ref['state']}__{ref['district']}__{ref['tehsil']}"


def make_tehsil_ref(state: str, district: str, tehsil: str) -> TehsilRef:
    return {"state": state, "district": district, "tehsil": tehsil}


def coerce_tehsil_ref(raw: dict[str, Any] | None) -> TehsilRef | None:
    if not raw:
        return None
    state = raw.get("state")
    district = raw.get("district")
    tehsil = raw.get("tehsil")
    if state and district and tehsil:
        return make_tehsil_ref(str(state), str(district), str(tehsil))
    return None


def normalize_tehsils(doc: dict[str, Any] | None) -> list[TehsilRef]:
    """Return tehsil membership list; fall back to legacy scalar fields."""
    if not doc:
        return []
    refs: list[TehsilRef] = []
    seen: set[str] = set()
    raw_list = doc.get("tehsils")
    if isinstance(raw_list, list):
        for item in raw_list:
            ref = coerce_tehsil_ref(item if isinstance(item, dict) else None)
            if ref is None:
                continue
            key = tehsil_key(ref)
            if key not in seen:
                seen.add(key)
                refs.append(ref)
    if refs:
        return refs
    legacy = coerce_tehsil_ref(doc)
    return [legacy] if legacy else []


def primary_tehsil(doc: dict[str, Any] | None) -> TehsilRef | None:
    refs = normalize_tehsils(doc)
    return refs[0] if refs else None


def doc_in_tehsil(doc: dict[str, Any] | None, ref: TehsilRef | dict[str, Any]) -> bool:
    target = tehsil_key(ref)
    return any(tehsil_key(item) == target for item in normalize_tehsils(doc))


def sync_legacy_tehsil_fields(doc: dict[str, Any], refs: list[TehsilRef]) -> None:
    """Keep scalar state/district/tehsil aligned with primary ref for legacy readers."""
    if not refs:
        return
    primary = refs[0]
    doc["state"] = primary["state"]
    doc["district"] = primary["district"]
    doc["tehsil"] = primary["tehsil"]


def tehsil_ref_dict(ref: TehsilRef | dict[str, Any] | None) -> dict[str, str] | None:
    coerced = coerce_tehsil_ref(ref if isinstance(ref, dict) else None)
    if coerced is None:
        return None
    return dict(coerced)


def resolve_active_tehsil(
    doc: dict[str, Any] | None,
    active_ref: TehsilRef | dict[str, Any] | None = None,
) -> TehsilRef | None:
    """Prefer explicit active ref (map selection); else primary membership."""
    coerced = coerce_tehsil_ref(active_ref if isinstance(active_ref, dict) else None)
    if coerced is not None:
        return coerced
    return primary_tehsil(doc)


def format_tehsil_label(ref: TehsilRef | dict[str, Any] | None) -> str:
    coerced = coerce_tehsil_ref(ref if isinstance(ref, dict) else None)
    if coerced is None:
        return "—"
    return f"{coerced['tehsil']}, {coerced['district']}, {coerced['state']}"


def format_tehsil_list(doc: dict[str, Any] | None, active_ref: TehsilRef | dict[str, Any] | None = None) -> str:
    refs = normalize_tehsils(doc)
    if not refs:
        return "—"
    active = resolve_active_tehsil(doc, active_ref)
    if active and len(refs) == 1:
        return format_tehsil_label(active)
    if active and doc_in_tehsil(doc, active):
        others = [r for r in refs if tehsil_key(r) != tehsil_key(active)]
        if not others:
            return format_tehsil_label(active)
        other_names = ", ".join(r["tehsil"] for r in others)
        return f"{format_tehsil_label(active)} (also in {other_names})"
    return "; ".join(format_tehsil_label(r) for r in refs)


def tehsil_membership_query(ref: TehsilRef | dict[str, Any]) -> dict[str, Any]:
    """MongoDB filter: MWS doc belongs to this tehsil."""
    coerced = coerce_tehsil_ref(ref if isinstance(ref, dict) else None)
    if coerced is None:
        return {}
    return {
        "tehsils": {
            "$elemMatch": {
                "state": coerced["state"],
                "district": coerced["district"],
                "tehsil": coerced["tehsil"],
            }
        }
    }


def merge_tehsil_refs(existing: list[TehsilRef], new_ref: TehsilRef) -> list[TehsilRef]:
    merged = list(existing)
    if not doc_in_tehsil({"tehsils": merged}, new_ref):
        merged.append(dict(new_ref))
    merged.sort(key=tehsil_key)
    return merged
