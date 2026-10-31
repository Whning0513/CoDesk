"""Conservative, read-only GUI handoff and simple-lock audit for Case 7 runs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def _document(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def _gui_reads(actions: list[dict], visible_after: float | None = None) -> list[dict]:
    evidence = []
    for row in actions:
        title = f"{row.get('window_before') or ''} {row.get('window_after') or ''}"
        started = row.get("action_started_at") or row.get("started_at") or row.get("t", 0)
        if ("inspection_note.txt" in title and "/outputs/agent_A" in title
                and (visible_after is None or started >= visible_after)):
            evidence.append({"step": row.get("n"), "time": started,
                             "window_before": row.get("window_before"),
                             "window_after": row.get("window_after")})
    return evidence


def _gui_path_open_candidates(actions: list[dict], visible_after: float | None,
                              root: Path) -> list[dict]:
    """Flag path-entry plus a later read-only viewer for screenshot review."""
    if visible_after is None:
        return []
    candidates = []
    delivered = "/outputs/agent_A/inspection_note.txt"
    for index, row in enumerate(actions):
        started = row.get("action_started_at") or row.get("started_at") or row.get("t", 0)
        entered = str((row.get("args") or {}).get("text") or "")
        if (row.get("tool") != "type_text" or delivered not in entered
                or started < visible_after or "Open" not in str(row.get("window_before") or "")):
            continue
        following = actions[index + 1:index + 5]
        submitted = next((item for item in following if item.get("tool") == "key" and
                          str((item.get("args") or {}).get("keys") or "").casefold()
                          in {"return", "enter"}), None)
        if submitted is None:
            continue
        opened = next((item for item in following if item.get("n", 0) > submitted.get("n", 0)
                       and "inspection_note.txt (read-only)" in
                       f"{item.get('window_before') or ''} {item.get('window_after') or ''}"), None)
        if opened is None:
            continue
        shot = root / f"actor_runs/B/B/shots/{int(opened['n']):03d}.png"
        candidates.append({"path_step": row.get("n"), "submit_step": submitted.get("n"),
                           "viewer_step": opened.get("n"), "viewer_time": opened.get("action_started_at"),
                           "viewer_title": opened.get("window_before") or opened.get("window_after"),
                           "screenshot": str(shot.relative_to(root)) if shot.exists() else None,
                           "requires_visual_review": True})
    return candidates


def audit(root: Path) -> dict:
    provenance = _document(root / "provenance.json")
    oracle = _document(root / "oracle.json")
    revisions = _rows(root / "workspace_versions/events.jsonl")
    messages = _rows(root / "collaboration/events.jsonl")
    actions = {role: _rows(root / f"actor_runs/{role}/{role}/actions.jsonl") for role in "AB"}
    shared = provenance.get("condition") == "collaborative_shared"
    a_saved = next((row for row in revisions if row.get("event") == "revision_saved"
                    and row.get("actor") == "A" and row.get("revision", 0) >= 1), None)
    a_visible = next((row for row in revisions if row.get("event") == "transfer_verified"
                      and row.get("actor") == "A" and row.get("revision", 0) >= 1), None)
    a_visible_time = (a_saved.get("time") if shared and a_saved else
                      a_visible.get("time") if a_visible else None)
    a_message = next((row for row in messages if row.get("type") == "message"
                      and row.get("actor") == "A" and row.get("recipient") == "B"), None)
    b_saved = next((row for row in revisions if row.get("event") == "revision_saved"
                    and row.get("actor") == "B" and row.get("revision", 0) >= 1), None)
    a_reads = _gui_reads(actions["A"])
    completed_handoff_time = (max(a_visible_time, a_message["timestamp"])
                              if a_visible_time is not None and a_message else None)
    b_reads = _gui_reads(actions["B"], completed_handoff_time) if completed_handoff_time is not None else []
    b_path_candidates = _gui_path_open_candidates(actions["B"], completed_handoff_time, root)
    lock = {}
    for role in "AB":
        executed = [row for row in actions[role] if row.get("executed")]
        locked = [row.get("input_lock") or {} for row in executed]
        enabled = [item for item in locked if item.get("enabled")]
        lock[role] = {"executed_gui_actions": len(executed),
                      "locked_actions": len(enabled),
                      "unlocked_actions": len(executed) - len(enabled),
                      "wait_s": round(sum(item.get("wait_s", 0) for item in enabled), 3),
                      "held_s": round(sum(item.get("held_s", 0) for item in enabled), 3),
                      "max_wait_s": round(max((item.get("wait_s", 0) for item in enabled), default=0), 3)}
    lock_arm = bool(provenance.get("gui_input_lock"))
    return {"run_id": root.name, "case_version": provenance.get("case_version"),
            "condition": provenance.get("condition"), "lock_arm": lock_arm,
            "oracle_joint_success": oracle.get("joint_success"),
            "A_saved_revision": a_saved.get("revision") if a_saved else None,
            "A_visible_to_B_at": a_visible_time,
            "A_message_to_B_at": a_message.get("timestamp") if a_message else None,
            "B_saved_revision": b_saved.get("revision") if b_saved else None,
            "A_delivered_note_GUI_read_evidence": a_reads,
            "B_post_revision_delivered_note_GUI_read_evidence": b_reads,
            "B_GUI_path_open_candidates": b_path_candidates,
            "manual_review_required": bool(b_path_candidates and not b_reads),
            "behavioral_handoff_verified": bool(a_saved and a_visible_time is not None and
                                                 a_message and b_reads and b_saved and
                                                 b_reads[0]["time"] <= b_saved["time"]),
            "v1p2_full_process_verified": bool(a_reads and a_saved and a_message and b_reads and b_saved and
                                               a_reads[0]["time"] <= a_message["timestamp"] and
                                               completed_handoff_time is not None and
                                               b_reads[0]["time"] <= b_saved["time"]),
            "input_lock": lock,
            "lock_contract_valid": (all(x["unlocked_actions"] == 0 for x in lock.values())
                                    if lock_arm else all(x["locked_actions"] == 0 for x in lock.values())),
            "scope": "A GUI read may occur before publication but must precede A's message for v1p2 process validity. A strict B GUI read requires a title showing the delivered path after its revision and A's message became visible. A full-path GUI Open submission followed by a matching read-only viewer is only a candidate: review its screenshot and A's delivered-note screenshot manually. No message or path string alone proves file use."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.run_root.resolve()), indent=2, ensure_ascii=False))
