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
    # A poll can re-verify the same immutable file after B acted. The first
    # successful verification of this revision is the relevant delivery time.
    mirror = next((x for x in events if x.get("event") == "peer_view_verified"
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
    needs = [score.get("expected_need_evaluator_only"),
             (score.get("measured") or {}).get("saved_forecast_need")]
    needs = [value for value in needs if type(value) in (int, float)]
    direct_numeric_leak = False
    if needs:
        for message in a_messages:
            for token in re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])", message.get("body") or ""):
                try:
                    direct_numeric_leak |= any(float(token) == float(need) for need in needs)
                except ValueError:
                    pass
    b_seen_index, b_read_index = None, None
    desktop_start_indices = []
    for i, event in enumerate(actor_events):
        item = event.get("item") or {}
        if event.get("type") == "item.started" and item.get("server") == "desktop":
            desktop_start_indices.append(i)
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
            title_matches = Path(view).name.casefold() in str(action.get("window_after") or "").casefold()
            # An explicit screenshot call does not sample a window title.
            # Keep it as a weaker candidate for visual inspection, never as
            # automatic proof that the correct revision was displayed.
            if not title_matches and action.get("tool") != "screenshot":
                continue
            number = action.get("n")
            if (not isinstance(number, int) or number < 1 or number > len(desktop_start_indices)
                    or b_seen_index is None or b_read_index is None):
                continue
            action_index = desktop_start_indices[number - 1]
            if action_index <= max(b_seen_index, b_read_index):
                continue
            shot = root / "actor_runs/B/B/shots" / f"{number:03d}.png"
            if shot.is_file():
                candidates.append({"action": number, "time": action.get("screenshot_started_at"),
                                   "stdout_start_index": action_index,
                                   "screenshot": str(shot.relative_to(root)),
                                   "window_after": action.get("window_after"),
                                   "candidate_basis": "matching_window" if title_matches else "explicit_screenshot"})
    # A formula can be typed over several adjacent calls; do not treat a
    # different chunking of identical GUI input as missing prework.
    groups, group = [], []
    for action in b_actions:
        if action.get("tool") == "type_text":
            group.append(action)
        elif action.get("tool") not in {"screenshot", "wait"}:
            if group:
                groups.append(group)
            group = []
    if group:
        groups.append(group)
    formula_groups = [items for items in groups if _general_cost_formula(
        "".join(str((item.get("args") or {}).get("text", "")) for item in items))]
    prework = [x.get("n") for group in formula_groups for x in group
               if mirror and x.get("started_at", 0) < mirror.get("time", 0)]
    pre_view_work = [x.get("n") for group in formula_groups for x in group
                     if candidates and x.get("started_at", 0) < candidates[0]["time"]]
    prework_screenshots = []
    for group in formula_groups:
        last = group[-1]
        number = last.get("n")
        if (not candidates or not isinstance(number, int)
                or last.get("screenshot_started_at", 0) >= candidates[0]["time"]
                or "order_plan.ods" not in str(last.get("window_after") or "").casefold()):
            continue
        shot = root / "actor_runs/B/B/shots" / f"{number:03d}.png"
        if shot.is_file():
            prework_screenshots.append({"action": number, "time": last.get("screenshot_started_at"),
                                        "screenshot": str(shot.relative_to(root)),
                                        "window_after": last.get("window_after")})
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
            "B_formula_prework_screenshot_candidates": prework_screenshots,
            "B_peer_view_screenshot_candidates": candidates,
            "B_saved_revision_after_view_candidate": b_saved_after_view,
            "visual_read_verified": False,
            "review_required": "Human must inspect candidate screenshot and chronology for visible correct H3 and review all noncanonical A messages; metadata or window title alone does not prove reading."}


if __name__ == "__main__":
    print(json.dumps(audit(Path(sys.argv[1])), indent=2))
