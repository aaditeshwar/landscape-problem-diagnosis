#!/usr/bin/env python3
"""Prune diagnosis JSONL logs and optionally remap query-eval log_index references.

Examples:
  # Keep only events referenced by query-eval batches (local tidy-up)
  python scripts/maintenance/cleanup_diagnosis_logs.py --only-query-eval

  # Delete everything (with backup)
  python scripts/maintenance/cleanup_diagnosis_logs.py --all

  # Delete events before a UTC date, but keep query-eval rows
  python scripts/maintenance/cleanup_diagnosis_logs.py --before 2026-06-01 --keep-query-eval

  # Delete particular sessions
  python scripts/maintenance/cleanup_diagnosis_logs.py --session-ids session_abc,session_def

  # Preview without writing
  python scripts/maintenance/cleanup_diagnosis_logs.py --only-query-eval --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

bootstrap(runtime=True)

from config import LOG_DIR  # noqa: E402
from services.query_eval_store import EVAL_DIR  # noqa: E402

SESSION_ID_RE = re.compile(r"^session_[0-9a-f]+$")


def _jsonl_path() -> Path:
    return Path(LOG_DIR) / "diagnosis.jsonl"


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _walk_json(node: Any, visitor) -> None:
    if isinstance(node, dict):
        visitor(node)
        for value in node.values():
            _walk_json(value, visitor)
    elif isinstance(node, list):
        for item in node:
            _walk_json(item, visitor)


def collect_query_eval_refs() -> tuple[set[int], set[str]]:
    """Return (log_indices, session_ids) referenced by query-eval artifacts."""
    indices: set[int] = set()
    sessions: set[str] = set()
    if not EVAL_DIR.is_dir():
        return indices, sessions

    def visitor(obj: dict[str, Any]) -> None:
        log_index = obj.get("log_index")
        if isinstance(log_index, int) and log_index >= 0:
            indices.add(log_index)
        session_id = str(obj.get("session_id") or "").strip()
        if SESSION_ID_RE.fullmatch(session_id):
            sessions.add(session_id)

    for manifest_path in sorted(EVAL_DIR.glob("*/manifest.json")):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        _walk_json(payload, visitor)
        batch_dir = manifest_path.parent
        for artifact in sorted(batch_dir.glob("responses/*.json")):
            try:
                _walk_json(json.loads(artifact.read_text(encoding="utf-8")), visitor)
            except (OSError, json.JSONDecodeError):
                continue
        for artifact in sorted(batch_dir.glob("evaluations/*.json")):
            try:
                _walk_json(json.loads(artifact.read_text(encoding="utf-8")), visitor)
            except (OSError, json.JSONDecodeError):
                continue
    return indices, sessions


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                event = json.loads(text)
            except json.JSONDecodeError:
                event = {"parse_error": True, "line_no": line_no, "raw": text[:500]}
            events.append(event)
    return events


def indices_to_delete(
    events: list[dict[str, Any]],
    *,
    delete_all: bool,
    before: datetime | None,
    session_ids: set[str],
    keep_query_eval: bool,
    query_eval_indices: set[int],
) -> set[int]:
    to_delete: set[int] = set()
    for index, event in enumerate(events):
        if keep_query_eval and index in query_eval_indices:
            continue

        if delete_all:
            to_delete.add(index)
            continue

        if before is not None:
            ts = _parse_ts(event.get("timestamp"))
            if ts is not None and ts < before:
                to_delete.add(index)
                continue

        if session_ids:
            sid = str(event.get("session_id") or "").strip()
            if sid in session_ids:
                to_delete.add(index)

    return to_delete


def rewrite_feedback_url(url: str, mapping: dict[int, int]) -> str:
    if not url or "log_index=" not in url:
        return url
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    raw = query.get("log_index", [None])[0]
    if raw is None:
        return url
    try:
        old = int(raw)
    except ValueError:
        return url
    if old not in mapping:
        return url
    query["log_index"] = [str(mapping[old])]
    new_query = urlencode({key: values[0] for key, values in query.items()})
    return urlunparse(parsed._replace(query=new_query))


def update_query_eval_artifacts(mapping: dict[int, int], *, dry_run: bool) -> list[str]:
    if not mapping:
        return []

    changed: list[str] = []

    def patch_node(obj: dict[str, Any]) -> None:
        if "log_index" in obj:
            old = obj.get("log_index")
            if isinstance(old, int) and old in mapping:
                obj["log_index"] = mapping[old]
        if isinstance(obj.get("feedback_url"), str):
            obj["feedback_url"] = rewrite_feedback_url(obj["feedback_url"], mapping)

    for manifest_path in sorted(EVAL_DIR.glob("*/manifest.json")):
        batch_dir = manifest_path.parent
        targets = [
            manifest_path,
            *sorted(batch_dir.glob("responses/*.json")),
            *sorted(batch_dir.glob("evaluations/*.json")),
        ]
        for path in targets:
            if not path.is_file():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            before = json.dumps(payload, sort_keys=True)
            _walk_json(payload, patch_node)
            after = json.dumps(payload, sort_keys=True)
            if before == after:
                continue
            changed.append(str(path.relative_to(ROOT)))
            if not dry_run:
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def write_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    lines = [json.dumps(event, ensure_ascii=False) for event in events]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def backup_file(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_suffix(path.suffix + f".bak.{stamp}")
    backup.write_bytes(path.read_bytes())
    return backup


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prune diagnosis JSONL logs.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--all", action="store_true", help="Delete all log events (subject to --keep-query-eval).")
    mode.add_argument(
        "--only-query-eval",
        action="store_true",
        help="Delete every event except those referenced by query-eval batches.",
    )
    parser.add_argument(
        "--before",
        metavar="YYYY-MM-DD",
        help="Delete events with timestamp strictly before this UTC date.",
    )
    parser.add_argument(
        "--session-ids",
        metavar="ID[,ID...]",
        help="Delete events whose session_id is in this comma-separated list.",
    )
    parser.add_argument(
        "--keep-query-eval",
        action="store_true",
        help="Never delete events referenced by query-eval batches.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing files.")
    parser.add_argument("--no-backup", action="store_true", help="Skip creating a .bak copy of diagnosis.jsonl.")
    parser.add_argument(
        "--skip-query-eval-remap",
        action="store_true",
        help="Do not rewrite log_index values inside reports/query_eval after compaction.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    jsonl_path = _jsonl_path()
    events = load_events(jsonl_path)
    if not events:
        print(f"No events found at {jsonl_path}")
        return 0

    query_eval_indices, query_eval_sessions = collect_query_eval_refs()

    delete_all = bool(args.all or args.only_query_eval)
    keep_query_eval = bool(args.keep_query_eval or args.only_query_eval)
    before: datetime | None = None
    if args.before:
        before = datetime.fromisoformat(args.before).replace(tzinfo=timezone.utc)
    session_ids = {part.strip() for part in str(args.session_ids or "").split(",") if part.strip()}

    if not delete_all and before is None and not session_ids:
        print("Specify a delete mode: --all, --only-query-eval, --before, and/or --session-ids.")
        return 2

    to_delete = indices_to_delete(
        events,
        delete_all=delete_all,
        before=before,
        session_ids=session_ids,
        keep_query_eval=keep_query_eval,
        query_eval_indices=query_eval_indices,
    )

    kept = [event for index, event in enumerate(events) if index not in to_delete]
    mapping: dict[int, int] = {}
    new_index = 0
    for old_index in range(len(events)):
        if old_index in to_delete:
            continue
        mapping[old_index] = new_index
        new_index += 1

    print(f"Log file: {jsonl_path}")
    print(f"Total events: {len(events)}")
    print(f"Query-eval referenced indices: {sorted(query_eval_indices)}")
    print(f"Query-eval referenced sessions: {len(query_eval_sessions)}")
    print(f"Delete: {len(to_delete)} | Keep: {len(kept)}")
    if to_delete:
        preview = sorted(to_delete)[:12]
        suffix = " ..." if len(to_delete) > 12 else ""
        print(f"Deleting indices: {preview}{suffix}")
    if mapping and any(old != new for old, new in mapping.items()):
        changed = {old: new for old, new in mapping.items() if old != new}
        preview = list(changed.items())[:8]
        print(f"Index remap (old->new): {preview}{' ...' if len(changed) > 8 else ''}")

    if not to_delete:
        print("Nothing to delete.")
        return 0

    if args.dry_run:
        changed_artifacts = update_query_eval_artifacts(mapping, dry_run=True) if not args.skip_query_eval_remap else []
        if changed_artifacts:
            print(f"Would update {len(changed_artifacts)} query-eval artifact(s).")
        print("Dry run — no files written.")
        return 0

    if not args.no_backup and jsonl_path.is_file():
        backup = backup_file(jsonl_path)
        print(f"Backup: {backup}")

    write_jsonl(jsonl_path, kept)
    print(f"Wrote {len(kept)} event(s) to {jsonl_path}")

    if not args.skip_query_eval_remap and mapping:
        changed_artifacts = update_query_eval_artifacts(mapping, dry_run=False)
        if changed_artifacts:
            print(f"Updated query-eval artifacts ({len(changed_artifacts)}):")
            for rel in changed_artifacts[:20]:
                print(f"  - {rel}")
            if len(changed_artifacts) > 20:
                print(f"  ... and {len(changed_artifacts) - 20} more")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
