"""Detached supervision and cooperative draining without a Guest or model."""
from __future__ import annotations
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from oscombo.collab.spreadsheet_handoff_lite_v1_2 import supervisor


def _fake_repo(tmp_path: Path, monkeypatch) -> Path:
    repo = tmp_path / "repo"
    package = repo / "oscombo/collab/spreadsheet_handoff_lite_v1_2"
    package.mkdir(parents=True)
    source = Path(__file__).resolve().parents[1] / supervisor.WORKER
    shutil.copy2(source, package / "supervisor_worker.sh")
    # This is an owned fake arm: it intentionally keeps running after a stop
    # request until the test releases it, then simulates finally/reset cleanup.
    runner = package / "run_guest_controls.sh"
    runner.write_text("""#!/usr/bin/env bash
set -u
trap 'printf signalled > "$CODESK_CASE6_SUPERVISOR_DIR/child-signalled"; exit 99' TERM INT
[[ -z "${AIGCBEST_API_KEY:-}" ]] && printf yes > "$CODESK_CASE6_SUPERVISOR_DIR/provider-key-absent"
printf ready > "$CODESK_CASE6_SUPERVISOR_DIR/arm-ready"
while [[ ! -f "$CODESK_CASE6_SUPERVISOR_DIR/release-arm" ]]; do sleep 0.05; done
printf cleaned > "$CODESK_CASE6_SUPERVISOR_DIR/arm-cleaned"
if [[ -f "$CODESK_CASE6_STOP_FILE" ]]; then exit 143; fi
printf started > "$CODESK_CASE6_SUPERVISOR_DIR/next-arm-started"
exit 0
""")
    runner.chmod(0o755)
    bin_dir = tmp_path / "bin"; bin_dir.mkdir()
    git = bin_dir / "git"; git.write_text("#!/bin/sh\nprintf '0123456789abcdef0123456789abcdef01234567\\n'\n"); git.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}")
    monkeypatch.setenv("AIGCBEST_API_KEY", "synthetic-secret-not-for-worker")
    return repo


def _wait_for(path: Path, timeout: float = 6) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert path.exists(), f"timed out waiting for {path}"


@pytest.mark.parametrize("how", ["request_stop", "signal_supervisor"])
def test_detached_supervisor_drains_active_arm_without_signalling_child(tmp_path, monkeypatch, how):
    repo = _fake_repo(tmp_path, monkeypatch)
    # Launch from a separate short-lived process; its exit must not end the
    # detached worker or hold its stdout pipe open.
    command = ("import json,sys; from pathlib import Path; "
               "from oscombo.collab.spreadsheet_handoff_lite_v1_2 import supervisor; "
               "print(json.dumps(supervisor.start(Path(sys.argv[1]),'controls')))" )
    launcher = subprocess.run([sys.executable, "-c", command, str(repo)],
                              capture_output=True, text=True, check=True, timeout=5)
    launched = json.loads(launcher.stdout)
    directory = Path(launched["directory"]); pid = launched["supervisor_pid"]
    try:
        _wait_for(directory / "arm-ready")
        _wait_for(directory / "runner.json")
        assert os.getsid(pid) == pid
        assert supervisor.status(repo, launched["cohort"])["supervisor_live"]
        assert (directory / "provider-key-absent").read_text() == "yes"
        if how == "request_stop":
            result = supervisor.request_stop(repo, launched["cohort"])
            assert result["stop_action"] == "drain_current_arm"
        else:
            os.kill(pid, signal.SIGTERM)
            _wait_for(directory / "stop.requested")
        # The runner remains alive and was not terminated while doing work.
        assert supervisor.status(repo, launched["cohort"])["runner_live"]
        assert not (directory / "arm-cleaned").exists()
        assert not (directory / "child-signalled").exists()
        (directory / "release-arm").write_text("go")
        _wait_for(directory / "exit-code.txt")
        assert (directory / "exit-code.txt").read_text().strip() == "143"
        assert (directory / "arm-cleaned").read_text() == "cleaned"
        assert not (directory / "next-arm-started").exists()
        state = supervisor.status(repo, launched["cohort"])
        assert state["exit_code"] == 143 and state["stop_requested"]
    finally:
        state = supervisor._identity(pid)
        if state and state["state"] != "Z":
            os.killpg(pid, signal.SIGKILL)
