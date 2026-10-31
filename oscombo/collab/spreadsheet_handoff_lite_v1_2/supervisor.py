"""Detached, run-owned Case 6 supervisor with cooperative arm-boundary stop.

Stopping requests a drain; it does not signal a model process or a Guest while
an arm is running. The worker records each child and relies on the runner's
normal finally/reset cleanup. A hard-killed supervisor requires manual review.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MODES = {"controls", "pilot", "triad1", "triad2", "triad3"}
RELATIVE_BASE = Path("audits/three_lite_cases_20261029/case6-v1p2-supervisors")
WORKER = Path("oscombo/collab/spreadsheet_handoff_lite_v1_2/supervisor_worker.sh")


def _boot_id() -> str:
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def _identity(pid: int) -> dict | None:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1].split()
        return {"pid": pid, "state": fields[0], "start_ticks": int(fields[19]), "boot_id": _boot_id()}
    except (OSError, IndexError, ValueError):
        return None


def _atomic_json(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.replace(path)


def _cohort_dir(repo: Path, cohort: str) -> Path:
    if not re.fullmatch(r"(?:controls|pilot|triad[123])-[0-9]{8}T[0-9]{6}Z-[0-9]+", cohort):
        raise ValueError("invalid cohort identifier")
    return repo.resolve() / RELATIVE_BASE / cohort


def start(repo: Path, mode: str) -> dict:
    if mode not in MODES:
        raise ValueError("invalid mode")
    repo = repo.resolve()
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{os.getpid()}{time.time_ns() % 1_000_000:06d}"
    cohort = f"{mode}-{stamp}"
    directory = _cohort_dir(repo, cohort)
    directory.mkdir(parents=True, exist_ok=False)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                            capture_output=True, text=True, timeout=10).stdout.strip()
    env = dict(os.environ)
    # The detached worker loads the provider key later from a private local file.
    for key in ("AIGCBEST_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
        env.pop(key, None)
    env.update({"CODESK_CASE6_STAMP": stamp, "CODESK_CASE6_SUPERVISOR_DIR": str(directory),
                "CODESK_CASE6_STOP_FILE": str(directory / "stop.requested"),
                "CODESK_CASE6_SUPERVISOR_COMMIT": commit})
    metadata = {"cohort": cohort, "mode": mode, "stamp": stamp, "source_commit": commit,
                "boot_id": _boot_id(), "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "log": str(directory / "supervisor.log"), "stop_file": str(directory / "stop.requested")}
    _atomic_json(directory / "supervisor.json", metadata)
    with (directory / "supervisor.log").open("xb") as log:
        process = subprocess.Popen(["bash", str(repo / WORKER), mode], cwd=repo, env=env,
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True, close_fds=True)
    identity = None
    for _ in range(50):
        identity = _identity(process.pid)
        if identity or process.poll() is not None:
            break
        time.sleep(0.02)
    metadata.update({"supervisor_pid": process.pid,
                     "start_ticks": identity.get("start_ticks") if identity else None})
    _atomic_json(directory / "supervisor.json", metadata)
    return {**metadata, "directory": str(directory)}


def status(repo: Path, cohort: str) -> dict:
    directory = _cohort_dir(repo, cohort)
    metadata = json.loads((directory / "supervisor.json").read_text())
    current = _identity(metadata.get("supervisor_pid", -1))
    live = bool(current and current["state"] != "Z" and current["boot_id"] == metadata.get("boot_id")
                and current["start_ticks"] == metadata.get("start_ticks"))
    runner_path = directory / "runner.json"
    runner = json.loads(runner_path.read_text()) if runner_path.exists() else {}
    runner_state = _identity(runner.get("runner_pid", -1)) if runner else None
    runner_live = bool(runner_state and runner_state["state"] != "Z" and runner_state["boot_id"] == runner.get("boot_id")
                       and str(runner_state["start_ticks"]) == str(runner.get("start_ticks")))
    exit_path = directory / "exit-code.txt"
    driver_path = directory / "current-driver.json"
    driver = json.loads(driver_path.read_text()) if driver_path.exists() else {}
    driver_state = _identity(driver.get("driver_pid", -1)) if driver else None
    driver_live = bool(driver_state and driver_state["state"] != "Z" and driver_state["boot_id"] == driver.get("boot_id")
                       and str(driver_state["start_ticks"]) == str(driver.get("start_ticks")))
    return {"cohort": cohort, "supervisor_live": live, "runner_live": runner_live,
            "stop_requested": (directory / "stop.requested").exists(),
            "exit_code": int(exit_path.read_text().strip()) if exit_path.exists() else None,
            "current_driver": driver or None, "current_driver_live": driver_live,
            "directory": str(directory)}


def request_stop(repo: Path, cohort: str) -> dict:
    directory = _cohort_dir(repo, cohort)
    # This is a cooperative arm-boundary stop. Never signal unverified PIDs.
    before = status(repo, cohort)
    if not before["supervisor_live"] and not before["runner_live"]:
        return {**before, "stop_action": "already_stopped"}
    try:
        with (directory / "stop.requested").open("x") as stream:
            json.dump({"source": "cooperative-stop", "requested_utc": dt.datetime.now(dt.timezone.utc).isoformat()}, stream)
            stream.write("\n")
    except FileExistsError:
        pass
    return {**status(repo, cohort), "stop_action": "drain_current_arm"}


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    launch = sub.add_parser("start"); launch.add_argument("mode", choices=sorted(MODES))
    for command in ("status", "stop"):
        child = sub.add_parser(command); child.add_argument("cohort")
    args = parser.parse_args()
    if args.action == "start": result = start(ROOT, args.mode)
    elif args.action == "status": result = status(ROOT, args.cohort)
    else: result = request_stop(ROOT, args.cohort)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
