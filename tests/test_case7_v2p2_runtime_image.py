from __future__ import annotations

import socket
import subprocess
from pathlib import Path

import pytest

from oscombo.collab.workspace_assembly_lite_v2p2 import runtime_image


IMAGE_ID = "sha256:" + "a" * 64


def _mock_data2_daemon(monkeypatch, tmp_path: Path, *, root_output: str | None = None,
                       info_returncode: int = 0, inspect_returncode: int = 0,
                       inspect_output: str = IMAGE_ID + "\n"):
    data2 = tmp_path / "case7-data2"
    docker_root = data2 / "data"
    docker_root.mkdir(parents=True)
    socket_path = data2 / "docker.sock"
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(socket_path))
    sock.close()

    docker_host = f"unix://{socket_path}"
    monkeypatch.setattr(runtime_image, "DATA2_DOCKER_HOST", docker_host)
    monkeypatch.setattr(runtime_image, "DATA2_DOCKER_ROOT", str(docker_root))
    monkeypatch.setenv("DOCKER_HOST", docker_host)
    # This must not redirect Docker CLI calls away from DOCKER_HOST.
    monkeypatch.setenv("DOCKER_CONTEXT", "some-other-context")

    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[:2] == ["docker", "info"]:
            return subprocess.CompletedProcess(
                args, info_returncode,
                (str(docker_root) if root_output is None else root_output) + "\n", "")
        if args[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(args, inspect_returncode, inspect_output, "mocked")
        raise AssertionError(f"unexpected subprocess: {args}")

    monkeypatch.setattr(runtime_image.subprocess, "run", fake_run)
    return docker_host, docker_root, calls


def test_resolver_pins_configured_tag_to_id_using_verified_data2_daemon(monkeypatch, tmp_path) -> None:
    docker_host, docker_root, calls = _mock_data2_daemon(monkeypatch, tmp_path)

    assert runtime_image.resolve_runtime_image("oscombo/qemu-runtime:local") == IMAGE_ID
    assert len(calls) == 2
    assert calls[0][0] == ["docker", "info", "--format", "{{.DockerRootDir}}"]
    assert calls[1][0] == ["docker", "image", "inspect", "--format", "{{.Id}}",
                            "oscombo/qemu-runtime:local"]
    for _, kwargs in calls:
        assert kwargs["env"]["DOCKER_HOST"] == docker_host
        assert "DOCKER_CONTEXT" not in kwargs["env"]
        assert kwargs["timeout"] == 15
    assert Path(calls[0][1]["env"]["DOCKER_HOST"].removeprefix("unix://")).is_socket()
    assert docker_root.is_dir()


def test_resolver_requires_the_frozen_image_id(monkeypatch, tmp_path) -> None:
    _mock_data2_daemon(monkeypatch, tmp_path)
    assert runtime_image.resolve_runtime_image("runtime:local", expected_id=IMAGE_ID) == IMAGE_ID
    with pytest.raises(runtime_image.RuntimeImageError, match="differs"):
        runtime_image.resolve_runtime_image("runtime:local", expected_id="sha256:" + "b" * 64)


@pytest.mark.parametrize("returncode,stdout", [(1, ""), (0, ""), (0, "runtime:local")])
def test_resolver_fails_closed_when_inspection_has_no_immutable_id(
        monkeypatch, tmp_path, returncode: int, stdout: str) -> None:
    _mock_data2_daemon(monkeypatch, tmp_path, inspect_returncode=returncode,
                       inspect_output=stdout)
    with pytest.raises(runtime_image.RuntimeImageError):
        runtime_image.resolve_runtime_image("runtime:local")


def test_resolver_rejects_wrong_endpoint_before_calling_docker(monkeypatch, tmp_path) -> None:
    _, _, calls = _mock_data2_daemon(monkeypatch, tmp_path)
    monkeypatch.setenv("DOCKER_HOST", "unix:///tmp/other-daemon.sock")
    with pytest.raises(runtime_image.RuntimeImageError, match="dedicated Case 7 data2 socket"):
        runtime_image.resolve_runtime_image("runtime:local")
    assert calls == []


def test_resolver_rejects_missing_data2_socket_before_calling_docker(monkeypatch, tmp_path) -> None:
    docker_host, _, calls = _mock_data2_daemon(monkeypatch, tmp_path)
    Path(docker_host.removeprefix("unix://")).unlink()
    with pytest.raises(runtime_image.RuntimeImageError, match="socket is unavailable"):
        runtime_image.resolve_runtime_image("runtime:local")
    assert calls == []


def test_resolver_rejects_wrong_docker_data_root_before_image_inspect(monkeypatch, tmp_path) -> None:
    other_root = tmp_path / "other-daemon-root"
    other_root.mkdir()
    _, _, calls = _mock_data2_daemon(monkeypatch, tmp_path, root_output=str(other_root))
    with pytest.raises(runtime_image.RuntimeImageError, match="not using the dedicated"):
        runtime_image.resolve_runtime_image("runtime:local")
    assert len(calls) == 1
    assert calls[0][0][:2] == ["docker", "info"]


def test_resolver_rejects_failed_docker_root_query_before_image_inspect(monkeypatch, tmp_path) -> None:
    _, _, calls = _mock_data2_daemon(monkeypatch, tmp_path, info_returncode=1)
    with pytest.raises(runtime_image.RuntimeImageError, match="data-root query failed"):
        runtime_image.resolve_runtime_image("runtime:local")
    assert len(calls) == 1


def test_resolver_requires_explicit_endpoint_and_well_formed_expected_id(monkeypatch, tmp_path) -> None:
    _mock_data2_daemon(monkeypatch, tmp_path)
    monkeypatch.delenv("DOCKER_HOST")
    with pytest.raises(runtime_image.RuntimeImageError, match="DOCKER_HOST"):
        runtime_image.resolve_runtime_image("runtime:local")
    monkeypatch.setenv("DOCKER_HOST", runtime_image.DATA2_DOCKER_HOST)
    with pytest.raises(runtime_image.RuntimeImageError, match="malformed"):
        runtime_image.resolve_runtime_image("runtime:local", expected_id="runtime:local")
