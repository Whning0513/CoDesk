"""Fail-closed capacity checks for the run, Docker data and Git filesystems."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time


MIN_FREE_BYTES = 15 * 1024**3
MIN_FREE_INODES = 1024
LABELS = ("run", "docker_data", "git_common")


def discover_paths(run_path: Path, worktree: Path | None = None) -> dict[str, str]:
    """Discover real backing paths using the same Docker endpoint as the run."""
    run_path = Path(run_path).resolve(strict=True)
    worktree = Path(worktree or run_path).resolve(strict=True)
    docker_root = subprocess.run(
        ["docker", "info", "--format", "{{.DockerRootDir}}"],
        check=True, capture_output=True, text=True, timeout=15).stdout.strip()
    git_root = subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        check=True, capture_output=True, text=True, timeout=15).stdout.strip()
    if not docker_root or not git_root or not Path(docker_root).is_absolute() or not Path(git_root).is_absolute():
        raise ValueError("Docker data root and Git common directory must be absolute")
    return {"run": str(run_path), "docker_data": docker_root, "git_common": git_root}


def snapshot(paths: dict[str, str]) -> dict:
    """Sample each path independently, even when multiple paths share a device."""
    checks, errors = {}, []
    if set(paths) != set(LABELS):
        return {"valid": False, "errors": ["filesystem labels are incomplete"], "filesystems": {}}
    for label in LABELS:
        try:
            path = Path(paths[label]).resolve(strict=True)
            if not path.is_dir():
                raise NotADirectoryError(str(path))
            st, fs = path.stat(), os.statvfs(path)
            free_bytes = fs.f_bavail * fs.f_frsize
            free_inodes = fs.f_favail
            checks[label] = {"path": str(path), "device": st.st_dev,
                             "available_bytes": free_bytes, "available_inodes": free_inodes,
                             "total_inodes": fs.f_files}
            if not os.access(path, os.W_OK | os.X_OK):
                errors.append(f"{label} is not writable/searchable")
            if free_bytes < MIN_FREE_BYTES:
                errors.append(f"{label} below 15 GiB available")
            if free_inodes < MIN_FREE_INODES:
                errors.append(f"{label} below {MIN_FREE_INODES} available inodes")
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"{label} unavailable: {type(exc).__name__}")
    return {"valid": not errors, "errors": errors, "filesystems": checks,
            "minimum_available_bytes": MIN_FREE_BYTES,
            "minimum_available_inodes": MIN_FREE_INODES}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_path", type=Path)
    parser.add_argument("--worktree", type=Path)
    args = parser.parse_args()
    try:
        result = snapshot(discover_paths(args.run_path, args.worktree))
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        result = {"valid": False, "errors": [f"filesystem discovery failed: {type(exc).__name__}"],
                  "filesystems": {}}
    result["checked_at"] = time.time()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["valid"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
