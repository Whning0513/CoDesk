"""Fail-closed transport evidence for Case 6 v1.2 model episodes.

Relay events contain metadata only. A provider HTTP 200 is insufficient when
the stream ends without a completed Responses event or the relay records an
exception after forwarding headers or bytes.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path


def relay_event_clean(event: object) -> bool:
    """Require completed, delivered and allowlisted evidence for every request."""
    return (isinstance(event, dict)
            and type(event.get("actor")) is str and event["actor"] in {"A", "B"}
            and event.get("actor_mcp_only") is True
            and type(event.get("upstream_status")) is int and event["upstream_status"] == 200
            and "error_type" not in event and "phase" not in event
            and event.get("headers_sent") is True
            and type(event.get("forwarded_bytes")) is int and event["forwarded_bytes"] > 0
            and type(event.get("response_evidence_version")) is int
            and event["response_evidence_version"] == 1
            and event.get("response_format") in {"sse", "json"}
            and event.get("response_terminal") == "response.completed")


def audit(root: Path) -> dict:
    """Return a compact audit without logging request, response or credentials."""
    path = root / "codex_relay_events.jsonl"
    events: list[dict] = []
    malformed = 0
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                malformed += 1
                continue
            if isinstance(event, dict):
                events.append(event)
            else:
                malformed += 1
    counts = Counter(event.get("actor") if type(event.get("actor")) is str else "<invalid>"
                     for event in events)
    failures = sum(not relay_event_clean(event) for event in events)
    errors = []
    if not path.is_file():
        errors.append("relay event log missing")
    if malformed:
        errors.append("malformed relay event")
    if any(counts[role] == 0 for role in ("A", "B")):
        errors.append("both Actors require real relay requests")
    if failures:
        errors.append("relay error or incomplete/ambiguous Responses terminal evidence")
    return {"valid": not errors, "errors": errors,
            "requests_by_actor": {role: counts[role] for role in ("A", "B")},
            "event_count": len(events), "invalid_event_count": failures,
            "malformed_event_count": malformed,
            "scope": "all recorded relay requests; no request, response or credential content emitted"}


def audit_and_mark(root: Path) -> dict:
    """Mark a new run infrastructure-invalid if its model stream is unverified."""
    result = audit(root)
    (root / "relay_transport_audit.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if not result["valid"]:
        path = root / "result.json"
        if path.is_file():
            episode = json.loads(path.read_text())
            if episode.get("status") in {"PASS", "FAIL"}:
                episode["pre_transport_status"] = episode["status"]
            episode["status"] = "INVALID_INFRA_OR_RUNNER_ERROR"
            episode["infrastructure_audit_error"] = "model relay transport or terminal evidence invalid"
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(episode, indent=2, sort_keys=True) + "\n")
            temporary.replace(path)
    return result


if __name__ == "__main__":
    import sys
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_root", type=Path)
    args = parser.parse_args()
    outcome = audit_and_mark(args.run_root)
    print(json.dumps(outcome, sort_keys=True))
    sys.exit(0 if outcome["valid"] else 3)
