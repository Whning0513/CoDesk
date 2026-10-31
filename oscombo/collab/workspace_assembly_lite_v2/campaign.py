"""Run preregistered Case 7 v2 slots in order, retaining every attempt."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import uuid

from . import analyze, audit, contract, freeze, spec


def _atomic(path: Path, value: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_slot(state: dict) -> tuple[int, str, str] | None:
    attempts = state.get("attempts", [])
    if attempts and attempts[-1].get("status") == "RUNNING":
        raise RuntimeError("previous attempt has no terminal status; inspect its exact run/process before recovery")
    completed = [item for item in attempts if item.get("status") in {"VALID_PASS", "VALID_FAIL"}]
    if len(completed) > len(freeze.SEQUENCE):
        raise RuntimeError("campaign has too many completed slots")
    for index, item in enumerate(completed):
        if (item.get("round"), item.get("arm")) != freeze.SEQUENCE[index] or item.get("slot") != index + 1:
            raise RuntimeError("completed campaign slots do not match the frozen order")
    if len(completed) == len(freeze.SEQUENCE):
        return None
    round_name, arm = freeze.SEQUENCE[len(completed)]
    return len(completed) + 1, round_name, arm


def verify_reservation(state_path: Path, freeze_path: Path, run_id: str, round_name: str, arm: str) -> None:
    state, frozen = json.loads(state_path.read_text()), json.loads(freeze_path.read_text())
    if state.get("freeze_sha256") != _sha(freeze_path) or frozen.get("formal_sequence") != [list(x) for x in freeze.SEQUENCE]:
        raise RuntimeError("campaign freeze differs from preregistration")
    attempts = state.get("attempts", [])
    if not attempts or attempts[-1].get("status") != "RUNNING":
        raise RuntimeError("formal arm has no active campaign reservation")
    last = attempts[-1]
    if (last.get("run_id"), last.get("round"), last.get("arm")) != (run_id, round_name, arm):
        raise RuntimeError("formal arm differs from its campaign reservation")
    previous = {**state, "attempts": attempts[:-1]}
    expected = expected_slot(previous)
    if expected != (last.get("slot"), round_name, arm):
        raise RuntimeError("formal arm is out of frozen order")


def classify(run_root: Path, exit_code: int) -> str:
    if not run_root.exists():
        return "NOT_STARTED" if exit_code else "INVALID_INFRA"
    result_path = run_root / "result.json"
    if not result_path.is_file() or (run_root / "failure.json").exists():
        return "INVALID_INFRA"
    try:
        result = json.loads(result_path.read_text())
        resource = json.loads((run_root / "resource_audit.json").read_text())
        contract = json.loads((run_root / "contract_audit.json").read_text())
        metrics = json.loads((run_root / "model_metrics_v2.json").read_text())
        freeze._validate_reopens(run_root, result, allow_missing_outputs=True)
    except (OSError, ValueError):
        return "INVALID_INFRA"
    if not (result.get("postscore_lifecycle_ok") is True and result.get("bridge_valid") is True
            and result.get("oracle_fixture_valid") is True
            and resource.get("valid") is True
            and contract.get("valid") is True and not metrics.get("lifecycle_errors")):
        return "INVALID_INFRA"
    status = result.get("status")
    if status == "PASS" and exit_code == 0: return "VALID_PASS"
    if status == "FAIL" and exit_code == 2: return "VALID_FAIL"
    return "INVALID_INFRA"


def _validate_formal(root: Path, frozen: dict, round_name: str, arm: str) -> None:
    side = "isolated" if arm == "isolated" else "shared"
    meta, result = freeze._common(root, frozen["source_commit"], frozen["round_seeds"][round_name],
                                  side, allow_missing_outputs=True)
    if not (meta.get("model_called") is True and meta.get("model") == "gpt-6-astra"
            and meta.get("model_effort") == "medium" and meta.get("model_timeout") == 1200
            and meta.get("diagnostic_step_limit") is None and meta.get("actor_mcp_only") is True
            and meta.get("yield_wait_lifecycle") is True and
            meta.get("gui_input_lock") is (arm == "shared_lock") and
            meta.get("role_budget_contract") == spec.ROLE_BUDGET):
        raise ValueError("formal model, prompt budget, topology or lock differs from freeze")
    freeze._guest_identity(root, frozen["image_path"], frozen["image_stat"], frozen["runtime_image"])
    for role in "AB":
        expected = hashlib.sha256(spec.model_instruction(role).encode("utf-8")).hexdigest()
        if frozen.get("prompt_sha256", {}).get(role) != expected or \
                freeze._sha(freeze._file(root, f"actor_runs/{role}/{role}/instruction.txt")) != expected:
            raise ValueError(f"formal Actor {role} prompt differs from freeze")
    if ((result.get("status") == "PASS") is not bool(result.get("oracle", {}).get("joint_success"))):
        raise ValueError("formal status disagrees with artifact Oracle")
    observed_contract = contract.audit(root)
    if not observed_contract.get("valid") or observed_contract != json.loads((root / "contract_audit.json").read_text()):
        raise ValueError("formal Actor tool or transport evidence does not verify")
    observed_behavior = audit.audit(root)
    if observed_behavior != json.loads((root / "behavioral_audit.json").read_text()):
        raise ValueError("formal behavioral audit does not reproduce")
    metrics = analyze.analyze(root)
    if metrics != json.loads((root / "model_metrics_v2.json").read_text()) or metrics.get("lifecycle_errors"):
        raise ValueError("formal model metrics do not reproduce")
    for actor in metrics["actors"].values():
        if arm == "shared_lock" and actor["locked_inputs"] != actor["executed_inputs"]:
            raise ValueError("lock did not cover every executed input")
        if arm != "shared_lock" and actor["locked_inputs"]:
            raise ValueError("unexpected input lock outside lock arm")


def _verify_repair(path: Path, invalid_run_id: str, commit: str) -> dict:
    review = json.loads(path.read_text())
    if (review.get("invalid_run_id") != invalid_run_id or review.get("resolved") is not True
            or review.get("screenshots_reviewed") is not True or
            not str(review.get("reviewer", "")).strip() or not str(review.get("reason", "")).strip()):
        raise ValueError("repair review must identify and explain the invalid attempt")
    controls = review.get("symmetric_controls", {})
    needed = {"positive_shared", "positive_isolated", "negative_shared", "negative_isolated"}
    if set(controls) != needed:
        raise ValueError("repair review requires positive and negative controls in both topologies")
    for name in sorted(needed):
        freeze._control(Path(controls[name]).resolve(), commit, name)
    return review


def run_next(freeze_path: Path, state_path: Path, repair_review: Path | None = None) -> dict:
    freeze_path, state_path = freeze_path.resolve(strict=True), state_path.resolve()
    frozen = json.loads(freeze_path.read_text())
    if frozen.get("formal_sequence") != [list(x) for x in freeze.SEQUENCE]:
        raise ValueError("freeze sequence mismatch")
    commit = subprocess.check_output(["git", "rev-parse", "--verify", "HEAD"], text=True).strip()
    if frozen.get("source_commit") != commit:
        raise ValueError("source commit changed; create a new freeze with fresh controls")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.with_suffix(state_path.suffix + ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if state_path.exists():
            state = json.loads(state_path.read_text())
            if state.get("freeze_sha256") != _sha(freeze_path):
                raise ValueError("campaign state belongs to a different freeze")
        else:
            state = {"freeze_sha256": _sha(freeze_path), "attempts": []}
            _atomic(state_path, state)
        slot = expected_slot(state)
        if slot is None:
            return {"status": "COMPLETE", "slots": len(freeze.SEQUENCE)}
        if state["attempts"] and state["attempts"][-1].get("status") == "INVALID_INFRA":
            if repair_review is None:
                raise RuntimeError("invalid attempt requires recorded symmetric repair/control review")
            review = _verify_repair(repair_review, state["attempts"][-1]["run_id"], commit)
            state["attempts"][-1]["repair_review"] = review
        index, round_name, arm = slot
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"wa-lite-v2-{arm}-{round_name}-{stamp}-{uuid.uuid4().hex[:8]}"
        attempt = {"slot": index, "round": round_name, "arm": arm, "run_id": run_id, "status": "RUNNING"}
        state["attempts"].append(attempt)
        _atomic(state_path, state)
        env = os.environ.copy()
        env.update({"CODESK_CASE7_V2_FREEZE_FILE": str(freeze_path),
                    "CODESK_CASE7_V2_CAMPAIGN_STATE": str(state_path),
                    "CODESK_CASE7_V2_RUN_ID": run_id})
        log = state_path.parent / f"{run_id}-campaign.log"
        with log.open("x", encoding="utf-8") as stream:
            proc = subprocess.Popen(["bash", "audits/three_lite_cases_20261029/run_case7_v2_one.sh", arm, round_name],
                                    env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            attempt["pid"] = proc.pid
            _atomic(state_path, state)
            code = proc.wait()
        run_root = Path("runs") / run_id
        attempt["exit_code"] = code
        attempt["status"] = classify(run_root, code)
        if attempt["status"] in {"VALID_PASS", "VALID_FAIL"}:
            try:
                _validate_formal(run_root, frozen, round_name, arm)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                attempt["status"] = "INVALID_INFRA"
                attempt["validation_error"] = f"{type(exc).__name__}: {exc}"
        attempt["campaign_log"] = str(log)
        _atomic(state_path, state)
        return dict(attempt)


def resolve_interrupted(freeze_path: Path, state_path: Path, review_path: Path) -> dict:
    """Resolve only a dead, cleaned-up attempt; never terminate a process."""
    freeze_path, state_path = freeze_path.resolve(strict=True), state_path.resolve(strict=True)
    review = json.loads(review_path.read_text())
    with state_path.with_suffix(state_path.suffix + ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = json.loads(state_path.read_text())
        if state.get("freeze_sha256") != _sha(freeze_path):
            raise ValueError("campaign state belongs to a different freeze")
        attempts = state.get("attempts", [])
        if not attempts or attempts[-1].get("status") != "RUNNING":
            raise ValueError("no interrupted running attempt")
        item = attempts[-1]
        if (review.get("run_id") != item.get("run_id") or
                not str(review.get("reason", "")).strip() or not str(review.get("reviewer", "")).strip()):
            raise ValueError("interruption review must identify the run and reviewer")
        pid = item.get("pid")
        if not isinstance(pid, int) or pid <= 0:
            raise RuntimeError("missing process ID; cannot prove the old runner stopped")
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise RuntimeError("old runner PID is still present; do not replace it")
        run_id = item["run_id"]
        live = subprocess.run(["docker", "ps", "-aq", "--filter", f"label=oscombo.run={run_id}"],
                              capture_output=True, text=True, timeout=15, check=True).stdout.strip()
        if live:
            raise RuntimeError("run-owned Docker containers still exist")
        run_root = Path("runs") / run_id
        provenance = run_root / "provenance.json"
        if provenance.exists():
            guest_data = json.loads(provenance.read_text()).get("guests", [])
            overlays = [Path(g["overlay_path"]).name for g in guest_data if g.get("overlay_path")]
            processes = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True,
                                       timeout=15, check=True).stdout.splitlines()
            if any("qemu-system-" in line and any(name in line for name in overlays) for line in processes):
                raise RuntimeError("run-owned QEMU still exists")
        item["status"] = "INVALID_INFRA" if run_root.exists() else "NOT_STARTED"
        item["interruption_review"] = review
        _atomic(state_path, state)
        return dict(item)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--repair-review", type=Path)
    parser.add_argument("--resolve-interrupted", type=Path,
                        help="review JSON after proving the exact prior RUNNING process and Guests stopped")
    parser.add_argument("--all", action="store_true", help="continue sequentially until completion or the first invalid/not-started slot")
    args = parser.parse_args()
    if args.resolve_interrupted:
        print(json.dumps(resolve_interrupted(args.freeze, args.state, args.resolve_interrupted)))
        raise SystemExit(0)
    review = args.repair_review
    while True:
        outcome = run_next(args.freeze, args.state, review)
        print(json.dumps(outcome), flush=True)
        review = None
        if not args.all or outcome["status"] not in {"VALID_PASS", "VALID_FAIL"}:
            break
