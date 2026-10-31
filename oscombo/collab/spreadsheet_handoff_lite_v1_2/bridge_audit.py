"""Inspect persistent bridge events and unfinished revision state after stop."""
from __future__ import annotations
import json
from pathlib import Path


def audit_bridge_history(root: Path, final_versions: dict) -> dict:
    log = root / "events.jsonl"
    failures, unknown_failures, parse_errors, unfinished = [], [], [], []
    # These are classified from the durable event stream by the common bridge
    # diagnostics, including whether a save-validation retry later recovered.
    classified = {"sync_error", "transfer_error", "peer_view_error", "peer_view_conflict",
                  "ownership_or_sync_conflict", "guest_read_error", "guest_probe_error"}
    try:
        with log.open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                try:
                    item = json.loads(line)
                    if not isinstance(item, dict) or not isinstance(item.get("event"), str):
                        raise ValueError("event must be an object with a name")
                    name = item["event"]
                    if (name.endswith("_error") or name.endswith("_conflict")
                            or name.endswith("_failed") or name in {"sync_error", "publication_failed"}):
                        failures.append(item)
                        if name not in classified:
                            unknown_failures.append(item)
                except (ValueError, TypeError) as exc:
                    parse_errors.append({"file": "events.jsonl", "line": number, "error": str(exc)})
    except OSError as exc:
        parse_errors.append({"file": "events.jsonl", "error": str(exc)})
    for role in ("A", "B"):
        pending_path = root / f"pending-{role}.json"
        if not pending_path.exists():
            continue
        try:
            pending = json.loads(pending_path.read_text())
            if not isinstance(pending, list):
                raise ValueError("pending state is not a list")
            current = final_versions.get(role) or {}
            committed = current.get("revision", -1)
            if not isinstance(committed, int):
                raise ValueError("committed revision is invalid")
            for entry in pending:
                if (not isinstance(entry, dict) or not isinstance(entry.get("revision"), int)
                        or not isinstance(entry.get("sha256"), str)):
                    raise ValueError("pending revision is invalid")
                if entry["revision"] > committed:
                    unfinished.append({"actor": role, **entry})
        except (OSError, ValueError, TypeError) as exc:
            parse_errors.append({"file": pending_path.name, "error": str(exc)})
    undelivered = [role for role in ("A", "B")
                   if not isinstance(final_versions.get(role), dict)
                   or final_versions[role].get("delivered") is not True]
    return {"persistent_errors": failures, "unknown_persistent_errors": unknown_failures,
            "unresolved_pending": unfinished,
            "parse_errors": parse_errors, "undelivered_roles": undelivered,
            "history_clean": not (unknown_failures or unfinished or parse_errors or undelivered),
            "scope": "Bridge diagnostics classifies known faults and recovered save retries; pending records at or below committed revisions are normal."}
