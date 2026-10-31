"""Prevent restarting a whole round over an already valid sample."""
from __future__ import annotations
import argparse
import csv
import json
import re
import sys
from pathlib import Path
from . import spec
from .verify_controls import _fixture_fingerprint, verify as verify_controls


def check(audit_dir: Path, run_base: Path, mode: str, commit: str,
          expected_fixture: dict | None = None) -> dict:
    if mode not in {"pilot", "triad1", "triad2", "triad3"} or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("invalid mode or source commit")
    conflicts, unreadable = [], []
    for manifest in sorted(audit_dir.glob(f"case6-v1p2-{mode}-*.tsv")):
        try:
            with manifest.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
            for row in rows:
                if row.get("mode") != mode:
                    unreadable.append({"manifest": str(manifest), "reason": "mode mismatch"}); continue
                if row.get("exit_code") not in {"0", "2"}:
                    continue
                run_id = row.get("run_id", "")
                if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", run_id):
                    unreadable.append({"manifest": str(manifest), "reason": "invalid run_id"}); continue
                provenance = run_base / run_id / "provenance.json"
                try:
                    provenance_data = json.loads(provenance.read_text())
                    source = provenance_data.get("source_commit")
                except (OSError, ValueError, AttributeError):
                    source = None
                if source is None:
                    unreadable.append({"manifest": str(manifest), "run_id": run_id,
                                       "reason": "valid-looking sample lacks provenance"})
                elif source == commit:
                    try:
                        result = json.loads((run_base / run_id / "result.json").read_text())
                        resource = json.loads((run_base / run_id / "resource_profile_check.json").read_text())
                        sync = json.loads((run_base / run_id / "workspace_sync_result.json").read_text())
                        boundary = json.loads((run_base / run_id / "actor_tool_boundary_audit.json").read_text())
                        with (run_base / run_id / "codex_relay_events.jsonl").open() as stream:
                            relay = [json.loads(line) for line in stream]
                        forwarded = [x for x in relay if x.get("upstream_status") is not None]
                        arm = row.get("arm")
                        expected_condition = "collaborative_isolated" if arm == "isolated" else "collaborative_shared"
                        expected_guests = 2 if arm == "isolated" else 1
                        budget = 18 if mode == "pilot" else 25
                        timeout = 900 if mode == "pilot" else 1200
                        actual_fixture = _fixture_fingerprint(run_base / run_id)
                        valid = (result.get("status") == ("PASS" if row.get("exit_code") == "0" else "FAIL")
                                 and result.get("condition") == expected_condition
                                 and result.get("reopen_complete") is True
                                 and len(result.get("reset") or []) == expected_guests
                                 and all(x.get("workspace_clean") is True for x in result.get("reset") or [])
                                 and provenance_data.get("case_id") == spec.CASE_ID
                                 and provenance_data.get("case_version") == spec.CASE_VERSION
                                 and provenance_data.get("model") == "gpt-6-astra"
                                 and provenance_data.get("effort") == "medium"
                                 and provenance_data.get("endpoint") == "https://api.haogpt.net/v1"
                                 and provenance_data.get("model_request_retries") == 2
                                 and provenance_data.get("actor_mcp_only") is True
                                 and provenance_data.get("handoff_lifecycle") is True
                                 and provenance_data.get("yield_wait_lifecycle") is True
                                 and provenance_data.get("active_model_timeout_s") == timeout
                                 and provenance_data.get("effective_role_step_budget") == {"A": budget, "B": budget}
                                 and provenance_data.get("gui_input_lock") is (arm == "sharedlock")
                                 and actual_fixture is not None
                                 and (expected_fixture is None or actual_fixture == expected_fixture)
                                 and resource.get("resource_observation_complete") is True
                                 and sync.get("verified") is True and bool(forwarded)
                                 and {x.get("actor") for x in forwarded} == {"A", "B"}
                                 and all(x.get("actor_mcp_only") is True for x in forwarded)
                                 and all(not (boundary.get("actors", {}).get(role, {}).get("outside_gui_collaboration_contract") or {})
                                         and boundary.get("actors", {}).get(role, {}).get("total_tool_calls", 0) > 0
                                         for role in ("A", "B")))
                    except (OSError, ValueError, AttributeError, TypeError):
                        valid = False
                    if valid:
                        conflicts.append({"manifest": str(manifest), "run_id": run_id,
                                          "arm": row.get("arm"), "exit_code": row.get("exit_code")})
                    else:
                        unreadable.append({"manifest": str(manifest), "run_id": run_id,
                                           "reason": "valid-looking sample lacks complete evidence"})
        except (OSError, csv.Error) as exc:
            unreadable.append({"manifest": str(manifest), "reason": type(exc).__name__})
    order = {"triad1": ["isolated", "shared", "sharedlock"],
             "triad2": ["sharedlock", "shared", "isolated"],
             "triad3": ["isolated", "sharedlock", "shared"]}
    return {"mode": mode, "source_commit": commit, "valid_prior_samples": conflicts,
            "unreadable_prior_manifests": unreadable,
            "safe_to_start_full_round": not conflicts and not unreadable,
            "round_complete": (not unreadable and mode in order
                               and [x.get("arm") for x in conflicts] == order[mode])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("pilot", "triad1", "triad2", "triad3"))
    parser.add_argument("commit")
    parser.add_argument("--audit-dir", type=Path, default=Path("audits/three_lite_cases_20261029"))
    parser.add_argument("--run-base", type=Path, default=Path("runs"))
    parser.add_argument("--controls-manifest", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    controls = verify_controls(args.controls_manifest, args.run_base, args.commit) if args.controls_manifest else None
    if controls is not None and not controls.get("valid"):
        raise SystemExit("Controls are not valid for this source commit.")
    result = check(args.audit_dir, args.run_base, args.mode, args.commit,
                   controls.get("fixture_sha256") if controls else None)
    print(json.dumps(result, indent=2))
    allowed = result["round_complete"] if args.require_complete else result["safe_to_start_full_round"]
    if not allowed:
        print("Round evidence is incomplete or prior valid samples exist; inspect the manifest and coordinate a controlled resume.", file=sys.stderr)
    sys.exit(0 if allowed else 3)
