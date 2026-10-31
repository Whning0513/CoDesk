"""Separate filesystems must each pass capacity and inode checks."""

from pathlib import Path
from types import SimpleNamespace
import json
import subprocess

import pytest

from oscombo.collab.workspace_assembly_lite_v2 import filesystem_capacity as capacity
from oscombo.collab.workspace_assembly_lite_v2 import resource_sampler


def test_each_backing_filesystem_has_its_own_limits(tmp_path, monkeypatch):
    paths = {label: str(tmp_path / label) for label in capacity.LABELS}
    for path in paths.values():
        Path(path).mkdir()
    status = {label: [20 * 1024**3, 5000] for label in capacity.LABELS}

    def fake_statvfs(path):
        free_bytes, free_inodes = status[Path(path).name]
        return SimpleNamespace(f_bavail=free_bytes, f_frsize=1, f_favail=free_inodes,
                               f_files=10000)

    monkeypatch.setattr(capacity.os, "statvfs", fake_statvfs)
    report = capacity.snapshot(paths)
    assert report["valid"] and set(report["filesystems"]) == set(capacity.LABELS)
    status["docker_data"][0] = 15 * 1024**3 - 1
    report = capacity.snapshot(paths)
    assert not report["valid"] and "docker_data below 15 GiB available" in report["errors"]
    status["docker_data"][0] = 20 * 1024**3
    status["git_common"][1] = 1023
    report = capacity.snapshot(paths)
    assert not report["valid"] and "git_common below 1024 available inodes" in report["errors"]
    paths["run"] = str(tmp_path / "missing")
    assert not capacity.snapshot(paths)["valid"]


def test_discovery_uses_current_docker_endpoint_and_worktree(tmp_path, monkeypatch):
    calls = []
    run_path, worktree = tmp_path / "external-runs", tmp_path / "worktree"
    run_path.mkdir()
    worktree.mkdir()

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if argv[:2] == ["docker", "info"]:
            return SimpleNamespace(stdout="/data3/docker-root\n")
        if argv[:2] == ["git", "-C"]:
            return SimpleNamespace(stdout="/data3/repo/.git\n")
        raise AssertionError(argv)

    monkeypatch.setattr(capacity.subprocess, "run", fake_run)
    paths = capacity.discover_paths(run_path, worktree)
    assert paths == {"run": str(run_path.resolve()), "docker_data": "/data3/docker-root",
                     "git_common": "/data3/repo/.git"}
    assert calls[1][2] == str(worktree.resolve())
    monkeypatch.setattr(capacity.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(
        subprocess.CalledProcessError(1, "docker")))
    with pytest.raises(subprocess.CalledProcessError):
        capacity.discover_paths(run_path, worktree)


def test_sampler_persists_preflight_and_all_filesystem_samples(tmp_path, monkeypatch):
    root = tmp_path / "run"
    root.mkdir()
    paths = {label: str(tmp_path) for label in capacity.LABELS}
    values = {"path": str(tmp_path), "device": 1, "available_bytes": 20 * 1024**3,
              "available_inodes": 10000}
    record = {"valid": True, "filesystems": {label: dict(values) for label in capacity.LABELS}}
    preflight = tmp_path / "preflight.json"
    preflight.write_text(json.dumps(record))
    monkeypatch.setenv("CODESK_CASE7_FS_PREFLIGHT", str(preflight))
    monkeypatch.setenv("CODESK_CASE7_WORKTREE", str(tmp_path))
    monkeypatch.setattr(capacity, "discover_paths", lambda run, worktree: paths)
    monkeypatch.setattr(capacity, "snapshot", lambda selected: record)
    monkeypatch.setattr(resource_sampler.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=""))
    clock = iter((0.0, 0.0, 2.0))
    monkeypatch.setattr(resource_sampler.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(resource_sampler.time, "sleep", lambda _: None)
    resource_sampler.sample(root, interval=1, max_seconds=1)
    assert json.loads((root / "filesystem_preflight.json").read_text()) == record
    row = json.loads((root / "resource_samples_v2.jsonl").read_text())
    assert row["filesystem_capacity"] == record
