"""Scorer-side Case 6 revision/message/GUI audit; never staged in an Actor Guest."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    result = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            result.append(item)
    return result


def audit(root: Path) -> dict:
    root = root.resolve()
    bridge = _jsonl(root / "workspace_versions/events.jsonl")
    messages = _jsonl(root / "collaboration/events.jsonl")
    stdout = _jsonl(root / "actor_runs/B/B/stdout.log")
    oracle_path = root / "oracle.json"
    oracle = json.loads(oracle_path.read_text()) if oracle_path.exists() else {}
    a_revs = [x for x in bridge if x.get("event") == "revision_saved"
              and x.get("actor") == "A" and x.get("revision", 0) > 0]
    b_revs = [x for x in bridge if x.get("event") == "revision_saved"
              and x.get("actor") == "B" and x.get("revision", 0) > 0]
    a_rev = a_revs[-1] if a_revs else None
    b_rev = b_revs[-1] if b_revs else None
    a_messages = [x for x in messages if x.get("actor") == "A"
                  and x.get("recipient") in ("B", "all") and a_rev
                  and x.get("timestamp", 0) > a_rev.get("time", 0)]
    a_message = a_messages[-1] if a_messages else None
    transfers = [x for x in bridge if x.get("event") == "transfer_verified"
                 and x.get("actor") == "A" and a_rev
                 and x.get("revision") == a_rev.get("revision")
                 and x.get("sha256") == a_rev.get("sha256")]
    a_delivered = bool(a_rev and (a_rev.get("delivered") or transfers))

    b_seen_revision_index = None
    b_read_message_index = None
    b_post_handoff_gui_index = None
    for i, event in enumerate(stdout):
        item = event.get("item") or {}
        if event.get("type") == "item.completed" and item.get("server") == "collaboration":
            result = (item.get("result") or {}).get("structured_content") or {}
            if item.get("tool") == "list_saved_artifacts" and a_rev:
                observed = result.get("A") or (result.get("result") or {}).get("A") or {}
                if (observed.get("revision", 0) >= a_rev["revision"]
                        and observed.get("sha256") == a_rev.get("sha256")):
                    b_seen_revision_index = i if b_seen_revision_index is None else b_seen_revision_index
            if item.get("tool") == "read_messages" and a_message:
                records = result.get("result") or []
                if any(x.get("message_id") == a_message.get("message_id")
                       for x in records if isinstance(x, dict)):
                    b_read_message_index = i if b_read_message_index is None else b_read_message_index
        if (event.get("type") == "item.started" and item.get("server") == "desktop"
                and item.get("tool") in {"click", "type_text", "key", "drag"}
                and b_seen_revision_index is not None and b_read_message_index is not None
                and i > max(b_seen_revision_index, b_read_message_index)
                and b_post_handoff_gui_index is None):
            b_post_handoff_gui_index = i

    b_saved_after_handoff = bool(b_rev and a_message and b_rev.get("time", 0) > a_message.get("timestamp", 0))
    artifact_success = bool(oracle.get("joint_success"))
    trace_consistent = bool(a_delivered and a_message and b_seen_revision_index is not None
                            and b_read_message_index is not None
                            and b_post_handoff_gui_index is not None
                            and b_saved_after_handoff and artifact_success)
    return {
        "run_id": root.name,
        "artifact_joint_success": artifact_success,
        "a_latest_revision": {k: a_rev.get(k) for k in ("revision", "sha256", "time")} if a_rev else None,
        "a_message_after_latest_revision": {k: a_message.get(k) for k in ("message_id", "timestamp")}
        if a_message else None,
        "a_latest_revision_delivered": a_delivered,
        "a_latest_revision_transfer_count": len(transfers),
        "b_observed_latest_revision_stdout_index": b_seen_revision_index,
        "b_read_latest_a_message_stdout_index": b_read_message_index,
        "b_first_gui_action_after_both_reads_stdout_index": b_post_handoff_gui_index,
        "b_saved_revision": {k: b_rev.get(k) for k in ("revision", "sha256", "time")} if b_rev else None,
        "b_saved_after_handoff": b_saved_after_handoff,
        "trace_consistent_handoff": trace_consistent,
        "limit": "This chronology supports use of the public handoff; it cannot prove the model's internal reasoning. Review screenshots and final cells as well.",
    }


if __name__ == "__main__":
    result = audit(Path(sys.argv[1]))
    print(json.dumps(result, indent=2))
