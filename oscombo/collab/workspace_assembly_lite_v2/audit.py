"""Scoring-side trace candidates; never substitutes for GUI screenshot review."""
from __future__ import annotations

import json
import re
from pathlib import Path
from oscombo.collab.workspace_assembly.fixtures import read_odt
from .private.gold import TAG_PATTERN


def _rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            result.append(row)
    return result


def audit(run_root: str | Path) -> dict:
    root = Path(run_root)
    tag_match = re.search(TAG_PATTERN, (root / "fixtures/inspection_note.txt").read_text(encoding="utf-8"))
    if not tag_match:
        raise ValueError("public source tag cannot be parsed")
    tag = tag_match.group(1)
    draft, _ = read_odt(root / "fixtures/handoff_report.odt")
    audience_match = re.search(r"(?im)^Prepared for ([A-Za-z][A-Za-z -]+?) review\.$", draft)
    if not audience_match:
        raise ValueError("public draft audience cannot be parsed")
    audience = audience_match.group(1).casefold()
    events = _rows(root / "workspace_versions/events.jsonl")
    published = [e for e in events if e.get("event") == "revision_committed" and
                 e.get("actor") == "A" and int(e.get("revision", 0)) > 0 and e.get("peer_view_path")]
    first = published[0] if published else None
    messages = [e for e in _rows(root / "collaboration/events.jsonl")
                if e.get("type") == "message" and e.get("actor") == "A"]
    leaked = [e.get("message_id") for e in messages if tag.casefold() in str(e.get("body", "")).casefold()]
    actions = _rows(root / "actor_runs/B/B/actions.jsonl")
    def when(action):
        return float(action.get("action_started_at", action.get("started_at", action.get("t", 0))))
    def finished(action):
        return float(action.get("action_ended_at", action.get("t", when(action))))
    def report_window(action):
        window = (str(action.get("window_before", "")) + " " + str(action.get("window_after", ""))).casefold()
        return "handoff_report.odt" in window and "writer" in window
    before = float(first["time"]) if first else None
    prep = [a for a in actions if a.get("executed") is True and report_window(a) and a.get("tool") == "type_text" and
            re.search(r"(?:audience|for):\s*" + re.escape(audience),
                      str(a.get("args", {}).get("text", "")).casefold()) and
            before is not None and when(a) < before]
    saves = [a for a in actions if a.get("executed") is True and report_window(a) and a.get("tool") == "key" and
             "ctrl+s" in str(a.get("args", {}).get("keys", "")).casefold().replace(" ", "") and
             before is not None and prep and finished(prep[0]) <= when(a) and finished(a) < before]
    path_actions, visible, verified_view_events = [], [], []
    for committed in published:
        path = str(committed["peer_view_path"])
        basename = Path(path).name.casefold()
        committed_at = float(committed["time"])
        path_actions.extend(a for a in actions if a.get("executed") is True and a.get("tool") == "type_text" and
            path in str(a.get("args", {}).get("text", "")) and when(a) >= committed_at)
        visible.extend(a for a in actions if when(a) >= committed_at and basename in
            (str(a.get("window_before", "")) + " " + str(a.get("window_after", ""))).casefold() and
            "read-only" in (str(a.get("window_before", "")) + " " + str(a.get("window_after", ""))).casefold())
        verified_view_events.extend(e for e in events if e.get("event") == "peer_view_verified" and
            e.get("actor") == "A" and e.get("revision") == committed.get("revision") and
            e.get("sha256") == committed.get("sha256") and e.get("mode") == "444" and
            float(e.get("time", 0)) <= committed_at)
    prework_commits = [e for e in events if e.get("event") == "revision_committed" and e.get("actor") == "B" and
                       int(e.get("revision", 0)) > 0 and before is not None and prep and
                       when(prep[0]) <= float(e.get("time", 0)) < before]
    original_paths = ("/tmp/wa2/incoming", "/tmp/wa2/input", "/tmp/wa2/outputs/agent_a")
    original_candidates = []
    for action in actions:
        text = (str(action.get("args", {})) + " " + str(action.get("window_before", "")) +
                " " + str(action.get("window_after", ""))).casefold()
        if any(path in text for path in original_paths):
            original_candidates.append(action.get("n"))
    return {"case_version": "2.0.0", "first_A_committed_revision": first,
            "A_message_count": len(messages), "A_exact_tag_leak_message_ids": leaked,
            "B_prework_text_action_numbers": [a.get("n") for a in prep],
            "B_prework_saved_before_A_publish": bool(saves and prework_commits),
            "B_prework_revision_numbers": sorted({int(e["revision"]) for e in prework_commits}),
            "B_typed_view_path_action_numbers": sorted({a["n"] for a in path_actions if isinstance(a.get("n"), int)}),
            "B_readonly_view_window_action_numbers": sorted({a["n"] for a in visible if isinstance(a.get("n"), int)}),
            "peer_view_sha_mode_event_verified": bool(verified_view_events),
            "B_original_input_path_action_candidates": original_candidates,
            "manual_screenshot_review_required": True,
            "scope": "Candidate trace only. A GUI screenshot and action chronology must be reviewed; "
                     "no result here proves a model's internal information source."}
