"""Short human-readable labels for signals in overall_reasoning_note prose."""

from __future__ import annotations

import re

SIG_REF_RE = re.compile(r"sig_\d+", re.IGNORECASE)
SIG_PAREN_RE = re.compile(r"sig_\d+\s*\([^)]*\)", re.IGNORECASE)

# Rationale tails added after the measurable claim in qualitative_description.
_RATIONALE_RES = (
    re.compile(r",?\s*indicating\b.+$", re.IGNORECASE),
    re.compile(r",?\s*indicates?\b.+$", re.IGNORECASE),
    re.compile(r",?\s*confirm(?:s|ing)?\b.+$", re.IGNORECASE),
    re.compile(r",?\s*together\b.+$", re.IGNORECASE),
    re.compile(r"\s+per the\b.+$", re.IGNORECASE),
)


def note_label_from_qual(qual: str, *, max_words: int | None = None) -> str:
    """Derive a compact note label from qualitative_description (expression stays in tooltip)."""
    text = str(qual or "").strip()
    if not text:
        return ""

    if ". " in text:
        first, rest = text.split(". ", 1)
        if len(first) >= 20 and not rest.lower().startswith(("if ", "when ")):
            text = first

    for pattern in _RATIONALE_RES:
        text = pattern.sub("", text).strip().rstrip(",")

    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"\([^)]*\)", "", text).strip()
        text = re.sub(r"\s{2,}", " ", text)

    if (
        " or " in text
        and len(text.split()) > (max_words or 99)
        and not re.search(r"\bor (?:less|more|fewer|worse)\b", text, re.IGNORECASE)
    ):
        left, _right = text.split(" or ", 1)
        if len(left.split()) >= 6:
            text = left.strip().rstrip(",")

    if max_words and len(text.split()) > max_words:
        words = text.split()[:max_words]
        while words and words[-1].lower() in {"the", "a", "an", "and", "or", "of", "in", "to", "for", "than"}:
            words.pop()
        text = " ".join(words)

    return text.strip()


def sig_note_label(card: dict, sig_id: str) -> str:
    """Format sig_id with a short note label (no ellipsis truncation)."""
    from lib.card_policy_utils import signal_map
    from lib.note_label_templates import template_note_label

    signal = signal_map(card).get(sig_id) or {}
    pathway = str(card.get("causal_pathway") or "")
    expression = str((signal.get("condition") or {}).get("expression") or "")
    short = template_note_label(pathway, sig_id, expression)
    if not short:
        qual = str((signal.get("condition") or {}).get("qualitative_description") or "").strip()
        short = note_label_from_qual(qual)
    if short:
        return f"{sig_id} ({short})"
    variables = ", ".join(signal.get("variables") or [])
    return f"{sig_id} ({variables})" if variables else sig_id


CONTEXTUAL_SIG_RE = re.compile(
    r"(?:prerequisite|redirect|amplif|context|distinction|prioriti|rule out|distinguish)",
    re.IGNORECASE,
)


def strip_redundant_tail_sig_mentions(opening: str, tail: str) -> str:
    """Drop tail list-style repeats of signals already named in the policy opening."""
    if not tail:
        return tail
    tail = re.sub(r"^\s*\.{2,}\)[^.]*\.", "", tail).strip()
    tail = re.sub(r"^\s*…\)[^.]*\.", "", tail).strip()

    opening_ids = {s.lower() for s in SIG_REF_RE.findall(opening)}
    if not opening_ids:
        return tail

    kept: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", tail):
        sent = sentence.strip()
        if not sent:
            continue
        sent_ids = {s.lower() for s in SIG_REF_RE.findall(sent)}
        if (
            sent_ids
            and sent_ids <= opening_ids
            and SIG_PAREN_RE.search(sent)
            and not CONTEXTUAL_SIG_RE.search(sent)
        ):
            continue
        kept.append(sent)
    return " ".join(kept).strip()


def infer_policy_opening(note: str) -> str:
    """Best-effort split between rebuilt policy clauses and contextual tail."""
    text = str(note or "").strip()
    if not text:
        return ""
    for pattern in (
        r"\bAlways (?:verify|probe|distinguish|rule)\b",
        r"\bDistinguish from\b",
        r"\bPrioritise\b",
        r"\bThe alluvial aquifer context\b",
        r"\bThe key distinction\b",
        r"\bWhen rainfall is near-normal\b",
        r"\bIn AER-\d+",
        r"\bRecommended interventions\b",
    ):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match and match.start() > 80:
            return text[: match.start()].strip()
    return ""


def scrub_duplicate_signal_mentions(note: str, *, opening: str = "") -> str:
    """Remove corrupted or repeated sig_XX (...) list fragments in note prose."""
    text = re.sub(r"\s+", " ", str(note or "")).strip()
    if not text:
        return text

    opening = opening or infer_policy_opening(text)

    # Legacy ellipsis-corruption chunks glued after amplifier lists.
    text = re.sub(
        r"\.{3,}\),\s*(?:sig_\d+\s*\([^)]*\)\s*,?\s*)+\.",
        ".",
        text,
    )
    text = re.sub(r"\.{3,}\)[^.]*\.", ".", text)
    text = re.sub(r"\.\s*\.{2,}\)[^.]+\.", ".", text)
    # Orphan list continuations after a closed amplifier sentence: "). ), sig_04 (...), ... )."
    text = re.sub(
        r"\.\s*\),\s*(?:sig_\d+\s*\([^)]*\)\s*,?\s*)+\.\s*\)\.\s*",
        ". ",
        text,
    )
    text = re.sub(r"\.\s*\)\.\s*(?=[A-Z])", ". ", text)

    # Keep only the first amplifier block.
    amp_blocks = list(
        re.finditer(
            r"Amplifying signals\s*\(do not alone confirm\):\s*[^.]+\.",
            text,
            flags=re.IGNORECASE,
        )
    )
    if len(amp_blocks) > 1:
        for match in reversed(amp_blocks[1:]):
            text = text[: match.start()] + text[match.end() :]

    if opening:
        split_at = len(opening)
        if text.startswith(opening):
            tail = strip_redundant_tail_sig_mentions(opening, text[split_at:].strip())
            text = f"{opening} {tail}".strip() if tail else opening
    else:
        # Drop exact duplicate sig_XX (...) spans (second occurrence onward).
        seen_spans: set[str] = set()
        pieces: list[str] = []
        last = 0
        for match in SIG_PAREN_RE.finditer(text):
            pieces.append(text[last : match.start()])
            span = match.group(0)
            norm = re.sub(r"\s+", " ", span.lower())
            if norm not in seen_spans:
                seen_spans.add(norm)
                pieces.append(span)
            last = match.end()
        pieces.append(text[last:])
        text = re.sub(r"\s+", " ", "".join(pieces)).strip()

    text = re.sub(
        r"(?i)\s*Confirmation requires at least (?:one|1|two|2|three|3)[^.]*\.\s*",
        " ",
        text,
    ).strip()

    return re.sub(r"\s+", " ", text).strip()
