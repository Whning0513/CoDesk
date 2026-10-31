"""Audit actual model tool calls and relay status without logging prompt contents."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path


def audit(root: Path) -> dict:
    errors = []
    events_path = root / "codex_relay_events.jsonl"
    events = []
    if not events_path.is_file():
        errors.append("relay event log missing")
    else:
        with events_path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    item = json.loads(line)
                    if not isinstance(item, dict):
                        raise ValueError("non-object event")
                    events.append(item)
                except ValueError:
                    errors.append("malformed relay event")
    by_role = Counter(e.get("actor") for e in events)
    if any(by_role[role] == 0 for role in "AB"):
        errors.append("both Actors require real relay requests")
    if any(e.get("actor_mcp_only") is not True for e in events):
        errors.append("request-level tool allowlist missing")
    if any(e.get("upstream_status") != 200 for e in events):
        errors.append("upstream response missing or not HTTP 200; review transport")
    call_types = {"mcp_tool_call", "command_execution", "file_change", "web_search",
                  "collab_tool_call", "dynamic_tool_call", "tool_call", "function_call", "custom_tool_call"}
    seen = {"A": set(), "B": set()}
    counts = Counter()
    for role in "AB":
        path = root / f"actor_runs/{role}/{role}/stdout.log"
        if not path.is_file():
            errors.append(f"Actor {role} transcript missing")
            continue
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(event, dict):
                    errors.append(f"Actor {role} transcript has a non-object event")
                    continue
                item = event.get("item") or {}
                if not isinstance(item, dict):
                    errors.append(f"Actor {role} transcript has a malformed item")
                    continue
                kind = str(item.get("type", ""))
                if event.get("type") not in {"item.started", "item.completed"}:
                    continue
                if kind not in call_types and not kind.endswith("_tool_call"):
                    continue
                identity = item.get("id")
                if identity is None:
                    errors.append(f"Actor {role} tool call is missing its ID")
                    continue
                if identity in seen[role]:
                    continue
                seen[role].add(identity)
                server = item.get("server")
                counts[f"{role}:{kind}:{server}"] += 1
                if kind != "mcp_tool_call" or server not in {"desktop", "collaboration"}:
                    errors.append(f"Actor {role} used disallowed tool type/server: {kind}/{server}")
        if not seen[role]:
            errors.append(f"Actor {role} has no recorded tool calls")
    return {"valid": not errors, "errors": errors, "relay_requests_by_actor": dict(by_role),
            "actor_tool_calls": dict(counts), "scope": "request and recorded tool boundary; no prompt or credential values emitted"}


if __name__ == "__main__":
    import sys
    path = Path(sys.argv[1]).resolve()
    result = audit(path)
    (path / "contract_audit.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result))
    raise SystemExit(0 if result["valid"] else 3)
