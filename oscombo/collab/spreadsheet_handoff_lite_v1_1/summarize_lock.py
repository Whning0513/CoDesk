"""Summarize Case 6 Shared GUI-call mutex cost from preserved Actor action logs."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def summarize(root: Path) -> dict:
    records = {role: [row for row in _rows(root / "actor_runs" / role / role / "actions.jsonl")
                      if row.get("executed") and row.get("code")]
               for role in "AB"}
    per_role = {}
    for role, rows in records.items():
        locked = [row.get("input_lock") or {} for row in rows]
        waits = [float(item.get("wait_s") or 0) for item in locked if item.get("enabled")]
        holds = [float(item.get("held_s") or 0) for item in locked if item.get("enabled")]
        per_role[role] = {
            "input_calls": len(rows),
            "locked_input_calls": len(waits),
            "lock_wait_total_s": round(sum(waits), 3),
            "lock_wait_max_s": round(max(waits, default=0), 3),
            "lock_held_total_s": round(sum(holds), 3),
        }
    a_intervals = [(float(x["action_started_at"]), float(x["action_ended_at"]))
                   for x in records["A"] if x.get("action_started_at") and x.get("action_ended_at")]
    b_intervals = [(float(x["action_started_at"]), float(x["action_ended_at"]))
                   for x in records["B"] if x.get("action_started_at") and x.get("action_ended_at")]
    overlap = sum(max(0.0, min(a1, b1) - max(a0, b0))
                  for a0, a1 in a_intervals for b0, b1 in b_intervals)
    all_locked = bool(sum(x["input_calls"] for x in per_role.values())
                      and all(x["input_calls"] == x["locked_input_calls"]
                              for x in per_role.values()))
    return {
        "run_id": root.name,
        "roles": per_role,
        "cross_actor_gui_input_overlap_s": round(overlap, 3),
        "lock_enabled_for_all_input_calls": all_locked,
        "lock_serialization_violated": bool(all_locked and overlap > 0.001),
        "scope": "Only GUI input action intervals; screenshots and model requests are separate.",
    }


if __name__ == "__main__":
    print(json.dumps(summarize(Path(sys.argv[1]).resolve()), indent=2))
