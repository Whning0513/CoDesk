from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from oscombo.collab.spreadsheet_handoff_lite_v1_3 import resource_gate_amendment as gate


def test_writable_directory_requires_capacity_and_write_access(tmp_path: Path) -> None:
    assert gate.writable_path_errors(
        tmp_path, available_bytes=gate.MIN_FREE_BYTES,
        available_inodes=gate.MIN_FREE_INODES) == []
    assert gate.writable_path_errors(
        tmp_path, available_bytes=gate.MIN_FREE_BYTES - 1,
        available_inodes=gate.MIN_FREE_INODES) == ["below minimum free bytes"]
    assert gate.writable_path_errors(
        tmp_path, available_bytes=gate.MIN_FREE_BYTES,
        available_inodes=gate.MIN_FREE_INODES - 1) == ["below minimum free inodes"]


def test_missing_writable_directory_fails_closed(tmp_path: Path) -> None:
    assert gate.writable_path_errors(
        tmp_path / "missing", available_bytes=gate.MIN_FREE_BYTES,
        available_inodes=gate.MIN_FREE_INODES) == ["path unavailable"]


def test_guest_base_is_digest_pinned_without_a_free_space_requirement(tmp_path: Path) -> None:
    image = tmp_path / "guest.qcow2"
    image.write_bytes(b"small immutable test image")
    expected = hashlib.sha256(image.read_bytes()).hexdigest()
    frozen_stat = gate.verify_frozen_image_sha256(image, expected)
    gate.verify_image_unchanged(image, frozen_stat)


def test_guest_image_digest_mismatch_is_rejected(tmp_path: Path) -> None:
    image = tmp_path / "guest.qcow2"
    image.write_bytes(b"fixture")
    with pytest.raises(ValueError, match="does not match"):
        gate.verify_frozen_image_sha256(image, "0" * 64)


def test_guest_image_change_during_hash_is_rejected(tmp_path: Path, monkeypatch) -> None:
    image = tmp_path / "guest.qcow2"
    image.write_bytes(b"before")
    expected = hashlib.sha256(b"before").hexdigest()
    real_sha256 = gate.hashlib.sha256

    class MutatingHash:
        def __init__(self):
            self.inner = real_sha256()
            self.changed = False

        def update(self, chunk: bytes) -> None:
            self.inner.update(chunk)
            if not self.changed:
                image.write_bytes(b"changed-during-hash")
                self.changed = True

        def hexdigest(self) -> str:
            return self.inner.hexdigest()

    monkeypatch.setattr(gate.hashlib, "sha256", MutatingHash)
    with pytest.raises(ValueError, match="changed while it was being hashed"):
        gate.verify_frozen_image_sha256(image, expected)


def test_guest_image_requires_a_frozen_digest(tmp_path: Path) -> None:
    image = tmp_path / "guest.qcow2"
    image.write_bytes(b"fixture")
    with pytest.raises(ValueError, match="missing or malformed"):
        gate.verify_frozen_image_sha256(image, "")


def test_guest_image_symlink_is_rejected(tmp_path: Path) -> None:
    image = tmp_path / "guest.qcow2"
    target = tmp_path / "target.qcow2"
    target.write_bytes(b"fixture")
    image.symlink_to(target)
    with pytest.raises(ValueError, match="symbolic link"):
        gate.image_fingerprint(image)


def _runtime_evidence(tmp_path: Path) -> dict:
    run_root = tmp_path / "run"
    image = tmp_path / "guest.qcow2"
    image.write_bytes(b"fixture")
    (run_root / "overlay").mkdir(parents=True)
    (run_root / "cache").mkdir(parents=True)
    overlay = run_root / "overlay" / "guest.qcow2"
    overlay.write_bytes(b"overlay")
    cache = run_root / "cache" / "A"
    cache.mkdir()
    return {
        "run_root": run_root,
        "image": image,
        "overlay": overlay,
        "cache": cache,
        "mount": {"Source": str(image), "Destination": "/System.qcow2", "RW": False},
    }


def test_exact_ro_mount_and_run_owned_writes_pass(tmp_path: Path) -> None:
    row = _runtime_evidence(tmp_path)
    gate.verify_guest_mount_and_writes(
        image_path=row["image"], run_root=row["run_root"], mount=row["mount"],
        overlay_path=row["overlay"], cache_path=row["cache"])


@pytest.mark.parametrize("mutation, message", [
    (lambda m: m.update(RW=True), "read-only"),
    (lambda m: m.update(Destination="/tmp/System.qcow2"), "read-only"),
    (lambda m: m.update(Source="/missing/base.qcow2"), "source is unavailable"),
])
def test_wrong_mount_evidence_fails_closed(tmp_path: Path, mutation, message: str) -> None:
    row = _runtime_evidence(tmp_path)
    mutation(row["mount"])
    with pytest.raises(ValueError, match=message):
        gate.verify_guest_mount_and_writes(
            image_path=row["image"], run_root=row["run_root"], mount=row["mount"],
            overlay_path=row["overlay"], cache_path=row["cache"])


@pytest.mark.parametrize("field, outside", [
    ("overlay", "overlay-outside"),
    ("cache", "cache-outside"),
])
def test_writable_guest_outputs_must_be_inside_run_root(
        tmp_path: Path, field: str, outside: str) -> None:
    row = _runtime_evidence(tmp_path)
    external = tmp_path / outside
    external.mkdir()
    if field == "overlay":
        output = external / "guest.qcow2"
        output.write_bytes(b"overlay")
        row[field] = output
    else:
        row[field] = external
    with pytest.raises(ValueError, match=field):
        gate.verify_guest_mount_and_writes(
            image_path=row["image"], run_root=row["run_root"], mount=row["mount"],
            overlay_path=row["overlay"], cache_path=row["cache"])


def test_post_run_image_metadata_change_is_rejected(tmp_path: Path) -> None:
    image = tmp_path / "guest.qcow2"
    image.write_bytes(b"before")
    before = gate.image_fingerprint(image)
    image.write_bytes(b"after-content-is-different")
    with pytest.raises(ValueError, match="metadata changed"):
        gate.verify_image_unchanged(image, before)


def test_robase_runner_keeps_capacity_gate_on_writable_paths_only() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "oscombo/collab/spreadsheet_handoff_lite_v1_3/run_model_triad_robase.sh").read_text()
    assert script.count("case6_check_fs '") == 3
    assert "case6_check_fs 'Guest image'" not in script
    assert "CODESK_CASE6_V13_GUEST_IMAGE_SHA256" in script
    assert "case6_guest_image_fingerprint" in script
    assert "trap case6_exit_trap EXIT" in script
    selected_host = script.index('case6_docker_host="${DOCKER_HOST:-unix:///var/run/docker.sock}"')
    osworld_pin = script.index(': "${CODESK_CASE6_V13_OSWORLD_COMMIT:')
    osworld_diff_pin = script.index(': "${CODESK_CASE6_V13_OSWORLD_DIFF_SHA256:')
    osworld_head = script.index('git -C "$OSWORLD_DIR" rev-parse HEAD')
    osworld_match = script.index('"$case6_actual_osworld_commit" == "$CODESK_CASE6_V13_OSWORLD_COMMIT"')
    osworld_diff = script.index('git -C "$OSWORLD_DIR" diff --binary HEAD | sha256sum')
    osworld_untracked = script.index('git -C "$OSWORLD_DIR" ls-files --others --exclude-standard')
    socket_check = script.index('[[ -S "$case6_docker_socket"')
    exported_host = script.index('export DOCKER_HOST="$case6_docker_host"')
    docker_info = script.index("docker info --format '{{.DockerRootDir}}'")
    model_runner = script.index("-m oscombo.collab.spreadsheet_handoff_lite_v1_3.model_pilot")
    assert osworld_pin < osworld_diff_pin < osworld_head < osworld_match < osworld_diff < osworld_untracked < docker_info
    assert selected_host < socket_check < exported_host < model_runner
    assert all(name in script for name in (
        "osworld_commit_pin", "osworld_commit_actual",
        "osworld_diff_sha256_pin", "osworld_diff_sha256_actual"))
    assert "case6_verify_osworld_source_unchanged()" in script
    assert "if ! case6_verify_osworld_source_unchanged; then" in script
    model = (root / "oscombo/collab/spreadsheet_handoff_lite_v1_3/model_pilot.py").read_text()
    assert 'metadata["osworld_commit"] = actual_osworld_identity["commit"]' in model
    assert 'metadata["osworld_diff_sha256"] = actual_osworld_identity["diff_sha256"]' in model
    context_guard = script.index('[[ -z "${DOCKER_CONTEXT:-}" ]]')
    assert context_guard < script.index("docker info --format")
    assert '[[ "$OSCOMBO_GUEST_IMAGE" == "$case6_guest_image" ]]' in script
    assert 'export OSCOMBO_GUEST_IMAGE="$case6_guest_image"' in script
    assert "verify_frozen_image_sha256" in script
    assert "verify_image_unchanged" in script
    assert "guest_image_sha256_verified" in script
    assert "guest_image_sha256_actual" not in script
    assert "--robase-validation" in script
    assert 'for arm in isolated shared sharedlock; do' in script
    assert 'case6_check_fs "run base before $arm"' in script
    assert 'case6_check_fs "Docker data-root before $arm"' in script
    assert 'case6_check_fs "Git common directory before $arm"' in script
