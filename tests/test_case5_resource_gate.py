"""Offline fail-closed checks for the Case 5 Guest resource gate."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "audits/three_lite_cases_20261029/case5_resource_gate.sh"


@pytest.mark.parametrize(("mode", "expected_code", "message"), [
    ("idle", 0, ""),
    ("active", 4, "Active oscombo Guest"),
    ("error", 4, "Docker Guest query failed"),
])
def test_case5_guest_gate_fails_closed(tmp_path, mode, expected_code, message):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker = fake_bin / "docker"
    docker.write_text("#!/bin/sh\n"
                      "[ \"$1\" = ps ] && [ \"$2\" = --filter ] && "
                      "[ \"$3\" = 'label=oscombo=1' ] || exit 9\n"
                      "case \"$FAKE_DOCKER_MODE\" in\n"
                      "  idle) exit 0;;\n"
                      "  active) echo guest-container-id; exit 0;;\n"
                      "  error) echo daemon-unavailable >&2; exit 1;;\n"
                      "esac\n")
    docker.chmod(0o755)
    env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}",
           "FAKE_DOCKER_MODE": mode}
    result = subprocess.run(["bash", "-c", f"source {GATE}; case5_require_no_active_oscombo_guests"],
                            cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == expected_code
    assert message in result.stderr


def test_case5_entrypoints_check_guest_gate_before_launch():
    for name in ("run_case5_isolated_control.sh", "run_case5_model.sh"):
        script = (GATE.parent / name).read_text()
        assert script.index("case5_require_no_active_oscombo_guests || exit 4") < script.index(
            "oscombo.collab.model_and_review_lite_v1.live_pilot")


def test_case5_guest_gate_rejects_missing_docker(tmp_path):
    env = {**os.environ, "PATH": str(tmp_path)}
    result = subprocess.run(["/bin/bash", "-c",
                             f"source {GATE}; case5_require_no_active_oscombo_guests"],
                            cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 4
    assert "Docker Guest query failed" in result.stderr
