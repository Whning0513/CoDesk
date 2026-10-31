"""Verify four scripted controls and independently recorded screenshot reviews."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from . import spec


def _json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _fixture_fingerprint(root: Path) -> dict | None:
    fixture = root / "fixtures"
    manifest = _json(fixture / "fixture_manifest.json")
    entries = manifest.get("fixture_sha256") or {}
    if (manifest.get("case_id") != spec.CASE_ID or manifest.get("case_version") != spec.CASE_VERSION
            or set(entries) != set(spec.FIXTURE_NAMES.values())):
        return None
    fingerprint = {}
    for name in sorted(entries):
        info = entries.get(name) or {}
        path = fixture / name
        if not path.is_file():
            return None
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if info.get("sha256") != sha or info.get("bytes") != path.stat().st_size:
            return None
        fingerprint[name] = sha
    return fingerprint


def verify(manifest: Path, run_base: Path, expected_commit: str | None = None) -> dict:
    with manifest.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    expected = {(control, condition) for control in ("positive", "wrong-units")
                for condition in ("shared", "isolated")}
    expected_order = [(control, condition) for control in ("positive", "wrong-units")
                      for condition in ("shared", "isolated")]
    unique = {(r.get("control"), r.get("condition")) for r in rows}
    actual_order = [(r.get("control"), r.get("condition")) for r in rows]
    checks, commits, fingerprints = [], set(), []
    for row in rows:
        kind, side, run_id = row.get("control"), row.get("condition"), row.get("run_id")
        root = run_base / str(run_id)
        result, sync = _json(root / "result.json"), _json(root / "workspace_sync_result.json")
        provenance = _json(root / "provenance.json")
        commit, fingerprint = provenance.get("source_commit"), _fixture_fingerprint(root)
        if isinstance(commit, str): commits.add(commit)
        if fingerprint is not None: fingerprints.append(fingerprint)
        shot_info, review = _json(root / "scripted_peer_view.json"), _json(root / "peer_view_visual_review.json")
        stale, stale_review = _json(root / "scripted_stale_view.json"), _json(root / "stale_view_visual_review.json")
        resources = _json(root / "resource_profile_check.json")
        shot_name = shot_info.get("screenshot", "")
        relative_shot = Path(shot_name)
        safe_path = bool(shot_name and not relative_shot.is_absolute() and ".." not in relative_shot.parts)
        shot = root / relative_shot if safe_path else None
        shot_sha = hashlib.sha256(shot.read_bytes()).hexdigest() if shot and shot.is_file() else None
        events_path = root / "workspace_versions/events.jsonl"
        try:
            events = [json.loads(line) for line in events_path.read_text().splitlines()]
        except (OSError, ValueError):
            events = []
        mirror_verified = any(x.get("event") == "peer_view_verified" and x.get("actor") == "A"
                              and x.get("revision") == shot_info.get("revision")
                              and x.get("sha256") == shot_info.get("sha256")
                              and x.get("peer_view_path") == shot_info.get("peer_view_path")
                              and x.get("mode") == "444"
                              and x.get("time", 0) <= shot_info.get("view_opened_at", 0)
                              for x in events)
        stale_name = stale.get("screenshot", "")
        stale_rel = Path(stale_name)
        stale_path = root / stale_rel if stale_name and not stale_rel.is_absolute() and ".." not in stale_rel.parts else None
        stale_sha = hashlib.sha256(stale_path.read_bytes()).hexdigest() if stale_path and stale_path.is_file() else None
        stale_verified = any(x.get("event") == "peer_view_verified" and x.get("actor") == "A"
                             and x.get("revision") == stale.get("revision")
                             and x.get("sha256") == stale.get("sha256")
                             and x.get("peer_view_path") == stale.get("peer_view_path")
                             and x.get("mode") == "444" for x in events)
        stale_reviewed = bool(stale_sha and stale_review.get("screenshot_sha256") == stale_sha
                              and stale_review.get("revision") == stale.get("revision") == 0
                              and stale_review.get("view_path") == stale.get("peer_view_path")
                              and stale_review.get("visible_H3_blank") is True
                              and stale_review.get("reviewed_by") and stale_review.get("reviewed_at_utc"))
        oracle = result.get("oracle") or {}
        b_checks = ((oracle.get("actors") or {}).get("B") or {}).get("checks") or {}
        expect_success = kind == "positive"
        expected_exit = "0" if expect_success else "2"
        expected_count = 2 if side == "isolated" else 1
        reset = result.get("reset") or []
        screenshot_reviewed = bool(shot_sha and review.get("screenshot_sha256") == shot_sha
                                   and review.get("revision") == shot_info.get("revision")
                                   and review.get("view_path") == shot_info.get("peer_view_path")
                                   and type(review.get("visible_H3_value")) in (int, float)
                                   and review.get("visible_H3_value") == oracle.get("expected_need_evaluator_only")
                                   and review.get("visible_H3_matches_scored_A") is True
                                   and review.get("reviewed_by") and review.get("reviewed_at_utc"))
        good = bool(row.get("exit_code") == expected_exit
                    and provenance.get("case_id") == spec.CASE_ID
                    and provenance.get("case_version") == spec.CASE_VERSION
                    and isinstance(commit, str) and len(commit) == 40
                    and (expected_commit is None or commit == expected_commit)
                    and fingerprint is not None
                    and result.get("status") == ("PASS" if expect_success else "FAIL")
                    and oracle.get("joint_success") is expect_success
                    and (expect_success or b_checks.get("correct_whole_case_order") is False)
                    and result.get("reopen_complete") is True
                    and len(reset) == expected_count and all(x.get("workspace_clean") is True for x in reset)
                    and sync.get("verified") is True
                    and (sync.get("diagnostics") or {}).get("infrastructure_review_required") is False
                    and (sync.get("persistent_history") or {}).get("history_clean") is True
                    and resources.get("resource_observation_complete") is True
                    and shot_info.get("revision", 0) >= 1 and shot_info.get("sha256")
                    and mirror_verified and screenshot_reviewed and stale_verified and stale_reviewed
                    and stale.get("stale_revision_rejected") is True
                    and stale.get("latest_revision") == shot_info.get("revision")
                    and stale.get("latest_sha256") == shot_info.get("sha256")
                    and stale.get("sha256") != shot_info.get("sha256"))
        checks.append({"run_id": run_id, "control": kind, "condition": side,
                       "valid": good, "visual_review_valid": screenshot_reviewed,
                       "stale_view_review_valid": stale_reviewed and stale_verified})
    valid = (len(rows) == 4 and len(unique) == 4 and unique == expected and actual_order == expected_order
             and all(x["valid"] for x in checks)
             and len(commits) == 1 and len(fingerprints) == 4 and all(x == fingerprints[0] for x in fingerprints))
    return {"manifest": str(manifest), "required_controls": list(map(list, expected_order)),
            "actual_order": list(map(list, actual_order)),
            "controls": checks, "valid": valid, "source_commit": next(iter(commits)) if len(commits) == 1 else None,
            "fixture_sha256": fingerprints[0] if len(fingerprints) == 4 and all(x == fingerprints[0] for x in fingerprints) else None,
            "scope": "scripted control outcomes and explicit screenshot review; no model result"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--run-base", type=Path, default=Path("runs"))
    parser.add_argument("--expected-commit")
    args = parser.parse_args()
    result = verify(args.manifest, args.run_base, args.expected_commit)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["valid"] else 3)
