"""Check an isolated diagnostic pilot's evidence before a frozen cohort."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path


def _json(path: Path) -> dict:
    try:
        result = json.loads(path.read_text())
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def _rows(path: Path) -> list[dict]:
    try:
        return [item for line in path.read_text().splitlines()
                if isinstance((item := json.loads(line)), dict)]
    except (OSError, ValueError):
        return []


def verify(root: Path) -> dict:
    result, sync = _json(root / "result.json"), _json(root / "workspace_sync_result.json")
    resources = _json(root / "resource_profile_check.json")
    audit, review = _json(root / "handoff_audit.json"), _json(root / "pilot_visual_review.json")
    boundary = _json(root / "actor_tool_boundary_audit.json")
    relay = _rows(root / "codex_relay_events.jsonl")
    forwarded = [x for x in relay if x.get("upstream_status") is not None]
    allowlist_ok = (bool(forwarded) and {x.get("actor") for x in forwarded} == {"A", "B"}
                    and all(x.get("actor_mcp_only") is True for x in forwarded)
                    and all(not (boundary.get("actors", {}).get(role, {}).get("outside_gui_collaboration_contract") or {})
                            and boundary.get("actors", {}).get(role, {}).get("total_tool_calls", 0) > 0
                            for role in ("A", "B")))
    candidates = audit.get("B_peer_view_screenshot_candidates") or []
    chosen = next((x for x in candidates if x.get("screenshot") == review.get("screenshot")), None)
    shot_name = (chosen or {}).get("screenshot", "")
    relative = Path(shot_name)
    path = root / relative if shot_name and not relative.is_absolute() and ".." not in relative.parts else None
    sha = hashlib.sha256(path.read_bytes()).hexdigest() if path and path.is_file() else None
    prework_candidates = audit.get("B_formula_prework_screenshot_candidates") or []
    prework = next((x for x in prework_candidates if x.get("screenshot") == review.get("prework_screenshot")), None)
    prework_name = (prework or {}).get("screenshot", "")
    prework_rel = Path(prework_name)
    prework_path = (root / prework_rel if prework_name and not prework_rel.is_absolute()
                    and ".." not in prework_rel.parts else None)
    prework_sha = hashlib.sha256(prework_path.read_bytes()).hexdigest() if prework_path and prework_path.is_file() else None
    prework_reviewed = bool(prework_sha and prework_sha == review.get("prework_screenshot_sha256")
                            and review.get("visible_F3_cost_formula") is True)
    visual = bool(sha and sha == review.get("screenshot_sha256")
                  and review.get("revision") == audit.get("latest_A_revision")
                  and review.get("view_path") == audit.get("peer_view_path")
                  and type(review.get("visible_H3_value")) in (int, float)
                  and review.get("visible_H3_value") == ((result.get("oracle") or {}).get("measured") or {}).get("saved_forecast_need")
                  and review.get("visible_H3_matches_saved_revision") is True
                  and review.get("A_messages_disclose_no_result") is True
                  and review.get("reviewed_by") and review.get("reviewed_at_utc"))
    behavior = bool(audit.get("peer_view_verified_readonly_and_delivered")
                    and audit.get("A_ready_message_after_delivery")
                    and not audit.get("A_explicit_numeric_result_in_message")
                    and audit.get("B_metadata_seen_stdout_index") is not None
                    and audit.get("B_message_read_stdout_index") is not None
                    and audit.get("B_formula_before_view_candidate_actions")
                    and audit.get("B_saved_revision_after_view_candidate") and visual and prework_reviewed)
    reset = result.get("reset") or []
    infra = bool(result.get("condition") == "collaborative_isolated"
                 and result.get("status") in {"PASS", "FAIL"}
                 and result.get("reopen_complete") is True and len(reset) == 2
                 and all(x.get("workspace_clean") is True for x in reset)
                 and sync.get("verified") is True
                 and (sync.get("diagnostics") or {}).get("infrastructure_review_required") is False
                 and (sync.get("persistent_history") or {}).get("history_clean") is True
                 and resources.get("resource_observation_complete") is True)
    return {"run_id": root.name, "artifact_status": result.get("status"),
            "infrastructure_and_resource_valid": infra, "request_tool_boundary_valid": allowlist_ok,
            "handoff_behavior_visually_reviewed": behavior,
            "gate_passed": bool(infra and allowlist_ok and behavior),
            "note": "The gate checks execution and evidence; artifact PASS is not selected or required."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root", type=Path)
    args = parser.parse_args()
    result = verify(args.run_root)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["gate_passed"] else 3)
