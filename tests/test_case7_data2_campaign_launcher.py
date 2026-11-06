from pathlib import Path
import json
import os
import shlex
import socket
import subprocess

import pytest


def test_case7_campaign_launcher_fails_closed_to_the_dedicated_data2_daemon() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "audits/three_lite_cases_20261029/run_case7_v2p2_campaign_data2.sh").read_text()
    example = (root / "configs/case7_data2.env.example.sh").read_text()
    assert "source env.local.sh" in script
    assert script.index("unset DOCKER_CONTEXT") < script.index("docker info --format")
    assert "export PYTHONDONTWRITEBYTECODE=1" in script
    assert "unix:///data2/whn/codesk-runs/case7-docker-data2/docker.sock" in script
    assert "/data2/whn/codesk-runs/case7-docker-data2/data" in script
    assert script.index("[[ -S \"$case7_socket\"") < script.index("docker info --format")
    assert 'record.get("runtime_image")' in script
    assert "docker image inspect" in script
    assert "case7_actual_runtime" in script and "case7_expected_runtime" in script
    assert script.index("docker image inspect") < script.index("exec \"$case7_python\" -m")
    assert "exec \"$case7_python\" -m oscombo.collab.workspace_assembly_lite_v2p2.campaign" in script
    assert "oscombo.collab.workspace_assembly_lite_v2.campaign" not in script
    assert "DOCKER_HOST=unix:///data2/whn/codesk-runs/case7-docker-data2/docker.sock" in example
    assert "API_KEY" not in example

    slot = (root / "audits/three_lite_cases_20261029/run_case7_v2p2_one.sh").read_text()
    unset_context = slot.index("unset DOCKER_CONTEXT")
    source_finished = slot.index("export PYTHONDONTWRITEBYTECODE=1")
    digest_resolve = slot.index("oscombo.collab.workspace_assembly_lite_v2p2.runtime_image")
    digest_export = slot.index('export OSCOMBO_RUNTIME_IMAGE="$case7_resolved_runtime_image"')
    freeze_guard = slot.index('if x.get(\'runtime_image\') != sys.argv[6]:')
    guest_launch = slot.index('--runtime "$OSCOMBO_RUNTIME_IMAGE"')
    assert unset_context < source_finished < digest_resolve < digest_export < freeze_guard < guest_launch
    assert "--expected-id \"$CODESK_CASE7_V2P2_VERIFIED_RUNTIME_IMAGE_ID\"" in slot
    assert "case7_runtime_args=(\"$OSCOMBO_RUNTIME_IMAGE\")" in slot
    assert unset_context < slot.index('docker ps --filter label=oscombo=1')


def _run_mock_campaign_launcher(tmp_path: Path, *, frozen_runtime: str | None,
                                inspected_runtime: str | None, image_missing: bool = False):
    source_root = Path(__file__).resolve().parents[1]
    source = (source_root / "audits/three_lite_cases_20261029/run_case7_v2p2_campaign_data2.sh").read_text()
    source_prefix = "/data2/whn/codesk-runs/case7-docker-data2"
    mock_root = tmp_path / "mock-data2"
    docker_root = mock_root / "data"
    docker_root.mkdir(parents=True)
    source = source.replace(source_prefix, str(mock_root))

    checkout = tmp_path / "checkout"
    launcher = checkout / "audits/three_lite_cases_20261029/run_case7_v2p2_campaign_data2.sh"
    launcher.parent.mkdir(parents=True)
    launcher.write_text(source)

    socket_path = mock_root / "docker.sock"
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(socket_path))
    sock.close()

    fake_osworld = tmp_path / "fake-osworld"
    python_bin = fake_osworld / ".venv/bin/python"
    python_bin.parent.mkdir(parents=True)
    python_bin.write_text("""#!/usr/bin/env python3
import argparse, json, os, re, sys
from pathlib import Path
if sys.argv[1:2] == ["-"]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--freeze", required=True)
    args, _ = parser.parse_known_args(sys.argv[2:])
    value = json.loads(Path(args.freeze).read_text()).get("runtime_image")
    if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise SystemExit(3)
    print(value)
elif sys.argv[1:3] == ["-m", "oscombo.collab.workspace_assembly_lite_v2p2.campaign"]:
    Path(os.environ["CASE7_TEST_CAMPAIGN_RECORD"]).write_text(json.dumps({
        "argv": sys.argv[1:],
        "runtime_image": os.environ.get("OSCOMBO_RUNTIME_IMAGE"),
        "verified_runtime_image_id": os.environ.get("CODESK_CASE7_V2P2_VERIFIED_RUNTIME_IMAGE_ID"),
    }))
else:
    raise SystemExit(90)
""")
    python_bin.chmod(0o755)

    mock_bin = tmp_path / "mock-bin"
    mock_bin.mkdir()
    docker_log = tmp_path / "docker-calls.jsonl"
    docker_bin = mock_bin / "docker"
    docker_bin.write_text("""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
if "DOCKER_CONTEXT" in os.environ:
    raise SystemExit(9)
with Path(os.environ["CASE7_TEST_DOCKER_LOG"]).open("a") as stream:
    stream.write(json.dumps(args) + "\\n")
if args[:1] == ["info"]:
    print(os.environ["CASE7_TEST_DOCKER_ROOT"])
elif args[:2] == ["image", "inspect"]:
    if os.environ.get("CASE7_TEST_IMAGE_MISSING") == "1":
        raise SystemExit(7)
    print(os.environ.get("CASE7_TEST_INSPECTED_RUNTIME", ""))
else:
    raise SystemExit(8)
""")
    docker_bin.chmod(0o755)

    env_file = checkout / "env.local.sh"
    env_file.write_text(
        f"export OSWORLD_DIR={shlex.quote(str(fake_osworld))}\n"
        "export OSCOMBO_GUEST_IMAGE=/unused/base.qcow2\n"
        "export OSCOMBO_RUNTIME_IMAGE=oscombo/qemu-runtime:local\n"
        f"export DOCKER_HOST=unix://{socket_path}\n")
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps({} if frozen_runtime is None else {"runtime_image": frozen_runtime}))
    campaign_record = tmp_path / "campaign.json"
    env = os.environ.copy()
    env.update({
        "PATH": f"{mock_bin}:{env.get('PATH', '')}",
        "CASE7_TEST_DOCKER_ROOT": str(docker_root),
        "CASE7_TEST_INSPECTED_RUNTIME": inspected_runtime or "",
        "CASE7_TEST_IMAGE_MISSING": "1" if image_missing else "0",
        "CASE7_TEST_DOCKER_LOG": str(docker_log),
        "CASE7_TEST_CAMPAIGN_RECORD": str(campaign_record),
        "DOCKER_CONTEXT": "wrong-context-must-be-ignored",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    result = subprocess.run(
        ["bash", str(launcher), "--freeze", str(freeze), "--state", str(tmp_path / "state.json")],
        env=env, capture_output=True, text=True, timeout=10)
    calls = [json.loads(line) for line in docker_log.read_text().splitlines()]
    return result, campaign_record, calls


@pytest.mark.parametrize(
    ("frozen_runtime", "inspected_runtime", "image_missing", "should_start"),
    [
        ("sha256:" + "a" * 64, "sha256:" + "a" * 64, False, True),
        ("sha256:" + "a" * 64, "sha256:" + "b" * 64, False, False),
        ("sha256:" + "a" * 64, None, True, False),
        (None, "sha256:" + "a" * 64, False, False),
    ],
    ids=("tag-resolves-to-frozen-id", "digest-mismatch", "tag-missing", "freeze-digest-missing"),
)
def test_data2_launcher_passes_verified_image_id_and_fails_closed(
        tmp_path: Path, frozen_runtime: str | None, inspected_runtime: str | None,
        image_missing: bool, should_start: bool) -> None:
    result, campaign_record, calls = _run_mock_campaign_launcher(
        tmp_path, frozen_runtime=frozen_runtime, inspected_runtime=inspected_runtime,
        image_missing=image_missing)
    assert (result.returncode == 0) is should_start
    assert campaign_record.exists() is should_start
    inspect_calls = [call for call in calls if call[:2] == ["image", "inspect"]]
    if frozen_runtime is None:
        assert not inspect_calls
    else:
        assert len(inspect_calls) == 1
        assert inspect_calls[0][-1] == "oscombo/qemu-runtime:local"
    if should_start:
        invoked = json.loads(campaign_record.read_text())
        assert invoked["argv"][:2] == ["-m", "oscombo.collab.workspace_assembly_lite_v2p2.campaign"]
        assert invoked["runtime_image"] == frozen_runtime
        assert invoked["verified_runtime_image_id"] == frozen_runtime
