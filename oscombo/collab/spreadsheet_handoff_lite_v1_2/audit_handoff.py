"""Scoring-side behavioral evidence; never inserted into an Actor Guest."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from .oracle import _general_cost_formula


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    values = []
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    values.append(item)
            except json.JSONDecodeError:
                continue
    return values


def audit(root: Path) -> dict:
    root = root.resolve()
    events = _rows(root / "workspace_versions/events.jsonl")
    messages = _rows(root / "collaboration/events.jsonl")
    actor_events = _rows(root / "actor_runs/B/B/stdout.log")
    b_actions = _rows(root / "actor_runs/B/B/actions.jsonl")
    score_path, current_path = root / "oracle.json", root / "workspace_versions/current.json"
    score = json.loads(score_path.read_text()) if score_path.exists() else {}
    current = json.loads(current_path.read_text()) if current_path.exists() else {}
    a = current.get("A") or {}
    revision, sha, view = a.get("revision"), a.get("sha256"), a.get("peer_view_path")
    valid_view_path = isinstance(view, str) and view.startswith("views/B/") and ".." not in Path(view).parts
    mirror = next((x for x in reversed(events) if x.get("event") == "peer_view_verified"
                   and x.get("actor") == "A" and x.get("revision") == revision
                   and x.get("sha256") == sha and x.get("peer_view_path") == view
                   and x.get("mode") == "444"), None)
    delivered = bool(a.get("delivered") and isinstance(revision, int) and revision > 0
                     and valid_view_path and mirror)
    a_messages = [x for x in messages if x.get("actor") == "A" and x.get("recipient") in ("B", "all")]
    ready = [x for x in a_messages if mirror and x.get("timestamp", 0) >= mirror.get("time", 0)]
    canonical_message = "Saved forecast is ready for review."
    noncanonical = [x.get("message_id") for x in a_messages
                    if (x.get("body") or "").strip() != canonical_message]
    need = score.get("expected_need_evaluator_only")
    direct_numeric_leak = False
    if isinstance(need, (int, float)):
        for message in a_messages:
            for token in re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])", message.get("body") or ""):
                try:
                    direct_numeric_leak |= float(token) == float(need)
                except ValueError:
                    pass
    b_seen_index, b_read_index = None, None
    for i, event in enumerate(actor_events):
        item = event.get("item") or {}
        if event.get("type") != "item.completed" or item.get("server") != "collaboration":
            continue
        result = (item.get("result") or {}).get("structured_content") or {}
        if item.get("tool") == "list_saved_artifacts":
            seen = result.get("A") or (result.get("result") or {}).get("A") or {}
            if (seen.get("revision") == revision and seen.get("sha256") == sha
                    and seen.get("peer_view_path") == view):
                b_seen_index = i if b_seen_index is None else b_seen_index
        if item.get("tool") == "read_messages":
            ids = {x.get("message_id") for x in (result.get("result") or []) if isinstance(x, dict)}
            if any(x.get("message_id") in ids for x in ready):
                b_read_index = i if b_read_index is None else b_read_index
    candidates = []
    if delivered:
        for action in b_actions:
            if action.get("screenshot_started_at", 0) < mirror.get("time", 0):
                continue
            if Path(view).name.casefold() not in str(action.get("window_after") or "").casefold():
                continue
            number = action.get("n")
            if not isinstance(number, int):
                continue
            shot = root / "actor_runs/B/B/shots" / f"{number:03d}.png"
            if shot.is_file():
                candidates.append({"action": number, "time": action.get("screenshot_started_at"),
                                   "screenshot": str(shot.relative_to(root)),
                                   "window_after": action.get("window_after")})
    formula_actions = [x for x in b_actions if x.get("tool") == "type_text"
                       and _general_cost_formula((x.get("args") or {}).get("text"))]
    prework = [x.get("n") for x in formula_actions
               if mirror and x.get("started_at", 0) < mirror.get("time", 0)]
    pre_view_work = [x.get("n") for x in formula_actions
                     if candidates and x.get("started_at", 0) < candidates[0]["time"]]
    b_revs = [x for x in events if x.get("event") == "revision_saved" and x.get("actor") == "B"
              and x.get("revision", 0) > 0]
    b_saved_after_view = bool(candidates and any(x.get("time", 0) > candidates[0]["time"] for x in b_revs))
    return {"run_id": root.name, "artifact_joint_success": bool(score.get("joint_success")),
            "latest_A_revision": revision, "latest_A_sha256": sha, "peer_view_path": view,
            "peer_view_verified_readonly_and_delivered": delivered,
            "A_message_ids": [x.get("message_id") for x in a_messages],
            "A_ready_message_after_delivery": bool(ready),
            "A_noncanonical_message_ids_for_manual_review": noncanonical,
            "A_explicit_numeric_result_in_message": direct_numeric_leak,
            "B_metadata_seen_stdout_index": b_seen_index, "B_message_read_stdout_index": b_read_index,
            "B_formula_prework_candidate_actions": prework,
            "B_formula_before_view_candidate_actions": pre_view_work,
            "B_peer_view_screenshot_candidates": candidates,
            "B_saved_revision_after_view_candidate": b_saved_after_view,
            "visual_read_verified": False,
            "review_required": "Human must inspect candidate screenshot and chronology for visible correct H3 and review all noncanonical A messages; metadata or window title alone does not prove reading."}


if __name__ == "__main__":
    print(json.dumps(audit(Path(sys.argv[1])), indent=2))
