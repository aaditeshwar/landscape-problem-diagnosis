"""Reviewer allowlist for triaging and revise-cards finalize."""

from __future__ import annotations

from config import ALLOWED_REVIEWERS, ALLOWED_REVIEWERS_ALL


class ReviewerNotAllowedError(ValueError):
    pass


def validate_reviewer_name(name: str | None) -> str:
    cleaned = str(name or "").strip()
    if not cleaned:
        raise ReviewerNotAllowedError("Reviewer name is required")
    if ALLOWED_REVIEWERS_ALL:
        return cleaned
    if cleaned not in ALLOWED_REVIEWERS:
        allowed = ", ".join(ALLOWED_REVIEWERS)
        raise ReviewerNotAllowedError(
            f"Reviewer {cleaned!r} is not allowed. Set ALLOWED_REVIEWERS=ALL or use: {allowed}"
        )
    return cleaned


def reviewer_access_payload() -> dict[str, object]:
    return {
        "allowed_reviewers_all": ALLOWED_REVIEWERS_ALL,
        "allowed_reviewers": [] if ALLOWED_REVIEWERS_ALL else list(ALLOWED_REVIEWERS),
    }
