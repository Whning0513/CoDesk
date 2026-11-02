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


@pytest.mark.parametrize(("mode", "expected"), [("ok", 0), ("low_image", 4),
                                                  ("low_inode", 4), ("docker_error", 4)])
def test_case5_capacity_checks_all_backing_filesystems(tmp_path, mode, expected):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    image = tmp_path / "guest.qcow2"
    image.write_bytes(b"guest")
    docker_root, git_root = tmp_path / "docker", tmp_path / "git"
    docker_root.mkdir()
    git_root.mkdir()
    scripts = {
        "docker": '#!/bin/sh\n[ "$FAKE_MODE" != docker_error ] || exit 1\nprintf "%s\\n" "$FAKE_DOCKER_ROOT"\n',
        "git": '#!/bin/sh\nprintf "%s\\n" "$FAKE_GIT_ROOT"\n',
        "df": ('#!/bin/sh\necho "Filesystem 1K-blocks Used Available Use% Mounted"\n'
               'if [ "$1" = -Pi ]; then\n'
               '  [ "$FAKE_MODE" = low_inode ] && echo "fs 100 99 1 99% /" && exit 0\n'
               '  echo "fs 9999 1 9998 1% /"; exit 0\nfi\n'
               'if [ "$FAKE_MODE" = low_image ] && [ "$2" = "$OSCOMBO_GUEST_IMAGE" ]; then\n'
               '  echo "fs 9999 1 100 99% /"; exit 0\nfi\n'
               'echo "fs 99999999999 1 99999999998 1% /"\n'),
    }
    for name, body in scripts.items():
        target = fake_bin / name
        target.write_text(body)
        target.chmod(0o755)
    env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}", "FAKE_MODE": mode,
           "FAKE_DOCKER_ROOT": str(docker_root), "FAKE_GIT_ROOT": str(git_root),
           "OSCOMBO_GUEST_IMAGE": str(image)}
    result = subprocess.run(["bash", "-c", f"source {GATE}; case5_require_capacity"],
                            cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == expected
